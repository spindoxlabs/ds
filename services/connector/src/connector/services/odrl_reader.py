"""Reading ODRL policies that arrive from elsewhere.

Both sides of an exchange read the same constraint and must agree on what it
says. The consumer reads the offer's purposes to validate a declaration
(`/consumer/negotiate`); the provider reads the *agreed* policy's purposes to
decide what a data-plane query may be made for
(`/internal/dataplane/authorize`). Two readers would eventually disagree, and
the disagreement would look like a permission difference between negotiating and
querying — the hardest kind to diagnose.

Mirrors `Purposes.java` in `services/edc-extensions`, which does the same job
inside the JVM. That one cannot be shared; this one must not be forked again.
"""
from __future__ import annotations

from typing import Any

# `odrl:purpose` as the catalogue serves it, and the IRI ODRL's context expands
# it to — `Purposes.COMPACT` / `Purposes.EXPANDED` on the Java side.
PURPOSE_OPERANDS = {
    "odrl:purpose",
    "purpose",
    "http://www.w3.org/ns/odrl/2/purpose",
}


def _operand_values(right: Any) -> list[str]:
    """Every value in a right operand, scalar or set-valued.

    A single-purpose dataset yields a scalar (`odrl:isA`); a multi-purpose one
    yields a **list** (`odrl:isAnyOf`), which is what the ODRL Information Model
    prescribes for set-based operators. Reading only the scalar form returns
    nothing for exactly the datasets whose purpose is ambiguous.
    """
    values: list[str] = []
    for item in right if isinstance(right, list) else [right]:
        if isinstance(item, dict):
            item = item.get("@id") or item.get("id") or item.get("@value")
        if isinstance(item, str) and item and item not in values:
            values.append(item)
    return values


def extract_purposes(policy: dict | None) -> list[str]:
    """Every purpose IRI a policy names, in document order.

    Walks the whole document rather than a known path: the same policy reaches
    us as a catalogue offer, as an EDC-stored agreement snapshot and as a
    counterparty's JSON-LD, and those nest their rules differently.
    """
    purposes: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            left = value.get("odrl:leftOperand") or value.get("leftOperand")
            if isinstance(left, dict):
                left = left.get("@id") or left.get("id")
            if left in PURPOSE_OPERANDS:
                right = value.get("odrl:rightOperand") or value.get("rightOperand")
                for purpose in _operand_values(right):
                    if purpose not in purposes:
                        purposes.append(purpose)
            for item in value.values():
                walk(item)

    walk(policy or {})
    return purposes
