from __future__ import annotations

import threading
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from threading import Thread, Timer

import uvicorn
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from clipping_automation.config import (
    APPROVED_ASSETS_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_DB_PATH,
    DEFAULT_EXPORT_DIR,
    bootstrap_workspace,
)
from clipping_automation.db import (
    connect,
    delete_candidates_by_status,
    fetch_candidates,
    get_candidate,
    initialize_database,
)
from clipping_automation.services.approval import approve_candidate
from clipping_automation.services.archive import archive_candidates_from_plan
from clipping_automation.services.discovery import run_discovery
from clipping_automation.services.music_detection import scan_candidates_for_music
from clipping_automation.services.music_review import review_candidate_music
from clipping_automation.services.render_plan import SHORTS_MAX_SECONDS, create_compilation_plan, run_render
from clipping_automation.web_shared import candidate_view_model
from clipping_automation.web_plans import (
    list_plan_paths,
    plan_view_model,
    resolve_plan_path,
    update_plan_audio_beds,
)


APP_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"

app = FastAPI(title="Clipbot Local Review UI", version="0.1.0")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_render_jobs: dict[str, dict] = {}
_render_jobs_lock = threading.Lock()


def _prepare_workspace() -> None:
    paths = bootstrap_workspace()
    initialize_database(paths["db_path"])


@app.on_event("startup")
def startup_event() -> None:
    _prepare_workspace()


def _fetch_view_models(
    *,
    status: str | None = None,
    source: str | None = None,
    music_status: str | None = None,
    local_only: bool = False,
    limit: int = 100,
) -> list[dict]:
    with connect(DEFAULT_DB_PATH) as conn:
        rows = [
            candidate_view_model(dict(row))
            for row in fetch_candidates(
                conn,
                limit=limit,
                source_type=source,
                rights_status=status,
                local_only=local_only,
            )
        ]
    if music_status:
        rows = [row for row in rows if row["music_status"] == music_status]
    return rows


def _fetch_candidate(candidate_id: int) -> dict:
    with connect(DEFAULT_DB_PATH) as conn:
        row = get_candidate(conn, candidate_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Candidate {candidate_id} not found.")
    return candidate_view_model(dict(row))


def _redirect(target: str) -> RedirectResponse:
    return RedirectResponse(url=target, status_code=303)


def _extra_video_options() -> list[str]:
    extras_dir = DEFAULT_EXPORT_DIR / "Extras"
    if not extras_dir.exists():
        return []
    return sorted(
        str(path)
        for path in extras_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
    )


def _plan_status(plan_item: dict) -> dict:
    filename = plan_item["filename"]
    with _render_jobs_lock:
        job = dict(_render_jobs.get(filename, {}))

    if job.get("state") == "running":
        return {
            "state": "running",
            "label": "running",
            "started_at": job.get("started_at"),
            "finished_at": None,
            "last_error": "",
        }
    if job.get("state") == "failed":
        return {
            "state": "failed",
            "label": "failed",
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "last_error": job.get("last_error") or "",
        }
    if job.get("state") == "completed" or plan_item["output_exists"]:
        return {
            "state": "completed",
            "label": "rendered",
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "last_error": "",
        }
    return {
        "state": "idle",
        "label": "idle",
        "started_at": None,
        "finished_at": None,
        "last_error": "",
    }


def _plan_item(plan_path: Path) -> dict:
    item = plan_view_model(plan_path)
    item["render_status"] = _plan_status(item)
    return item


def _render_plan_background(plan_path: Path) -> None:
    filename = plan_path.name
    try:
        run_render(plan_path=plan_path, execute=True)
    except Exception as exc:  # noqa: BLE001
        with _render_jobs_lock:
            _render_jobs[filename] = {
                "state": "failed",
                "started_at": _render_jobs.get(filename, {}).get("started_at"),
                "finished_at": datetime.now(UTC).isoformat(),
                "output_path": "",
                "last_error": str(exc),
            }
    else:
        output_path = _plan_item(plan_path)["output_video_path"]
        with _render_jobs_lock:
            _render_jobs[filename] = {
                "state": "completed",
                "started_at": _render_jobs.get(filename, {}).get("started_at"),
                "finished_at": datetime.now(UTC).isoformat(),
                "output_path": output_path,
                "last_error": "",
            }


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    review_count = len(_fetch_view_models(status="needs_review", limit=200))
    approved = _fetch_view_models(status="approved", limit=200)
    plans = [_plan_item(path) for path in list_plan_paths()]
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "request": request,
            "review_count": review_count,
            "approved_count": len(approved),
            "ready_count": len([row for row in approved if row["usable_for_planning"]]),
            "plan_count": len(plans),
        },
    )


@app.get("/review", response_class=HTMLResponse)
def review_page(
    request: Request,
    music_status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    scan_message: str | None = Query(default=None),
) -> HTMLResponse:
    candidates = _fetch_view_models(
        status="needs_review",
        source=source,
        music_status=music_status,
        limit=200,
    )
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={
            "request": request,
            "candidates": candidates,
            "music_status": music_status or "",
            "source": source or "",
            "scan_message": scan_message or "",
        },
    )


@app.get("/approved", response_class=HTMLResponse)
def approved_page(
    request: Request,
    music_status: str | None = Query(default=None),
    ready_only: bool = Query(default=False),
    created_plan: str | None = Query(default=None),
    plan_error: str | None = Query(default=None),
) -> HTMLResponse:
    candidates = _fetch_view_models(
        status="approved",
        music_status=music_status,
        limit=200,
    )
    if ready_only:
        candidates = [row for row in candidates if row["usable_for_planning"]]
    return templates.TemplateResponse(
        request=request,
        name="approved.html",
        context={
            "request": request,
            "candidates": candidates,
            "music_status": music_status or "",
            "ready_only": ready_only,
            "created_plan": created_plan or "",
            "plan_error": plan_error or "",
            "extra_video_options": _extra_video_options(),
            "web_max_clip_duration": SHORTS_MAX_SECONDS,
        },
    )


@app.get("/plans", response_class=HTMLResponse)
def plans_page(
    request: Request,
    action_message: str | None = Query(default=None),
) -> HTMLResponse:
    plans = [_plan_item(path) for path in list_plan_paths()]
    return templates.TemplateResponse(
        request=request,
        name="plans.html",
        context={
            "request": request,
            "plans": plans,
            "action_message": action_message or "",
        },
    )


@app.get("/plans/{plan_filename}", response_class=HTMLResponse)
def plan_detail_page(
    request: Request,
    plan_filename: str,
    action_message: str | None = Query(default=None),
) -> HTMLResponse:
    try:
        plan_path = resolve_plan_path(plan_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan = _plan_item(plan_path)
    return templates.TemplateResponse(
        request=request,
        name="plan_detail.html",
        context={
            "request": request,
            "plan": plan,
            "action_message": action_message or "",
        },
    )


@app.get("/candidate/{candidate_id}", response_class=HTMLResponse)
def candidate_page(request: Request, candidate_id: int) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="candidate.html",
        context={
            "request": request,
            "candidate": _fetch_candidate(candidate_id),
        },
    )


@app.post("/actions/discover")
def discover_action(next_url: str = Form(default="/review")) -> RedirectResponse:
    _prepare_workspace()
    run_discovery(config_path=DEFAULT_CONFIG_PATH, db_path=DEFAULT_DB_PATH)
    return _redirect(next_url)


@app.post("/actions/scan-music")
def scan_music_action(
    next_url: str = Form(default="/review"),
    status: str = Form(default="needs_review"),
    limit: int = Form(default=50),
    download_remote: bool = Form(default=True),
) -> RedirectResponse:
    _prepare_workspace()
    summary = scan_candidates_for_music(
        db_path=DEFAULT_DB_PATH,
        rights_status=status,
        limit=limit,
        allow_remote_media=download_remote,
    )
    message = (
        f"Music scan complete: scanned {summary['scanned']}, "
        f"skipped {summary['skipped']}"
    )
    separator = "&" if "?" in next_url else "?"
    return _redirect(f"{next_url}{separator}scan_message={message}")


@app.post("/actions/flush")
def flush_action(
    status: str = Form(default="needs_review"),
    next_url: str = Form(default="/review"),
) -> RedirectResponse:
    _prepare_workspace()
    with connect(DEFAULT_DB_PATH) as conn:
        delete_candidates_by_status(conn, rights_status=status)
        conn.commit()
    return _redirect(next_url)


@app.post("/actions/candidates/{candidate_id}/review")
def review_action(
    candidate_id: int,
    rights_status: str = Form(...),
    notes: str | None = Form(default=None),
    clip_title: str | None = Form(default=None),
    music_status_override: str | None = Form(default=None),
    next_url: str = Form(default="/review"),
) -> RedirectResponse:
    _prepare_workspace()
    if music_status_override:
        review_candidate_music(
            candidate_id=candidate_id,
            music_status=music_status_override,
            music_notes=notes,
            db_path=DEFAULT_DB_PATH,
        )
    approve_candidate(
        candidate_id=candidate_id,
        rights_status=rights_status,
        rights_notes=notes,
        local_file=None,
        clip_title=clip_title,
        db_path=DEFAULT_DB_PATH,
    )
    return _redirect(next_url)


@app.post("/actions/plan")
def plan_action(
    style: str = Form(default="top5"),
    count: int = Form(default=5),
    name: str | None = Form(default=None),
    intro_path: str | None = Form(default=None),
    outro_path: str | None = Form(default=None),
    download_approved: bool = Form(default=False),
) -> RedirectResponse:
    _prepare_workspace()
    try:
        plan = create_compilation_plan(
            db_path=DEFAULT_DB_PATH,
            style=style,
            count=count,
            name=name,
            max_clip_duration=SHORTS_MAX_SECONDS,
            intro_path=Path(intro_path).expanduser() if intro_path else None,
            outro_path=Path(outro_path).expanduser() if outro_path else None,
            allow_remote_media=download_approved,
        )
    except Exception as exc:  # noqa: BLE001
        return _redirect(f"/approved?plan_error={str(exc)}")
    plan_filename = Path(plan["render"]["plan_path"]).name
    return _redirect(f"/plans/{plan_filename}?action_message=Plan created")


@app.post("/actions/plans/{plan_filename}/render")
def plan_render_action(plan_filename: str) -> RedirectResponse:
    _prepare_workspace()
    try:
        plan_path = resolve_plan_path(plan_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with _render_jobs_lock:
        job = _render_jobs.get(plan_filename)
        if job and job.get("state") == "running":
            return _redirect(f"/plans/{plan_filename}?action_message=Render already running")
        _render_jobs[plan_filename] = {
            "state": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "output_path": "",
            "last_error": "",
        }

    Thread(target=_render_plan_background, args=(plan_path,), daemon=True).start()
    return _redirect(f"/plans/{plan_filename}?action_message=Render started")


@app.post("/actions/plans/{plan_filename}/audio-beds")
async def plan_audio_beds_action(plan_filename: str, request: Request) -> RedirectResponse:
    _prepare_workspace()
    try:
        plan_path = resolve_plan_path(plan_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    form = await request.form()
    plan = _plan_item(plan_path)
    selections: dict[int, str | None] = {}
    for clip in plan["clips"]:
        if not clip.get("is_no_audio"):
            continue
        candidate_id = int(clip["candidate_id"])
        selections[candidate_id] = (form.get(f"audio_bed_{candidate_id}") or "").strip() or None

    result = update_plan_audio_beds(plan_path, selections)
    return _redirect(
        f"/plans/{plan_filename}?action_message=Saved audio bed selections for {result['updated']} clip(s)"
    )


@app.post("/actions/plans/{plan_filename}/archive")
def plan_archive_action(plan_filename: str) -> RedirectResponse:
    _prepare_workspace()
    try:
        plan_path = resolve_plan_path(plan_filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    plan = _plan_item(plan_path)
    if not plan["output_exists"]:
        return _redirect(f"/plans/{plan_filename}?action_message=Archive blocked: render output not found")

    result = archive_candidates_from_plan(
        plan_path=plan_path,
        db_path=DEFAULT_DB_PATH,
        note=plan["name"],
    )
    return _redirect(
        f"/plans/{plan_filename}?action_message=Archived {result['archived_count']} clip(s) from this plan"
    )


@app.post("/actions/candidates/{candidate_id}/music-review")
def music_review_action(
    candidate_id: int,
    music_status: str = Form(...),
    notes: str | None = Form(default=None),
    next_url: str = Form(default="/review"),
) -> RedirectResponse:
    _prepare_workspace()
    review_candidate_music(
        candidate_id=candidate_id,
        music_status=music_status,
        music_notes=notes,
        db_path=DEFAULT_DB_PATH,
    )
    return _redirect(next_url)


@app.get("/api/health")
def api_health() -> dict:
    return {"status": "ok"}


@app.post("/api/discover")
def api_discover() -> dict:
    _prepare_workspace()
    summary = run_discovery(config_path=DEFAULT_CONFIG_PATH, db_path=DEFAULT_DB_PATH)
    return {
        "ok": True,
        "summary": {
            "total_discovered": summary["total_discovered"],
            "reddit_discovered": summary["reddit_discovered"],
            "youtube_discovered": summary["youtube_discovered"],
            "snapshot_path": str(summary["snapshot_path"]),
            "errors": summary["errors"],
        },
    }


@app.get("/api/candidates")
def api_candidates(
    status: str | None = Query(default=None),
    source: str | None = Query(default=None),
    music_status: str | None = Query(default=None),
    local_only: bool = Query(default=False),
    ready_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    candidates = _fetch_view_models(
        status=status,
        source=source,
        music_status=music_status,
        local_only=local_only,
        limit=limit,
    )
    if ready_only:
        candidates = [row for row in candidates if row["usable_for_planning"]]
    return {"items": candidates, "count": len(candidates)}


@app.get("/api/candidates/{candidate_id}")
def api_candidate_detail(candidate_id: int) -> dict:
    return {"item": _fetch_candidate(candidate_id)}


@app.post("/api/candidates/{candidate_id}/review")
def api_candidate_review(
    candidate_id: int,
    rights_status: str = Form(...),
    notes: str | None = Form(default=None),
    clip_title: str | None = Form(default=None),
) -> dict:
    _prepare_workspace()
    result = approve_candidate(
        candidate_id=candidate_id,
        rights_status=rights_status,
        rights_notes=notes,
        local_file=None,
        clip_title=clip_title,
        db_path=DEFAULT_DB_PATH,
    )
    return {"ok": True, "result": result}


@app.post("/api/candidates/{candidate_id}/music-review")
def api_candidate_music_review(
    candidate_id: int,
    music_status: str = Form(...),
    notes: str | None = Form(default=None),
) -> dict:
    _prepare_workspace()
    result = review_candidate_music(
        candidate_id=candidate_id,
        music_status=music_status,
        music_notes=notes,
        db_path=DEFAULT_DB_PATH,
    )
    return {"ok": True, "result": result}


@app.post("/api/flush")
def api_flush(status: str = Form(default="needs_review")) -> dict:
    _prepare_workspace()
    with connect(DEFAULT_DB_PATH) as conn:
        deleted = delete_candidates_by_status(conn, rights_status=status)
        conn.commit()
    return {"ok": True, "deleted": deleted}


@app.get("/media/approved/{filename}")
def approved_media(filename: str) -> FileResponse:
    path = (APPROVED_ASSETS_DIR / filename).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found.")
    if not path.is_relative_to(APPROVED_ASSETS_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden path.")
    return FileResponse(path)


@app.get("/exports/{filename}")
def export_file(filename: str) -> FileResponse:
    path = (DEFAULT_EXPORT_DIR / filename).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Export file not found.")
    if not path.is_relative_to(DEFAULT_EXPORT_DIR.resolve()):
        raise HTTPException(status_code=403, detail="Forbidden path.")
    return FileResponse(path)


def main() -> None:
    url = "http://127.0.0.1:8000"
    Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run("clipping_automation.web:app", host="127.0.0.1", port=8000, reload=False)


__all__ = ["app", "main"]
