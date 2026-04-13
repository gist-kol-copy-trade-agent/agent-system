from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel

from app.agents.runtime_context import ParsingAgentRuntimeContext
from app.services.onchainos_runner import OnchainOSReadonlyRunner
from app.services.okx_skills import OKXSkillRegistry
from app.schemas.domain import ParsedSignal
from app.config.settings import ensure_openai_runtime_env, get_settings
from app.tools.langchain_agent_tools import build_parsing_agent_tools


class ParsedSignalOutput(BaseModel):
    message_type: str
    is_actionable: bool
    raw_symbol: str | None = None
    raw_contract_address: str | None = None
    raw_chain_hint: str | None = None
    entry_reference_text: str | None = None
    target_reference_text: str | None = None
    stop_reference_text: str | None = None
    urgency: str | None = None
    resolved_symbol: str | None = None
    resolved_contract_address: str | None = None
    resolved_chain: str | None = None
    resolved_token_name: str | None = None
    resolved_decimals: int | None = None
    confidence: float
    reasoning_summary: str


class ParsingBackend(Protocol):
    def parse(self, *, source_id: str, message_id: str, message_text: str) -> ParsedSignal: ...


@dataclass
class ParsingAgentConfig:
    tools: list = field(default_factory=build_parsing_agent_tools)


class LangChainParsingBackend:
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
        self.tools = tools if tools is not None else build_parsing_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(
            timeout_seconds=get_settings().models.timeout_seconds
        )

    def parse(self, *, source_id: str, message_id: str, message_text: str) -> ParsedSignal:
        agent = self._get_agent()
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Parse this Telegram trading message into structured fields.\n"
                            "If token identity is ambiguous or incomplete, first load the relevant OKX skill prompt, "
                            "then use run_onchainos_readonly with the commands described by that skill to resolve token clues.\n"
                            f"Message:\n{message_text}"
                        ),
                    }
                ]
            },
            context=ParsingAgentRuntimeContext(
                source_id=source_id,
                message_id=message_id,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
            ),
        )
        output = self._extract_output(result)
        return ParsedSignal(
            source_id=source_id,
            message_id=message_id,
            message_type=output.message_type,  # type: ignore[arg-type]
            is_actionable=output.is_actionable,
            raw_symbol=output.raw_symbol,
            raw_contract_address=output.raw_contract_address,
            raw_chain_hint=output.raw_chain_hint,
            entry_reference_text=output.entry_reference_text,
            target_reference_text=output.target_reference_text,
            stop_reference_text=output.stop_reference_text,
            urgency=output.urgency,  # type: ignore[arg-type]
            resolved_symbol=output.resolved_symbol,
            resolved_contract_address=output.resolved_contract_address,
            resolved_chain=output.resolved_chain,
            resolved_token_name=output.resolved_token_name,
            resolved_decimals=output.resolved_decimals,
            confidence=output.confidence,
            reasoning_summary=output.reasoning_summary,
        )

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        ensure_openai_runtime_env()

        try:
            from langchain.agents import create_agent
            from langchain.agents.structured_output import ToolStrategy
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("LangChain is not installed for LangChainParsingBackend.") from exc

        system_prompt = (
            "You are a parsing agent for Telegram KOL trading messages. "
            "Classify each message into one of: trade_call, trade_update, exit_signal, noise. "
            "Extract raw symbol, raw contract address, raw chain hint, entry, target, stop, urgency, confidence, and reasoning summary. "
            "When needed, also resolve the best supported token clue set: resolved symbol, resolved contract address, resolved chain, token name, and decimals. "
            "For OKX OnchainOS capabilities, use the skills pattern with progressive disclosure: "
            "load the relevant skill prompt first, then follow its command guidance via run_onchainos_readonly when needed. "
            "Do not invent token contracts or chains if the evidence is weak. "
            "Output only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.parsing_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=ParsingAgentRuntimeContext,
            response_format=ToolStrategy(ParsedSignalOutput),
        )
        return self._agent

    def _extract_output(self, result) -> ParsedSignalOutput:
        if isinstance(result, ParsedSignalOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, ParsedSignalOutput):
                    return structured
                if isinstance(structured, dict):
                    return ParsedSignalOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return ParsedSignalOutput(**result["output"])
        if isinstance(result, str):
            return ParsedSignalOutput(**json.loads(result))
        raise RuntimeError("Could not extract structured parsing output from LangChain agent result.")


class ParsingAgent:
    """Parsing agent with pluggable backends.

    Runtime behavior always uses a LangChain-backed path unless a fake backend
    is injected explicitly for tests.
    """

    def __init__(self, config: ParsingAgentConfig | None = None, backend: ParsingBackend | None = None) -> None:
        self.config = config or ParsingAgentConfig()
        if backend is not None:
            self.backend = backend
        else:
            self.backend = LangChainParsingBackend(tools=self.config.tools)

    def parse(self, *, source_id: str, message_id: str, message_text: str) -> ParsedSignal:
        return self.backend.parse(source_id=source_id, message_id=message_id, message_text=message_text)
