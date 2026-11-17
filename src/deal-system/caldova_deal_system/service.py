"""Deal System business logic. Approval authority is enforced here, by caller identity, not by the model."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from caldova_pricing import (
    APPROVER_DISPLAY,
    DealContext,
    InvalidTermsError,
    Terms,
    can_approve,
    classify_deal,
    evaluate,
    required_approval,
    terms_hash,
)

from .config import Settings
from .errors import DealSystemError, forbidden, invalid_argument, invalid_state, invalid_terms, not_found, requires_human_approval
from .identities import Identity
from .store import JsonStore
from .termsheet import render_term_sheet

STATUSES = ("open", "auto_approved", "countered", "awaiting_approval", "approved", "rejected", "signed")
CRM_STAGES = ("counter_sent", "approval_requested", "term_sheet_sent", "signed", "closed_lost")
APPROVED_STATES = ("auto_approved", "approved")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class DealService:
    def __init__(self, settings: Settings, *, clock: Callable[[], datetime] | None = None) -> None:
        self.settings = settings
        self.store = JsonStore(settings.state_dir, settings.seed_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _parse_terms(terms: Any) -> Terms:
        if isinstance(terms, Terms):
            return terms
        if hasattr(terms, "model_dump"):
            terms = terms.model_dump(exclude_none=True)
        try:
            return Terms.from_dict(terms)
        except InvalidTermsError as exc:
            raise invalid_terms(str(exc)) from exc

    @staticmethod
    def _deal(state: dict[str, Any], deal_id: str) -> dict[str, Any]:
        deal = state["deals"].get(deal_id)
        if deal is None:
            raise not_found("deal", deal_id)
        return deal

    def _economics(self, deal: dict[str, Any], terms: Terms) -> dict[str, Any]:
        ctx = DealContext.from_dict(deal["context"])
        pnl = evaluate(ctx, terms)
        auth = required_approval(ctx, terms)
        return {
            "terms_hash": terms_hash(terms),
            "gm_pct": round(pnl.gm_pct, 2),
            "meets_floor": pnl.meets_floor,
            "customer_value_usd": round(pnl.customer_value_usd, 2),
            "concession_usd": round(pnl.concession_usd, 2),
            "required_role": auth.required_role,
            "required_approver": APPROVER_DISPLAY[auth.required_role],
            "exceeded_agent_authority": [e.to_dict() for e in auth.exceeded],
            "pnl": pnl.to_dict(),
        }

    def _expired(self, approval: dict[str, Any]) -> bool:
        return self.clock() > _parse_iso(approval["expires_at"])

    def _approval_view(self, a: dict[str, Any]) -> dict[str, Any]:
        view = {k: v for k, v in a.items() if k != "token_sha256"}
        if view["status"] == "pending" and self._expired(a):
            view["status"] = "expired"
        return view

    def _deal_view(self, deal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in deal.items() if k != "approval_ids"}
        out["ask_economics"] = self._economics(deal, Terms.from_dict(deal["ask"]))
        out["approvals"] = [self._approval_view(state["approvals"][a]) for a in deal["approval_ids"]]
        return out

    # ------------------------------------------------------------------ reads
    def get_deal(self, caller: Identity, deal_id: str) -> dict[str, Any]:
        return self.store.read(lambda s: self._deal_view(self._deal(s, deal_id), s))

    def list_queue(self, caller: Identity, status: str | None = None, limit: int = 50) -> dict[str, Any]:
        if status is not None and status not in STATUSES:
            raise invalid_argument(f"status must be one of {list(STATUSES)}")
        limit = max(1, min(int(limit), 500))

        def q(s: dict[str, Any]) -> dict[str, Any]:
            counts = {st: 0 for st in STATUSES}
            rows = []
            for d in s["deals"].values():
                counts[d["status"]] += 1
                if status is None or d["status"] == status:
                    rows.append({k: d[k] for k in ("deal_id", "customer_name", "segment", "tcv_usd", "term_years", "status", "seller", "ask")})
            return {"synthetic": True, "total": len(rows), "deals": rows[:limit], "counts": counts}

        return self.store.read(q)

    def get_approval(self, caller: Identity, approval_id: str) -> dict[str, Any]:
        def q(s: dict[str, Any]) -> dict[str, Any]:
            a = s["approvals"].get(approval_id)
            if a is None:
                raise not_found("approval", approval_id)
            return self._approval_view(a)

        return self.store.read(q)

    def list_deals(self) -> list[dict[str, Any]]:
        return self.store.read(lambda s: list(s["deals"].values()))

    def list_approvals(self) -> list[dict[str, Any]]:
        """Newest first, for the local dashboard."""
        return self.store.read(lambda s: [self._approval_view(a) for a in reversed(list(s["approvals"].values()))])

    def inbox_token(self, approval_id: str) -> str | None:
        """The one-time token delivered to the approver's local inbox. Only the local approval page reads it."""
        def q(s: dict[str, Any]) -> str | None:
            return next((m["approval_token"] for m in s["inbox"] if m["approval_id"] == approval_id), None)

        return self.store.read(q)

    def inbox(self) -> list[dict[str, Any]]:
        return self.store.read(lambda s: s["inbox"])

    # ------------------------------------------------------------------ decisions
    def submit_decision(self, caller: Identity, deal_id: str, decision: str, terms: Any = None, rationale: str = "") -> dict[str, Any]:
        if decision not in ("approve", "counter", "reject"):
            raise invalid_argument("decision must be approve | counter | reject")
        if caller.is_human and decision == "approve":
            raise forbidden(f"{caller.display} approves through the approval page, not submit_decision", next_action="request_approval")
        parsed = self._parse_terms(terms) if decision != "reject" else None

        def m(s: dict[str, Any]) -> dict[str, Any]:
            deal = self._deal(s, deal_id)
            if deal["status"] == "signed":
                raise invalid_state("deal is already signed", deal_id=deal_id, status=deal["status"])
            now = _iso(self.clock())
            record: dict[str, Any] = {"decision": decision, "by": caller.to_dict(), "at": now, "rationale": rationale}
            if parsed is not None:
                econ = self._economics(deal, parsed)
                record.update({"terms": parsed.to_dict(), "terms_hash": econ["terms_hash"], "gm_pct": econ["gm_pct"], "required_role": econ["required_role"]})
                if decision == "approve" and deal["status"] in APPROVED_STATES and deal["approved_terms_hash"] == econ["terms_hash"]:
                    return {"deal_id": deal_id, "status": deal["status"], "idempotent": True, **econ}
                if not can_approve(caller.role, econ["required_role"]):
                    raise requires_human_approval(
                        f"Terms exceed the authority of {caller.display}.",
                        deal_id=deal_id,
                        caller=caller.to_dict(),
                        decision=decision,
                        terms_hash=econ["terms_hash"],
                        gm_pct=econ["gm_pct"],
                        concession_usd=econ["concession_usd"],
                        exceeded=econ["exceeded_agent_authority"],
                        required_approver_role=econ["required_role"],
                        required_approver=econ["required_approver"],
                    )
            if decision == "approve":
                deal["status"] = "auto_approved"
                deal.update({"approved_terms": record["terms"], "approved_terms_hash": record["terms_hash"], "approved_by": caller.to_dict(), "approved_at": now})
            elif decision == "counter":
                deal["status"] = "countered"
                deal["counter_terms"] = record["terms"]
            else:
                deal["status"] = "rejected"
            deal["decisions"].append(record)
            return {"deal_id": deal_id, "status": deal["status"], "decision": record}

        return self.store.mutate(m)

    # ------------------------------------------------------------------ approvals
    def request_approval(self, caller: Identity, deal_id: str, terms: Any, rationale: str, summary: str | None = None,
                         alternatives: list[str] | None = None) -> dict[str, Any]:
        parsed = self._parse_terms(terms)
        token = secrets.token_urlsafe(24)
        approval_id = "APR-" + secrets.token_hex(4).upper()
        now = self.clock()

        def m(s: dict[str, Any]) -> dict[str, Any]:
            deal = self._deal(s, deal_id)
            if deal["status"] in ("signed",) + APPROVED_STATES:
                raise invalid_state(f"deal is {deal['status']}; no approval needed", deal_id=deal_id, status=deal["status"])
            econ = self._economics(deal, parsed)
            if econ["required_role"] == "agent":
                raise invalid_state("terms are within agent authority; use submit_decision(approve)", deal_id=deal_id, terms_hash=econ["terms_hash"])
            for aid in deal["approval_ids"]:
                if s["approvals"][aid]["status"] == "pending":
                    s["approvals"][aid]["status"] = "superseded"
            approval = {
                "approval_id": approval_id,
                "deal_id": deal_id,
                "customer_name": deal["customer_name"],
                "status": "pending",
                "terms": parsed.to_dict(),
                "terms_summary": parsed.describe(),
                "terms_hash": econ["terms_hash"],
                "required_role": econ["required_role"],
                "approver_display": econ["required_approver"],
                "gm_pct": econ["gm_pct"],
                "concession_usd": econ["concession_usd"],
                "exceeded": econ["exceeded_agent_authority"],
                "rationale": rationale,
                "summary": summary,
                "alternatives": [str(a) for a in (alternatives or [])][:5],
                "requested_by": caller.to_dict(),
                "requested_at": _iso(now),
                "expires_at": _iso(now + timedelta(minutes=self.settings.approval_ttl_minutes)),
                "token_sha256": _token_digest(token),
                "decision": None,
                "decided_by": None,
                "decided_at": None,
                "comment": None,
            }
            s["approvals"][approval_id] = approval
            deal["approval_ids"].append(approval_id)
            deal["status"] = "awaiting_approval"
            # Local notifier: deliver the one-time token to the approver's inbox (the local dashboard), never to the caller.
            s["inbox"].append({"approval_id": approval_id, "approver_display": econ["required_approver"],
                               "approval_token": token, "delivered_at": _iso(now)})
            return self._approval_view(approval)

        view = self.store.mutate(m)
        view["approval_page"] = f"{self.settings.local_url}/approvals/{approval_id}"
        return view

    def record_approval(self, caller: Identity, approval_id: str, approval_token: str, decision: str, terms_hash_value: str,
                        comment: str | None = None) -> dict[str, Any]:
        if decision not in ("approve", "reject"):
            raise invalid_argument("decision must be approve | reject")

        def m(s: dict[str, Any]) -> dict[str, Any]:
            a = s["approvals"].get(approval_id)
            if a is None:
                raise not_found("approval", approval_id)
            if not caller.is_human or not can_approve(caller.role, a["required_role"]):
                raise DealSystemError(
                    "APPROVER_NOT_AUTHORIZED", 403, f"{caller.display} cannot record a {a['required_role']} approval",
                    caller=caller.to_dict(), required_approver_role=a["required_role"],
                )
            if a["status"] != "pending":
                raise DealSystemError("APPROVAL_ALREADY_USED", 409, f"approval is {a['status']}; approvals are one-time", approval_id=approval_id)
            if self._expired(a):
                a["status"] = "expired"
                return {"expired": True}
            if not approval_token or not hmac.compare_digest(_token_digest(approval_token), a["token_sha256"]):
                raise DealSystemError("INVALID_APPROVAL_TOKEN", 403, "approval token is invalid", approval_id=approval_id)
            if not hmac.compare_digest(str(terms_hash_value or ""), a["terms_hash"]):
                raise DealSystemError("TERMS_MISMATCH", 409, "terms hash does not match the approval request", approval_id=approval_id)
            deal = self._deal(s, a["deal_id"])
            if deal["status"] != "awaiting_approval":
                raise invalid_state(f"deal is {deal['status']}", deal_id=deal["deal_id"])
            now = _iso(self.clock())
            a.update({"status": "approved" if decision == "approve" else "rejected", "decision": decision,
                      "decided_by": caller.to_dict(), "decided_at": now, "comment": comment})
            if decision == "approve":
                deal.update({"status": "approved", "approved_terms": a["terms"], "approved_terms_hash": a["terms_hash"],
                             "approved_by": caller.to_dict(), "approved_at": now})
            else:
                deal["status"] = "rejected"
            deal["decisions"].append({"decision": decision, "by": caller.to_dict(), "at": now, "approval_id": approval_id,
                                      "terms_hash": a["terms_hash"], "rationale": comment or ""})
            return {"approval": self._approval_view(a), "deal_id": deal["deal_id"], "deal_status": deal["status"]}

        result = self.store.mutate(m)  # an expiry is persisted before it is reported
        if result.get("expired"):
            raise DealSystemError("APPROVAL_EXPIRED", 410, "approval request expired", approval_id=approval_id)
        return result

    # ------------------------------------------------------------------ CRM + term sheet
    def update_crm(self, caller: Identity, deal_id: str, stage: str, note: str = "") -> dict[str, Any]:
        if stage not in CRM_STAGES:
            raise invalid_argument(f"stage must be one of {list(CRM_STAGES)}")

        def m(s: dict[str, Any]) -> dict[str, Any]:
            deal = self._deal(s, deal_id)
            if stage in ("signed", "term_sheet_sent") and deal["status"] not in APPROVED_STATES + ("signed",):
                raise invalid_state(f"cannot set CRM stage {stage!r}: deal is {deal['status']}", deal_id=deal_id)
            entry = {"stage": stage, "note": note, "by": caller.to_dict(), "at": _iso(self.clock())}
            deal["crm_activity"].append(entry)
            if stage == "signed":
                deal["status"] = "signed"
            return {"deal_id": deal_id, "status": deal["status"], "crm_entry": entry, "crm_activity_count": len(deal["crm_activity"])}

        return self.store.mutate(m)

    def term_sheet_path(self, deal_id: str) -> Path:
        return self.settings.state_dir / "term_sheets" / f"{deal_id}.docx"

    def generate_term_sheet(self, caller: Identity, deal_id: str) -> dict[str, Any]:
        deal = self.store.read(lambda s: self._deal(s, deal_id))
        if deal["status"] not in APPROVED_STATES + ("signed",) or not deal["approved_terms"]:
            raise invalid_state(f"term sheet requires an approved deal; deal is {deal['status']}", deal_id=deal_id)
        terms = Terms.from_dict(deal["approved_terms"])
        pnl = evaluate(DealContext.from_dict(deal["context"]), terms)
        approver = deal["approved_by"] or {}
        values = {
            "deal_id": deal_id, "customer_name": deal["customer_name"], "segment": deal["segment"].replace("_", " "),
            "stores": f"{deal['stores']:,}" if deal["stores"] else "n/a", "seller": deal["seller"], "term_years": deal["term_years"],
            "start_date": deal["start_date"], "tcv": f"${deal['tcv_usd'] / 1e6:,.1f}M",
            "rebate": f"{terms.rebate_pct:g}% of list revenue",
            "kicker": f"+{terms.growth_kicker_pct:g}% on all volume in years >= {terms.growth_kicker_threshold_pct:g}% of commit" if terms.growth_kicker_pct else "none",
            "payment_terms": f"Net-{terms.payment_terms_days}",
            "price_protection": f"{terms.price_protection_months} months" + (", then CPI-capped adjustments" if terms.cpi_cap else ""),
            "mdf": f"${terms.mdf_usd:,.0f}" + (" tied to verified sell-through" if terms.mdf_sell_through else ""),
            "gm_pct": f"{pnl.gm_pct:.1f}%", "concession": f"${pnl.concession_usd / 1e6:,.2f}M",
            "decision": "Auto-approved within agent authority" if deal["status"] == "auto_approved" else "Approved",
            "approver": approver.get("display", ""), "approver_identity": approver.get("identity_id", ""),
            "approved_at": deal["approved_at"] or "", "terms_hash": deal["approved_terms_hash"],
        }
        out = self.term_sheet_path(deal_id)
        render_term_sheet(self.settings.template_path, values, out)
        info = {"path": str(out), "download_url": f"{self.settings.local_url}/term-sheets/{deal_id}",
                "terms_hash": deal["approved_terms_hash"], "generated_at": _iso(self.clock()), "generated_by": caller.to_dict()}

        def m(s: dict[str, Any]) -> dict[str, Any]:
            self._deal(s, deal_id)["term_sheet"] = info
            return {"deal_id": deal_id, **info}

        return self.store.mutate(m)

    def reset(self) -> dict[str, Any]:
        return self.store.reset()

    # ------------------------------------------------------------------ economics fallback / batch tool
    def evaluate_deal(self, caller: Identity, deal_id: str, terms: Any = None) -> dict[str, Any]:
        """Same deterministic caldova_pricing engine as the hosted Deal Economics agent (the primary path for live
        reviews); used by the scheduled sweep and as a fallback."""
        deal = self.store.read(lambda s: self._deal(s, deal_id))
        ask = Terms.from_dict(deal["ask"])
        ask_econ = self._economics(deal, ask)

        def brief(econ: dict[str, Any], t: Terms) -> dict[str, Any]:
            value_pct = round(econ["customer_value_usd"] / ask_econ["customer_value_usd"] * 100, 1) if ask_econ["customer_value_usd"] else None
            return {"terms": t.to_dict(), "summary": t.describe(), **{k: v for k, v in econ.items() if k != "pnl"},
                    "waterfall": econ["pnl"], "customer_value_pct_of_ask": value_pct}

        out: dict[str, Any] = {
            "deal_id": deal_id, "customer_name": deal["customer_name"], "synthetic": True,
            "source": "Deal System economics (caldova_pricing); the hosted Deal Economics agent is the primary path",
            "margin_floor_pct": 32.0, "ask": brief(ask_econ, ask),
        }
        if terms is not None:
            parsed = self._parse_terms(terms)
            out["proposed"] = brief(self._economics(deal, parsed), parsed)
        else:
            cls = classify_deal(DealContext.from_dict(deal["context"]), ask)
            out["classification"] = {k: v for k, v in cls.to_dict().items() if k != "counter_terms"}
            if cls.counter_terms is not None:
                out["recommended_counter"] = brief(self._economics(deal, cls.counter_terms), cls.counter_terms)
        return out
