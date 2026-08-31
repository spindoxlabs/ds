"""Evidence records for operator-provisioned consent.

`POST /consent/admin/shares` refuses to *grant* without evidence of what the
person was shown: which system asked, which revision of the text, and the hash of
the exact bytes rendered. A harness that sends a token evidence record would pass
its own probes while proving nothing, so the hash here is a real digest over the
string this harness stands behind as "the text shown".

Withdrawal (`enabled: false`) needs no evidence and must not be given any — a
person may always stop, and a flow that supplies proof to stop would hide a
regression in that rule.
"""

from __future__ import annotations

import hashlib
from typing import Any

CONSENT_TEXT = (
    "End-to-end verification: the subject agrees to share the named dataset "
    "with parties inside the circle, for the offer's declared purpose."
)
CONSENT_TEXT_VERSION = "e2e-1.0"


def legal_basis(submission_ref: str, *, source: str = "ds-e2e") -> dict[str, Any]:
    """A complete evidence record, as an external caller must supply it."""
    return {
        "source": source,
        "consent_text_version": CONSENT_TEXT_VERSION,
        "rendered_text_sha256": hashlib.sha256(CONSENT_TEXT.encode()).hexdigest(),
        "locale": "en",
        "submission_ref": submission_ref,
    }
