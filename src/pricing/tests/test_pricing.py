from dataclasses import replace

import pytest

from caldova_pricing import (
    CostForecast,
    InvalidTermsError,
    SearchConstraints,
    Terms,
    can_approve,
    check_margin_floor,
    classify_deal,
    evaluate,
    grid_size,
    naive_gm_pct,
    price_protection_cost,
    required_approval,
    scenario_search,
    standard_terms,
    terms_hash,
)
from caldova_pricing import fixtures as F
from caldova_pricing.engine import rebate_cost


@pytest.fixture
def nw():
    return F.northwind_context()


def test_northwind_ask_gm_is_26_4(nw):
    pnl = evaluate(nw, F.northwind_ask())
    assert pnl.list_revenue == pytest.approx(48_000_000)
    assert pnl.gm_pct == pytest.approx(26.4, abs=0.5)
    assert not check_margin_floor(pnl)


def test_northwind_counter_gm_is_33_and_85pct_value(nw):
    ask = evaluate(nw, F.northwind_ask())
    ctr = evaluate(nw, F.northwind_counter())
    assert ctr.gm_pct == pytest.approx(33.0, abs=0.5)
    assert check_margin_floor(ctr)
    assert ctr.customer_value_usd / ask.customer_value_usd * 100 == pytest.approx(85.0, abs=0.5)


def test_kicker_summary_matches_inclusive_threshold(nw):
    terms = F.northwind_counter()
    at_threshold = replace(nw, annual_list_revenue_usd=(110.0,), annual_commit_usd=(100.0,))
    below_threshold = replace(at_threshold, annual_list_revenue_usd=(109.0,))
    assert "at or above 110% of commit" in terms.describe()
    assert rebate_cost(at_threshold, terms) == pytest.approx(110.0 * 0.14)
    assert rebate_cost(below_threshold, terms) == pytest.approx(109.0 * 0.12)


def test_waterfall_lines_reconcile(nw):
    pnl = evaluate(nw, F.northwind_ask())
    assert pnl.net_revenue == pytest.approx(pnl.list_revenue - pnl.rebates - pnl.mdf + pnl.pass_through_recovery)
    assert pnl.deal_margin == pytest.approx(pnl.net_revenue - pnl.cogs - pnl.financing_cost)
    assert pnl.price_protection_cost == pytest.approx(pnl.sensor_cost_increase - pnl.pass_through_recovery)


def test_price_protection_beyond_cost_increase_costs_money():
    f = CostForecast((0.0, 5.0, 5.5))
    rev = (14_400_000, 16_000_000, 17_600_000)
    assert price_protection_cost(12, f, rev) == pytest.approx(0.0)
    assert price_protection_cost(24, f, rev) == pytest.approx(0.05 * 16_000_000)
    # CPI cap after protection: year 2 capped at 3 %, year 3 at 6.09 % (> 5.5 % planned)
    assert price_protection_cost(12, f, rev, cpi_cap=True) == pytest.approx(0.02 * 16_000_000)
    assert price_protection_cost(18, f, rev) == pytest.approx(0.05 * 16_000_000 / 2)
    with pytest.raises(ValueError):
        price_protection_cost(-1, f, rev)


def test_rebate_alone_looks_survivable_if_you_ignore_the_cost_forecast(nw):
    rebate_only = Terms(rebate_pct=18, payment_terms_days=45, price_protection_months=12, mdf_usd=480_000)
    assert naive_gm_pct(nw, rebate_only, ignore_cost_forecast=True) > evaluate(nw, rebate_only).gm_pct


def test_mdf_as_opex_overstates_gm(nw):
    t = F.northwind_ask()
    assert naive_gm_pct(nw, t, mdf_as_opex=True) > evaluate(nw, t).gm_pct


def test_scenario_search_returns_recommended_counter_first(nw):
    res = scenario_search(F.northwind_ask(), SearchConstraints(), nw)
    assert res.evaluated == grid_size(nw) >= 5000
    assert len(res.top) == 3
    assert res.top[0].terms == F.northwind_counter()
    for c in res.top:
        assert c.pnl.gm_pct >= 32.0
        assert c.pnl.gm_pct == pytest.approx(evaluate(nw, c.terms).gm_pct)
    assert [c.value_pct_of_ask for c in res.top] == sorted([c.value_pct_of_ask for c in res.top], reverse=True)


def test_scenario_search_is_deterministic_and_reports_progress(nw):
    seen = []
    a = scenario_search(F.northwind_ask(), SearchConstraints(), nw, progress=lambda d, t: seen.append((d, t)))
    b = scenario_search(F.northwind_ask(), SearchConstraints(), nw)
    assert [c.terms for c in a.top] == [c.terms for c in b.top]
    assert seen and seen[-1][0] == seen[-1][1]


def test_slow_mode_adds_risk_pass(nw):
    res = scenario_search(F.northwind_ask(), SearchConstraints(), nw, slow=True, mc_draws=50)
    assert res.mode == "slow"
    assert all(c.gm_p10_pct is not None and c.gm_p10_pct < c.pnl.gm_pct + 5 for c in res.top)


def test_fast_top_p10_matches_slow_mode(nw):
    fast = scenario_search(F.northwind_ask(), SearchConstraints(), nw, top_p10=True, mc_draws=300)
    slow = scenario_search(F.northwind_ask(), SearchConstraints(), nw, slow=True, mc_draws=300)
    assert fast.mode == "fast+p10"
    assert [c.terms for c in fast.top] == [c.terms for c in slow.top]
    assert [c.gm_p10_pct for c in fast.top] == [c.gm_p10_pct for c in slow.top]
    assert all(c.gm_p10_pct is not None for c in fast.top)
    assert all(c.gm_p10_pct is None for c in scenario_search(F.northwind_ask(), SearchConstraints(), nw).top)


def test_authority_matrix(nw):
    assert required_approval(nw, F.northwind_ask()).required_role == "cfo"
    ctr = required_approval(nw, F.northwind_counter())
    assert ctr.required_role == "vp_finance"
    assert [e.field for e in ctr.exceeded] == ["effective_rebate_pct"]
    assert ctr.exceeded[0].requested == 14.0
    rt = required_approval(F.routine_context(), F.routine_ask())
    assert rt.required_role == "agent" and rt.gm_pct >= 32
    assert can_approve("vp_finance", "vp_finance") and can_approve("cfo", "vp_finance")
    assert not can_approve("agent", "vp_finance") and not can_approve("seller", "agent")


def test_classification(nw):
    assert classify_deal(F.routine_context(), F.routine_ask()).outcome == "auto_approve"
    c = classify_deal(nw, F.northwind_ask())
    assert c.outcome == "escalate" and c.required_role == "vp_finance"
    assert c.counter_terms == F.northwind_counter()


def test_standard_terms_within_authority(nw):
    assert required_approval(nw, standard_terms(nw)).required_role == "agent"


def test_terms_hash_is_canonical():
    a = F.northwind_counter()
    b = Terms.from_dict({**a.to_dict(), "rebate_pct": 12, "mdf_usd": "900000"})
    assert terms_hash(a) == terms_hash(b) == terms_hash(a.to_dict())
    assert terms_hash(a) != terms_hash(F.northwind_ask())


def test_invalid_terms_rejected():
    with pytest.raises(InvalidTermsError):
        Terms.from_dict({"rebate_pct": 12})
    with pytest.raises(InvalidTermsError):
        Terms.from_dict({**F.northwind_ask().to_dict(), "approve": True})
    with pytest.raises(InvalidTermsError):
        Terms(rebate_pct=-1, payment_terms_days=45, price_protection_months=12, mdf_usd=0)
