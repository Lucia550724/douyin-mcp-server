#!/usr/bin/env python3
"""HTTP/SSE 模式启动入口 - 用于 Railway 部署"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from douyin_mcp_server.server import mcp
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"🚀 启动抖音 MCP Server (HTTP模式) on {host}:{port}")
    
    # 使用 http_app() 获取 ASGI 应用，用 uvicorn 运行
    try:
        app = mcp.http_app()
        uvicorn.run(app, host=host, port=port)
    except AttributeError:
        # 如果不支持 http_app，回退到 sse_app
        try:
            app = mcp.sse_app()
            uvicorn.run(app, host=host, port=port)
        except AttributeError:
            # 最保守的方式，直接用 run
            mcp.run(transport="sse", host=host, port=port)
