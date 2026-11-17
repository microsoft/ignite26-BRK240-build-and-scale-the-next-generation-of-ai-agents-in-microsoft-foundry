import json
import os

import pytest

from caldova_pricing import fixtures as F
from caldova_deal_system import store as store_mod
from caldova_deal_system.config import Settings
from caldova_deal_system.identities import AGENT, DANA
from caldova_deal_system.service import DealService
from caldova_deal_system.store import JsonStore, atomic_write_text

NW = F.NORTHWIND_DEAL_ID
SEED = Settings().seed_path


def test_state_survives_a_restart_until_reset(tmp_path):
    svc = DealService(Settings(state_dir=tmp_path))
    appr = svc.request_approval(AGENT, NW, F.northwind_counter(), "counter")
    svc.record_approval(DANA, appr["approval_id"], svc.inbox_token(appr["approval_id"]), "approve", appr["terms_hash"])
    restarted = DealService(Settings(state_dir=tmp_path))
    assert restarted.get_deal(AGENT, NW)["approved_by"]["identity_id"] == "dana-vp-finance"
    restarted.reset()
    assert DealService(Settings(state_dir=tmp_path)).get_deal(AGENT, NW)["status"] == "open"


def test_seed_only_when_the_state_file_is_absent(tmp_path):
    JsonStore(tmp_path, SEED).mutate(lambda st: st["deals"][NW].update(status="countered"))
    assert JsonStore(tmp_path, SEED).read(lambda st: st["deals"][NW]["status"]) == "countered"
    (tmp_path / "deal_state.json").unlink()
    assert JsonStore(tmp_path, SEED).read(lambda st: st["deals"][NW]["status"]) == "open"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    p = tmp_path / "sub" / "x.json"
    atomic_write_text(p, '{"a": 1}')
    atomic_write_text(p, '{"a": 2}')
    assert json.loads(p.read_text()) == {"a": 2} and os.listdir(p.parent) == ["x.json"]


def test_failed_write_keeps_old_file_and_memory(tmp_path, monkeypatch):
    s = JsonStore(tmp_path, SEED)
    before = (tmp_path / "deal_state.json").read_text()

    def boom(src, dst):
        raise OSError("disk unavailable")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    with pytest.raises(OSError):
        s.mutate(lambda st: st["deals"][NW].update(status="countered"))
    monkeypatch.undo()
    assert (tmp_path / "deal_state.json").read_text() == before
    assert sorted(os.listdir(tmp_path)) == ["deal_state.json"]
    assert s.read(lambda st: st["deals"][NW]["status"]) == "open"


def test_missing_seed_has_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="DEAL_SYSTEM_SEED_PATH"):
        JsonStore(tmp_path, tmp_path / "nope.json")
