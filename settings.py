"""Configuration management: constants and load/save of telegram_config.json."""

import importlib
import json
import os
import tempfile
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from java import jclass
    from android import activity

try:
    java = importlib.import_module("java")
    android = importlib.import_module("android")
    jclass = java.jclass
    activity = android.activity

    Environment = jclass("android.os.Environment")
    APP_FILES_DIR = activity.getFilesDir().getAbsolutePath()
    if not os.path.exists(APP_FILES_DIR):
        os.makedirs(APP_FILES_DIR, exist_ok=True)

    CONFIG_FILE = os.path.join(APP_FILES_DIR, "telegram_config.json")
    DB_FILE = os.path.join(APP_FILES_DIR, "telegram_manager.db")
    DEFAULT_DOWNLOAD_DIR = os.path.join(
        Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath(),
        "TelegramDownloads",
    )
except ImportError:
    CONFIG_FILE = "telegram_config.json"
    DB_FILE = "telegram_manager.db"
    DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "TelegramDownloads")

LANGUAGE_OPTIONS = [
    ("English", "en"), ("Arabic", "ar"), ("Turkish", "tr"),
    ("French", "fr"), ("Spanish", "es"), ("Hindi", "hi"), ("Urdu", "ur"),
]

# LibreTranslate mirrors — tried in order, first working one wins
LIBRETRANSLATE_MIRRORS = [
    "https://libretranslate.de/translate",
    "https://translate.argosopentech.com/translate",
    "https://libretranslate.com/translate",
]

# Premium constants
PREMIUM_MSG_LIMIT = 200
STD_MSG_LIMIT = 60
PREMIUM_MAX_CONCURRENT_DL = 6
STD_MAX_CONCURRENT_DL = 2

# Batch forward constants
BATCH_SIZE = 99
BATCH_CACHE_DIR = os.path.join(tempfile.gettempdir(), "tg_batch_cache")
MAX_WORKERS = 4

# Auto-sync defaults
DEFAULT_SYNC_INTERVAL_MINUTES = 30

# Web UI defaults
WEBUI_PORT = 8080


def load_config() -> Optional[Dict[str, Any]]:
    """Load config from CONFIG_FILE, or None if it doesn't exist."""
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def get_setting(key: str, default: Any) -> Any:
    """Read a user-overridable setting from telegram_config.json, falling
    back to the given default (usually a module constant above) if unset."""
    cfg = load_config() or {}
    value = cfg.get(key)
    return value if value is not None else default
