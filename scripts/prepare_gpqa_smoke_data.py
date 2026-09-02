#!/usr/bin/env python3
"""Materialize a tiny GPQA fixture so CLI dry-run / G2 smoke can resolve --task gpqa.

Cloud checkouts often omit ``sia/tasks/gpqa/data/`` (gitignored). Offline unit tests
build the same shape under tmp_path; this script writes it into the real task tree so
``sia run --task gpqa ...`` works without rediscovering the layout.

Modes:
  smoke (default) — synthetic 5-question fixture (no API; enough for dry-run / harness)
  check           — verify layout only; exit 1 if missing

Does NOT download the real GPQA diamond set (license / size). For live G2–G4, replace
``diamond_questions.json`` under public/private with the real files (same schema) after
API keys are present.

Examples:
  python scripts/prepare_gpqa_smoke_data.py
  python scripts/prepare_gpqa_smoke_data.py --roots SIA sia-upstream
  python scripts/prepare_gpqa_smoke_data.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from icml_env_checks import icml_human_required_secrets_phrase  # noqa: E402

DEFAULT_ROOTS = ("SIA", "sia-upstream")


def live_g2_next_steps_message() -> str:
    """Operator Next lines after smoke fixture write (Tick 307 / Tick 292 phrase).

    Tick 292 fixed gate/cron human text, but this script still hard-coded
    ``ANTHROPIC_API_KEY + NEBIUS_API_KEY`` for live G2 — misleading under Nebius meta.
    """
    secrets = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    return (
        "\nNext (dry-run Condition D / G2 harness, unused run_id):\n"
        "  cd SIA && python -m sia run "
        "--task gpqa --darwinian --cabs --cabs-inline "
        "--population_size 2 --elite_count 1 --max_gen 2 "
        "--run_id 1800 --eval_subset 5 --dry-run --no-web --seed 42\n"
        "Live G2: replace diamond_questions.json with real GPQA "
        f"(``scripts/prepare_gpqa_diamond.py``), drop --dry-run, set {secrets}, "
        "unused run_id, budget check. Prefer: ``bash scripts/icml_cron_entry.sh``.\n"
    )

TASK_MD = """# GPQA smoke fixture (synthetic)

Tiny synthetic questions for harness / dry-run / G2 layout checks.

**Not** the real GPQA diamond benchmark. Replace ``diamond_questions.json`` in
``data/public`` and ``data/private`` with the licensed GPQA files before paid runs.
"""


def _questions(n: int = 5) -> list[dict]:
    return [
        {
            "id": i,
            "Question": f"Smoke Q{i}: which option is correct?",
            "options": {"A": "alpha", "B": "beta", "C": "gamma", "D": "delta"},
            "correct_answer_letter": "A",
            "domain": "smoke",
            "subdomain": "harness",
        }
        for i in range(n)
    ]


def _public_view(questions: list[dict]) -> list[dict]:
    """Agent-visible rows: drop ground-truth letter (private keeps it)."""
    out = []
    for q in questions:
        row = {k: v for k, v in q.items() if k != "correct_answer_letter"}
        out.append(row)
    return out


def prepare_task_tree(task_dir: Path, n: int = 5) -> None:
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    ref = task_dir / "reference"
    pub.mkdir(parents=True, exist_ok=True)
    priv.mkdir(parents=True, exist_ok=True)
    ref.mkdir(parents=True, exist_ok=True)

    qs = _questions(n)
    (pub / "diamond_questions.json").write_text(
        json.dumps(_public_view(qs), indent=2) + "\n", encoding="utf-8"
    )
    (priv / "diamond_questions.json").write_text(
        json.dumps(qs, indent=2) + "\n", encoding="utf-8"
    )
    (pub / "task.md").write_text(TASK_MD, encoding="utf-8")

    # Keep existing reference agent if present; otherwise stub for structure tests.
    ref_agent = ref / "reference_target_agent.py"
    if not ref_agent.exists():
        ref_agent.write_text(
            '"""Stub reference agent for smoke fixture."""\nprint("gpqa-smoke-ref")\n',
            encoding="utf-8",
        )
    samples = ref / "SAMPLE_TASK_DESCRIPTIONS.md"
    if not samples.exists():
        samples.write_text("# GPQA smoke samples\n", encoding="utf-8")


def ensure_shared(repo_root: Path) -> None:
    shared = repo_root / "sia" / "tasks" / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    sample = shared / "sample_agent_execution.json"
    if not sample.exists():
        sample.write_text("[]\n", encoding="utf-8")


def check_task_tree(task_dir: Path) -> list[str]:
    required = [
        task_dir / "data" / "public" / "diamond_questions.json",
        task_dir / "data" / "public" / "task.md",
        task_dir / "data" / "private" / "diamond_questions.json",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    return missing


def is_synthetic_smoke(task_dir: Path) -> bool:
    """True when diamond_questions.json looks like this script's synthetic fixture.

    Live/paid G2 must refuse synthetic answers (domain=smoke / Smoke Q* text).
    Missing files → False (caller should use check_task_tree separately).
    """
    priv = task_dir / "data" / "private" / "diamond_questions.json"
    pub = task_dir / "data" / "public" / "diamond_questions.json"
    path = priv if priv.is_file() else pub
    if not path.is_file():
        return False
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(rows, list) or not rows:
        return False
    sample = rows[0] if isinstance(rows[0], dict) else {}
    domain = str(sample.get("domain") or "").lower()
    question = str(sample.get("Question") or sample.get("question") or "")
    if domain == "smoke":
        return True
    if question.startswith("Smoke Q"):
        return True
    # All-smoke domains count even if first row was weird.
    domains = {
        str(r.get("domain") or "").lower()
        for r in rows
        if isinstance(r, dict)
    }
    return domains == {"smoke"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roots",
        nargs="+",
        default=list(DEFAULT_ROOTS),
        help="Repo subtrees containing sia/tasks/gpqa (default: SIA sia-upstream)",
    )
    parser.add_argument(
        "--n",
        type=int,
        default=5,
        help="Number of synthetic questions (default 5; G2 uses --eval_subset ≤5)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only verify layout; do not write",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing diamond_questions.json even if present",
    )
    args = parser.parse_args(argv)

    wrote: list[str] = []
    checked_ok: list[str] = []
    errors: list[str] = []

    for root_name in args.roots:
        repo = (REPO_ROOT / root_name).resolve()
        task_dir = repo / "sia" / "tasks" / "gpqa"
        if not task_dir.is_dir():
            errors.append(f"missing task dir: {task_dir}")
            continue

        if args.check:
            missing = check_task_tree(task_dir)
            if missing:
                errors.extend(f"missing: {m}" for m in missing)
            else:
                checked_ok.append(str(task_dir))
            continue

        pub_q = task_dir / "data" / "public" / "diamond_questions.json"
        if pub_q.exists() and not args.force:
            # Preserve real GPQA if already installed; still ensure task.md exists.
            pub = task_dir / "data" / "public"
            pub.mkdir(parents=True, exist_ok=True)
            task_md = pub / "task.md"
            if not task_md.exists():
                task_md.write_text(TASK_MD, encoding="utf-8")
            checked_ok.append(f"{task_dir} (kept existing questions)")
            ensure_shared(repo)
            continue

        prepare_task_tree(task_dir, n=args.n)
        ensure_shared(repo)
        wrote.append(str(task_dir))

    if args.check:
        if errors:
            print("GPQA layout CHECK FAIL:", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        print("GPQA layout CHECK OK:")
        for p in checked_ok:
            print(f"  - {p}")
        return 0

    if errors:
        print("GPQA smoke prepare partial FAIL:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)

    print("GPQA smoke fixture ready:")
    for p in wrote:
        print(f"  wrote: {p}/data/{{public,private}}/")
    for p in checked_ok:
        print(f"  kept:  {p}")

    print(live_g2_next_steps_message(), end="")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
