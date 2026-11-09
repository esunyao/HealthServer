# Integrations 测试导航

父级导航：[`../AGENTS.md`](../AGENTS.md)。实现导航：[`../../src/nutriathena_agent/integrations/AGENTS.md`](../../src/nutriathena_agent/integrations/AGENTS.md)。

- `test_auth.py`：JWT 签名、issuer、audience、caller、scope 与拒绝响应。
- `test_media.py`：图片签名、MIME、数量/字节限制、主机通配符、HTTPS 端口和重定向限制。
- `test_model.py`：配置公开入口和模型构造参数，使用构造器替身。
- `test_mcp_context.py`：capture 契约、SDK 结构化/文本解析、错误结果、脱敏与 notes。
- `test_mcp_tools.py`：SDK 元信息、工具匹配、缓存和单次远端调用。
- `test_mcp_client.py`：OAuth、SDK 会话阶段、capture 预取与资源关闭，使用本地替身。
