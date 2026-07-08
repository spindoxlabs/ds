import pytest
from pydantic import ValidationError

from dataset_api_fiware.config import FiwareSettings


def test_defaults():
    s = FiwareSettings()
    assert s.enabled is True
    assert s.default_timeout_ms == 10000
    assert s.max_limit == 10000
    assert s.jwt_forwarding is False


def test_custom_values():
    s = FiwareSettings(
        enabled=False,
        default_timeout_ms=5000,
        max_limit=1000,
        jwt_forwarding=True,
    )
    assert s.enabled is False
    assert s.default_timeout_ms == 5000
    assert s.max_limit == 1000
    assert s.jwt_forwarding is True


def test_timeout_minimum():
    with pytest.raises(ValidationError):
        FiwareSettings(default_timeout_ms=500)


def test_max_limit_minimum():
    with pytest.raises(ValidationError):
        FiwareSettings(max_limit=0)
