from __future__ import annotations

from typing import Any

import requests

from clipping_automation.config import env_value
from clipping_automation.services.scoring import compute_score
from clipping_automation.utils import days_ago_iso, parse_iso8601_duration, utc_now_iso

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def _video_lookup(api_key: str, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    response = requests.get(
        VIDEOS_URL,
        params={
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids),
            "key": api_key,
            "maxResults": len(video_ids),
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    return {item["id"]: item for item in payload.get("items", [])}


def discover_youtube_candidates(config: dict, scoring_config: dict | None = None) -> list[dict]:
    youtube_config = config.get("youtube", {})
    if not youtube_config.get("enabled", True):
        return []

    api_key_name = youtube_config.get("api_key_env", "YOUTUBE_API_KEY")
    api_key = env_value(api_key_name)
    if not api_key:
        return []

    searches = youtube_config.get("searches", [])
    if not searches:
        return []

    creative_commons_only = bool(youtube_config.get("creative_commons_only", True))
    max_results = int(youtube_config.get("max_results_per_query", 10))
    order = youtube_config.get("order", "relevance")
    all_candidates: list[dict] = []

    for search in searches:
        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": max_results,
            "q": search["query"],
            "order": order,
            "key": api_key,
        }
        if creative_commons_only:
            params["videoLicense"] = "creativeCommon"

        published_after_days = search.get("published_after_days")
        if published_after_days:
            params["publishedAfter"] = days_ago_iso(int(published_after_days))

        response = requests.get(SEARCH_URL, params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()

        ids = [item["id"]["videoId"] for item in payload.get("items", []) if item.get("id", {}).get("videoId")]
        details_by_id = _video_lookup(api_key, ids)

        for item in payload.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id or video_id not in details_by_id:
                continue

            details = details_by_id[video_id]
            snippet = details.get("snippet", {})
            statistics = details.get("statistics", {})
            content_details = details.get("contentDetails", {})
            duration_seconds = parse_iso8601_duration(content_details.get("duration"))
            license_hint = "Creative Commons via YouTube search filter" if creative_commons_only else "Review license manually"

            score, breakdown = compute_score(
                source_type="youtube",
                title=snippet.get("title", ""),
                description=snippet.get("description", ""),
                created_at=snippet.get("publishedAt"),
                duration_seconds=duration_seconds,
                aspect_ratio=None,
                views=int(statistics.get("viewCount", 0) or 0),
                upvotes=None,
                comments=int(statistics.get("commentCount", 0) or 0),
                license_hint=license_hint,
                scoring_config=scoring_config,
            )

            all_candidates.append(
                {
                    "source_type": "youtube",
                    "external_id": video_id,
                    "source_context": search["query"],
                    "title": snippet.get("title") or "Untitled YouTube video",
                    "description": snippet.get("description") or "",
                    "author": snippet.get("channelTitle"),
                    "source_url": f"https://www.youtube.com/watch?v={video_id}",
                    "media_url": None,
                    "permalink": f"https://www.youtube.com/watch?v={video_id}",
                    "created_at": snippet.get("publishedAt"),
                    "discovered_at": utc_now_iso(),
                    "duration_seconds": duration_seconds,
                    "aspect_ratio": None,
                    "views": int(statistics.get("viewCount", 0) or 0),
                    "upvotes": None,
                    "comments": int(statistics.get("commentCount", 0) or 0),
                    "score": score,
                    "score_breakdown": breakdown,
                    "license_hint": license_hint,
                    "metadata": {
                        "channel_id": snippet.get("channelId"),
                        "thumbnails": snippet.get("thumbnails", {}),
                        "duration": content_details.get("duration"),
                        "definition": content_details.get("definition"),
                        "licensed_content": content_details.get("licensedContent"),
                        "query": search["query"],
                    },
                }
            )

    return all_candidates
