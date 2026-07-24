/**
 * Buildable EDC connector JAR with DCP (Dataspace Credential Protocol) support.
 *
 * Replaces the edc-samples connector used in Iterations 0–4. Produces a
 * self-contained fat JAR via the Shadow plugin that includes:
 *   - controlplane-dcp-bom  — DCP identity/trust + VC verification
 *   - dataplane-base-bom    — HTTP data plane
 *   - filesystem-configuration-bom — .properties file config
 *   - identity-did-web      — did:web resolver
 *   - edc-extensions        — custom ODRL constraint functions
 *
 * Build:  ./gradlew :edc-connector:shadowJar
 * Output: edc-connector/build/libs/connector.jar
 */
plugins {
    java
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

val edcVersion = "0.16.0"

dependencies {
    // ── Core control plane with DCP ──────────────────────────────────────────
    runtimeOnly("org.eclipse.edc:controlplane-dcp-bom:${edcVersion}")

    // ── Data plane (HTTP proxy for EDR transfers) ─────────────────────────────
    runtimeOnly("org.eclipse.edc:dataplane-base-bom:${edcVersion}")

    // ── Filesystem configuration (reads .properties files) ───────────────────
    runtimeOnly("org.eclipse.edc:configuration-filesystem:${edcVersion}")

    // ── DID:web resolver ──────────────────────────────────────────────────────
    runtimeOnly("org.eclipse.edc:identity-did-web:${edcVersion}")

    // ── PostgreSQL SQL stores (replaces in-memory) ────────────────────────────
    runtimeOnly("org.eclipse.edc:control-plane-sql:${edcVersion}")
    runtimeOnly("org.eclipse.edc:data-plane-store-sql:${edcVersion}")
    runtimeOnly("org.eclipse.edc:sql-pool-apache-commons:${edcVersion}")
    runtimeOnly("org.eclipse.edc:sql-lease-core:${edcVersion}")
    runtimeOnly("org.eclipse.edc:edr-index-sql:${edcVersion}")
    // The policy monitor is what terminates a running transfer when consent is
    // revoked. Without a persistent store it defaults to in-memory, so a
    // control-plane restart would silently forget every transfer it was
    // watching — and a later revocation would never reach them.
    runtimeOnly("org.eclipse.edc:policy-monitor-store-sql:${edcVersion}")
    runtimeOnly("org.eclipse.edc:transaction-local:${edcVersion}")
    runtimeOnly("org.postgresql:postgresql:42.7.5")

    // ── Our custom ODRL constraint functions ─────────────────────────────────
    runtimeOnly(project(":edc-extensions"))
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.shadowJar {
    archiveFileName.set("connector.jar")
    mergeServiceFiles()
    manifest {
        attributes["Main-Class"] = "org.eclipse.edc.boot.system.runtime.BaseRuntime"
    }
}

tasks.build {
    dependsOn(tasks.shadowJar)
}
