"""Tick 445: finish/present judge demos must read ICML_READY STATUS header-only."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.mark.parametrize(
    "module_name",
    ("finish_hackathon", "present_hackathon"),
)
def test_judge_icml_status_header_only_despite_prose_before_header(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module_name: str
) -> None:
    """Pre-445 ``re.search`` matched mid-line ``**STATUS: READY**`` before header."""
    docs = tmp_path / "docs"
    docs.mkdir()
    ready = docs / "ICML_READY.md"
    ready.write_text(
        "_Note: never set **STATUS: READY** from offline / trust refuse alone._\n\n"
        "**STATUS: IN_PROGRESS**\n\n"
        "- [ ] PRIMARY\n"
        "_Also mentions **STATUS: READY** in footer._\n",
        encoding="utf-8",
    )

    mod = importlib.import_module(module_name)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod._icml_status_line() == "IN_PROGRESS"

    ready.write_text(
        "_Prose **STATUS: IN_PROGRESS** mention before header._\n\n"
        "  **STATUS: READY**\n\n"
        "- [x] PRIMARY\n",
        encoding="utf-8",
    )
    assert mod._icml_status_line() == "READY"

    ready.unlink()
    assert "UNKNOWN" in mod._icml_status_line()


def test_judge_demos_source_uses_header_helper_not_re_search() -> None:
    finish = (ROOT / "scripts" / "finish_hackathon.py").read_text(encoding="utf-8")
    present = (ROOT / "scripts" / "present_hackathon.py").read_text(encoding="utf-8")
    for label, body in (("finish", finish), ("present", present)):
        assert "_icml_ready_status_header" in body, label
        assert r're.search(r"\*\*STATUS:' not in body, label
        assert "import re" not in body, label
