"""SIA orchestrator with CABS hooks injected into the improvement loop."""

from __future__ import annotations

import os
from pathlib import Path

from sia import __version__ as sia_version
from sia import cli
from sia.agent_reference import ResolvedAgentReference, copy_reference_into, resolve_agent_reference
from sia.config import Config
from sia.io_utils import write_text
from sia.layout import BUNDLED_TASKS, Names, RunLayout, TaskLayout, resolve_task_dir
from sia.logging_setup import configure_logging, get_logger
from sia.orchestrator import (
    _build_feedback_context,
    _print_welcome,
    _run_target_agent,
    _run_web,
    run_evaluation,
)
from sia.profiles import load_meta_agent_profile, load_target_agent_profile
from sia.prompts import build_feedback_prompt, build_meta_prompt
from sia.run_setup import RunSetup, TaskFiles, load_task_files, setup_run_directory
from sia.util import run_agent

from cabs.belief_engine import BeliefEngine
from cabs.prompt_injection import inject_into_prompt
from cabs.sia_prompt_addons import feedback_beliefs_instruction, meta_task_hints

__all__ = [
    "BUNDLED_TASKS",
    "main",
    "run_generation",
]

logger = get_logger(__name__)

# Parsed before sia.cli (which rejects unknown flags)
_CABS_TAVILY = False
_CABS_TAVILY_MAX = 10
_CABS_COMMITTEE = False
_CABS_COMMITTEE_MAX = 5
_CABS_COMMITTEE_OFFLINE = False
_CABS_TASK_HINT = ""


def _parse_cabs_argv() -> None:
    """Strip sia-cabs-only flags from sys.argv before SIA CLI parsing."""
    import sys

    global _CABS_TAVILY, _CABS_TAVILY_MAX, _CABS_COMMITTEE, _CABS_COMMITTEE_MAX, _CABS_COMMITTEE_OFFLINE
    argv = sys.argv[1:]
    cleaned: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--tavily":
            _CABS_TAVILY = True
            i += 1
            continue
        if arg == "--tavily-max" and i + 1 < len(argv):
            _CABS_TAVILY_MAX = int(argv[i + 1])
            i += 2
            continue
        if arg == "--no-tavily":
            _CABS_TAVILY = False
            i += 1
            continue
        if arg == "--committee":
            _CABS_COMMITTEE = True
            i += 1
            continue
        if arg == "--committee-max" and i + 1 < len(argv):
            _CABS_COMMITTEE_MAX = int(argv[i + 1])
            i += 2
            continue
        if arg == "--committee-offline":
            _CABS_COMMITTEE_OFFLINE = True
            i += 1
            continue
        if arg == "--no-committee":
            _CABS_COMMITTEE = False
            i += 1
            continue
        cleaned.append(arg)
        i += 1
    sys.argv = [sys.argv[0]] + cleaned


def _tavily_enabled() -> bool:
    import os

    if _CABS_TAVILY:
        return True
    return os.getenv("CABS_ENABLE_TAVILY", "").strip().lower() in ("1", "true", "yes")


def _committee_enabled() -> bool:
    import os

    if _CABS_COMMITTEE:
        return True
    return os.getenv("CABS_ENABLE_COMMITTEE", "").strip().lower() in ("1", "true", "yes")


def _belief_store_for_run(run_dir: str) -> str:
    return str(Path(run_dir) / "belief_store")


def _run_feedback_agent_with_cabs(
    current_gen: int,
    max_gen: int,
    run_dir: str,
    next_gen_dir: str,
    task_files: TaskFiles,
    execution_status: str,
    execution_section: str,
    meta_profile,
    env_config: Config,
    dataset_dir: str,
    task_model: str,
    target_provider,
    focus: str = "harness",
    resolved_ref: ResolvedAgentReference | None = None,
) -> None:
    """Run feedback agent with CABS research agenda injected into its prompt."""
    gen_dir = os.path.join(run_dir, f"gen_{current_gen}")
    if focus == "weights":
        agent_file = os.path.join(gen_dir, Names.TRAIN_SCRIPT)
    else:
        agent_file = os.path.join(gen_dir, Names.TARGET_AGENT)

    agent_py = Path(agent_file).read_text(encoding="utf-8")
    task = Path(dataset_dir, "task.md").read_text(encoding="utf-8")

    previous_gens_list = list(range(1, current_gen)) if current_gen > 1 else []
    previous_gens_text = ", ".join(map(str, previous_gens_list)) if previous_gens_list else "None"
    requirements_dir = next_gen_dir if (resolved_ref and resolved_ref.requirements) else None

    feedback_agent_prompt = build_feedback_prompt(
        current_gen=current_gen,
        max_gen=max_gen,
        task_files=task_files,
        agent_py=agent_py,
        task=task,
        execution_status=execution_status,
        execution_section=execution_section,
        run_dir=run_dir,
        next_gen_dir=next_gen_dir,
        previous_gens=previous_gens_text,
        task_model=task_model,
        provider=target_provider,
        requirements_dir=requirements_dir,
        focus=focus,
    )
    feedback_agent_prompt = inject_into_prompt(feedback_agent_prompt, _belief_store_for_run(run_dir))
    feedback_agent_prompt = (
        f"{feedback_beliefs_instruction(current_gen, next_gen_dir)}\n{feedback_agent_prompt}"
    )

    os.makedirs(next_gen_dir, exist_ok=True)
    if resolved_ref is not None:
        copy_reference_into(resolved_ref, next_gen_dir)

    feedback_prompt_path = os.path.join(next_gen_dir, Names.FEEDBACK_PROMPT)
    write_text(feedback_prompt_path, feedback_agent_prompt)
    logger.info(f"  ✓ Saved CABS-augmented feedback prompt to: {feedback_prompt_path}")

    import asyncio

    asyncio.run(
        run_agent(
            model_name=meta_profile.model,
            max_turns=str(env_config.DEFAULT_MAX_TURNS),
            prompt=feedback_agent_prompt,
            agent_working_directory=next_gen_dir,
            agent_impl=meta_profile.agent_impl,
            provider=meta_profile.provider,
        )
    )

    ingest = BeliefEngine.for_run(
        run_dir,
        enable_tavily=_tavily_enabled(),
        tavily_max_calls=_CABS_TAVILY_MAX,
        enable_committee=_committee_enabled(),
        committee_max_reviews=_CABS_COMMITTEE_MAX,
        committee_use_llm=not _CABS_COMMITTEE_OFFLINE,
        task_hint=_CABS_TASK_HINT,
    ).ingest_feedback_beliefs(run_dir, next_gen_dir, source_generation=current_gen)
    if ingest.beliefs_added:
        logger.info(
            "  ✓ CABS feedback ingest: +%s beliefs, +%s contradictions, +%s research questions",
            ingest.beliefs_added,
            ingest.contradictions_added,
            ingest.research_questions_added,
        )

    next_gen = current_gen + 1
    logger.info(f"CABS feedback agent completed. Created improved agent for generation {next_gen}")


def run_generation(
    current_gen: int,
    max_gen: int,
    run_setup: RunSetup,
    task_files: TaskFiles,
    abs_dataset_dir: str,
    dataset_dir: str,
    meta_profile,
    sandbox: str,
    env_config: Config,
    task_model: str,
    target_provider,
    focus: str = "harness",
    training_sandbox: str = "modal",
    resolved_ref: ResolvedAgentReference | None = None,
) -> None:
    """Execute one generation, then run the CABS belief pipeline before feedback."""
    import time
    from datetime import datetime

    run_dir = run_setup.run_directory
    layout = RunLayout(run_dir)
    gen_dir = layout.gen_dir(current_gen)
    target_agent_path = os.path.join(gen_dir, "train.py") if focus == "weights" else layout.target_agent(current_gen)
    stdout_log_file = layout.stdout_log(current_gen, focus=focus)

    logger.info(f"Running target agent: {target_agent_path}")
    logger.info(f"  → Stdout log: {stdout_log_file}")
    logger.info(f"  → Focus mode: {focus}")
    logger.info("=" * 60)

    gen_requirements = os.path.join(gen_dir, Names.REQUIREMENTS_TXT)
    if os.path.isfile(gen_requirements):
        from sia.run_setup import install_requirements

        install_requirements(run_setup.venv_dir, gen_requirements)

    generation_start_time = time.time()
    target_agent_success, target_agent_stdout, target_agent_stderr, target_agent_error_msg = _run_target_agent(
        venv_dir=run_setup.venv_dir,
        target_agent_path=target_agent_path,
        abs_dataset_dir=abs_dataset_dir,
        gen_dir=gen_dir,
        stdout_log_file=stdout_log_file,
        sandbox=sandbox,
        env_config=env_config,
    )
    generation_duration = time.time() - generation_start_time

    logger.info("=" * 60)
    logger.info("Running evaluation (if available)...")
    run_evaluation(gen_dir, dataset_dir, run_setup.venv_dir, config=env_config)
    logger.info("=" * 60)

    improvement_md_path = layout.improvement_md(current_gen)
    run_setup.context_mgr.add_generation(
        gen_num=current_gen,
        gen_data={
            "success": target_agent_success,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "duration": generation_duration,
            "agent_path": target_agent_path,
            "gen_dir": gen_dir,
            "improvement_path": improvement_md_path if os.path.exists(improvement_md_path) else None,
            "execution_type": "Multi-trajectory"
            if os.path.isdir(layout.agent_execution_dir(current_gen))
            else "Single",
        },
    )

    logger.info("Running CABS belief pipeline...")
    cabs_result = BeliefEngine.for_run(
        run_dir,
        enable_tavily=_tavily_enabled(),
        tavily_max_calls=_CABS_TAVILY_MAX,
        enable_committee=_committee_enabled(),
        committee_max_reviews=_CABS_COMMITTEE_MAX,
        committee_use_llm=not _CABS_COMMITTEE_OFFLINE,
        task_hint=_CABS_TASK_HINT,
    ).process_generation(run_dir, current_gen)
    logger.info(
        "  ✓ CABS: +%s beliefs, +%s contradictions, +%s research questions "
        "(knowledge_gain=%.3f)",
        cabs_result.beliefs_added,
        cabs_result.contradictions_added,
        cabs_result.research_questions_added,
        cabs_result.knowledge_gain_score,
    )
    if cabs_result.tavily.get("enabled") and cabs_result.tavily.get("grounded"):
        logger.info(
            "  ✓ Tavily: %s call(s), %s question(s) grounded",
            cabs_result.tavily.get("calls_this_step", 0),
            len(cabs_result.tavily.get("grounded", [])),
        )
    if cabs_result.committee.get("enabled") and cabs_result.committee.get("reviews_run"):
        logger.info(
            "  ✓ Committee: %s review(s), %s approved, %s rejected",
            cabs_result.committee.get("reviews_run", 0),
            len(cabs_result.committee.get("approved", [])),
            len(cabs_result.committee.get("rejected", [])),
        )

    if current_gen < max_gen:
        logger.info(f"Running CABS-augmented feedback agent for generation {current_gen}")
        logger.info("Loading agent execution log...")

        execution_status, execution_section = _build_feedback_context(
            current_gen=current_gen,
            gen_dir=gen_dir,
            dataset_dir=dataset_dir,
            target_agent_success=target_agent_success,
            target_agent_error_msg=target_agent_error_msg,
            target_agent_stdout=target_agent_stdout,
            target_agent_stderr=target_agent_stderr,
            stdout_log_file=stdout_log_file,
            task_files=task_files,
            config=env_config,
        )

        next_gen = current_gen + 1
        next_gen_directory = layout.gen_dir(next_gen)

        _run_feedback_agent_with_cabs(
            current_gen=current_gen,
            max_gen=max_gen,
            run_dir=run_dir,
            next_gen_dir=next_gen_directory,
            task_files=task_files,
            execution_status=execution_status,
            execution_section=execution_section,
            meta_profile=meta_profile,
            env_config=env_config,
            dataset_dir=dataset_dir,
            task_model=task_model,
            target_provider=target_provider,
            focus=focus,
            resolved_ref=resolved_ref,
        )
    else:
        logger.info(f"Generation {current_gen} is the final generation. Skipping feedback agent.")


def main() -> None:
    import asyncio

    from sia_cabs.env_loader import load_project_dotenv

    _parse_cabs_argv()
    load_project_dotenv()
    configure_logging()
    _print_welcome()
    print(f"    • CABS    : SIA-CABS v{sia_cabs_version()} (belief-driven self-improvement)\n")

    env_config = Config.from_env()
    args = cli.parse_args(env_config)
    global _CABS_TASK_HINT
    _CABS_TASK_HINT = getattr(args, "task", "") or ""

    if args.command == "web":
        _run_web(args)
        return

    configure_logging(args.log_level)

    if not args.no_web:
        from sia.web import serve_in_background

        serve_in_background(host=args.web_host, port=args.web_port, runs_dir=Names.RUNS_ROOT)

    max_gen = args.max_gen
    task_dir, shared_dir = resolve_task_dir(args.task, args.task_dir)
    run_id = args.run_id

    meta_profile = load_meta_agent_profile(args.meta_agent_profile)
    target_profile = load_target_agent_profile(args.target_agent_profile)
    meta_model = meta_profile.model
    task_model = target_profile.model
    agent_impl = meta_profile.agent_impl
    target_provider = target_profile.provider

    task_layout = TaskLayout(task_dir, shared_dir)
    resolved_ref = resolve_agent_reference(target_profile.agent_reference, task_layout)

    logger.info("Configuration:")
    logger.info(f"  - Maximum generations: {max_gen}")
    logger.info(f"  - Task directory: {task_dir}")
    logger.info(f"  - Run ID: {run_id}")
    logger.info(f"  - SIA version: {sia_version}")
    logger.info(f"  - CABS enabled: True")
    logger.info(f"  - Tavily grounding: {_tavily_enabled()} (max calls: {_CABS_TAVILY_MAX})")
    logger.info(
        f"  - Committee gating: {_committee_enabled()} "
        f"(max reviews: {_CABS_COMMITTEE_MAX}, offline: {_CABS_COMMITTEE_OFFLINE})"
    )

    for label, prov in (("meta", meta_profile.provider), ("target", target_provider)):
        if not os.getenv(prov.api_key_env):
            logger.warning(f"  ⚠ {prov.api_key_env} is not set; the {label} agent may fail to authenticate.")

    task_files = load_task_files(task_dir, shared_dir, resolved_ref)
    run_setup = setup_run_directory(
        run_id,
        task_dir,
        meta_model,
        task_model,
        agent_impl,
        max_gen,
        focus=args.focus,
        config=env_config,
        meta_profile=meta_profile,
        target_profile=target_profile,
    )

    copy_reference_into(resolved_ref, run_setup.meta_agent_working_directory)
    reference_dir = run_setup.meta_agent_working_directory if resolved_ref.ref_dir is not None else None

    meta_agent_prompt = build_meta_prompt(
        task_files,
        task_model,
        run_setup.meta_agent_working_directory,
        provider=target_provider,
        reference_dir=reference_dir,
        focus=args.focus,
        training_sandbox=args.training_sandbox,
    )
    meta_agent_prompt = inject_into_prompt(meta_agent_prompt, _belief_store_for_run(run_setup.run_directory))
    task_hint = meta_task_hints(args.task)
    if task_hint:
        meta_agent_prompt = f"{task_hint}\n{meta_agent_prompt}"

    meta_agent_prompt_path = os.path.join(run_setup.meta_agent_working_directory, Names.META_PROMPT)
    write_text(meta_agent_prompt_path, meta_agent_prompt)
    logger.info(f"  ✓ Saved CABS-augmented meta-agent prompt to: {meta_agent_prompt_path}")

    asyncio.run(
        run_agent(
            model_name=meta_model,
            max_turns=str(env_config.DEFAULT_MAX_TURNS),
            prompt=meta_agent_prompt,
            agent_working_directory=run_setup.meta_agent_working_directory,
            agent_impl=agent_impl,
            provider=meta_profile.provider,
        )
    )

    dataset_directory = task_layout.dataset_dir
    abs_dataset_directory = task_layout.abs_dataset_dir
    logger.info(f"Dataset directory: {abs_dataset_directory}")

    for current_gen in range(1, max_gen + 1):
        logger.info("=" * 80)
        logger.info(f"Starting Generation {current_gen} of {max_gen}")
        logger.info("=" * 80)

        run_generation(
            current_gen=current_gen,
            max_gen=max_gen,
            run_setup=run_setup,
            task_files=task_files,
            abs_dataset_dir=abs_dataset_directory,
            dataset_dir=dataset_directory,
            meta_profile=meta_profile,
            sandbox=args.sandbox,
            env_config=env_config,
            task_model=task_model,
            target_provider=target_provider,
            focus=args.focus,
            training_sandbox=args.training_sandbox,
            resolved_ref=resolved_ref,
        )

        if args.focus == "weights" and current_gen < max_gen:
            next_gen = current_gen + 1
            next_gen_dir = RunLayout(run_setup.run_directory).gen_dir(next_gen)
            if os.path.exists(os.path.join(next_gen_dir, "COMPLETED")):
                logger.info("Feedback agent signaled completion via COMPLETED file. Exiting evolution loop early.")
                break

    logger.info("Finalizing context.md with summary statistics...")
    run_setup.context_mgr.finalize()

    logger.info("=" * 80)
    logger.info(f"SIA-CABS completed all {max_gen} generations successfully!")
    logger.info(f"Results saved in: {run_setup.run_directory}")
    logger.info(f"Belief store: {_belief_store_for_run(run_setup.run_directory)}")
    logger.info(f"Context summary: {os.path.join(run_setup.run_directory, Names.CONTEXT_MD)}")
    logger.info("=" * 80)


def sia_cabs_version() -> str:
    from sia_cabs import __version__

    return __version__
