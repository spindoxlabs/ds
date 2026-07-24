plugins {
    `java-library`
}

val edcVersion = "0.16.0"

dependencies {
    api("org.eclipse.edc:policy-engine-spi:$edcVersion")
    api("org.eclipse.edc:participant-spi:$edcVersion")
    api("org.eclipse.edc:data-plane-spi:$edcVersion")
    api("org.eclipse.edc:verifiable-credentials-spi:$edcVersion")
    // Contract agreements + negotiations: the policy-monitor consent check reads
    // the signed agreement, and the pending guard reads the negotiation.
    api("org.eclipse.edc:contract-spi:$edcVersion")
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
    compileOnly("jakarta.ws.rs:jakarta.ws.rs-api:3.1.0")
    // A policy that has been through EDC's JSON-LD expansion carries its right
    // operands as JsonString/JsonObject, not String — see Purposes.
    compileOnly("jakarta.json:jakarta.json-api:2.1.3")
    compileOnly("org.eclipse.edc:runtime-metamodel:$edcVersion")

    // HTTP client for consent check
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.0")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
