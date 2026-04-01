from __future__ import annotations

import json
import subprocess
from pathlib import Path

from clipping_automation.config import DEFAULT_DB_PATH
from clipping_automation.db import connect, fetch_candidates, get_candidate, update_candidate_music_detection
from clipping_automation.services.media import (
    cleanup_temp_dir,
    create_temp_download_dir,
    downloadable_media_url,
    download_media,
    download_reddit_media,
)
from clipping_automation.utils import ensure_directory, slugify, utc_now_iso


def _resolve_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Automatic music detection requires numpy. Install dependencies with `pip install -r requirements.txt`."
        ) from exc
    return np


def _ffprobe_has_audio(input_path: Path) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(input_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("ffprobe is required for automatic music detection.") from exc

    return bool(result.stdout.strip())


def _extract_audio_samples(input_path: Path, sample_rate: int = 16000):
    np = _resolve_numpy()
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(sample_rate),
                "-f",
                "s16le",
                "pipe:1",
            ],
            capture_output=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        raise RuntimeError("ffmpeg is required for automatic music detection.") from exc

    if not result.stdout:
        return np.array([], dtype=np.float32), sample_rate

    samples = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    return samples, sample_rate


def _frame_signal(samples, frame_size: int, hop_size: int):
    np = _resolve_numpy()
    if samples.size < frame_size:
        padded = np.zeros(frame_size, dtype=np.float32)
        padded[: samples.size] = samples
        return padded.reshape(1, -1)

    frame_count = 1 + (samples.size - frame_size) // hop_size
    frames = np.empty((frame_count, frame_size), dtype=np.float32)
    for idx in range(frame_count):
        start = idx * hop_size
        frames[idx] = samples[start : start + frame_size]
    return frames


def _classify_music(samples, sample_rate: int) -> dict:
    np = _resolve_numpy()
    if samples.size == 0:
        return {
            "status": "no_audio",
            "confidence": 1.0,
            "has_audio": False,
            "music_score": 0.0,
            "speech_score": 0.0,
            "features": {},
            "method": "heuristic_v1",
            "analyzed_at": utc_now_iso(),
        }

    frame_size = 2048
    hop_size = 1024
    frames = _frame_signal(samples, frame_size, hop_size)
    window = np.hanning(frame_size).astype(np.float32)
    windowed = frames * window

    rms = np.sqrt(np.mean(windowed**2, axis=1) + 1e-12)
    rms_max = float(np.max(rms)) if rms.size else 0.0
    if rms_max < 0.002:
        return {
            "status": "no_audio",
            "confidence": 0.99,
            "has_audio": False,
            "music_score": 0.0,
            "speech_score": 0.0,
            "features": {
                "rms_max": rms_max,
            },
            "method": "heuristic_v1",
            "analyzed_at": utc_now_iso(),
        }

    norm_rms = rms / max(rms_max, 1e-6)
    silence_ratio = float(np.mean(norm_rms < 0.08))
    energy_cv = float(np.std(rms) / (np.mean(rms) + 1e-9))
    zcr = np.mean(np.abs(np.diff(np.signbit(frames), axis=1)), axis=1).astype(np.float32)
    zcr_median = float(np.median(zcr))

    spectrum = np.abs(np.fft.rfft(windowed, axis=1)) + 1e-9
    freqs = np.fft.rfftfreq(frame_size, d=1.0 / sample_rate)
    centroid = np.sum(spectrum * freqs, axis=1) / np.sum(spectrum, axis=1)
    centroid_median = float(np.median(centroid))
    flatness = np.exp(np.mean(np.log(spectrum), axis=1)) / np.mean(spectrum, axis=1)
    flatness_median = float(np.median(flatness))
    active_ratio = float(np.mean(norm_rms >= 0.08))

    music_score = 0.0
    speech_score = 0.0

    if silence_ratio < 0.12:
        music_score += 0.25
    elif silence_ratio < 0.22:
        music_score += 0.12
    else:
        speech_score += 0.20

    if centroid_median > 1250:
        music_score += 0.20
    elif centroid_median > 900:
        music_score += 0.10
    else:
        speech_score += 0.18

    if 0.04 <= flatness_median <= 0.28:
        music_score += 0.18
    elif flatness_median > 0.38:
        speech_score += 0.10
    else:
        music_score += 0.08

    if energy_cv < 0.70:
        music_score += 0.17
    elif energy_cv > 1.05:
        speech_score += 0.18
    else:
        music_score += 0.05
        speech_score += 0.05

    if 0.04 <= zcr_median <= 0.16:
        music_score += 0.10
    elif zcr_median < 0.035:
        speech_score += 0.08

    if active_ratio > 0.80:
        music_score += 0.10
    elif active_ratio < 0.55:
        speech_score += 0.10

    score_gap = music_score - speech_score
    if music_score >= 0.72 and score_gap >= 0.14:
        status = "unsafe"
    elif music_score >= 0.48:
        status = "needs_review"
    else:
        status = "safe"

    confidence = min(0.99, max(0.35, 0.5 + abs(score_gap) * 0.8))
    return {
        "status": status,
        "confidence": round(float(confidence), 3),
        "has_audio": True,
        "music_score": round(float(music_score), 3),
        "speech_score": round(float(speech_score), 3),
        "features": {
            "silence_ratio": round(silence_ratio, 3),
            "active_ratio": round(active_ratio, 3),
            "spectral_centroid_hz": round(centroid_median, 1),
            "spectral_flatness": round(flatness_median, 3),
            "energy_cv": round(energy_cv, 3),
            "zcr_median": round(zcr_median, 3),
        },
        "method": "heuristic_v1",
        "analyzed_at": utc_now_iso(),
    }


def _download_to_temp(candidate: dict, downloads_dir: Path) -> Path:
    target_path = downloads_dir / f"{candidate['id']:04d}_{slugify(candidate['title'])}.mp4"
    if candidate["source_type"] == "reddit":
        metadata = candidate.get("metadata") or {}
        download_reddit_media(
            media_url=candidate["media_url"],
            destination=target_path,
            dash_url=metadata.get("dash_url"),
        )
    else:
        download_media(candidate["media_url"], target_path)
    return target_path


def _candidate_rows(
    *,
    db_path: Path,
    candidate_id: int | None,
    source_type: str | None,
    rights_status: str | None,
    limit: int,
) -> list[dict]:
    with connect(db_path) as conn:
        if candidate_id is not None:
            row = get_candidate(conn, candidate_id)
            return [dict(row)] if row else []

        rows = fetch_candidates(
            conn,
            limit=limit,
            source_type=source_type,
            rights_status=rights_status,
        )
        return [dict(row) for row in rows]


def scan_candidates_for_music(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    candidate_id: int | None = None,
    source_type: str | None = None,
    rights_status: str | None = None,
    limit: int = 20,
    allow_remote_media: bool = False,
) -> dict:
    rows = _candidate_rows(
        db_path=db_path,
        candidate_id=candidate_id,
        source_type=source_type,
        rights_status=rights_status,
        limit=limit,
    )

    ensure_directory(db_path.parent)
    downloads_dir: Path | None = None
    scanned = 0
    skipped = 0
    results: list[dict] = []

    try:
        with connect(db_path) as conn:
            for row in rows:
                metadata = {}
                if row.get("metadata_json"):
                    try:
                        metadata = json.loads(row["metadata_json"])
                    except json.JSONDecodeError:
                        metadata = {}
                row["metadata"] = metadata

                input_path: Path | None = None
                cleanup_path: Path | None = None
                try:
                    if row.get("local_media_path"):
                        input_path = Path(row["local_media_path"])
                    elif allow_remote_media and downloadable_media_url(row["source_type"], row.get("media_url")):
                        if downloads_dir is None:
                            downloads_dir = create_temp_download_dir(db_path.parent / "music_scan_tmp")
                        input_path = _download_to_temp(row, downloads_dir)
                        cleanup_path = input_path
                    else:
                        skipped += 1
                        results.append(
                            {
                                "candidate_id": row["id"],
                                "status": "skipped",
                                "reason": "No local file and remote scanning disabled or unavailable.",
                            }
                        )
                        continue

                    has_audio = _ffprobe_has_audio(input_path)
                    if not has_audio:
                        detection = {
                            "status": "no_audio",
                            "confidence": 1.0,
                            "has_audio": False,
                            "music_score": 0.0,
                            "speech_score": 0.0,
                            "features": {},
                            "method": "heuristic_v1",
                            "analyzed_at": utc_now_iso(),
                        }
                    else:
                        samples, sample_rate = _extract_audio_samples(input_path)
                        detection = _classify_music(samples, sample_rate)

                    update_candidate_music_detection(
                        conn,
                        candidate_id=row["id"],
                        detection=detection,
                    )
                    scanned += 1
                    results.append(
                        {
                            "candidate_id": row["id"],
                            "status": detection["status"],
                            "confidence": detection["confidence"],
                        }
                    )
                except Exception as exc:
                    detection = {
                        "status": "scan_failed",
                        "confidence": 0.0,
                        "has_audio": None,
                        "music_score": 0.0,
                        "speech_score": 0.0,
                        "features": {},
                        "method": "heuristic_v1",
                        "analyzed_at": utc_now_iso(),
                        "error": str(exc),
                    }
                    update_candidate_music_detection(
                        conn,
                        candidate_id=row["id"],
                        detection=detection,
                    )
                    results.append(
                        {
                            "candidate_id": row["id"],
                            "status": "scan_failed",
                            "reason": str(exc),
                        }
                    )
                finally:
                    if cleanup_path and cleanup_path.exists():
                        cleanup_path.unlink(missing_ok=True)

            conn.commit()
    finally:
        cleanup_temp_dir(downloads_dir)

    return {
        "scanned": scanned,
        "skipped": skipped,
        "results": results,
    }
