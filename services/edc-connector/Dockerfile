# Build context: repo root
# Requires ds-edc-base:0.16.0 to be built first (see Dockerfile.base).
# Builds a DCP-enabled EDC connector fat JAR with custom ODRL extensions.

FROM ds-edc-base:0.16.0 AS builder
WORKDIR /build

COPY settings.gradle.kts build.gradle.kts ./
COPY services/edc-extensions/ services/edc-extensions/
COPY services/edc-connector/  services/edc-connector/

RUN gradle :edc-connector:shadowJar --no-daemon -q

FROM eclipse-temurin:21-jre-alpine AS runtime
LABEL org.opencontainers.image.description="dataspaces EDC connector — DCP-enabled with custom ODRL extensions"

RUN apk add --no-cache curl
RUN addgroup -S edc && adduser -S -G edc edc

COPY --from=builder /build/services/edc-connector/build/libs/connector.jar /connector.jar

ENV JAVA_OPTS="-Xms256m -Xmx512m"
USER edc
EXPOSE 19193 19194 19195 19291 29193 29194 29195 29291

HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=10 \
  CMD curl -sf http://localhost:19195/api/check/health || \
      curl -sf http://localhost:29195/api/check/health || exit 1

CMD ["sh", "-c", "java $JAVA_OPTS -jar /connector.jar"]
