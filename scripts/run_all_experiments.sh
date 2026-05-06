#!/usr/bin/env zsh
set -euo pipefail

PYTHON="${PYTHON:-python}"
RESULTS_ROOT="results/pebench"
PRIMARY_MODEL="gpt-4.1"
SANITY_MODELS=(gpt-4.1-mini gpt-4.1 gpt-4o-mini o3-mini)
MAIN_BASELINES=(direct_prompting text_only_self_refine single_agent_same_tools single_agent_retry generic_two_role_mas pe_gpt_style reference_agent)
SANITY_BASELINES=(direct_prompting generic_two_role_mas reference_agent)

if [[ -n "${PEBENCH_LLM_API_KEY:-}" ]]; then
  export PEBENCH_LLM_API_KEY
elif [[ -n "${FLYBACKBENCH_LLM_API_KEY:-}" ]]; then
  export PEBENCH_LLM_API_KEY="$FLYBACKBENCH_LLM_API_KEY"
else
  echo "Missing PEBENCH_LLM_API_KEY (or legacy FLYBACKBENCH_LLM_API_KEY)" >&2
  exit 1
fi

export PEBENCH_LLM_BASE_URL="${PEBENCH_LLM_BASE_URL:-${FLYBACKBENCH_LLM_BASE_URL:-https://api.openai.com/v1}}"

for baseline in ${MAIN_BASELINES[@]}; do
  "$PYTHON" scripts/run_pebench_suite.py \
    --track all \
    --topology all \
    --baseline "$baseline" \
    --model "$PRIMARY_MODEL" \
    --seed 1 \
    --temperature 0.2 \
    --api-base "$PEBENCH_LLM_BASE_URL" \
    --api-key-env PEBENCH_LLM_API_KEY \
    --output-root "$RESULTS_ROOT"

done

for model in ${SANITY_MODELS[@]}; do
  for baseline in ${SANITY_BASELINES[@]}; do
    "$PYTHON" scripts/run_pebench_suite.py \
      --track all \
      --topology all \
      --baseline "$baseline" \
      --model "$model" \
      --seed 1 \
      --temperature 0.2 \
      --api-base "$PEBENCH_LLM_BASE_URL" \
      --api-key-env PEBENCH_LLM_API_KEY \
      --output-root "$RESULTS_ROOT"
  done

done

for flag in "--disable-formula-guardrails" "--disable-component-grounding" "--disable-correction-memory"; do
  "$PYTHON" scripts/run_pebench_suite.py \
    --track all \
    --topology all \
    --baseline reference_agent \
    --model "$PRIMARY_MODEL" \
    --seed 1 \
    --temperature 0.2 \
    --api-base "$PEBENCH_LLM_BASE_URL" \
    --api-key-env PEBENCH_LLM_API_KEY \
    --output-root "$RESULTS_ROOT" \
    $flag

done

echo "All experiments complete."
