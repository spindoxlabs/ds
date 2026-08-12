"""Measure `docs/rulebook/` against `docs/blueprints/` and against the tests.

The rulebook records what this data space decided; the blueprints state what a
data space owes. This package answers two questions about the pair, and it
answers them the same way on every machine because it reads only files:

1. **Does a rule that claims enforcement have a test that names it?**
   Evidence lives on the test — `@pytest.mark.rule`, `@Tag("rule:…")`, a flow's
   `rules` attribute, a Playwright title tag — so it moves with a rename and
   vanishes with a deletion. The status column becomes derivable.

2. **Is every binding blueprint row accounted for?** `docs/rulebook/coverage.yaml`
   maps each `must` and `should` row to the rules that answer it, or records it
   as open or declined with a reason. Rows nobody has looked at are
   `unassessed`, which is a state rather than a silence.

See `docs/development/conformance.md`.
"""

from .assess import assess
from .model import Assessment, Evidence, Requirement, Rule
from .report import Verdict, judge_all, render, summarise

__all__ = [
    "Assessment",
    "Evidence",
    "Requirement",
    "Rule",
    "Verdict",
    "assess",
    "judge_all",
    "render",
    "summarise",
]
