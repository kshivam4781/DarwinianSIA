"""CLI tests for Phase 1 flags."""

from sia.cli import build_parser
from sia.config import Config


def test_phase1_flags_parse():
    parser = build_parser(Config())
    args = parser.parse_args(
        [
            "run",
            "--task",
            "gpqa",
            "--darwinian",
            "--dry-run",
            "--eval_subset",
            "20",
            "--resume",
            "--population_size",
            "2",
            "--max_gen",
            "2",
            "--run_id",
            "100",
        ]
    )
    assert args.dry_run is True
    assert args.eval_subset == 20
    assert args.resume is True
