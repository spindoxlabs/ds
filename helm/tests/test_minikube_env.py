"""The `minikube` environment renders a production-posture deployment with generic names.

`helmfile -e minikube` is what `helm/minikube/minikube.sh` installs on a local cluster
(docs/deployment/local-cluster.md): the anchor and two participants, every guard armed
(the secret policy runs: it is not `example`), images built into the node, the
did:web internal allowance for the node's address (ADR-0029). Secrets are generated
here, as `minikube.sh secrets` generates them there.

*Red:* drop the environment, let it render without DS_MK_NODE_IP, or let it pull images.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import _objects, container_env, containers, find, pilot_secrets

NODE_IP = "192.168.49.2"


def _render(helm_copy: Path, node_ip: str | None) -> subprocess.CompletedProcess[str]:
    values = yaml.safe_load((helm_copy / "minikube" / "values.yaml.gotmpl").read_text())
    (helm_copy / "minikube" / "secrets.yaml").write_text(yaml.safe_dump(pilot_secrets(values)))
    env = {k: v for k, v in os.environ.items() if k != "DS_MK_NODE_IP"}
    if node_ip:
        env["DS_MK_NODE_IP"] = node_ip
    return subprocess.run(
        ["helmfile", "-e", "minikube", "template", "--skip-deps"],
        cwd=helm_copy, capture_output=True, text=True, env=env, check=False,
    )


@pytest.fixture(scope="module")
def minikube(helm_copy: Path) -> list[dict]:
    result = _render(helm_copy, NODE_IP)
    assert result.returncode == 0, result.stderr
    return _objects(result.stdout)


def test_it_does_not_render_without_the_nodes_address(helm_copy: Path):
    result = _render(helm_copy, None)
    assert result.returncode != 0
    assert "DS_MK_NODE_IP" in result.stderr


def test_the_anchor_and_both_participants_render(minikube):
    names = {o["metadata"]["name"] for o in minikube if o["kind"] == "Deployment"}
    for expected in (
        "ds-identity-registry",
        "ds-identity-registry-example-rec",
        "ds-identity-registry-example-dso",
        "ds-edc-example-rec",
        "ds-edc-example-dso",
        "ds-connector-example-rec",
        "ds-connector-example-dso",
        "ds-portal-example-rec",
    ):
        assert expected in names


def test_every_ds_container_is_production_and_built_locally(minikube):
    for obj in minikube:
        if obj["kind"] not in {"Deployment", "Job", "Pod"}:
            continue
        for c in containers(obj, init=True):
            if "spindoxlabs" not in c["image"]:
                continue
            assert c["image"].endswith(":minikube"), c["image"]
            assert c.get("imagePullPolicy") == "Never", (obj["metadata"]["name"], c["name"])
        if any("spindoxlabs" in c["image"] for c in containers(obj)) and obj["kind"] == "Deployment":
            assert container_env(obj).get("DS_ENV") == "production", obj["metadata"]["name"]


def test_every_registry_admits_the_node_address_for_the_dataspace_hosts_only(minikube):
    for name in ("ds-identity-registry", "ds-identity-registry-example-rec", "ds-identity-registry-example-dso"):
        env = container_env(find(minikube, "Deployment", name))
        assert env["IDENTITY_REGISTRY_DID_WEB_INTERNAL_HOSTS"] == ".ds.test"
        assert env["IDENTITY_REGISTRY_DID_WEB_INTERNAL_NETWORKS"] == f"{NODE_IP}/32"


def test_the_issuer_is_the_bundled_realm_on_the_local_domain(minikube):
    env = container_env(find(minikube, "Deployment", "ds-connector-example-dso"))
    assert env["CONNECTOR_OIDC_ISSUER_URL"] == "https://keycloak.ds.test/realms/dataspaces"
    assert env["CONNECTOR_PARTICIPANT_DID"] == "did:web:example-dso.ds.test"
