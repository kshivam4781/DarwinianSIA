"""Tests for scripts/prepare_gpqa_diamond.py (Tick 25 real GPQA materializer)."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from prepare_gpqa_diamond import (  # noqa: E402
    SOURCE_TAG,
    hf_row_to_sia,
    live_g2_next_steps_message,
    load_rows_from_csv,
    materialize_from_csv,
    rows_to_sia_questions,
    write_diamond_task_tree,
)
from prepare_gpqa_smoke_data import is_synthetic_smoke  # noqa: E402


def test_live_g2_next_steps_anthropic_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tick 307: diamond Next lines must not hard-demand Anthropic under Nebius meta."""
    monkeypatch.delenv("ICML_META_AGENT_PROFILE", raising=False)
    monkeypatch.delenv("SIA_META_AGENT_PROFILE", raising=False)
    text = live_g2_next_steps_message()
    assert "NEBIUS_API_KEY" in text
    assert "run_g2_smoke.py --live" in text
    assert "optional" in text.lower()
    assert "ANTHROPIC_API_KEY + NEBIUS_API_KEY" not in text


def _fake_hf_row(i: int = 0) -> dict[str, str]:
    # Invented content — not from GPQA (license forbids publishing examples).
    return {
        "Question": f"Harness physics item {i}: what is 2+2?",
        "Correct Answer": "four",
        "Incorrect Answer 1": "three",
        "Incorrect Answer 2": "five",
        "Incorrect Answer 3": "zero",
        "High-level domain": "Physics",
        "Subdomain": "Arithmetic",
    }


def test_hf_row_to_sia_shuffles_and_marks_correct() -> None:
    import random

    row = _fake_hf_row(1)
    q = hf_row_to_sia(row, qid=7, rng=random.Random(0))
    assert q["id"] == 7
    assert q["source"] == SOURCE_TAG
    assert q["domain"] == "Physics"
    assert set(q["options"]) == {"A", "B", "C", "D"}
    assert q["options"][q["correct_answer_letter"]] == "four"
    assert "three" in q["options"].values()


def test_rows_to_sia_questions_respects_n() -> None:
    rows = [_fake_hf_row(i) for i in range(10)]
    qs = rows_to_sia_questions(rows, n=3, seed=42)
    assert len(qs) == 3
    assert qs[0]["id"] == 0


def test_write_diamond_not_synthetic(tmp_path: Path) -> None:
    task_dir = tmp_path / "gpqa"
    task_dir.mkdir()
    qs = rows_to_sia_questions([_fake_hf_row(i) for i in range(5)], n=5, seed=1)
    write_diamond_task_tree(task_dir, qs)

    pub = json.loads((task_dir / "data" / "public" / "diamond_questions.json").read_text())
    priv = json.loads((task_dir / "data" / "private" / "diamond_questions.json").read_text())
    assert "correct_answer_letter" not in pub[0]
    assert priv[0]["correct_answer_letter"] in "ABCD"
    assert priv[0]["source"] == SOURCE_TAG
    assert is_synthetic_smoke(task_dir) is False


def test_materialize_from_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "gpqa_diamond.csv"
    rows = [_fake_hf_row(i) for i in range(8)]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    root = tmp_path / "repo"
    task = root / "SIA" / "sia" / "tasks" / "gpqa"
    task.mkdir(parents=True)

    wrote = materialize_from_csv(
        csv_path,
        ["SIA"],
        n=5,
        seed=2,
        force=True,
        repo_root=root,
    )
    assert any("gpqa" in p for p in wrote)
    assert is_synthetic_smoke(task) is False
    priv = json.loads((task / "data" / "private" / "diamond_questions.json").read_text())
    assert len(priv) == 5


def test_load_rows_from_csv_roundtrip(tmp_path: Path) -> None:
    csv_path = tmp_path / "mini.csv"
    row = _fake_hf_row(0)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row.keys()))
        w.writeheader()
        w.writerow(row)
    loaded = load_rows_from_csv(csv_path)
    assert loaded[0]["Correct Answer"] == "four"


def test_download_gpqa_diamond_csv_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_gpqa_diamond import download_gpqa_diamond_csv

    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.delenv("HUGGINGFACE_HUB_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="HF_TOKEN"):
        download_gpqa_diamond_csv(token=None)


def test_download_gpqa_diamond_csv_public_mirror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 497: public OpenAI mirror writes CSV without HF token."""
    from prepare_gpqa_diamond import download_gpqa_diamond_csv_public_mirror

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            header = (
                b"Question,Correct Answer,Incorrect Answer 1,"
                b"Incorrect Answer 2,Incorrect Answer 3\n"
            )
            rows = b"Harness Q?,four,three,five,zero\n" * 40
            return header + rows

    def _urlopen(url, timeout=120.0):  # noqa: ARG001
        assert "openaipublic.blob.core.windows.net" in url or url.startswith("http")
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    dest = tmp_path / "gpqa_diamond.csv"
    path = download_gpqa_diamond_csv_public_mirror(dest)
    assert path == dest.resolve()
    assert path.stat().st_size >= 64
    # Second call reuses without network.
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no network")),
    )
    path2 = download_gpqa_diamond_csv_public_mirror(dest)
    assert path2 == path


def test_public_mirror_dns_fallback_uses_dig_ip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tick 557: recursive-DNS failure → dig @8.8.8.8 + Host/SNI IP GET."""
    import urllib.error

    import prepare_gpqa_diamond as prep

    payload = (
        b"Question,Correct Answer,Incorrect Answer 1,"
        b"Incorrect Answer 2,Incorrect Answer 3\n"
        + b"Harness Q?,four,three,five,zero\n" * 40
    )

    def _boom(*_a, **_k):
        raise urllib.error.URLError(
            OSError(-3, "Temporary failure in name resolution")
        )

    monkeypatch.setattr("urllib.request.urlopen", _boom)
    monkeypatch.setattr(
        prep, "_resolve_host_via_public_dns", lambda _host: "203.0.113.10"
    )
    seen: dict[str, object] = {}

    def _via_ip(**kwargs):
        seen.update(kwargs)
        return payload

    monkeypatch.setattr(prep, "_http_get_bytes_via_ip", _via_ip)
    dest = tmp_path / "gpqa_diamond.csv"
    path = prep.download_gpqa_diamond_csv_public_mirror(dest)
    assert path == dest.resolve()
    assert path.read_bytes().startswith(b"Question")
    assert seen["host"] == "openaipublic.blob.core.windows.net"
    assert seen["ip"] == "203.0.113.10"
    assert seen["scheme"] == "https"


def test_public_mirror_dns_helpers_source_lock() -> None:
    """Tick 557: public-mirror download keeps dig@8.8.8.8 DNS fallback helpers."""
    src = Path(__file__).resolve().parents[1] / "scripts" / "prepare_gpqa_diamond.py"
    text = src.read_text(encoding="utf-8")
    assert "def _resolve_host_via_public_dns" in text
    assert "def _urlopen_bytes_with_dns_fallback" in text
    assert "@8.8.8.8" in text
    assert "Tick 557" in text
    assert "_urlopen_bytes_with_dns_fallback(mirror" in text


def test_cli_from_public_mirror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from prepare_gpqa_diamond import main as diamond_main

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self) -> bytes:
            header = (
                b"Question,Correct Answer,Incorrect Answer 1,"
                b"Incorrect Answer 2,Incorrect Answer 3\n"
            )
            rows = b"Harness Q?,four,three,five,zero\n" * 40
            return header + rows

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    # Minimal SIA/sia-upstream task dirs under tmp as repo root substitute:
    # CLI uses REPO_ROOT fixed to workspace — materialize into a fake via --roots
    # is relative to repo. Use materialize_from_public_mirror directly instead.
    from prepare_gpqa_diamond import materialize_from_public_mirror

    sia = tmp_path / "SIA" / "sia" / "tasks" / "gpqa"
    sia.mkdir(parents=True)
    (tmp_path / "SIA" / "sia" / "tasks" / "_shared").mkdir(parents=True)
    dest = tmp_path / "mirror.csv"
    wrote = materialize_from_public_mirror(
        ["SIA"],
        n=5,
        seed=1,
        force=True,
        dest=dest,
        repo_root=tmp_path,
    )
    assert wrote
    assert not is_synthetic_smoke(sia)
    # CLI flag is registered.
    with pytest.raises(SystemExit):
        diamond_main(["--help"])

