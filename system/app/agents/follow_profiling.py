from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import FollowProfilingAgentRuntimeContext
from app.config.settings import ensure_openai_runtime_env, get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.tools.langchain_agent_tools import build_follow_profiling_agent_tools


class FollowProfileOutput(BaseModel):
    extracted_call_count: int = Field(description="Number of historical trade calls extracted from the sampled messages.")
    evaluated_call_count: int = Field(description="Number of extracted calls that could be retrospectively evaluated with market kline data.")
    win_rate_1d_pct: float = Field(description="Percentage of evaluated calls that were positive within 1 day after the call.")
    median_return_1d_pct: float = Field(description="Median 1-day return percentage across evaluated calls.")
    average_return_1d_pct: float = Field(description="Average 1-day return percentage across evaluated calls.")
    suggested_conviction: Literal["low", "medium", "high"] = Field(
        description="Suggested default conviction for following this channel based on retrospective profiling."
    )
    profiling_summary: str = Field(description="Short user-facing summary of the channel's retrospective performance.")
    notable_patterns: list[str] = Field(default_factory=list, description="Notable patterns found during profiling.")


class FollowProfilingBackend(Protocol):
    def profile(
        self,
        *,
        user_id: str,
        source_id: str,
        channel_name: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


@dataclass
class FollowProfilingAgentConfig:
    tools: list = field(default_factory=build_follow_profiling_agent_tools)


class LangChainFollowProfilingBackend:
    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list | None = None,
        skill_registry: OKXSkillRegistry | None = None,
        readonly_runner: OnchainOSReadonlyRunner | None = None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_follow_profiling_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def profile(
        self,
        *,
        user_id: str,
        source_id: str,
        channel_name: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Profile this Telegram channel using the provided historical messages.\n"
                            "Extract actionable historical trade calls from the messages.\n"
                            "Then load okx-dex-market and use run_onchainos_readonly with onchainos market kline to evaluate "
                            "how those calls performed within 1 day after the call.\n"
                            "Return only a structured summary with retrospective metrics and a suggested conviction level.\n"
                            + json.dumps({"channel_name": channel_name, "messages": messages}, ensure_ascii=True)
                        ),
                    }
                ]
            },
            context=FollowProfilingAgentRuntimeContext(
                user_id=user_id,
                source_id=source_id,
                channel_name=channel_name,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
            ),
        )
        return self._extract_output(result).model_dump()

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        ensure_openai_runtime_env()
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainFollowProfilingBackend.") from exc

        system_prompt = (
            "You are a follow-profiling agent for a Telegram copy-trading bot. "
            "Use OKX skills with progressive disclosure. "
            "Load okx-dex-market when you need market kline data and use run_onchainos_readonly for read-only commands only. "
            "Your job is to retrospectively profile a channel, not to register it. "
            "Output only the structured profiling schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.follow_profiling_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=FollowProfilingAgentRuntimeContext,
            response_format=ToolStrategy(FollowProfileOutput),
        )
        return self._agent

    def _extract_output(self, result) -> FollowProfileOutput:
        if isinstance(result, FollowProfileOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, FollowProfileOutput):
                    return structured
                if isinstance(structured, dict):
                    return FollowProfileOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return FollowProfileOutput(**result["output"])
        if isinstance(result, str):
            return FollowProfileOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured follow profiling output from LangChain agent result.")


class FollowProfilingAgent:
    def __init__(self, config: FollowProfilingAgentConfig | None = None, backend: FollowProfilingBackend | None = None) -> None:
        self.config = config or FollowProfilingAgentConfig()
        self.backend = backend or LangChainFollowProfilingBackend(tools=self.config.tools)

    def profile(
        self,
        *,
        user_id: str,
        source_id: str,
        channel_name: str,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.backend.profile(
            user_id=user_id,
            source_id=source_id,
            channel_name=channel_name,
            messages=messages,
        )
