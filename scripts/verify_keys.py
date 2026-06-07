"""Verify API keys without printing secrets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


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


def main() -> int:
    load_dotenv()
    print("SIA-CABS API key verification\n")

    checks = [
        ("Anthropic", check_anthropic, True),
        ("Nebius", check_nebius, True),
        ("Tavily", check_tavily, False),
    ]
    required_ok = True
    for name, checker, required in checks:
        ok, message = checker()
        status = "PASS" if ok else ("FAIL" if required else "SKIP")
        if required and not ok:
            required_ok = False
        print(f"[{status}] {name}: {message}")

    print()
    if required_ok:
        print("Required keys verified. Tavily is optional for --tavily / sia-cabs-tools ground.")
        return 0
    print("Fix failing required keys, then re-run: python scripts/verify_keys.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
