# Orion — 模块大体说明

HealthServer 的用户身份、画像、健康记录和头像文件服务（默认端口 `8090`）。它是 Spring WebMVC Servlet 服务，用户请求通常经 Gateway 进入。

## 技术栈

| 组件 | 说明 |
|---|---|
| Web | Spring WebMVC、Spring Security Resource Server |
| 数据库 | PostgreSQL，Flyway 管理 `orion` schema |
| ORM | MyBatis-Plus |
| 对象存储 | AWS S3 SDK，支持 S3 兼容实现 |
| 契约 | `Orion/openapi.yaml` |

数据库、Authentik 和对象存储地址全部由环境变量或 Nacos 注入；公开配置不提供真实外部地址。

## 认证边界

- Gateway 验证用户 OIDC 令牌并注入可信的 `X-Auth-Subject`。
- `@CurrentUser` 将该主体解析为 `AuthenticatedUser`，控制器按用户主体查询数据。
- `/internal/v1/ai-context/nutrition` 是服务间营养上下文接口，使用独立的 Authentik M2M 资源保护。

## 接口范围

`/v1/users/self` 及其子资源覆盖用户资料、身体测量、健康目标、过敏、疾病、饮食限制、烹饪偏好、临床观察和同意记录；`/v1/files/avatar/*` 负责头像上传流程。

头像流程使用对象存储直传：

1. presign 为 `avatar-staging/{userId}/...` 生成短时上传地址。
2. confirm 校验对象存在、用户归属和 staging 前缀。
3. 服务端校验通过后将对象转入 `avatars/{userId}/...`，并更新用户头像记录。

## 代码位置

- `controller/rest/`：用户、健康记录和文件 HTTP 接口。
- `identity/`：可信用户主体与 `@CurrentUser` 解析。
- `internal/nutrition/`：供 HealthMind 使用的营养上下文查询。
- `service/`、`mapper/`、`model/`：业务服务、MyBatis 映射和领域数据。
- `config/`、`handler/`：基础设施配置和统一错误处理。

## 验证

```bash
./gradlew :orion:test
./gradlew :orion:bootRun
```

`bootRun` 需要 PostgreSQL、Nacos、Authentik 和 S3 兼容对象存储的环境配置。