#!/usr/bin/env python3
"""
抖音 MCP 服务器 - 独立入口 (Streamable HTTP)
直接运行在 Railway PORT 上，无 WebUI 依赖
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "douyin-video" / "scripts"))
sys.path.insert(0, str(BASE_DIR))

import uvicorn

from mcp_fastmcp import mcp

# 创建 Streamable HTTP 应用，path="/" 让路由在根路径生效
app = mcp.http_app(path="/", transport="streamable-http")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Douyin MCP Server (Streamable HTTP) on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
