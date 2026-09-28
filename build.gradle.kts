plugins {
    id("java-library")
}

repositories {
    mavenCentral()
    maven("https://repo.papermc.io/repository/maven-public/")
}

dependencies {
    implementation("com.nimbusds:oauth2-oidc-sdk:11.38.2")
    compileOnly("io.papermc.paper:paper-api:26.2.build.119-stable")
    testImplementation("io.papermc.paper:paper-api:26.2.build.119-stable")
    testImplementation(platform("org.junit:junit-bom:6.0.1"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.mockito:mockito-core:5.23.0")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

java {
    sourceCompatibility = JavaVersion.VERSION_25
    targetCompatibility = JavaVersion.VERSION_25
}

tasks {
    jar {
        duplicatesStrategy = DuplicatesStrategy.EXCLUDE
        from(configurations.runtimeClasspath.get().map { if (it.isDirectory) it else zipTree(it) })
        configurations.runtimeClasspath.get().filter { it.extension == "jar" }.forEach { dependency ->
            from(zipTree(dependency)) {
                include("META-INF/LICENSE*", "META-INF/NOTICE*", "LICENSE*", "NOTICE*")
                eachFile { path = "META-INF/third-party/${dependency.name}/$name" }
                includeEmptyDirs = false
            }
        }
        exclude("META-INF/*.SF", "META-INF/*.RSA", "META-INF/*.DSA", "module-info.class", "META-INF/versions/**/module-info.class")
    }
    withType<JavaCompile>().configureEach {
        options.release = 25
        options.encoding = "UTF-8"
    }

    test {
        useJUnitPlatform()
    }

    processResources {
        val props = mapOf("version" to version)
        filesMatching("plugin.yml") {
            expand(props)
        }
    }
}
