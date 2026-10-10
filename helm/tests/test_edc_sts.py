"""Each EDC asks its own participant registry for its STS tokens.

Since the split (`D-47`, `D-51`) a participant's key and the secret its EDC presents to
its STS live in that participant's own registry release
(`IDENTITY_REGISTRY_PARTICIPANT_STS_SECRET`); the trust anchor mints no STS secret and
holds no participant key. The local stack sends `edc.iam.sts.oauth.token.url` to the
participant's own host. The chart sent it to the **anchor's** registry, which cannot
sign for the participant, so no DCP token, so no negotiation (found reading the first
cluster install's rendered EDC config, the deployment's rehearsal, 2026-10-09).

*Red:* point the STS URL at the authority namespace again, or drop the EDC's egress to
its own namespace's registry port.
"""

from __future__ import annotations

from collections.abc import Callable

from conftest import PilotRender, find

PARTICIPANTS = {"example-rec": "example-ds-example-rec", "example-dso": "example-ds-example-dso"}


def _edc_properties(objects: list[dict], name: str) -> dict[str, str]:
    cm = find(objects, "ConfigMap", f"ds-edc-{name}")
    text = cm["data"]["edc.properties"]
    props = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            props[k] = v
    return props


def test_every_edc_asks_its_own_registry_for_sts_tokens(
    render_pilot: Callable[..., PilotRender],
) -> None:
    objects = render_pilot().ok()
    for name, ns in PARTICIPANTS.items():
        url = _edc_properties(objects, name)["edc.iam.sts.oauth.token.url"]
        assert url == (
            f"http://ds-identity-registry-{name}.{ns}.svc.cluster.local:30005"
            f"/sts/did:web:{name}.ds.example.org/token"
        ), url


def test_every_edc_may_reach_its_own_registry(
    render_pilot: Callable[..., PilotRender],
) -> None:
    objects = render_pilot().ok()
    for name in PARTICIPANTS:
        policy = find(objects, "NetworkPolicy", f"ds-edc-{name}-egress")
        same_namespace_ports = {
            port["port"]
            for rule in policy["spec"]["egress"]
            for peer in rule.get("to") or []
            if peer == {"podSelector": {}}
            for port in rule.get("ports") or []
        }
        assert 30005 in same_namespace_ports, same_namespace_ports
