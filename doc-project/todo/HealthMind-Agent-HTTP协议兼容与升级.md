# 待办：升级 HealthMind 与 NutriAthenaAgent 的 HTTP 协议兼容

- 状态：待实施临时缓解、待调查与验证长期升级方案。
- 范围：HealthMind 调用 NutriAthenaAgent 的 Agent HTTP 接口，以及 Python ASGI 服务端；同时检查相关部署、测试、文档和 Agent release 制品身份。
- 目标：先恢复当前调用；后续让 Python 侧及部署链路具备经验证的 HTTP/2 能力，移除 HealthMind 为兼容当前 Agent 服务而强制使用 HTTP/1.1 的临时配置。
- 本文是待办，不代表 HTTP/1.1 临时缓解或 HTTP/2 升级已经实施、部署或通过验收。HTTP/2 目标针对 HealthMind → Agent 链路，不要求立刻删除项目中所有其他用途的 HTTP/1.1。

## 背景和已确认的现象

1. HealthMind 先调用 Agent 的 `POST /threads` 创建 thread，再提交 run。创建 thread 失败时不会生成对应的 Agent run。
2. 2026-11-03 Agent 日志出现 `Unsupported upgrade request.`、`Invalid HTTP request received.`，以及 `POST /threads HTTP/1.1` 返回 422；HealthMind 记录 `AGENT_REQUEST_REJECTED`，数据库中对应任务没有创建 thread 或 run。
3. 在运行中的 Agent 上，使用认证令牌并故意提供不一致的 `thread_id` 与 `attempt_id` 做无写入对照：普通 HTTP/1.1 带请求体返回 `409 THREAD_IDENTITY_CONFLICT`，说明 JSON 被读取；带 `Upgrade: h2c` 和 `Transfer-Encoding: chunked` 的请求返回 422，详情为 `body` / `Field required`，说明请求体未被应用收到。对照请求在数据库写入之前被拒绝，没有创建 thread。
4. 本机 Agent 环境发现 `uvicorn 0.53.0`、`httptools 0.8.0` 和 `h11 0.16.0`；Agent 当前启动代码调用 `uvicorn.run(...)`，未显式指定 HTTP 解析器。实际运行时版本、所选解析器、代理与启动配置日后应重新核验。上游报告描述了类似症状：[Uvicorn issue #2722](https://github.com/Kludex/uvicorn/issues/2722)。
5. 以上对照已在本机复现，但尚未捕获 HealthMind 当次失败请求的原始头和请求体；这是高度吻合、仍需用实际 Java 客户端请求及修复前后结果确认的原因，不能把所有 422 或 HTTP 升级警告都视为同一问题。
6. 2026-11-03 建立本待办时，[AgentRunClient.kt](../../HealthMind/src/main/kotlin/cn/esuny/healthmind/infrastructure/agent/AgentRunClient.kt) 的 JDK `HttpClient` 构造未设置 `HTTP_1_1`；因此临时降级目前仅是已提出的修复方式，不能假设已经合入或部署。实施前需重新检查当前工作区与运行版本，避免覆盖用户的后续改动。

## 第一阶段：临时恢复服务

- [ ] 在 HealthMind → Agent 的 HTTP 客户端范围内评估并实施临时 HTTP/1.1 固定：对该链路使用的 JDK `HttpClient` 显式配置 `HttpClient.Version.HTTP_1_1`，避免明文连接触发 h2c 升级。不要无差别修改所有对外客户端，也不要改变 OAuth、MCP 或其他服务的权限。
- [ ] 重启或部署受影响的 HealthMind 实例，核实实际生效的部署地址、协议和运行版本；不要仅凭修改源码判断缓解已生效。若已有其他等效修复，先确认其效果，再决定是否还需要临时固定。
- [ ] 验证真实请求的 `POST /threads` 能携带完整 JSON、通过 Agent 校验并按契约创建 thread；随后提交 run，核对 HealthMind 与 Agent 的 task、attempt、thread、run 身份对应。不要修改旧任务或伪造成功结果。
- [ ] 记录变更位置、部署范围和验证日期，将 HTTP/1.1 固定明确标记为可移除的临时兼容设置；已经失败的任务按项目支持的重试或重新提交流程处理。

## 第二阶段：升级 Python 侧及部署链路，移除降级

- [ ] 核实升级时的 Python、ASGI server、HTTP 解析器及其 HTTP/2 支持状态，并评估使用原生支持 HTTP/2 的 ASGI 服务器，或由明确支持 HTTP/2 的入口/反向代理终止 HTTP/2 后转发给 Python 服务。不能假定升级 Python 语言本身或安装 WebSocket 依赖就会提供 HTTP/2。
- [ ] 先确定实际部署方式：端到端 HTTP/2，还是 HealthMind 到入口使用 HTTP/2、入口到 Python 使用 HTTP/1.1；明确目标是去掉 HealthMind 的临时 HTTP/1.1 强制降级。如果最终要求每一跳都不用 HTTP/1.1，需在设计时明确并单独验证。不要把客户端到代理的 HTTP/2 误称为端到端 HTTP/2。
- [ ] 明确 TLS + ALPN 与明文 h2c 的支持与适用场景；生产环境优先使用受信任的 HTTPS/TLS 和正常证书校验，本地回环开发模式按实际约束设计。不要把 HTTP/2、HTTPS 与 h2c 当作同一种协议，也不要为连通而关闭证书校验。
- [ ] 对齐 HealthMind 的协议协商和 Agent 服务端真实支持范围，完成部署和兼容验证后，移除 `AgentRunClient` 中为该问题引入的 HTTP/1.1 固定；不要通过全局降级隐藏其他客户端的协议问题。
- [ ] 若 Agent 源码、依赖、启动代码或制品内容发生变化，核对 Agent 制品摘要计算、固定 release 身份和部署配置；按既有 release 流程登记新版本或安排兼容迁移，不能静默改写已晋升 release 的制品身份。按项目规范更新受影响模块的公开文档与导航。
- [ ] 改善诊断：区分申请 OAuth token 与调用 Agent 的失败阶段，记录安全的 HTTP 状态、请求路径、失败类别与关联 ID，必要时记录不含敏感数据的校验错误摘要；不得记录 bearer token、客户端密钥、完整个人健康数据或未经脱敏的原始请求体。不要把所有 OAuth 失败误标为 Agent 请求被拒。

## 验收条件

- [ ] 用实际 HealthMind Java HTTP 客户端与部署的 Python 服务/入口测试 `POST /threads` 的真实请求体，覆盖 JSON、`Content-Length`、chunked 与协议协商场景；验证不会出现请求体缺失、422 和本次相关的升级/解析警告。
- [ ] 使用传输层或服务端证据核实协商结果为方案要求的 HTTP/2：HTTPS 场景检查 ALPN 和协商协议；h2c 场景单独验证握手与请求体处理。不能仅凭接口返回 200 宣称使用 HTTP/2。
- [ ] HealthMind → Agent 的 thread 创建、run 提交、状态查询、等待结果、重试/对账与幂等行为通过测试；重复请求、断连或不确定提交不产生重复 run。
- [ ] 核实 Agent → HealthMind MCP、OAuth 认证与授权、实际餐食分析及结果回传的端到端链路；在日志和数据库中验证 task/attempt/thread/run 的对应关系，不泄露密钥与敏感数据。
- [ ] 移除临时 HTTP/1.1 固定后完成回归，记录 TLS、代理、网络、依赖升级和回滚步骤；区分单元/集成测试与真实部署验证，并记录未完成项。

## 边界

本待办只记录背景和后续工作，不授权直接修改运行中的 Authentik、数据库、release、生产部署或其他未明确要求变更的组件。第一阶段缓解和第二阶段升级分别实施、验证和记录。
