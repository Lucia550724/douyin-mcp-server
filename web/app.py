#!/usr/bin/env python3
"""
抖音视频文案提取器 WebUI (端口 8080) + MCP 服务 (端口 8081)

同时提供:
1. WebUI 界面 (端口 8080, 用于手动操作和魔搭 MCP 保活)
2. MCP Streamable HTTP (端口 8081, 橘瓣可直接连接)

启动方式:
    python web/app.py
"""

import os
import re
import sys
import asyncio
import multiprocessing
from pathlib import Path
from urllib.parse import quote

BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / "douyin-video" / "scripts"))

# ── WebUI 部分 ──────────────────────────────────────────
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import uvicorn
import requests

from douyin_downloader import get_video_info, extract_text, HEADERS

web_app = FastAPI(title="Douyin WebUI", version="1.6.0", redirect_slashes=False)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


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


@web_app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@web_app.get("/api/health")
async def health_check():
    api_key = os.getenv("API_KEY", "")
    return {
        "status": "ok",
        "api_key_configured": bool(api_key),
    }


@web_app.post("/api/video/info", response_model=VideoInfoResponse)
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


@web_app.post("/api/video/extract", response_model=ExtractResponse)
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


@web_app.get("/api/video/download")
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


# ── MCP 服务（独立端口） ──────────────────────────────────
def run_mcp_server():
    """在 8081 端口独立运行 MCP Streamable HTTP 服务"""
    sys.path.insert(0, str(BASE_DIR))
    from mcp_fastmcp import mcp
    import uvicorn
    mcp_port = int(os.getenv("MCP_PORT", "8081"))
    mcp_app = mcp.http_app(path="/", transport="streamable-http")
    print(f"MCP server starting on port {mcp_port}")
    uvicorn.run(mcp_app, host="0.0.0.0", port=mcp_port)


# ── 主入口 ────────────────────────────────────────────────
def run_webui():
    """在 8080 端口运行 WebUI"""
    port = int(os.getenv("PORT", "8080"))
    print(f"WebUI starting on port {port}")
    uvicorn.run(web_app, host="0.0.0.0", port=port)


def main():
    # Railway 的 PORT 环境变量是 8080，MCP 用 8081
    mcp_port = int(os.getenv("MCP_PORT", "8081"))
    web_port = int(os.getenv("PORT", "8080"))

    print(f"Starting Douyin services...")
    print(f"  WebUI: http://0.0.0.0:{web_port}/")
    print(f"  MCP:   http://0.0.0.0:{mcp_port}/ (Streamable HTTP)")
    print(f"  MCP connect URL: https://douyin-mcp-server-production.up.railway.app/ (port {mcp_port})")

    mcp_proc = multiprocessing.Process(target=run_mcp_server, daemon=True)
    mcp_proc.start()

    run_webui()


if __name__ == "__main__":
    main()
