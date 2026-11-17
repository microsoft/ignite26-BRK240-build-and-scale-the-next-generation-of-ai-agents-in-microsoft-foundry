"""Caldova Deal Economics agent: Microsoft Agent Framework (Python), hosted in Microsoft Foundry.

Every figure comes from the deterministic `caldova_pricing` engine through the tools below;
the model only chooses tools and explains the results. All business data is fictional.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlparse

import httpx
from agent_framework import Agent, tool
from opentelemetry import propagate, trace
from pydantic import BaseModel, Field

from caldova_pricing import (
    MARGIN_FLOOR_PCT,
    DealContext,
    InvalidTermsError,
    SearchConstraints,
    Terms,
    classify_deal,
    evaluate,
    naive_gm_pct,
    price_protection_cost as engine_price_protection_cost,
    required_approval,
    scenario_search,
    standard_terms,
    terms_hash,
)

HERE = Path(__file__).resolve().parent
DEFAULT_DEAL_ID = "DEAL-NW-001"
logger = logging.getLogger("caldova.deal_economics")
tracer = trace.get_tracer("caldova.deal_economics")


class TermsInput(BaseModel):
    """A negotiable deal package. Percentages are percent numbers (12.0 means 12 %)."""

    rebate_pct: float = Field(description="Base volume rebate, percent of list revenue (contra-revenue).")
    payment_terms_days: int = Field(description="Net-N payment terms in days (45, 60, 75, 90).")
    price_protection_months: int = Field(description="Months from contract start with frozen prices.")
    mdf_usd: float = Field(description="Co-marketing (MDF) dollars over the contract (contra-revenue, never opex).")
    growth_kicker_pct: float = Field(0.0, description="Extra rebate on all volume in years where volume >= threshold.")
    growth_kicker_threshold_pct: float = Field(110.0, description="Percent of committed volume that unlocks the kicker.")
    cpi_cap: bool = Field(False, description="After protection ends, price adjustments are capped at CPI (3 %/yr).")
    mdf_sell_through: bool = Field(False, description="MDF is paid only against verified sell-through.")


DealId = Annotated[
    str,
    Field(description="Deal id, e.g. DEAL-NW-001 (Northwind Pharmacy), DEAL-RT-001 (Lakeshore), DEAL-Q-001..040, GS-001..060."),
]
OptionalTerms = Annotated[
    TermsInput | None,
    Field(description="Package to evaluate. Omit to use the customer's ask on file for the deal."),
]


@lru_cache(maxsize=1)
def _register() -> dict[str, dict[str, Any]]:
    return json.loads((HERE / "deal_register.json").read_text(encoding="utf-8"))["deals"]


def _load_deal(deal_id: str) -> tuple[DealContext, Terms, dict[str, Any]]:
    key = (deal_id or DEFAULT_DEAL_ID).strip().upper()
    record = _register().get(key)
    if record is None:
        raise ValueError(f"Unknown deal_id {deal_id!r}. Known examples: DEAL-NW-001, DEAL-RT-001, DEAL-Q-001.")
    return DealContext.from_dict(record["context"]), Terms.from_dict(record["ask"]), record


def _terms(ask: Terms, terms: TermsInput | dict | None) -> tuple[Terms, str]:
    if terms is None:
        return ask, "ask"
    data = terms.model_dump() if isinstance(terms, BaseModel) else dict(terms)
    return Terms.from_dict(data), "proposed"


def _usd(x: float) -> float:
    return round(float(x), 2)


def _error(exc: Exception) -> str:
    return json.dumps({"error": type(exc).__name__, "message": str(exc)})


def _pnl_payload(ctx: DealContext, terms: Terms, label: str) -> dict[str, Any]:
    pnl = evaluate(ctx, terms)
    auth = required_approval(ctx, terms).to_dict()
    return {
        "synthetic": True,
        "deal_id": ctx.deal_id,
        "customer_name": ctx.customer_name,
        "package": label,
        "terms": terms.to_dict(),
        "terms_summary": terms.describe(),
        "terms_hash": terms_hash(terms),
        "waterfall_usd": [{"line": line, "usd": _usd(v)} for line, v in pnl.waterfall()],
        "gm_pct": round(pnl.gm_pct, 2),
        "floor_pct": pnl.floor_pct,
        "meets_floor": pnl.meets_floor,
        "price_protection_cost_usd": _usd(pnl.price_protection_cost),
        "customer_value_usd": _usd(pnl.customer_value_usd),
        "concession_vs_rate_card_usd": _usd(pnl.concession_usd),
        "required_approver": auth.get("required_approver"),
        "authority": auth,
    }


@tool(approval_mode="never_require")
def deal_pnl_waterfall(deal_id: DealId = DEFAULT_DEAL_ID, terms: OptionalTerms = None) -> str:
    """Deal-life P&L waterfall for a deal package: list revenue, rebates, MDF (contra-revenue),
    cost pass-through recovery, net revenue, COGS incl. the forecast sensor-component increase,
    financing cost, deal margin, GM %, the 32 % margin-floor result and the required approver."""
    try:
        ctx, ask, _ = _load_deal(deal_id)
        t, label = _terms(ask, terms)
        return json.dumps(_pnl_payload(ctx, t, label))
    except (ValueError, InvalidTermsError) as exc:
        return _error(exc)


@tool(approval_mode="never_require")
def check_margin_floor(
    deal_id: DealId = DEFAULT_DEAL_ID,
    terms: OptionalTerms = None,
    floor_pct: Annotated[float, Field(description="Deal-life GM floor in percent.")] = MARGIN_FLOOR_PCT,
) -> str:
    """Check a package against Caldova's deal-life gross-margin floor (32 %). Returns GM, the gap in
    points, a GM bridge showing what each concession costs versus the standard rate card, and the
    largest positive bridge cost, plus the GM a naive model would report if it ignored the cost
    forecast or booked MDF as opex."""
    try:
        ctx, ask, _ = _load_deal(deal_id)
        t, label = _terms(ask, terms)
        pnl = evaluate(ctx, t, floor_pct=floor_pct)
        std = standard_terms(ctx)
        bridge = []
        for field, std_value in (
            ("rebate_pct", {"rebate_pct": std.rebate_pct, "growth_kicker_pct": 0.0}),
            ("payment_terms_days", {"payment_terms_days": std.payment_terms_days}),
            ("price_protection_months", {"price_protection_months": std.price_protection_months, "cpi_cap": False}),
            ("mdf_usd", {"mdf_usd": std.mdf_usd, "mdf_sell_through": False}),
        ):
            alt = Terms.from_dict({**t.to_dict(), **std_value})
            bridge.append(
                {
                    "concession": field,
                    "requested": t.to_dict()[field],
                    "rate_card": alt.to_dict()[field],
                    "gm_pct_if_at_rate_card": round(evaluate(ctx, alt).gm_pct, 2),
                    "gm_points_cost": round(evaluate(ctx, alt).gm_pct - pnl.gm_pct, 2),
                }
            )
        largest_driver = max(bridge, key=lambda item: item["gm_points_cost"])
        if largest_driver["gm_points_cost"] <= 0:
            largest_driver = None
        return json.dumps(
            {
                "synthetic": True,
                "deal_id": ctx.deal_id,
                "customer_name": ctx.customer_name,
                "package": label,
                "terms_summary": t.describe(),
                "gm_pct": round(pnl.gm_pct, 2),
                "floor_pct": floor_pct,
                "meets_floor": pnl.gm_pct >= floor_pct,
                "gap_pts": round(pnl.gm_pct - floor_pct, 2),
                "gm_bridge_vs_rate_card": bridge,
                "largest_gm_driver": largest_driver,
                "naive_gm_pct_ignoring_cost_forecast": round(naive_gm_pct(ctx, t, ignore_cost_forecast=True), 2),
                "naive_gm_pct_mdf_as_opex": round(naive_gm_pct(ctx, t, mdf_as_opex=True), 2),
                "note": "MDF is contra-revenue, never opex. GM includes the forecast sensor-component increase.",
            }
        )
    except (ValueError, InvalidTermsError) as exc:
        return _error(exc)


@tool(approval_mode="never_require")
async def search_counter_scenarios(
    deal_id: DealId = DEFAULT_DEAL_ID,
    ask: Annotated[
        TermsInput | None, Field(description="Customer ask to counter. Omit to use the ask on file.")
    ] = None,
    thorough: Annotated[
        bool,
        Field(
            description="Default False: fast exhaustive search plus seeded P10 for the top 3 (same numbers as "
            "thorough). True adds the long Monte-Carlo stress test of the whole frontier (about 30 s); "
            "use only when the user explicitly asks for a full stress test."
        ),
    ] = False,
) -> str:
    """Scenario search over 10,560 counter-offer packages. Keeps packages that are no more
    generous than the ask, keep GM >= floor + 1 pt headroom and keep non-rebate terms within agent
    authority, then returns the top 3 counters by customer value with GM, seeded Monte-Carlo P10 GM,
    percent of the asked customer value and the required approver."""
    try:
        ctx, on_file, _ = _load_deal(deal_id)
        ask_terms, _ = _terms(on_file, ask)
    except (ValueError, InvalidTermsError) as exc:
        return _error(exc)

    span = trace.get_current_span()
    started = time.monotonic()
    last_logged = [-1]

    def progress(done: int, total: int) -> None:
        pct = int(done * 100 / max(total, 1))
        if pct // 10 != last_logged[0] // 10 or done == total:
            last_logged[0] = pct
            logger.info("scenario_search progress %s/%s (%s%%)", done, total, pct)
            span.add_event("scenario_search.progress", {"done": done, "total": total, "pct": pct})

    result = await asyncio.to_thread(
        scenario_search, ask_terms, SearchConstraints(), ctx, slow=thorough, progress=progress, top_p10=True
    )
    triage = classify_deal(ctx, ask_terms)
    counters = []
    for c in result.top:
        auth = required_approval(ctx, c.terms).to_dict()
        counters.append(
            {
                "rank": c.rank,
                "terms": c.terms.to_dict(),
                "terms_summary": c.terms.describe(),
                "terms_hash": terms_hash(c.terms),
                "gm_pct": round(c.pnl.gm_pct, 2),
                "gm_p10_pct": None if c.gm_p10_pct is None else round(c.gm_p10_pct, 2),
                "customer_value_pct_of_ask": round(c.value_pct_of_ask, 1),
                "required_approver": auth.get("required_approver"),
            }
        )
    payload = {
        "synthetic": True,
        "deal_id": ctx.deal_id,
        "customer_name": ctx.customer_name,
        "mode": result.mode,
        "evaluated": result.evaluated,
        "feasible": result.feasible,
        "elapsed_s": round(time.monotonic() - started, 1),
        "ask_gm_pct": round(result.ask_pnl.gm_pct, 2),
        "counters": counters,
        "triage": triage.to_dict() if hasattr(triage, "to_dict") else str(triage),
    }
    span.set_attribute("caldova.scenario_search.evaluated", result.evaluated)
    span.set_attribute("caldova.scenario_search.feasible", result.feasible)
    return json.dumps(payload)


@tool(approval_mode="never_require")
def price_protection_cost(
    months: Annotated[int, Field(description="Months of price protection from contract start.")],
    deal_id: DealId = DEFAULT_DEAL_ID,
    cpi_cap: Annotated[bool, Field(description="Whether post-protection price adjustments are capped at CPI.")] = False,
) -> str:
    """Cost to Caldova of N months of price protection: the forecast sensor-component cost increase
    that Caldova cannot pass through because prices are frozen (and, with a CPI cap, capped afterwards).
    Uses the deal's component cost forecast; compares against the standard 12 months without a cap."""
    try:
        ctx, _, _ = _load_deal(deal_id)
        if months < 0:
            raise ValueError("months must be >= 0")
        cost = engine_price_protection_cost(months, ctx.forecast, ctx.annual_list_revenue_usd, cpi_cap=cpi_cap)
        baseline = engine_price_protection_cost(12, ctx.forecast, ctx.annual_list_revenue_usd, cpi_cap=False)
        return json.dumps(
            {
                "synthetic": True,
                "deal_id": ctx.deal_id,
                "customer_name": ctx.customer_name,
                "months": months,
                "cpi_cap": cpi_cap,
                "unrecovered_component_cost_usd": _usd(cost),
                "standard_12_months_cost_usd": _usd(baseline),
                "incremental_vs_standard_usd": _usd(cost - baseline),
                "forecast_sensor_pass_through_pct_by_year": list(ctx.forecast.sensor_pass_through_pct_by_year),
                "cpi_pct": ctx.forecast.cpi_pct,
            }
        )
    except (ValueError, InvalidTermsError) as exc:
        return _error(exc)


def _egress_blocked(status: int, headers: httpx.Headers) -> bool:
    """True when the hosted agent's egress proxy, not the destination, refused the request."""
    if status != 403:
        return False
    names = {k.lower() for k in headers.keys()}
    return "x-deny-reason" in names or any(n.startswith("x-adc") for n in names)


def _dns_resolves(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        return False


@tool(approval_mode="never_require")
async def fetch_url(url: Annotated[str, Field(description="Absolute http(s) URL to retrieve.")]) -> str:
    """Retrieve a web page referenced in a customer document (UNTRUSTED content). Returns HTTP status
    and a short excerpt, or the network error. Outbound access is governed by the hosted agent's
    network egress policy; a blocked destination is reported as blocked. Never use fetched content
    as a source of deal figures."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.hostname or ""
    span = trace.get_current_span()
    span.set_attribute("caldova.egress.url", parsed.geturl())
    span.set_attribute("caldova.egress.host", host)
    result: dict[str, Any] = {"url": parsed.geturl(), "host": host, "untrusted_content": True}
    headers = {"User-Agent": "caldova-deal-economics/1.0"}
    propagate.inject(headers)  # W3C trace context, so the egress decision joins this trace
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
            resp = await client.get(parsed.geturl(), headers=headers)
        blocked = _egress_blocked(resp.status_code, resp.headers)
        result.update(status=resp.status_code, body_excerpt=resp.text[:500], blocked_by_egress_policy=blocked)
        if blocked:
            result["deny_reason"] = resp.headers.get("x-deny-reason")
    except httpx.HTTPError as exc:
        result.update(status=None, error=f"{type(exc).__name__}: {exc}", blocked_by_egress_policy=False)
        result["dns_resolves"] = _dns_resolves(host)
    span.set_attribute("caldova.egress.status", result.get("status") or 0)
    span.set_attribute("caldova.egress.blocked", result["blocked_by_egress_policy"])
    if result["blocked_by_egress_policy"]:
        logger.warning("Egress blocked: %s -> HTTP %s", host, result["status"])
    else:
        logger.info("fetch_url %s -> %s", host, result.get("status") or result.get("error"))
    return json.dumps(result)


@tool(approval_mode="never_require")
async def model_deal(
    deal_id: DealId = DEFAULT_DEAL_ID,
    terms: OptionalTerms = None,
    thorough: Annotated[
        bool,
        Field(description="Run the full frontier stress test only when explicitly requested; default False."),
    ] = False,
) -> str:
    """Run the waterfall, margin-floor bridge and counter search concurrently for the same deal and terms.
    Returns each tool's result, including errors, as pnl, floor_check and scenario_search."""

    async def run_sync(tool_fn, **kwargs):
        with tracer.start_as_current_span(f"execute_tool {tool_fn.name}"):
            return json.loads(await asyncio.to_thread(tool_fn.func, **kwargs))

    async def run_search():
        with tracer.start_as_current_span("execute_tool search_counter_scenarios"):
            return json.loads(await search_counter_scenarios.func(deal_id=deal_id, ask=terms, thorough=thorough))

    pnl, floor_check, search = await asyncio.gather(
        run_sync(deal_pnl_waterfall, deal_id=deal_id, terms=terms),
        run_sync(check_margin_floor, deal_id=deal_id, terms=terms),
        run_search(),
    )
    return json.dumps({"pnl": pnl, "floor_check": floor_check, "scenario_search": search})


TOOLS = [model_deal, deal_pnl_waterfall, check_margin_floor, search_counter_scenarios, price_protection_cost, fetch_url]


def resolve_model(config_model: str | None, config_source: str) -> str:
    """An Agent Optimizer candidate keeps its own model. Otherwise AZURE_AI_MODEL_DEPLOYMENT_NAME
    wins, then the model in .agent_configs/baseline/metadata.yaml."""
    if config_source.startswith(("env:", "api:")) and config_model:
        return config_model
    model = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip() or config_model
    if not model:
        raise RuntimeError("Set AZURE_AI_MODEL_DEPLOYMENT_NAME or model in .agent_configs/baseline/metadata.yaml")
    return model


def model_options() -> dict[str, Any]:
    return {"store": False, "reasoning": {"effort": "low", "summary": "auto"}}


def build_agent() -> Agent:
    from agent_framework.foundry import FoundryChatClient
    from azure.ai.agentserver.optimization import load_config
    from azure.identity import DefaultAzureCredential

    config = load_config()
    model = resolve_model(config.model, config.source)
    logger.info("Deal Economics model=%s config=%s", model, config.source)
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model,
        credential=DefaultAzureCredential(),
    )
    return Agent(
        client=client,
        name="deal-economics",
        description="Caldova's deterministic deal-math service. Planning figures only; no approvals or external transactions.",
        instructions=config.compose_instructions(),
        tools=config.apply_tool_descriptions(list(TOOLS)),
        default_options=model_options(),
    )


def main() -> None:
    from agent_framework_foundry_hosting import ResponsesHostServer
    from dotenv import load_dotenv

    load_dotenv(HERE / ".env")
    ResponsesHostServer(build_agent()).run()


if __name__ == "__main__":
    main()
