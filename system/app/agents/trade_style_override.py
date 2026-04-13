from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.schemas.strategy import StrategyProfilePatch


class TradeStyleOverrideOutput(BaseModel):
    patch: StrategyProfilePatch = Field(description="Structured profile updates extracted from the user's free-form message.")
    change_summary: str = Field(description="Short explanation of what changes were understood from the user message.")


class TradeStyleOverrideBackend(Protocol):
    def parse_override(self, *, raw_text: str, current_profile: dict) -> TradeStyleOverrideOutput: ...


@dataclass
class TradeStyleOverrideAgentConfig:
    model: str | None = None


class LangChainTradeStyleOverrideBackend:
    def __init__(self, *, model: str | None = None) -> None:
        self._agent = None
        self.model = model

    def parse_override(self, *, raw_text: str, current_profile: dict) -> TradeStyleOverrideOutput:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Parse this free-form trading-style update request into a structured patch.\n"
                            "Only map fields that are explicitly requested.\n"
                            "Do not apply the patch or validate business rules.\n"
                            "If the request is unclear, return an empty patch.\n"
                            + json.dumps(
                                {
                                    "current_profile": current_profile,
                                    "user_request": raw_text,
                                },
                                ensure_ascii=True,
                            )
                        ),
                    }
                ]
            }
        )
        return self._extract_output(result)

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainTradeStyleOverrideBackend.") from exc

        system_prompt = (
            "You are a bounded settings parser for a trading-style setup flow. "
            "Your only job is to convert the user's free-form text into a structured StrategyProfilePatch. "
            "Do not invent fields. Do not validate or persist anything. "
            "If the user did not clearly ask for a change, return an empty patch. "
            "Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.summary_model,
            tools=[],
            system_prompt=system_prompt,
            response_format=ToolStrategy(TradeStyleOverrideOutput),
        )
        return self._agent

    @staticmethod
    def _extract_output(result) -> TradeStyleOverrideOutput:
        if isinstance(result, TradeStyleOverrideOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, TradeStyleOverrideOutput):
                    return structured
                if isinstance(structured, dict):
                    return TradeStyleOverrideOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return TradeStyleOverrideOutput(**result["output"])
        if isinstance(result, str):
            return TradeStyleOverrideOutput(**json.loads(result))
        raise RuntimeError("Could not extract trade-style override output from LangChain agent result.")


class TradeStyleOverrideAgent:
    def __init__(
        self,
        config: TradeStyleOverrideAgentConfig | None = None,
        backend: TradeStyleOverrideBackend | None = None,
    ) -> None:
        self.config = config or TradeStyleOverrideAgentConfig()
        self.backend = backend or LangChainTradeStyleOverrideBackend(model=self.config.model)

    def parse_override(self, *, raw_text: str, current_profile: dict) -> TradeStyleOverrideOutput:
        return self.backend.parse_override(raw_text=raw_text, current_profile=current_profile)
