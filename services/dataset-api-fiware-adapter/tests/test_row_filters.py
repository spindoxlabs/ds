import pytest

from dataset_api_fiware.row_filters import (
    FiwareRowFilterResult,
    resolve_fiware_row_filters,
)
from celine.dataset.security.models import AuthenticatedUser


def _user(**kw):
    defaults = dict(sub="user-1", claims={})
    defaults.update(kw)
    return AuthenticatedUser(**defaults)


@pytest.mark.asyncio
async def test_no_specs_returns_empty():
    result = await resolve_fiware_row_filters(
        specs=[], user=_user(), rec_registry_url="http://rr",
    )
    assert result.allowed_entity_ids is None
    assert result.deny is False


@pytest.mark.asyncio
async def test_no_user_returns_empty():
    result = await resolve_fiware_row_filters(
        specs=[{"handler": "rec_registry", "args": {}}],
        user=None,
        rec_registry_url="http://rr",
    )
    assert result.deny is False


@pytest.mark.asyncio
async def test_deny_handler():
    result = await resolve_fiware_row_filters(
        specs=[{"handler": "deny", "args": {}}],
        user=_user(),
        rec_registry_url="http://rr",
    )
    assert result.deny is True


@pytest.mark.asyncio
async def test_unknown_handler_skipped():
    result = await resolve_fiware_row_filters(
        specs=[{"handler": "unknown_handler", "args": {}}],
        user=_user(),
        rec_registry_url="http://rr",
    )
    assert result.deny is False
    assert result.allowed_entity_ids is None


@pytest.mark.asyncio
async def test_direct_user_match_skipped():
    result = await resolve_fiware_row_filters(
        specs=[{"handler": "direct_user_match", "args": {"column": "owner"}}],
        user=_user(),
        rec_registry_url="http://rr",
    )
    assert result.deny is False
    assert result.allowed_entity_ids is None
