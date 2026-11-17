from datetime import datetime, timezone

import pytest

from caldova_deal_system.config import Settings
from caldova_deal_system.errors import DealSystemError
from caldova_deal_system.service import DealService


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 9, 9, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def settings(tmp_path):
    return Settings(state_dir=tmp_path / "state")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def svc(settings, clock):
    return DealService(settings, clock=clock)


def error_of(fn) -> DealSystemError:
    with pytest.raises(DealSystemError) as e:
        fn()
    return e.value
