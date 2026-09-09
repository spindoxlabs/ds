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
#: The EDC watch loop, which cannot live in the Taskfile — see
#: `test_the_edc_lifecycle_does_not_live_in_the_taskfile`.
RUNNER = ROOT / "services" / "edc-connector" / "dev-watch.sh"

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
    assert "dev-watch.sh rec" in script
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


# ── the shell these have to run in ───────────────────────────────────────────


def test_the_edc_lifecycle_does_not_live_in_the_taskfile():
    """`task` runs command blocks in an embedded Go shell, not bash.

    In it, `$!` yields a **job id** (`g1`) rather than a pid, and `kill` is an
    *unsupported builtin* that exits 2. Both watch loops were built on `PID=$!`
    plus `kill`, under `2>/dev/null` — so every kill silently did nothing,
    `kill -0 "$PID"` reported a serving runtime dead, and the loop started a
    second JVM onto ports the first still held. That is issue #35 items 2-4, and
    it could not have been fixed inside a Taskfile block.

    Measured, not assumed: `task` on a block doing `sleep 300 & kill $!` prints
    `victim pid: g1` and `kill: unsupported builtin`.
    """
    for task in WATCH_TASKS:
        script = _task_script(task)
        assert "dev-watch.sh" in script, (
            f"{task} must delegate to the bash runner — process management does "
            f"not work in task's shell"
        )
        assert "bash " in script
        assert "PID=$!" not in script, (
            "`$!` is a job id in task's shell, not a pid — this is the defect"
        )


def test_the_runner_exists_and_is_bash():
    assert RUNNER.exists()
    assert RUNNER.read_text().startswith("#!/usr/bin/env bash")


def test_the_prepare_kill_runs_in_a_real_shell():
    """`e2e:prepare` killed the host JVMs with task's `kill`, i.e. not at all.

    The gate then found the same runtime serving and the run continued against a
    control plane whose database had just been dropped.
    """
    script = _task_script("e2e:prepare")
    assert "bash -c" in script, "the kill must run in a shell that has a working `kill`"
    assert "SIGKILL" in script, "and it must escalate, since the kill is the restart"


# ── items 2 + 3 · the stale JVM, and the gate that accepted it ───────────────


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_reaper_waits_for_the_ports_not_for_a_guess(task: str):
    """`kill_stale` reaped by pattern and slept a flat second.

    A dead pid is not a free port. When the guess was short the boot that
    followed lost the race, failed to bind and died — and the survivor was the
    *old* runtime, which then answered the readiness gate for the whole run.
    """
    script = RUNNER.read_text()
    assert "ports_held()" in script
    assert re.search(r"kill_stale\(\)[\s\S]*ports_held", script), (
        "kill_stale must wait for the sockets to come free before returning"
    )
    assert 'comm= 2>/dev/null)" = "java"' in script


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_reaper_looks_at_listeners_only(task: str):
    """`lsof -i tcp:PORT` matches either end of a socket.

    Without `-sTCP:LISTEN` the provider's reaper matched the **consumer** JVM,
    which holds an outbound DSP connection to `:19194`, and killed it — both
    loops doing that to each other, so neither runtime could stay up. Measured
    2026-09-09.
    """
    script = RUNNER.read_text()
    reaper = script.split("ports_held()", 1)[1]
    assert "-sTCP:LISTEN" in reaper
    assert "lsof -ti tcp:" not in script, (
        "the unfiltered form is the bug: it matches clients as well as listeners"
    )


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_reaper_does_not_swallow_a_failed_kill(task: str):
    """It printed "Reaping …" and then discarded the kill's error for 24 passes."""
    script = RUNNER.read_text()
    assert "could not kill" in script


def test_the_readiness_gate_checks_which_runtime_answered():
    """Three steady answers stop a *dying* runtime, not a *stale* one.

    A JVM that outlived its watcher kept `:x9193` and answered 401 steadily for
    the whole gate, so readiness passed on a runtime nobody had just started; the
    run then failed three tasks later on `delete_contract_definition 500` and
    *published nothing*, which reads as a governance defect.
    """
    script = _task_script("e2e:prepare")
    assert "java_on_port" in script
    assert "OLD_19193" in script and "OLD_29193" in script and "OLD_39193" in script
    assert 'now_pid" = "$old_pid"' in script
    assert "-sTCP:LISTEN" in script, (
        "the gate must compare listeners, or a client socket's pid answers for "
        "the runtime"
    )


def test_the_gate_still_works_where_no_pid_is_observable():
    """`docker:*` publishes the port through docker-proxy, so there is no java pid.

    The identity check must narrow to nothing there and leave the streak as the
    whole gate — otherwise this fix breaks the mode that was never broken.
    """
    script = _task_script("e2e:prepare")
    assert '[ -n "$old_pid" ]' in script


@pytest.mark.parametrize("task", WATCH_TASKS)
def test_the_runtime_never_runs_the_file_gradle_is_writing(task: str):
    """`edc:watch-build` replaces `connector.jar` in place, under a live JVM.

    Classes not yet loaded vanish (`NoClassDefFoundError: okhttp3/…`), and the
    runtime keeps its ports while answering nothing — worse than crashing,
    because it looks like a slow one. Gradle owns its output path, so the swap
    happens here: run a private copy taken while no JVM holds it.
    """
    script = RUNNER.read_text()
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
    script = RUNNER.read_text()
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
    script = RUNNER.read_text()
    assert "/data/edc-run/" in script
