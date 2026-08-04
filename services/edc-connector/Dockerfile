# Build context: repo root
# Requires ds-edc-base:0.16.0 to be built first (see Dockerfile.base).
# Builds a DCP-enabled EDC connector fat JAR with custom ODRL extensions.

# Locally the base is the one `task edc:base` builds. CI has no such image and
# passes the published copy instead:
#   --build-arg EDC_BASE_IMAGE=ghcr.io/spindoxlabs/ds-edc-base:0.16.0
ARG EDC_BASE_IMAGE=ds-edc-base:0.16.0
FROM ${EDC_BASE_IMAGE} AS builder
WORKDIR /build

# gradle.properties carries `edcVersion`, which :edc-connector reads with
# `by project` — omit it and the build fails with "property does not exist",
# which is how this line got here.
COPY settings.gradle.kts build.gradle.kts gradle.properties ./
COPY services/edc-extensions/ services/edc-extensions/
COPY services/edc-connector/  services/edc-connector/

RUN gradle :edc-connector:shadowJar --no-daemon -q

FROM eclipse-temurin:21-jre-alpine AS runtime
LABEL org.opencontainers.image.description="dataspaces EDC connector — DCP-enabled with custom ODRL extensions"

RUN apk add --no-cache curl
# uid/gid pinned: kubelet cannot verify runAsNonRoot against a named USER
RUN addgroup -S -g 10001 edc && adduser -S -u 10001 -G edc edc

COPY --from=builder /build/services/edc-connector/build/libs/connector.jar /connector.jar

ENV JAVA_OPTS="-Xms256m -Xmx512m"
USER edc

# No EXPOSE, and no HEALTHCHECK. One image runs every participant, and each one
# binds a different port block from its own properties file — 19xxx for `rec`,
# 29xxx for `third-party`, 39xxx for `grid-operator` — so nothing baked into the
# image can be right for more than one of them.
#
# What was here was wrong for all of them: EXPOSE listed 19195/29195 (version)
# and 19291/29291 (public), contexts no packaged module registers, omitted the
# 39xxx block entirely, and never named 19191/29191 where the health endpoint
# actually lives. The HEALTHCHECK probed :19195 — a port with no listener — so
# in plain `docker run` the container was unhealthy no matter how well it served.
#
# The health surface is `/api/check/health` on `web.http.port`. Whoever starts
# the container knows which port that is and probes it there:
#   compose → the `healthcheck:` block on each edc-<participant> service
#   Helm    → livenessProbe/readinessProbe on the `api` port (k8s ignores
#             a Docker HEALTHCHECK anyway)

CMD ["sh", "-c", "java $JAVA_OPTS -jar /connector.jar"]
