import os
import json
from typing import Any, Dict
import sys

ASR_DICT = [("自动检测", "Auto"), ("英语", "en"), ("中文", "zh"), ("西班牙语", "es"), ("日语", "ja"), ("法语", "fr"), ("德语", "de"), ("韩语", "ko"), ("葡萄牙语", "pt"), ("俄语", "ru"), ("意大利语", "it"), ("印尼语", "id"), ("土耳其语", "tr"),  ("越南语", "vi"), ("阿拉伯语", "ar"), ("荷兰语", "nl")]
TRANS_DICT = [("中文", "zh"), ("英语", "en"), ("西班牙语", "es"), ("日语", "ja"), ("法语", "fr"), ("德语", "de"), ("韩语", "ko"), ("葡萄牙语", "pt"), ("俄语", "ru"), ("意大利语", "it"), ("印尼语", "id"), ("土耳其语", "tr"),  ("越南语", "vi"), ("阿拉伯语", "ar"), ("荷兰语", "nl")]
# --- UPDATE CONFIGURATION ---
CURRENT_VERSION = "1.0"
# PASTE YOUR RAW GITHUB LINK INSIDE THE QUOTES BELOW:
UPDATE_URL = "https://gitee.com/nicksub/nick-sub-updates/raw/master/version.json"

# --- robust base dir (works in dev & PyInstaller) ---
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

# 简化资源路径定义，实际路径检测由main.py负责
RESOURCES_DIR = os.path.join(BASE_DIR, "resources")
DEFAULT_FFMPEG_PATH = os.path.join(RESOURCES_DIR, "bin", "ffmpeg.exe")

RESULT_DIR = os.path.join(BASE_DIR, "Result")
SUB_RESULT_DIR = os.path.join(RESULT_DIR, "sub_result")
VIDEO_RESULT_DIR = os.path.join(RESULT_DIR, "video_result")

APP_NAME = "NickSub Pro v1.0"
DEFAULT_API_BASE = os.environ.get("BISUB_API_BASE", "https://api.nicksubtitle.com")

WORK_DIR = os.path.join(os.path.expanduser("~"), ".bisubpro")
AUDIO_DIR = os.path.join(WORK_DIR, "audio")
OUTPUT_DIR = os.path.join(WORK_DIR, "outputs")
DOWNLOAD_DIR = os.path.join(WORK_DIR, "downloads")
CONFIG_PATH = os.path.join(WORK_DIR, "config.json")
TOKEN_PATH = os.path.join(WORK_DIR, ".token")

def ensure_dirs():
    for d in (WORK_DIR, AUDIO_DIR, OUTPUT_DIR, DOWNLOAD_DIR, RESULT_DIR, SUB_RESULT_DIR, VIDEO_RESULT_DIR):
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
    return read_json(CONFIG_PATH, default_config)

def save_config(config: Dict[str, Any]) -> None:
    """Save application configuration to file."""
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")