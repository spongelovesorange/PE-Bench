from __future__ import annotations

from pebench.evaluator import simulator


def test_plecs_xmlrpc_endpoint_uses_pebench_env(monkeypatch) -> None:
    monkeypatch.setenv("PEBENCH_PLECS_XMLRPC_HOST", "127.0.0.2")
    monkeypatch.setenv("PEBENCH_PLECS_XMLRPC_PORT", "12345")

    assert simulator.plecs_xmlrpc_endpoint_from_env() == ("127.0.0.2", 12345)


def test_plecs_auto_probe_uses_configured_xmlrpc_port(monkeypatch) -> None:
    checked: list[tuple[str, int]] = []

    def fake_port_open(host: str, port: int, timeout: float = 0.15) -> bool:
        checked.append((host, port))
        return True

    monkeypatch.setenv("PEBENCH_PLECS_XMLRPC_HOST", "localhost")
    monkeypatch.setenv("PEBENCH_PLECS_XMLRPC_PORT", "4567")
    monkeypatch.setattr(simulator, "_port_open", fake_port_open)

    should_attempt, reason = simulator._should_attempt_live(
        "auto",
        {"available": {"plecs_xmlrpc": True, "plecs_mcp": False}, "modules": {}},
    )

    assert should_attempt is True
    assert reason is None
    assert checked == [("localhost", 4567)]
