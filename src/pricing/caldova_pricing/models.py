"""Typed value objects for the Caldova pricing engine. All data is fictional."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

TERMS_FIELDS = (
    "rebate_pct",
    "growth_kicker_pct",
    "growth_kicker_threshold_pct",
    "payment_terms_days",
    "price_protection_months",
    "cpi_cap",
    "mdf_usd",
    "mdf_sell_through",
)


class InvalidTermsError(ValueError):
    """Raised when a terms payload is malformed or out of range."""


@dataclass(frozen=True)
class Terms:
    """A negotiable deal package. Percentages are percent numbers (12.0 == 12 %)."""

    rebate_pct: float
    payment_terms_days: int
    price_protection_months: int
    mdf_usd: float
    growth_kicker_pct: float = 0.0
    growth_kicker_threshold_pct: float = 110.0
    cpi_cap: bool = False
    mdf_sell_through: bool = False

    def __post_init__(self) -> None:
        if not 0 <= self.rebate_pct <= 60:
            raise InvalidTermsError("rebate_pct must be between 0 and 60")
        if not 0 <= self.growth_kicker_pct <= 20:
            raise InvalidTermsError("growth_kicker_pct must be between 0 and 20")
        if not 100 <= self.growth_kicker_threshold_pct <= 300:
            raise InvalidTermsError("growth_kicker_threshold_pct must be between 100 and 300")
        if not 0 <= self.payment_terms_days <= 365:
            raise InvalidTermsError("payment_terms_days must be between 0 and 365")
        if not 0 <= self.price_protection_months <= 120:
            raise InvalidTermsError("price_protection_months must be between 0 and 120")
        if self.mdf_usd < 0:
            raise InvalidTermsError("mdf_usd must be >= 0")

    @property
    def effective_rebate_pct(self) -> float:
        """Rebate the authority check uses: base + kicker (kicker assumed earned)."""
        return self.rebate_pct + self.growth_kicker_pct

    def to_dict(self) -> dict[str, Any]:
        return {
            "rebate_pct": float(self.rebate_pct),
            "growth_kicker_pct": float(self.growth_kicker_pct),
            "growth_kicker_threshold_pct": float(self.growth_kicker_threshold_pct),
            "payment_terms_days": int(self.payment_terms_days),
            "price_protection_months": int(self.price_protection_months),
            "cpi_cap": bool(self.cpi_cap),
            "mdf_usd": float(self.mdf_usd),
            "mdf_sell_through": bool(self.mdf_sell_through),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Terms":
        if not isinstance(data, Mapping):
            raise InvalidTermsError("terms must be an object")
        unknown = set(data) - set(TERMS_FIELDS)
        if unknown:
            raise InvalidTermsError(f"unknown terms fields: {sorted(unknown)}")
        missing = {"rebate_pct", "payment_terms_days", "price_protection_months", "mdf_usd"} - set(data)
        if missing:
            raise InvalidTermsError(f"missing terms fields: {sorted(missing)}")
        try:
            return cls(
                rebate_pct=float(data["rebate_pct"]),
                payment_terms_days=int(data["payment_terms_days"]),
                price_protection_months=int(data["price_protection_months"]),
                mdf_usd=float(data["mdf_usd"]),
                growth_kicker_pct=float(data.get("growth_kicker_pct", 0.0)),
                growth_kicker_threshold_pct=float(data.get("growth_kicker_threshold_pct", 110.0)),
                cpi_cap=_as_bool(data.get("cpi_cap", False)),
                mdf_sell_through=_as_bool(data.get("mdf_sell_through", False)),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, InvalidTermsError):
                raise
            raise InvalidTermsError(str(exc)) from exc

    def describe(self) -> str:
        parts = [f"{self.rebate_pct:g}% rebate"]
        if self.growth_kicker_pct:
            parts[0] += (
                f" + {self.growth_kicker_pct:g}% growth kicker at or above "
                f"{self.growth_kicker_threshold_pct:g}% of commit"
            )
        parts.append(f"Net-{self.payment_terms_days}")
        prot = f"{self.price_protection_months}-mo price protection"
        if self.cpi_cap:
            prot += " with CPI cap"
        parts.append(prot)
        mdf = f"${self.mdf_usd / 1e6:,.2f}M MDF"
        if self.mdf_sell_through:
            mdf += " tied to sell-through"
        parts.append(mdf)
        return " · ".join(parts)


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y"}
    return bool(value)


def canonical_terms_json(terms: Terms | Mapping[str, Any]) -> str:
    t = terms if isinstance(terms, Terms) else Terms.from_dict(terms)
    normalized: dict[str, Any] = {}
    for key, value in t.to_dict().items():
        if isinstance(value, bool):
            normalized[key] = value
        elif isinstance(value, float):
            rounded = round(value, 4)
            normalized[key] = int(rounded) if rounded.is_integer() else rounded
        else:
            normalized[key] = value
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def terms_hash(terms: Terms | Mapping[str, Any]) -> str:
    """sha256 of canonical terms JSON. The only supported way to bind approvals to terms."""
    return hashlib.sha256(canonical_terms_json(terms).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CostForecast:
    """Forecast sensor-component cost increase, expressed as the cumulative list-price
    pass-through (percent of contract-start list price) needed to recover it, per contract year.
    Year 1 is 0; the increase lands at month 13 (year 2) with a further step in year 3."""

    sensor_pass_through_pct_by_year: tuple[float, ...] = (0.0, 5.0, 5.5)
    cpi_pct: float = 3.0

    def pass_through_pct(self, year_index: int) -> float:
        series = self.sensor_pass_through_pct_by_year
        return series[min(year_index, len(series) - 1)]

    def cpi_cum_pct(self, year_index: int) -> float:
        return ((1 + self.cpi_pct / 100) ** year_index - 1) * 100

    def to_dict(self) -> dict[str, Any]:
        return {"sensor_pass_through_pct_by_year": list(self.sensor_pass_through_pct_by_year), "cpi_pct": self.cpi_pct}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CostForecast":
        return cls(
            sensor_pass_through_pct_by_year=tuple(float(x) for x in data["sensor_pass_through_pct_by_year"]),
            cpi_pct=float(data.get("cpi_pct", 3.0)),
        )


@dataclass(frozen=True)
class DealContext:
    """Everything about a deal except the negotiable terms."""

    deal_id: str
    customer_name: str
    annual_list_revenue_usd: tuple[float, ...]
    annual_commit_usd: tuple[float, ...]
    cogs_ratio: float
    forecast: CostForecast = field(default_factory=CostForecast)
    customer_plan_revenue_usd: tuple[float, ...] | None = None
    caldova_wacc_pct: float = 7.0
    customer_cost_of_capital_pct: float = 12.0
    customer_market_increase_pct: float = 6.7
    mdf_claim_rate: float = 0.80
    sell_through_mdf_customer_value: float = 0.95

    @property
    def years(self) -> int:
        return len(self.annual_list_revenue_usd)

    @property
    def tcv_usd(self) -> float:
        return float(sum(self.annual_list_revenue_usd))

    @property
    def plan_revenue(self) -> tuple[float, ...]:
        return self.customer_plan_revenue_usd or self.annual_list_revenue_usd

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["forecast"] = self.forecast.to_dict()
        for key in ("annual_list_revenue_usd", "annual_commit_usd", "customer_plan_revenue_usd"):
            if d[key] is not None:
                d[key] = list(d[key])
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DealContext":
        plan = data.get("customer_plan_revenue_usd")
        return cls(
            deal_id=str(data["deal_id"]),
            customer_name=str(data["customer_name"]),
            annual_list_revenue_usd=tuple(float(x) for x in data["annual_list_revenue_usd"]),
            annual_commit_usd=tuple(float(x) for x in data["annual_commit_usd"]),
            cogs_ratio=float(data["cogs_ratio"]),
            forecast=CostForecast.from_dict(data.get("forecast") or CostForecast().to_dict()),
            customer_plan_revenue_usd=tuple(float(x) for x in plan) if plan else None,
            caldova_wacc_pct=float(data.get("caldova_wacc_pct", 7.0)),
            customer_cost_of_capital_pct=float(data.get("customer_cost_of_capital_pct", 12.0)),
            customer_market_increase_pct=float(data.get("customer_market_increase_pct", 6.7)),
            mdf_claim_rate=float(data.get("mdf_claim_rate", 0.80)),
            sell_through_mdf_customer_value=float(data.get("sell_through_mdf_customer_value", 0.95)),
        )


@dataclass(frozen=True)
class PnL:
    """Deal-life P&L waterfall (USD) plus derived metrics."""

    list_revenue: float
    rebates: float
    mdf: float
    pass_through_recovery: float
    net_revenue: float
    cogs: float
    sensor_cost_increase: float
    price_protection_cost: float
    financing_cost: float
    deal_margin: float
    gm_pct: float
    customer_value_usd: float
    concession_usd: float
    floor_pct: float = 32.0

    @property
    def meets_floor(self) -> bool:
        return self.gm_pct >= self.floor_pct

    def to_dict(self) -> dict[str, Any]:
        d = {k: round(v, 2) if isinstance(v, float) else v for k, v in asdict(self).items()}
        d["gm_pct"] = round(self.gm_pct, 2)
        d["meets_floor"] = self.meets_floor
        return d

    def waterfall(self) -> list[tuple[str, float]]:
        return [
            ("List revenue (TCV)", self.list_revenue),
            ("Rebates incl. growth kicker (contra-revenue)", -self.rebates),
            ("MDF (contra-revenue)", -self.mdf),
            ("Cost pass-through recovery (post-protection)", self.pass_through_recovery),
            ("Net revenue", self.net_revenue),
            ("COGS incl. forecast sensor-component increase", -self.cogs),
            ("Payment-terms financing cost", -self.financing_cost),
            ("Deal margin", self.deal_margin),
        ]
