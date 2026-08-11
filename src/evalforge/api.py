"""FastAPI control plane for trace ingestion, evaluation, and release evidence."""

from __future__ import annotations

import hmac
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .models import AgentTrace, Scenario, new_id
from .service import EvalForgeService
from .storage import Storage


class ScenarioRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=3, max_length=120, pattern=r"^[a-zA-Z0-9._-]+$")
    title: str = Field(min_length=3, max_length=200)
    prompt: str = Field(min_length=3, max_length=20_000)
    expected_terms: list[str] = Field(min_length=1, max_length=30)
    required_tools: list[str] = Field(default_factory=list, max_length=30)
    forbidden_terms: list[str] = Field(default_factory=list, max_length=30)
    latency_budget_ms: float = Field(default=2_000, gt=0, le=300_000)
    cost_budget_usd: float = Field(default=0.01, gt=0, le=100)
    critical: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class TraceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=3, max_length=120)
    variant: str = Field(min_length=1, max_length=120)
    output: str = Field(max_length=200_000)
    tool_calls: list[str] = Field(default_factory=list, max_length=1_000)
    latency_ms: float = Field(ge=0, le=3_600_000)
    cost_usd: float = Field(ge=0, le=10_000)
    policy_violations: list[str] = Field(default_factory=list, max_length=100)
    model: str = Field(default="unknown", max_length=120)
    prompt_version: str = Field(default="unknown", max_length=120)
    metadata: dict[str, Any] = Field(default_factory=dict)


async def tenant_from_key(
    request: Request,
    x_evalforge_key: Annotated[str | None, Header()] = None,
) -> str:
    if x_evalforge_key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key")
    for configured_key, tenant in request.app.state.settings.api_keys.items():
        if hmac.compare_digest(x_evalforge_key, configured_key):
            return tenant
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")


Tenant = Annotated[str, Depends(tenant_from_key)]


def create_app(settings: Settings | None = None, storage: Storage | None = None) -> FastAPI:
    runtime_settings = settings or Settings.from_env()
    runtime_storage = storage or Storage(runtime_settings.database_path)
    service = EvalForgeService(runtime_storage)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        if storage is None:
            runtime_storage.close()

    app = FastAPI(
        title="EvalForge",
        version="1.0.0",
        description="Evidence-driven release engineering for production AI agents.",
        lifespan=lifespan,
        docs_url="/docs" if runtime_settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.settings = runtime_settings
    app.state.storage = runtime_storage
    app.state.service = service

    static_dir = Path(__file__).with_name("static")
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.middleware("http")
    async def operational_headers(request: Request, call_next):
        request_id = request.headers.get("x-request-id", uuid4().hex)
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["content-security-policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:"
        )
        return response

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "evalforge", "version": "1.0.0"}

    @app.get("/ready")
    async def ready(tenant: Tenant) -> dict[str, Any]:
        return {"status": "ready", "audit_chain_valid": runtime_storage.verify_audit_chain(tenant)}

    @app.post("/api/v1/scenarios", status_code=status.HTTP_201_CREATED)
    async def create_scenario(payload: ScenarioRequest, tenant: Tenant) -> dict[str, Any]:
        scenario = Scenario(
            id=payload.id,
            title=payload.title,
            prompt=payload.prompt,
            expected_terms=tuple(payload.expected_terms),
            required_tools=tuple(payload.required_tools),
            forbidden_terms=tuple(payload.forbidden_terms),
            latency_budget_ms=payload.latency_budget_ms,
            cost_budget_usd=payload.cost_budget_usd,
            critical=payload.critical,
            metadata=payload.metadata,
        )
        runtime_storage.upsert_scenario(tenant, scenario)
        return scenario.to_dict()

    @app.get("/api/v1/scenarios")
    async def list_scenarios(tenant: Tenant) -> list[dict[str, Any]]:
        return [item.to_dict() for item in runtime_storage.list_scenarios(tenant)]

    @app.post("/api/v1/traces", status_code=status.HTTP_201_CREATED)
    async def ingest_trace(payload: TraceRequest, tenant: Tenant) -> dict[str, Any]:
        scenario = runtime_storage.get_scenario(tenant, payload.scenario_id)
        if scenario is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "scenario not found")
        trace = AgentTrace(
            id=new_id("trace"),
            tenant_id=tenant,
            scenario_id=payload.scenario_id,
            variant=payload.variant,
            output=payload.output,
            tool_calls=tuple(payload.tool_calls),
            latency_ms=payload.latency_ms,
            cost_usd=payload.cost_usd,
            policy_violations=tuple(payload.policy_violations),
            model=payload.model,
            prompt_version=payload.prompt_version,
            metadata=payload.metadata,
        )
        runtime_storage.add_trace(trace)
        result = service.evaluator.evaluate(trace, scenario)
        return {"trace": trace.to_dict(), "evaluation": result.to_dict()}

    @app.get("/api/v1/traces/{trace_id}")
    async def get_trace(trace_id: str, tenant: Tenant) -> dict[str, Any]:
        trace = runtime_storage.get_trace(tenant, trace_id)
        if trace is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "trace not found")
        return trace.to_dict()

    @app.post("/api/v1/experiments/demo", status_code=status.HTTP_201_CREATED)
    async def run_demo(tenant: Tenant) -> dict[str, Any]:
        outcome = service.run_demo(tenant)
        return {"experiment": outcome.report.to_dict(), "decision": outcome.decision.to_dict()}

    @app.get("/api/v1/dashboard")
    async def dashboard(tenant: Tenant) -> dict[str, Any]:
        return service.dashboard(tenant)

    @app.get("/metrics", response_class=Response)
    async def metrics(tenant: Tenant) -> Response:
        counts = runtime_storage.counts(tenant)
        lines = [
            "# HELP evalforge_resources_total Persisted control-plane resources.",
            "# TYPE evalforge_resources_total gauge",
        ]
        lines.extend(
            f'evalforge_resources_total{{resource="{name}"}} {value}'
            for name, value in counts.items()
        )
        lines.append(
            f"evalforge_audit_chain_valid {int(runtime_storage.verify_audit_chain(tenant))}"
        )
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return app


app = create_app()
