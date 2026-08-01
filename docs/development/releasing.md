# Releasing

The repository has **one version**. The services are coupled by internal contracts — the
connector's `/internal/*` PDP, the DSP/DCP exchange, the dataplane authorize callback — and one
helmfile deploys them together, so "which version is this dataspace running" has to have a
single answer.

Cutting a release is a deliberate local act. Publishing is not: the only thing that publishes
anything is a `v*` tag arriving on GitHub.

## Cutting a release

From a clean `main`, up to date with `origin`:

```bash
task release:dry     # what would the next version be, and what would it stamp
task release         # do it
```

`task release` runs [python-semantic-release](https://python-semantic-release.readthedocs.io/)
against `releaserc.toml`, which:

1. computes the bump from the conventional-commit log since the last tag —
   `feat:` minor, `fix:`/`perf:` patch, everything else no bump;
2. stamps the new version into every `pyproject.toml`, `services/portal/package.json`, and
   every chart's `appVersion`;
3. writes `CHANGELOG.md`, commits, and tags `vX.Y.Z`.

It then shows you the commit and pushes with `--follow-tags`. Nothing is uploaded to PyPI and
no GitHub Release is created — **the container images are the release artifact.**

Pre-1.0 is configured explicitly (`allow_zero_version`, `major_on_zero = false`): a `feat:`
takes `0.3.1` to `0.4.0`, not to `1.0.0`.

### What is not stamped

Chart `version:` — chart packaging is pinned by each `Chart.lock` and its vendored
`ds-common-0.1.0.tgz`. Only `appVersion` moves, and that is what `ds.image` resolves the image
tag from. `ds-oauth2-proxy`'s `appVersion` is upstream's `7.11.0` and is left alone.

## What CI does with the tag

`.github/workflows/release.yml` builds and pushes, for the tagged commit:

| Image | From |
|---|---|
| `ghcr.io/spindoxlabs/ds-connector` | `services/connector/Dockerfile` |
| `ghcr.io/spindoxlabs/ds-identity-registry` | `services/identity-registry/Dockerfile` |
| `ghcr.io/spindoxlabs/ds-provenance` | `services/provenance/Dockerfile` |
| `ghcr.io/spindoxlabs/ds-federated-catalog` | `services/federated-catalog/Dockerfile` |
| `ghcr.io/spindoxlabs/ds-portal` | `services/portal/Dockerfile` |
| `ghcr.io/spindoxlabs/ds-edc-connector` | `services/edc-connector/Dockerfile` |

each tagged `X.Y.Z` and `latest`. The names are not free: they are what
`helm/charts/ds-common/templates/_helpers.tpl` composes from `global.image.prefix` and each
chart's `service.name`. Renaming one breaks a deployment, not a build.

`dataset-api-mock` is not published. It is a dev fixture standing in for celine's
`dataset-api` and is never deployed.

Every Dockerfile builds with the **repo root as context** — the Python services install `libs/`
as path dependencies.

### Branch pushes publish nothing

Deliberate, while the platform is early: a `:dev` tag that moves under a running cluster is a
worse problem than not having one. Two ways to get an image without cutting a release:

- **Run the workflow manually** — `workflow_dispatch` takes a `ref` and an image `tag`
  (default `dev`).
- **Turn it on permanently** — uncomment `branches: [main]` in `release.yml`. The matching
  `type=raw,value=dev` rule is already in the metadata step, dormant.

### The EDC base image

The Java build needs `ghcr.io/spindoxlabs/ds-edc-base:<edcVersion>`, a Gradle dependency cache
with no source in it, published by `.github/workflows/edc-base.yml`. It rebuilds only when a
`build.gradle.kts` or `Dockerfile.base` changes.

**On a fresh registry, run that workflow once by hand** — the release job checks for the image
and fails with a clear message rather than starting a ten-minute BOM resolution. When you bump
`edcVersion`, bump `EDC_VERSION` in the workflow in the same commit; the workflow asserts the
two agree.

Locally nothing changes: `task edc:build` and `task edc:docker` still use the `ds-edc-base:0.16.0`
that `task edc:base` builds. The Dockerfile takes it as `--build-arg EDC_BASE_IMAGE`, defaulting
to the local name.

## Deploying a release

A checkout of tag `vX.Y.Z` already carries `appVersion: X.Y.Z` in every chart, so:

```bash
helmfile -e production apply
```

deploys `X.Y.Z`. To deploy a different release from the same checkout — a rollback — set
`DS_IMAGE_TAG`; see [Configuration · Choosing a release](../deployment/configuration.md#choosing-a-release).
