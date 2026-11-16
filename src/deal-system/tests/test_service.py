from datetime import timedelta

from docx import Document

from caldova_pricing import fixtures as F
from caldova_pricing import terms_hash
from caldova_deal_system.identities import AGENT, DANA, MORGAN

from conftest import error_of

NW, RT = F.NORTHWIND_DEAL_ID, F.ROUTINE_DEAL_ID


def _request(svc, terms=None):
    appr = svc.request_approval(AGENT, NW, terms or F.northwind_counter(), "counter")
    return appr, svc.inbox_token(appr["approval_id"])


def test_seed_loads_42_open_deals(svc):
    q = svc.list_queue(AGENT, limit=500)
    assert q["counts"]["open"] == 42 and q["total"] == 42
    econ = svc.get_deal(AGENT, NW)["ask_economics"]
    assert abs(econ["gm_pct"] - 26.4) < 0.5 and econ["required_role"] == "cfo"


def test_over_authority_approve_is_403_with_reason(svc):
    e = error_of(lambda: svc.submit_decision(AGENT, NW, "approve", F.northwind_counter()))
    assert e.code == "REQUIRES_HUMAN_APPROVAL" and e.http_status == 403
    body = e.to_dict()["error"]
    assert body["required_approver_role"] == "vp_finance"
    assert body["exceeded"] == [{"field": "effective_rebate_pct", "requested": 14.0, "limit": 10.0}]
    assert body["terms_hash"] == terms_hash(F.northwind_counter())
    e = error_of(lambda: svc.submit_decision(AGENT, NW, "approve", F.northwind_ask()))
    assert e.to_dict()["error"]["required_approver_role"] == "cfo"
    assert error_of(lambda: svc.submit_decision(AGENT, NW, "counter", F.northwind_counter())).code == "REQUIRES_HUMAN_APPROVAL"
    assert svc.get_deal(AGENT, NW)["status"] == "open"


def test_routine_auto_approve_is_idempotent(svc):
    assert svc.submit_decision(AGENT, RT, "approve", F.routine_ask(), "within authority")["status"] == "auto_approved"
    assert svc.submit_decision(AGENT, RT, "approve", F.routine_ask()).get("idempotent") is True


def test_approval_happy_path_records_identity(svc):
    appr, token = _request(svc)
    assert appr["status"] == "pending" and appr["required_role"] == "vp_finance"
    assert "token_sha256" not in appr and "approval_token" not in appr and token not in str(appr)
    assert appr["approval_page"].endswith(f"/approvals/{appr['approval_id']}")
    assert svc.get_deal(AGENT, NW)["status"] == "awaiting_approval"
    out = svc.record_approval(DANA, appr["approval_id"], token, "approve", appr["terms_hash"], "ok")
    assert out["deal_status"] == "approved"
    deal = svc.get_deal(AGENT, NW)
    assert deal["approved_by"]["identity_id"] == "dana-vp-finance" and deal["approved_at"]
    assert deal["approved_terms_hash"] == terms_hash(F.northwind_counter())
    ts = svc.generate_term_sheet(AGENT, NW)
    text = "\n".join(p.text for p in Document(ts["path"]).paragraphs)
    assert ts["path"].endswith("DEAL-NW-001.docx") and "Fictional sample data" in text
    assert svc.update_crm(AGENT, NW, "signed", "countersigned")["status"] == "signed"


def test_approval_negative_paths(svc):
    appr, token = _request(svc)
    aid, h = appr["approval_id"], appr["terms_hash"]
    assert error_of(lambda: svc.record_approval(AGENT, aid, token, "approve", h)).code == "APPROVER_NOT_AUTHORIZED"
    assert error_of(lambda: svc.record_approval(DANA, aid, "wrong-token", "approve", h)).code == "INVALID_APPROVAL_TOKEN"
    assert error_of(lambda: svc.record_approval(DANA, aid, token, "approve", terms_hash(F.northwind_ask()))).code == "TERMS_MISMATCH"
    assert error_of(lambda: svc.record_approval(DANA, "APR-NOPE", token, "approve", h)).code == "APPROVAL_NOT_FOUND"
    svc.record_approval(DANA, aid, token, "approve", h)
    assert error_of(lambda: svc.record_approval(DANA, aid, token, "approve", h)).code == "APPROVAL_ALREADY_USED"


def test_approval_expires(svc, clock):
    appr, token = _request(svc)
    clock.now += timedelta(minutes=241)
    assert svc.get_approval(AGENT, appr["approval_id"])["status"] == "expired"
    e = error_of(lambda: svc.record_approval(DANA, appr["approval_id"], token, "approve", appr["terms_hash"]))
    assert e.code == "APPROVAL_EXPIRED" and e.http_status == 410


def test_vp_cannot_approve_cfo_level_terms(svc):
    appr, token = _request(svc, F.northwind_ask())
    assert appr["required_role"] == "cfo"
    assert error_of(lambda: svc.record_approval(DANA, appr["approval_id"], token, "approve", appr["terms_hash"])).code == "APPROVER_NOT_AUTHORIZED"
    assert svc.record_approval(MORGAN, appr["approval_id"], token, "approve", appr["terms_hash"])["deal_status"] == "approved"


def test_new_request_supersedes_pending(svc):
    first, token = _request(svc)
    second, _ = _request(svc)
    assert svc.get_approval(AGENT, first["approval_id"])["status"] == "superseded"
    assert error_of(lambda: svc.record_approval(DANA, first["approval_id"], token, "approve", first["terms_hash"])).code == "APPROVAL_ALREADY_USED"
    assert second["status"] == "pending"


def test_guards(svc):
    assert error_of(lambda: svc.request_approval(AGENT, RT, F.routine_ask(), "x")).code == "INVALID_STATE"
    assert error_of(lambda: svc.generate_term_sheet(AGENT, NW)).code == "INVALID_STATE"
    assert error_of(lambda: svc.update_crm(AGENT, NW, "signed")).code == "INVALID_STATE"
    assert error_of(lambda: svc.submit_decision(AGENT, NW, "approve", {"rebate_pct": 5})).code == "INVALID_TERMS"
    assert error_of(lambda: svc.get_deal(AGENT, "DEAL-NOPE")).code == "DEAL_NOT_FOUND"


def test_evaluate_deal_triage(svc):
    out = svc.evaluate_deal(AGENT, NW)
    assert out["ask"]["required_role"] == "cfo" and "recommended_counter" in out
