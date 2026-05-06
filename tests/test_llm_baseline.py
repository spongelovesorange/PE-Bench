from __future__ import annotations

from pebench.adapters.registry import get_baseline
from pebench.baselines.llm_client import _extract_json_object, load_runtime_config
from pebench.tasks.schema import iter_task_files, load_task
from pebench.utils.paths import DEFAULT_TASK_DIR


def test_load_runtime_config_normalizes_openai_compatible_base_url(monkeypatch) -> None:
    monkeypatch.setenv("PEBENCH_LLM_API_KEY", "test-key")
    monkeypatch.setenv("PEBENCH_LLM_BASE_URL", "https://api.example.com")

    config = load_runtime_config("demo-model")

    assert config.base_url == "https://api.example.com/v1"
    assert config.provider_label == "openai_compatible"
    assert config.model_name == "demo-model"


def test_extract_json_object_handles_code_fences() -> None:
    parsed = _extract_json_object(
        """```json
        {"ok": true, "value": 3}
        ```"""
    )
    assert parsed == {"ok": True, "value": 3}


def test_direct_prompting_uses_llm_payload_when_model_is_not_heuristic(monkeypatch) -> None:
    task = load_task(iter_task_files(DEFAULT_TASK_DIR)[0])

    def fake_payload(**_: object) -> dict[str, object]:
        return {
            "design_rationale": "LLM candidate",
            "theoretical_design": {
                "topology": "flyback",
                "turns_ratio_primary_to_secondary": 7.2,
                "magnetizing_inductance_uh": 320.0,
                "switching_frequency_khz": 82.0,
                "duty_cycle_max": 0.39,
                "primary_peak_current_a": 1.95,
            },
            "bom": [
                {"category": "controller", "part_id": "UCC28740"},
                {"category": "mosfet", "part_id": "IPD60R380P7"},
                {"category": "diode", "part_id": "STPS8H100"},
                {"category": "output_capacitor", "part_id": "EEU-FR1E221"},
                {"category": "core", "part_id": "EFD20_3C95"},
            ],
            "final_claimed_metrics": {
                "efficiency_percent": 84.2,
                "ripple_mv": 38.0,
                "mosfet_voltage_stress_v": 470.0,
                "diode_reverse_voltage_v": 66.0,
                "flux_density_mt": 176.0,
                "estimated_cost_usd": 4.15,
            },
            "uncertainty_or_escalation_flag": {
                "escalate": False,
                "reason": None,
            },
            "metadata": {
                "llm_generation": {
                    "enabled": True,
                    "provider": "mock",
                }
            },
        }

    monkeypatch.setattr("pebench.baselines.methods.generate_llm_candidate_payload", fake_payload)

    candidate = get_baseline("direct_prompting").generate(
        task=task,
        model_name="demo-model",
        seed=11,
        simulator_mode="stub",
    )

    assert candidate["design_rationale"] == "LLM candidate"
    assert candidate["metadata"]["llm_generation"]["enabled"] is True
    assert candidate["simulation_config"]["mode"] == "stub"
    assert candidate["model_name"] == "demo-model"


def test_pe_gpt_style_baseline_uses_llm_payload_when_model_is_not_heuristic(monkeypatch) -> None:
    task = load_task(iter_task_files(DEFAULT_TASK_DIR)[0])

    def fake_payload(**_: object) -> dict[str, object]:
        return {
            "design_rationale": "PE-GPT-style candidate",
            "theoretical_design": {
                "topology": "flyback",
                "turns_ratio_primary_to_secondary": 6.8,
                "magnetizing_inductance_uh": 310.0,
                "switching_frequency_khz": 88.0,
                "duty_cycle_max": 0.41,
                "primary_peak_current_a": 1.88,
            },
            "bom": [
                {"category": "controller", "part_id": "UCC28740"},
                {"category": "mosfet", "part_id": "IPD60R380P7"},
                {"category": "diode", "part_id": "STPS8H100"},
                {"category": "output_capacitor", "part_id": "EEU-FR1E221"},
                {"category": "core", "part_id": "EFD20_3C95"},
            ],
            "final_claimed_metrics": {
                "efficiency_percent": 85.0,
                "ripple_mv": 31.0,
                "mosfet_voltage_stress_v": 455.0,
                "diode_reverse_voltage_v": 68.0,
                "flux_density_mt": 170.0,
                "estimated_cost_usd": 4.4,
            },
            "uncertainty_or_escalation_flag": {
                "escalate": False,
                "reason": None,
            },
            "metadata": {
                "llm_generation": {
                    "enabled": True,
                    "provider": "mock",
                }
            },
        }

    monkeypatch.setattr("pebench.baselines.methods.generate_llm_candidate_payload", fake_payload)

    candidate = get_baseline("pe_gpt_style").generate(
        task=task,
        model_name="demo-model",
        seed=7,
        simulator_mode="stub",
    )

    assert candidate["design_rationale"] == "PE-GPT-style candidate"
    assert candidate["metadata"]["pe_gpt_style_integration"]["enabled"] is True
    assert candidate["metadata"]["pe_gpt_style_integration"]["mode"] == "public_framework_prompt_adapter"
    assert candidate["simulation_config"]["mode"] == "stub"
