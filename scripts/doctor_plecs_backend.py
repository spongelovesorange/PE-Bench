from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pebench.evaluator.simulator import plecs_xmlrpc_endpoint_from_env
from pebench.integrations.reference_agent import get_reference_agent_assets


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check optional PLECS backend readiness for PE-Bench live reruns.")
    parser.add_argument("--host", default=None, help="Override PLECS XML-RPC host for this check.")
    parser.add_argument("--port", type=int, default=None, help="Override PLECS XML-RPC port for this check.")
    parser.add_argument("--timeout-sec", type=float, default=1.0)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    parser.add_argument("--fail-if-unavailable", action="store_true", help="Return non-zero if no live backend is ready.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_human_report(report)
    if args.fail_if_unavailable and not report["ready_for_live_simulation"]:
        return 1
    return 0


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    env_host, env_port = plecs_xmlrpc_endpoint_from_env()
    host = args.host or env_host
    port = int(args.port or env_port)
    assets = get_reference_agent_assets()
    xmlrpc_module_available = bool(assets["available"].get("plecs_xmlrpc"))
    mcp_module_available = bool(assets["available"].get("plecs_mcp"))
    xmlrpc_port_open = _port_open(host, port, timeout=float(args.timeout_sec))
    mcp_configured = bool(
        str(os.getenv("REFERENCE_AGENT_PLECS_MCP_COMMAND", "")).strip()
        or str(os.getenv("REFERENCE_AGENT_PLECS_MCP_ARGS", "")).strip()
    )
    live_env_enabled = str(
        os.getenv("PEBENCH_ENABLE_LIVE_SIM") or os.getenv("FLYBACKBENCH_ENABLE_LIVE_SIM") or ""
    ).strip().lower() in {"1", "true", "yes", "on"}
    ready = (xmlrpc_module_available and xmlrpc_port_open) or (mcp_module_available and mcp_configured)
    return {
        "ready_for_live_simulation": ready,
        "recommended_simulator_mode": "live" if ready else "stub",
        "xmlrpc": {
            "host": host,
            "port": port,
            "module_available": xmlrpc_module_available,
            "port_open": xmlrpc_port_open,
        },
        "mcp": {
            "module_available": mcp_module_available,
            "command_configured": mcp_configured,
        },
        "environment": {
            "PEBENCH_ENABLE_LIVE_SIM": live_env_enabled,
            "PEBENCH_PLECS_XMLRPC_HOST_set": "PEBENCH_PLECS_XMLRPC_HOST" in os.environ,
            "PEBENCH_PLECS_XMLRPC_PORT_set": "PEBENCH_PLECS_XMLRPC_PORT" in os.environ,
            "REFERENCE_AGENT_PLECS_MCP_COMMAND_set": "REFERENCE_AGENT_PLECS_MCP_COMMAND" in os.environ,
            "REFERENCE_AGENT_PLECS_MCP_ARGS_set": "REFERENCE_AGENT_PLECS_MCP_ARGS" in os.environ,
        },
        "notes": [
            "PLECS is optional for reviewer smoke tests; stub mode is the default reproducibility path.",
            "Live XML-RPC checks require PLECS to be running locally and listening on the configured host/port.",
            "No API keys or local paths are printed by this doctor.",
        ],
    }


def print_human_report(report: dict[str, Any]) -> None:
    xmlrpc = report["xmlrpc"]
    mcp = report["mcp"]
    print("PE-Bench PLECS backend doctor")
    print(f"ready_for_live_simulation: {report['ready_for_live_simulation']}")
    print(f"recommended_simulator_mode: {report['recommended_simulator_mode']}")
    print(
        "xmlrpc: "
        f"{xmlrpc['host']}:{xmlrpc['port']} "
        f"module_available={xmlrpc['module_available']} "
        f"port_open={xmlrpc['port_open']}"
    )
    print(
        "mcp: "
        f"module_available={mcp['module_available']} "
        f"command_configured={mcp['command_configured']}"
    )
    if not report["ready_for_live_simulation"]:
        print("live backend unavailable; use --simulator-mode stub or configure PLECS before live reruns")


def _port_open(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
