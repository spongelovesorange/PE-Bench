from __future__ import annotations

import json
from dataclasses import dataclass
from random import Random
from typing import Any

import httpx
from openai import OpenAI

from pebench.baselines.llm_client import _chat_json, _extract_json_object, load_runtime_config, should_use_llm
from pebench.tasks.inverter_schema import INVERTER_COMPONENT_SLOTS
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_INVERTER_CATALOG_PATH


INVERTER_BASELINES = [
    "direct_prompting",
    "structured_output_only",
    "text_only_self_refine",
    "single_agent_same_tools",
    "single_agent_retry",
    "generic_two_role_mas",
    "pe_gpt_style",
    "reference_agent",
]
EXPECTED_BOM_SLOTS = list(INVERTER_COMPONENT_SLOTS.keys())


def _catalog() -> dict[str, list[dict[str, Any]]]:
    return load_yaml(DEFAULT_INVERTER_CATALOG_PATH)


def _catalog_prompt_payload() -> dict[str, list[dict[str, Any]]]:
    catalog = _catalog()
    allowed = {
        "part_id",
        "description",
        "technology",
        "voltage_rating_v",
        "current_rating_a",
        "ripple_current_a",
        "capacitance_uf",
        "isolation_voltage_v",
        "peak_drive_current_a",
        "bandwidth_khz",
        "cost_usd",
    }
    return {
        category: [{key: value for key, value in row.items() if key in allowed} for row in rows]
        for category, rows in catalog.items()
        if category != "version"
    }


def _as_float(mapping: dict[str, Any], key: str, fallback: float | None = None) -> float:
    value = mapping.get(key)
    if value is None:
        if fallback is None:
            raise ValueError(f"Missing numeric field '{key}'")
        return round(float(fallback), 4)
    return round(float(value), 4)


def _normalize_llm_partial(raw: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    theory = raw.get("theoretical_design", {})
    claims = raw.get("final_claimed_metrics", {})
    decision = raw.get("topology_decision", {})
    uncertainty = raw.get("uncertainty_or_escalation_flag", {})
    reference = task["reference_design"]
    expected = reference["expected_metrics"]

    normalized_bom: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw.get("bom", []):
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        part_id = str(item.get("part_id") or "").strip()
        if category and part_id and category not in seen:
            normalized_bom.append({"category": category, "part_id": part_id})
            seen.add(category)
    missing = [slot for slot in EXPECTED_BOM_SLOTS if slot not in seen]
    if missing:
        raise ValueError(f"LLM inverter output missed BOM slots: {missing}")

    return {
        "design_rationale": str(raw.get("design_rationale") or "").strip()
        or "LLM-generated three-phase inverter candidate.",
        "topology_decision": {
            "selected_topology": str(decision.get("selected_topology") or theory.get("topology") or "three_phase_inverter"),
            "reason": str(decision.get("reason") or "selected from task requirements"),
        },
        "theoretical_design": {
            "topology": str(theory.get("topology") or "three_phase_inverter"),
            "dc_link_voltage_v": _as_float(theory, "dc_link_voltage_v", float(reference["dc_link_voltage_v"])),
            "modulation_index": _as_float(theory, "modulation_index", float(reference["modulation_index"])),
            "switching_frequency_khz": _as_float(
                theory,
                "switching_frequency_khz",
                float(reference["switching_frequency_khz"]),
            ),
            "phase_current_rms_a": _as_float(theory, "phase_current_rms_a", float(reference["phase_current_rms_a"])),
        },
        "bom": normalized_bom,
        "final_claimed_metrics": {
            "efficiency_percent": _as_float(claims, "efficiency_percent", float(expected["efficiency_percent"])),
            "thd_percent": _as_float(claims, "thd_percent", float(expected["thd_percent"])),
            "dc_link_ripple_a": _as_float(claims, "dc_link_ripple_a", float(expected["dc_link_ripple_a"])),
            "device_stress_v": _as_float(claims, "device_stress_v", float(expected["device_stress_v"])),
            "phase_current_rms_a": _as_float(claims, "phase_current_rms_a", float(expected["phase_current_rms_a"])),
            "estimated_cost_usd": _as_float(claims, "estimated_cost_usd", float(reference["cost_proxy_usd"])),
        },
        "uncertainty_or_escalation_flag": {
            "escalate": bool(uncertainty.get("escalate")),
            "reason": str(uncertainty.get("reason") or "").strip() or None,
        },
    }


def _generate_llm_partial(
    *,
    task: dict[str, Any],
    baseline_name: str,
    model_name: str,
    seed: int,
    feedback_history: list[dict[str, Any]] | None,
    enable_component_grounding: bool,
) -> dict[str, Any]:
    config = load_runtime_config(model_name)
    visible_task = {
        "task_id": task["task_id"],
        "topology": task["topology"],
        "natural_language_spec": task["natural_language_spec"],
        "difficulty_tier": task["difficulty_tier"],
        "structured_spec": task["structured_spec"],
        "closure_gates": task["closure_gates"],
        "known_failure_modes": task["known_failure_modes"],
    }
    payload: dict[str, Any] = {
        "seed_hint": seed,
        "task": visible_task,
        "baseline_name": baseline_name,
        "instructions": [
            "Return one three-phase two-level inverter design candidate as valid JSON only.",
            "Expose topology decision, DC-link assumptions, modulation index, phase current, BOM, claimed metrics, and escalation behavior.",
            "Claims must be conservative and supportable from the theory and selected parts.",
            "Escalate unsafe or under-supported designs rather than reporting unsupported success.",
        ],
        "response_contract": {
            "design_rationale": "short paragraph",
            "topology_decision": {"selected_topology": "three_phase_inverter", "reason": "string"},
            "theoretical_design": {
                "topology": "three_phase_inverter",
                "dc_link_voltage_v": "float",
                "modulation_index": "float",
                "switching_frequency_khz": "float",
                "phase_current_rms_a": "float",
            },
            "bom": [{"category": slot, "part_id": "string"} for slot in EXPECTED_BOM_SLOTS],
            "final_claimed_metrics": {
                "efficiency_percent": "float",
                "thd_percent": "float",
                "dc_link_ripple_a": "float",
                "device_stress_v": "float",
                "phase_current_rms_a": "float",
                "estimated_cost_usd": "float",
            },
            "uncertainty_or_escalation_flag": {"escalate": "bool", "reason": "string or null"},
        },
    }
    if enable_component_grounding:
        payload["component_catalog"] = _catalog_prompt_payload()
    if feedback_history:
        payload["retry_feedback"] = feedback_history
    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        http_client=httpx.Client(timeout=config.timeout_seconds, trust_env=False, http2=False),
    )
    content = _chat_json(
        client=client,
        config=config,
        messages=[
            {"role": "system", "content": "You are generating PE-Bench inverter candidates. Return JSON only."},
            {"role": "user", "content": json.dumps(payload, indent=2, sort_keys=True)},
        ],
        seed=seed,
    )
    partial = _normalize_llm_partial(_extract_json_object(content), task)
    partial["metadata"] = {
        "llm_generation": {
            "enabled": True,
            "provider": config.provider_label,
            "base_url": config.base_url,
            "prompt_mode": baseline_name,
            "seed_hint": seed,
            "task_bank": "three_phase_inverter",
        }
    }
    return partial


@dataclass
class InverterBaseline:
    name: str
    noise_scale: float
    claim_bias: float
    prefers_safe_parts: bool
    escalates_on_stress: bool
    disable_component_grounding: bool = False
    disable_formula_guardrails: bool = False
    disable_correction_memory: bool = False

    @property
    def run_name(self) -> str:
        suffixes: list[str] = []
        if self.disable_formula_guardrails:
            suffixes.append("wo_formula_guardrails")
        if self.disable_component_grounding:
            suffixes.append("wo_component_grounding")
        if self.disable_correction_memory:
            suffixes.append("wo_correction_memory")
        return self.name if not suffixes else f"{self.name}__{'__'.join(suffixes)}"

    def _build_candidate(
        self,
        *,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str,
        partial: dict[str, Any],
        attempt_index: int,
        feedback_history: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        spec = task["structured_spec"]
        metadata = dict(partial.get("metadata", {}))
        metadata.update(
            {
                "task_bank": "three_phase_inverter",
                "attempt_index": attempt_index,
                "retry_enabled": self.name == "single_agent_retry",
                "retry_history": list(feedback_history or []),
                "baseline_family": self.name,
                "ablations": {
                    "disable_formula_guardrails": self.disable_formula_guardrails,
                    "disable_component_grounding": self.disable_component_grounding,
                    "disable_correction_memory": self.disable_correction_memory,
                },
            }
        )
        return {
            "task_id": task["task_id"],
            "baseline_name": self.run_name,
            "model_name": model_name,
            "seed": seed,
            "parsed_spec": {
                "dc_link_voltage_v": dict(spec["dc_link_voltage_v"]),
                "output": dict(spec["output"]),
                "targets": dict(spec["targets"]),
            },
            "topology_decision": partial["topology_decision"],
            "design_rationale": partial["design_rationale"],
            "theoretical_design": partial["theoretical_design"],
            "bom": partial["bom"],
            "simulation_config": {"mode": simulator_mode, "max_sim_calls": 1, "max_iterations": attempt_index},
            "final_claimed_metrics": partial["final_claimed_metrics"],
            "uncertainty_or_escalation_flag": partial["uncertainty_or_escalation_flag"],
            "metadata": metadata,
        }

    def generate(
        self,
        *,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str = "stub",
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if should_use_llm(model_name) and self.name != "reference_agent":
            partial = _generate_llm_partial(
                task=task,
                baseline_name=self.name,
                model_name=model_name,
                seed=seed,
                feedback_history=feedback_history,
                enable_component_grounding=not self.disable_component_grounding,
            )
            return self._build_candidate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                partial=partial,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )

        rng = Random(f"{task['task_id']}:{self.run_name}:{model_name}:{seed}:attempt{attempt_index}")
        reference = task["reference_design"]
        expected = reference["expected_metrics"]
        difficulty_multiplier = {"easy": 1.0, "medium": 1.25, "hard": 1.6, "stress": 2.1}[task["difficulty_tier"]]
        noise = self.noise_scale * difficulty_multiplier
        if feedback_history and not self.disable_correction_memory:
            noise *= max(0.62, 1.0 - 0.12 * len(feedback_history))
        claim_bias = self.claim_bias + (1.2 if self.disable_formula_guardrails else 0.0)
        selected = dict(reference["selected_components"])
        if self.disable_component_grounding:
            selected = {slot: f"unverified_{slot}_three_phase_inverter" for slot in EXPECTED_BOM_SLOTS}
        elif not self.prefers_safe_parts:
            for slot in ("power_module", "dc_link_capacitor"):
                if task["difficulty_tier"] in {"hard", "stress"} and rng.random() < 0.35:
                    selected[slot] = next(iter(_catalog()[INVERTER_COMPONENT_SLOTS[slot]]))["part_id"]
        partial = {
            "design_rationale": f"{self.name} generated a three-phase inverter candidate with seed={seed}.",
            "topology_decision": {
                "selected_topology": "three_phase_inverter",
                "reason": "selected from DC-AC three-phase requirement",
            },
            "theoretical_design": {
                "topology": "three_phase_inverter",
                "dc_link_voltage_v": round(float(reference["dc_link_voltage_v"]) * (1.0 + rng.uniform(-0.05 * noise, 0.05 * noise)), 2),
                "modulation_index": round(float(reference["modulation_index"]) + rng.uniform(-0.04 * noise, 0.08 * noise), 3),
                "switching_frequency_khz": round(float(reference["switching_frequency_khz"]) * (1.0 + rng.uniform(-0.5 * noise, 0.5 * noise)), 2),
                "phase_current_rms_a": round(float(reference["phase_current_rms_a"]) * (1.0 + rng.uniform(-0.2 * noise, 0.8 * noise)), 3),
            },
            "bom": [{"category": slot, "part_id": selected[slot]} for slot in EXPECTED_BOM_SLOTS],
            "final_claimed_metrics": {
                "efficiency_percent": round(float(expected["efficiency_percent"]) + claim_bias - 2.5 * noise + rng.uniform(-0.5, 0.6), 2),
                "thd_percent": round(max(0.5, float(expected["thd_percent"]) * (1.0 + 0.55 * noise) - 0.2 * claim_bias), 3),
                "dc_link_ripple_a": round(float(expected["dc_link_ripple_a"]) * (1.0 + 0.55 * noise), 3),
                "device_stress_v": round(float(expected["device_stress_v"]) * (1.0 + 0.18 * noise), 3),
                "phase_current_rms_a": round(float(expected["phase_current_rms_a"]) * (1.0 + 0.22 * noise), 3),
                "estimated_cost_usd": round(float(reference["cost_proxy_usd"]) * (1.05 if self.prefers_safe_parts else 0.88), 2),
            },
            "uncertainty_or_escalation_flag": {
                "escalate": self.escalates_on_stress and task["difficulty_tier"] == "stress",
                "reason": "stress inverter task flagged for review"
                if self.escalates_on_stress and task["difficulty_tier"] == "stress"
                else None,
            },
            "metadata": {"llm_generation": {"enabled": False}},
        }
        return self._build_candidate(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )


def get_inverter_baseline(name: str, **kwargs: object) -> InverterBaseline:
    profiles = {
        "direct_prompting": dict(noise_scale=0.17, claim_bias=2.4, prefers_safe_parts=False, escalates_on_stress=False),
        "structured_output_only": dict(noise_scale=0.15, claim_bias=2.0, prefers_safe_parts=False, escalates_on_stress=False),
        "text_only_self_refine": dict(noise_scale=0.14, claim_bias=1.8, prefers_safe_parts=False, escalates_on_stress=False),
        "single_agent_same_tools": dict(noise_scale=0.10, claim_bias=1.0, prefers_safe_parts=True, escalates_on_stress=False),
        "single_agent_retry": dict(noise_scale=0.085, claim_bias=0.65, prefers_safe_parts=True, escalates_on_stress=True),
        "generic_two_role_mas": dict(noise_scale=0.09, claim_bias=0.75, prefers_safe_parts=True, escalates_on_stress=True),
        "pe_gpt_style": dict(noise_scale=0.08, claim_bias=0.5, prefers_safe_parts=True, escalates_on_stress=True),
        "reference_agent": dict(noise_scale=0.035, claim_bias=0.0, prefers_safe_parts=True, escalates_on_stress=True),
    }
    if name not in profiles:
        raise ValueError(f"Unknown inverter baseline '{name}'. Available: {sorted(profiles)}")
    profile = dict(profiles[name])
    profile.update(kwargs)
    return InverterBaseline(name=name, **profile)
