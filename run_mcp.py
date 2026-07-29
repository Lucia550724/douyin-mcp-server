#!/usr/bin/env python3
"""
抖音 MCP 服务器 - 独立入口 (Streamable HTTP)
直接运行在 Railway PORT 上，无 WebUI 依赖
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

# ── 启动前确保 ffmpeg 可用 ──────────────────────────────
def ensure_ffmpeg():
    """检查并安装 ffmpeg（Railpack 不会执行 nixpacks cmds）"""
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return  # 已经有了

    print("ffmpeg not found, attempting to install...")
    methods = [
        # 方法1: apt-get
        ["apt-get", "update", "-qq"],
        ["apt-get", "install", "-y", "-qq", "ffmpeg"],
        # 方法2: apt
        ["apt", "update", "-qq"],
        ["apt", "install", "-y", "-qq", "ffmpeg"],
        # 方法3: 通过 pip 安装 static ffmpeg
        [sys.executable, "-m", "pip", "install", "ffmpeg-static"],
    ]

    for i in range(0, len(methods), 2):
        if i + 1 < len(methods):
            try:
                subprocess.run(methods[i], capture_output=True, timeout=30)
                subprocess.run(methods[i + 1], capture_output=True, timeout=60)
                if shutil.which("ffprobe"):
                    print("ffmpeg installed successfully!")
                    return
            except Exception:
                continue

    print("WARNING: Could not install ffmpeg - video frame extraction will not work")
    print(f"  ffmpeg found: {shutil.which('ffmpeg') is not None}")
    print(f"  ffprobe found: {shutil.which('ffprobe') is not None}")

ensure_ffmpeg()


BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR / "douyin-video" / "scripts"))
sys.path.insert(0, str(BASE_DIR))

import uvicorn
from mcp_fastmcp import mcp

# 创建 Streamable HTTP 应用
app = mcp.http_app(path="/", transport="streamable-http")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"Starting Douyin MCP Server (Streamable HTTP) on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
