#!/bin/sh
# Attach the OpenTelemetry Java agent when — and only when — a collector is
# configured, then run whatever command was given.
#
# **Why an entrypoint and not the CMD.** Every compose file overrides `command:`
# to name its participant's properties file (`-Dedc.fs.config=/config/rec.properties`
# and its two twins), so anything written into the image's CMD is discarded for
# all three EDCs — which is exactly how a feature ends up present in the image
# and absent in every deployment. An ENTRYPOINT survives a `command:` override,
# and augmenting `JAVA_OPTS` means the three existing commands pick the agent up
# **unchanged**: each already runs `java $JAVA_OPTS …`. One copy of the logic,
# and no compose file has to know the agent exists.
#
# The switch is `OTEL_EXPORTER_OTLP_ENDPOINT`, the same variable
# `ds_obs.tracing` reads in the Python services — so a deployment turns tracing
# on for the whole exchange with one value and cannot turn it on for half of it.
set -eu

if [ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
  # Metrics and logs off explicitly. The agent defaults to exporting all three
  # signals to this one endpoint, and a trace backend that speaks only OTLP
  # traces answers the other two with 404s — a steady error stream in the EDC's
  # log that says nothing about the EDC. A deployment wanting them points
  # `OTEL_METRICS_EXPORTER` at something that accepts them.
  export OTEL_METRICS_EXPORTER="${OTEL_METRICS_EXPORTER:-none}"
  export OTEL_LOGS_EXPORTER="${OTEL_LOGS_EXPORTER:-none}"
  # The agent's configuration file turns JDBC spans off and drops the
  # `/api/check/*` probe spans: together ~99% of an EDC's traces, none of them
  # about an exchange. The file reads the endpoint, service name, resource
  # attributes and sampling ratio from their usual variables, and the agent then
  # ignores every other OTEL_* variable (see the file). OTEL_CONFIG_FILE names
  # another file; set it empty for variable-only configuration.
  OTEL_CONFIG_FILE="${OTEL_CONFIG_FILE-/otel-config.yaml}"
  if [ -n "$OTEL_CONFIG_FILE" ]; then
    JAVA_OPTS="-Dotel.config.file=${OTEL_CONFIG_FILE} ${JAVA_OPTS:-}"
  fi
  JAVA_OPTS="-javaagent:/otel-agent.jar ${JAVA_OPTS:-}"
  export JAVA_OPTS
  echo "EDC: tracing on — exporting to ${OTEL_EXPORTER_OTLP_ENDPOINT} as ${OTEL_SERVICE_NAME:-unnamed}${OTEL_CONFIG_FILE:+, configured by ${OTEL_CONFIG_FILE}}"
else
  echo "EDC: tracing off — set OTEL_EXPORTER_OTLP_ENDPOINT to enable it"
fi

exec "$@"
