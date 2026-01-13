import os
import json
from typing import Any, Dict
import sys

ASR_DICT = [("自动检测", "Auto"), ("无", "None"), ("英语", "en"), ("中文", "zh"), ("西班牙语", "es"), ("日语", "ja"), ("法语", "fr"), ("德语", "de"),
            ("韩语", "ko"), ("葡萄牙语", "pt"), ("俄语", "ru"), ("意大利语", "it"), ("印尼语", "id"), ("土耳其语", "tr"), ("越南语", "vi"),
            ("阿拉伯语", "ar"), ("荷兰语", "nl")]
TRANS_DICT = [("中文", "zh"), ("无", "None"), ("英语", "en"), ("西班牙语", "es"), ("日语", "ja"), ("法语", "fr"), ("德语", "de"), ("韩语", "ko"),
              ("葡萄牙语", "pt"), ("俄语", "ru"), ("意大利语", "it"), ("印尼语", "id"), ("土耳其语", "tr"), ("越南语", "vi"),
              ("阿拉伯语", "ar"), ("荷兰语", "nl")]
# --- UPDATE CONFIGURATION ---
CURRENT_VERSION = "1.0"
# PASTE YOUR RAW GITHUB LINK INSIDE THE QUOTES BELOW:
UPDATE_URL = "https://gitee.com/nicksub/nick-sub-updates/raw/master/version.json"

BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


# 简化资源路径定义，实际路径检测由main.py负责
def _detect_resources_dir() -> str:
    """检测resources目录位置，确保在不同分发环境下都能正确找到资源"""
    candidates = [
        os.path.join(BASE_DIR, "resources"),
        os.path.join(os.path.dirname(BASE_DIR), "resources"),
        os.path.join(BASE_DIR, "_internal", "resources"),
        os.path.join(BASE_DIR, "_internal", "_internal", "resources"),
    ]
    best = None
    for p in candidates:
        if os.path.isdir(p):
            ff = os.path.join(p, "bin", "ffmpeg.exe")
            if os.path.isfile(ff):
                return p
            best = best or p
    return best or os.path.join(BASE_DIR, "resources")


# 修复FFmpeg路径问题：使用动态检测的资源目录
RESOURCES_DIR = _detect_resources_dir()
DEFAULT_FFMPEG_PATH = os.path.join(RESOURCES_DIR, "bin", "ffmpeg.exe")

APP_NAME = "NickSub Pro v1.0"
DEFAULT_API_BASE = os.environ.get("BISUB_API_BASE", "https://api.nicksubtitle.com")

WORK_DIR = os.path.join(os.path.expanduser("~"), ".NickSub")
AUDIO_DIR = os.path.join(WORK_DIR, "audio")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs")
DOWNLOAD_DIR = os.path.join(WORK_DIR, "downloads")
CONFIG_PATH = os.path.join(WORK_DIR, "config.json")
TOKEN_PATH = os.path.join(WORK_DIR, ".token")

RESULT_DIR = os.path.join(WORK_DIR, "result")
SUB_RESULT_DIR = os.path.join(RESULT_DIR, "sub_result")
VIDEO_RESULT_DIR = os.path.join(RESULT_DIR, "video_result")
DOWNLOAD_VIDEO_DIR = os.path.join(RESULT_DIR, "download_video")


def ensure_dirs():
    for d in (
    WORK_DIR, AUDIO_DIR, OUTPUT_DIR, DOWNLOAD_DIR, RESULT_DIR, SUB_RESULT_DIR, VIDEO_RESULT_DIR, DOWNLOAD_VIDEO_DIR):
        os.makedirs(d, exist_ok=True)


def read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


# 添加缺失的配置加载和保存函数
def load_config() -> Dict[str, Any]:
    """Load application configuration from file."""
    default_config = {
        "theme": "Light",
        "ffmpeg_path": DEFAULT_FFMPEG_PATH,
        "work_dir": WORK_DIR
    }
    config = read_json(CONFIG_PATH, default_config)

    # 确保ffmpeg_path始终指向正确的路径
    if "ffmpeg_path" not in config or not config["ffmpeg_path"] or not os.path.exists(config["ffmpeg_path"]):
        config["ffmpeg_path"] = DEFAULT_FFMPEG_PATH

    return config


def save_config(config: Dict[str, Any]) -> None:
    """Save application configuration to file."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")