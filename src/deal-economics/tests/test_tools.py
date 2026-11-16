"""Deterministic tool tests for the Deal Economics agent (no model calls). All data is fictional."""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest
import yaml
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import agent  # noqa: E402
import sync_vendor  # noqa: E402


def call(tool, **kwargs):
    out = tool.func(**kwargs) if hasattr(tool, "func") else tool(**kwargs)
    if asyncio.iscoroutine(out):
        out = asyncio.run(out)
    return json.loads(out)


def test_eval_manifest_uses_available_local_inputs():
    manifest = yaml.safe_load((HERE / "eval.yaml").read_text(encoding="utf-8"))
    datasets = {entry["name"] for entry in manifest["datasets"]}
    assert all((HERE / entry["file"]).is_file() for entry in manifest["datasets"])
    assert all(evaluation["dataset"] in datasets for evaluation in manifest["evals"])
    assert all((HERE / entry["source"]).is_file() for entry in manifest.get("evaluators", []))


def test_northwind_ask_waterfall_below_floor():
    r = call(agent.deal_pnl_waterfall, deal_id="DEAL-NW-001")
    assert r["package"] == "ask"
    assert r["gm_pct"] == pytest.approx(26.4, abs=0.5)
    assert r["meets_floor"] is False
    assert r["waterfall_usd"][0]["usd"] == pytest.approx(48_000_000)
    assert r["synthetic"] is True


def test_margin_floor_bridge_and_naive_views():
    r = call(agent.check_margin_floor, deal_id="DEAL-NW-001")
    assert r["meets_floor"] is False
    assert r["gap_pts"] < -5
    assert {b["concession"] for b in r["gm_bridge_vs_rate_card"]} == {
        "rebate_pct", "payment_terms_days", "price_protection_months", "mdf_usd"
    }
    assert r["largest_gm_driver"]["concession"] == "rebate_pct"
    assert r["largest_gm_driver"]["gm_points_cost"] == pytest.approx(8.04)
    assert r["naive_gm_pct_ignoring_cost_forecast"] > r["gm_pct"]


def test_largest_driver_tracks_terms_and_handles_no_concession_cost():
    ctx, _, _ = agent._load_deal("DEAL-NW-001")
    standard = agent.standard_terms(ctx).to_dict()
    at_rate_card = call(agent.check_margin_floor, terms=agent.TermsInput(**standard))
    assert at_rate_card["largest_gm_driver"] is None

    longer_protection = agent.TermsInput(**{**standard, "price_protection_months": 24})
    result = call(agent.check_margin_floor, terms=longer_protection)
    assert result["largest_gm_driver"]["concession"] == "price_protection_months"
    assert result["largest_gm_driver"]["gm_points_cost"] > 0


def test_recommended_counter_terms_meet_floor():
    counter = {
        "rebate_pct": 12.0, "growth_kicker_pct": 2.0, "payment_terms_days": 60,
        "price_protection_months": 12, "cpi_cap": True, "mdf_usd": 900_000, "mdf_sell_through": True,
    }
    r = call(agent.deal_pnl_waterfall, deal_id="DEAL-NW-001", terms=agent.TermsInput(**counter))
    assert r["package"] == "proposed"
    assert r["gm_pct"] == pytest.approx(33.07, abs=0.5)
    assert r["meets_floor"] is True


def test_scenario_search_default_is_fast_with_top_p10():
    r = call(agent.search_counter_scenarios, deal_id="DEAL-NW-001")
    assert r["mode"] == "fast+p10"
    assert len(r["counters"]) == 3
    assert r["evaluated"] > 0
    assert all(c["gm_pct"] >= 33.0 and c["gm_p10_pct"] is not None for c in r["counters"])
    assert r["counters"][0]["gm_pct"] == pytest.approx(33.07, abs=0.01)
    assert r["counters"][0]["gm_p10_pct"] == pytest.approx(31.7, abs=0.05)
    assert r["elapsed_s"] < 5


def test_model_deal_uses_all_three_results():
    result = call(agent.model_deal, deal_id="DEAL-NW-001")
    assert result["pnl"]["gm_pct"] == pytest.approx(26.4, abs=0.01)
    assert result["floor_check"]["largest_gm_driver"]["concession"] == "rebate_pct"
    assert result["scenario_search"]["counters"][0]["gm_p10_pct"] == pytest.approx(31.7, abs=0.05)

    errors = call(agent.model_deal, deal_id="DEAL-NOPE")
    assert all(result["error"] == "ValueError" for result in errors.values())


def test_model_deal_runs_calculations_concurrently(monkeypatch):
    barrier = threading.Barrier(3, timeout=3)
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    def sync_tool(**kwargs):
        barrier.wait()
        return "{}"

    async def search_tool(**kwargs):
        await asyncio.to_thread(barrier.wait)
        return "{}"

    monkeypatch.setattr(agent.deal_pnl_waterfall, "func", sync_tool)
    monkeypatch.setattr(agent.check_margin_floor, "func", sync_tool)
    monkeypatch.setattr(agent.search_counter_scenarios, "func", search_tool)
    monkeypatch.setattr(agent, "tracer", tracer)
    with tracer.start_as_current_span("parent") as parent:
        assert call(agent.model_deal) == {"pnl": {}, "floor_check": {}, "scenario_search": {}}
        parent_id = parent.get_span_context().span_id
    children = [span for span in exporter.get_finished_spans() if span.name != "parent"]
    assert {span.name for span in children} == {
        "execute_tool deal_pnl_waterfall", "execute_tool check_margin_floor", "execute_tool search_counter_scenarios"
    }
    assert all(span.parent.span_id == parent_id for span in children)
    provider.shutdown()


def test_model_deal_passes_proposed_terms_and_thorough(monkeypatch):
    seen = {}

    def pnl(**kwargs):
        seen["pnl"] = kwargs
        return "{}"

    def floor(**kwargs):
        seen["floor"] = kwargs
        return "{}"

    async def search(**kwargs):
        seen["search"] = kwargs
        return "{}"

    monkeypatch.setattr(agent.deal_pnl_waterfall, "func", pnl)
    monkeypatch.setattr(agent.check_margin_floor, "func", floor)
    monkeypatch.setattr(agent.search_counter_scenarios, "func", search)
    ctx, _, _ = agent._load_deal("DEAL-NW-001")
    terms = agent.TermsInput(**agent.standard_terms(ctx).to_dict())
    call(agent.model_deal, deal_id="DEAL-NW-001", terms=terms, thorough=True)
    assert seen["pnl"] == seen["floor"] == {"deal_id": "DEAL-NW-001", "terms": terms}
    assert seen["search"] == {"deal_id": "DEAL-NW-001", "ask": terms, "thorough": True}


def test_model_options_use_low_reasoning_effort():
    assert agent.model_options() == {"store": False, "reasoning": {"effort": "low", "summary": "auto"}}


def test_price_protection_cost_grows_with_months():
    m12 = call(agent.price_protection_cost, months=12)
    m24 = call(agent.price_protection_cost, months=24)
    assert m24["unrecovered_component_cost_usd"] > m12["unrecovered_component_cost_usd"]
    assert m24["incremental_vs_standard_usd"] > 0


def test_unknown_deal_is_an_error_not_a_number():
    r = call(agent.deal_pnl_waterfall, deal_id="DEAL-NOPE")
    assert r["error"] == "ValueError"


def test_resolve_model_precedence(monkeypatch):
    monkeypatch.setenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "my-deployment")
    assert agent.resolve_model("gpt-5.5", "local:x") == "my-deployment"
    assert agent.resolve_model("gpt-5.4-mini", "env:OPTIMIZATION_CONFIG") == "gpt-5.4-mini"
    monkeypatch.delenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    assert agent.resolve_model("gpt-5.5", "local:x") == "gpt-5.5"
    with pytest.raises(RuntimeError):
        agent.resolve_model(None, "local:x")


def test_egress_block_detection():
    import httpx

    assert agent._egress_blocked(403, httpx.Headers({"x-deny-reason": "example.com:GET"})) is True
    assert agent._egress_blocked(403, httpx.Headers({"X-Adc-Proxy": "1"})) is True
    assert agent._egress_blocked(403, httpx.Headers({"content-type": "text/html"})) is False
    assert agent._egress_blocked(200, httpx.Headers({"x-deny-reason": "x"})) is False


def test_baseline_config_loads():
    from azure.ai.agentserver.optimization import load_config

    cfg = load_config(config_dir=str(HERE / ".agent_configs"))
    assert cfg.model == "gpt-5.5"
    assert "deterministic deal-math service" in cfg.compose_instructions()
    names = {t["function"]["name"] for t in cfg.tool_definitions}
    assert names == {t.name for t in agent.TOOLS}


def test_vendored_copies_match_sources():
    assert sync_vendor.drift() == [], "run: python sync_vendor.py"
