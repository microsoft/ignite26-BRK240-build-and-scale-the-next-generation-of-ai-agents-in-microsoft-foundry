"""caldova_pricing: deterministic deal economics for the Caldova Deal Desk sample. All data is fictional."""

from .engine import (
    MARGIN_FLOOR_PCT,
    check_margin_floor,
    customer_value,
    evaluate,
    naive_gm_pct,
    price_protection_cost,
    standard_terms,
)
from .models import CostForecast, DealContext, InvalidTermsError, PnL, Terms, canonical_terms_json, terms_hash
from .policy import (
    APPROVER_DISPLAY,
    AUTHORITY_MATRIX,
    AuthorityDecision,
    Classification,
    can_approve,
    classify_deal,
    required_approval,
)
from .search import Counter, SearchConstraints, SearchResult, grid_size, scenario_search

__all__ = [
    "APPROVER_DISPLAY",
    "AUTHORITY_MATRIX",
    "AuthorityDecision",
    "Classification",
    "CostForecast",
    "Counter",
    "DealContext",
    "InvalidTermsError",
    "MARGIN_FLOOR_PCT",
    "PnL",
    "SearchConstraints",
    "SearchResult",
    "Terms",
    "can_approve",
    "canonical_terms_json",
    "check_margin_floor",
    "classify_deal",
    "customer_value",
    "evaluate",
    "grid_size",
    "naive_gm_pct",
    "price_protection_cost",
    "required_approval",
    "scenario_search",
    "standard_terms",
    "terms_hash",
]

__version__ = "0.1.0"
