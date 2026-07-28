#!/usr/bin/env python3
"""Railway 部署入口 - FastAPI 挂载 MCP Server 到 /mcp"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "douyin-video" / "scripts"))

from douyin_mcp_server.server import mcp
from fastapi import FastAPI
import uvicorn

# 创建 FastAPI 应用
app = FastAPI(title="抖音 MCP Server")

# 健康检查
@app.get("/")
async def root():
    return {"status": "ok", "message": "Douyin MCP Server is running"}

# 挂载 MCP Server 到 /mcp 路径
app.mount("/mcp", mcp.sse_app())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
