import asyncio
import re
import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from caldova_pricing import fixtures as F
from caldova_deal_system.app import create_app
from caldova_deal_system.config import Settings

NW, RT = F.NORTHWIND_DEAL_ID, F.ROUTINE_DEAL_ID
KEY = "test-key-123"
LOCAL = {"base_url": "http://localhost:8080", "client": ("127.0.0.1", 50000)}


@pytest.fixture
def local(settings):
    with TestClient(create_app(settings), **LOCAL) as c:
        yield c


@pytest.fixture
def keyed(tmp_path):
    with TestClient(create_app(Settings(state_dir=tmp_path / "state", api_key=KEY)), **LOCAL) as c:
        yield c


def test_rest_enforces_authority(local):
    r = local.post(f"/api/deals/{NW}/decision", json={"decision": "approve", "terms": F.northwind_ask().to_dict()})
    assert r.status_code == 403 and r.json()["error"]["code"] == "REQUIRES_HUMAN_APPROVAL"
    assert r.json()["error"]["required_approver_role"] == "cfo"
    r = local.post(f"/api/deals/{RT}/decision", json={"decision": "approve", "terms": F.routine_ask().to_dict()})
    assert r.status_code == 200 and r.json()["status"] == "auto_approved"
    assert local.get("/openapi.json").status_code == 404


def test_without_key_api_only_answers_direct_local_requests(local):
    assert local.get(f"/api/deals/{NW}", headers={"Host": "evil.example:8080"}).status_code == 403
    assert local.get(f"/api/deals/{NW}", headers={"X-Forwarded-For": "203.0.113.7"}).status_code == 403
    assert local.post("/mcp", headers={"Host": "evil.example"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 403
    assert local.get(f"/api/deals/{NW}", headers={"Host": "127.0.0.1:8080"}).status_code == 200


def test_api_key_guards_api_and_mcp_but_not_health(keyed):
    h = keyed.get("/health")
    assert h.status_code == 200 and h.json()["api_key_required"] is True and h.json()["deals"] == 42
    assert keyed.get(f"/api/deals/{NW}").status_code == 401
    assert keyed.get(f"/api/deals/{NW}", headers={"x-api-key": "wrong"}).status_code == 401
    assert keyed.get(f"/api/deals/{NW}", headers={"x-api-key": KEY}).status_code == 200
    r = keyed.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "UNAUTHENTICATED"
    assert "No API key set" not in keyed.get("/").text


@pytest.mark.parametrize("kwargs", [
    {"headers": {"X-Forwarded-For": "203.0.113.7"}},
    {"headers": {"X-Forwarded-Host": "example.devtunnels.ms"}},
    {"headers": {"Forwarded": "for=203.0.113.7"}},
    {"headers": {"Host": "evil.example"}},
])
def test_html_pages_are_local_only(local, kwargs):
    for path in ("/", "/approvals/APR-ANY", f"/term-sheets/{NW}"):
        assert local.get(path, **kwargs).status_code == 404
    assert local.post("/approvals/APR-ANY", content=b"x=1", **kwargs).status_code == 404


def test_html_pages_refuse_remote_clients(settings):
    with TestClient(create_app(settings), base_url="http://localhost:8080", client=("203.0.113.7", 50000)) as c:
        assert c.get("/").status_code == 404
        assert c.get("/health").status_code == 200


def test_browser_approval_flow(local):
    assert "No API key set" in local.get("/").text
    body = {"terms": F.northwind_counter().to_dict(), "rationale": "counter", "alternatives": ["13% + 2% kicker"]}
    appr = local.post(f"/api/deals/{NW}/approval-requests", json=body).json()
    aid = appr["approval_id"]
    assert appr["status"] == "pending" and "approval_token" not in appr
    assert f"/approvals/{aid}" in local.get("/").text
    page = local.get(f"/approvals/{aid}").text
    assert "Dana (VP Finance)" in page and "13% + 2% kicker" in page
    token = re.search(r"name='approval_token' value='([^']+)'", page).group(1)
    assert token not in local.get(f"/api/approvals/{aid}").text and token not in local.get(f"/api/deals/{NW}").text
    form = {"approval_token": token, "terms_hash": appr["terms_hash"], "approver": "dana-vp-finance", "decision": "approve"}
    r = local.post(f"/approvals/{aid}", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/approvals/{aid}"
    assert local.get(f"/api/approvals/{aid}").json()["status"] == "approved"
    deal = local.get(f"/api/deals/{NW}").json()
    assert deal["status"] == "approved" and deal["approved_by"]["display"] == "Dana (VP Finance)"
    assert local.post(f"/approvals/{aid}", data=form).status_code == 409
    ts = local.post(f"/api/deals/{NW}/term-sheet").json()
    assert ts["download_url"].endswith(f"/term-sheets/{NW}")
    assert local.get(f"/term-sheets/{NW}").status_code == 200


def test_cfo_level_request_offers_only_morgan(local):
    appr = local.post(f"/api/deals/{NW}/approval-requests", json={"terms": F.northwind_ask().to_dict(), "rationale": "ask"}).json()
    page = local.get(f"/approvals/{appr['approval_id']}").text
    assert "Morgan (CFO)" in page and "<option value='dana-vp-finance'" not in page
    token = re.search(r"name='approval_token' value='([^']+)'", page).group(1)
    form = {"approval_token": token, "terms_hash": appr["terms_hash"], "approver": "dana-vp-finance", "decision": "approve"}
    assert local.post(f"/approvals/{appr['approval_id']}", data=form).status_code == 403


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_mcp_over_streamable_http(tmp_path):
    import httpx2
    from mcp import Client
    from mcp.client.streamable_http import streamable_http_client
    from mcp.shared._httpx_utils import create_mcp_http_client

    port = _free_port()
    settings = Settings(state_dir=tmp_path / "state", api_key=KEY, port=port)
    server = uvicorn.Server(uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)

    async def calls():
        http = create_mcp_http_client(headers={"x-api-key": KEY}, timeout=httpx2.Timeout(30))
        async with http, Client(streamable_http_client(f"http://127.0.0.1:{port}/mcp", http_client=http), mode="legacy") as c:
            names = {t.name for t in (await c.list_tools()).tools}
            deal = await c.call_tool("get_deal", {"deal_id": NW})
            denied = await c.call_tool("submit_decision", {"deal_id": NW, "decision": "approve", "terms": F.northwind_ask().to_dict()})
            appr = await c.call_tool("request_approval", {"deal_id": NW, "terms": F.northwind_ask().to_dict(), "rationale": "ask"})
            return names, deal, denied, appr

    try:
        names, deal, denied, appr = asyncio.run(calls())
    finally:
        server.should_exit = True
        thread.join(5)
    assert {"get_deal", "list_queue", "submit_decision", "request_approval", "get_approval", "record_approval",
            "update_crm", "generate_term_sheet", "evaluate_deal"} <= names
    assert deal.structured_content["deal_id"] == NW
    assert denied.is_error and denied.structured_content["error"]["code"] == "REQUIRES_HUMAN_APPROVAL"
    assert appr.structured_content["status"] == "pending" and "approval_token" not in str(appr.structured_content)
