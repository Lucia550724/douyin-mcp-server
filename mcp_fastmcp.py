#!/usr/bin/env python3
"""用独立 fastmcp 包创建的抖音 MCP Server"""
import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "douyin-video" / "scripts"))

from fastmcp import FastMCP
from douyin_downloader import get_video_info, extract_text

mcp = FastMCP("Douyin MCP Server")


@mcp.tool()
def parse_douyin_video_info(share_link: str) -> str:
    """
    解析抖音分享链接，获取视频基本信息

    参数:
    - share_link: 抖音分享链接或包含链接的文本

    返回:
    - 视频信息（JSON格式字符串）
    """
    try:
        info = get_video_info(share_link)
        return json.dumps({
            "video_id": info["video_id"],
            "title": info["title"],
            "download_url": info["url"],
            "status": "success"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_douyin_download_link(share_link: str) -> str:
    """
    获取抖音视频的无水印下载链接

    参数:
    - share_link: 抖音分享链接或包含链接的文本

    返回:
    - 包含下载链接和视频信息的JSON字符串
    """
    try:
        info = get_video_info(share_link)
        return json.dumps({
            "status": "success",
            "video_id": info["video_id"],
            "title": info["title"],
            "download_url": info["url"]
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def extract_douyin_text(share_link: str) -> str:
    """
    从抖音分享链接提取视频中的文本内容

    参数:
    - share_link: 抖音分享链接或包含链接的文本

    返回:
    - 提取的文本内容

    注意: 需要设置环境变量 API_KEY（硅基流动）或 DASHSCOPE_API_KEY（阿里云百炼）
    """
    api_key = os.getenv("API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return json.dumps({
            "status": "error",
            "error": "未设置 API_KEY 或 DASHSCOPE_API_KEY 环境变量"
        }, ensure_ascii=False)
    try:
        result = extract_text(share_link, api_key=api_key, show_progress=False)
        return json.dumps({
            "status": "success",
            "video_id": result["video_info"]["video_id"],
            "title": result["video_info"]["title"],
            "text": result["text"]
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)
