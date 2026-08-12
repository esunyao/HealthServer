# Repository Guidelines

## Project Structure & Module Organization

HealthServer is a Kotlin 2.3.21 / Java 21 Spring Boot 4.1 multi-module Gradle project. `gateway/` is the reactive API gateway (port 8080); `Orion/` is the user/auth service (port 8081); and `DietServer/` is the early diet-service skeleton (port 8082). Module source lives under `src/main/kotlin`, resources under `src/main/resources`, and tests under `src/test/kotlin`. Orion also keeps Flyway migrations in `Orion/src/main/resources/db/migration`. Shared build and dependency management belongs in the root `build.gradle`; module registration belongs in `settings.gradle` (the Gradle project name is lowercase `orion` even though the directory is `Orion`). Read the relevant module `CLAUDE.md` before changing its architecture.

## Build, Test, and Development Commands

Use the Gradle wrapper from the repository root and Java 21:

```bash
./gradlew build                 # build and test every registered module
./gradlew test                  # run all JUnit 5 tests
./gradlew :gateway:bootRun      # start the gateway
./gradlew :orion:bootRun        # start Orion
./gradlew :gateway:test         # test one module
./gradlew :orion:test --tests "cn.esuny.orion.util.JwtUtilTest"
./gradlew clean                 # remove generated build output
```

Orion and DietServer need PostgreSQL; Orion also needs Redis and external configuration may require Nacos. Do not commit credentials or machine-specific endpoints.

## Coding Style & Naming Conventions

Use Kotlin with four-space indentation, idiomatic null-safety, and the existing `cn.esuny.<module>` package layout. Name classes and objects in `PascalCase`, functions and properties in `camelCase`, constants in `UPPER_SNAKE_CASE`, and tests with a `Test` suffix. Keep controllers, services, mappers, models, and configuration in their established packages. Follow the existing compiler options and keep comments concise; repository code currently uses Chinese comments where explanation is needed. Preserve the project’s Jackson 3 and reactive-vs-servlet boundaries.

## Testing Guidelines

Tests use JUnit 5 through Spring Boot test starters, Kotlin test, coroutines-test, and MockK in Orion. Prefer focused unit tests for services and utilities, and web/controller tests for HTTP contracts. Place tests in the matching package under `src/test/kotlin` and name them after the production type, for example `JwtUtilTest`. Run the affected module test task before the full `./gradlew test`; no explicit coverage threshold is currently configured.

## Commit & Pull Request Guidelines

Recent commits use short imperative summaries such as `Add ...`, `Refactor ...`, and `Enhance ...`; follow that style and keep each commit focused on one change. Pull requests should explain the behavior and affected module, link the relevant issue or plan when available, list verification commands, and include API examples or screenshots when externally visible behavior changes. Call out required PostgreSQL, Redis, Nacos, or object-storage setup explicitly.

## Security & Configuration Tips

Keep JWT secrets, database passwords, Redis credentials, and S3/RustFS settings in local or deployment configuration, never source control. When changing authentication, gateway filters, migrations, or file storage, add regression tests and verify token type, user identity headers, schema changes, and error responses.
