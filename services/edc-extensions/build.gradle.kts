plugins {
    `java-library`
}

val edcVersion = "0.16.0"

dependencies {
    api("org.eclipse.edc:policy-engine-spi:$edcVersion")
    api("org.eclipse.edc:participant-spi:$edcVersion")
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
