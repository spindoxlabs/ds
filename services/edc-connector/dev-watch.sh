#!/usr/bin/env bash
# Run one EDC connector from source and restart it when the fat JAR is rebuilt.
#
# **Why this is a script and not a Taskfile block, which is the whole point.**
# `task` runs command blocks in an embedded Go shell (mvdan/sh), not in bash, and
# that shell cannot do process management:
#
#   * `$!` yields a **job id** — the literal `g1` — not a pid;
#   * `kill` is an *unsupported builtin* and fails with exit 2.
#
# Both loops lived in `Taskfile.yml` and both were built on `PID=$!` plus `kill`,
# under `2>/dev/null`. So every `kill` silently did nothing, `kill -0 "$PID"`
# reported the runtime dead while it was serving, and the loop started a second
# JVM onto ports the first still held — a BindException storm whose survivor was
# the *old* runtime. That is issue #35 items 2-4, and no amount of care inside a
# Taskfile block could have fixed it.
#
# Keep this in bash. If it moves back into YAML, it stops working and says so
# only in stderr nobody reads.
#
# Usage: dev-watch.sh <rec|third-party>
set +e

ROLE_KEY="${1:?usage: dev-watch.sh <rec|third-party>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

case "$ROLE_KEY" in
  rec)
    ROLE="provider"
    PORTS="19191 19192 19193 19194"
    ;;
  third-party)
    ROLE="consumer"
    PORTS="29191 29192 29193 29194"
    ;;
  *)
    echo "unknown role '$ROLE_KEY' — expected 'rec' or 'third-party'" >&2
    exit 2
    ;;
esac

conf="$ROOT/services/connector/config/${ROLE_KEY}.properties"
vault="$ROOT/services/connector/config/${ROLE_KEY}-vault.properties"
jar="$ROOT/services/edc-connector/build/libs/connector.jar"

if [ ! -f "$jar" ]; then
  echo "No connector.jar found — building..."
  (cd "$ROOT" && task edc:build)
fi

PID=

# Stop the JVM without ever blocking forever.
#
# The old loop did `kill $PID; wait $PID`. An EDC that is slow to run its
# shutdown hooks — or does not act on SIGTERM at all — left `wait` blocked for
# good: the watcher printed "restarting", then never restarted, and the stale JVM
# kept serving the *old* JAR while every rebuild appeared to do nothing. Losing a
# watcher silently is worse than a hard kill, so escalate and move on.
stop_edc() {
  [ -z "$PID" ] && return 0
  kill "$PID" 2>/dev/null
  local i=0
  while [ $i -lt 20 ]; do
    kill -0 "$PID" 2>/dev/null || { PID=; return 0; }
    sleep 0.5
    i=$((i + 1))
  done
  echo "EDC $ROLE ignored SIGTERM for 10s — sending SIGKILL"
  kill -9 "$PID" 2>/dev/null
  i=0
  while [ $i -lt 10 ]; do
    kill -0 "$PID" 2>/dev/null || { PID=; return 0; }
    sleep 0.5
    i=$((i + 1))
  done
  echo "EDC $ROLE survived SIGKILL — $PORTS may still be held" >&2
  PID=
}

cleanup() { stop_edc; exit 0; }
trap cleanup INT TERM EXIT

# Who is *serving* one of this runtime's ports.
#
# **`-sTCP:LISTEN` is the whole correctness of this function.** `lsof -i
# tcp:19194` matches a socket with that port on *either* end, so without the
# state filter this returns the **consumer's** JVM — which holds an outbound DSP
# connection to the provider's protocol port — and the reaper below kills it.
# Measured 2026-09-09: with both loops doing that to each other, neither runtime
# could stay up. A listener is what "holds the port" means; a client connected to
# one holds nothing.
ports_held() {
  local p pid
  for p in $PORTS; do
    for pid in $(lsof -nP -t -iTCP:"$p" -sTCP:LISTEN 2>/dev/null); do
      [ "$(ps -p "$pid" -o comm= 2>/dev/null)" = "java" ] || continue
      [ "$pid" = "$PID" ] && continue
      echo "$pid"
    done
  done
}

# An EDC that outlived its watcher still holds the ports, so every boot after it
# fails to bind and the loop spins — 200+ restarts with nothing in the log but
# BindException. Reap our own strays before starting.
#
# **A dead pid is not a free port, and the config path is not the only way to
# hold one.** This reaped by `pgrep -f edc.fs.config=$conf` and then slept a flat
# second, which is a guess about how long a JVM takes to release its sockets.
# When the guess was short the boot that followed lost the race, failed to bind,
# died — and *the survivor was the old runtime*, which then answered the
# readiness gate and served the whole run. So: reap by port as well, and wait for
# the sockets themselves.
kill_stale() {
  local stale i
  # Deduplicated: `ports_held` reports a listener once per port, so the same pid
  # arrived four times and the log read as four failed reaps.
  for stale in $(printf '%s\n' $(pgrep -f "edc.fs.config=$conf" 2>/dev/null) $(ports_held) | sort -u); do
    [ "$stale" = "$PID" ] && continue
    echo "Reaping stale EDC $ROLE JVM $stale (it still holds the ports)"
    # **Not `2>/dev/null`.** A reaper that reports success whatever happens is
    # the same defect as a gate that passes on the wrong runtime: the loop below
    # spent five boots failing to bind while this line claimed to have cleared
    # the port every time.
    kill -9 "$stale" || echo "could not kill $stale — it still holds the port" >&2
  done
  i=0
  while [ $i -lt 20 ]; do
    [ -z "$(ports_held)" ] && return 0
    sleep 0.5
    i=$((i + 1))
  done
  echo "EDC $ROLE: $PORTS still held after 10s — the next boot cannot bind" >&2
}

# **Never run the file Gradle is writing.** `edc:watch-build` replaces
# `connector.jar` in place while this JVM has it open, so classes not yet loaded
# vanish underneath it — `NoClassDefFoundError: okhttp3/…`,
# `ClassNotFoundException: org.apache.commons.pool2.…` — and the runtime then
# keeps its ports while answering nothing, which is worse than crashing because
# it looks like a slow one.
#
# Gradle `--continuous` owns its output path, so the swap has to happen at this
# end: run a private copy, taken while no JVM holds it, and let the rebuild
# replace a file nobody has open. Under `./data/`, gitignored in full (ADR-0008).
run_jar="$ROOT/data/edc-run/${ROLE_KEY}-connector.jar"
mkdir -p "$(dirname "$run_jar")"

# A copy of a half-written JAR is a JAR that will not boot, and the crash loop
# that follows reads as a code problem. Wait for the file to stop changing first
# — size as well as mtime, because a multi-second write inside one clock second
# moves only the size.
copy_jar() {
  local i=0 a b
  while [ $i -lt 60 ]; do
    a=$(stat -c '%Y %s' "$jar" 2>/dev/null)
    sleep 1
    b=$(stat -c '%Y %s' "$jar" 2>/dev/null)
    [ -n "$a" ] && [ "$a" = "$b" ] && break
    i=$((i + 1))
  done
  cp "$jar" "$run_jar.partial" && mv "$run_jar.partial" "$run_jar"
}

FAILS=0
while true; do
  kill_stale
  # In this order: the copy waits for the build to settle, so reading the mtime
  # afterwards records the JAR this JVM is actually running. Read first and a
  # rebuild that landed during the copy looks like a change the moment the loop
  # starts watching, restarting a runtime that is already current.
  copy_jar
  MTIME=$(stat -c %Y "$jar" 2>/dev/null)
  STARTED=$(date +%s)
  echo "Starting EDC $ROLE (JAR mtime: $MTIME)..."
  java -Xms256m -Xmx512m \
    -Dedc.fs.config="$conf" \
    -Dds.vault.seed.file="$vault" \
    -jar "$run_jar" &
  PID=$!

  while true; do
    sleep 2
    if ! kill -0 "$PID" 2>/dev/null; then
      echo "EDC $ROLE exited on its own — restarting..."
      break
    fi
    NOW=$(stat -c %Y "$jar" 2>/dev/null)
    # An empty mtime means the JAR is mid-write: wait for the new one rather than
    # restarting onto a file that is not there yet.
    if [ -n "$NOW" ] && [ "$NOW" != "$MTIME" ]; then
      echo "JAR changed ($MTIME → $NOW) — restarting EDC $ROLE..."
      break
    fi
  done

  stop_edc

  # Back off when the JVM dies almost immediately. A crash loop is a
  # configuration problem, not something to retry 200 times a minute — slow down
  # so the reason stays readable in the log.
  if [ $(( $(date +%s) - STARTED )) -lt 20 ]; then
    FAILS=$((FAILS + 1))
    BACKOFF=$((FAILS * 5))
    [ $BACKOFF -gt 60 ] && BACKOFF=60
    echo "EDC $ROLE died after <20s (attempt $FAILS) — waiting ${BACKOFF}s before retrying"
    sleep $BACKOFF
  else
    FAILS=0
    sleep 1
  fi
done
