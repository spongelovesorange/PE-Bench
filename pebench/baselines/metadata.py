from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BaselineMetadata:
    code_id: str
    display_label: str
    family_group: str
    external_root: str | None
    notes: str


BASELINE_METADATA: dict[str, BaselineMetadata] = {
    "direct_prompting": BaselineMetadata(
        code_id="direct_prompting",
        display_label="LLM-only",
        family_group="llm_baselines",
        external_root=None,
        notes="Single-shot LLM baseline without tools or retries.",
    ),
    "structured_output_only": BaselineMetadata(
        code_id="structured_output_only",
        display_label="Structured-output only",
        family_group="llm_baselines",
        external_root=None,
        notes="Required-schema prompting baseline without tool feedback or PE-specific closure checks.",
    ),
    "text_only_self_refine": BaselineMetadata(
        code_id="text_only_self_refine",
        display_label="Text Self-Refine",
        family_group="llm_baselines",
        external_root=None,
        notes="Text-only internal draft-critique-revise baseline without executable feedback.",
    ),
    "single_agent_same_tools": BaselineMetadata(
        code_id="single_agent_same_tools",
        display_label="LLM+Tools",
        family_group="llm_baselines",
        external_root=None,
        notes="Single-agent baseline with the same tool surface as the multi-stage system.",
    ),
    "single_agent_retry": BaselineMetadata(
        code_id="single_agent_retry",
        display_label="Single-Agent+Retry",
        family_group="llm_baselines",
        external_root=None,
        notes="Single-agent baseline with evaluator-guided retries and failure-aware revisions.",
    ),
    "generic_two_role_mas": BaselineMetadata(
        code_id="generic_two_role_mas",
        display_label="Generic Two-Role MAS",
        family_group="generic_mas_baselines",
        external_root=None,
        notes="Designer/Critic MAS baseline with matched tool feedback but without private reference-agent modules.",
    ),
    "pe_gpt_style": BaselineMetadata(
        code_id="pe_gpt_style",
        display_label="PE-GPT-style",
        family_group="external_pe_baselines",
        external_root=None,
        notes="Public-framework PE-GPT-style adapter; not a native flyback runtime.",
    ),
    "reference_agent": BaselineMetadata(
        code_id="reference_agent",
        display_label="Reference Agent",
        family_group="external_pe_baselines",
        external_root=None,
        notes="PE-specialized reference-agent probe with theory, grounding, and simulator-aware closure.",
    ),
}


def canonical_baseline_code(run_name: str) -> str:
    return str(run_name or "").split("__", 1)[0]


def get_baseline_metadata(run_name: str) -> BaselineMetadata:
    code_id = canonical_baseline_code(run_name)
    try:
        return BASELINE_METADATA[code_id]
    except KeyError as error:
        raise ValueError(
            f"Unknown baseline metadata for '{run_name}'. Available baselines: {sorted(BASELINE_METADATA)}"
        ) from error


def baseline_metadata_record(run_name: str) -> dict[str, str | None]:
    return asdict(get_baseline_metadata(run_name))
