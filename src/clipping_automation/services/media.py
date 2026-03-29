from __future__ import annotations

import shutil
import tempfile
import urllib.parse
from pathlib import Path

import requests

from clipping_automation.utils import ensure_directory


def create_temp_download_dir(base_dir: Path) -> Path:
    ensure_directory(base_dir)
    return Path(tempfile.mkdtemp(prefix="remote_media_", dir=base_dir))


def cleanup_temp_dir(path: Path | None) -> None:
    if path and path.exists():
        shutil.rmtree(path, ignore_errors=True)


def downloadable_media_url(source_type: str, media_url: str | None) -> bool:
    if not media_url:
        return False
    parsed = urllib.parse.urlparse(media_url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if source_type == "youtube":
        return False
    return True


def download_media(url: str, destination: Path, timeout: int = 60) -> Path:
    ensure_directory(destination.parent)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with destination.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    return destination
