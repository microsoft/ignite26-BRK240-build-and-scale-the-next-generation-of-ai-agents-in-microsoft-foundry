"""Who is acting. API and MCP callers always act as the Deal Desk agent; the human approvers
(Dana and Morgan) act only through the local approval page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Identity:
    identity_id: str
    display: str
    role: str  # agent | vp_finance | cfo
    kind: str  # agent | human

    @property
    def is_human(self) -> bool:
        return self.kind == "human"

    def to_dict(self) -> dict[str, Any]:
        return {"identity_id": self.identity_id, "display": self.display, "role": self.role, "kind": self.kind}


AGENT = Identity("agent-deal-desk", "Caldova Deal Desk (agent)", "agent", "agent")
DANA = Identity("dana-vp-finance", "Dana (VP Finance)", "vp_finance", "human")
MORGAN = Identity("morgan-cfo", "Morgan (CFO)", "cfo", "human")

APPROVERS: dict[str, Identity] = {i.identity_id: i for i in (DANA, MORGAN)}
