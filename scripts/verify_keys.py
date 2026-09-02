"""Verify API keys without printing secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


def load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


def anthropic_is_required() -> bool:
    """True when ICML/hackathon live stack still needs Anthropic for meta.

    Tick 308: under default Nebius pydantic-ai meta (Tick 289), Anthropic is
    optional — operators running this script after adding only NEBIUS must not
    see a hard FAIL that blocks unblocking live G2→G4.
    """
    try:
        from icml_env_checks import icml_meta_requires_anthropic

        return bool(icml_meta_requires_anthropic())
    except Exception:
        # Conservative fallback if env checks are unavailable.
        return True


def check_anthropic() -> tuple[bool, str]:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return False, "ANTHROPIC_API_KEY is not set"
    if not key.startswith("sk-ant-"):
        return False, "ANTHROPIC_API_KEY should start with sk-ant-"

    try:
        import anthropic
    except ImportError:
        return False, "anthropic package not installed (pip install anthropic)"

    try:
        client = anthropic.Anthropic(api_key=key)
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=8,
            messages=[{"role": "user", "content": "Reply with OK"}],
        )
        return True, "Anthropic key works (Haiku test call succeeded)"
    except Exception as exc:
        return False, f"Anthropic key failed: {exc}"


def check_nebius() -> tuple[bool, str]:
    key = os.environ.get("NEBIUS_API_KEY", "").strip()
    if not key:
        return False, "NEBIUS_API_KEY is not set"

    base_url = "https://api.tokenfactory.us-central1.nebius.com/v1/"

    try:
        from openai import OpenAI
    except ImportError:
        return False, "openai package not installed (pip install openai)"

    try:
        client = OpenAI(base_url=base_url, api_key=key)
        response = client.chat.completions.create(
            model="moonshotai/Kimi-K2.6",
            max_tokens=8,
            messages=[{"role": "user", "content": "Reply with OK"}],
        )
        text = (response.choices[0].message.content or "").strip()
        return True, f"Nebius key works (Kimi test call succeeded, reply={text[:20]!r})"
    except Exception as exc:
        return False, f"Nebius key failed: {exc}"


def check_tavily() -> tuple[bool, str]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not key:
        return False, "TAVILY_API_KEY is not set (optional for Layer 2)"

    try:
        from cabs.tavily_client import TavilyClient

        client = TavilyClient(api_key=key)
        result = client.search("self-improving AI agents memory techniques", max_results=1)
        n = len(result.results)
        return True, f"Tavily key works (search returned {n} result(s))"
    except Exception as exc:
        return False, f"Tavily key failed: {exc}"


def required_key_checks() -> list[tuple[str, object, bool]]:
    """Ordered (name, checker, required) rows for verify_keys (Tick 308)."""
    return [
        ("Anthropic", check_anthropic, anthropic_is_required()),
        ("Nebius", check_nebius, True),
        ("Tavily", check_tavily, False),
    ]


def main() -> int:
    load_dotenv()
    print("SIA-CABS API key verification\n")

    anth_required = anthropic_is_required()
    if not anth_required:
        print(
            "Note: ANTHROPIC_API_KEY is optional under Tick 289 Nebius "
            "pydantic-ai meta (required only if ICML_META_AGENT_PROFILE="
            "default-meta).\n"
        )

    checks = required_key_checks()
    required_ok = True
    for name, checker, required in checks:
        ok, message = checker()  # type: ignore[operator]
        status = "PASS" if ok else ("FAIL" if required else "SKIP")
        if required and not ok:
            required_ok = False
        print(f"[{status}] {name}: {message}")

    print()
    if required_ok:
        print(
            "Required keys verified. Tavily is optional for --tavily / "
            "sia-cabs-tools ground."
        )
        if not anth_required:
            print(
                "Anthropic skipped/optional — ICML live needs NEBIUS_API_KEY + "
                "(HF_TOKEN or local gpqa_diamond.csv); see docs/ICML_HUMAN_UNBLOCK.md."
            )
        return 0
    print("Fix failing required keys, then re-run: python scripts/verify_keys.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
