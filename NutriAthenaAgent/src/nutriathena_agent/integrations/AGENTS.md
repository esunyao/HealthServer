# Integrations 导航

父级导航：[`../AGENTS.md`](../AGENTS.md)。

- [`auth.py`](auth.py)：入站 JWT/JWKS 验签与 caller、scope 校验；配置来自 `config.RuntimeSettings`。
- [`media.py`](media.py)：本地图片校验与授权图片下载、大小/MIME/主机限制、多模态编码。
- [`model.py`](model.py)：从 `config` 的公开配置入口装配聊天模型和餐食模型。
- [`mcp/AGENTS.md`](mcp/AGENTS.md)：只读 HealthMind MCP 连接、上下文解析和绑定工具。
- 回归测试：[`../../../tests/integrations/`](../../../tests/integrations/)。
