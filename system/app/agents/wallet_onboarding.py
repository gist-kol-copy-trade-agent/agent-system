from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel

from app.agents.runtime_context import WalletOnboardingRuntimeContext
from app.config.settings import get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.services.onchainos_runner import OnchainOSMutatingRunner, OnchainOSReadonlyRunner
from app.tools.langchain_agent_tools import build_wallet_onboarding_agent_tools


class WalletOnboardingOutput(BaseModel):
    phase: str
    message: str
    payload: dict[str, Any]


class WalletOnboardingBackend(Protocol):
    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletOnboardingOutput: ...


@dataclass
class WalletOnboardingAgentConfig:
    tools: list = field(default_factory=build_wallet_onboarding_agent_tools)


class LangChainWalletOnboardingBackend:
    def __init__(
        self,
        *,
        model: str | None = None,
        tools: list | None = None,
        skill_registry: OKXSkillRegistry | None = None,
        readonly_runner: OnchainOSReadonlyRunner | None = None,
        mutating_runner: OnchainOSMutatingRunner | None = None,
    ) -> None:
        self._agent = None
        self.model = model
        self.tools = tools if tools is not None else build_wallet_onboarding_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(timeout_seconds=get_settings().models.timeout_seconds)
        self.mutating_runner = mutating_runner or OnchainOSMutatingRunner(timeout_seconds=get_settings().models.timeout_seconds)

    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletOnboardingOutput:
        agent = self._get_agent()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": self._build_prompt(raw_text=raw_text, phase=phase, locale=locale)}]},
            context=WalletOnboardingRuntimeContext(
                user_id=user_id,
                raw_text=raw_text,
                phase=phase,
                locale=locale,
                load_skill_provider=self.skill_registry.load_skill,
                load_reference_provider=self.skill_registry.load_reference,
                readonly_command_provider=self.readonly_runner.run,
                mutating_wallet_provider=self._mutating_wallet_provider,
            ),
        )
        return self._extract_output(result)

    def _get_agent(self):
        if self._agent is not None:
            return self._agent
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy

        system_prompt = (
            "You are a wallet onboarding agent for an OKX OnchainOS trading bot. "
            "Always load okx-agentic-wallet first and follow its authentication flow exactly. "
            "Use run_onchainos_readonly for wallet status, balance, and addresses. "
            "Use run_onchainos_mutating_wallet only for wallet_login and wallet_verify. "
            "Support three phases: start, awaiting_email, awaiting_otp. "
            "If wallet is already logged in, fetch balance and addresses and finish. "
            "If login is needed, ask for email first, then verification code, then return wallet-ready output. "
            "Return only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.summary_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=WalletOnboardingRuntimeContext,
            response_format=ToolStrategy(WalletOnboardingOutput),
        )
        return self._agent

    @staticmethod
    def _build_prompt(*, raw_text: str, phase: str, locale: str) -> str:
        return (
            "Handle this wallet onboarding turn.\n"
            f"phase={phase}\n"
            f"locale={locale}\n"
            f"user_input={raw_text}"
        )

    def _mutating_wallet_provider(self, request: dict[str, Any]) -> dict[str, Any]:
        action = request.get("action")
        if action == "wallet_login":
            email = str(request.get("email") or "").strip()
            locale = str(request.get("locale") or "en-US")
            return self.mutating_runner.run(f"onchainos wallet login {email} --locale {locale}")
        if action == "wallet_verify":
            otp = str(request.get("otp") or "").strip()
            return self.mutating_runner.run(f"onchainos wallet verify {otp}")
        return {"ok": False, "error": f"unsupported wallet action: {action}"}

    @staticmethod
    def _extract_output(result) -> WalletOnboardingOutput:
        if isinstance(result, WalletOnboardingOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, WalletOnboardingOutput):
                    return structured
                if isinstance(structured, dict):
                    return WalletOnboardingOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return WalletOnboardingOutput(**result["output"])
        if isinstance(result, str):
            return WalletOnboardingOutput(**json.loads(result))
        raise RuntimeError("Could not extract wallet onboarding output from LangChain agent result.")


class WalletOnboardingAgent:
    def __init__(self, config: WalletOnboardingAgentConfig | None = None, backend: WalletOnboardingBackend | None = None) -> None:
        self.config = config or WalletOnboardingAgentConfig()
        self.backend = backend or LangChainWalletOnboardingBackend(tools=self.config.tools)

    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletOnboardingOutput:
        return self.backend.handle(user_id=user_id, raw_text=raw_text, phase=phase, locale=locale)
