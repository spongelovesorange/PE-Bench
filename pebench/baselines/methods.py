from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import Any

from pebench.baselines.llm_client import generate_llm_candidate_payload, should_use_llm
from pebench.integrations.reference_agent import generate_reference_agent_candidate, get_reference_agent_assets
from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_CATALOG_PATH


def _catalog_by_alias() -> dict[str, list[dict[str, Any]]]:
    catalog = load_yaml(DEFAULT_CATALOG_PATH)
    return {
        "controller": catalog["controllers"],
        "mosfet": catalog["mosfets"],
        "diode": catalog["diodes"],
        "output_capacitor": catalog["output_capacitors"],
        "core": catalog["cores"],
    }


def safe_bom(bom: list[dict[str, str]]) -> bool:
    lookup = {item["category"]: item["part_id"] for item in bom}
    return lookup.get("mosfet") == "IPD60R380P7" and lookup.get("diode") == "STPS8H100"


def _last_failure_tags(feedback_history: list[dict[str, Any]] | None) -> list[str]:
    if not feedback_history:
        return []
    return list(feedback_history[-1].get("failure_tags", []))


def _suggested_repairs_from_failure_tags(failure_tags: list[str]) -> list[str]:
    suggestions: list[str] = []
    if "Invalid or Unsafe BOM" in failure_tags:
        suggestions.extend(
            [
                "reselect_catalog_grounded_bom",
                "prefer_higher_margin_switch_and_rectifier",
            ]
        )
    if "Stress Violation / Escalation Required" in failure_tags:
        suggestions.extend(
            [
                "reduce_peak_stress_margin_risk",
                "lower_duty_cycle_and_primary_peak_current",
            ]
        )
    if "Efficiency Miss" in failure_tags:
        suggestions.append("retune_switching_frequency_for_efficiency")
    if "Ripple / Regulation Miss" in failure_tags:
        suggestions.append("increase_output_filter_margin")
    if "Infeasible Theory Failure" in failure_tags:
        suggestions.append("repair_theoretical_design_parameters")
    if "Optimistic but Unrealistic Claim" in failure_tags:
        suggestions.append("lower_claims_to_match_physical_expectations")
    if "Simulation Execution Failure" in failure_tags:
        suggestions.append("use_safer_startup_and_more_conservative_design")
    if "Spec Parsing Failure" in failure_tags:
        suggestions.append("re-read_structured_spec_and_targets")
    deduped: list[str] = []
    for suggestion in suggestions:
        if suggestion not in deduped:
            deduped.append(suggestion)
    return deduped


@dataclass
class BaseBaseline:
    name: str = "base"
    noise_scale: float = 0.1
    claim_bias: float = 0.0
    escalates_on_stress: bool = False
    prefers_safe_parts: bool = False
    disable_formula_guardrails: bool = False
    disable_component_grounding: bool = False
    disable_correction_memory: bool = False

    @property
    def max_attempts(self) -> int:
        return 1

    @property
    def run_name(self) -> str:
        suffixes: list[str] = []
        if self.disable_formula_guardrails:
            suffixes.append("wo_formula_guardrails")
        if self.disable_component_grounding:
            suffixes.append("wo_component_grounding")
        if self.disable_correction_memory:
            suffixes.append("wo_correction_memory")
        if not suffixes:
            return self.name
        return f"{self.name}__{'__'.join(suffixes)}"

    def _attempt_counters(self, attempt_index: int) -> tuple[int, int]:
        iterations = 1 if self.name == "direct_prompting" else 2
        sim_calls = 1 if self.name != "reference_agent" else 2
        if self.name == "text_only_self_refine":
            iterations = 2
            sim_calls = 1
        if self.name == "single_agent_retry":
            iterations = max(1, attempt_index)
            sim_calls = max(1, attempt_index)
        if self.name == "generic_two_role_mas":
            iterations = max(2, attempt_index)
            sim_calls = max(1, attempt_index)
        if self.disable_correction_memory and self.name == "reference_agent":
            iterations = 1
            sim_calls = 1
        return iterations, sim_calls

    def _build_candidate_from_partial(
        self,
        *,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None,
        partial: dict[str, Any],
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        spec = task["structured_spec"]
        iterations_used, sim_calls_used = self._attempt_counters(attempt_index)
        metadata = dict(partial.get("metadata", {}))
        metadata.update(
            {
                "attempt_index": attempt_index,
                "retry_enabled": self.max_attempts > 1,
                "retry_history": list(feedback_history or []),
                "retry_suggested_repairs": _suggested_repairs_from_failure_tags(
                    _last_failure_tags(feedback_history)
                ),
                "iterations_used": iterations_used,
                "sim_calls_used": sim_calls_used,
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
            "design_rationale": partial["design_rationale"],
            "theoretical_design": partial["theoretical_design"],
            "bom": partial["bom"],
            "simulation_config": {
                "mode": simulator_mode or "auto",
                "max_sim_calls": sim_calls_used,
                "max_iterations": iterations_used,
                "fallback_policy": "stub_on_live_failure",
            },
            "final_claimed_metrics": partial["final_claimed_metrics"],
            "uncertainty_or_escalation_flag": partial["uncertainty_or_escalation_flag"],
            "metadata": metadata,
        }

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        difficulty_multiplier = {
            "easy": 1.0,
            "medium": 1.25,
            "hard": 1.6,
            "boundary": 1.85,
            "stress": 2.0,
        }[task["difficulty_tier"]]
        rng = Random(f"{task['task_id']}:{self.run_name}:{model_name}:{seed}:attempt{attempt_index}")
        reference = task["reference_design"]
        spec = task["structured_spec"]
        noise = self.noise_scale * difficulty_multiplier
        if self.disable_formula_guardrails:
            noise *= 1.25
        if feedback_history:
            noise *= max(0.7, 1.0 - 0.08 * len(feedback_history))
        claim_bias = self.claim_bias + (1.3 if self.disable_formula_guardrails else 0.0)

        parsed_spec = {
            "input_range_volts": dict(spec["input_range_volts"]),
            "output": dict(spec["output"]),
            "targets": dict(spec["targets"]),
        }
        if self.name == "direct_prompting" and task["difficulty_tier"] in {"hard", "stress"}:
            parsed_spec["targets"]["ripple_mv"] = round(
                spec["targets"]["ripple_mv"] * (1.0 - 0.2 * noise),
                2,
            )
            parsed_spec["output"]["current_a"] = round(
                spec["output"]["current_a"] * (1.0 - 0.08 * noise),
                2,
            )
        elif self.name == "single_agent_same_tools" and task["difficulty_tier"] == "stress":
            parsed_spec["targets"]["efficiency_percent"] = round(
                spec["targets"]["efficiency_percent"] + 0.8,
                2,
            )

        theoretical_design = {
            "topology": "flyback",
            "turns_ratio_primary_to_secondary": round(
                reference["turns_ratio_primary_to_secondary"] * (1.0 + rng.uniform(-noise, noise)),
                3,
            ),
            "magnetizing_inductance_uh": round(
                reference["magnetizing_inductance_uh"] * (1.0 + rng.uniform(-noise, noise)),
                2,
            ),
            "switching_frequency_khz": round(
                reference["switching_frequency_khz"] * (1.0 + rng.uniform(-0.8 * noise, 0.8 * noise)),
                2,
            ),
            "duty_cycle_max": round(
                reference["duty_cycle_max"] + rng.uniform(-0.05 * noise, 0.08 * noise),
                3,
            ),
            "primary_peak_current_a": round(
                reference["primary_peak_current_a"] * (1.0 + rng.uniform(-noise, 1.2 * noise)),
                3,
            ),
        }

        last_failure_tags = _last_failure_tags(feedback_history)
        safe_parts = self.prefers_safe_parts or (
            self.name == "single_agent_retry"
            and any(tag in last_failure_tags for tag in {"Invalid or Unsafe BOM", "Stress Violation / Escalation Required"})
        )
        bom = self._select_bom(task=task, rng=rng, safe=safe_parts)

        claimed_metrics = {
            "efficiency_percent": round(
                reference["expected_metrics"]["efficiency_percent"]
                + claim_bias
                - 3.0 * noise
                + rng.uniform(-0.8, 1.0),
                2,
            ),
            "ripple_mv": round(
                max(
                    5.0,
                    reference["expected_metrics"]["ripple_mv"]
                    * (1.0 + 0.4 * noise)
                    - claim_bias * 2.5
                    + rng.uniform(-2.0, 3.0),
                ),
                2,
            ),
            "mosfet_voltage_stress_v": round(
                reference["expected_metrics"]["mosfet_voltage_stress_v"] * (1.0 + 0.18 * noise),
                2,
            ),
            "diode_reverse_voltage_v": round(
                reference["expected_metrics"]["diode_reverse_voltage_v"] * (1.0 + 0.16 * noise),
                2,
            ),
            "flux_density_mt": round(
                reference["expected_metrics"]["flux_density_mt"] * (1.0 + 0.15 * noise),
                2,
            ),
            "estimated_cost_usd": round(
                reference["cost_proxy_usd"] * (1.0 + (0.08 if safe_bom(bom) else -0.04)),
                2,
            ),
        }

        if feedback_history:
            if "Stress Violation / Escalation Required" in last_failure_tags:
                theoretical_design["duty_cycle_max"] = round(
                    max(0.08, theoretical_design["duty_cycle_max"] - 0.03),
                    3,
                )
                theoretical_design["primary_peak_current_a"] = round(
                    max(0.4, theoretical_design["primary_peak_current_a"] * 0.92),
                    3,
                )
                theoretical_design["turns_ratio_primary_to_secondary"] = round(
                    theoretical_design["turns_ratio_primary_to_secondary"] * 1.04,
                    3,
                )
                claimed_metrics["efficiency_percent"] = round(claimed_metrics["efficiency_percent"] - 0.8, 2)
            if "Invalid or Unsafe BOM" in last_failure_tags:
                bom = self._select_bom(task=task, rng=rng, safe=True)
                claimed_metrics["estimated_cost_usd"] = round(reference["cost_proxy_usd"] * 1.05, 2)
            if "Efficiency Miss" in last_failure_tags:
                theoretical_design["switching_frequency_khz"] = round(
                    theoretical_design["switching_frequency_khz"] * 1.04,
                    2,
                )
                claimed_metrics["efficiency_percent"] = round(claimed_metrics["efficiency_percent"] - 0.5, 2)
            if "Ripple / Regulation Miss" in last_failure_tags:
                claimed_metrics["ripple_mv"] = round(max(8.0, claimed_metrics["ripple_mv"] + 6.0), 2)
            if "Optimistic but Unrealistic Claim" in last_failure_tags:
                claimed_metrics["efficiency_percent"] = round(claimed_metrics["efficiency_percent"] - 1.2, 2)
                claimed_metrics["ripple_mv"] = round(claimed_metrics["ripple_mv"] + 5.0, 2)

        escalate = self.escalates_on_stress and task["difficulty_tier"] == "stress"
        rationale = (
            f"{self.name} generated a flyback design candidate using a deterministic "
            f"heuristic policy with seed={seed}."
        )
        if feedback_history:
            rationale += (
                " Retry guidance incorporated previous evaluator failures: "
                + ", ".join(_suggested_repairs_from_failure_tags(last_failure_tags))
                + "."
            )

        iterations_used, sim_calls_used = self._attempt_counters(attempt_index)
        return {
            "task_id": task["task_id"],
            "baseline_name": self.run_name,
            "model_name": model_name,
            "seed": seed,
            "parsed_spec": parsed_spec,
            "design_rationale": rationale,
            "theoretical_design": theoretical_design,
            "bom": bom,
            "simulation_config": {
                "mode": simulator_mode or "auto",
                "max_sim_calls": sim_calls_used,
                "max_iterations": iterations_used,
                "fallback_policy": "stub_on_live_failure",
            },
            "final_claimed_metrics": claimed_metrics,
            "uncertainty_or_escalation_flag": {
                "escalate": escalate,
                "reason": "Stress task flagged for review" if escalate else None,
            },
            "metadata": {
                "attempt_index": attempt_index,
                "retry_enabled": self.max_attempts > 1,
                "retry_history": list(feedback_history or []),
                "retry_suggested_repairs": _suggested_repairs_from_failure_tags(last_failure_tags),
                "iterations_used": iterations_used,
                "sim_calls_used": sim_calls_used,
                "baseline_family": self.name,
                "ablations": {
                    "disable_formula_guardrails": self.disable_formula_guardrails,
                    "disable_component_grounding": self.disable_component_grounding,
                    "disable_correction_memory": self.disable_correction_memory,
                },
            },
        }

    def _select_bom(
        self,
        task: dict[str, Any],
        rng: Random,
        safe: bool,
    ) -> list[dict[str, str]]:
        catalog = _catalog_by_alias()
        power_w = task["structured_spec"]["output"]["power_w"]
        output_current = task["structured_spec"]["output"]["current_a"]

        selected: list[dict[str, str]] = []
        for alias, parts in catalog.items():
            filtered = parts
            if alias == "mosfet":
                filtered = sorted(parts, key=lambda item: (item["voltage_rating_v"], item["cost_usd"]))
            elif alias == "diode":
                filtered = sorted(parts, key=lambda item: (item["current_rating_a"], item["cost_usd"]))
            elif alias == "core":
                filtered = sorted(parts, key=lambda item: (item["max_power_w"], item["cost_usd"]))
            elif alias == "output_capacitor":
                filtered = sorted(parts, key=lambda item: (item["ripple_current_a"], item["cost_usd"]))
            else:
                filtered = sorted(parts, key=lambda item: item["cost_usd"])

            if safe:
                chosen = filtered[-1]
            else:
                index = min(len(filtered) - 1, 1 if power_w <= 24 and output_current <= 2.0 else 0)
                chosen = filtered[index]
                if self.name == "direct_prompting" and task["difficulty_tier"] == "stress" and alias in {"mosfet", "diode"}:
                    chosen = filtered[0]
            if self.disable_component_grounding:
                chosen = filtered[0]

            selected.append({"category": alias, "part_id": chosen["part_id"]})

        return selected


class DirectPromptingBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="direct_prompting",
            noise_scale=0.12,
            claim_bias=2.1,
            escalates_on_stress=False,
            prefers_safe_parts=False,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            return super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=feedback_history,
        )
        return self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )


class StructuredOutputOnlyBaseline(DirectPromptingBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        BaseBaseline.__init__(
            self,
            name="structured_output_only",
            noise_scale=0.11,
            claim_bias=1.9,
            escalates_on_stress=False,
            prefers_safe_parts=False,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )


class TextOnlySelfRefineBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="text_only_self_refine",
            noise_scale=0.105,
            claim_bias=1.65,
            escalates_on_stress=False,
            prefers_safe_parts=False,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            candidate = super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=None,
            )
            candidate["design_rationale"] += " Text-only self-refine used an internal draft-critique-revise pass without executable feedback."
            return candidate

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=None,
        )
        candidate = self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=[],
        )
        candidate["design_rationale"] += " The candidate reflects internal self-refinement only; no evaluator feedback was used."
        return candidate


class SingleAgentSameToolsBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="single_agent_same_tools",
            noise_scale=0.075,
            claim_bias=0.9,
            escalates_on_stress=False,
            prefers_safe_parts=True,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            return super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=feedback_history,
        )
        return self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )


class SingleAgentRetryBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="single_agent_retry",
            noise_scale=0.06,
            claim_bias=0.6,
            escalates_on_stress=True,
            prefers_safe_parts=True,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    @property
    def max_attempts(self) -> int:
        return 3

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            return super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=feedback_history,
        )
        candidate = self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )
        if feedback_history:
            last_tags = _last_failure_tags(feedback_history)
            candidate["design_rationale"] += (
                " Retry pass explicitly addressed prior failures: "
                + ", ".join(last_tags or ["none"])
                + "."
            )
        return candidate


class PEGPTBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="pe_gpt_style",
            noise_scale=0.055,
            claim_bias=0.45,
            escalates_on_stress=True,
            prefers_safe_parts=True,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            candidate = super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )
            candidate["design_rationale"] += " PE-GPT baseline fell back to heuristic mode because no live LLM model was requested."
            candidate["metadata"]["pe_gpt_style_integration"] = {
                "enabled": False,
                "mode": "heuristic_fallback",
                "root_path": None,
            }
            return candidate

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=feedback_history,
        )
        candidate = self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )
        candidate["metadata"]["pe_gpt_style_integration"] = {
            "enabled": True,
            "mode": "public_framework_prompt_adapter",
            "root_path": None,
            "note": (
                "Adapted from the public PE-GPT repository's general PE reasoning and RAG framing. "
                "The released repo does not expose a native flyback CLI/runtime, so this benchmark adapter "
                "uses its public framework description rather than the DAB/buck GUI flow."
            ),
        }
        return candidate


class GenericTwoRoleMASBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="generic_two_role_mas",
            noise_scale=0.05,
            claim_bias=0.45,
            escalates_on_stress=True,
            prefers_safe_parts=True,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    @property
    def max_attempts(self) -> int:
        return 2

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not should_use_llm(model_name):
            candidate = super().generate(
                task=task,
                model_name=model_name,
                seed=seed,
                simulator_mode=simulator_mode,
                attempt_index=attempt_index,
                feedback_history=feedback_history,
            )
            candidate["design_rationale"] += (
                " Generic two-role MAS heuristic path used Designer/Critic decomposition "
                "without private reference-agent theory or component modules."
            )
            candidate["metadata"]["generic_mas_integration"] = {
                "enabled": True,
                "roles": ["designer", "critic"],
                "pe_specific_modules": False,
            }
            return candidate

        partial = generate_llm_candidate_payload(
            task=task,
            baseline_name=self.name,
            model_name=model_name,
            seed=seed,
            enable_formula_guardrails=not self.disable_formula_guardrails,
            enable_component_grounding=not self.disable_component_grounding,
            feedback_history=feedback_history,
        )
        candidate = self._build_candidate_from_partial(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            partial=partial,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )
        candidate["metadata"]["generic_mas_integration"] = {
            "enabled": True,
            "roles": ["designer", "critic"],
            "pe_specific_modules": False,
        }
        if feedback_history:
            candidate["design_rationale"] += (
                " The critic incorporated evaluator feedback from prior attempts: "
                + ", ".join(_last_failure_tags(feedback_history) or ["none"])
                + "."
            )
        return candidate


class ReferenceAgentBaseline(BaseBaseline):
    def __init__(
        self,
        disable_formula_guardrails: bool = False,
        disable_component_grounding: bool = False,
        disable_correction_memory: bool = False,
    ) -> None:
        super().__init__(
            name="reference_agent",
            noise_scale=0.03,
            claim_bias=0.2,
            escalates_on_stress=True,
            prefers_safe_parts=True,
            disable_formula_guardrails=disable_formula_guardrails,
            disable_component_grounding=disable_component_grounding,
            disable_correction_memory=disable_correction_memory,
        )

    def generate(
        self,
        task: dict[str, Any],
        model_name: str,
        seed: int,
        simulator_mode: str | None = None,
        attempt_index: int = 1,
        feedback_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        candidate = generate_reference_agent_candidate(
            task=task,
            model_name=model_name,
            seed=seed,
            baseline_name=self.run_name,
            disable_correction_memory=self.disable_correction_memory,
        )
        if candidate is not None:
            candidate["simulation_config"]["mode"] = simulator_mode or "auto"
            candidate["simulation_config"]["fallback_policy"] = "stub_on_live_failure"
            candidate["metadata"]["attempt_index"] = attempt_index
            candidate["metadata"]["retry_enabled"] = self.max_attempts > 1
            candidate["metadata"]["retry_history"] = list(feedback_history or [])
            candidate["metadata"]["retry_suggested_repairs"] = _suggested_repairs_from_failure_tags(
                _last_failure_tags(feedback_history)
            )
            candidate["metadata"]["baseline_family"] = self.name
            candidate["metadata"]["ablations"] = {
                "disable_formula_guardrails": self.disable_formula_guardrails,
                "disable_component_grounding": self.disable_component_grounding,
                "disable_correction_memory": self.disable_correction_memory,
            }
            if self.disable_formula_guardrails:
                theory = candidate["theoretical_design"]
                claims = candidate["final_claimed_metrics"]
                theory["switching_frequency_khz"] = round(float(theory["switching_frequency_khz"]) * 1.12, 2)
                theory["duty_cycle_max"] = round(float(theory["duty_cycle_max"]) + 0.05, 3)
                theory["primary_peak_current_a"] = round(float(theory["primary_peak_current_a"]) * 1.16, 3)
                claims["efficiency_percent"] = round(float(claims["efficiency_percent"]) + 1.1, 2)
                claims["ripple_mv"] = round(max(5.0, float(claims["ripple_mv"]) * 0.82), 2)
                candidate["design_rationale"] += " Formula-guardrail ablation disables conservative reference-agent theory checks."
            if self.disable_component_grounding:
                ablation_rng = Random(f"{task['task_id']}:{self.run_name}:{model_name}:{seed}:bom")
                candidate["bom"] = super()._select_bom(task=task, rng=ablation_rng, safe=False)
                candidate["design_rationale"] += " Component-grounding ablation replaces reference-agent catalog grounding with benchmark-level weak BOM picks."
                reference_agent_integration = candidate["metadata"].get("reference_agent_integration", {})
                reference_agent_integration["enabled"] = False
                reference_agent_integration["reason"] = "component_grounding_ablation"
                candidate["metadata"]["reference_agent_integration"] = reference_agent_integration
            if self.disable_correction_memory:
                candidate["design_rationale"] += " Correction/memory ablation disables post-design repair and reduces closure iterations."
            return candidate

        fallback = super().generate(
            task=task,
            model_name=model_name,
            seed=seed,
            simulator_mode=simulator_mode,
            attempt_index=attempt_index,
            feedback_history=feedback_history,
        )
        fallback["metadata"]["reference_agent_integration"] = {
            "enabled": False,
            "reason": "Reference-agent assets unavailable; fallback heuristic path used.",
            "available_modules": get_reference_agent_assets().get("available", {}),
        }
        return fallback
