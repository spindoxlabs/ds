"""The declared payload model and the rendered one, compared against a running stack.

`T-3`'s live half, and the assertion the semantic-model seam exists for. A
producer declares `dcat.conforms_to`
in `governance.yaml`; ds validates it, publishes it into the DSP catalogue as
`dct:conformsTo` and serves a local copy at `/ns/{slug}`. **None of that
establishes that the rows a consumer receives mean what the IRI says** — a
producer could declare any model and return anything, and until the data plane
implemented the other end there was nothing to compare the declaration against.

There is now. The celine `dataset-api` derives `GET /catalogue/{id}/vocabulary`
from the dataset's mapping spec and carries `dct:conformsTo` on its catalogue
entry; `services/dataset-api-mock` answers the same shape. So this flow reads
both ends of one fact and asserts they agree:

    ds        → EDC asset properties, `dct:conformsTo` (what the producer declares)
    data plane → `/catalogue/{id}` `dct:conformsTo` (what the renderer states)
                 `/catalogue/{id}/vocabulary`      (what the columns mean)

`libs/governance/tests/test_semantic_model_contract.py` pins the shape without a
stack. This is the part that could not be unit-tested: whether the two
implementations, running, actually say the same thing.

**Every data plane, and each named.** `settings.data_planes` is iterated rather
than `dataset_api_url` alone (`T-1`, `E2E-13`): the platform has two
implementations of this surface, a run exercises whichever holds the port, and
a seam implemented on one and missing on the other would otherwise pass or fail
depending on which was up — with nothing in the output saying which it was.
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

from ds_e2e.flows.base import BaseFlow
from ds_e2e.models import FlowResult

log = logging.getLogger(__name__)

#: The spellings one `dct:conformsTo` arrives under. EDC compacts asset
#: properties against the context the asset was created with, and the connector
#: declares `dct` only when a property uses it — so both the compacted CURIE and
#: the expanded IRI are legitimate readings of the same property, and a flow that
#: knew only one would report a missing declaration for a present one.
_CONFORMS_TO_KEYS = (
    "dct:conformsTo",
    "http://purl.org/dc/terms/conformsTo",
    "conformsTo",
)


def _conforms_to(document: Any) -> str | None:
    """The model IRI in a document, whichever of the three spellings it uses.

    Accepts both `{"@id": iri}` and a bare string, and normalises to the IRI.
    Reading the node form is the point — a bare string expands to a *literal* in
    JSON-LD, so it is a defect worth reporting separately rather than one to
    fail to parse (see `_is_node_form`).
    """
    if not isinstance(document, dict):
        return None
    for holder in (document, document.get("properties") or {}):
        if not isinstance(holder, dict):
            continue
        for key in _CONFORMS_TO_KEYS:
            value = holder.get(key)
            if isinstance(value, dict) and value.get("@id"):
                return str(value["@id"])
            if isinstance(value, str) and value:
                return value
    return None


def _is_node_form(document: Any) -> bool:
    """`{"@id": …}` rather than a bare string, for the holder that has it."""
    if not isinstance(document, dict):
        return False
    for holder in (document, document.get("properties") or {}):
        if not isinstance(holder, dict):
            continue
        for key in _CONFORMS_TO_KEYS:
            if key in holder:
                return isinstance(holder[key], dict) and "@id" in holder[key]
    return False


class SemanticModelFlow(BaseFlow):
    name = "semantic-model"
    description = (
        "The payload model a producer declares is the one every data plane "
        "states and serves a vocabulary for"
    )
    rules = ("M-4", "M-7", "M-8")

    def execute(self) -> FlowResult:
        s = self.settings
        result = FlowResult(flow_name=self.name)

        if not self._check_health(result):
            return result
        try:
            headers = self.http.bearer_headers()
        except Exception as exc:
            result.fail_step("service token", str(exc))
            return result

        declared = self._declared_models(result, headers)
        if declared is None:
            return result

        self._models_resolve_on_the_participant(result, declared, headers)

        for label, url in s.data_planes:
            self._plane_agrees(result, label, url, declared)

        return result

    # ── What ds declares ─────────────────────────────────────────────────────

    def _providers(self) -> tuple[tuple[str, str], ...]:
        s = self.settings
        return (
            ("rec", s.connector_url),
            ("grid-operator", s.grid_operator_connector_url),
        )

    def _declared_models(
        self, result: FlowResult, headers: dict[str, str]
    ) -> dict[str, tuple[str, str]] | None:
        """`{asset id: (model IRI, declaring participant)}` from the EDC assets.

        Read from the **published assets**, not from `governance.yaml`. The file
        is the producer's intent; the asset is what a consumer discovers, and
        the gap between them is a sync away. A comparison against the file would
        stay green through a connector that never synced — and the first thing
        this flow found was precisely that gap, with the property never reaching
        EDC at all.

        **No node-form check here.** An EDC asset property is a flat value, so
        the IRI arrives as a string by construction; `{"@id": …}` is required of
        the *catalogue* documents, which are JSON-LD, and is asserted there.
        """
        declared: dict[str, tuple[str, str]] = {}
        for participant, url in self._providers():
            assets_url = f"{url}/provider/assets"
            status, body = self.http.raw("GET", assets_url, headers=headers)
            if status != 200 or not isinstance(body, list):
                result.fail_step(
                    "read published assets",
                    f"{participant} did not serve its assets ({status})",
                    url=f"{url}/provider/assets",
                    body=str(body)[:200],
                )
                return None
            for asset in body:
                asset_id = str(asset.get("@id") or asset.get("id") or "")
                if not asset_id:
                    continue
                if iri := _conforms_to(asset):
                    declared[asset_id] = (iri, participant)

        if not declared:
            # **The loud form of "not verified"** the plan asks for. A flow that
            # compared nothing and reported PASS would state agreement between
            # one party and nothing — which is what this seam shipped as, and
            # the reason it was unfalsifiable for a release.
            result.fail_step(
                "a model is declared",
                "no published asset declares dct:conformsTo, so nothing exercises "
                "the semantic-model seam — this run verified no agreement at all",
                providers=[p for p, _ in self._providers()],
            )
            return None

        result.pass_step(
            "a model is declared",
            f"{len(declared)} published asset(s) declare a payload model",
            assets={asset: iri for asset, (iri, _) in declared.items()},
        )
        return declared

    def _models_resolve_on_the_participant(
        self,
        result: FlowResult,
        declared: dict[str, tuple[str, str]],
        headers: dict[str, str],
    ) -> None:
        """`M-8` — a declared IRI in the participant's own namespace resolves.

        Scoped to the declaring participant's *own* namespace deliberately: an
        external standard is a legitimate reference whether or not it is
        mirrored here (`V-6`), but an IRI a participant coins and does not serve
        is an address it published and does not answer at.
        """
        connectors = dict(self._providers())
        for asset, (iri, participant) in sorted(declared.items()):
            base = connectors[participant]
            registry = self.http.get(f"{base}/ns/vocabularies", raise_for_status=False)
            # A bare list is what `/ns/vocabularies` serves; the wrapped form is
            # accepted too rather than assumed absent, since reading the shape
            # wrong here would report every model as unserved.
            entries = (
                registry
                if isinstance(registry, list)
                else (registry or {}).get("vocabularies") or []
            )
            entry = next(
                (v for v in entries if isinstance(v, dict) and v.get("iri") == iri),
                None,
            )
            if entry is None:
                if participant in iri:
                    result.fail_step(
                        "declared model resolves",
                        f"{participant} declares {iri} — its own namespace — and "
                        f"serves no vocabulary for it",
                        asset=asset,
                    )
                else:
                    result.pass_step(
                        "declared model resolves",
                        f"{asset} names {iri}, a model this participant does not "
                        "publish — legitimate unmirrored (V-6)",
                    )
                continue

            slug = entry.get("slug") or ""
            status, media_type, _ = self.http.get_document(f"{base}/ns/{quote(slug)}")
            if status != 200:
                result.fail_step(
                    "declared model resolves",
                    f"{iri} is registered by {participant} as {slug!r} but "
                    f"GET /ns/{slug} answers {status}",
                    asset=asset,
                )
                continue
            result.pass_step(
                "declared model resolves",
                f"{asset} → {iri}, served by {participant} at /ns/{slug}",
                media_type=media_type,
            )

    # ── What the data plane states ───────────────────────────────────────────

    def _plane_agrees(
        self,
        result: FlowResult,
        label: str,
        base: str,
        declared: dict[str, tuple[str, str]],
    ) -> None:
        try:
            self.http.get(f"{base}/health")
        except Exception as exc:
            # `E2E-14`: one unreachable service used to raise out of the runner
            # and end the run with a traceback and zero results. A configured
            # plane that is down verified nothing, and that is a legible failure
            # rather than an exception.
            result.fail_step(
                f"coverage — {label}",
                f"{label} is configured as a data plane and is unreachable, so "
                f"nothing was compared against it: {exc}",
            )
            return

        listed = self._listed_entries(result, label, base)
        if listed is None:
            return

        compared: list[str] = []
        absent: list[str] = []

        for asset, (iri, _participant) in sorted(declared.items()):
            entry = listed.get(asset)
            if entry is None:
                # This plane does not hold this dataset. Recorded rather than
                # failed: which datasets a deployment's data plane carries is
                # inventory, and this flow compares *declarations* — but a
                # silent skip would let the coverage shrink to nothing while
                # every step still read PASS.
                absent.append(asset)
                continue

            self._single_entry_agrees(result, label, base, asset, entry)
            compared.append(asset)
            rendered = _conforms_to(entry)
            if rendered is None:
                result.fail_step(
                    f"declaration matches — {label}",
                    f"ds publishes {asset} as conforming to {iri}; this plane's "
                    "catalogue entry states no model at all, so the declaration "
                    "is a claim nothing backs",
                    asset=asset,
                )
                continue
            if rendered != iri:
                result.fail_step(
                    f"declaration matches — {label}",
                    f"{asset}: ds publishes {iri}, this plane renders {rendered}",
                    asset=asset,
                    declared=iri,
                    rendered=rendered,
                )
                continue
            if not _is_node_form(entry):
                result.fail_step(
                    f"declaration matches — {label}",
                    f"{asset}: the model is stated as a literal, not a node "
                    "reference — a consumer following it gets text, not a model",
                    asset=asset,
                )
                continue
            result.pass_step(
                f"declaration matches — {label}",
                f"{asset} → {iri}, stated by both ends",
            )

            self._vocabulary_agrees(result, label, base, asset, iri)

        if not compared:
            result.fail_step(
                f"coverage — {label}",
                "this plane holds none of the datasets ds publishes with a "
                "declared model, so nothing was compared against it",
                absent=absent,
            )
            return
        result.pass_step(
            f"coverage — {label}",
            f"{len(compared)} dataset(s) compared on {label}",
            compared=compared,
            # Named, so a shrinking comparison is visible in the report rather
            # than looking like a smaller run.
            not_held_by_this_plane=absent or None,
        )

    def _listed_entries(
        self, result: FlowResult, label: str, base: str
    ) -> dict[str, dict[str, Any]] | None:
        """`{dataset id: entry}` from `GET /catalogue`.

        **The list, not one read per asset.** The contract names both routes, and
        the list is the one a consumer browses — it is also the one that works on
        both implementations: the real dataset-api registers an HTML view at
        `/catalogue/{id}` *before* its JSON route, so a single-entry read there
        never returns the DCAT document at all. Comparing from the list keeps
        that defect from collapsing this flow's coverage to nothing, and
        `_single_entry_agrees` reports it in its own step rather than hiding it.

        Two shapes, because there are two implementations: DCAT-AP
        (`dcat:dataset`, keyed by `dct:identifier`) and the mock's
        `{"datasets": [...]}`.
        """
        status, body = self.http.raw("GET", f"{base}/catalogue")
        if status != 200:
            result.fail_step(
                f"coverage — {label}",
                f"the catalogue this plane publishes answers {status}, so nothing "
                "could be compared against it",
            )
            return None

        rows = (
            body.get("dcat:dataset") or body.get("datasets") or []
            if isinstance(body, dict)
            else body if isinstance(body, list) else []
        )
        if isinstance(rows, dict):
            rows = [rows]

        entries: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in ("dct:identifier", "asset_id", "id", "@id"):
                if identifier := row.get(key):
                    entries[str(identifier)] = row
                    break
        return entries

    def _single_entry_agrees(
        self,
        result: FlowResult,
        label: str,
        base: str,
        asset: str,
        listed: dict[str, Any],
    ) -> None:
        """`GET /catalogue/{id}` serves what the list served.

        Its own step because it is its own claim: the contract names this route
        alongside the list, and a consumer that resolves one dataset rather than
        browsing all of them uses it. A 500 here is not a smaller failure than a
        wrong model — it is a route a consumer cannot use.
        """
        entry_url = f"{base}/catalogue/{quote(asset, safe='')}"
        status, entry = self.http.raw("GET", entry_url)
        if status != 200 or not isinstance(entry, dict):
            result.fail_step(
                f"single entry resolves — {label}",
                f"GET /catalogue/{asset} answers {status}; the catalogue lists "
                "this dataset, so the two routes disagree about whether it exists",
                asset=asset,
                body=str(entry)[:200],
            )
            return
        if _conforms_to(entry) != _conforms_to(listed):
            result.fail_step(
                f"single entry resolves — {label}",
                f"{asset} states one model in the catalogue listing and another "
                "when resolved on its own",
                listed=_conforms_to(listed),
                resolved=_conforms_to(entry),
            )
            return
        result.pass_step(
            f"single entry resolves — {label}",
            f"{asset} resolves on its own and states the same model as the listing",
        )

    def _vocabulary_agrees(
        self, result: FlowResult, label: str, base: str, asset: str, iri: str
    ) -> None:
        """The locator answers, and names the identity the catalogue named."""
        url = f"{base}/catalogue/{quote(asset, safe='')}/vocabulary"
        status, media_type, document = self.http.get_document(url)

        if status != 200:
            result.fail_step(
                f"vocabulary is served — {label}",
                f"{asset} declares {iri} and its vocabulary answers {status}. "
                "404 here means 'no mapping', which contradicts the model its "
                "own catalogue entry states",
                asset=asset,
                url=url,
            )
            return
        if media_type != "application/ld+json":
            result.fail_step(
                f"vocabulary is served — {label}",
                f"{asset}'s vocabulary is served as {media_type!r}; a consumer "
                "negotiating for JSON-LD skips it",
                asset=asset,
            )
            return
        if not isinstance(document, dict) or not document.get("@context"):
            result.fail_step(
                f"vocabulary is served — {label}",
                f"{asset}'s vocabulary carries no @context, so it maps no column "
                "to any term",
                asset=asset,
                keys=sorted(document.keys()) if isinstance(document, dict) else None,
            )
            return

        stated = _conforms_to(document)
        if stated and stated != iri:
            result.fail_step(
                f"vocabulary is served — {label}",
                f"{asset}: the catalogue states {iri} and the vocabulary states "
                f"{stated} — one dataset advertising two models",
                asset=asset,
            )
            return

        result.pass_step(
            f"vocabulary is served — {label}",
            f"{asset} serves a JSON-LD context for {len(document['@context'])} term(s)",
            asset=asset,
        )
