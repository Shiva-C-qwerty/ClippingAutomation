# Clipping Automation MVP

This is a first version of a funny-clips workflow built for safety and repeatability:

1. Discover candidate clips from Reddit and YouTube metadata.
2. Score and store them in a local SQLite database.
3. Manually approve only clips you have the rights to reuse.
4. Attach local media files for approved clips.
5. Generate a compilation plan plus an FFmpeg render script.
6. Upload the finished file to YouTube with the Data API.

The current MVP intentionally does **not** auto-download clips from third-party platforms. That is where copyright and ToS risk spikes. Instead, it helps you track sources, approvals, local assets, and upload metadata in one place.

## What This Version Includes

- `Reddit` discovery from subreddit JSON feeds
- `YouTube` discovery from the official Data API
- Local `SQLite` storage
- Feed-level category tagging for Reddit candidates
- Heuristic scoring for funny/short/recent clips
- A rights review gate: `needs_review`, `approved`, `rejected`
- Local media attachment for clips you cleared manually
- Compilation planning for `top5` or regular `compilation`
- FFmpeg PowerShell script generation for a 1080x1920 Shorts export
- YouTube upload command using OAuth

## What You Need Installed

- Python 3.11+
- FFmpeg on your `PATH` if you want to render videos
- A YouTube Data API project with uploads enabled

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
clipbot init
```

That creates:

- `config/sources.toml`
- `data/state/clips.db`
- `data/assets/approved/`
- `data/exports/`

## Configure Discovery Sources

Edit `config/sources.toml` and add the subreddits / queries you actually want to mine.

The current sample config is focused on `animal` clips and tags these subreddits as `animal` automatically:

- `r/funnypets`
- `r/FunnyAnimals`
- `r/AnimalsBeingDerps`
- `r/animalsdoingstuff`

YouTube discovery needs an API key:

```powershell
$env:YOUTUBE_API_KEY = "your_key_here"
```

If you want uploads:

```powershell
$env:YOUTUBE_CLIENT_SECRETS_FILE = "C:\path\to\client_secret.json"
$env:YOUTUBE_TOKEN_FILE = "data/state\youtube_token.json"
```

## Typical Workflow

### 1. Discover candidates

```powershell
clipbot discover
```

### 2. Review candidates

```powershell
clipbot list --status needs_review --limit 20
```

`clipbot list` now includes:

- `CAT`: the discovered or configured category, such as `animal`
- `FROM`: the source subreddit, such as `r/funnypets`

### 3. Approve a clip and attach a local file

```powershell
clipbot approve --candidate 12 --notes "Creator approved reuse by email on 2026-03-29" --file "C:\clips\funny-cat.mp4"
```

### 4. Build a compilation plan

```powershell
clipbot plan --style top5 --count 5 --name funny-top-5
```

That writes:

- `data/exports/funny-top-5.plan.json`
- `data/exports/funny-top-5.render.ps1`

You can also include local intro/outro clips and let the renderer temporarily fetch approved direct-media clips:

```powershell
clipbot plan --style top5 --count 5 --name funny-top-5 --intro "C:\clips\intro.mp4" --outro "C:\clips\outro.mp4" --download-approved
```

The planner keeps the whole compilation within `180s`, including intro and outro.

### 5. Render with FFmpeg

```powershell
clipbot render --plan data/exports/funny-top-5.plan.json --execute
```

If FFmpeg is not installed, the generated PowerShell render script is still useful as a handoff.

When `--download-approved` is used, approved remote clips are downloaded into a temporary folder inside the build directory and deleted automatically after the render finishes.

### 6. Upload to YouTube

```powershell
clipbot upload --plan data/exports/funny-top-5.plan.json
```

The first upload opens the OAuth consent flow in your browser and stores a token file locally.

### 7. Archive clips after a finished compilation

```powershell
clipbot archive-plan --plan data/exports/funny-top-5.plan.json
```

That marks the clips from that plan as `archived` so future planning will not reuse them by default.

## Rights Workflow

This project is built around a simple rule:

- discover anything
- only render what you explicitly approved
- only upload what you have the rights to reuse

Recommended approval notes:

- source of permission
- date of permission
- attribution requirements
- revenue split / licensing notes if any

## Notes

- Reddit discovery is metadata-only and best used to surface clips for manual review.
- Reddit category tagging is currently driven by feed config and known subreddit mappings.
- YouTube discovery is metadata-only and can be filtered to Creative Commons via config.
- The generated FFmpeg script normalizes clips to `1080x1920`, `30fps`, and AAC audio.
- Auto-download during render is limited to direct media URLs for approved clips and does not support generic YouTube scraping.
- The uploader defaults to `private` unless the plan says otherwise.
- New or unaudited YouTube API projects may have private-only upload restrictions.
