"""The `POST /internal/dataplane/authorize` wire contract.

The connector answers it; every data-plane PEP consumes it — the celine
`dataset-api` in a deployment, `services/dataset-api-mock` in a local run. It
lives here rather than in the connector because a shape with more than one
implementer belongs to neither of them, and because what it carries is
governance's own `RowFilter` with the consenting principals resolved into it.

**The row filter travels whole.** Handler, args and principals — not a column
and a list of ids. The handler is what knows how a person maps to values in the
column: `rec_registry` resolves a member to their devices, `direct_user_match`
matches the subject directly. A decision reduced to a column forces the
receiving PEP to assume one of them, and that is exactly what went wrong: the
connector emitted `{handler, args, principals}` while the mock read
`{column, subject_ids}`, so every *allow* carrying a filter was an unhandled
`KeyError` — a 500 in the one code path whose whole job is to narrow rows.

**Unknown fields are refused, on purpose.** These models are evidence of an
authorization decision, and the dangerous direction of drift is one-way: a PDP
that adds a narrowing an older PEP silently ignores serves rows it should have
withheld. `extra="forbid"` turns that into a loud parse failure on the PEP side,
which is a denial. The cost is real and accepted — upgrading the connector ahead
of a PEP stops the data plane rather than widening it. Rulebook `CR-4`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

#: A dataset whose subject column holds the principal itself, needing no
#: registry in between. `celine-utils/schema/governance.schema.json` names it,
#: and it is what the legacy `user_filter_column` spelling migrates to on both
#: sides — see `subject_column`.
DIRECT_USER_MATCH = "direct_user_match"

ALLOW = "allow"
DENY = "deny"


class DecisionCache(BaseModel):
    """How long the PEP may reuse this decision without asking again."""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int


class DataplaneRowFilter(BaseModel):
    """A row filter as the PDP puts it on the wire.

    A verdict of *allow* carrying one of these means **allow these rows**, never
    allow the dataset. A PEP that cannot apply the filter has not been permitted
    to serve unfiltered rows — it has been given an instruction it does not
    understand, and must refuse.
    """

    model_config = ConfigDict(extra="forbid")

    handler: str
    #: Governance's `RowFilter.args`, verbatim. `{"column": ...}` for every
    #: handler in use today, and deliberately open: a handler defines its own
    #: arguments and the PDP does not interpret them.
    args: dict[str, Any] = Field(default_factory=dict)
    #: Identifiers **native to the receiving system** — usernames the handler can
    #: resolve, never subject DIDs. A DID here is derived from an unsalted email
    #: hash, so it re-identifies the subject to whoever later holds the payload.
    principals: list[str] = Field(default_factory=list)


class DatasetVerdict(BaseModel):
    """One dataset's answer.

    Per dataset because one SQL statement can touch several, and the envelope's
    answer is the strictest of them.
    """

    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    decision: str
    reason: str | None = None
    #: `None` on an *allow* means no filter applies — every row may leave. It
    #: never means "a filter was intended but could not be built": that case is
    #: a deny, because the two are indistinguishable to the PEP.
    row_filter: DataplaneRowFilter | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW


class DataplaneDecision(BaseModel):
    """The whole answer to "may this data-plane request return rows, and which?"

    `decision` is the strictest of `datasets`; a PEP that reads only the envelope
    is correct but coarse, and one that reads only the per-dataset verdicts
    without the envelope is wrong on a join.
    """

    model_config = ConfigDict(extra="forbid")

    decision: str
    reason: str | None = None
    #: Free text expanding `reason`, for a human reading a log. Never parsed.
    detail: str | None = None
    agreement_id: str
    transfer_id: str | None = None
    purpose: list[str] = Field(default_factory=list)
    datasets: list[DatasetVerdict] = Field(default_factory=list)
    cache: DecisionCache | None = None

    @property
    def allowed(self) -> bool:
        return self.decision == ALLOW

    def verdict_for(self, dataset_id: str) -> DatasetVerdict | None:
        """The verdict naming `dataset_id`, or `None` if the PDP named no such dataset.

        `None` is not an allow. A PEP asking about a dataset the decision does
        not mention has learned nothing about it and must refuse it.
        """
        for verdict in self.datasets:
            if verdict.dataset_id == dataset_id:
                return verdict
        return None
