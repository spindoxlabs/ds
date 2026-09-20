plugins {
    `java-library`
}

val edcVersion = "0.18.0"

dependencies {
    api("org.eclipse.edc:policy-engine-spi:$edcVersion")
    api("org.eclipse.edc:participant-spi:$edcVersion")
    api("org.eclipse.edc:data-plane-spi:$edcVersion")
    api("org.eclipse.edc:verifiable-credentials-spi:$edcVersion")
    // Contract agreements + negotiations: the policy-monitor consent check reads
    // the signed agreement, and the pending guard reads the negotiation.
    api("org.eclipse.edc:contract-spi:$edcVersion")
    // CatalogPolicyContext — the `catalog` scope, where the ContractDefinition's
    // access policy decides who sees the dataset and who may open a negotiation
    // for it.
    api("org.eclipse.edc:catalog-spi:$edcVersion")
    // TransferProcessEvent — the transfer half of the lifecycle the connector
    // cannot see over DSP. Without a producer for it, a provider emitted no
    // `DataTransferCompleted` at all (rulebook L-1).
    api("org.eclipse.edc:transfer-spi:$edcVersion")
    // PolicyMonitorContext — the `policy.monitor` scope, where a revoked consent
    // terminates a transfer that is already running.
    api("org.eclipse.edc:policy-monitor-spi:$edcVersion")
    // Oauth2Client — a client-credentials token for ds-connector's internal API,
    // replacing the X-Api-Key that doubled as EDC's Management API key.
    api("org.eclipse.edc:oauth2-spi:$edcVersion")
    // WebService + TransactionContext — the negotiation resume endpoint, the one
    // operation EDC's Management API cannot express (it can terminate a
    // negotiation but not clear `pending`).
    api("org.eclipse.edc:web-spi:$edcVersion")
    api("org.eclipse.edc:transaction-spi:$edcVersion")
    // The resume route's authorisation: EDC's `@RequiredScope` and ownership
    // check (`auth-spi`), and the classic runtime's one participant context.
    // Provided at runtime by `management-api-authorization` and
    // `participant-context-connector-classic-core`.
    api("org.eclipse.edc:auth-spi:$edcVersion")
    api("org.eclipse.edc:participant-context-single-spi:$edcVersion")
    // Needed to compile the forked JsonObjectFromPolicyTransformer (see the file
    // header for why it is forked). Provided by the EDC runtime, so compileOnly.
    compileOnly("org.eclipse.edc:json-ld-spi:$edcVersion")
    compileOnly("org.eclipse.edc:transform-spi:$edcVersion")
    compileOnly("org.eclipse.edc:control-plane-transform:$edcVersion")
    compileOnly("jakarta.ws.rs:jakarta.ws.rs-api:3.1.0")
    // A policy that has been through EDC's JSON-LD expansion carries its right
    // operands as JsonString/JsonObject, not String — see Purposes.
    compileOnly("jakarta.json:jakarta.json-api:2.1.3")
    compileOnly("org.eclipse.edc:runtime-metamodel:$edcVersion")
    // SqlSchemaBootstrapper — EdcSchemaMigrationExtension queues ds's schema migrations
    // on it. The interface lives in the extension module, not an SPI; the runtime
    // packages it through `control-plane-sql`, so compileOnly.
    compileOnly("org.eclipse.edc:sql-bootstrapper:$edcVersion")
    // HTTP client for consent check
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.0")

    // Purposes reads the shape a policy arrives in, and that shape varies by how
    // the policy reached the store — the one place here worth unit-testing
    // directly, since getting it wrong denies access silently.
    testImplementation(platform("org.junit:junit-bom:5.10.2"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("jakarta.json:jakarta.json-api:2.1.3")
    // The resume route takes the caller's `SecurityContext`; compileOnly for main.
    testImplementation("jakarta.ws.rs:jakarta.ws.rs-api:3.1.0")
    // The forked JsonObjectFromPolicyTransformer is the highest-risk file here —
    // a silent revert republishes unreadable policies while everything looks
    // healthy — so its test drives the class rather than reading its source.
    // These are compileOnly for main (the EDC runtime provides them) and have to
    // be on the test classpath explicitly.
    testImplementation("org.eclipse.edc:json-ld-spi:$edcVersion")
    testImplementation("org.eclipse.edc:transform-spi:$edcVersion")
    testImplementation("org.eclipse.edc:sql-bootstrapper:$edcVersion")
    testRuntimeOnly("org.eclipse.parsson:parsson:1.1.5")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    // JsonObjectFromPolicyTransformerForkTest fails if this moves away from the
    // version the forked transformer was taken from.
    systemProperty("edc.version", edcVersion)
}
