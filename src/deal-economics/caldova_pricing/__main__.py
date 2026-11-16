"""CLI: python -m caldova_pricing {northwind|routine|search} [--slow] [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from . import fixtures
from .engine import evaluate
from .policy import classify_deal, required_approval
from .search import SearchConstraints, grid_size, scenario_search


def _money(x: float) -> str:
    return f"{'-' if x < 0 else ' '}${abs(x) / 1e6:7.3f}M"


def _deal(name: str):
    if name == "northwind":
        return fixtures.northwind_context(), fixtures.northwind_ask()
    if name == "routine":
        return fixtures.routine_context(), fixtures.routine_ask()
    raise SystemExit(f"unknown deal {name!r} (use northwind|routine)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="caldova_pricing", description="Caldova deal economics: illustrative planning figures, no external transactions")
    p.add_argument("command", choices=["northwind", "routine", "search"])
    p.add_argument("--deal", default="northwind")
    p.add_argument("--slow", action="store_true", help="long-running Monte-Carlo mode with progress")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)

    if a.command in ("northwind", "routine"):
        ctx, ask = _deal(a.command)
        packages = [("ask", ask)]
        if a.command == "northwind":
            packages.append(("recommended counter", fixtures.northwind_counter()))
        out = []
        for label, terms in packages:
            pnl = evaluate(ctx, terms)
            auth = required_approval(ctx, terms)
            out.append({"label": label, "terms": terms.to_dict(), "pnl": pnl.to_dict(), "authority": auth.to_dict()})
            if not a.json:
                print(f"\n[ILLUSTRATIVE FIGURES; no external transaction] {ctx.customer_name} — {label}: {terms.describe()}")
                for line, value in pnl.waterfall():
                    print(f"  {line:<48}{_money(value)}")
                print(f"  {'Deal-life gross margin':<48}{pnl.gm_pct:8.2f}%  (floor 32%: {'PASS' if pnl.meets_floor else 'FAIL'})")
                print(f"  {'Price-protection cost (unrecovered increase)':<48}{_money(pnl.price_protection_cost)}")
                print(f"  {'Customer value':<48}{_money(pnl.customer_value_usd)}")
                print(f"  {'Concession vs. rate card':<48}{_money(pnl.concession_usd)}")
                print(f"  Approval required: {auth.to_dict()['required_approver']}")
        if a.command == "northwind" and not a.json:
            ratio = out[1]["pnl"]["customer_value_usd"] / out[0]["pnl"]["customer_value_usd"] * 100
            print(f"\n  Counter delivers {ratio:.1f}% of the customer value Northwind asked for.")
        if a.json:
            print(json.dumps(out, indent=2))
        return 0

    ctx, ask = _deal(a.deal)

    def progress(done: int, total: int) -> None:
        if not a.json:
            print(f"  progress {done:>6}/{total}", file=sys.stderr, flush=True)

    res = scenario_search(ask, SearchConstraints(), ctx, slow=a.slow, progress=progress)
    if a.json:
        print(json.dumps(res.to_dict(), indent=2))
        return 0
    print(f"[ILLUSTRATIVE FIGURES; no external transaction] scenario search ({res.mode}): {res.evaluated} of {grid_size(ctx)} combos evaluated, "
          f"{res.feasible} feasible, {res.elapsed_s:.2f}s")
    for c in res.top:
        p10 = f", P10 GM {c.gm_p10_pct:.1f}%" if c.gm_p10_pct is not None else ""
        print(f"  #{c.rank}: {c.terms.describe()}\n      GM {c.pnl.gm_pct:.2f}%{p10}, "
              f"{c.value_pct_of_ask:.1f}% of asked customer value, approver: "
              f"{required_approval(ctx, c.terms).to_dict()['required_approver']}")
    cls = classify_deal(ctx, ask)
    print(f"  Triage: {cls.outcome} ({cls.reason})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
