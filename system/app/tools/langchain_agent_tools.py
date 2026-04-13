from __future__ import annotations

from typing import Any

from app.agents.runtime_context import (
    DecisionAgentRuntimeContext,
    ExitAgentRuntimeContext,
    ParsingAgentRuntimeContext,
    WalletCommandRuntimeContext,
)


try:
    from langchain.tools import ToolRuntime, tool
except ModuleNotFoundError:  # pragma: no cover - local test fallback
    class ToolRuntime:  # type: ignore[no-redef]
        def __class_getitem__(cls, _item):
            return cls

    def tool(*_args, **_kwargs):
        def decorator(func):
            func.name = func.__name__
            return func

        return decorator


def build_parsing_agent_tools() -> list[Any]:
    @tool(parse_docstring=True)
    def load_okx_skill(
        skill_name: str,
        runtime: ToolRuntime[ParsingAgentRuntimeContext] | None = None,
    ) -> str:
        """Load an OKX OnchainOS skill prompt by name.

        Args:
            skill_name: Skill directory name, such as okx-dex-token or okx-dex-market.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_skill_provider(skill_name)

    @tool(parse_docstring=True)
    def load_okx_skill_reference(
        skill_name: str,
        relative_path: str,
        runtime: ToolRuntime[ParsingAgentRuntimeContext] | None = None,
    ) -> str:
        """Load a reference file mentioned by an OKX skill.

        Args:
            skill_name: Skill directory name.
            relative_path: Relative path inside the skill directory.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_reference_provider(skill_name, relative_path)

    @tool(parse_docstring=True)
    def run_onchainos_readonly(
        command: str,
        runtime: ToolRuntime[ParsingAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Execute a read-only onchainos CLI command and return parsed output.

        Args:
            command: Full onchainos command string. Only read-only commands are allowed.
        """

        if runtime is None or runtime.context is None:
            return {"ok": False, "error": "missing runtime context"}
        return runtime.context.readonly_command_provider(command)

    return [load_okx_skill, load_okx_skill_reference, run_onchainos_readonly]


def build_decision_agent_tools() -> list[Any]:
    @tool(parse_docstring=True)
    def load_okx_skill(
        skill_name: str,
        runtime: ToolRuntime[DecisionAgentRuntimeContext] | None = None,
    ) -> str:
        """Load an OKX OnchainOS skill prompt by name.

        Args:
            skill_name: Skill directory name, such as okx-agentic-wallet, okx-security, or okx-dex-swap.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_skill_provider(skill_name)

    @tool(parse_docstring=True)
    def load_okx_skill_reference(
        skill_name: str,
        relative_path: str,
        runtime: ToolRuntime[DecisionAgentRuntimeContext] | None = None,
    ) -> str:
        """Load a reference file inside a selected OKX skill.

        Args:
            skill_name: Skill directory name.
            relative_path: Relative path inside the skill directory.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_reference_provider(skill_name, relative_path)

    @tool(parse_docstring=True)
    def run_onchainos_readonly(
        command: str,
        runtime: ToolRuntime[DecisionAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Execute a read-only onchainos CLI command and return parsed output.

        Args:
            command: Full onchainos command string. Side-effecting commands are not allowed here.
        """

        if runtime is None or runtime.context is None:
            return {"ok": False, "error": "missing runtime context"}
        return runtime.context.readonly_command_provider(command)

    @tool(parse_docstring=True)
    def compute_ta_score(
        runtime: ToolRuntime[DecisionAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Compute or load TA score for the current trade candidate."""

        if runtime is None or runtime.context is None:
            return {}
        return runtime.context.ta_score_provider()

    @tool(parse_docstring=True)
    def build_trade_sizing_inputs(
        runtime: ToolRuntime[DecisionAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Build deterministic sizing inputs and capped amount for the current candidate."""

        if runtime is None or runtime.context is None:
            return {}
        return runtime.context.trade_sizing_inputs_provider()

    return [
        load_okx_skill,
        load_okx_skill_reference,
        run_onchainos_readonly,
        compute_ta_score,
        build_trade_sizing_inputs,
    ]


def build_wallet_command_agent_tools() -> list[Any]:
    @tool(parse_docstring=True)
    def load_okx_skill(
        skill_name: str,
        runtime: ToolRuntime[WalletCommandRuntimeContext] | None = None,
    ) -> str:
        """Load an OKX OnchainOS skill prompt by name.

        Args:
            skill_name: Skill directory name, typically okx-agentic-wallet or okx-dex-market.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_skill_provider(skill_name)

    @tool(parse_docstring=True)
    def load_okx_skill_reference(
        skill_name: str,
        relative_path: str,
        runtime: ToolRuntime[WalletCommandRuntimeContext] | None = None,
    ) -> str:
        """Load a reference file inside a selected OKX skill.

        Args:
            skill_name: Skill directory name.
            relative_path: Relative path inside the skill directory.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_reference_provider(skill_name, relative_path)

    @tool(parse_docstring=True)
    def run_onchainos_readonly(
        command: str,
        runtime: ToolRuntime[WalletCommandRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Execute a read-only onchainos CLI command and return parsed output.

        Args:
            command: Full onchainos command string. Side-effecting commands are not allowed here.
        """

        if runtime is None or runtime.context is None:
            return {"ok": False, "error": "missing runtime context"}
        return runtime.context.readonly_command_provider(command)

    return [load_okx_skill, load_okx_skill_reference, run_onchainos_readonly]


def build_exit_agent_tools() -> list[Any]:
    @tool(parse_docstring=True)
    def load_okx_skill(
        skill_name: str,
        runtime: ToolRuntime[ExitAgentRuntimeContext] | None = None,
    ) -> str:
        """Load an OKX OnchainOS skill prompt by name.

        Args:
            skill_name: Skill directory name, typically okx-dex-market or okx-agentic-wallet.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_skill_provider(skill_name)

    @tool(parse_docstring=True)
    def load_okx_skill_reference(
        skill_name: str,
        relative_path: str,
        runtime: ToolRuntime[ExitAgentRuntimeContext] | None = None,
    ) -> str:
        """Load a reference file inside a selected OKX skill.

        Args:
            skill_name: Skill directory name.
            relative_path: Relative path inside the skill directory.
        """

        if runtime is None or runtime.context is None:
            return ""
        return runtime.context.load_reference_provider(skill_name, relative_path)

    @tool(parse_docstring=True)
    def get_position_snapshot(
        runtime: ToolRuntime[ExitAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Load the current normalized position snapshot."""

        if runtime is None or runtime.context is None:
            return {}
        return runtime.context.position_snapshot_provider()

    @tool(parse_docstring=True)
    def get_token_market_snapshot(
        runtime: ToolRuntime[ExitAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Load the current normalized market snapshot for the active position."""

        if runtime is None or runtime.context is None:
            return {}
        return runtime.context.exit_market_snapshot_provider()

    @tool(parse_docstring=True)
    def compute_exit_ta_score(
        runtime: ToolRuntime[ExitAgentRuntimeContext] | None = None,
    ) -> dict[str, Any]:
        """Compute or load deterministic exit TA signals for the active position."""

        if runtime is None or runtime.context is None:
            return {}
        return runtime.context.exit_ta_score_provider()

    return [
        load_okx_skill,
        load_okx_skill_reference,
        get_position_snapshot,
        get_token_market_snapshot,
        compute_exit_ta_score,
    ]
