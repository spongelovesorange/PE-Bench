from __future__ import annotations

from pebench.baselines.methods import (
    BaseBaseline,
    DirectPromptingBaseline,
    GenericTwoRoleMASBaseline,
    PEGPTBaseline,
    ReferenceAgentBaseline,
    SingleAgentRetryBaseline,
    SingleAgentSameToolsBaseline,
    StructuredOutputOnlyBaseline,
    TextOnlySelfRefineBaseline,
)
from pebench.baselines.metadata import (
    BASELINE_METADATA,
    BaselineMetadata,
    baseline_metadata_record,
    canonical_baseline_code,
    get_baseline_metadata,
)


BASELINE_REGISTRY: dict[str, type[BaseBaseline]] = {
    "direct_prompting": DirectPromptingBaseline,
    "structured_output_only": StructuredOutputOnlyBaseline,
    "text_only_self_refine": TextOnlySelfRefineBaseline,
    "single_agent_same_tools": SingleAgentSameToolsBaseline,
    "single_agent_retry": SingleAgentRetryBaseline,
    "generic_two_role_mas": GenericTwoRoleMASBaseline,
    "pe_gpt_style": PEGPTBaseline,
    "reference_agent": ReferenceAgentBaseline,
}


def get_baseline(name: str, **kwargs: object) -> BaseBaseline:
    try:
        return BASELINE_REGISTRY[name](**kwargs)
    except KeyError as error:
        raise ValueError(
            f"Unknown baseline '{name}'. Available baselines: {sorted(BASELINE_REGISTRY)}"
        ) from error


__all__ = [
    "BASELINE_METADATA",
    "BASELINE_REGISTRY",
    "BaselineMetadata",
    "baseline_metadata_record",
    "canonical_baseline_code",
    "get_baseline",
    "get_baseline_metadata",
]
