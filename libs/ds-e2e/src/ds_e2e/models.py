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
    def passed(self) -> bool:
        """Every recorded step passed, **and at least one was recorded**.

        `all([])` is `True`, so a flow that returned before asserting anything
        reported PASS (`E2E-01`). That is not a hypothetical: a flow that exits
        early on a setup problem, or one whose body is refactored to return
        before its first assertion, produced a green line with no steps under it
        — and `run_all`'s exit code said the dataspace was healthy.

        This is the same failure the ledger closes with — *a green check is not a
        check that ran* — inside the harness whose whole job is to notice it.
        """
        return bool(self.steps) and all(s.status == "PASS" for s in self.steps)

    def pass_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(
            Step(name, "PASS", detail, {k: v for k, v in data.items() if v is not None})
        )

    def fail_step(self, name: str, detail: str = "", **data: Any) -> None:
        self.steps.append(
            Step(name, "FAIL", detail, {k: v for k, v in data.items() if v is not None})
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
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
            f"- Status: **{'PASS' if self.passed else 'FAIL'}**",
            f"- Generated: {self.generated_at}",
            "",
            "## Steps",
        ]
        for step in self.steps:
            icon = "✅" if step.status == "PASS" else "❌"
            detail = f" — {step.detail}" if step.detail else ""
            lines.append(f"- {icon} `{step.name}`{detail}")
        lines.append("")
        return "\n".join(lines)
