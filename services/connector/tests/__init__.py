import jwt as pyjwt


def make_headers(scope: str = "connector.admin") -> dict:
    """A service-account bearer (scope-based authority).

    ``preferred_username=service-account-*`` is what marks a Keycloak
    client-credentials token as a service account, so ds-auth authorizes it on
    its ``scope`` claim (vs a user token, which authorizes on groups).
    """
    token = pyjwt.encode(
        {
            "scope": scope,
            "sub": "test",
            "preferred_username": "service-account-svc-ds-test",
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def make_user_headers(groups: list[str] | None = None) -> dict:
    """A user bearer (group-based authority)."""
    token = pyjwt.encode(
        {
            "sub": "user-test",
            "email": "user@example.test",
            "groups": list(groups or []),
        },
        "secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}
