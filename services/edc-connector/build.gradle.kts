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
import java.util.zip.ZipFile

plugins {
    java
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

val edcVersion = "0.16.0"

dependencies {
    // ── Our custom ODRL constraint functions ─────────────────────────────────
    //
    // Declared FIRST on purpose. It carries a forked copy of EDC's
    // JsonObjectFromPolicyTransformer (see that file's header), and with
    // DuplicatesStrategy.EXCLUDE the first copy written to the JAR wins. Order is
    // not a guarantee, so `verifyForkedTransformer` below asserts the outcome.
    runtimeOnly(project(":edc-extensions"))

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

}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.shadowJar {
    archiveFileName.set("connector.jar")
    mergeServiceFiles()
    // Keep the first copy of a duplicated entry rather than writing both. Combined
    // with :edc-extensions being declared first, this is what lets the forked
    // JsonObjectFromPolicyTransformer replace upstream's.
    duplicatesStrategy = DuplicatesStrategy.EXCLUDE
    manifest {
        attributes["Main-Class"] = "org.eclipse.edc.boot.system.runtime.BaseRuntime"
    }
    finalizedBy("verifyForkedTransformer")
}

/**
 * Fail the build if the packaged JsonObjectFromPolicyTransformer is upstream's
 * rather than our patched fork.
 *
 * Dependency order decides which copy is written, and nothing else would notice if
 * it changed: the connector would start, serve a catalogue, and quietly publish
 * unreadable multi-valued ODRL operands again. Delete this together with the fork
 * once the fix is upstream.
 */
tasks.register("verifyForkedTransformer") {
    val jar = layout.buildDirectory.file("libs/connector.jar")
    inputs.file(jar)
    doLast {
        val pkg = "org/eclipse/edc/connector/controlplane/transform/odrl/from/"
        // The outer class carries the marker constant; the fix itself lives in the
        // inner Visitor. Check both — a mixed packaging would otherwise look fine.
        val expected = mapOf(
            "${pkg}JsonObjectFromPolicyTransformer.class" to "ds-fork-multivalued-right-operand",
            "${pkg}JsonObjectFromPolicyTransformer\$Visitor.class" to "literalNode",
        )
        ZipFile(jar.get().asFile).use { zip ->
            expected.forEach { (entryName, needle) ->
                val entry = zip.getEntry(entryName)
                    ?: throw GradleException("$entryName is missing from connector.jar")
                val bytes = zip.getInputStream(entry).readBytes()
                if (!String(bytes, Charsets.ISO_8859_1).contains(needle)) {
                    throw GradleException(
                        "connector.jar packaged UPSTREAM's $entryName, not the patched fork in " +
                            ":edc-extensions. Multi-valued ODRL right operands would again be " +
                            "published as a stringified Java object that no counterparty can " +
                            "parse. Check dependency order and shadowJar duplicatesStrategy."
                    )
                }
            }
        }
        logger.lifecycle("verifyForkedTransformer: patched transformer is packaged")
    }
}

tasks.build {
    dependsOn(tasks.shadowJar)
}
