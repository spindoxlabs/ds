rootProject.name = "dataspaces"

// Keep short project names so build.gradle.kts references don't change
include(":edc-extensions")
project(":edc-extensions").projectDir = file("services/edc-extensions")

include(":edc-connector")
project(":edc-connector").projectDir = file("services/edc-connector")
