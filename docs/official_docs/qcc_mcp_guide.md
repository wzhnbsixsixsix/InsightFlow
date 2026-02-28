# 企查查 MCP 服务接入指南 (AI 专用版)

### 1. 服务概述

企查查 MCP（Model Context Protocol）为 LLM 提供实时的企业全景数据，包括工商信息、风险信息、知识产权等。

* **传输协议**: `streamable-http`
* **专属 URL 格式**: `https://mcp.qcc.com/basic/stream?key=YOUR_KEY`
* **前置条件**: 需在[企查查开放平台](https://www.google.com/search?q=https://openapi.qcc.com/mcpTools)开通服务并获取 API Key。

---

### 2. 标准 JSON 配置 (通用型)

适用于 **Cursor, Trae, Cline, Continue** 等大多数支持标准 MCP 协议的客户端。

```json
{
  "mcpServers": {
    "qcc-mcp-server": {
      "transport": "streamable-http",
      "url": "https://mcp.qcc.com/basic/stream?key=YOUR_KEY"
    }
  }
}

```

---

### 3. 特殊客户端配置 (Cherry Studio)

Cherry Studio 目前对字段定义有特殊要求，请使用以下格式：

```json
{
  "mcpServers": {
    "qcc-mcp-server": {
      "type": "streamableHttp",
      "url": "https://mcp.qcc.com/basic/stream?key=YOUR_KEY"
    }
  }
}

```

---

### 4. 核心接入流程

1. **获取 URL**: 登录企查查开放平台，在 MCP 页面获取包含 `key` 的完整专属 URL。
2. **定位配置**:
* **Cursor**: `Settings` -> `Tools & MCP` -> `Add Custom MCP`。
* **Trae**: `AI Management` -> `MCP` -> `Add Manually`。
* **Cherry Studio**: `MCP` -> `添加` -> `从 JSON 导入`。


3. **写入配置**: 将上述对应的 JSON 片段粘贴至配置文件中（注意替换 `YOUR_KEY`）。
4. **验证状态**: 检查连接状态。
* **绿灯/对勾**: 表示连接成功，AI 已具备调用企查查数据的能力。



---

### 5. 常见问题排查

* **连接失败**: 请确认 MCP 服务余额充足且工具已在后台点击“启用”。
* **协议报错**: 若标准 `transport` 不行，请尝试将字段名改为 `type` (如 Cherry Studio 案例)。
