from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.agents.runtime_context import WalletAgentRuntimeContext
from app.config.settings import ensure_openai_runtime_env, get_settings
from app.services.okx_skills import OKXSkillRegistry
from app.services.onchainos_runner import OnchainOSMutatingRunner, OnchainOSReadonlyRunner
from app.tools.langchain_agent_tools import build_wallet_agent_tools


class WalletAgentPayload(BaseModel):
    logged_in: bool = Field(description="Whether the wallet is authenticated after this turn.")
    email: str | None = Field(default=None, description="Email captured during onboarding, if applicable.")
    account_id: str | None = Field(default=None, description="Current wallet account identifier if available.")
    account_name: str | None = Field(default=None, description="Current wallet account name if available.")
    login_type: str | None = Field(default=None, description="Login type if exposed by the wallet skill.")
    wallet_evm_address: str | None = Field(default=None, description="Primary EVM wallet address if available.")
    wallet_sol_address: str | None = Field(default=None, description="Primary Solana wallet address if available.")
    wallet_xlayer_address: str | None = Field(default=None, description="Primary X Layer wallet address if available.")


class WalletAgentOutput(BaseModel):
    phase: Literal["start", "awaiting_email", "awaiting_otp", "ready", "status"] = Field(
        description="Next wallet phase after handling the current turn."
    )
    message: str = Field(description="User-facing wallet response.")
    payload: WalletAgentPayload = Field(description="Structured wallet state and wallet details.")


class WalletAgentBackend(Protocol):
    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletAgentOutput: ...


@dataclass
class WalletAgentConfig:
    tools: list = field(default_factory=build_wallet_agent_tools)


class LangChainWalletBackend:
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
        self.tools = tools if tools is not None else build_wallet_agent_tools()
        self.skill_registry = skill_registry or OKXSkillRegistry()
        self.readonly_runner = readonly_runner or OnchainOSReadonlyRunner(timeout_seconds=get_settings().models.timeout_seconds)
        self.mutating_runner = mutating_runner or OnchainOSMutatingRunner(timeout_seconds=get_settings().models.timeout_seconds)

    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletAgentOutput:
        agent = self._get_agent()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": self._build_prompt(raw_text=raw_text, phase=phase, locale=locale)}]},
            context=WalletAgentRuntimeContext(
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
        ensure_openai_runtime_env()
        from langchain.agents import create_agent
        from langchain.agents.structured_output import ToolStrategy

        system_prompt = (
            "You are a wallet agent for an OKX OnchainOS trading bot. "
            "Always load okx-agentic-wallet first and follow its authentication and status flow exactly. "
            "Use run_onchainos_readonly for wallet status, balance, and addresses. "
            "Use run_onchainos_mutating_wallet only for wallet_login and wallet_verify. "
            "Support phases: start, awaiting_email, awaiting_otp, and status. "
            "If phase=status, inspect wallet status and return current readiness without starting onboarding unless clearly needed. "
            "If phase=start and wallet is already logged in, fetch wallet-ready details and finish. "
            "If login is needed, ask for email first, then verification code, then return wallet-ready output. "
            "Return only the structured schema."
        )
        self._agent = create_agent(
            model=self.model or get_settings().models.wallet_model,
            tools=self.tools,
            system_prompt=system_prompt,
            context_schema=WalletAgentRuntimeContext,
            response_format=ToolStrategy(WalletAgentOutput),
        )
        return self._agent

    @staticmethod
    def _build_prompt(*, raw_text: str, phase: str, locale: str) -> str:
        return (
            "Handle this wallet turn.\n"
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
    def _extract_output(result) -> WalletAgentOutput:
        if isinstance(result, WalletAgentOutput):
            return result
        if isinstance(result, dict):
            if "structured_response" in result:
                structured = result["structured_response"]
                if isinstance(structured, WalletAgentOutput):
                    return structured
                if isinstance(structured, dict):
                    return WalletAgentOutput(**structured)
            if "output" in result and isinstance(result["output"], dict):
                return WalletAgentOutput(**result["output"])
        if isinstance(result, str):
            return WalletAgentOutput(**json.loads(result))
        raise RuntimeError("Could not extract wallet agent output from LangChain agent result.")


class WalletAgent:
    def __init__(self, config: WalletAgentConfig | None = None, backend: WalletAgentBackend | None = None) -> None:
        self.config = config or WalletAgentConfig()
        self.backend = backend or LangChainWalletBackend(tools=self.config.tools)

    def handle(self, *, user_id: str, raw_text: str, phase: str, locale: str) -> WalletAgentOutput:
        return self.backend.handle(user_id=user_id, raw_text=raw_text, phase=phase, locale=locale)
