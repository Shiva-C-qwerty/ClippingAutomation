from __future__ import annotations

import os
import shutil
import tomllib
from pathlib import Path

from clipping_automation.utils import ensure_directory

ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"
DATA_DIR = ROOT_DIR / "data"
STATE_DIR = DATA_DIR / "state"
EXPORT_DIR = DATA_DIR / "exports"
APPROVED_ASSETS_DIR = DATA_DIR / "assets" / "approved"

DEFAULT_CONFIG_PATH = CONFIG_DIR / "sources.toml"
EXAMPLE_CONFIG_PATH = CONFIG_DIR / "sources.example.toml"
DEFAULT_DB_PATH = STATE_DIR / "clips.db"
DEFAULT_EXPORT_DIR = EXPORT_DIR
DEFAULT_YOUTUBE_TOKEN_PATH = STATE_DIR / "youtube_token.json"


def bootstrap_workspace() -> dict[str, Path]:
    ensure_directory(CONFIG_DIR)
    ensure_directory(DATA_DIR)
    ensure_directory(STATE_DIR)
    ensure_directory(EXPORT_DIR)
    ensure_directory(APPROVED_ASSETS_DIR)

    if EXAMPLE_CONFIG_PATH.exists() and not DEFAULT_CONFIG_PATH.exists():
        shutil.copy2(EXAMPLE_CONFIG_PATH, DEFAULT_CONFIG_PATH)

    return {
        "config_path": DEFAULT_CONFIG_PATH,
        "db_path": DEFAULT_DB_PATH,
        "exports_dir": EXPORT_DIR,
        "approved_assets_dir": APPROVED_ASSETS_DIR,
    }


def load_source_config(path: Path | None = None) -> dict:
    config_path = path or DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Run `clipbot init` first."
        )

    with config_path.open("rb") as handle:
        return tomllib.load(handle)


def env_value(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)
