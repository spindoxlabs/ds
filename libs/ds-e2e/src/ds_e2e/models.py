from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Step:
    name: str
    status: str
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "status": self.status}
        if self.detail:
            payload["detail"] = self.detail
        if self.data:
            payload["data"] = self.data
        return payload


@dataclass
class FlowResult:
    flow_name: str
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    steps: list[Step] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        """Any step failed — **or nothing was recorded at all**.

        `all([])` is `True`, so a flow that returned before asserting anything
        reported PASS (`E2E-01`). That is not a hypothetical: a flow that exits
        early on a setup problem, or one whose body is refactored to return
        before its first assertion, produced a green line with no steps under it
        — and `run_all`'s exit code said the dataspace was healthy.

        This is the same failure the ledger closes with — *a green check is not a
        check that ran* — inside the harness whose whole job is to notice it. An
        empty result stays a failure here for that reason, and `skipped` below
        does not rescue it: a flow that skipped says so in a step.
        """
        return not self.steps or any(s.status == "FAIL" for s in self.steps)

    @property
    def skipped(self) -> bool:
        """Nothing failed and nothing was actually checked (`SKIP`).

        A third outcome, added because two were not enough to describe `dev:*`:
        `fail-closed` stops a container that the host-process topology does not
        have, so the flow could not pass there however healthy the platform was,
        and `e2e:all` in dev carried a permanent red line. A suite with a
        standing failure is one people learn to scroll past, which costs more
        than the flow was worth.

        **The objection this has to answer** is written in `fail_closed.py` and
        is right: *a P0 check that silently skips is the defect this ledger keeps
        finding*. The word doing the work is **silently**. A skip is a step with
        a reason, counted apart from passes, printed in the summary and never
        folded into the exit code's "everything is fine" — so it cannot be
        mistaken for evidence. What it must never become is a way to make a red
        flow quiet: a skip is declared *before* the checks, by a flow that has
        established it cannot run, never in place of one that failed.
        """
        return (
            bool(self.steps)
            and not self.failed
            and not any(s.status == "PASS" for s in self.steps)
        )

    @property
    def passed(self) -> bool:
        """Something was checked, and nothing failed.

        A flow that skipped is not passing — `all(...)` over a list of skips
        would have said it was, which is the trap the third status introduces
        and the reason `passed` is defined against the other two rather than
        over the steps.
        """
        return not self.failed and not self.skipped

    def pass_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(
            Step(name, "PASS", detail, {k: v for k, v in data.items() if v is not None})
        )

    def fail_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(
            Step(name, "FAIL", detail, {k: v for k, v in data.items() if v is not None})
        )

    def skip_step(self, name: str, detail: str = "", **data: Any) -> None:
        """Record that this check could not run, and why.

        ``detail`` is not optional in practice: a skip with no reason is the
        silent skip the comment above refuses. Say what was missing and which
        target has it.
        """
        self.steps.append(
            Step(name, "SKIP", detail, {k: v for k, v in data.items() if v is not None})
        )

    @property
    def status(self) -> str:
        """`PASS` | `FAIL` | `SKIP` — the one place the three are ranked.

        Failure outranks a skip: a flow that ran some checks, failed one and
        skipped another is a failure, not a partial result.
        """
        if self.failed:
            return "FAIL"
        if self.skipped:
            return "SKIP"
        return "PASS"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "flow": self.flow_name,
            "generated_at": self.generated_at,
            "steps": [s.as_dict() for s in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def to_markdown(self) -> str:
        lines = [
            f"# E2E Report — {self.flow_name}",
            "",
            f"- Status: **{self.status}**",
            f"- Generated: {self.generated_at}",
            "",
            "## Steps",
        ]
        _ICONS = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭️"}
        for step in self.steps:
            icon = _ICONS.get(step.status, "❌")
            detail = f" — {step.detail}" if step.detail else ""
            lines.append(f"- {icon} `{step.name}`{detail}")
        lines.append("")
        return "\n".join(lines)
