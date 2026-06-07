"""Darwinian AI Civilization: population-based self-improvement for SIA."""

from sia.evolution.dna import AgentDNA
from sia.evolution.operators import crossover, mutate, select_elites, tournament_rank
from sia.evolution.population import run_darwinian_loop

__all__ = [
    "AgentDNA",
    "crossover",
    "mutate",
    "run_darwinian_loop",
    "select_elites",
    "tournament_rank",
]
