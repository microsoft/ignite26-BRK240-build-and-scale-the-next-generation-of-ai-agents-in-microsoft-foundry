"""Deterministic deal economics: P&L waterfall, margin floor, price-protection cost.

Fictional sample model. See src/pricing/README.md for the definitions."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CostForecast, DealContext, PnL, Terms

MARGIN_FLOOR_PCT = 32.0
STANDARD_REBATE_PCT = 8.0
STANDARD_PAYMENT_TERMS_DAYS = 45
STANDARD_PRICE_PROTECTION_MONTHS = 12
STANDARD_MDF_PCT_OF_TCV = 1.0


def standard_terms(ctx: DealContext) -> Terms:
    """Caldova rate card: 8 % rebate, Net-45, 12-month protection, MDF 1 % of TCV."""
    return Terms(
        rebate_pct=STANDARD_REBATE_PCT,
        payment_terms_days=STANDARD_PAYMENT_TERMS_DAYS,
        price_protection_months=STANDARD_PRICE_PROTECTION_MONTHS,
        mdf_usd=round(ctx.tcv_usd * STANDARD_MDF_PCT_OF_TCV / 100, 2),
    )


@dataclass(frozen=True)
class ProtectionEffect:
    sensor_cost_increase: float
    recovery: float

    @property
    def forgone(self) -> float:
        return self.sensor_cost_increase - self.recovery


def _protection_effect(
    months: int, cpi_cap: bool, forecast: CostForecast, annual_list_revenue_usd: tuple[float, ...]
) -> ProtectionEffect:
    increase = 0.0
    recovery = 0.0
    for year_index, annual in enumerate(annual_list_revenue_usd):
        monthly = annual / 12.0
        planned = forecast.pass_through_pct(year_index)
        cap = forecast.cpi_cum_pct(year_index)
        for m in range(12):
            month_no = year_index * 12 + m + 1
            increase += monthly * planned / 100
            if month_no <= months:
                allowed = 0.0
            elif cpi_cap:
                allowed = min(planned, cap)
            else:
                allowed = planned
            recovery += monthly * allowed / 100
    return ProtectionEffect(sensor_cost_increase=increase, recovery=recovery)


def price_protection_cost(
    months: int,
    forecast: CostForecast,
    annual_list_revenue_usd: tuple[float, ...] | list[float],
    *,
    cpi_cap: bool = False,
) -> float:
    """USD of forecast sensor-component cost increase Caldova cannot pass through because
    prices are frozen for `months` (and, with `cpi_cap`, capped at CPI afterwards).

    Zero when protection ends before the cost increase lands (month 13) and there is no cap."""
    if months < 0:
        raise ValueError("months must be >= 0")
    return _protection_effect(months, cpi_cap, forecast, tuple(annual_list_revenue_usd)).forgone


def _kicker_earned(revenue: float, commit: float, threshold_pct: float) -> bool:
    return commit > 0 and revenue >= commit * threshold_pct / 100


def rebate_cost(ctx: DealContext, terms: Terms) -> float:
    total = 0.0
    for revenue, commit in zip(ctx.annual_list_revenue_usd, ctx.annual_commit_usd):
        pct = terms.rebate_pct
        if terms.growth_kicker_pct and _kicker_earned(revenue, commit, terms.growth_kicker_threshold_pct):
            pct += terms.growth_kicker_pct
        total += revenue * pct / 100
    return total


def mdf_cost(ctx: DealContext, terms: Terms) -> float:
    return terms.mdf_usd * (ctx.mdf_claim_rate if terms.mdf_sell_through else 1.0)


def financing_cost(ctx: DealContext, days: int) -> float:
    return ctx.tcv_usd * ctx.caldova_wacc_pct / 100 * days / 365


def customer_value(ctx: DealContext, terms: Terms) -> float:
    """Customer-perceived USD value of a package (synthetic model, see README)."""
    rebates = 0.0
    for plan, commit in zip(ctx.plan_revenue, ctx.annual_commit_usd):
        pct = terms.rebate_pct
        if terms.growth_kicker_pct and _kicker_earned(plan, commit, terms.growth_kicker_threshold_pct):
            pct += terms.growth_kicker_pct
        rebates += plan * pct / 100
    mdf = terms.mdf_usd * (ctx.sell_through_mdf_customer_value if terms.mdf_sell_through else 1.0)
    float_value = sum(ctx.plan_revenue) * ctx.customer_cost_of_capital_pct / 100 * terms.payment_terms_days / 365
    return rebates + mdf + float_value + price_certainty_value(ctx, terms.price_protection_months, terms.cpi_cap)


def price_certainty_value(ctx: DealContext, months: int, cpi_cap: bool) -> float:
    """Value to the customer of avoided price increases, against the customer's own
    expectation of market increases (compounding yearly from year 2)."""
    value = 0.0
    m_pct = ctx.customer_market_increase_pct
    for year_index, annual in enumerate(ctx.plan_revenue):
        expected = ((1 + m_pct / 100) ** year_index - 1) * 100
        cap = ctx.forecast.cpi_cum_pct(year_index)
        monthly = annual / 12.0
        for m in range(12):
            month_no = year_index * 12 + m + 1
            if month_no <= months:
                allowed = 0.0
            elif cpi_cap:
                allowed = min(expected, cap)
            else:
                allowed = expected
            value += monthly * (expected - allowed) / 100
    return value


def _margin(ctx: DealContext, terms: Terms) -> tuple[float, float, float, float, float, ProtectionEffect]:
    effect = _protection_effect(terms.price_protection_months, terms.cpi_cap, ctx.forecast, ctx.annual_list_revenue_usd)
    reb = rebate_cost(ctx, terms)
    mdf = mdf_cost(ctx, terms)
    net = ctx.tcv_usd - reb - mdf + effect.recovery
    cogs = ctx.tcv_usd * ctx.cogs_ratio + effect.sensor_cost_increase
    fin = financing_cost(ctx, terms.payment_terms_days)
    return reb, mdf, net, cogs, fin, effect


def evaluate(ctx: DealContext, terms: Terms, *, floor_pct: float = MARGIN_FLOOR_PCT) -> PnL:
    """Full deal-life P&L waterfall for `terms` on `ctx`."""
    reb, mdf, net, cogs, fin, effect = _margin(ctx, terms)
    margin = net - cogs - fin
    std = standard_terms(ctx)
    _, _, s_net, s_cogs, s_fin, _ = _margin(ctx, std)
    std_margin = s_net - s_cogs - s_fin
    return PnL(
        list_revenue=ctx.tcv_usd,
        rebates=reb,
        mdf=mdf,
        pass_through_recovery=effect.recovery,
        net_revenue=net,
        cogs=cogs,
        sensor_cost_increase=effect.sensor_cost_increase,
        price_protection_cost=effect.forgone,
        financing_cost=fin,
        deal_margin=margin,
        gm_pct=margin / net * 100 if net else float("-inf"),
        customer_value_usd=customer_value(ctx, terms),
        concession_usd=std_margin - margin,
        floor_pct=floor_pct,
    )


def check_margin_floor(pnl: PnL, floor_pct: float = MARGIN_FLOOR_PCT) -> bool:
    return pnl.gm_pct >= floor_pct


def naive_gm_pct(ctx: DealContext, terms: Terms, *, ignore_cost_forecast: bool = False, mdf_as_opex: bool = False) -> float:
    """GM a naive analyst/agent computes with a known error. Used to build golden-set traps
    and code evaluators; never used for decisions."""
    if ignore_cost_forecast:
        ctx = DealContext(**{**ctx.__dict__, "forecast": CostForecast(
            sensor_pass_through_pct_by_year=tuple(0.0 for _ in ctx.forecast.sensor_pass_through_pct_by_year),
            cpi_pct=ctx.forecast.cpi_pct,
        )})
    pnl = evaluate(ctx, terms)
    if not mdf_as_opex:
        return pnl.gm_pct
    net = pnl.net_revenue + pnl.mdf
    margin = net - pnl.cogs - pnl.financing_cost
    return margin / net * 100
