> 不是说AI发展快吗，为什么拉的是怎么一坨😫😫😫😫😫😫😫😫😫😫😫😫

# NutriAthenaAgent

NutriAthenaAgent 是为 HealthMind 提供持久化执行能力的餐食分析运行服务。HealthMind 创建一次分析尝试（attempt）后，通过 HTTP 调用本服务；服务先将请求保存到 PostgreSQL，再由持有租约的工作进程（worker）执行餐食分析流程，最后由 HealthMind 获取结果。本模块同时保留两个小型 LangGraph/LangChain 教学示例。

## 启动服务

使用 Python 3.11 及以上版本，通过 `uv` 管理依赖：

```bash
cd NutriAthenaAgent
uv sync --extra test
```

将 `.env.example` 复制为 `.env`，配置运行参数、数据库、OAuth 签发方（issuer）与 JWKS、模型，以及只读的 HealthMind MCP 客户端。不要提交 `.env`，也不要在命令行参数中填写凭据。为兼容已有本地环境，旧的 `AGENTDEVELOP_*` 模型和 MCP 环境变量仍可作为回退配置。

启动服务前，先执行版本化 SQL 迁移：

```bash
uv run nutriathena-agent migrate
uv run nutriathena-agent serve
```

HTTP 服务监听 `NUTRIATHENA_HOST:NUTRIATHENA_PORT`，默认地址为 `0.0.0.0:8101`。`GET /healthz` 用于检查数据库连通性。需要认证的接口要求携带 OAuth Bearer Token，并校验配置的签发方、受众（audience）、允许的调用方 ID 和 `healthmind.agent.run` 权限范围（scope）。

HealthMind 运行协议见 [`doc/README.md`](./doc/README.md)。本服务为每次 attempt 创建绑定的线程（thread），返回 HealthMind 要求的固定 task/attempt 身份元数据；每次 attempt 最多接收一个幂等运行记录（run），提供待执行、执行中和终态查询，尽力响应取消请求，并将成功结果保留至少 24 小时。PostgreSQL 使用独立的 `nutriathena_agent` schema；本服务没有跨 schema 外键，也不写入 HealthMind 的业务记录。

## Docker 部署

Docker 构建需要整个仓库：构建上下文是仓库根目录，镜像会同时包含本模块和同级 `AgentDeveloper/skills`。Alpine 与 Python 依赖使用阿里云镜像源；依赖版本与哈希来自 `uv.lock`。不要从单独复制的 Agent 目录构建。

在部署服务器的 `NutriAthenaAgent/.env` 中配置现有数据库、模型、OAuth、HealthMind MCP 等参数，并将 `HEALTHSERVER_DOCKER_NETWORK` 设为已有 Docker 网络的实际名称。`NUTRIATHENA_PUBLISHED_PORT` 可选，默认是宿主机端口 8101；容器始终监听 8101。Compose 会覆盖 `NUTRIATHENA_HOST` 和 `NUTRIATHENA_PORT`，不影响直接运行 Python 的配置。容器中的 `localhost` 仅指容器本身；数据库、HealthMind MCP 等应填写容器网络内可访问的服务名或地址，OAuth issuer 则必须继续与签发的令牌一致。确认 HealthMind 的 Agent 部署地址也能访问此容器。Compose 对 `.env` 进行变量插值，含美元符号的密钥使用单引号包裹或按 Compose 规则转义。

从仓库根目录执行：

```bash
docker network ls
docker compose -f NutriAthenaAgent/docker-compose.yaml build
docker compose -f NutriAthenaAgent/docker-compose.yaml up -d
docker compose -f NutriAthenaAgent/docker-compose.yaml ps
docker compose -f NutriAthenaAgent/docker-compose.yaml logs -f nutriathena-agent
```

每次容器启动先执行已有的版本化迁移，再启动服务；迁移失败时不会启动 HTTP 服务，容器会按重启策略重试。数据库账号必须有相应 schema 和迁移权限；迁移账本会校验已应用文件，不能改写已应用的 SQL。`/healthz` 检查数据库连通性；Compose 不创建数据库，也不创建指定的外部网络。

镜像内运行代码、迁移、技能资产、`pyproject.toml` 与 `uv.lock` 必须和 HealthMind 的 release 制品摘要一致。构建后可以在不连接数据库的情况下计算镜像内摘要：

```bash
docker compose -f NutriAthenaAgent/docker-compose.yaml run --rm --no-deps --entrypoint python nutriathena-agent -c "from nutriathena_agent.artifact import compute_artifact_sha256; print(compute_artifact_sha256())"
```

将结果与 HealthMind release 的 `agent_artifact_sha256` 比对，同时核对 `NUTRIATHENA_RELEASE_ID`、`NUTRIATHENA_DEPLOYMENT_KEY` 和 `NUTRIATHENA_ASSISTANT_ID`。仅当摘要或 release 身份发生变化时，按 [release 登记指南](doc/release.md) 处理；升级前先对账旧 release 的 pending/running 任务。默认日志输出到容器 stderr；如果设置了文件日志，需要自行挂载可写且持久化的目录。

## 真实环境冒烟测试

`smoke` 通过已部署的 HTTP 服务发送一次真实请求。如果提交结果不明确，会查询已有 run 进行核对，然后等待执行结果。输出仅包含 ID、状态、摘要和菜品数量，不打印访问令牌、图片 URL 或食物名称。测试必须使用已获授权的 task 和 attempt，并确保对应餐食图片可用；命令不会自动构造任务上下文或示例结果。

```bash
uv run nutriathena-agent smoke \
  --task-id <authorized-task-uuid> \
  --attempt-id <authorized-attempt-uuid> \
  --trace-id <trace-id>
```

在本地配置 `NUTRIATHENA_SMOKE_TOKEN_URL`、`NUTRIATHENA_SMOKE_CLIENT_ID` 和 `NUTRIATHENA_SMOKE_CLIENT_SECRET`。使用相同 attempt 和相同请求重复执行时，会复用已有 run；如果修改已有 attempt 的请求内容，则会因幂等冲突而被拒绝。

## 测试与教学命令

默认自动化测试使用可替换的执行器和模拟依赖，无需连接真实 OAuth、MCP 或模型服务；PostgreSQL 集成测试需要 Docker：

```bash
uv run pytest -q
uv run nutriathena-agent graph
uv run nutriathena-agent graph "嗯"
uv run nutriathena-agent agent "统计一下这句话的词数：晚饭吃了清蒸鲈鱼"
```

`meal` 命令通过 MCP 和模型运行端直接执行一次已获授权的 attempt。生产任务应通过 `serve` 接入，以使用 PostgreSQL 提供的幂等控制、执行租约、数据保留和取消机制。

## 日志与调试模式

服务日志统一由 loguru 输出到 stderr；设置 `NUTRIATHENA_LOG_FILE` 时额外写入轮转文件（10 MB 轮转、保留 7 天）。默认文本格式，`NUTRIATHENA_LOG_FORMAT=json` 时每行输出一个 JSON。`NUTRIATHENA_LOG_LEVEL` 控制基础级别（默认 INFO）；`NUTRIATHENA_DEBUG != off` 时 sink 强制到 DEBUG。

文本日志默认 `NUTRIATHENA_LOG_COLOR=auto`：在 TTY 终端或 PyCharm/JetBrains 运行窗口中为时间戳、级别、logger、trace/run 上下文、event 与字段名着色；`always` 强制彩色，`never` 关闭；`auto` 尊重 `NO_COLOR`/`FORCE_COLOR`，管道/重定向/文件/JSON 默认无色。若 JetBrains Run 窗口没有自动着色，在运行配置或 `.env` 中设 `NUTRIATHENA_LOG_COLOR=always`。

通过环境变量 `NUTRIATHENA_DEBUG` 或 `serve`/`meal` 子命令的 `--debug` 选择细节级别；CLI 优先于环境变量：

```bash
NUTRIATHENA_DEBUG=trace uv run nutriathena-agent serve
uv run nutriathena-agent meal --debug --task-id <uuid> --attempt-id <uuid>
uv run nutriathena-agent meal --debug full --task-id <uuid> --attempt-id <uuid>
NUTRIATHENA_LOG_FORMAT=json NUTRIATHENA_LOG_FILE=logs/agent.log uv run nutriathena-agent serve
NUTRIATHENA_LOG_COLOR=always uv run nutriathena-agent serve
```

| 级别 | 输出 |
|---|---|
| `off`（默认） | INFO 运行日记：HTTP/worker/meal 阶段、耗时、状态与 trace/run/task/attempt 上下文；失败带完整异常链 |
| `trace` | 在 `off` 基础上增加 DEBUG 步骤：MCP OAuth/连接、LangGraph 节点、模型/工具调用、token 与租约心跳 |
| `full` | 在 `trace` 基础上输出餐食备注、模型输入输出、工具返回与最终结果；仅限本地开发 |

失败时即使 `off` 也能直接看到阶段与根因，例如：

```text
... | ERROR | nutriathena_agent.meal_agent:run:335 | trace="..." run="..." task="..." attempt="..." | event=meal.failed | stage="oauth" | mcp_stage="oauth" | status="error" | error_type="McpSetupError" | error_chain="McpSetupError <- ConnectError <- OSError <- ConnectionRefusedError" OAuth token endpoint could not be reached
Traceback (most recent call last):
  ...
httpx.ConnectError: All connection attempts failed
The above exception was the direct cause of the following exception:
nutriathena_agent.mcp_tools.McpSetupError: OAuth token endpoint could not be reached
```

常规日志（`off`/`trace`）不会输出 `.env`、OAuth token/模型 key、Authorization、JWT、data URL、签名图片 URL 或图片字节；`ValidationError` 只输出 `loc/type` 摘要。`full` 会包含真实餐食备注与模型输出，仍会移除上述凭据与 URL，并在启动时打印一次警告；不要在生产环境或长期留存中使用。文件 sink 面向当前单进程 `serve`；若未来启用多进程，应改用外部日志采集。

新增依赖或源码会改变 `artifact_sha256`。升级本模块前先 drain/对账旧 release 的 pending/running run，部署后重新登记 release（见 [`doc/release.md`](./doc/release.md)），避免旧 pending run 无法被新 worker claim。

## 餐食分析边界

- 餐食提示词和膳食技能沿用同级目录 [`AgentDeveloper/skills`](../AgentDeveloper/skills/) 中维护的资产，本服务将现有分析流程适配为可替换的执行器。
- 每次 attempt 在视觉模型调用前预取一次餐食采集 MCP 上下文，以获得已授权的图片 URL；面向模型的工具返回脱敏后的缓存上下文。营养画像 MCP 工具仍由模型按原有时序调用。稳定审计 ID 使用 attempt UUID 和完整 MCP 工具代码派生的 UUIDv5，通过 MCP `_meta.tool_call_id` 传递；每个工具在一次 attempt 中最多远程读取一次。
- 餐食采集上下文包含可空的餐食备注 `notes`。备注作为数据传入视觉分析流程，不能覆盖系统指令。
- 仅下载已授权采集记录返回的签名图片 URL。下载主机必须匹配 `NUTRIATHENA_MEDIA_ALLOWED_HOSTS` 逗号分隔的白名单，支持 `*.example.test` 和 `*` 通配符，HTTPS 允许任意有效端口；重定向、不支持的 MIME 类型或文件签名、图片数量超限、响应体大小超限都会被拒绝。图片 URL 和原始字节不会作为工具上下文或服务输出暴露给模型；视觉输入使用经过校验的内存编码图片。
- 采集图片缺失或不可用时，返回现有 `needs_review`（需要复核）结果，不会将其声称为成功完成的模型分析。
- 当前生产运行没有食物成分检索数据源。提示词明确声明未提供证据，允许基于常见食物知识进行保守估算并降低置信度，同时禁止伪造引用或声称进行过检索。
- 模型不具备 Shell、文件系统、写入、删除或子 Agent 工具。业务侧授权与结果持久化仍由 HealthMind 负责。
