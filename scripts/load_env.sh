#!/usr/bin/env bash
# Load .env into the current shell (does not print secrets).
# ICML Thesis 1 (Tick 289/308–312): Nebius-first. Anthropic is optional under
# default kimi-nebius-pydantic-meta; HF_TOKEN needed for --fetch-diamond unless
# a local gpqa_diamond.csv is present (see docs/ICML_HUMAN_UNBLOCK.md).
#
# Usage (must be sourced, not executed):
#   source scripts/load_env.sh
#   . scripts/load_env.sh

_ICML_LOAD_ENV_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
_ICML_ENV_FILE="${_ICML_LOAD_ENV_ROOT}/.env"

if [[ ! -f "${_ICML_ENV_FILE}" ]]; then
  echo "No .env file found. Copy .env.example to .env and add your keys." >&2
  unset _ICML_LOAD_ENV_ROOT _ICML_ENV_FILE
  return 1 2>/dev/null || exit 1
fi

# Only export missing names so process/automation secrets win (Tick 277 pattern).
while IFS= read -r line || [[ -n "${line}" ]]; do
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "${line}" || "${line}" == \#* ]] && continue
  [[ "${line}" != *=* ]] && continue
  name="${line%%=*}"
  value="${line#*=}"
  name="${name#"${name%%[![:space:]]*}"}"
  name="${name%"${name##*[![:space:]]}"}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  value="${value#\"}"
  value="${value%\"}"
  value="${value#\'}"
  value="${value%\'}"
  [[ -z "${name}" || -z "${value}" ]] && continue
  if [[ -z "${!name+x}" || -z "${!name}" ]]; then
    export "${name}=${value}"
  fi
done < "${_ICML_ENV_FILE}"

echo "Loaded keys from .env (ICML: Nebius required; Anthropic optional; HF or CSV for diamond):"
if [[ -n "${NEBIUS_API_KEY:-}" ]]; then
  echo "  NEBIUS_API_KEY: SET (required for ICML live)"
else
  echo "  NEBIUS_API_KEY: missing (required for ICML live G2→G4)"
fi
if [[ -n "${HF_TOKEN:-}${HUGGINGFACE_HUB_TOKEN:-}" ]]; then
  echo "  HF_TOKEN / HUGGINGFACE_HUB_TOKEN: SET (for --fetch-diamond)"
else
  echo "  HF_TOKEN: missing (optional if local gpqa_diamond.csv is present)"
fi
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "  ANTHROPIC_API_KEY: SET (optional under Nebius meta)"
else
  echo "  ANTHROPIC_API_KEY: absent (optional — only needed if ICML_META_AGENT_PROFILE=default-meta)"
fi
if [[ -n "${TAVILY_API_KEY:-}" ]]; then
  echo "  TAVILY_API_KEY: SET"
else
  echo "  TAVILY_API_KEY: absent (optional)"
fi

unset _ICML_LOAD_ENV_ROOT _ICML_ENV_FILE
return 0 2>/dev/null || true
