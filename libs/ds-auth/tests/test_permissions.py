from ds_auth import grant_satisfies, has_permission


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
