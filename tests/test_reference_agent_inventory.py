from __future__ import annotations

from pebench.integrations.reference_agent import build_reference_agent_benchmark_inventory


def test_reference_agent_benchmark_inventory_shape() -> None:
    inventory = build_reference_agent_benchmark_inventory()

    assert "benchmark_roles" in inventory
    assert "runtime_snapshot" in inventory

    roles = inventory["benchmark_roles"]
    for key in [
        "baseline_assets",
        "evaluator_assets",
        "artifact_assets",
        "deferred_non_core",
    ]:
        assert key in roles
        assert isinstance(roles[key], list)
        assert roles[key], f"{key} should not be empty"

    baseline_names = {entry["name"] for entry in roles["baseline_assets"]}
    evaluator_names = {entry["name"] for entry in roles["evaluator_assets"]}

    assert "flyback_math" in baseline_names
    assert "formula_guardrails" in baseline_names
    assert "design_peer_review" in evaluator_names
    assert "simulation_consistency_checker" in evaluator_names
