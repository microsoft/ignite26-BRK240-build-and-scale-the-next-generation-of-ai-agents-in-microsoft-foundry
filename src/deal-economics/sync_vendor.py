"""Refresh the copies this hosted agent ships with. All data is fictional.

`azd deploy` packages only this folder, so the agent carries:
  * caldova_pricing/     - verbatim copy of ../pricing/caldova_pricing (the shared engine)
  * deal_register.json   - deal contexts and asks (no human decisions) from ../../data/generated

    python sync_vendor.py           # refresh the copies
    python sync_vendor.py --check   # exit 1 if the copies drifted
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENGINE_SRC = REPO / "src" / "pricing" / "caldova_pricing"
ENGINE_DST = HERE / "caldova_pricing"
DATA = REPO / "data" / "generated"
REGISTER = HERE / "deal_register.json"


def build_register() -> dict:
    seed = json.loads((DATA / "deal_system_seed.json").read_text(encoding="utf-8"))
    deals: dict[str, dict] = {}
    for d in seed["deals"]:
        deals[d["deal_id"]] = {
            "deal_id": d["deal_id"],
            "customer_name": d["customer_name"],
            "segment": d.get("segment"),
            "context": d["context"],
            "ask": d["ask"],
        }
    # Golden-set cases contribute only the deal inputs, never the human decision or trap labels.
    for line in (DATA / "golden_set.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = json.loads(line)
        deals[c["case_id"]] = {
            "deal_id": c["case_id"],
            "customer_name": c["customer_name"],
            "segment": c.get("segment"),
            "context": c["deal"],
            "ask": c["ask"],
        }
    return {"synthetic": True, "source": "data/generated (deal_system_seed.json + golden_set.jsonl deal inputs)", "deals": deals}


def engine_files(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes().replace(b"\r\n", b"\n") for p in sorted(root.glob("*.py"))}


def drift() -> list[str]:
    problems = []
    src, dst = engine_files(ENGINE_SRC), engine_files(ENGINE_DST) if ENGINE_DST.exists() else {}
    problems += [f"caldova_pricing/{n}" for n in sorted(src.keys() | dst.keys()) if src.get(n) != dst.get(n)]
    if not REGISTER.exists() or json.loads(REGISTER.read_text(encoding="utf-8")) != build_register():
        problems.append(REGISTER.name)
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if the copies drifted")
    if ap.parse_args(argv).check:
        problems = drift()
        print(f"out of date: {', '.join(problems)}; run: python sync_vendor.py" if problems else "vendored copies are up to date")
        return 1 if problems else 0

    if ENGINE_DST.exists():
        shutil.rmtree(ENGINE_DST)
    ENGINE_DST.mkdir()
    for name, data in engine_files(ENGINE_SRC).items():
        (ENGINE_DST / name).write_bytes(data)
    REGISTER.write_text(json.dumps(build_register(), indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"synced {ENGINE_DST.relative_to(REPO).as_posix()} and {REGISTER.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
