任意支持 MCP 协议的客户端皆可接入

除了下方示例的 Cursor、Trae、Cherry Studio 外，任何支持 MCP 协议的 AI 工具（如 Claude、Cline、Continue、Witsy 等）都可以通过相同方式接入企查查 MCP 服务：

{
    "mcpServers":{
      "qcc-mcp-server": {
        "transport": "streamable-http",
        "url": "https://mcp.qcc.com/basic/stream?key=YOUR_KEY"
      }
    }
}
只需将上述配置添加到对应客户端 MCP 配置文件中，即可启用企查查企业数据能力