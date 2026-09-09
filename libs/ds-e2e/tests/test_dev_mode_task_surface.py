"""Issue #35 · the four `dev:*` lifecycle fixes, pinned on the Taskfile.

These are shell, and the conditions they exist for cannot be produced in a unit
suite: a stale JVM holding a port, a JAR replaced under a live runtime, a task
run with no terminal. `test_build_covers_every_stack` is the precedent — the
invariant spans the root `Taskfile.yml`, so it belongs to no service, and it
lands in the unit whose subject is the whole running dataspace.

Each assertion names the property, not the spelling, and the docstring says what
went wrong without it. A rewrite that keeps the property should keep these green;
one that drops it should not.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TASKFILE = ROOT / "Taskfile.yml"

WATCH_TASKS = ("edc-rec:watch", "edc-third-party:watch")


def _task_script(name: str) -> str:
    """One task's commands, as raw text."""
    text = TASKFILE.read_text(encoding="utf-8")
    start = text.index(f"\n  {name}:\n")
    rest = text[start + 1 :]
    end = re.search(r"\n  [a-zA-Z][\w:-]*:\n", rest)
    return rest[: end.start()] if end else rest


def test_the_slicer_finds_a_task_and_stops_at_the_next():
    """Guards the helper: a slicer that over-runs makes every test below vacuous."""
    script = _task_script("edc-rec:watch")
    assert "Reaping stale EDC provider JVM" in script
    assert "edc-third-party:watch" not in script


# ── item 6 · a successful start must not exit non-zero ───────────────────────


def test_dev_start_does_not_attach_without_a_terminal():
    """`tmux attach` fails with `open terminal failed: not a terminal`.

    It is the last command of `dev:start`, so the task reported failure *after*
    bringing the whole stack up, and anything scripted read a healthy start as a
    failed one.
    """
    script = _task_script("dev:start")
    assert "tmux attach -t ds" in script
    assert "[ -t 1 ]" in script, (
        "the attach must be guarded by a terminal check, or a scripted "
        "`task dev:start` fails after starting the stack correctly"
    )
    # And it must still tell a non-interactive caller how to get in.
    assert "tmux attach -t ds" in script.split("[ -t 1 ]", 1)[1]


# ── items 2 + 3 · the stale JVM, and the gate that accepted it ───────────────


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_reaper_waits_for_the_ports_not_for_a_guess(task: str):
    """`kill_stale` reaped by pattern and slept a flat second.

    A dead pid is not a free port. When the guess was short the boot that
    followed lost the race, failed to bind and died — and the survivor was the
    *old* runtime, which then answered the readiness gate for the whole run.
    """
    script = _task_script(task)
    assert "ports_held()" in script, (
        "the reaper must be able to ask which pids hold the ports, not only "
        "which match the config path"
    )
    assert re.search(r"kill_stale\(\)[\s\S]*ports_held", script), (
        "kill_stale must wait for the sockets to come free before returning"
    )
    # docker-proxy publishes these ports in `docker:*`; killing it would take
    # out the port mapping rather than a runtime.
    assert 'comm= 2>/dev/null)" = "java"' in script


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_reaper_looks_at_the_ports_as_well_as_the_config_path(task: str):
    """A JVM started by hand holds :x9193 and matches no `edc.fs.config=` pattern."""
    script = _task_script(task)
    reaper = script.split("kill_stale()", 1)[1]
    assert "pgrep -f" in reaper and "ports_held" in reaper


def test_the_readiness_gate_checks_which_runtime_answered():
    """Three steady answers stop a *dying* runtime, not a *stale* one.

    A JVM that outlived its watcher answered 401 for the whole gate, so readiness
    passed on a runtime nobody had started; the run then failed three tasks later
    on `delete_contract_definition 500` and *published nothing*, which reads as a
    governance defect.
    """
    script = _task_script("e2e:prepare")
    assert "java_on_port" in script, "the gate needs a handle on who holds the port"
    assert "OLD_19193" in script and "OLD_29193" in script and "OLD_39193" in script, (
        "the pid holding each management port must be recorded before the kill, "
        "or there is nothing to compare the new one against"
    )
    assert 'now_pid" = "$old_pid"' in script, (
        "answering is not evidence when the answer comes from the runtime the "
        "restart was supposed to replace"
    )


def test_the_gate_still_works_where_no_pid_is_observable():
    """`docker:*` publishes the port through docker-proxy, so there is no java pid.

    The identity check must narrow to nothing there and leave the streak as the
    whole gate — otherwise this fix breaks the mode that was never broken.
    """
    script = _task_script("e2e:prepare")
    assert '[ -n "$old_pid" ]' in script, (
        "the comparison must be conditional on having observed a pid at all"
    )


# ── item 4 · a rebuilt JAR under a live JVM ──────────────────────────────────


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_runtime_never_runs_the_file_gradle_is_writing(task: str):
    """`edc:watch-build` replaces `connector.jar` in place, under a live JVM.

    Classes not yet loaded vanish (`NoClassDefFoundError: okhttp3/…`), and the
    runtime keeps its ports while answering nothing — worse than crashing,
    because it looks like a slow one. Gradle owns its output path, so the swap
    happens here: run a private copy taken while no JVM holds it.
    """
    script = _task_script(task)
    assert "run_jar=" in script
    assert '-jar "$run_jar"' in script, (
        "the JVM must run the copy, not the build output"
    )
    assert '-jar "$jar" &' not in script


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_copy_waits_for_the_build_to_settle(task: str):
    """A copy of a half-written JAR is a JAR that will not boot.

    The crash loop that follows reads as a code problem, which is the most
    expensive way to be wrong about a build artefact.
    """
    script = _task_script(task)
    assert "copy_jar()" in script
    assert "%Y %s" in script, (
        "size as well as mtime — a multi-second write inside one clock second "
        "moves only the size"
    )
    # Taken before the mtime is read, so the recorded mtime is the JAR running.
    assert re.search(r"copy_jar\n\s*MTIME=", script)


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_private_copy_lives_under_data(task: str):
    """ADR-0008: fetched and generated material lives under `./data/`, gitignored
    in full. A copy beside the build output would be one more thing Gradle's
    `--continuous` might decide to clean."""
    script = _task_script(task)
    assert "/data/edc-run/" in script
