from typing import Literal

from pydantic import BaseModel


CommandName = Literal["start", "trade-style", "follow", "stop", "portfolio", "history", "status"]


class CommandEnvelope(BaseModel):
    user_id: str
    chat_id: str
    raw_text: str


class CommandResponse(BaseModel):
    ok: bool
    command: CommandName
    message: str
    payload: dict = {}


WALLET_AGENT_COMMANDS: set[str] = {"start", "status", "portfolio", "history"}
