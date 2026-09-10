"""Tests for consent-time membership check helpers."""

from __future__ import annotations

import textwrap

import httpx
import pytest
import respx

from connector.services.membership_check import (
    Membership,
    check_subject_membership,
    resolve_dataset_owner,
)


class TestResolveDatasetOwner:
    @pytest.mark.rule("D-21")
    def test_returns_owner_alias_when_ownership_present(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(
            textwrap.dedent("""
            defaults:
              ownership:
                - name: example-org
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """)
        )
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias == "example-org"

    def test_returns_none_when_no_ownership(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(
            textwrap.dedent("""
            defaults:
              access_level: open
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """)
        )
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias is None

    @pytest.mark.rule("D-21")
    def test_per_dataset_ownership_overrides_defaults(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(
            textwrap.dedent("""
            defaults:
              ownership:
                - name: default-org
            sources:
              datasets.gold.test:
                ownership:
                  - name: specific-org
                dataspace:
                  expose: true
        """)
        )
        alias = resolve_dataset_owner(str(yaml_path), "datasets.gold.test")
        assert alias == "specific-org"

    @pytest.mark.rule("D-21")
    def test_overlay_ownership(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(
            textwrap.dedent("""
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """)
        )
        (tmp_path / "governance.prod.yaml").write_text(
            textwrap.dedent("""
            defaults:
              ownership:
                - name: prod-org
        """)
        )
        alias = resolve_dataset_owner(
            str(yaml_path), "datasets.gold.test", overlay_name="prod"
        )
        assert alias == "prod-org"

    def test_no_ownership_with_overlay(self, tmp_path):
        yaml_path = tmp_path / "governance.yaml"
        yaml_path.write_text(
            textwrap.dedent("""
            sources:
              datasets.gold.test:
                title: Test
                dataspace:
                  expose: true
        """)
        )
        alias = resolve_dataset_owner(
            str(yaml_path), "datasets.gold.test", overlay_name="missing"
        )
        assert alias is None


class TestTheThreeAnswers:
    """The check has three answers, and the third one is about us.

    This underwrites two authorization gates, and both used to be handed a bare
    bool. Every way of failing to reach the registry — an outage, a refused
    token, an unreadable body — therefore arrived at the gate as False, the
    same value a subject who genuinely never joined produces. The gate refused
    with a 403 naming the person, the caller believed it, and a transient
    fault was filed as a settled fact about somebody's membership.

    An answer from the registry decides; anything else is UNKNOWN for the
    caller to treat as retryable.
    """

    IR = "http://registry.test"
    DID = "did:web:example.test:users:subject-1"
    ORG = "example-org"

    @property
    def route(self) -> str:
        return f"{self.IR}/memberships/check"

    async def _check(self, **kwargs):
        return await check_subject_membership(
            self.IR, user_did=self.DID, organization_alias=self.ORG, **kwargs
        )

    @respx.mock
    async def test_a_member_is_a_member(self):
        respx.get(self.route).mock(
            return_value=httpx.Response(200, json={"member": True})
        )
        assert await self._check() is Membership.MEMBER

    @respx.mock
    async def test_a_registry_that_says_no_is_believed(self):
        respx.get(self.route).mock(
            return_value=httpx.Response(200, json={"member": False})
        )
        assert await self._check() is Membership.NOT_MEMBER

    @pytest.mark.parametrize("status", [401, 403])
    async def test_our_own_credentials_being_refused_says_nothing_about_them(
        self, status
    ):
        """A registry refusing *this service* is our misconfiguration, not their
        membership."""
        with respx.mock:
            respx.get(self.route).mock(
                return_value=httpx.Response(status, json={"detail": "nope"})
            )
            assert await self._check() is Membership.UNKNOWN

    @pytest.mark.parametrize("status", [404, 500, 502, 503])
    async def test_any_other_status_is_unknown(self, status):
        with respx.mock:
            respx.get(self.route).mock(return_value=httpx.Response(status, text="boom"))
            assert await self._check() is Membership.UNKNOWN

    @respx.mock
    async def test_an_unreachable_registry_is_unknown(self):
        respx.get(self.route).mock(side_effect=httpx.ConnectError("no route to host"))
        assert await self._check() is Membership.UNKNOWN

    @respx.mock
    async def test_an_unreadable_body_is_unknown(self):
        respx.get(self.route).mock(return_value=httpx.Response(200, text="not json"))
        assert await self._check() is Membership.UNKNOWN

    @respx.mock
    async def test_a_missing_member_field_is_unknown(self):
        """The old code read an absent member as False via .get(..., False).

        That turns a contract the registry did not keep into a denial, which is
        the same conflation this enum exists to end.
        """
        respx.get(self.route).mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        assert await self._check() is Membership.UNKNOWN

    @respx.mock
    async def test_a_non_boolean_member_field_is_unknown(self):
        respx.get(self.route).mock(
            return_value=httpx.Response(200, json={"member": "yes"})
        )
        assert await self._check() is Membership.UNKNOWN

    @respx.mock
    async def test_a_token_that_cannot_be_minted_is_unknown(self):
        """Never reached the registry, so nothing was learned about the subject."""
        respx.get(self.route).mock(
            return_value=httpx.Response(200, json={"member": True})
        )

        async def _broken_provider():
            raise RuntimeError("token endpoint unavailable")

        assert await self._check(token_provider=_broken_provider) is Membership.UNKNOWN

    def test_every_answer_is_truthy(self):
        """The guard against the old if not is_member shape coming back.

        Testing the result for truthiness must not quietly compile down to
        "deny", so no member of the enum may be falsy.
        """
        assert all(bool(m) for m in Membership)

    @respx.mock
    async def test_the_organisation_is_named_in_the_log(self, caplog):
        """A check fails most often because the caller asked under the wrong name.

        The membership API matches organization as a literal string, so a log
        line naming only the subject sends the reader after the wrong thing.
        """
        respx.get(self.route).mock(return_value=httpx.Response(500, text="boom"))
        with caplog.at_level("ERROR"):
            await self._check()
        assert self.ORG in caplog.text
        assert self.DID in caplog.text
