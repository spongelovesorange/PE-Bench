from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from pebench.utils.io import load_yaml
from pebench.utils.paths import DEFAULT_CATALOG_PATH, DEFAULT_PE_GPT_ROOT


HEURISTIC_MODEL_NAMES = {"", "heuristic", "heuristic-v0", "none", "stub"}
EXPECTED_BOM_CATEGORIES = ["controller", "mosfet", "diode", "output_capacitor", "core"]

PE_GPT_CONTEXT_FILES = [
    DEFAULT_PE_GPT_ROOT / "core" / "knowledge" / "kb" / "introduction" / ("PE" + "-GPT.txt"),
    DEFAULT_PE_GPT_ROOT / "README.md",
]


@dataclass(frozen=True)
class LLMRuntimeConfig:
    model_name: str
    api_key: str
    base_url: str
    provider_label: str
    temperature: float
    timeout_seconds: float


def should_use_llm(model_name: str) -> bool:
    return str(model_name or "").strip().lower() not in HEURISTIC_MODEL_NAMES


def load_runtime_config(requested_model: str) -> LLMRuntimeConfig:
    _load_dotenv_if_available()

    model_name = str(requested_model or "").strip()
    if not should_use_llm(model_name):
        raise RuntimeError("Heuristic model names do not use the LLM runtime.")

    api_key = (
        os.getenv("PEBENCH_LLM_API_KEY")
        or os.getenv("FLYBACKBENCH_LLM_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise RuntimeError(
            "No LLM API key found. Set PEBENCH_LLM_API_KEY or OPENAI_API_KEY."
        )

    base_url = (
        os.getenv("PEBENCH_LLM_BASE_URL")
        or os.getenv("FLYBACKBENCH_LLM_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or "https://api.openai.com/v1"
    ).strip()
    provider_label = "openai_compatible"

    return LLMRuntimeConfig(
        model_name=model_name,
        api_key=api_key,
        base_url=_normalize_base_url(base_url),
        provider_label=provider_label,
        temperature=float(
            os.getenv("PEBENCH_LLM_TEMPERATURE")
            or os.getenv("FLYBACKBENCH_LLM_TEMPERATURE")
            or "0.25"
        ),
        timeout_seconds=float(
            os.getenv("PEBENCH_LLM_TIMEOUT_SEC")
            or os.getenv("FLYBACKBENCH_LLM_TIMEOUT_SEC")
            or "90"
        ),
    )


def generate_llm_candidate_payload(
    *,
    task: dict[str, Any],
    baseline_name: str,
    model_name: str,
    seed: int,
    enable_formula_guardrails: bool,
    enable_component_grounding: bool,
    feedback_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_runtime_config(model_name)
    prompt_payload = _build_prompt_payload(
        task=task,
        baseline_name=baseline_name,
        seed=seed,
        enable_formula_guardrails=enable_formula_guardrails,
        enable_component_grounding=enable_component_grounding,
        feedback_history=feedback_history,
    )
    # Some OpenAI-compatible providers work reliably only with an explicit httpx client.
    # We disable trust_env to avoid inheriting shell proxy settings and force HTTP/1.1.
    client = OpenAI(
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.timeout_seconds,
        http_client=httpx.Client(
            timeout=config.timeout_seconds,
            trust_env=False,
            http2=False,
        ),
    )

    messages = [
        {"role": "system", "content": prompt_payload["system_prompt"]},
        {"role": "user", "content": prompt_payload["user_prompt"]},
    ]

    raw_content = _chat_json(client=client, config=config, messages=messages, seed=seed)
    parsed = _extract_json_object(raw_content)
    partial = _normalize_candidate_payload(parsed)
    partial["metadata"] = {
        "llm_generation": {
            "enabled": True,
            "provider": config.provider_label,
            "base_url": config.base_url,
            "prompt_mode": baseline_name,
            "seed_hint": seed,
        }
    }
    return partial


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(override=False)


def _normalize_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    if not normalized:
        return "https://api.openai.com/v1"
    if normalized.endswith("/chat/completions"):
        normalized = normalized[: -len("/chat/completions")]
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _catalog_for_prompt() -> dict[str, Any]:
    catalog = load_yaml(DEFAULT_CATALOG_PATH)
    return {
        "controllers": [
            {
                "part_id": item["part_id"],
                "family": item["family"],
                "max_input_v": item["max_input_v"],
                "cost_usd": item["cost_usd"],
            }
            for item in catalog["controllers"]
        ],
        "mosfets": [
            {
                "part_id": item["part_id"],
                "voltage_rating_v": item["voltage_rating_v"],
                "current_rating_a": item["current_rating_a"],
                "cost_usd": item["cost_usd"],
            }
            for item in catalog["mosfets"]
        ],
        "diodes": [
            {
                "part_id": item["part_id"],
                "voltage_rating_v": item["voltage_rating_v"],
                "current_rating_a": item["current_rating_a"],
                "cost_usd": item["cost_usd"],
            }
            for item in catalog["diodes"]
        ],
        "output_capacitors": [
            {
                "part_id": item["part_id"],
                "voltage_rating_v": item["voltage_rating_v"],
                "ripple_current_a": item["ripple_current_a"],
                "cost_usd": item["cost_usd"],
            }
            for item in catalog["output_capacitors"]
        ],
        "cores": [
            {
                "part_id": item["part_id"],
                "max_power_w": item["max_power_w"],
                "cost_usd": item["cost_usd"],
            }
            for item in catalog["cores"]
        ],
    }


def _load_pe_gpt_style_context() -> str:
    chunks: list[str] = []
    for path in PE_GPT_CONTEXT_FILES:
        if not path.exists():
            continue
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        chunks.append(text[:1400])
    if not chunks:
        return ""
    return " ".join(chunks)[:2200]


def _build_prompt_payload(
    *,
    task: dict[str, Any],
    baseline_name: str,
    seed: int,
    enable_formula_guardrails: bool,
    enable_component_grounding: bool,
    feedback_history: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    visible_task = {
        "task_id": task["task_id"],
        "natural_language_spec": task["natural_language_spec"],
        "difficulty_tier": task["difficulty_tier"],
        "structured_spec": task["structured_spec"],
        "known_failure_modes": task["known_failure_modes"],
    }

    baseline_guidance = {
        "direct_prompting": [
            "Produce a single-shot design without iterative self-correction.",
            "If multiple options are feasible, use the benchmark seed only as a tie-break hint.",
        ],
        "structured_output_only": [
            "Produce a single structured JSON design candidate.",
            "Follow the required output schema, but do not use tool feedback, retries, or PE-specific verifier assumptions.",
        ],
        "text_only_self_refine": [
            "Produce a text-only design after an internal draft, critique, and revision pass.",
            "Do not rely on simulator outputs or executable feedback; use only the prompt information.",
            "Keep the final answer concise and return only the revised candidate.",
        ],
        "single_agent_same_tools": [
            "Do a conservative internal self-check before deciding.",
            "Prefer safer parts and more realistic claims when trade-offs are close.",
            "Escalate on stress-like uncertainty instead of bluffing.",
        ],
        "single_agent_retry": [
            "Treat prior evaluator failures as hard design feedback.",
            "Revise the candidate to directly address previous failure tags before claiming success.",
            "Keep the same tool surface as the LLM+Tools baseline, but use retries to converge on a safer design.",
        ],
        "generic_two_role_mas": [
            "Simulate a generic two-role MAS with a Designer role and a Critic role.",
            "The Designer proposes a flyback design; the Critic checks consistency, risk, and prior feedback.",
            "Use role decomposition and executable feedback, but do not assume private reference-agent modules.",
            "Prefer conservative revisions when the critic detects stress, BOM, or efficiency risk.",
        ],
        "pe_gpt_style": [
            "Use a structured power-electronics reasoning style informed by PE-GPT's public framework description.",
            "Be explicit about trade-offs among efficiency, stress, switching frequency, magnetics, and component realism.",
            "Prefer physically grounded, conservative claims over aggressive headline metrics.",
            "If a design remains ambiguous or high-risk, escalate instead of bluffing.",
        ],
    }.get(baseline_name, ["Produce one best-effort candidate."])

    engineering_notes = [
        "Topology must be flyback.",
        "Keep turns_ratio_primary_to_secondary above 1.0.",
        "Keep switching_frequency_khz inside the task range unless you intentionally accept risk.",
        "Keep duty_cycle_max and primary_peak_current_a within the structured constraints when possible.",
        "Claimed metrics should be physically plausible for the selected theory and BOM.",
        "Exactly one BOM item is required for each category: controller, mosfet, diode, output_capacitor, core.",
    ]
    if enable_formula_guardrails:
        engineering_notes.extend(
            [
                "Use conservative guardrails: avoid optimistic efficiency claims and keep ripple/stress margins realistic.",
                "Self-check MOSFET voltage stress, diode reverse voltage, and flux density before finalizing.",
            ]
        )
    else:
        engineering_notes.append(
            "Formula guardrails are disabled. Optimize more aggressively and do not add extra conservative margin beyond the stated task."
        )
    if enable_component_grounding:
        engineering_notes.extend(
            [
                "Component grounding is enabled. Every part_id must come from the provided catalog.",
                "Prefer a controller family allowed by structured_spec.preferences.allowed_controller_families.",
            ]
        )
    else:
        engineering_notes.append(
            "Component grounding is disabled. You may name plausible parts even if they are not from a provided catalog."
        )

    response_contract = {
        "design_rationale": "short paragraph",
        "theoretical_design": {
            "topology": "flyback",
            "turns_ratio_primary_to_secondary": "float",
            "magnetizing_inductance_uh": "float",
            "switching_frequency_khz": "float",
            "duty_cycle_max": "float",
            "primary_peak_current_a": "float",
        },
        "bom": [
            {"category": "controller", "part_id": "string"},
            {"category": "mosfet", "part_id": "string"},
            {"category": "diode", "part_id": "string"},
            {"category": "output_capacitor", "part_id": "string"},
            {"category": "core", "part_id": "string"},
        ],
        "final_claimed_metrics": {
            "efficiency_percent": "float",
            "ripple_mv": "float",
            "mosfet_voltage_stress_v": "float",
            "diode_reverse_voltage_v": "float",
            "flux_density_mt": "float",
            "estimated_cost_usd": "float",
        },
        "uncertainty_or_escalation_flag": {
            "escalate": "bool",
            "reason": "string or null",
        },
    }

    user_payload: dict[str, Any] = {
        "seed_hint": seed,
        "task": visible_task,
        "baseline_guidance": baseline_guidance,
        "engineering_notes": engineering_notes,
        "response_contract": response_contract,
    }
    if baseline_name == "pe_gpt_style":
        pe_gpt_style_context = _load_pe_gpt_style_context()
        if pe_gpt_style_context:
            user_payload["pe_gpt_style_public_context"] = pe_gpt_style_context
    if feedback_history:
        user_payload["retry_feedback"] = [
            {
                "attempt": int(item.get("attempt", 0)),
                "failure_tags": list(item.get("failure_tags", [])),
                "suggested_repairs": list(item.get("suggested_repairs", [])),
                "summary": str(item.get("summary") or ""),
            }
            for item in feedback_history
        ]
    if enable_component_grounding:
        user_payload["component_catalog"] = _catalog_for_prompt()

    system_prompt = (
        "You are generating one benchmark candidate for PE-Bench. "
        "Return valid JSON only, with no markdown fences and no extra commentary. "
        "Use only the task data and optional component catalog included in the prompt. "
        "Do not mention hidden reference designs or evaluator internals."
    )
    user_prompt = json.dumps(user_payload, indent=2, sort_keys=True)
    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def _chat_json(
    *,
    client: OpenAI,
    config: LLMRuntimeConfig,
    messages: list[dict[str, str]],
    seed: int,
) -> str:
    kwargs = {
        "model": config.model_name,
        "messages": messages,
        "temperature": config.temperature,
        "seed": seed,
    }
    try:
        response = client.chat.completions.create(
            **kwargs,
            response_format={"type": "json_object"},
        )
    except Exception:
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception:
            kwargs.pop("seed", None)
            try:
                response = client.chat.completions.create(
                    **kwargs,
                    response_format={"type": "json_object"},
                )
            except Exception:
                response = client.chat.completions.create(**kwargs)

    message = response.choices[0].message
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                chunks.append(str(part.get("text") or ""))
            elif hasattr(part, "text"):
                chunks.append(str(getattr(part, "text") or ""))
            else:
                chunks.append(str(part))
        return "".join(chunks).strip()
    return str(content or "").strip()


def _extract_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        raise ValueError("LLM returned empty content.")

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start : end + 1])


def _normalize_candidate_payload(raw: dict[str, Any]) -> dict[str, Any]:
    theory = raw.get("theoretical_design", {})
    claims = raw.get("final_claimed_metrics", {})
    uncertainty = raw.get("uncertainty_or_escalation_flag", {})
    bom = raw.get("bom", [])

    normalized_bom: list[dict[str, str]] = []
    seen_categories: set[str] = set()
    for item in bom:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        part_id = str(item.get("part_id") or "").strip()
        if not category or not part_id or category in seen_categories:
            continue
        normalized_bom.append({"category": category, "part_id": part_id})
        seen_categories.add(category)

    missing_categories = [category for category in EXPECTED_BOM_CATEGORIES if category not in seen_categories]
    if missing_categories:
        raise ValueError(f"LLM output missed BOM categories: {missing_categories}")

    return {
        "design_rationale": str(raw.get("design_rationale") or "").strip() or "LLM-generated flyback design.",
        "theoretical_design": {
            "topology": str(theory.get("topology") or "flyback"),
            "turns_ratio_primary_to_secondary": _as_float(theory, "turns_ratio_primary_to_secondary"),
            "magnetizing_inductance_uh": _as_float(theory, "magnetizing_inductance_uh"),
            "switching_frequency_khz": _as_float(theory, "switching_frequency_khz"),
            "duty_cycle_max": _as_float(theory, "duty_cycle_max"),
            "primary_peak_current_a": _as_float(theory, "primary_peak_current_a"),
        },
        "bom": normalized_bom,
        "final_claimed_metrics": {
            "efficiency_percent": _as_float(claims, "efficiency_percent"),
            "ripple_mv": _as_float(claims, "ripple_mv"),
            "mosfet_voltage_stress_v": _as_float(claims, "mosfet_voltage_stress_v"),
            "diode_reverse_voltage_v": _as_float(claims, "diode_reverse_voltage_v"),
            "flux_density_mt": _as_float(claims, "flux_density_mt"),
            "estimated_cost_usd": _as_float(claims, "estimated_cost_usd"),
        },
        "uncertainty_or_escalation_flag": {
            "escalate": bool(uncertainty.get("escalate")),
            "reason": _optional_text(uncertainty.get("reason")),
        },
    }


def _as_float(mapping: dict[str, Any], key: str) -> float:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"LLM output missed numeric field '{key}'.")
    return round(float(value), 4)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
