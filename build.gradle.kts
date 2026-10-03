// Root build — no source, just common config propagated to subprojects
allprojects {
    repositories {
        mavenCentral()
    }

    // **Dependency locking** (supply chain). Every resolvable configuration is
    // pinned by a committed `gradle.lockfile` per project, so a transitive
    // version can only change in a reviewed diff — not because a BOM or a range
    // moved upstream between two builds of the same commit.
    //
    // After changing a dependency, regenerate the lockfiles the way the build
    // runs (pinned container, no wrapper):
    //
    //   docker run --rm -v "$PWD:/project" -v "$PWD/data/gradle:/home/gradle/.gradle" \
    //     -w /project gradle:8.12-jdk21 \
    //     gradle :edc-extensions:dependencies :edc-connector:dependencies --write-locks --no-daemon
    dependencyLocking {
        lockAllConfigurations()
    }
}
