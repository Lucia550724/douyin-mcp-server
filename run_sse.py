#!/usr/bin/env python3
"""SSE 模式启动入口 - 用于 Railway 部署"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from douyin_mcp_server.server import mcp

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    print(f"🚀 启动抖音 MCP Server (SSE模式): http://0.0.0.0:{port}")
    mcp.run(transport="sse", port=port)
