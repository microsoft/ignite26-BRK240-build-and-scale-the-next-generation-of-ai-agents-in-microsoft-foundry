"""Canonical SYNTHETIC deal fixtures shared by tests, the data generator, the deal system and agents."""

from __future__ import annotations

from .models import CostForecast, DealContext, Terms

NORTHWIND_DEAL_ID = "DEAL-NW-001"
ROUTINE_DEAL_ID = "DEAL-RT-001"

# Contract years 2027-2029. Sensor-component increase lands in 2028 (year 2), small further step in 2029.
DEFAULT_FORECAST = CostForecast(sensor_pass_through_pct_by_year=(0.0, 5.0, 5.5), cpi_pct=3.0)

_NW_LIST = (14_400_000.0, 16_000_000.0, 17_600_000.0)  # $48.0M TCV at Caldova's forecast volume
_NW_CALDOVA_ATTAINMENT = (1.04, 1.08, 1.12)  # forecast volume vs committed volume
_NW_PLAN_ATTAINMENT = (1.11, 1.15, 1.20)  # Northwind's own (optimistic) volume plan vs commit
_NW_COMMIT = tuple(round(v / a, 2) for v, a in zip(_NW_LIST, _NW_CALDOVA_ATTAINMENT))
_NW_PLAN = tuple(round(c * a, 2) for c, a in zip(_NW_COMMIT, _NW_PLAN_ATTAINMENT))


def northwind_context() -> DealContext:
    return DealContext(
        deal_id=NORTHWIND_DEAL_ID,
        customer_name="Northwind Pharmacy",
        annual_list_revenue_usd=_NW_LIST,
        annual_commit_usd=_NW_COMMIT,
        cogs_ratio=0.5459,
        forecast=DEFAULT_FORECAST,
        customer_plan_revenue_usd=_NW_PLAN,
        caldova_wacc_pct=7.0,
        customer_cost_of_capital_pct=12.0,
        customer_market_increase_pct=6.7,
        mdf_claim_rate=0.80,
        sell_through_mdf_customer_value=0.95,
    )


def northwind_ask() -> Terms:
    """18 % rebate, Net-90, 24-month price protection, $1.2M MDF."""
    return Terms(rebate_pct=18.0, payment_terms_days=90, price_protection_months=24, mdf_usd=1_200_000.0)


def northwind_counter() -> Terms:
    """12 % base + 2 % growth kicker at or above 110 % of commit, Net-60, 12-month protection with CPI cap,
    $900K MDF tied to sell-through."""
    return Terms(
        rebate_pct=12.0,
        growth_kicker_pct=2.0,
        growth_kicker_threshold_pct=110.0,
        payment_terms_days=60,
        price_protection_months=12,
        cpi_cap=True,
        mdf_usd=900_000.0,
        mdf_sell_through=True,
    )


_RT_LIST = (2_000_000.0, 2_100_000.0, 2_200_000.0)


def routine_context() -> DealContext:
    return DealContext(
        deal_id=ROUTINE_DEAL_ID,
        customer_name="Lakeshore Pharmacy Group",
        annual_list_revenue_usd=_RT_LIST,
        annual_commit_usd=tuple(round(v / 1.03, 2) for v in _RT_LIST),
        cogs_ratio=0.50,
        forecast=DEFAULT_FORECAST,
        mdf_claim_rate=0.80,
    )


def routine_ask() -> Terms:
    """Regional chain: 9 % rebate, Net-45, standard 12-month protection, MDF 1 % of TCV."""
    return Terms(rebate_pct=9.0, payment_terms_days=45, price_protection_months=12, mdf_usd=63_000.0)
