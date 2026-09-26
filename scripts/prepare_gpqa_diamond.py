#!/usr/bin/env python3
"""Materialize real GPQA diamond JSON for live G2–G4 (never commit the data).

Cloud live G2 is blocked when only the synthetic smoke fixture exists
(``prepare_gpqa_smoke_data.py``). This script converts HuggingFace
``Idavidrein/gpqa`` / ``gpqa_diamond`` rows into SIA's
``diamond_questions.json`` schema:

  public/  — agent-visible rows (no ``correct_answer_letter``)
  private/ — held-out answers for eval

Sources (first match wins when using CLI defaults):
  1. ``--from-csv PATH`` — local/exported ``gpqa_diamond.csv``
  2. ``--from-hf`` — download via ``huggingface_hub`` (needs ``HF_TOKEN`` /
     ``HUGGINGFACE_HUB_TOKEN`` and accepted dataset access)

**License:** GPQA forbids posting examples online. Do **not** commit
``diamond_questions.json`` from this script. Data dirs stay gitignored.

Examples (Linux/cloud: python3; Windows venv: python):
  python3 scripts/prepare_gpqa_diamond.py --from-csv /tmp/gpqa_diamond.csv --n 5
  python3 scripts/prepare_gpqa_diamond.py --from-hf --n 5 --seed 1
  python3 scripts/prepare_gpqa_diamond.py --from-hf --roots SIA sia-upstream --force
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "scripts"))

from icml_env_checks import (  # noqa: E402
    icml_human_required_secrets_phrase,
    icml_python_cli,
)

DEFAULT_ROOTS = ("SIA", "sia-upstream")
HF_REPO_ID = "Idavidrein/gpqa"
HF_FILENAME = "gpqa_diamond.csv"
SOURCE_TAG = "gpqa_diamond"


def live_g2_next_steps_message() -> str:
    """Operator Next lines after diamond materialize (Tick 307 / Tick 292 phrase).

    Tick 292 fixed gate/cron human text, but this script still hard-coded
    ``ANTHROPIC_API_KEY + NEBIUS_API_KEY`` — operators waited on an optional key.
    Tick 323: use ``icml_python_cli()`` (cold Linux has no bare ``python``).
    """
    secrets = icml_human_required_secrets_phrase(for_fetch_diamond=True)
    py = icml_python_cli()
    return (
        "\nNext:\n"
        f"  {py} scripts/run_g2_smoke.py --preflight-only --run-id 1850\n"
        f"  # when {secrets} present:\n"
        f"  {py} scripts/run_g2_smoke.py --live --run-id 1300 --fetch-diamond\n"
        "  # or: bash scripts/icml_cron_entry.sh\n"
    )

TASK_MD = """# GPQA Diamond (local materialization)

Questions from HuggingFace `Idavidrein/gpqa` (`gpqa_diamond`).

**Do not commit** these JSON files. GPQA terms forbid publishing examples online.
Replace or regenerate with `scripts/prepare_gpqa_diamond.py` when needed.
"""

# Column aliases observed across GPQA CSV exports / HF configs.
_Q_KEYS = ("Question", "question")
_CORRECT_KEYS = ("Correct Answer", "correct_answer", "Correct answer")
_INCORRECT_KEYS = (
    ("Incorrect Answer 1", "Incorrect Answer 2", "Incorrect Answer 3"),
    ("incorrect_answer_1", "incorrect_answer_2", "incorrect_answer_3"),
)
_DOMAIN_KEYS = ("High-level domain", "domain", "Domain", "High level domain")
_SUBDOMAIN_KEYS = ("Subdomain", "subdomain", "Sub-domain")


def _first(row: Mapping[str, Any], keys: Sequence[str]) -> Any:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _incorrect_answers(row: Mapping[str, Any]) -> list[str]:
    for keys in _INCORRECT_KEYS:
        vals = [row.get(k) for k in keys]
        if all(v not in (None, "") for v in vals):
            return [str(v) for v in vals]
    # Fallback: any Incorrect Answer* columns in order
    keyed = sorted(
        (k, v)
        for k, v in row.items()
        if str(k).lower().startswith("incorrect") and v not in (None, "")
    )
    if len(keyed) >= 3:
        return [str(keyed[i][1]) for i in range(3)]
    raise ValueError(f"row missing three incorrect answers; keys={list(row.keys())}")


def hf_row_to_sia(
    row: Mapping[str, Any],
    *,
    qid: int,
    rng: random.Random,
) -> dict[str, Any]:
    """Convert one HF/CSV GPQA row into SIA public+private question dict."""
    question = _first(row, _Q_KEYS)
    correct = _first(row, _CORRECT_KEYS)
    if question is None or correct is None:
        raise ValueError(f"row missing Question/Correct Answer; keys={list(row.keys())}")
    incorrect = _incorrect_answers(row)
    choices = [str(correct), *incorrect]
    if len(choices) != 4:
        raise ValueError(f"expected 4 choices, got {len(choices)}")
    if len(set(choices)) < 4:
        # Rare duplicate strings — still shuffle but keep positions distinct letters
        pass
    rng.shuffle(choices)
    letters = ["A", "B", "C", "D"]
    options = {let: text for let, text in zip(letters, choices)}
    correct_letter = next(let for let, text in options.items() if text == str(correct))
    domain = _first(row, _DOMAIN_KEYS) or "unknown"
    subdomain = _first(row, _SUBDOMAIN_KEYS) or "unknown"
    return {
        "id": qid,
        "Question": str(question),
        "options": options,
        "correct_answer_letter": correct_letter,
        "domain": str(domain),
        "subdomain": str(subdomain),
        "source": SOURCE_TAG,
    }


def rows_to_sia_questions(
    rows: Iterable[Mapping[str, Any]],
    *,
    n: int | None = None,
    seed: int = 1,
    start_id: int = 0,
) -> list[dict[str, Any]]:
    """Convert many HF/CSV rows; optionally take first ``n`` after conversion."""
    rng = random.Random(seed)
    out: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if n is not None and len(out) >= n:
            break
        out.append(hf_row_to_sia(row, qid=start_id + i, rng=rng))
    if n is not None and len(out) < n:
        raise ValueError(f"only converted {len(out)} rows; need n={n}")
    return out


def _public_view(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for q in questions:
        row = {k: v for k, v in q.items() if k != "correct_answer_letter"}
        out.append(row)
    return out


def write_diamond_task_tree(task_dir: Path, questions: list[dict[str, Any]]) -> None:
    """Write public/private diamond_questions.json (+ task.md) under task_dir."""
    if not questions:
        raise ValueError("questions must be non-empty")
    pub = task_dir / "data" / "public"
    priv = task_dir / "data" / "private"
    pub.mkdir(parents=True, exist_ok=True)
    priv.mkdir(parents=True, exist_ok=True)
    (pub / "diamond_questions.json").write_text(
        json.dumps(_public_view(questions), indent=2) + "\n", encoding="utf-8"
    )
    (priv / "diamond_questions.json").write_text(
        json.dumps(questions, indent=2) + "\n", encoding="utf-8"
    )
    (pub / "task.md").write_text(TASK_MD, encoding="utf-8")


def load_rows_from_csv(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    rows = [dict(r) for r in reader]
    if not rows:
        raise ValueError(f"empty CSV: {path}")
    return rows


def download_gpqa_diamond_csv(
    *,
    token: str | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """Download ``gpqa_diamond.csv`` via huggingface_hub (gated dataset)."""
    tok = (token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_HUB_TOKEN") or "").strip()
    if not tok:
        raise RuntimeError(
            "HF_TOKEN / HUGGINGFACE_HUB_TOKEN required to download gated "
            f"{HF_REPO_ID}. Accept dataset terms on HuggingFace, then set the token."
        )
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "huggingface_hub is not installed. "
            "Run: pip install huggingface_hub"
        ) from exc

    kwargs: dict[str, Any] = {
        "repo_id": HF_REPO_ID,
        "filename": HF_FILENAME,
        "repo_type": "dataset",
        "token": tok,
    }
    if cache_dir is not None:
        kwargs["cache_dir"] = str(cache_dir)
    path = hf_hub_download(**kwargs)
    return Path(path)


def materialize_from_rows(
    roots: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
    *,
    n: int = 5,
    seed: int = 1,
    force: bool = False,
    repo_root: Path | None = None,
) -> list[str]:
    """Write diamond JSON under each root's sia/tasks/gpqa. Returns written paths."""
    root = repo_root or REPO_ROOT
    questions = rows_to_sia_questions(rows, n=n, seed=seed)
    wrote: list[str] = []
    for root_name in roots:
        repo = (root / root_name).resolve()
        task_dir = repo / "sia" / "tasks" / "gpqa"
        if not task_dir.is_dir():
            raise FileNotFoundError(f"missing task dir: {task_dir}")
        pub_q = task_dir / "data" / "public" / "diamond_questions.json"
        if pub_q.exists() and not force:
            # Keep existing unless force; still useful when real data already present.
            wrote.append(f"{task_dir} (kept existing; pass --force to overwrite)")
            continue
        write_diamond_task_tree(task_dir, questions)
        # Ensure _shared exists (same as smoke helper)
        shared = repo / "sia" / "tasks" / "_shared"
        shared.mkdir(parents=True, exist_ok=True)
        sample = shared / "sample_agent_execution.json"
        if not sample.exists():
            sample.write_text("[]\n", encoding="utf-8")
        wrote.append(str(task_dir))
    return wrote


def materialize_from_csv(
    csv_path: Path,
    roots: Sequence[str],
    *,
    n: int = 5,
    seed: int = 1,
    force: bool = False,
    repo_root: Path | None = None,
) -> list[str]:
    rows = load_rows_from_csv(csv_path)
    return materialize_from_rows(
        roots, rows, n=n, seed=seed, force=force, repo_root=repo_root
    )


def materialize_from_hf(
    roots: Sequence[str],
    *,
    n: int = 5,
    seed: int = 1,
    force: bool = False,
    token: str | None = None,
    cache_dir: Path | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    csv_path = download_gpqa_diamond_csv(token=token, cache_dir=cache_dir)
    return materialize_from_csv(
        csv_path, roots, n=n, seed=seed, force=force, repo_root=repo_root
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from-csv",
        type=Path,
        help="Path to gpqa_diamond.csv (or compatible export)",
    )
    src.add_argument(
        "--from-hf",
        action="store_true",
        help="Download Idavidrein/gpqa gpqa_diamond.csv via HF token",
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=list(DEFAULT_ROOTS),
        help="Repo subtrees containing sia/tasks/gpqa",
    )
    parser.add_argument("--n", type=int, default=5, help="Questions to write (default 5)")
    parser.add_argument("--seed", type=int, default=1, help="Shuffle seed for option letters")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing diamond_questions.json",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Optional HF cache directory",
    )
    args = parser.parse_args(argv)

    try:
        if args.from_csv is not None:
            wrote = materialize_from_csv(
                args.from_csv,
                args.roots,
                n=args.n,
                seed=args.seed,
                force=args.force,
            )
        else:
            wrote = materialize_from_hf(
                args.roots,
                n=args.n,
                seed=args.seed,
                force=args.force,
                cache_dir=args.cache_dir,
            )
    except Exception as exc:
        print(f"GPQA diamond prepare FAIL: {exc}", file=sys.stderr)
        return 1

    print("GPQA diamond fixture ready (do not commit JSON):")
    for p in wrote:
        print(f"  {p}")
    print(live_g2_next_steps_message(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
