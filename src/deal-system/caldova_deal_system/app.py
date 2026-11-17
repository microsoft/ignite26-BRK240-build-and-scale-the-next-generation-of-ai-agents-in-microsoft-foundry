"""FastAPI app: REST API, MCP (streamable HTTP at /mcp), local dashboard and approval pages, health."""

from __future__ import annotations

import hmac
import urllib.parse
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp, Receive, Scope, Send

from caldova_pricing import can_approve

from .config import Settings
from .errors import DealSystemError, forbidden, invalid_state, unauthenticated
from .identities import AGENT, APPROVERS
from .mcp_server import build_mcp
from .pages import render_approval_page, render_dashboard, render_message
from .service import DealService

LOOPBACK_CLIENTS = {"127.0.0.1", "::1"}
LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}
PROXY_HEADERS = (b"x-forwarded-for", b"x-forwarded-host", b"forwarded")


def is_direct_local(scope: Scope) -> bool:
    """A client on this machine talking to the server directly: loopback client, a localhost Host header, and no
    proxy (dev tunnel) forwarding headers."""
    client = (scope.get("client") or ("", 0))[0]
    headers = dict(scope["headers"])
    if client not in LOOPBACK_CLIENTS or any(h in headers for h in PROXY_HEADERS):
        return False
    host = headers.get(b"host", b"").decode("latin-1")
    return (urllib.parse.urlsplit(f"//{host}").hostname or "") in LOCAL_HOSTNAMES


class ApiGuard:
    """Guards /mcp and /api/*. With an API key set, a matching x-api-key header is required. Without one the API is
    unauthenticated, so it only answers direct local requests (never a tunnel, proxy or DNS-rebinding web page)."""

    def __init__(self, app: ASGIApp, api_key: str | None) -> None:
        self.app = app
        self.api_key = api_key.encode("utf-8") if api_key else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].split("/")[1] in ("mcp", "api"):
            error = None
            if self.api_key is not None:
                if not hmac.compare_digest(dict(scope["headers"]).get(b"x-api-key", b""), self.api_key):
                    error = unauthenticated()
            elif not is_direct_local(scope):
                error = forbidden("DEAL_SYSTEM_API_KEY is not set, so the API only answers direct local requests.")
            if error is not None:
                await JSONResponse(error.to_dict(), status_code=error.http_status)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    service = DealService(settings)
    mcp = build_mcp(service)
    # ApiGuard does the API key and local-only checks for /mcp, so the SDK's own Host allow-list is off.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True, transport_security=security)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="Caldova Deal System", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    app.state.settings = settings
    app.router.routes.extend(mcp_app.routes)
    app.add_middleware(ApiGuard, api_key=settings.api_key)

    @app.exception_handler(DealSystemError)
    async def _err(_: Request, exc: DealSystemError) -> JSONResponse:
        return JSONResponse(exc.to_dict(), status_code=exc.http_status)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "caldova-deal-system", "deals": len(service.list_deals()), "mcp_path": "/mcp",
                "api_key_required": bool(settings.api_key)}

    # ------------------------------------------------------------- REST API (acts as the Deal Desk agent)
    @app.get("/api/deals")
    def list_deals(status: str | None = None, limit: int = 50) -> dict[str, Any]:
        return service.list_queue(AGENT, status, limit)

    @app.get("/api/deals/{deal_id}")
    def get_deal(deal_id: str) -> dict[str, Any]:
        return service.get_deal(AGENT, deal_id)

    @app.post("/api/deals/{deal_id}/decision")
    def decision(deal_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.submit_decision(AGENT, deal_id, body.get("decision", ""), body.get("terms"), body.get("rationale", ""))

    @app.post("/api/deals/{deal_id}/approval-requests")
    def approval_request(deal_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.request_approval(AGENT, deal_id, body.get("terms"), body.get("rationale", ""), body.get("summary"),
                                        body.get("alternatives"))

    @app.get("/api/approvals/{approval_id}")
    def get_approval(approval_id: str) -> dict[str, Any]:
        return service.get_approval(AGENT, approval_id)

    @app.post("/api/deals/{deal_id}/crm")
    def crm(deal_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.update_crm(AGENT, deal_id, body.get("stage", ""), body.get("note", ""))

    @app.post("/api/deals/{deal_id}/term-sheet")
    def make_term_sheet(deal_id: str) -> dict[str, Any]:
        return service.generate_term_sheet(AGENT, deal_id)

    @app.get("/api/deals/{deal_id}/term-sheet", response_model=None)
    def download_term_sheet(deal_id: str) -> FileResponse:
        return term_sheet_file(deal_id)

    def term_sheet_file(deal_id: str) -> FileResponse:
        service.get_deal(AGENT, deal_id)
        path = service.term_sheet_path(deal_id)
        if not path.exists():
            raise invalid_state("term sheet not generated yet", deal_id=deal_id)
        return FileResponse(path, filename=f"{deal_id}-term-sheet.docx")

    # ------------------------------------------------------------- local-only pages (the human approvers)
    def local_only() -> Response:
        return PlainTextResponse("Not found", status_code=404)

    @app.get("/", response_class=HTMLResponse, response_model=None)
    def dashboard(request: Request) -> Response:
        if not is_direct_local(request.scope):
            return local_only()
        return HTMLResponse(render_dashboard(service.list_deals(), service.list_approvals(), api_key_required=bool(settings.api_key)))

    @app.get("/approvals/{approval_id}", response_class=HTMLResponse, response_model=None)
    def approval_page(approval_id: str, request: Request) -> Response:
        if not is_direct_local(request.scope):
            return local_only()
        try:
            approval = service.get_approval(AGENT, approval_id)
            deal = service.get_deal(AGENT, approval["deal_id"])
        except DealSystemError as exc:
            return HTMLResponse(render_message("Approval unavailable", exc.message), status_code=exc.http_status)
        approvers = [i for i in APPROVERS.values() if can_approve(i.role, approval["required_role"])]
        return HTMLResponse(render_approval_page(approval, deal, approvers, service.inbox_token(approval_id)))

    @app.post("/approvals/{approval_id}", response_model=None)
    async def approval_submit(approval_id: str, request: Request) -> Response:
        if not is_direct_local(request.scope):
            return local_only()
        form = {k: v[0] for k, v in urllib.parse.parse_qs((await request.body()).decode("utf-8")).items()}
        approver = APPROVERS.get(form.get("approver", ""))
        if approver is None:
            return HTMLResponse(render_message("Unknown approver", "Choose Dana (VP Finance) or Morgan (CFO)."), status_code=422)
        try:
            service.record_approval(approver, approval_id, form.get("approval_token", ""), form.get("decision", ""),
                                    form.get("terms_hash", ""), form.get("comment") or None)
        except DealSystemError as exc:
            return HTMLResponse(render_message(exc.code, exc.message, back=f"/approvals/{approval_id}"), status_code=exc.http_status)
        return RedirectResponse(f"/approvals/{approval_id}", status_code=303)

    @app.get("/term-sheets/{deal_id}", response_model=None)
    def term_sheet_page(deal_id: str, request: Request) -> Response:
        if not is_direct_local(request.scope):
            return local_only()
        return term_sheet_file(deal_id)

    return app
