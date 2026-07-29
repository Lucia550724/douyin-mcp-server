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

# 阿里云百炼视觉模型（qwen3-vl-plus 有免费额度）
DASHSCOPE_VISION_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DASHSCOPE_VISION_MODEL = "qwen3-vl-plus"

# 硅基流动视觉模型（备用）
SILICONFLOW_VISION_URL = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_VISION_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"


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
    从抖音分享链接提取视频中的文本内容（语音转文字）

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
    """完整解析抖音分享链接，提取图片、视频、封面等内容"""
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

    if "author" in item:
        author_info = item["author"]
        result["author"] = {
            "nickname": author_info.get("nickname", ""),
            "avatar": author_info.get("avatar_thumb", {}).get("url_list", [None])[0] if "avatar_thumb" in author_info else None,
            "unique_id": author_info.get("unique_id", ""),
        }

    if "video" in item and "cover" in item["video"]:
        result["cover_url"] = item["video"]["cover"]["url_list"][0] if item["video"]["cover"].get("url_list") else None

    if "images" in item:
        result["content_type"] = "image_post"
        result["images"] = [
            img.get("url_list", [img.get("display_url", "")])[0]
            for img in item["images"]
            if img.get("url_list") or img.get("display_url")
        ]
        result["image_count"] = len(result["images"])

    if "video" in item and "play_addr" in item["video"]:
        result["content_type"] = "video" if result["content_type"] == "video" else "mixed"
        video_url = item["video"]["play_addr"]["url_list"][0].replace("playwm", "play")
        result["video_url"] = video_url

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
    """
    try:
        info = _rich_parse(share_link)
        return json.dumps(info, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


def _ocr_image(image_url: str, api_key: str, prompt: str = "请提取这张图片中的所有文字内容，包括标题、正文、水印等") -> str:
    """使用视觉模型提取图片中的文字"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # 优先使用 DASHSCOPE_API_KEY + 阿里云百炼（qwen3-vl-plus 有免费额度）
    if os.getenv("DASHSCOPE_API_KEY"):
        url = DASHSCOPE_VISION_URL
        model = DASHSCOPE_VISION_MODEL
    else:
        # 否则用硅基流动
        url = SILICONFLOW_VISION_URL
        model = SILICONFLOW_VISION_MODEL

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "max_tokens": 4096
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


@mcp.tool()
def analyze_douyin_images(share_link: str) -> str:
    """
    从抖音链接提取所有图片，并用视觉模型自动识别图片中的文字内容
    支持图文作品（多张图片）和视频封面

    参数:
    - share_link: 抖音分享链接或包含链接的文本

    返回:
    - 图片中的文字内容

    注意: 
    - 推荐设置 DASHSCOPE_API_KEY（阿里云百炼，qwen3-vl-plus 免费额度）
    - 也可设置 API_KEY（硅基流动）
    """
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        return json.dumps({
            "status": "error",
            "error": "请设置环境变量 DASHSCOPE_API_KEY（推荐，有免费额度）或 API_KEY"
        }, ensure_ascii=False)

    try:
        info = _rich_parse(share_link)
        image_urls = []

        if info.get("images"):
            image_urls.extend(info["images"])
        if info.get("cover_url"):
            image_urls.append(info["cover_url"])

        if not image_urls:
            return json.dumps({
                "status": "error",
                "error": "未找到可识别的图片"
            }, ensure_ascii=False)

        results = {
            "status": "success",
            "video_id": info["video_id"],
            "title": info["title"],
            "author": info.get("author", {}).get("nickname", ""),
            "content_type": info["content_type"],
            "image_count": len(image_urls),
            "extracted_text": []
        }

        for i, img_url in enumerate(image_urls):
            text = _ocr_image(img_url, api_key)
            results["extracted_text"].append({
                "image_index": i + 1,
                "text": text
            })

        if info.get("music"):
            results["background_music"] = info["music"]["title"]

        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)
