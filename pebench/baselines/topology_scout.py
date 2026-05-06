from __future__ import annotations

import json
from dataclasses import dataclass
from random import Random
from typing import Any

import httpx
from openai import OpenAI

from pebench.baselines.llm_client import (
    _chat_json,
    _extract_json_object,
    load_runtime_config,
    should_use_llm,
)
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_SCOUT_CATALOG_PATH


SCOUT_BASELINES = [
    "direct_prompting",
    "structured_output_only",
    "text_only_self_refine",
    "single_agent_same_tools",
    "single_agent_retry",
    "generic_two_role_mas",
    "pe_gpt_style",
    "reference_agent",
]
EXPECTED_BOM_SLOTS = ["controller", "switch", "diode", "inductor", "output_capacitor"]


def _catalog() -> dict[str, list[dict[str, Any]]]:
    return load_yaml(DEFAULT_SCOUT_CATALOG_PATH)


def _catalog_prompt_payload() -> dict[str, list[dict[str, Any]]]:
    catalog = _catalog()
    return {
        category: [
            {key: value for key, value in row.items() if key in {"part_id", "family", "voltage_rating_v", "current_rating_a", "saturation_current_a", "capacitance_uf", "cost_usd"}}
            for row in rows
        ]
        for category, rows in catalog.items()
        if category != "version"
    }


def _catalog_by_slot() -> dict[str, list[dict[str, Any]]]:
    catalog = _catalog()
    return {
        "controller": catalog["controllers"],
        "switch": catalog["switches"],
        "diode": catalog["diodes"],
        "inductor": catalog["inductors"],
        "output_capacitor": catalog["output_capacitors"],
    }


def _as_float(mapping: dict[str, Any], key: str, fallback: float | None = None) -> float:
    value = mapping.get(key)
    if value is None:
        if fallback is None:
            raise ValueError(f"Missing numeric field '{key}'")
        return fallback
    return round(float(value), 4)


def _normalize_llm_partial(raw: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    theory = raw.get("theoretical_design", {})
    claims = raw.get("final_claimed_metrics", {})
    decision = raw.get("topology_decision", {})
    uncertainty = raw.get("uncertainty_or_escalation_flag", {})
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
        raise ValueError(f"LLM topology scout output missed BOM slots: {missing}")
    reference = task["reference_design"]
    return {
        "design_rationale": str(raw.get("design_rationale") or "").strip() or "LLM-generated PE topology scout candidate.",
        "topology_decision": {
            "selected_topology": str(decision.get("selected_topology") or theory.get("topology") or task["topology"]),
            "reason": str(decision.get("reason") or "selected from task requirements"),
        },
        "theoretical_design": {
            "topology": str(theory.get("topology") or task["topology"]),
            "duty_cycle_nominal": _as_float(theory, "duty_cycle_nominal", float(reference["duty_cycle_nominal"])),
            "inductance_uh": _as_float(theory, "inductance_uh", float(reference["inductance_uh"])),
            "output_capacitance_uf": _as_float(theory, "output_capacitance_uf", float(reference["output_capacitance_uf"])),
            "switching_frequency_khz": _as_float(theory, "switching_frequency_khz", float(reference["switching_frequency_khz"])),
            "inductor_ripple_current_a": _as_float(theory, "inductor_ripple_current_a", float(reference["inductor_ripple_current_a"])),
            "switch_peak_current_a": _as_float(theory, "switch_peak_current_a", float(reference["switch_peak_current_a"])),
        },
        "bom": normalized_bom,
        "final_claimed_metrics": {
            "efficiency_percent": _as_float(claims, "efficiency_percent", float(reference["expected_metrics"]["efficiency_percent"])),
            "ripple_mv": _as_float(claims, "ripple_mv", float(reference["expected_metrics"]["ripple_mv"])),
            "mosfet_voltage_stress_v": _as_float(claims, "mosfet_voltage_stress_v", float(reference["expected_metrics"]["mosfet_voltage_stress_v"])),
            "diode_reverse_voltage_v": _as_float(claims, "diode_reverse_voltage_v", float(reference["expected_metrics"]["diode_reverse_voltage_v"])),
            "inductor_peak_current_a": _as_float(claims, "inductor_peak_current_a", float(reference["expected_metrics"]["inductor_peak_current_a"])),
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
            "Return one non-isolated DC/DC power converter design candidate as valid JSON only.",
            "Choose the required topology from the task unless the task is under-specified.",
            "Expose topology decision, theory parameters, BOM, claimed metrics, and escalation behavior.",
            "Claims must be conservative and consistent with the theory and selected parts.",
        ],
        "response_contract": {
            "design_rationale": "short paragraph",
            "topology_decision": {"selected_topology": "buck|boost|buck_boost", "reason": "string"},
            "theoretical_design": {
                "topology": "buck|boost|buck_boost",
                "duty_cycle_nominal": "float",
                "inductance_uh": "float",
                "output_capacitance_uf": "float",
                "switching_frequency_khz": "float",
                "inductor_ripple_current_a": "float",
                "switch_peak_current_a": "float",
            },
            "bom": [{"category": slot, "part_id": "string"} for slot in EXPECTED_BOM_SLOTS],
            "final_claimed_metrics": {
                "efficiency_percent": "float",
                "ripple_mv": "float",
                "mosfet_voltage_stress_v": "float",
                "diode_reverse_voltage_v": "float",
                "inductor_peak_current_a": "float",
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
            {
                "role": "system",
                "content": "You are generating PE-Bench topology scout candidates. Return JSON only.",
            },
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
            "task_bank": "topology_scout",
        }
    }
    return partial


@dataclass
class TopologyScoutBaseline:
    name: str
    noise_scale: float
    claim_bias: float
    prefers_safe_parts: bool
    escalates_on_stress: bool
    disable_component_grounding: bool = False
    disable_formula_guardrails: bool = False
    disable_correction_memory: bool = False

    @property
    def max_attempts(self) -> int:
        return 3 if self.name == "single_agent_retry" else 1

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

    def _attempt_counters(self, attempt_index: int) -> tuple[int, int]:
        if self.name == "single_agent_retry":
            return attempt_index, attempt_index
        if self.name in {"generic_two_role_mas", "text_only_self_refine"}:
            return 2, 1
        if self.name == "reference_agent":
            return 2, 2
        return 1, 1

    def _build_candidate(
        self,
        *,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        partial: dict[str, Any],
        attempt_index: int,
        feedback_history: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        spec = task["structured_spec"]
        iterations, sim_calls = self._attempt_counters(attempt_index)
        metadata = dict(partial.get("metadata", {}))
        metadata.update(
            {
                "task_bank": "topology_scout",
                "attempt_index": attempt_index,
                "retry_enabled": self.max_attempts > 1,
                "retry_history": list(feedback_history or []),
                "iterations_used": iterations,
                "sim_calls_used": sim_calls,
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
                "input_range_volts": dict(spec["input_range_volts"]),
                "output": dict(spec["output"]),
                "targets": dict(spec["targets"]),
            },
            "topology_decision": partial["topology_decision"],
            "design_rationale": partial["design_rationale"],
            "theoretical_design": partial["theoretical_design"],
            "bom": partial["bom"],
            "simulation_config": {"mode": "formula_stub", "max_sim_calls": sim_calls, "max_iterations": iterations},
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
                partial=partial,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )

        rng = Random(f"{task['task_id']}:{self.run_name}:{model_name}:{seed}:attempt{attempt_index}")
        reference = task["reference_design"]
        difficulty_multiplier = {
            "easy": 1.0,
            "medium": 1.25,
            "hard": 1.55,
            "boundary": 1.85,
            "stress": 2.15,
        }[task["difficulty_tier"]]
        noise = self.noise_scale * difficulty_multiplier
        if feedback_history and not self.disable_correction_memory:
            noise *= max(0.62, 1.0 - 0.12 * len(feedback_history))
        claim_bias = self.claim_bias + (1.1 if self.disable_formula_guardrails else 0.0)
        selected_topology = task["topology"]
        if self.name == "direct_prompting" and task["difficulty_tier"] in {"boundary", "stress"} and rng.random() < 0.18:
            selected_topology = rng.choice([top for top in ["buck", "boost", "buck_boost"] if top != task["topology"]])
        theory = {
            "topology": selected_topology,
            "duty_cycle_nominal": round(float(reference["duty_cycle_nominal"]) + rng.uniform(-0.08 * noise, 0.12 * noise), 3),
            "inductance_uh": round(float(reference["inductance_uh"]) * (1.0 + rng.uniform(-noise, noise)), 2),
            "output_capacitance_uf": round(float(reference["output_capacitance_uf"]) * (1.0 + rng.uniform(-0.9 * noise, 1.1 * noise)), 2),
            "switching_frequency_khz": round(float(reference["switching_frequency_khz"]) * (1.0 + rng.uniform(-0.7 * noise, 0.7 * noise)), 2),
            "inductor_ripple_current_a": round(float(reference["inductor_ripple_current_a"]) * (1.0 + rng.uniform(-noise, 1.1 * noise)), 3),
            "switch_peak_current_a": round(float(reference["switch_peak_current_a"]) * (1.0 + rng.uniform(-0.4 * noise, 1.3 * noise)), 3),
        }
        bom = self._select_bom(task=task, safe=self.prefers_safe_parts or bool(feedback_history), rng=rng)
        expected = reference["expected_metrics"]
        claims = {
            "efficiency_percent": round(float(expected["efficiency_percent"]) + claim_bias - 2.6 * noise + rng.uniform(-0.6, 0.8), 2),
            "ripple_mv": round(max(4.0, float(expected["ripple_mv"]) * (1.0 + 0.35 * noise) - 1.8 * claim_bias + rng.uniform(-2.0, 3.0)), 2),
            "mosfet_voltage_stress_v": round(float(expected["mosfet_voltage_stress_v"]) * (1.0 + 0.12 * noise), 2),
            "diode_reverse_voltage_v": round(float(expected["diode_reverse_voltage_v"]) * (1.0 + 0.12 * noise), 2),
            "inductor_peak_current_a": round(float(expected["inductor_peak_current_a"]) * (1.0 + 0.12 * noise), 3),
            "estimated_cost_usd": round(float(reference["cost_proxy_usd"]) * (1.03 if self.prefers_safe_parts else 0.92), 2),
        }
        partial = {
            "design_rationale": f"{self.name} generated a topology scout candidate for {task['topology']} with seed={seed}.",
            "topology_decision": {"selected_topology": selected_topology, "reason": "heuristic topology selection from Vin/Vout relation"},
            "theoretical_design": theory,
            "bom": bom,
            "final_claimed_metrics": claims,
            "uncertainty_or_escalation_flag": {
                "escalate": self.escalates_on_stress and task["difficulty_tier"] == "stress",
                "reason": "stress task flagged for review" if self.escalates_on_stress and task["difficulty_tier"] == "stress" else None,
            },
            "metadata": {"llm_generation": {"enabled": False}},
        }
        return self._build_candidate(
            task=task,
            model_name=model_name,
            seed=seed,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )

    def _select_bom(self, *, task: dict[str, Any], safe: bool, rng: Random) -> list[dict[str, str]]:
        if safe and not self.disable_component_grounding:
            selected = dict(task["reference_design"]["selected_components"])
            return [{"category": slot, "part_id": selected[slot]} for slot in EXPECTED_BOM_SLOTS]

        catalog = _catalog_by_slot()
        bom: list[dict[str, str]] = []
        for slot in EXPECTED_BOM_SLOTS:
            rows = catalog[slot]
            if self.disable_component_grounding:
                part_id = f"unverified_{slot}_{task['topology']}"
            elif slot in {"switch", "diode", "inductor"} and task["difficulty_tier"] in {"hard", "boundary", "stress"}:
                part_id = rows[0]["part_id"]
            else:
                part_id = rng.choice(rows[: max(1, min(2, len(rows)))])["part_id"]
            bom.append({"category": slot, "part_id": str(part_id)})
        return bom


def get_topology_scout_baseline(name: str, **kwargs: object) -> TopologyScoutBaseline:
    profiles = {
        "direct_prompting": dict(noise_scale=0.16, claim_bias=2.2, prefers_safe_parts=False, escalates_on_stress=False),
        "structured_output_only": dict(noise_scale=0.145, claim_bias=1.95, prefers_safe_parts=False, escalates_on_stress=False),
        "text_only_self_refine": dict(noise_scale=0.135, claim_bias=1.7, prefers_safe_parts=False, escalates_on_stress=False),
        "single_agent_same_tools": dict(noise_scale=0.095, claim_bias=0.9, prefers_safe_parts=True, escalates_on_stress=False),
        "single_agent_retry": dict(noise_scale=0.08, claim_bias=0.55, prefers_safe_parts=True, escalates_on_stress=True),
        "generic_two_role_mas": dict(noise_scale=0.085, claim_bias=0.7, prefers_safe_parts=True, escalates_on_stress=True),
        "pe_gpt_style": dict(noise_scale=0.075, claim_bias=0.45, prefers_safe_parts=True, escalates_on_stress=True),
        "reference_agent": dict(noise_scale=0.035, claim_bias=0.0, prefers_safe_parts=True, escalates_on_stress=True),
    }
    if name not in profiles:
        raise ValueError(f"Unknown topology scout baseline '{name}'. Available: {sorted(profiles)}")
    profile = dict(profiles[name])
    profile.update(kwargs)
    return TopologyScoutBaseline(name=name, **profile)
