"""Tests for darwinian CLI flags."""

from sia.cli import build_parser
from sia.config import Config


def test_darwinian_flags_in_run_help():
    parser = build_parser(Config())
    args = parser.parse_args(
        [
            "run",
            "--task",
            "lawbench",
            "--darwinian",
            "--population_size",
            "8",
            "--elite_count",
            "2",
            "--mutation_rate",
            "0.3",
            "--seed",
            "42",
        ]
    )
    assert args.darwinian is True
    assert args.population_size == 8
    assert args.elite_count == 2
    assert args.mutation_rate == 0.3
    assert args.seed == 42


def test_darwinian_defaults():
    parser = build_parser(Config())
    args = parser.parse_args(["run", "--task", "gpqa"])
    assert args.darwinian is False
    assert args.population_size == 8
    assert args.elite_count == 2
