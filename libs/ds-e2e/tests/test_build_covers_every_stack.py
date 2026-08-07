"""`task build` must rebuild every participant stack, or say why it does not.

**Why this lives here.** The invariant spans the root `Taskfile.yml` and the set
of compose files, so it belongs to no service. `libs/ds-e2e` is the unit whose
subject *is* the whole running dataspace, and it runs in CI, so the check lands
where a broken topology is already this unit's problem.

**The defect.** `build` ran three commands: the root compose, then
`-f docker-compose.rec.yml`, then `-f docker-compose.third-party.yml`. `DID-15`
added the grid operator as a second provider with its own compose file and did
not add a fourth line. So from that commit, `task build` rebuilt two of the
three participant stacks and left the third on its previous image — and a
rebuild-then-restart produced a dataspace running half old code with every
container healthy and nothing to indicate it. `edc:restart` had the identical
defect and the same commit fixed it there; nobody looked at `build`.

Found 2026-08-05 while rebuilding to run `task e2e:all`, which is the only
reason it surfaced at all: the grid operator's connector kept answering, from
the image it had.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TASKFILE = ROOT / "Taskfile.yml"

#: Compose files `task build` may skip, each with the reason it is exempt.
#: Adding an entry here is the only way to exclude a stack, which is the point:
#: a skip has to be a decision someone wrote down, not a line nobody added.
DECLARED_SKIPS = {
    "docker-compose.override.yml": (
        "compose applies it automatically to the root project; it defines no build"
    ),
    "docker-compose.dataset-api.yml": (
        "builds celine's rec-registry and dataset-api from optional sibling "
        "checkouts (REC_REGISTRY_PATH / DATASET_API_PATH) — building it here "
        "would fail on a machine that does not have them"
    ),
}


def _build_task_script() -> str:
    """The `build:` task's commands, as raw text."""
    text = TASKFILE.read_text(encoding="utf-8")
    start = text.index("\n  build:\n")
    # Up to the next task at the same indent level.
    rest = text[start + 1 :]
    end = re.search(r"\n  [a-zA-Z][\w:-]*:\n", rest)
    return rest[: end.start()] if end else rest


def _stacks_on_disk() -> set[str]:
    return {p.name for p in ROOT.glob("docker-compose.*.yml")}


@pytest.fixture(scope="module")
def script() -> str:
    return _build_task_script()


def test_every_stack_is_built_or_declared(script: str):
    """No compose file may be silently absent from `task build`."""
    covered_by_glob = "docker-compose.*.yml" in script
    missing = []
    for stack in sorted(_stacks_on_disk()):
        if stack in DECLARED_SKIPS:
            continue
        if covered_by_glob or stack in script:
            continue
        missing.append(stack)
    assert not missing, (
        f"`task build` does not rebuild {missing} — add it, or declare it in "
        f"DECLARED_SKIPS with the reason it is exempt"
    )


def test_declared_skips_are_skipped_in_the_task(script: str):
    """A stack this test exempts must actually be exempted by the task.

    Otherwise the two drift the other way: the test says a file is deliberately
    not built while the task builds it, and the exemption stops meaning anything.
    """
    for stack in DECLARED_SKIPS:
        if not (ROOT / stack).exists():
            continue
        assert stack in script, (
            f"{stack} is declared exempt here but the build task never names it — "
            f"if the exemption is real it belongs in the task, with the reason"
        )


def _is_tracked(path: str) -> bool:
    """Is *path* committed to this repository?

    `docker-compose.override.yml` is not, and cannot be: compose applies it
    automatically and it is where a developer puts machine-local changes. So it
    exists on the machine that wrote one and in no fresh clone — which is
    precisely the state CI is always in.
    """
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_declared_skips_still_exist():
    """Drop the exemption when the file goes, so the list cannot rot.

    **Tracked files only**, and that is not a loophole — it is the difference
    between *deleted* and *never committed*. This asserted plain existence and so
    was red on `main` for as long as `docker-compose.override.yml` was in the
    list: the file is untracked by design, so a CI checkout has none and the test
    failed on every run while passing on every laptop. The sibling test above
    already made the distinction (`if not (ROOT / stack).exists(): continue`);
    this one did not, and the two disagreed.

    An untracked entry is still checked for rot, just not by existence: it must
    remain named in the task, which `test_declared_skips_are_skipped_in_the_task`
    covers wherever the file is present.
    """
    gone = [
        s for s in DECLARED_SKIPS if _is_tracked(s) and not (ROOT / s).exists()
    ]
    assert not gone, (
        f"declared exempt but no longer present: {gone}. The file was deleted or "
        "renamed — drop it from DECLARED_SKIPS, and from the build task."
    )


def test_the_three_participant_stacks_are_covered(script: str):
    """The regression itself, named.

    A glob satisfies the general test above, so this pins the specific case:
    all three participants — including the grid operator, the one that was
    missing — must be reachable by whatever form `build` takes.
    """
    covered_by_glob = "docker-compose.*.yml" in script
    for stack in (
        "docker-compose.rec.yml",
        "docker-compose.third-party.yml",
        "docker-compose.grid-operator.yml",
    ):
        assert (ROOT / stack).exists(), f"{stack} vanished — update this test"
        assert covered_by_glob or stack in script, f"`task build` skips {stack}"
