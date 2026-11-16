"""Authority matrix and deal classification. Enforced by the Caldova Deal System, not the model.

Fictional sample policy; human-readable copy in src/deal-desk/skills/pricing-policy/authority-matrix.md."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import MARGIN_FLOOR_PCT, evaluate
from .models import DealContext, PnL, Terms, terms_hash

AUTHORITY_MATRIX: dict[str, dict[str, float]] = {
    "agent": {
        "max_effective_rebate_pct": 10.0,
        "max_payment_terms_days": 60,
        "max_price_protection_months": 12,
        "max_mdf_pct_of_tcv": 2.0,
        "min_gm_pct": MARGIN_FLOOR_PCT,
    },
    "vp_finance": {
        "max_concession_usd": 5_000_000.0,
        "min_gm_pct": 28.0,
    },
    "cfo": {},
}

ROLE_RANK: dict[str, int] = {"readonly": -1, "seller": -1, "agent": 0, "vp_finance": 1, "cfo": 2}
APPROVER_DISPLAY: dict[str, str] = {"agent": "Caldova Deal Desk (agent)", "vp_finance": "Dana (VP Finance)", "cfo": "Morgan (CFO)"}


@dataclass(frozen=True)
class Exceeded:
    field: str
    requested: float
    limit: float

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "requested": round(self.requested, 4), "limit": self.limit}


@dataclass(frozen=True)
class AuthorityDecision:
    required_role: str
    exceeded: tuple[Exceeded, ...]
    gm_pct: float
    concession_usd: float
    terms_hash: str

    @property
    def within_agent_authority(self) -> bool:
        return self.required_role == "agent"

    def to_dict(self) -> dict[str, Any]:
        return {
            "required_role": self.required_role,
            "required_approver": APPROVER_DISPLAY[self.required_role],
            "exceeded": [e.to_dict() for e in self.exceeded],
            "gm_pct": round(self.gm_pct, 2),
            "concession_usd": round(self.concession_usd, 2),
            "terms_hash": self.terms_hash,
        }


def agent_limit_violations(ctx: DealContext, terms: Terms, pnl: PnL | None = None) -> list[Exceeded]:
    limits = AUTHORITY_MATRIX["agent"]
    pnl = pnl or evaluate(ctx, terms)
    out: list[Exceeded] = []
    if terms.effective_rebate_pct > limits["max_effective_rebate_pct"]:
        out.append(Exceeded("effective_rebate_pct", terms.effective_rebate_pct, limits["max_effective_rebate_pct"]))
    if terms.payment_terms_days > limits["max_payment_terms_days"]:
        out.append(Exceeded("payment_terms_days", terms.payment_terms_days, limits["max_payment_terms_days"]))
    if terms.price_protection_months > limits["max_price_protection_months"]:
        out.append(Exceeded("price_protection_months", terms.price_protection_months, limits["max_price_protection_months"]))
    mdf_pct = terms.mdf_usd / ctx.tcv_usd * 100 if ctx.tcv_usd else 0.0
    if mdf_pct > limits["max_mdf_pct_of_tcv"] + 1e-9:
        out.append(Exceeded("mdf_pct_of_tcv", mdf_pct, limits["max_mdf_pct_of_tcv"]))
    if pnl.gm_pct < limits["min_gm_pct"]:
        out.append(Exceeded("gm_pct", pnl.gm_pct, limits["min_gm_pct"]))
    return out


def required_approval(ctx: DealContext, terms: Terms) -> AuthorityDecision:
    """Lowest role allowed to approve `terms` on `ctx`."""
    pnl = evaluate(ctx, terms)
    exceeded = agent_limit_violations(ctx, terms, pnl)
    if not exceeded:
        role = "agent"
    else:
        vp = AUTHORITY_MATRIX["vp_finance"]
        if pnl.concession_usd <= vp["max_concession_usd"] and pnl.gm_pct >= vp["min_gm_pct"]:
            role = "vp_finance"
        else:
            role = "cfo"
            if pnl.concession_usd > vp["max_concession_usd"]:
                exceeded.append(Exceeded("concession_usd", pnl.concession_usd, vp["max_concession_usd"]))
            if pnl.gm_pct < vp["min_gm_pct"]:
                exceeded.append(Exceeded("gm_pct_vp_finance", pnl.gm_pct, vp["min_gm_pct"]))
    return AuthorityDecision(role, tuple(exceeded), pnl.gm_pct, pnl.concession_usd, terms_hash(terms))


def can_approve(role: str, required_role: str) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK[required_role] and ROLE_RANK.get(role, -1) >= 0


@dataclass(frozen=True)
class Classification:
    outcome: str  # auto_approve | counter | escalate
    required_role: str
    ask_gm_pct: float
    reason: str
    counter_terms: Terms | None = None
    counter_gm_pct: float | None = None
    counter_value_pct_of_ask: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "required_role": self.required_role,
            "ask_gm_pct": round(self.ask_gm_pct, 2),
            "reason": self.reason,
            "counter_terms": self.counter_terms.to_dict() if self.counter_terms else None,
            "counter_gm_pct": round(self.counter_gm_pct, 2) if self.counter_gm_pct is not None else None,
            "counter_value_pct_of_ask": round(self.counter_value_pct_of_ask, 1)
            if self.counter_value_pct_of_ask is not None
            else None,
        }


COUNTER_VALUE_THRESHOLD = 0.80


def classify_deal(ctx: DealContext, ask: Terms, *, counter_value_threshold: float = COUNTER_VALUE_THRESHOLD) -> Classification:
    """Queue triage (see authority-matrix.md): auto-approve within authority; counter when a within-authority
    package keeps >= 80 % of the asked customer value; otherwise escalate with the recommended
    (headroom-respecting) counter for a human approver."""
    from .search import SearchConstraints, scenario_search

    decision = required_approval(ctx, ask)
    if decision.within_agent_authority:
        return Classification("auto_approve", "agent", decision.gm_pct, "Ask is within agent authority and meets the 32% floor.")

    ask_value = evaluate(ctx, ask).customer_value_usd
    within = scenario_search(ask, SearchConstraints.agent_authority(), ctx)
    if within.top and within.top[0].pnl.customer_value_usd >= counter_value_threshold * ask_value:
        best = within.top[0]
        return Classification(
            "counter",
            "agent",
            decision.gm_pct,
            "Ask exceeds agent authority; a within-authority counter keeps "
            f"{best.value_pct_of_ask:.0f}% of the asked customer value.",
            counter_terms=best.terms,
            counter_gm_pct=best.pnl.gm_pct,
            counter_value_pct_of_ask=best.value_pct_of_ask,
        )

    recommended = scenario_search(ask, SearchConstraints(), ctx)
    if recommended.top:
        best = recommended.top[0]
        role = required_approval(ctx, best.terms).required_role
        return Classification(
            "escalate",
            role,
            decision.gm_pct,
            "No within-authority counter keeps 80% of the asked value; recommended counter needs "
            f"{APPROVER_DISPLAY[role]}.",
            counter_terms=best.terms,
            counter_gm_pct=best.pnl.gm_pct,
            counter_value_pct_of_ask=best.value_pct_of_ask,
        )
    return Classification(
        "escalate", decision.required_role, decision.gm_pct, "No counter meets the margin floor; human decision required."
    )
