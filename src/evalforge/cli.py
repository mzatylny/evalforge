"""Command-line entrypoint for local demos and operations."""

from __future__ import annotations

import argparse
import json

from .service import EvalForgeService
from .storage import Storage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalforge", description="Agent reliability control tower"
    )
    parser.add_argument("--database", default="evalforge.db", help="SQLite database path")
    subcommands = parser.add_subparsers(dest="command", required=True)
    demo = subcommands.add_parser("demo", help="run a deterministic baseline/candidate evaluation")
    demo.add_argument("--tenant", default="portfolio")
    verify = subcommands.add_parser("verify-audit", help="verify the tenant audit hash chain")
    verify.add_argument("--tenant", default="portfolio")
    serve = subcommands.add_parser("serve", help="start the API and dashboard")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=8000, type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "serve":
        import uvicorn

        uvicorn.run("evalforge.api:app", host=args.host, port=args.port, reload=False)
        return 0

    storage = Storage(args.database)
    try:
        if args.command == "demo":
            outcome = EvalForgeService(storage).run_demo(args.tenant)
            print(
                json.dumps(
                    {
                        "experiment": outcome.report.to_dict(),
                        "decision": outcome.decision.to_dict(),
                    },
                    indent=2,
                )
            )
            return 0 if outcome.decision.status in {"promoted", "blocked"} else 2
        valid = storage.verify_audit_chain(args.tenant)
        print(json.dumps({"tenant": args.tenant, "audit_chain_valid": valid}))
        return 0 if valid else 1
    finally:
        storage.close()


if __name__ == "__main__":
    raise SystemExit(main())
