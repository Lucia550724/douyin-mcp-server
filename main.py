#!/usr/bin/env python3
"""Railway 部署入口 - FastAPI 挂载 MCP Server"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "douyin-video" / "scripts"))

from douyin_mcp_server.server import mcp
from fastapi import FastAPI
import uvicorn

app = FastAPI(title="抖音 MCP Server")

@app.get("/")
async def root():
    return {"status": "ok", "message": "Douyin MCP Server is running"}

# 用 http_app() 支持 Streamable HTTP 协议
app.mount("/mcp", mcp.http_app())

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
