from __future__ import annotations

import json

from evalforge.cli import build_parser, main


def test_parser_requires_command() -> None:
    parser = build_parser()
    assert parser.prog == "evalforge"


def test_demo_and_audit_commands(tmp_path, capsys) -> None:
    database = str(tmp_path / "evalforge.db")
    assert main(["--database", database, "demo", "--tenant", "test"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["decision"]["status"] == "blocked"
    assert main(["--database", database, "verify-audit", "--tenant", "test"]) == 0
    assert json.loads(capsys.readouterr().out)["audit_chain_valid"] is True


def test_serve_delegates_to_uvicorn(monkeypatch) -> None:
    called = {}

    def fake_run(app, **kwargs):
        called.update({"app": app, **kwargs})

    monkeypatch.setattr("uvicorn.run", fake_run)
    assert main(["serve", "--host", "0.0.0.0", "--port", "9999"]) == 0
    assert called == {"app": "evalforge.api:app", "host": "0.0.0.0", "port": 9999, "reload": False}
