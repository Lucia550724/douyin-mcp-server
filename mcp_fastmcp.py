#!/usr/bin/env python3
"""用独立 fastmcp 包创建的抖音 MCP Server"""
import os
import re
import json
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "douyin-video" / "scripts"))

from fastmcp import FastMCP
from douyin_downloader import get_video_info, extract_text, HEADERS
import requests

mcp = FastMCP("Douyin MCP Server")

DASHSCOPE_VISION_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
DASHSCOPE_VISION_MODEL = "qwen3-vl-plus"
SILICONFLOW_VISION_URL = "https://api.siliconflow.cn/v1/chat/completions"
SILICONFLOW_VISION_MODEL = "Qwen/Qwen2.5-VL-72B-Instruct"


def _find_bin(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    for p in ["/usr/bin", "/usr/local/bin", "/opt/homebrew/bin", "/usr/local/opt/ffmpeg/bin"]:
        candidate = Path(p) / name
        if candidate.exists():
            return str(candidate)
    raise FileNotFoundError(f"{name} not found. Please install ffmpeg")


@mcp.tool()
def parse_douyin_video_info(share_link: str) -> str:
    try:
        info = get_video_info(share_link)
        return json.dumps({"video_id": info["video_id"], "title": info["title"], "download_url": info["url"], "status": "success"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_douyin_download_link(share_link: str) -> str:
    try:
        info = get_video_info(share_link)
        return json.dumps({"status": "success", "video_id": info["video_id"], "title": info["title"], "download_url": info["url"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def extract_douyin_text(share_link: str) -> str:
    api_key = os.getenv("API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return json.dumps({"status": "error", "error": "未设置 API_KEY 或 DASHSCOPE_API_KEY"}, ensure_ascii=False)
    try:
        result = extract_text(share_link, api_key=api_key, show_progress=False)
        return json.dumps({"status": "success", "video_id": result["video_info"]["video_id"], "title": result["video_info"]["title"], "text": result["text"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


def _rich_parse(share_text: str) -> dict:
    urls = re.findall(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', share_text)
    if not urls:
        raise ValueError("未找到有效的分享链接")
    share_url = urls[0]
    share_response = requests.get(share_url, headers=HEADERS)
    video_id = share_response.url.split("?")[0].strip("/").split("/")[-1]
    response = requests.get(f"https://www.iesdouyin.com/share/video/{video_id}", headers=HEADERS)
    response.raise_for_status()
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", response.text, re.DOTALL)
    if not match:
        raise ValueError("从HTML中解析视频信息失败")
    json_data = json.loads(match.group(1).strip())
    ld = json_data["loaderData"]
    key = "video_(id)/page" if "video_(id)/page" in ld else ("note_(id)/page" if "note_(id)/page" in ld else None)
    if not key:
        raise Exception("无法从JSON中解析内容")
    item = ld[key]["videoInfoRes"]["item_list"][0]
    desc = re.sub(r'[\\/:*?"<>|]', '_', item.get("desc", "").strip() or f"douyin_{video_id}")
    result = {"video_id": video_id, "title": desc, "content_type": "video", "images": [], "video_url": None, "cover_url": None, "author": None, "music": None}
    if "author" in item:
        a = item["author"]
        av = a.get("avatar_thumb", {}).get("url_list")
        result["author"] = {"nickname": a.get("nickname", ""), "avatar": av[0] if av else None, "unique_id": a.get("unique_id", "")}
    if isinstance(item.get("video"), dict):
        cv = item["video"].get("cover")
        if isinstance(cv, dict):
            cl = cv.get("url_list")
            if cl:
                result["cover_url"] = cl[0]
        pa = item["video"].get("play_addr")
        if isinstance(pa, dict):
            vl = pa.get("url_list")
            if vl:
                result["video_url"] = vl[0].replace("playwm", "play")
                if result["content_type"] == "image_post":
                    result["content_type"] = "mixed"
    imgs = item.get("images")
    if isinstance(imgs, list):
        result["content_type"] = "image_post"
        urls = []
        for img in imgs:
            if isinstance(img, dict):
                u = img.get("url_list", img.get("display_url", []))
                if isinstance(u, list) and u:
                    urls.append(u[0])
                elif isinstance(u, str):
                    urls.append(u)
        if urls:
            result["images"] = urls
            result["image_count"] = len(urls)
    mus = item.get("music")
    if isinstance(mus, dict):
        ct = mus.get("cover_thumb", {})
        cl = ct.get("url_list") if isinstance(ct, dict) else None
        result["music"] = {"title": mus.get("title", ""), "author": mus.get("author", ""), "cover": cl[0] if cl else None}
    return result


@mcp.tool()
def extract_douyin_content(share_link: str) -> str:
    try:
        return json.dumps(_rich_parse(share_link), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


# 图文兼视觉描述 prompt：同时提取文字 + 描述画面
IMAGE_ANALYZE_PROMPT = (
    "请综合描述这张图片的完整内容，包括两个方面：\n"
    "1. 【画面描述】图片中有什么物体、人物、场景、颜色、风格，整体的构图和氛围\n"
    "2. 【文字提取】图片中出现的所有文字内容，包括标题、正文、贴纸、水印、品牌标识等\n"
    "请用中文详细回答，先描述画面再给出文字内容"
)


def _analyze_image(image_url: str, api_key: str, prompt: str = IMAGE_ANALYZE_PROMPT) -> str:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url, model = (DASHSCOPE_VISION_URL, DASHSCOPE_VISION_MODEL) if os.getenv("DASHSCOPE_API_KEY") else (SILICONFLOW_VISION_URL, SILICONFLOW_VISION_MODEL)
    resp = requests.post(url, headers=headers, json={"model": model, "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_url}}, {"type": "text", "text": prompt}]}], "max_tokens": 4096}, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


@mcp.tool()
def analyze_douyin_images(share_link: str) -> str:
    """
    分析抖音图文/视频封面中的图片内容，同时提取文字和描述画面

    参数:
    - share_link: 抖音分享链接

    返回:
    - 每张图片的画面描述 + 文字内容
    """
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        return json.dumps({"status": "error", "error": "请设置 DASHSCOPE_API_KEY"}, ensure_ascii=False)
    try:
        info = _rich_parse(share_link)
        urls = list(info.get("images", []))
        if info.get("cover_url"):
            urls.append(info["cover_url"])
        if not urls:
            return json.dumps({"status": "error", "error": "未找到可识别的图片"}, ensure_ascii=False)
        result = {"status": "success", "video_id": info["video_id"], "title": info["title"], "author": info.get("author", {}).get("nickname", ""), "content_type": info["content_type"], "image_count": len(urls), "image_analysis": []}
        for i, u in enumerate(urls):
            result["image_analysis"].append({"image_index": i + 1, "content": _analyze_image(u, api_key)})
        if info.get("music"):
            result["background_music"] = info["music"]["title"]
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


def _download_video(video_url: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    p = Path(tmp.name)
    r = requests.get(video_url, headers=HEADERS, stream=True, timeout=30)
    r.raise_for_status()
    with open(p, "wb") as f:
        for c in r.iter_content(8192):
            if c:
                f.write(c)
    return p


def _extract_frames(video_path: Path, num_frames: int = 5) -> list[Path]:
    ffprobe = _find_bin("ffprobe")
    ffmpeg = _find_bin("ffmpeg")
    frames = []
    dur = float(subprocess.check_output([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)], timeout=15).decode().strip())
    if dur <= 0:
        dur = 30
    interval = max(dur / (num_frames + 1), 1)
    for i in range(num_frames):
        fp = video_path.with_name(f"frame_{i}.jpg")
        subprocess.run([ffmpeg, "-y", "-ss", str(interval * (i + 1)), "-i", str(video_path), "-vframes", "1", "-q:v", "2", str(fp)], capture_output=True, timeout=30)
        if fp.exists():
            frames.append(fp)
    if not frames:
        raise Exception("未能提取到任何视频帧")
    return frames


def _image_to_base64(image_path: Path) -> str:
    import base64
    with open(image_path, "rb") as f:
        return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"


def _analyze_frames(frames: list[Path], api_key: str, prompt: str) -> str:
    url, model = (DASHSCOPE_VISION_URL, DASHSCOPE_VISION_MODEL) if os.getenv("DASHSCOPE_API_KEY") else (SILICONFLOW_VISION_URL, SILICONFLOW_VISION_MODEL)
    content = [{"type": "text", "text": prompt}]
    for f in frames:
        content.append({"type": "image_url", "image_url": {"url": _image_to_base64(f)}})
    r = requests.post(url, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 4096}, timeout=120)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


@mcp.tool()
def analyze_douyin_video(share_link: str, num_frames: int = 5) -> str:
    """
    从抖音链接下载视频，提取关键帧，并用视觉模型分析画面内容

    参数:
    - share_link: 抖音分享链接
    - num_frames: 抽取帧数（默认5张，越多越详细但消耗更多额度）

    返回:
    - 视频画面内容的文字描述
    """
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("API_KEY")
    if not api_key:
        return json.dumps({"status": "error", "error": "请设置 DASHSCOPE_API_KEY"}, ensure_ascii=False)
    video_path = None
    try:
        info = _rich_parse(share_link)
        vu = info.get("video_url")
        if not vu:
            return json.dumps({"status": "error", "error": "该内容没有视频可下载"}, ensure_ascii=False)
        result = {"status": "success", "video_id": info["video_id"], "title": info["title"], "author": info.get("author", {}).get("nickname", "")}
        video_path = _download_video(vu)
        frames = _extract_frames(video_path, num_frames)
        result["frames_extracted"] = len(frames)
        analysis = _analyze_frames(frames, api_key, "请分析这组视频截图，详细描述：1.画面中的场景和人物/动物 2.任何文字内容（标题、字幕、贴纸、水印）3.风格、氛围和主题 4.动作、表情、互动。请用中文详细描述")
        result["analysis"] = analysis
        if info.get("music"):
            result["background_music"] = info["music"]["title"]
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)
    finally:
        if video_path and video_path.exists():
            video_path.unlink(missing_ok=True)
            for f in video_path.parent.glob("frame_*.jpg"):
                f.unlink(missing_ok=True)
