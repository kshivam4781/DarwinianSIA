#!/usr/bin/env python3
"""Phase 0 verification: Python version, .env keys, Nebius API connectivity."""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request


def _check_python() -> bool:
    ok = sys.version_info >= (3, 11)
    print(f"[{'OK' if ok else 'FAIL'}] Python {sys.version.split()[0]} (need >= 3.11)")
    return ok


def _check_keys() -> bool:
    from sia.env_loader import load_project_dotenv, required_keys_present

    path = load_project_dotenv()
    print(f"[INFO] .env loaded from: {path}" if path else "[WARN] No .env file found")

    status = required_keys_present("NEBIUS_API_KEY", "ANTHROPIC_API_KEY")
    nebius_ok = status["NEBIUS_API_KEY"]
    anthropic_ok = status["ANTHROPIC_API_KEY"]
    print(f"[{'OK' if nebius_ok else 'FAIL'}] NEBIUS_API_KEY set (required)")
    print(f"[{'OK' if anthropic_ok else 'WARN'}] ANTHROPIC_API_KEY set (optional fallback)")
    return nebius_ok


def _check_nebius_api() -> bool:
    key = os.getenv("NEBIUS_API_KEY")
    if not key:
        print("[FAIL] Nebius API check skipped — no key")
        return False

    url = "https://api.tokenfactory.us-central1.nebius.com/v1/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(500).decode("utf-8", errors="replace")
            ok = resp.status == 200
            print(f"[{'OK' if ok else 'FAIL'}] Nebius Token Factory API reachable (HTTP {resp.status})")
            if ok and "data" in body:
                print("[OK] Models endpoint returned JSON")
            return ok
    except urllib.error.HTTPError as e:
        print(f"[FAIL] Nebius API HTTP {e.code}: {e.reason}")
        return False
    except OSError as e:
        print(f"[FAIL] Nebius API connection error: {e}")
        return False


def main() -> int:
    print("=== Phase 0 verification ===\n")
    results = [_check_python(), _check_keys(), _check_nebius_api()]
    print()
    if all(results):
        print("Phase 0 gates 0–0.5 PASSED (env + API). Ready for venv smoke / Gate 1 run.")
        return 0
    print("Phase 0 FAILED — fix items above before proceeding.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
