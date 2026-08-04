"""Population-based evolutionary loop for Darwinian AI Civilization."""

from __future__ import annotations

import asyncio
import json
import os
import random
import shutil
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from sia.agent_reference import ResolvedAgentReference, copy_reference_into
from sia.config import Config
from sia.evolution.civilization import CivilizationMemory
from sia.evolution.dna import AgentDNA
from sia.evolution.evolution_prompts import (
    darwinian_feedback_addon,
    darwinian_meta_addon,
)
from sia.evolution.dry_run import (
    agent_creation_complete,
    agent_run_complete,
    deterministic_fitness,
    parse_agent_coords,
    write_mock_results,
    write_mock_target_agent,
)
from sia.evolution.operators import breed_offspring, extract_fitness, select_elites
from sia.io_utils import write_text
from sia.layout import Names, RunLayout
from sia.logging_setup import get_logger
from sia.profiles import MetaAgentProfile
from sia.prompts import build_feedback_prompt, build_meta_prompt
from sia.providers import Provider
from sia.run_setup import RunSetup, TaskFiles, install_requirements
from sia.util import run_agent

logger = get_logger(__name__)


def _orch():
    """Lazy import to avoid circular dependency with orchestrator."""
    from sia import orchestrator

    return orchestrator


def _load_results(agent_dir: str) -> dict | None:
    path = os.path.join(agent_dir, Names.RESULTS_JSON)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_score(agent_dir: str, fitness: float, results: dict | None) -> None:
    score = {"fitness": fitness, "results": results or {}}
    with open(os.path.join(agent_dir, "score.json"), "w", encoding="utf-8") as f:
        json.dump(score, f, indent=2)


def _run_single_agent(
    agent_dir: str,
    run_setup: RunSetup,
    abs_dataset_dir: str,
    eval_task_dir: str,
    task_root: str,
    sandbox: str,
    env_config: Config,
    focus: str,
    eval_subset: int | None = None,
    resume: bool = False,
    dry_run: bool = False,
    task_name: str = "gpqa",
    agent_id: int | None = None,
    generation: int | None = None,
) -> tuple[bool, float, float]:
    """Run target agent + evaluation in an agent directory. Returns (success, fitness, duration)."""
    if resume and agent_run_complete(agent_dir):
        results = _load_results(agent_dir)
        fitness = extract_fitness(results)
        logger.info(f"  → Resume: using cached fitness={fitness:.4f}")
        return True, fitness, 0.0

    # Dry-run: DNA-hash fitness (varied Δfitness for offline H5). Skip real eval —
    # mock GPQA agents that always answer "A" collapse every agent to accuracy=1.0.
    if dry_run:
        dna_path = os.path.join(agent_dir, Names.AGENT_DNA)
        dna = AgentDNA.load(dna_path) if os.path.isfile(dna_path) else AgentDNA()
        parsed_id, parsed_gen = parse_agent_coords(agent_dir)
        aid = agent_id if agent_id is not None else parsed_id
        gen = generation if generation is not None else parsed_gen
        fitness = deterministic_fitness(aid, dna, gen)
        write_mock_results(agent_dir, fitness, task_name, eval_subset)
        logger.info(f"  → Dry-run: deterministic fitness={fitness:.4f} (agent={aid}, gen={gen})")
        return True, fitness, 0.0

    target_path = os.path.join(agent_dir, Names.TARGET_AGENT if focus == "harness" else Names.TRAIN_SCRIPT)
    stdout_log = os.path.join(agent_dir, Names.STDOUT_LOG if focus == "harness" else Names.TRAIN_STDOUT_LOG)

    gen_requirements = os.path.join(agent_dir, Names.REQUIREMENTS_TXT)
    if os.path.isfile(gen_requirements):
        install_requirements(run_setup.venv_dir, gen_requirements)

    start = time.time()
    orch = _orch()
    success, stdout, stderr, error_msg = orch._run_target_agent(
        venv_dir=run_setup.venv_dir,
        target_agent_path=target_path,
        abs_dataset_dir=abs_dataset_dir,
        gen_dir=agent_dir,
        stdout_log_file=stdout_log,
        sandbox=sandbox,
        env_config=env_config,
    )
    duration = time.time() - start

    orch.run_evaluation(
        agent_dir,
        eval_task_dir,
        run_setup.venv_dir,
        config=env_config,
        eval_subset=eval_subset,
        task_root=task_root,
    )

    results = _load_results(agent_dir)
    fitness = extract_fitness(results)
    _save_score(agent_dir, fitness, results)

    return success, fitness, duration


def _create_agent_with_meta(
    agent_dir: str,
    dna: AgentDNA,
    agent_id: int,
    population_size: int,
    task_files: TaskFiles,
    task_model: str,
    target_provider: Provider,
    meta_profile: MetaAgentProfile,
    env_config: Config,
    working_dir: str,
    reference_dir: str | None,
    focus: str,
    training_sandbox: str,
    resolved_ref: ResolvedAgentReference | None,
    dry_run: bool = False,
    resume: bool = False,
    task_name: str = "gpqa",
    baseline_seed: str | None = None,
) -> None:
    """Use meta-agent to create target_agent.py for one population member."""
    os.makedirs(agent_dir, exist_ok=True)
    dna.save(os.path.join(agent_dir, Names.AGENT_DNA))

    if resume and agent_creation_complete(agent_dir):
        logger.info(f"  → Resume: keeping existing target agent in {agent_dir}")
        return

    if baseline_seed:
        seed_path = os.path.abspath(baseline_seed)
        if os.path.isfile(seed_path):
            shutil.copy2(seed_path, os.path.join(agent_dir, Names.TARGET_AGENT))
            write_text(
                os.path.join(agent_dir, Names.META_PROMPT),
                f"# Baseline seed: copied from {seed_path}\n# DNA genotype saved; agent code from proven baseline.\n",
            )
            logger.info(f"  → Baseline seed: copied {seed_path} into {agent_dir}")
            return
        logger.warning(f"  ⚠ baseline_seed not found: {seed_path}; falling back to meta-agent")

    if dry_run:
        write_mock_target_agent(agent_dir, task_name)
        write_text(
            os.path.join(agent_dir, Names.META_PROMPT),
            f"# Dry-run: mock target agent for {task_name}\n",
        )
        logger.info(f"  → Dry-run: wrote mock target agent for agent in {agent_dir}")
        return

    if resolved_ref is not None:
        copy_reference_into(resolved_ref, agent_dir)

    base_prompt = build_meta_prompt(
        task_files,
        task_model,
        agent_dir,
        provider=target_provider,
        reference_dir=reference_dir if resolved_ref and resolved_ref.ref_dir else None,
        focus=focus,
        training_sandbox=training_sandbox,
    )
    full_prompt = base_prompt + darwinian_meta_addon(dna, agent_id, population_size)
    write_text(os.path.join(agent_dir, Names.META_PROMPT), full_prompt)

    asyncio.run(
        run_agent(
            model_name=meta_profile.model,
            max_turns=str(env_config.DEFAULT_MAX_TURNS),
            prompt=full_prompt,
            agent_working_directory=agent_dir,
            agent_impl=meta_profile.agent_impl,
            provider=meta_profile.provider,
        )
    )


def _create_offspring_with_feedback(
    agent_dir: str,
    offspring_dna: AgentDNA,
    agent_id: int,
    population_size: int,
    parent_dirs: list[str],
    parent_dnas: list[AgentDNA],
    parent_fitnesses: list[float],
    current_gen: int,
    max_gen: int,
    run_dir: str,
    task_files: TaskFiles,
    dataset_dir: str,
    meta_profile: MetaAgentProfile,
    env_config: Config,
    task_model: str,
    target_provider: Provider,
    focus: str,
    resolved_ref: ResolvedAgentReference | None,
    civilization: CivilizationMemory,
    dry_run: bool = False,
    resume: bool = False,
    task_name: str = "gpqa",
    enable_cabs: bool = False,
    cabs_store: str | None = None,
) -> None:
    """Breed offspring via feedback agent using best parent code + new DNA."""
    os.makedirs(agent_dir, exist_ok=True)
    offspring_dna.save(os.path.join(agent_dir, Names.AGENT_DNA))

    if resume and agent_creation_complete(agent_dir):
        logger.info(f"  → Resume: keeping existing offspring in {agent_dir}")
        return

    # Copy best parent's code as starting point
    best_idx = parent_fitnesses.index(max(parent_fitnesses))
    best_parent_dir = parent_dirs[best_idx]
    for fname in (Names.TARGET_AGENT, Names.TRAIN_SCRIPT, Names.REQUIREMENTS_TXT):
        src = os.path.join(best_parent_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(agent_dir, fname))

    if resolved_ref is not None:
        copy_reference_into(resolved_ref, agent_dir)

    if dry_run:
        write_mock_target_agent(agent_dir, task_name)
        write_text(os.path.join(agent_dir, Names.FEEDBACK_PROMPT), "# Dry-run: offspring from parent mock agents\n")
        logger.info(f"  → Dry-run: wrote mock offspring target agent in {agent_dir}")
        return

    agent_file = os.path.join(agent_dir, Names.TARGET_AGENT if focus == "harness" else Names.TRAIN_SCRIPT)
    if not os.path.isfile(agent_file):
        agent_file = os.path.join(best_parent_dir, Names.TARGET_AGENT)
    agent_py = Path(agent_file).read_text(encoding="utf-8") if os.path.isfile(agent_file) else ""
    task = Path(dataset_dir, "task.md").read_text(encoding="utf-8")

    # Build feedback context from best parent's last run
    parent_stdout = os.path.join(best_parent_dir, Names.STDOUT_LOG)
    stdout_text = Path(parent_stdout).read_text(encoding="utf-8") if os.path.isfile(parent_stdout) else ""
    execution_status, execution_section = _orch()._build_feedback_context(
        current_gen=current_gen,
        gen_dir=best_parent_dir,
        dataset_dir=dataset_dir,
        target_agent_success=True,
        target_agent_error_msg="",
        target_agent_stdout=stdout_text,
        target_agent_stderr="",
        stdout_log_file=parent_stdout,
        task_files=task_files,
        config=env_config,
    )

    previous_gens = ", ".join(str(g) for g in range(1, current_gen + 1))
    requirements_dir = agent_dir if (resolved_ref and resolved_ref.requirements) else None

    base_feedback = build_feedback_prompt(
        current_gen=current_gen,
        max_gen=max_gen,
        task_files=task_files,
        agent_py=agent_py,
        task=task,
        execution_status=execution_status,
        execution_section=execution_section,
        run_dir=run_dir,
        next_gen_dir=agent_dir,
        previous_gens=previous_gens,
        task_model=task_model,
        provider=target_provider,
        requirements_dir=requirements_dir,
        focus=focus,
    )

    civ_insights = civilization.summary_markdown()
    evolution_addon = darwinian_feedback_addon(
        offspring_dna,
        parent_dnas,
        parent_fitnesses,
        agent_id,
        population_size,
        civilization_insights=civ_insights,
    )

    cabs_addon = ""
    if enable_cabs:
        from sia.evolution.cabs_bridge import load_cabs_agenda

        cabs_addon = load_cabs_agenda(run_dir, cabs_store)

    from sia.evolution.evolution_prompts import cabs_feedback_addon

    full_prompt = cabs_feedback_addon(cabs_addon) + base_feedback + evolution_addon
    write_text(os.path.join(agent_dir, Names.FEEDBACK_PROMPT), full_prompt)

    asyncio.run(
        run_agent(
            model_name=meta_profile.model,
            max_turns=str(env_config.DEFAULT_MAX_TURNS),
            prompt=full_prompt,
            agent_working_directory=agent_dir,
            agent_impl=meta_profile.agent_impl,
            provider=meta_profile.provider,
        )
    )


def run_population_generation(
    gen: int,
    agent_ids: list[int],
    run_setup: RunSetup,
    layout: RunLayout,
    abs_dataset_dir: str,
    eval_task_dir: str,
    task_root: str,
    sandbox: str,
    env_config: Config,
    focus: str,
    eval_subset: int | None = None,
    resume: bool = False,
    dry_run: bool = False,
) -> list[dict]:
    """Run all agents in a generation and return scored agent records."""
    records: list[dict] = []

    for agent_id in agent_ids:
        agent_dir = layout.gen_agent_dir(gen, agent_id)
        logger.info("=" * 60)
        logger.info(f"Running gen_{gen}/agent_{agent_id}")
        logger.info("=" * 60)

        success, fitness, duration = _run_single_agent(
            agent_dir,
            run_setup,
            abs_dataset_dir,
            eval_task_dir,
            task_root,
            sandbox,
            env_config,
            focus,
            eval_subset=eval_subset,
            resume=resume,
            dry_run=dry_run,
            agent_id=agent_id,
            generation=gen,
        )

        dna_path = os.path.join(agent_dir, Names.AGENT_DNA)
        dna = AgentDNA.load(dna_path) if os.path.isfile(dna_path) else AgentDNA()

        record = {
            "agent_id": agent_id,
            "agent_dir": agent_dir,
            "dna": asdict(dna),
            "fitness": fitness,
            "success": success,
            "duration": duration,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        records.append(record)
        logger.info(f"  agent_{agent_id} fitness={fitness:.4f} success={success}")

    return records


def run_darwinian_loop(
    max_gen: int,
    run_setup: RunSetup,
    task_files: TaskFiles,
    abs_dataset_dir: str,
    dataset_dir: str,
    meta_profile: MetaAgentProfile,
    sandbox: str,
    env_config: Config,
    task_model: str,
    target_provider: Provider,
    focus: str,
    training_sandbox: str,
    resolved_ref: ResolvedAgentReference | None,
    reference_dir: str | None,
    population_size: int,
    elite_count: int,
    mutation_rate: float,
    seed: int | None = None,
    eval_subset: int | None = None,
    resume: bool = False,
    dry_run: bool = False,
    task_name: str = "gpqa",
    task_root: str | None = None,
    baseline_seed: str | None = None,
    enable_cabs: bool = False,
    cabs_store: str | None = None,
    cabs_inline: bool = False,
) -> None:
    """Main Darwinian evolution loop."""
    layout = RunLayout(run_setup.run_directory)
    rng = random.Random(seed)

    task_root = task_root or dataset_dir
    if cabs_inline:
        enable_cabs = True

    civilization = CivilizationMemory(
        path=layout.civilization_json,
        population_size=population_size,
        elite_count=elite_count,
        mutation_rate=mutation_rate,
    )

    logger.info("=" * 80)
    logger.info("Darwinian AI Civilization — Population-Based Self-Improvement")
    logger.info(f"  Population size: {population_size}")
    logger.info(f"  Elite count: {elite_count}")
    logger.info(f"  Mutation rate: {mutation_rate}")
    logger.info(f"  Generations: {max_gen}")
    if dry_run:
        logger.info("  Mode: DRY-RUN (no LLM API calls for meta/feedback)")
    if eval_subset:
        logger.info(f"  Eval subset: first {eval_subset} samples")
    if resume:
        logger.info("  Resume: enabled (skip completed agents)")
    if baseline_seed:
        logger.info(f"  Baseline seed: gen 1 agents copied from {baseline_seed}")
    if enable_cabs:
        logger.info(f"  CABS integration: enabled (belief_store in run dir)")
    if cabs_inline:
        logger.info("  CABS inline: analyze after each gen eval (Condition D / epistemic_full)")
    logger.info("=" * 80)

    # Generation 1: create initial population with diverse DNA
    logger.info("Creating initial population (generation 1)...")
    for agent_id in range(population_size):
        agent_dir = layout.gen_agent_dir(1, agent_id)
        dna = AgentDNA.random(rng=rng)
        logger.info(f"  Creating agent_{agent_id} with DNA: {asdict(dna)}")

        _create_agent_with_meta(
            agent_dir=agent_dir,
            dna=dna,
            agent_id=agent_id,
            population_size=population_size,
            task_files=task_files,
            task_model=task_model,
            target_provider=target_provider,
            meta_profile=meta_profile,
            env_config=env_config,
            working_dir=agent_dir,
            reference_dir=reference_dir,
            focus=focus,
            training_sandbox=training_sandbox,
            resolved_ref=resolved_ref,
            dry_run=dry_run,
            resume=resume,
            task_name=task_name,
            baseline_seed=baseline_seed,
        )

    # Evolution loop across generations
    for current_gen in range(1, max_gen + 1):
        logger.info("=" * 80)
        logger.info(f"Generation {current_gen}/{max_gen} — Benchmark Competition")
        logger.info("=" * 80)

        agent_ids = list(range(population_size))
        records = run_population_generation(
            gen=current_gen,
            agent_ids=agent_ids,
            run_setup=run_setup,
            layout=layout,
            abs_dataset_dir=abs_dataset_dir,
            eval_task_dir=dataset_dir,
            task_root=task_root,
            sandbox=sandbox,
            env_config=env_config,
            focus=focus,
            eval_subset=eval_subset,
            resume=resume,
            dry_run=dry_run,
        )

        scored = [(r["agent_id"], r["fitness"]) for r in records]
        elite_ids = select_elites(scored, elite_count)
        civilization.record_generation(current_gen, records, elite_ids)
        civilization.save()

        logger.info(f"Generation {current_gen} results:")
        for r in sorted(records, key=lambda x: x["fitness"], reverse=True):
            marker = " ★ ELITE" if r["agent_id"] in elite_ids else ""
            logger.info(f"  agent_{r['agent_id']}: fitness={r['fitness']:.4f}{marker}")

        # Condition D: refresh belief_store before breeding so bias/agenda see this gen
        if cabs_inline:
            from sia.evolution.cabs_inline import run_cabs_inline

            try:
                inline_summary = run_cabs_inline(
                    run_setup.run_directory,
                    current_gen,
                    cabs_store=cabs_store,
                    task_hint=task_name,
                    enable_committee=False,
                )
                logger.info(
                    "  CABS inline gen %s: beliefs+%s contradictions+%s RQs+%s epistemic_value=%.3f",
                    current_gen,
                    inline_summary.get("beliefs_added"),
                    inline_summary.get("contradictions_added"),
                    inline_summary.get("research_questions_added"),
                    float(inline_summary.get("epistemic_value") or 0),
                )
            except Exception as exc:  # noqa: BLE001 — never abort evolution on CABS analyze failure
                logger.warning("  CABS inline analyze failed (continuing Darwinian loop): %s", exc)

        # Log to context.md
        run_setup.context_mgr.add_generation(
            gen_num=current_gen,
            gen_data={
                "success": any(r["success"] for r in records),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "duration": sum(r["duration"] for r in records),
                "agent_path": os.path.join(layout.gen_agent_dir(current_gen, elite_ids[0]), Names.TARGET_AGENT),
                "gen_dir": layout.gen_dir(current_gen),
                "improvement_path": None,
                "execution_type": f"Darwinian population ({population_size} agents)",
                "best_fitness": max(r["fitness"] for r in records),
                "mean_fitness": sum(r["fitness"] for r in records) / len(records),
                "elite_ids": elite_ids,
                "skip_llm_summary": dry_run,
            },
        )

        if current_gen >= max_gen:
            logger.info("Final generation complete. Skipping breeding.")
            break

        # Breed next generation
        next_gen = current_gen + 1
        logger.info("=" * 80)
        logger.info(f"Breeding generation {next_gen} (crossover + mutation)...")
        logger.info("=" * 80)

        elite_records = [r for r in records if r["agent_id"] in elite_ids]
        elite_dnas = [AgentDNA.from_dict(r["dna"]) for r in elite_records]
        elite_dirs = [r["agent_dir"] for r in elite_records]
        elite_fitnesses = [r["fitness"] for r in elite_records]

        mutation_bias = None
        cabs_technique_seeds: list[str] = []
        if enable_cabs:
            from sia.evolution.cabs_bridge import load_approved_technique_names, load_mutation_bias

            mutation_bias = load_mutation_bias(run_setup.run_directory, cabs_store)
            cabs_technique_seeds = load_approved_technique_names(run_setup.run_directory, cabs_store)
            if mutation_bias:
                logger.info(f"  CABS mutation bias: {mutation_bias}")
            if cabs_technique_seeds:
                logger.info(f"  CABS technique seeds: {cabs_technique_seeds}")

        # Delay bias-aware crossover until breeding from gen≥2 (→ gen≥3).
        # First breeding (gen1→gen2) keeps fair XO + mutation bias only so
        # preferred alleles are not over-collapsed before H5 / gens-to-threshold
        # signal can accumulate; later gens apply soft bias-aware XO.
        apply_crossover_bias = current_gen >= 2

        for agent_id in range(population_size):
            # Tournament selection: pick two elites (with replacement if only one)
            parent_a_idx = rng.randint(0, len(elite_dnas) - 1)
            parent_b_idx = rng.randint(0, len(elite_dnas) - 1)
            offspring_dna = breed_offspring(
                elite_dnas[parent_a_idx],
                elite_dnas[parent_b_idx],
                mutation_rate,
                rng=rng,
                bias=mutation_bias,
                technique_seeds=cabs_technique_seeds,
                apply_crossover_bias=apply_crossover_bias,
            )

            agent_dir = layout.gen_agent_dir(next_gen, agent_id)
            logger.info(f"  Breeding agent_{agent_id}: parents=({elite_ids[parent_a_idx]}, {elite_ids[parent_b_idx]})")

            _create_offspring_with_feedback(
                agent_dir=agent_dir,
                offspring_dna=offspring_dna,
                agent_id=agent_id,
                population_size=population_size,
                parent_dirs=[elite_dirs[parent_a_idx], elite_dirs[parent_b_idx]],
                parent_dnas=[elite_dnas[parent_a_idx], elite_dnas[parent_b_idx]],
                parent_fitnesses=[elite_fitnesses[parent_a_idx], elite_fitnesses[parent_b_idx]],
                current_gen=current_gen,
                max_gen=max_gen,
                run_dir=run_setup.run_directory,
                task_files=task_files,
                dataset_dir=dataset_dir,
                meta_profile=meta_profile,
                env_config=env_config,
                task_model=task_model,
                target_provider=target_provider,
                focus=focus,
                resolved_ref=resolved_ref,
                civilization=civilization,
                dry_run=dry_run,
                resume=resume,
                task_name=task_name,
                enable_cabs=enable_cabs,
                cabs_store=cabs_store,
            )

    # Append civilization summary to context.md
    civ_summary_path = os.path.join(run_setup.run_directory, "civilization_summary.md")
    write_text(civ_summary_path, civilization.summary_markdown())
    logger.info(f"Civilization memory saved to: {layout.civilization_json}")
    logger.info(f"Civilization summary saved to: {civ_summary_path}")
