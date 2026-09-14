# 项目总体阅读说明

> [!important]
>
> 1. 你必须先了解整个项目背景、项目意图、项目意义、项目目的、研究背景、以及项目未来的拓展性
>
> 2. 必须秉持着严谨的态度，片面的看待介绍文件
>
> 3. 在每个子项目中，都有可能有 `**doc**`文件夹，必要时你需要阅读这些文件
>
> 4. 倘若你上下文内缺失项目背景等资料，请先阅读 `doc-project` 下的文件。
>
>    > [!note]
>    >
>    > 你需要区分`doc`与`doc-project`文件夹的区别。对于`doc`文件夹而言，这是仓库公开文件，目的是为了让其他人能够读懂此项目（一般情况下不需要使用，本仓库暂时不需要公开讲解这些核心概念等内容，出于保密性原因）
>    >
>    > `doc-project` 则是本地文件夹，将不会被上传到仓库中，因此所有内容都是为我个人开发者提供。
>    >
>    > 其中，根目录下的`doc-project`是项目整体背景说明。其他的`docp`文件夹、全称是`doc-personal`，是对某个子项目的说明
>
> 5. `docp`适时阅读该文件夹而不是阅读代码来思考，当然你也要避免因为文档更新不及时而导致的误判
>
> 6. 你需要记得更新这些文件。
>
> 7. 你还需要阅读CLAUDE.md

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
