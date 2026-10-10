"""Every pod the charts render is admitted by the namespaces' Pod Security level.

`ds-namespaces` labels every dataspace namespace
`pod-security.kubernetes.io/enforce: restricted`, so the API server refuses a pod
whose containers miss any of the profile's container-level rules, with an event on
the ReplicaSet and nothing else: the release waits out its timeout and rolls back.
The first install on a cluster (the deployment's rehearsal, 2026-10-09) found the
participant registry's `identity` init container rendered without them.

Asserted over both renders and every pod-bearing object (Deployments, hook Jobs,
`helm test` Pods), init containers included. *Red:* give one container a security
context that does not come from `ds.containerSecurityContext`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import PilotRender, _render, containers, pod_spec, release_of

POD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Pod"}


def _violations(objects: list[dict]) -> list[str]:
    """The `restricted` profile's rules, per container (Kubernetes Pod Security
    Standards): no privilege escalation, every capability dropped, non-root,
    and a RuntimeDefault or Localhost seccomp profile — the last two may be set
    on the pod instead."""
    found = []
    for obj in objects:
        if obj["kind"] not in POD_KINDS:
            continue
        spec = pod_spec(obj)
        pod_ctx = spec.get("securityContext") or {}
        for c in containers(obj, init=True):
            ctx = c.get("securityContext") or {}
            where = f"{obj['kind']}/{obj['metadata']['name']} ({release_of(obj)}) container {c['name']}"
            if ctx.get("allowPrivilegeEscalation") is not False:
                found.append(f"{where}: allowPrivilegeEscalation is not false")
            if "ALL" not in ((ctx.get("capabilities") or {}).get("drop") or []):
                found.append(f"{where}: capabilities.drop lacks ALL")
            if ctx.get("privileged"):
                found.append(f"{where}: privileged")
            if not ctx.get("runAsNonRoot", pod_ctx.get("runAsNonRoot")):
                found.append(f"{where}: runAsNonRoot is not true")
            seccomp = (ctx.get("seccompProfile") or pod_ctx.get("seccompProfile") or {}).get("type")
            if seccomp not in ("RuntimeDefault", "Localhost"):
                found.append(f"{where}: seccompProfile is {seccomp!r}")
    return found


def test_every_example_pod_meets_the_restricted_profile(helm_copy: Path) -> None:
    assert _violations(_render(helm_copy)) == []


def test_every_pilot_pod_meets_the_restricted_profile(
    render_pilot: Callable[..., PilotRender],
) -> None:
    objects = render_pilot().ok()
    assert any(o["kind"] in POD_KINDS for o in objects)
    assert _violations(objects) == []


@pytest.mark.parametrize("missing", ["allowPrivilegeEscalation", "capabilities"])
def test_the_check_names_a_container_that_misses_a_rule(missing: str) -> None:
    """The check itself can fail (a test that cannot fail is not a test)."""
    ctx = {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}}
    del ctx[missing]
    pod = {
        "kind": "Deployment",
        "metadata": {"name": "x", "labels": {"app.kubernetes.io/instance": "r"}},
        "spec": {
            "template": {
                "spec": {
                    "securityContext": {
                        "runAsNonRoot": True,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "initContainers": [{"name": "init", "securityContext": ctx}],
                    "containers": [
                        {
                            "name": "main",
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        }
                    ],
                }
            }
        },
    }
    assert [v for v in _violations([pod]) if "container init" in v]
    assert not [v for v in _violations([pod]) if "container main" in v]
