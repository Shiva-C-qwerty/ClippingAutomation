from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from clipping_automation.config import DEFAULT_CONFIG_PATH, DEFAULT_EXPORT_DIR, env_value
from clipping_automation.services.scoring import compute_score
from clipping_automation.utils import days_ago_iso, ensure_directory, parse_iso8601_duration, slugify, utc_now_iso

REDDIT_BASE_URL = "https://www.reddit.com"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prototype: discover clip candidates from a free-text query instead of fixed subreddit feeds."
    )
    parser.add_argument("query", help="Topic or keyword to search for, such as 'IShowSpeed' or 'USA vs Iran'.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--reddit-limit", type=int, default=10)
    parser.add_argument("--youtube-limit", type=int, default=8)
    parser.add_argument("--published-after-days", type=int, default=30)
    parser.add_argument(
        "--reddit-subreddits",
        nargs="*",
        help="Optional subreddit shortlist to constrain Reddit search, e.g. funny ContagiousLaughter.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output JSON path. Defaults to data/exports/query-<slug>.prototype.json",
    )
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        import tomllib
    except ModuleNotFoundError as exc:
        raise RuntimeError("Python 3.11+ is required because this prototype uses tomllib.") from exc
    return tomllib.loads(config_path.read_text(encoding="utf-8"))


def build_scoring_config(base_config: dict, query: str) -> dict:
    scoring = dict(base_config.get("scoring", {}))
    keywords = list(scoring.get("keywords", []))
    keywords.extend(part.strip() for part in query.split() if part.strip())
    scoring["keywords"] = list(dict.fromkeys(keywords))
    return scoring


def looks_like_video(post: dict) -> bool:
    if post.get("is_video"):
        return True
    if post.get("post_hint") in {"hosted:video", "rich:video"}:
        return True
    media = post.get("secure_media") or post.get("media") or {}
    if media.get("reddit_video"):
        return True
    url = (post.get("url_overridden_by_dest") or post.get("url") or "").lower()
    return any(domain in url for domain in ("v.redd.it", "youtube.com", "youtu.be", "redgifs.com"))


def normalize_reddit_post(post: dict, *, query: str, scoring_config: dict) -> dict | None:
    if not looks_like_video(post):
        return None

    reddit_video = (
        (post.get("secure_media") or {}).get("reddit_video")
        or (post.get("media") or {}).get("reddit_video")
        or {}
    )
    media_url = reddit_video.get("fallback_url") or post.get("url_overridden_by_dest") or post.get("url")
    dash_url = reddit_video.get("dash_url")
    duration_seconds = reddit_video.get("duration")
    created_at = None
    if post.get("created_utc"):
        from datetime import UTC, datetime

        created_at = datetime.fromtimestamp(post["created_utc"], tz=UTC).isoformat()

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
        license_hint="Manual permission required from original creator",
        scoring_config=scoring_config,
    )

    permalink = post.get("permalink") or ""
    source_url = f"{REDDIT_BASE_URL}{permalink}" if permalink.startswith("/") else permalink
    subreddit = post.get("subreddit")
    return {
        "source_type": "reddit",
        "external_id": post["id"],
        "source_context": subreddit,
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
        "license_hint": "Manual permission required from original creator",
        "metadata": {
            "query": query,
            "source_label": f"r/{subreddit}" if subreddit else None,
            "subreddit": subreddit,
            "dash_url": dash_url,
            "search_mode": "keyword",
        },
    }


def discover_reddit_by_query(
    *,
    query: str,
    limit: int,
    user_agent: str,
    scoring_config: dict,
    subreddits: list[str] | None = None,
) -> list[dict]:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent})
    params = {
        "q": query,
        "sort": "relevance",
        "limit": limit,
        "type": "link",
        "restrict_sr": "on" if subreddits else "off",
        "raw_json": 1,
    }

    if subreddits:
        joined = "+".join(subreddits)
        url = f"{REDDIT_BASE_URL}/r/{joined}/search.json"
    else:
        url = f"{REDDIT_BASE_URL}/search.json"

    response = session.get(url, params=params, timeout=20)
    response.raise_for_status()
    payload = response.json()

    results: list[dict] = []
    for child in payload.get("data", {}).get("children", []):
        normalized = normalize_reddit_post(child.get("data", {}), query=query, scoring_config=scoring_config)
        if normalized:
            results.append(normalized)
    return results


def youtube_video_lookup(api_key: str, video_ids: list[str]) -> dict[str, dict]:
    if not video_ids:
        return {}
    response = requests.get(
        YOUTUBE_VIDEOS_URL,
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


def discover_youtube_by_query(
    *,
    query: str,
    limit: int,
    published_after_days: int,
    scoring_config: dict,
    api_key: str | None,
) -> list[dict]:
    if not api_key:
        return []

    response = requests.get(
        YOUTUBE_SEARCH_URL,
        params={
            "part": "snippet",
            "type": "video",
            "maxResults": limit,
            "q": query,
            "order": "relevance",
            "publishedAfter": days_ago_iso(published_after_days),
            "key": api_key,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    ids = [item["id"]["videoId"] for item in payload.get("items", []) if item.get("id", {}).get("videoId")]
    details_by_id = youtube_video_lookup(api_key, ids)

    results: list[dict] = []
    for item in payload.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if not video_id or video_id not in details_by_id:
            continue

        details = details_by_id[video_id]
        snippet = details.get("snippet", {})
        statistics = details.get("statistics", {})
        content_details = details.get("contentDetails", {})
        duration_seconds = parse_iso8601_duration(content_details.get("duration"))

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
            license_hint="Review license manually",
            scoring_config=scoring_config,
        )

        results.append(
            {
                "source_type": "youtube",
                "external_id": video_id,
                "source_context": query,
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
                "license_hint": "Review license manually",
                "metadata": {
                    "query": query,
                    "channel_id": snippet.get("channelId"),
                    "thumbnails": snippet.get("thumbnails", {}),
                    "duration": content_details.get("duration"),
                    "search_mode": "keyword",
                    "source_label": snippet.get("channelTitle"),
                },
            }
        )
    return results


def print_summary(candidates: list[dict]) -> None:
    if not candidates:
        print("No candidates found.")
        return

    header = f"{'SRC':<8} {'SCORE':<8} {'DUR':<6} {'FROM':<24} TITLE"
    print(header)
    print("-" * len(header))
    for candidate in candidates:
        duration = candidate.get("duration_seconds") or "-"
        metadata = candidate.get("metadata") or {}
        source_label = metadata.get("source_label") or candidate.get("source_context") or "-"
        print(
            f"{candidate['source_type']:<8} "
            f"{candidate['score']:<8.2f} "
            f"{str(duration):<6} "
            f"{source_label[:24]:<24} "
            f"{candidate['title'][:80]}"
        )


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    scoring_config = build_scoring_config(config, args.query)
    reddit_user_agent = config.get("reddit", {}).get("user_agent", "ClippingAutomation/0.1 by query-prototype")
    youtube_api_env = config.get("youtube", {}).get("api_key_env", "YOUTUBE_API_KEY")
    youtube_api_key = env_value(youtube_api_env)

    errors: list[str] = []
    reddit_candidates: list[dict] = []
    youtube_candidates: list[dict] = []

    try:
        reddit_candidates = discover_reddit_by_query(
            query=args.query,
            limit=args.reddit_limit,
            user_agent=reddit_user_agent,
            scoring_config=scoring_config,
            subreddits=args.reddit_subreddits,
        )
    except Exception as exc:
        errors.append(f"Reddit query failed: {exc}")

    try:
        youtube_candidates = discover_youtube_by_query(
            query=args.query,
            limit=args.youtube_limit,
            published_after_days=args.published_after_days,
            scoring_config=scoring_config,
            api_key=youtube_api_key,
        )
    except Exception as exc:
        errors.append(f"YouTube query failed: {exc}")

    combined = sorted([*reddit_candidates, *youtube_candidates], key=lambda item: item["score"], reverse=True)
    output_path = args.output or (DEFAULT_EXPORT_DIR / f"query-{slugify(args.query)}.prototype.json")
    ensure_directory(output_path.parent)
    payload = {
        "query": args.query,
        "generated_at": utc_now_iso(),
        "counts": {
            "reddit": len(reddit_candidates),
            "youtube": len(youtube_candidates),
            "total": len(combined),
        },
        "errors": errors,
        "candidates": combined,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Query: {args.query}")
    print(f"Reddit candidates: {len(reddit_candidates)}")
    print(f"YouTube candidates: {len(youtube_candidates)}")
    print(f"Output: {output_path}")
    if errors:
        print("Warnings:")
        for error in errors:
            print(f"- {error}")
    print_summary(combined[: min(len(combined), 12)])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
