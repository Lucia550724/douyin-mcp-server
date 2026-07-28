#!/usr/bin/env python3
"""SSE 模式启动入口 - 用于 Railway 部署"""
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 强制设置 PORT 环境变量给 FastMCP 使用
port = os.getenv("PORT", "8080")
os.environ["PORT"] = port

print(f"🚀 启动抖音 MCP Server (SSE模式) on port {port}")

from douyin_mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="sse")
