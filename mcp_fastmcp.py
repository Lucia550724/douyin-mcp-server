#!/usr/bin/env python3
"""用独立 fastmcp 包创建的抖音 MCP Server"""
import os
import re
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "douyin-video" / "scripts"))

from fastmcp import FastMCP
from douyin_downloader import get_video_info, extract_text, HEADERS
import requests

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


def _rich_parse(share_text: str) -> dict:
    """
    更完整地解析抖音分享链接，提取图片、视频、封面等所有可用内容
    """
    # 提取分享链接
    urls = re.findall(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
        share_text
    )
    if not urls:
        raise ValueError("未找到有效的分享链接")

    share_url = urls[0]
    share_response = requests.get(share_url, headers=HEADERS)
    video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
    api_url = f"https://www.iesdouyin.com/share/video/{video_id}"

    response = requests.get(api_url, headers=HEADERS)
    response.raise_for_status()

    pattern = re.compile(
        pattern=r"window\._ROUTER_DATA\s*=\s*(.*?)</script>",
        flags=re.DOTALL,
    )
    match = pattern.search(response.text)
    if not match:
        raise ValueError("从HTML中解析视频信息失败")

    json_data = json.loads(match.group(1).strip())
    VIDEO_KEY = "video_(id)/page"
    NOTE_KEY = "note_(id)/page"

    if VIDEO_KEY in json_data["loaderData"]:
        page_data = json_data["loaderData"][VIDEO_KEY]
    elif NOTE_KEY in json_data["loaderData"]:
        page_data = json_data["loaderData"][NOTE_KEY]
    else:
        raise Exception("无法从JSON中解析内容")

    item = page_data["videoInfoRes"]["item_list"][0]
    desc = item.get("desc", "").strip() or f"douyin_{video_id}"
    desc = re.sub(r'[\\/:*?"<>|]', '_', desc)

    result = {
        "video_id": video_id,
        "title": desc,
        "content_type": "video",
        "images": [],
        "video_url": None,
        "cover_url": None,
        "author": None,
        "music": None,
    }

    # 作者信息
    if "author" in item:
        author_info = item["author"]
        result["author"] = {
            "nickname": author_info.get("nickname", ""),
            "avatar": author_info.get("avatar_thumb", {}).get("url_list", [None])[0] if "avatar_thumb" in author_info else None,
            "unique_id": author_info.get("unique_id", ""),
        }

    # 封面图
    if "video" in item and "cover" in item["video"]:
        result["cover_url"] = item["video"]["cover"]["url_list"][0] if item["video"]["cover"].get("url_list") else None

    # 图文作品的图片集
    if "images" in item:
        result["content_type"] = "image_post"
        result["images"] = [
            img.get("url_list", [img.get("display_url", "")])[0]
            for img in item["images"]
            if img.get("url_list") or img.get("display_url")
        ]
        result["image_count"] = len(result["images"])

    # 视频信息
    if "video" in item and "play_addr" in item["video"]:
        result["content_type"] = "video" if result["content_type"] == "video" else "mixed"
        video_url = item["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        result["video_url"] = video_url

    # 音乐信息
    if "music" in item:
        music = item["music"]
        result["music"] = {
            "title": music.get("title", ""),
            "author": music.get("author", ""),
            "cover": music.get("cover_thumb", {}).get("url_list", [None])[0] if "cover_thumb" in music else None,
        }

    return result


@mcp.tool()
def extract_douyin_content(share_link: str) -> str:
    """
    从抖音分享链接提取完整内容（图片、封面、视频、文字、作者信息等）
    支持视频和图文作品

    参数:
    - share_link: 抖音分享链接或包含链接的文本

    返回:
    - 包含完整内容的JSON字符串，图片URL可用于OCR识别
    """
    try:
        info = _rich_parse(share_link)
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)
