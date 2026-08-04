/**
 * Buildable EDC connector JAR with DCP (Dataspace Credential Protocol) support.
 *
 * Replaces the edc-samples connector used in Iterations 0–4. Produces a
 * self-contained fat JAR via the Shadow plugin out of:
 *   - controlplane-dcp-bom     — DCP identity/trust + VC verification
 *   - dataplane-base-bom       — HTTP data plane
 *   - configuration-filesystem — .properties file config (a plain module, not a
 *                                BOM; this header used to name a
 *                                `filesystem-configuration-bom` that does not
 *                                exist in any EDC release)
 *   - identity-did-web         — did:web resolver
 *   - the SQL stores           — control plane, data plane, EDR index and the
 *                                policy monitor; see the block below for why the
 *                                last one is not optional
 *   - edc-extensions           — custom ODRL constraint functions
 *
 * Build:  task edc:build          → the fat JAR, in Docker, cached in data/gradle
 *         task edc:docker         → the image
 * Output: services/edc-connector/build/libs/connector.jar
 *
 * **There is no Gradle wrapper in this repository, deliberately** — the build
 * runs in a pinned `gradle:8.12-jdk21` container so that a checkout needs Docker
 * and nothing else. `./gradlew :edc-connector:shadowJar`, which this header used
 * to document, has never worked here.
 */
import java.util.zip.ZipFile

plugins {
    java
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

// From gradle.properties at the repo root — one source for a literal that also
// has to appear in two Dockerfiles, the Taskfile and a CI workflow.
val edcVersion: String by project

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

    // ── Tests ────────────────────────────────────────────────────────────────
    //
    // This project has no main source, and that is precisely why it needs tests:
    // what it can get wrong is the *assembly* — which modules are packaged, and
    // whether the configuration handed to the result is configuration the result
    // reads. Both fail silently at runtime. See RuntimeContractTest.
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    // The tests read the assembled artifact, not the source, because the assembly
    // is the thing under test — dependency order and BOM contents decide what is
    // in it, and neither is visible from any file in this directory.
    dependsOn(tasks.shadowJar)
    systemProperty("ds.connector.jar", tasks.shadowJar.get().archiveFile.get().asFile.absolutePath)
    systemProperty("ds.repo.root", rootDir.absolutePath)

    // Everything the tests read that is NOT on the compile classpath. Without
    // this Gradle sees no changed input, reports the task UP-TO-DATE, and the
    // suite passes without running — which is exactly what happened the first
    // time a config was edited to check that these tests can fail.
    inputs.files(
        fileTree(rootDir.resolve("services/connector/config")) { include("*.properties") },
        rootDir.resolve("gradle.properties"),
        rootDir.resolve("Taskfile.yml"),
        rootDir.resolve("services/edc-connector/Dockerfile"),
        rootDir.resolve("services/edc-connector/Dockerfile.base"),
        rootDir.resolve("services/edc-extensions/build.gradle.kts"),
        rootDir.resolve(".github/workflows/edc-base.yml"),
        rootDir.resolve(".github/workflows/release.yml"),
    ).withPropertyName("dsConfigurationUnderTest")

    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
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
