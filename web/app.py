#!/usr/bin/env python3
"""
抖音视频文案提取器 WebUI + MCP Streamable HTTP 端点

同时提供:
1. WebUI 界面 (用于手动操作和魔搭 MCP 保活)
2. MCP Streamable HTTP 端点 at /mcp (橘瓣可直接连接，无需魔搭)

启动方式:
    cd douyin-mcp-server
    export API_KEY="sk-xxx"
    python web/app.py
    # 访问 http://localhost:8080
"""

import os
import re
import sys
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "douyin-video" / "scripts"))
sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

from douyin_downloader import get_video_info, extract_text, HEADERS

# -- 使用独立 fastmcp 库创建 MCP 端点 --
try:
    # fastmcp (standalone) 支持 http_app(path="/") 和 lifespan 合并
    from mcp_fastmcp import mcp as douyin_mcp
    HAS_MCP = True
except ImportError:
    HAS_MCP = False
    print("WARNING: MCP tools not available, running WebUI only")

# -- 魔搭 MCP 保活配置 --
MCP_KEEPALIVE_URL = os.getenv("MCP_KEEPALIVE_URL", "")
KEEPALIVE_INTERVAL = int(os.getenv("KEEPALIVE_INTERVAL", "300"))
_keepalive_task = None

# -- 构建 ASGI 应用 --
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

if HAS_MCP:
    # 用 path="/" 创建 MCP 子应用，然后 mount 到 /mcp
    # path="/" 让 MCP 内部路由认为自己在根路径
    # 外层 mount("/mcp") 让它实际响应 /mcp/*
    mcp_app = douyin_mcp.http_app(path="/", transport="streamable-http")

    @asynccontextmanager
    async def combined_lifespan(app):
        # WebUI 启动任务
        global _keepalive_task
        if MCP_KEEPALIVE_URL:
            _keepalive_task = asyncio.create_task(keep_mcp_alive())
        # MCP 子应用的 lifespan
        async with mcp_app.lifespan(app) as maybe_state:
            yield maybe_state
        # 清理
        if _keepalive_task:
            _keepalive_task.cancel()

    app = FastAPI(
        title="Douyin MCP + WebUI",
        version="1.6.0",
        lifespan=combined_lifespan,
        redirect_slashes=False,
    )
    app.mount("/mcp", mcp_app)
    print("MCP endpoint mounted at /mcp (Streamable HTTP)")
    print("Clients connect to: https://douyin-mcp-server-production.up.railway.app/mcp")
else:
    app = FastAPI(
        title="Douyin MCP + WebUI",
        version="1.6.0",
        redirect_slashes=False,
    )

    @app.on_event("startup")
    async def startup():
        global _keepalive_task
        if MCP_KEEPALIVE_URL:
            _keepalive_task = asyncio.create_task(keep_mcp_alive())

    @app.on_event("shutdown")
    async def shutdown():
        if _keepalive_task:
            _keepalive_task.cancel()


async def keep_mcp_alive():
    """定时请求魔搭 MCP，防止 session 过期"""
    if not MCP_KEEPALIVE_URL:
        return
    print(f"Mcp keepalive started: every {KEEPALIVE_INTERVAL}s")
    while True:
        try:
            await asyncio.to_thread(requests.get, MCP_KEEPALIVE_URL, timeout=10)
        except Exception:
            pass
        await asyncio.sleep(KEEPALIVE_INTERVAL)


class VideoRequest(BaseModel):
    url: str
    api_key: str = ""


class VideoInfoResponse(BaseModel):
    success: bool
    video_id: str = ""
    title: str = ""
    download_url: str = ""
    error: str = ""


class ExtractResponse(BaseModel):
    success: bool
    video_id: str = ""
    title: str = ""
    text: str = ""
    download_url: str = ""
    error: str = ""


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    api_key = os.getenv("API_KEY", "")
    return {
        "status": "ok",
        "api_key_configured": bool(api_key),
        "mcp_endpoint": "/mcp",
        "mcp_available": HAS_MCP,
    }


@app.post("/api/video/info", response_model=VideoInfoResponse)
async def get_info(req: VideoRequest):
    try:
        info = await asyncio.to_thread(get_video_info, req.url)
        return VideoInfoResponse(
            success=True,
            video_id=info["video_id"],
            title=info["title"],
            download_url=info["url"],
        )
    except Exception as e:
        return VideoInfoResponse(success=False, error=str(e))


@app.post("/api/video/extract", response_model=ExtractResponse)
async def extract_transcript(req: VideoRequest):
    api_key = req.api_key or os.getenv("API_KEY", "")
    if not api_key:
        return ExtractResponse(success=False, error="Please configure API Key")
    try:
        result = await asyncio.to_thread(
            extract_text, req.url, api_key=api_key, show_progress=False
        )
        return ExtractResponse(
            success=True,
            video_id=result["video_info"]["video_id"],
            title=result["video_info"]["title"],
            text=result["text"],
            download_url=result["video_info"]["url"],
        )
    except Exception as e:
        return ExtractResponse(success=False, error=str(e))


def _content_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "video.mp4"
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(filename)}'


@app.get("/api/video/download")
async def download_video(video_id: str, filename: str = "video.mp4"):
    if not re.fullmatch(r"\d+", video_id):
        raise HTTPException(status_code=400, detail="Invalid video ID")
    try:
        share_url = f"https://www.iesdouyin.com/share/video/{video_id}"
        info = await asyncio.to_thread(get_video_info, share_url)
        download_headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Referer": "https://www.douyin.com/",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        response = await asyncio.to_thread(
            requests.get, info["url"],
            headers=download_headers, stream=True, allow_redirects=True
        )
        response.raise_for_status()
        content_length = response.headers.get("content-length", "")

        def iter_content():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

        headers = {"Content-Disposition": _content_disposition(filename)}
        if content_length:
            headers["Content-Length"] = content_length
        return StreamingResponse(
            iter_content(), media_type="video/mp4", headers=headers
        )
    except requests.exceptions.HTTPError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Download failed: {e.response.status_code}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    print(f"Starting Douyin MCP + WebUI on http://0.0.0.0:{port}")
    print(f"API_KEY configured: {bool(os.getenv('API_KEY'))}")
    print(f"WebUI: http://0.0.0.0:{port}/")
    print(f"MCP endpoint: http://0.0.0.0:{port}/mcp (Streamable HTTP)")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
