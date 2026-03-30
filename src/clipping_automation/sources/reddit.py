from __future__ import annotations

from datetime import UTC, datetime

import requests

from clipping_automation.services.scoring import compute_score
from clipping_automation.utils import utc_now_iso

BASE_URL = "https://www.reddit.com"


def _looks_like_video(post: dict) -> bool:
    if post.get("is_video"):
        return True
    if post.get("post_hint") in {"hosted:video", "rich:video"}:
        return True
    media = post.get("secure_media") or post.get("media") or {}
    if media.get("reddit_video"):
        return True
    url = (post.get("url_overridden_by_dest") or post.get("url") or "").lower()
    return any(domain in url for domain in ("v.redd.it", "youtube.com", "youtu.be", "redgifs.com"))


def _normalize_post(post: dict, *, scoring_config: dict | None) -> dict | None:
    if not _looks_like_video(post):
        return None

    created_utc = post.get("created_utc")
    created_at = None
    if created_utc:
        created_at = datetime.fromtimestamp(created_utc, tz=UTC).isoformat()

    reddit_video = (
        (post.get("secure_media") or {}).get("reddit_video")
        or (post.get("media") or {}).get("reddit_video")
        or {}
    )
    media_url = reddit_video.get("fallback_url") or post.get("url_overridden_by_dest") or post.get("url")
    dash_url = reddit_video.get("dash_url")
    duration_seconds = reddit_video.get("duration")
    license_hint = "Manual permission required from original creator"

    score, breakdown = compute_score(
        source_type="reddit",
        title=post.get("title", ""),
        description=post.get("selftext", ""),
        created_at=created_at,
        duration_seconds=duration_seconds,
        aspect_ratio=None,
        views=post.get("view_count"),
        upvotes=post.get("score"),
        comments=post.get("num_comments"),
        license_hint=license_hint,
        scoring_config=scoring_config,
    )

    permalink = post.get("permalink") or ""
    source_url = f"{BASE_URL}{permalink}" if permalink.startswith("/") else permalink

    return {
        "source_type": "reddit",
        "external_id": post["id"],
        "source_context": post.get("subreddit"),
        "title": post.get("title") or "Untitled Reddit post",
        "description": post.get("selftext") or "",
        "author": post.get("author"),
        "source_url": source_url,
        "media_url": media_url,
        "permalink": source_url,
        "created_at": created_at,
        "discovered_at": utc_now_iso(),
        "duration_seconds": duration_seconds,
        "aspect_ratio": None,
        "views": post.get("view_count"),
        "upvotes": post.get("score"),
        "comments": post.get("num_comments"),
        "score": score,
        "score_breakdown": breakdown,
        "license_hint": license_hint,
        "metadata": {
            "over_18": post.get("over_18"),
            "upvote_ratio": post.get("upvote_ratio"),
            "domain": post.get("domain"),
            "is_video": post.get("is_video"),
            "subreddit": post.get("subreddit"),
            "url": post.get("url"),
            "dash_url": dash_url,
        },
    }


def discover_reddit_candidates(config: dict, scoring_config: dict | None = None) -> list[dict]:
    reddit_config = config.get("reddit", {})
    if not reddit_config.get("enabled", True):
        return []

    feeds = reddit_config.get("feeds", [])
    if not feeds:
        return []

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": reddit_config.get(
                "user_agent",
                "ClippingAutomation/0.1 by local-workflow",
            )
        }
    )

    limit = int(reddit_config.get("limit_per_feed", 15))
    all_candidates: list[dict] = []

    for feed in feeds:
        subreddit = feed["subreddit"]
        sort = feed.get("sort", "top")
        params = {"limit": limit, "raw_json": 1}
        if sort in {"top", "controversial"} and feed.get("time"):
            params["t"] = feed["time"]

        response = session.get(
            f"{BASE_URL}/r/{subreddit}/{sort}.json",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()

        for child in payload.get("data", {}).get("children", []):
            post = child.get("data", {})
            normalized = _normalize_post(post, scoring_config=scoring_config)
            if normalized:
                all_candidates.append(normalized)

    return all_candidates
