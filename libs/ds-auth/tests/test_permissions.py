from ds_auth import grant_satisfies, has_exact_permission, has_permission


def test_exact_match():
    assert grant_satisfies("connector.provider.read", "connector.provider.read")
    assert not grant_satisfies("connector.provider.read", "connector.provider.write")


def test_admin_is_superset_of_service():
    assert grant_satisfies("connector.admin", "connector.provider.write")
    assert grant_satisfies("connector.admin", "connector.internal")
    assert grant_satisfies("connector.admin", "connector.admin")


def test_admin_does_not_cross_services():
    assert not grant_satisfies("connector.admin", "provenance.read")
    assert not grant_satisfies("dataset.admin", "connector.provider.read")


def test_non_admin_is_not_a_superset():
    assert not grant_satisfies("connector.provider", "connector.provider.read")


def test_has_permission_any_of():
    grants = ["provenance.read", "connector.provider.read"]
    assert has_permission(grants, ["connector.provider.read", "connector.admin"])
    assert not has_permission(grants, ["connector.provider.write"])


def test_has_permission_empty():
    assert not has_permission([], ["connector.admin"])


# ── has_exact_permission ─────────────────────────────────────────────────────


def test_exact_matches_by_name():
    assert has_exact_permission(["connector.webhook"], ["connector.webhook"])


def test_exact_is_not_satisfied_by_admin():
    assert not has_exact_permission(["connector.admin"], ["connector.webhook"])


def test_exact_is_not_satisfied_by_a_different_service_admin():
    assert not has_exact_permission(["provenance.admin"], ["connector.internal"])


def test_exact_accepts_any_of_the_required():
    assert has_exact_permission(
        ["connector.internal"], ["connector.webhook", "connector.internal"]
    )


def test_exact_with_no_grants_is_false():
    assert not has_exact_permission([], ["connector.webhook"])


def test_admin_still_satisfies_the_normal_rule():
    """The superset is unchanged for ordinary resource permissions."""
    assert has_permission(["connector.admin"], ["connector.provider.read"])
    assert not has_exact_permission(["connector.admin"], ["connector.provider.read"])
