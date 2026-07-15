import jwt as pyjwt


def make_headers(scope: str = "connector.admin") -> dict:
    token = pyjwt.encode({"scope": scope, "sub": "test"}, "secret", algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}
