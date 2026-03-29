from __future__ import annotations

import json
from pathlib import Path

from clipping_automation.config import DEFAULT_YOUTUBE_TOKEN_PATH, env_value

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _youtube_service() -> object:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    client_secrets_file = env_value("YOUTUBE_CLIENT_SECRETS_FILE")
    if not client_secrets_file:
        raise ValueError("Set YOUTUBE_CLIENT_SECRETS_FILE before uploading.")

    token_path = Path(env_value("YOUTUBE_TOKEN_FILE", str(DEFAULT_YOUTUBE_TOKEN_PATH)) or DEFAULT_YOUTUBE_TOKEN_PATH)
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    elif not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("youtube", "v3", credentials=creds)


def _metadata_from_plan(plan_path: Path) -> tuple[dict, Path]:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    output_path = Path(plan["render"]["output_video_path"])
    return plan["youtube"], output_path


def upload_from_plan(plan_path: Path) -> dict:
    from googleapiclient.http import MediaFileUpload

    youtube_metadata, video_path = _metadata_from_plan(plan_path)
    if not video_path.exists():
        raise FileNotFoundError(
            f"Rendered video not found: {video_path}. Run `clipbot render --execute` first."
        )

    service = _youtube_service()
    body = {
        "snippet": {
            "title": youtube_metadata["title"],
            "description": youtube_metadata["description"],
            "tags": youtube_metadata.get("tags", []),
            "categoryId": youtube_metadata.get(
                "category_id",
                env_value("YOUTUBE_DEFAULT_CATEGORY_ID", "23"),
            ),
        },
        "status": {
            "privacyStatus": youtube_metadata.get("privacy_status", "private"),
            "selfDeclaredMadeForKids": bool(youtube_metadata.get("made_for_kids", False)),
        },
    }

    if youtube_metadata.get("publish_at"):
        body["status"]["publishAt"] = youtube_metadata["publish_at"]

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), resumable=True),
    )
    response = request.execute()

    return {
        "video_id": response["id"],
        "video_url": f"https://www.youtube.com/watch?v={response['id']}",
        "privacy_status": body["status"]["privacyStatus"],
    }
