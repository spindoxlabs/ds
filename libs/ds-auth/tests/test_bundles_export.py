"""The portal's generated bundle table must match the Python definition.

If this fails, the table changed and the generated copy did not — run
``task -d libs/ds-auth bundles:generate`` and commit the result.
"""
from __future__ import annotations

from pathlib import Path

from ds_auth.bundles import ROLE_BUNDLES
from ds_auth.bundles_export import PORTAL_TARGET, render_typescript

REPO = Path(__file__).resolve().parents[3]


def test_generated_typescript_exists():
    assert (REPO / PORTAL_TARGET).is_file(), (
        f"{PORTAL_TARGET} missing — run `task -d libs/ds-auth bundles:generate`"
    )


def test_generated_typescript_matches_regeneration():
    published = (REPO / PORTAL_TARGET).read_text(encoding="utf-8")
    assert published == render_typescript(), (
        f"{PORTAL_TARGET} is stale — regenerate with "
        "`task -d libs/ds-auth bundles:generate`"
    )


def test_every_bundle_appears_in_the_rendered_output():
    """Cheap guard against a renderer that silently drops entries."""
    rendered = render_typescript()
    for bundle, capabilities in ROLE_BUNDLES.items():
        assert f"'{bundle}'" in rendered
        for capability in capabilities:
            assert f"'{capability}'" in rendered


def test_generated_file_declares_itself_generated():
    """Someone will open it and start editing otherwise."""
    assert render_typescript().startswith("// GENERATED FILE — DO NOT EDIT.")
