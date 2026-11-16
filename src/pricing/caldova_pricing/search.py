"""Scenario search: enumerate counter packages and return the best for the customer that
keep Caldova above its margin floor. Deterministic; `slow=True` adds a Monte-Carlo risk
pass per feasible candidate so the hosted agent can show a long-running run."""

from __future__ import annotations

import itertools
import random
import time
from dataclasses import dataclass, replace
from typing import Any, Callable

from .engine import (
    MARGIN_FLOOR_PCT,
    _protection_effect,
    customer_value,
    evaluate,
    financing_cost,
    mdf_cost,
    price_certainty_value,
    rebate_cost,
)
from .models import DealContext, PnL, Terms

REBATE_GRID = tuple(float(x) for x in range(8, 19))  # 8..18 %
KICKER_GRID = (0.0, 1.0, 2.0, 3.0)
TERMS_GRID = (45, 60, 75, 90)
PROTECTION_GRID = (12, 18, 24)
CPI_CAP_GRID = (False, True)
MDF_PCT_GRID = (1.0, 1.25, 1.5625, 1.875, 2.5)  # % of TCV -> $480K..$1.2M on $48M
SELL_THROUGH_GRID = (False, True)

ProgressFn = Callable[[int, int], None]


@dataclass(frozen=True)
class SearchConstraints:
    floor_pct: float = MARGIN_FLOOR_PCT
    headroom_pct: float = 1.0  # counters keep >= 1 pt negotiation headroom (counterproposal skill)
    within_ask: bool = True
    max_effective_rebate_pct: float | None = None
    max_kicker_pct: float = 2.0
    max_payment_terms_days: int = 60
    max_price_protection_months: int = 12
    max_mdf_pct_of_tcv: float = 2.0
    top_n: int = 3

    @classmethod
    def agent_authority(cls) -> "SearchConstraints":
        """Everything within the agent's own authority (no human needed)."""
        return cls(headroom_pct=0.0, max_effective_rebate_pct=10.0)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class Counter:
    rank: int
    terms: Terms
    pnl: PnL
    value_pct_of_ask: float
    gm_p10_pct: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "terms": self.terms.to_dict(),
            "summary": self.terms.describe(),
            "gm_pct": round(self.pnl.gm_pct, 2),
            "customer_value_usd": round(self.pnl.customer_value_usd, 2),
            "customer_value_pct_of_ask": round(self.value_pct_of_ask, 1),
            "concession_usd": round(self.pnl.concession_usd, 2),
            "gm_p10_pct": round(self.gm_p10_pct, 2) if self.gm_p10_pct is not None else None,
            "pnl": self.pnl.to_dict(),
        }


@dataclass(frozen=True)
class SearchResult:
    top: tuple[Counter, ...]
    evaluated: int
    feasible: int
    ask_pnl: PnL
    elapsed_s: float
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "evaluated": self.evaluated,
            "feasible": self.feasible,
            "elapsed_s": round(self.elapsed_s, 3),
            "ask": {"gm_pct": round(self.ask_pnl.gm_pct, 2), "customer_value_usd": round(self.ask_pnl.customer_value_usd, 2)},
            "top": [c.to_dict() for c in self.top],
        }


def mdf_grid(ctx: DealContext) -> tuple[float, ...]:
    return tuple(round(ctx.tcv_usd * pct / 100, -4) for pct in MDF_PCT_GRID)


def grid_size(ctx: DealContext) -> int:
    return (
        len(REBATE_GRID) * len(KICKER_GRID) * len(TERMS_GRID) * len(PROTECTION_GRID)
        * len(CPI_CAP_GRID) * len(mdf_grid(ctx)) * len(SELL_THROUGH_GRID)
    )


def scenario_search(
    ask: Terms,
    constraints: SearchConstraints,
    ctx: DealContext,
    *,
    slow: bool = False,
    mc_draws: int = 2000,
    progress: ProgressFn | None = None,
    seed: int = 20261117,
    top_p10: bool = False,
) -> SearchResult:
    """Enumerate every combo on the grid; keep those that satisfy `constraints` and
    GM >= floor + headroom; return the top-N by customer value (tie-break: higher GM).

    `top_p10=True` adds the seeded Monte-Carlo P10 for the top-N only (values identical to
    slow mode, which draws them first from the same RNG); `slow=True` also stress-tests the
    whole feasible frontier."""
    started = time.perf_counter()
    c = constraints
    tcv = ctx.tcv_usd
    cogs_base = tcv * ctx.cogs_ratio
    ask_pnl = evaluate(ctx, ask)
    min_gm = c.floor_pct + c.headroom_pct

    # Every P&L line is separable by dimension, so precompute each one once.
    prot: dict[tuple[int, bool], tuple[float, float, float]] = {}
    for months, cap in itertools.product(PROTECTION_GRID, CPI_CAP_GRID):
        eff = _protection_effect(months, cap, ctx.forecast, ctx.annual_list_revenue_usd)
        prot[(months, cap)] = (eff.recovery, eff.sensor_cost_increase, price_certainty_value(ctx, months, cap))
    fin = {d: (financing_cost(ctx, d), sum(ctx.plan_revenue) * ctx.customer_cost_of_capital_pct / 100 * d / 365) for d in TERMS_GRID}
    mdfs = mdf_grid(ctx)
    reb_cache: dict[tuple[float, float], tuple[float, float]] = {}
    for base, kick in itertools.product(REBATE_GRID, KICKER_GRID):
        probe = Terms(rebate_pct=base, growth_kicker_pct=kick, payment_terms_days=45, price_protection_months=12, mdf_usd=0.0)
        reb_cache[(base, kick)] = (rebate_cost(ctx, probe), customer_value(ctx, probe) - _non_rebate_value(ctx, probe))

    total = grid_size(ctx)
    evaluated = 0
    feasible: list[tuple[float, float, Terms]] = []
    for base, kick, days, months, cap, mdf, st in itertools.product(
        REBATE_GRID, KICKER_GRID, TERMS_GRID, PROTECTION_GRID, CPI_CAP_GRID, mdfs, SELL_THROUGH_GRID
    ):
        evaluated += 1
        if progress and evaluated % 1000 == 0:
            progress(evaluated, total)
        terms = Terms(
            rebate_pct=base,
            growth_kicker_pct=kick,
            growth_kicker_threshold_pct=110.0,
            payment_terms_days=days,
            price_protection_months=months,
            cpi_cap=cap,
            mdf_usd=mdf,
            mdf_sell_through=st,
        )
        if not _allowed(terms, ask, c, tcv):
            continue
        rec, inc, certainty = prot[(months, cap)]
        reb, reb_value = reb_cache[(base, kick)]
        mdf_c = mdf_cost(ctx, terms)
        net = tcv - reb - mdf_c + rec
        margin = net - cogs_base - inc - fin[days][0]
        gm = margin / net * 100
        if gm < min_gm - 1e-9:
            continue
        mdf_value = mdf * (ctx.sell_through_mdf_customer_value if st else 1.0)
        value = reb_value + mdf_value + fin[days][1] + certainty
        feasible.append((value, gm, terms))
    if progress:
        progress(total, total)

    feasible.sort(key=lambda x: (-x[0], -x[1], x[2].effective_rebate_pct))
    top: list[Counter] = []
    rng = random.Random(seed)
    for value, _gm, terms in feasible[: c.top_n]:
        pnl = evaluate(ctx, terms)
        p10 = _monte_carlo_p10(ctx, terms, mc_draws, rng) if slow or top_p10 else None
        top.append(Counter(len(top) + 1, terms, pnl, value / ask_pnl.customer_value_usd * 100, p10))

    if slow:
        # Long-running mode: also stress-test the whole feasible frontier (real work, with progress).
        frontier = feasible
        for i, (_v, _g, terms) in enumerate(frontier, 1):
            _monte_carlo_p10(ctx, terms, mc_draws, rng)
            if progress and (i % 10 == 0 or i == len(frontier)):
                progress(total + i, total + len(frontier))

    mode = "slow" if slow else ("fast+p10" if top_p10 else "fast")
    return SearchResult(tuple(top), evaluated, len(feasible), ask_pnl, time.perf_counter() - started, mode)


def _non_rebate_value(ctx: DealContext, t: Terms) -> float:
    float_value = sum(ctx.plan_revenue) * ctx.customer_cost_of_capital_pct / 100 * t.payment_terms_days / 365
    return t.mdf_usd + float_value + price_certainty_value(ctx, t.price_protection_months, t.cpi_cap)


def _allowed(t: Terms, ask: Terms, c: SearchConstraints, tcv: float) -> bool:
    if t.growth_kicker_pct > c.max_kicker_pct:
        return False
    if c.max_effective_rebate_pct is not None and t.effective_rebate_pct > c.max_effective_rebate_pct:
        return False
    if t.payment_terms_days > c.max_payment_terms_days:
        return False
    if t.price_protection_months > c.max_price_protection_months:
        return False
    if t.mdf_usd > tcv * c.max_mdf_pct_of_tcv / 100 + 1e-6:
        return False
    if c.within_ask:
        if t.effective_rebate_pct > ask.effective_rebate_pct:
            return False
        if t.payment_terms_days > max(ask.payment_terms_days, 45):
            return False
        if t.price_protection_months > max(ask.price_protection_months, 12):
            return False
        if t.mdf_usd > max(ask.mdf_usd, tcv * 0.01) + 1e-6:
            return False
        if t.mdf_sell_through is False and ask.mdf_sell_through is True:
            return False
    return True


def _monte_carlo_p10(ctx: DealContext, terms: Terms, draws: int, rng: random.Random) -> float:
    """P10 deal-life GM under sensor-cost and volume uncertainty."""
    results: list[float] = []
    for _ in range(draws):
        shock = max(0.0, rng.gauss(1.0, 0.25))
        vol = max(0.5, rng.gauss(1.0, 0.06))
        f = replace(ctx.forecast, sensor_pass_through_pct_by_year=tuple(x * shock for x in ctx.forecast.sensor_pass_through_pct_by_year))
        sim = replace(
            ctx,
            forecast=f,
            annual_list_revenue_usd=tuple(x * vol for x in ctx.annual_list_revenue_usd),
        )
        results.append(evaluate(sim, terms).gm_pct)
    results.sort()
    return results[max(0, int(0.1 * len(results)) - 1)]
