"""Local HTML pages: the dashboard and the human approval page. Served only to direct local requests."""

from __future__ import annotations

from html import escape
from typing import Any

from caldova_pricing import MARGIN_FLOOR_PCT

from .identities import Identity

STATUS_COLOR = {
    "open": "#6b7280", "auto_approved": "#15803d", "countered": "#b45309", "awaiting_approval": "#7c3aed",
    "approved": "#0369a1", "rejected": "#b91c1c", "signed": "#065f46", "pending": "#7c3aed",
    "expired": "#6b7280", "superseded": "#6b7280",
}

STYLE = """<style>body{font-family:Segoe UI,system-ui,sans-serif;margin:24px;color:#111;max-width:1100px}
.banner{background:#fef3c7;border:1px solid #f59e0b;padding:8px 12px;border-radius:6px;margin-bottom:12px}
.warn{background:#fee2e2;border-color:#b91c1c}
table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #e5e7eb;padding:6px 8px;text-align:left;vertical-align:top}
.chip{color:#fff;border-radius:10px;padding:2px 8px;font-size:12px;white-space:nowrap}
button{font-size:16px;padding:8px 18px;margin-right:8px;border-radius:6px;border:0;color:#fff;cursor:pointer}
.ok{background:#15803d}.no{background:#b91c1c}select,input{font-size:15px;padding:6px}</style>"""

FICTIONAL = "<div class='banner'><b>Fictional sample data.</b> Decisions are recorded only in this local Deal System.</div>"


def _chip(status: str) -> str:
    return f"<span class='chip' style='background:{STATUS_COLOR.get(status, '#6b7280')}'>{escape(status.replace('_', ' '))}</span>"


def _page(title: str, body: str, *, refresh: bool = False) -> str:
    meta = "<meta http-equiv='refresh' content='3'>" if refresh else ""
    return (f"<!doctype html><html><head><meta charset='utf-8'>{meta}<title>{escape(title)}</title>{STYLE}</head>"
            f"<body>{FICTIONAL}{body}</body></html>")


def _terms_rows(t: dict[str, Any]) -> list[tuple[str, str]]:
    kicker = f" + {t['growth_kicker_pct']:g}% kicker at or above {t['growth_kicker_threshold_pct']:g}% of commit" if t.get("growth_kicker_pct") else ""
    return [
        ("Rebate", f"{t['rebate_pct']:g}%{kicker}"),
        ("Payment terms", f"Net-{t['payment_terms_days']}"),
        ("Price protection", f"{t['price_protection_months']} months" + (" + CPI cap" if t.get("cpi_cap") else "")),
        ("MDF", f"${t['mdf_usd']:,.0f}" + (" (sell-through)" if t.get("mdf_sell_through") else "")),
    ]


def render_message(title: str, message: str, back: str = "/") -> str:
    return _page(title, f"<h2>{escape(title)}</h2><p>{escape(message)}</p><p><a href='{escape(back)}'>Back</a></p>")


def render_dashboard(deals: list[dict[str, Any]], approvals: list[dict[str, Any]], *, api_key_required: bool) -> str:
    warn = "" if api_key_required else (
        "<div class='banner warn'><b>No API key set.</b> The REST and MCP API is unauthenticated; "
        "set DEAL_SYSTEM_API_KEY before exposing this server.</div>")
    approval_rows = "".join(
        f"<tr><td><a href='/approvals/{escape(a['approval_id'])}'>{escape(a['approval_id'])}</a></td>"
        f"<td>{escape(a['customer_name'])} <code>{escape(a['deal_id'])}</code></td><td>{escape(a['terms_summary'])}</td>"
        f"<td>{a['gm_pct']:.2f}%</td><td>{escape(a['approver_display'])}</td><td>{_chip(a['status'])}</td></tr>"
        for a in approvals
    ) or "<tr><td colspan='6'>No approval requests yet.</td></tr>"
    deal_rows = []
    for d in deals:
        a = d["ask"]
        ask = f"{a['rebate_pct']:g}% / Net-{a['payment_terms_days']} / {a['price_protection_months']} mo / ${a['mdf_usd'] / 1e3:,.0f}K MDF"
        deal_rows.append(
            f"<tr><td><code>{escape(d['deal_id'])}</code></td><td>{escape(d['customer_name'])}</td><td>{escape(d['seller'])}</td>"
            f"<td>${d['tcv_usd'] / 1e6:,.1f}M</td><td>{escape(ask)}</td><td>{_chip(d['status'])}</td>"
            f"<td>{escape((d.get('approved_by') or {}).get('display', ''))}</td></tr>")
    body = (
        f"{warn}<h2>Caldova Deal System</h2>"
        "<h3>Approval requests</h3><table><thead><tr><th>Approval</th><th>Deal</th><th>Terms</th><th>GM</th>"
        f"<th>Approver</th><th>Status</th></tr></thead><tbody>{approval_rows}</tbody></table>"
        "<h3>Deal queue</h3><table><thead><tr><th>Deal</th><th>Customer</th><th>Seller</th><th>TCV</th><th>Ask</th>"
        f"<th>Status</th><th>Approved by</th></tr></thead><tbody>{''.join(deal_rows)}</tbody></table>"
    )
    return _page("Caldova Deal System", body, refresh=True)


def render_approval_page(approval: dict[str, Any], deal: dict[str, Any], approvers: list[Identity], token: str | None) -> str:
    exceeded = "; ".join(f"{e['field']}: requested {e['requested']:g}, agent limit {e['limit']:g}" for e in approval["exceeded"])
    rows = [
        ("Customer", f"{deal['customer_name']} ({deal['deal_id']}, {deal['segment'].replace('_', ' ')})"),
        ("Seller", deal["seller"]),
        ("TCV", f"${deal['tcv_usd'] / 1e6:,.1f}M over {deal['term_years']} years"),
        *_terms_rows(approval["terms"]),
        ("Deal-life GM", f"{approval['gm_pct']:.2f}% (ask {deal['ask_economics']['gm_pct']:.2f}%, floor {MARGIN_FLOOR_PCT:g}%)"),
        ("Concession", f"${approval['concession_usd']:,.0f}"),
        ("Exceeds agent authority", exceeded or "none"),
        ("Required approver", approval["approver_display"]),
        ("Summary", approval.get("summary") or ""),
        ("Rationale", approval.get("rationale") or ""),
        ("Requested by", f"{approval['requested_by']['display']} at {approval['requested_at']}"),
        ("Expires", approval["expires_at"]),
        ("Terms hash", approval["terms_hash"]),
    ]
    table = "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows)
    alts = "".join(f"<li>{escape(a)}</li>" for a in approval.get("alternatives") or [])
    alts = f"<h3>Alternatives considered</h3><ol>{alts}</ol>" if alts else ""
    if approval["status"] == "pending" and token and approvers:
        options = "".join(
            f"<option value='{escape(i.identity_id)}'{' selected' if i.role == approval['required_role'] else ''}>{escape(i.display)}</option>"
            for i in approvers)
        action = (f"<form method='post'><input type='hidden' name='approval_token' value='{escape(token)}'>"
                  f"<input type='hidden' name='terms_hash' value='{escape(approval['terms_hash'])}'>"
                  f"<p><label>Decide as <select name='approver'>{options}</select></label></p>"
                  "<p><input name='comment' placeholder='Comment (optional)' style='width:100%'></p>"
                  "<button class='ok' name='decision' value='approve'>Approve</button>"
                  "<button class='no' name='decision' value='reject'>Reject</button></form>")
    else:
        by = approval.get("decided_by") or {}
        decided = f" by {by['display']} at {approval['decided_at']}" if by else ""
        comment = f" ({approval['comment']})" if approval.get("comment") else ""
        action = f"<p>{_chip(approval['status'])} {escape(decided + comment)}</p>"
    body = (f"<p><a href='/'>Dashboard</a></p><h2>Approval {escape(approval['approval_id'])} {_chip(approval['status'])}</h2>"
            f"<table>{table}</table>{alts}<h3>Decision</h3>{action}")
    return _page(f"Approval {approval['approval_id']}", body)
