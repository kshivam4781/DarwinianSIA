"""Tests for the agent-impl registry and the PydanticAI agent impl."""

import asyncio

import pytest

from sia.agent_impls import available_agent_impls, get_agent_impl


def test_registry_lists_builtin_agent_impls():
    assert set(available_agent_impls()) >= {"claude", "openhands", "pydantic-ai"}


def test_get_agent_impl_returns_callable():
    assert callable(get_agent_impl("claude"))
    assert callable(get_agent_impl("pydantic-ai"))


def test_get_agent_impl_unknown_raises():
    with pytest.raises(ValueError):
        get_agent_impl("does-not-exist")


def test_util_reexports_registry_run_agent():
    from sia.agent_impls import run_agent as impl_run_agent
    from sia.util import run_agent as util_run_agent

    assert util_run_agent is impl_run_agent


def test_pydantic_ai_impl_runs_with_test_model(tmp_path):
    pytest.importorskip("pydantic_ai")
    from pydantic_ai.models.test import TestModel

    from sia.agent_impls.pydantic_ai import run_agent_pydantic_ai

    # TestModel drives the agent without network; it exercises each registered tool,
    # so write_file should create a file in the working directory.
    asyncio.run(
        run_agent_pydantic_ai(
            TestModel(),
            "5",
            "Create a file with some content using the write_file tool.",
            str(tmp_path),
        )
    )
    assert any(tmp_path.iterdir())


def test_pydantic_ai_model_passthrough():
    from sia.agent_impls.pydantic_ai import _resolve_model

    # Model specs are passed through unchanged to PydanticAI's native parsing.
    assert _resolve_model("openai:gpt-4o") == "openai:gpt-4o"
    assert _resolve_model("anthropic:claude-sonnet-4-5") == "anthropic:claude-sonnet-4-5"
    # No provider -> still a plain passthrough.
    assert _resolve_model("openai:gpt-4o", None) == "openai:gpt-4o"


def test_openhands_model_gets_openai_prefix_for_compatible_provider():
    """An OpenAI-compatible provider (base_url) gets an explicit litellm 'openai/' prefix."""
    from sia.agent_impls.openhands import _resolve_model
    from sia.providers import load_provider

    nebius = load_provider("nebius")  # client_kind=openai, has base_url
    assert _resolve_model("moonshotai/Kimi-K2.6", nebius) == "openai/moonshotai/Kimi-K2.6"
    # Already prefixed -> not double-prefixed.
    assert _resolve_model("openai/gpt-4o", nebius) == "openai/gpt-4o"


def test_openhands_model_passthrough_without_compatible_provider():
    """Native (anthropic) and provider-less specs pass through unchanged."""
    from sia.agent_impls.openhands import _resolve_model
    from sia.providers import load_provider

    assert _resolve_model("claude-sonnet-4-5", None) == "claude-sonnet-4-5"
    anthropic = load_provider("anthropic")  # client_kind=anthropic, no base_url
    assert _resolve_model("claude-sonnet-4-5", anthropic) == "claude-sonnet-4-5"


def test_run_agent_threads_provider_to_agent_impl():
    """run_agent forwards the optional provider kwarg to the dispatched agent impl."""
    import asyncio

    from sia.agent_impls import base
    from sia.providers import load_provider

    captured = {}

    async def fake_runner(model, max_turns, prompt, cwd, provider=None):
        captured["provider"] = provider

    base.register("capture-test", fake_runner)
    nebius = load_provider("nebius")
    asyncio.run(base.run_agent("m", "5", "p", "/tmp", agent_impl="capture-test", provider=nebius))
    assert captured["provider"] is nebius
