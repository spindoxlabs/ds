from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    steps: list[Step] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(s.status == "PASS" for s in self.steps)

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
