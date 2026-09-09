# HealthMindControl

HealthMind、NutriMemo、Kafka 和 Dify 的本地 Web 运维控制台。程序只监听
`127.0.0.1:8765`，不会开放到局域网或公网。

## 1. 准备 Python 环境

项目使用父目录 `HealthServer/.venv`，不要在 `HealthMindControl` 内再创建虚拟环境。

```powershell
cd E:\ProjectSpace\HealthServer
\.venv\Scripts\Activate.ps1
$env:UV_PROJECT_ENVIRONMENT = "E:\ProjectSpace\HealthServer\.venv"
uv sync --project HealthMindControl --extra test
```

如果不激活 `.venv`，只要保留上述绝对路径形式的 `UV_PROJECT_ENVIRONMENT` 设置也可以。

## 2. 创建并配置 `.env`

```powershell
cd E:\ProjectSpace\HealthServer\HealthMindControl
Copy-Item .env.example .env
notepad .env
```

程序启动时会自动读取下面的文件，不需要额外执行“绑定”命令：

```text
E:\ProjectSpace\HealthServer\HealthMindControl\.env
```

最低配置示例：

```dotenv
HMC_DATABASE_DSN=postgresql://数据库用户:数据库密码@192.168.3.101:5432/Health
HMC_KAFKA_BOOTSTRAP_SERVERS=192.168.3.101:9092
HMC_DIFY_URL=https://dify.lovedage.com.cn
HMC_MCP_URL=http://192.168.3.101:8093/mcp
HMC_AUTH_URL=https://auth.lovedage.com.cn:8093
HMC_DIFYCTL_PATH=C:/Users/Esuny/AppData/Local/difyctl/bin/difyctl.exe
```

| 配置项 | 用途 |
|---|---|
| `HMC_DATABASE_DSN` | PostgreSQL 连接串，同时访问 `healthmind` 和 `nutri` schema |
| `HMC_NUTRI_DATABASE_DSN` | 可选；仅当 Nutri 使用另一个数据库时填写 |
| `HMC_KAFKA_BOOTSTRAP_SERVERS` | Kafka 地址，多个地址用逗号分隔 |
| `HMC_DIFY_URL` | Dify 基础地址 |
| `HMC_MCP_URL` | HealthMind MCP 地址 |
| `HMC_AUTH_URL` | Authentik 地址 |
| `HMC_DIFYCTL_PATH` | 本机 `difyctl.exe` 完整路径 |
| `HMC_DIFY_CONSOLE_TOKEN` | 可选；自动读取 published workflow 时使用 |
| `HMC_STALE_MINUTES` | 滞留判定时间，默认 5 分钟 |
| `HMC_REFRESH_SECONDS` | 总览刷新间隔，默认 5 秒 |

密码包含 `@`、`:`、`/`、`#` 等字符时需要 URL 编码，例如 `a@b` 写成 `a%40b`。
`.env` 已被 Git 忽略，请勿把真实凭据复制到 `.env.example`。

## 3. 启动

当前位于 `HealthMindControl` 目录时：

```powershell
cd E:\ProjectSpace\HealthServer\HealthMindControl
uv run --active --project . healthmind-control
```

也可以简写为：

```powershell
uv run --active healthmind-control
```

当前位于父目录 `HealthServer` 时：

```powershell
cd E:\ProjectSpace\HealthServer
uv run --active --project HealthMindControl healthmind-control
```

成功启动后会显示：

```text
Application startup complete.
Uvicorn running on http://127.0.0.1:8765
```

浏览器打开 <http://127.0.0.1:8765>，按 `Ctrl+C` 停止程序。

## 4. 检查与常见问题

运行测试：

```powershell
cd E:\ProjectSpace\HealthServer
\.venv\Scripts\python.exe -m pytest -q HealthMindControl\tests
```

- `Project directory HealthMindControl does not exist`：你已经位于该目录，应使用 `--project .`。
- `HMC_DATABASE_DSN 未配置`：检查 `.env` 的位置和变量名；变量必须以 `HMC_` 开头。
- `password authentication failed for user "user"`：当前 `.env` 仍是模板值，请把
  `数据库用户`、`数据库密码`（或 `user`、`password`）替换为 PostgreSQL 的真实账号。
- 数据库可读但写入禁用：页面会显示缺少的表，需要先执行对应 Flyway migration。
- Dify `/v1/info` 返回 401：包含 Bearer challenge 时会被识别为服务正常。

## 5. 安全规则

- Kafka 消息查看器不提交业务消费 offset。
- 所有数据库和 Kafka 写操作都必须先预览，再输入确认文本。
- 操作审计位于 `HealthMindControl/var/audit/admin-actions.jsonl`。
- Dify App API Key 继续由 HealthMind 的 Nacos/环境变量管理。
