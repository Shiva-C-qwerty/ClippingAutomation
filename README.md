# Clipping Automation MVP

This is a first version of a funny-clips workflow built for safety and repeatability:

1. Discover candidate clips from Reddit and YouTube metadata.
2. Score and store them in a local SQLite database.
3. Automatically scan clips for likely music presence.
4. Review clips for reuse rights and music risk before approval.
5. Manually approve only clips you have the rights to reuse and that are safe enough to compile.
6. Attach local media files for approved clips.
7. Generate a compilation plan plus an FFmpeg render script.
8. Export the finished file for manual upload.

The current MVP intentionally does **not** auto-download clips from third-party platforms in a generic way. That is where copyright and ToS risk spikes. Instead, it helps you track sources, approvals, local assets, music-review decisions, and export metadata in one place.

## What This Version Includes

- `Reddit` discovery from subreddit JSON feeds
- `YouTube` discovery from the official Data API
- Local `SQLite` storage
- Feed-level category tagging for Reddit candidates
- Heuristic scoring for funny/short/recent clips
- A rights review gate: `needs_review`, `approved`, `rejected`
- Automatic music-presence scanning for clips with usable media
- A music-risk review step before clips should be approved for compilation
- Local media attachment for clips you cleared manually
- Compilation planning for `top5` or regular `compilation`
- FFmpeg PowerShell script generation for a 1080x1920 Shorts export

## What You Need Installed

- Python 3.11+
- FFmpeg on your `PATH` if you want to render videos
- NumPy for automatic music detection

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

## Local Web Review Prototype

You can now run a local browser-based review UI on top of the same database and files:

```powershell
pip install -r requirements.txt
pip install -e .
clipbot-web
```

That starts a local FastAPI app on `http://127.0.0.1:8000` and opens it in your browser.

The local UI includes:

- `/` home dashboard
- `/review` review queue for `needs_review`
- `/approved` approved clips, including a ready-to-plan view
- `/candidate/<id>` full candidate detail page

The web prototype keeps using the same local storage:

- database: `data/state/clips.db`
- approved local media: `data/assets/approved`
- plans and rendered videos: `data/exports`

No cloud storage, auth, or remote deploy is included in this prototype.

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

- `MUSIC`: the effective music status, such as `safe`, `needs_review`, `unsafe`, `no_audio`, or `unknown`
- `CAT`: the discovered or configured category, such as `animal`
- `FROM`: the source subreddit, such as `r/funnypets`
- `LINK`: the source post/video URL shown under each row for direct review

You can also shortlist by music status:

```powershell
clipbot list --music-status unsafe
```

If you want to clear the review backlog and start fresh without losing approved or archived history:

```powershell
clipbot flush --status needs_review
```

### 3. Automatically scan clips for likely music

Run the automatic scan before approval:

```powershell
clipbot scan-music --status needs_review --limit 20 --download-remote
```

This writes a detection result into candidate metadata and surfaces it in `clipbot list`.

Automatic detection uses a heuristic audio classifier and can tag clips as:

- `safe`
- `needs_review`
- `unsafe`
- `no_audio`
- `scan_failed`

### 4. Review the clip for music risk

Before approval, check whether the clip contains obvious commercial or copyrighted music.

Recommended rule:

- approve clips with speech, natural sound, laughter, or clearly safe audio
- manually review clips with strong background music
- reject or hold clips with obvious copyrighted songs unless you are comfortable with that risk

If you want to override the automatic result after manual review:

```powershell
clipbot music-review --candidate 12 --status unsafe --notes "Obvious commercial song in the background"
```

### 5. Approve a clip and attach a local file

```powershell
clipbot approve --candidate 12 --clip-title "tiny duck swim" --notes "Creator approved reuse by email on 2026-03-29" --file "C:\clips\funny-cat.mp4"
```

Include permission notes and, if relevant, mention that the clip passed your music-risk check.

For `top5` renders, `--clip-title` is the short manual label shown next to the active rank in the final numbered video. If you omit it, the ranking overlay still renders, but that clip will only show the number.

### 6. Build a compilation plan

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

For `top5` compilations, the current playback order is `best-last`, so the highest-scoring selected clip is placed at the end as the payoff.

Clips tagged as `unsafe` or `needs_review` for music are excluded from planning by default unless you manually clear them.

For `top5` renders, the final export now includes a reference-style ranking overlay with:

- a fixed heading at the top
- a persistent left-side ranking stack
- the active clip title next to the current rank, using the `--clip-title` value saved at approval time

The default render framing now preserves the full original clip inside the `9:16` Shorts canvas and fills the extra space with a blurred background, instead of cropping the source frame to fill the canvas.

### 7. Render with FFmpeg

```powershell
clipbot render --plan data/exports/funny-top-5.plan.json --execute
```

If FFmpeg is not installed, the generated PowerShell render script is still useful as a handoff.

When `--download-approved` is used, approved remote clips are downloaded into a temporary folder inside the build directory and deleted automatically after the render finishes.

### 8. Upload manually after your final checks

The current practical scope ends at exporting the final video file. After render, review the export and upload it manually.

Suggested final check:

- confirm the final compilation does not contain risky background music before publishing

### 9. Archive clips after a finished compilation

```powershell
clipbot archive-plan --plan data/exports/funny-top-5.plan.json
```

That marks the clips from that plan as `archived` so future planning will not reuse them by default.

## Rights Workflow

This project is built around a simple rule:

- discover anything
- review rights and music risk
- only render what you explicitly approved
- only upload what you have the rights to reuse and are comfortable publishing

Recommended approval notes:

- source of permission
- date of permission
- attribution requirements
- revenue split / licensing notes if any
- whether the clip passed manual music review

## Notes

- Reddit discovery is metadata-only and best used to surface clips for manual review.
- Reddit category tagging is currently driven by feed config and known subreddit mappings.
- YouTube discovery is metadata-only and can be filtered to Creative Commons via config.
- `clipbot discover` now exports `data/exports/review_candidates.json`, which is a snapshot of the current `needs_review` queue rather than a generic latest-results dump.
- The generated FFmpeg script normalizes clips to `1080x1920`, `30fps`, and AAC audio.
- The current music-safety workflow is auto-scan plus manual review: use `clipbot scan-music` first, then use `clipbot music-review` only when you want to override or confirm a result.
- Auto-download during render is limited to direct media URLs for approved clips and does not support generic YouTube scraping.
- Upload automation is intentionally out of current scope; export now and upload manually.
- Rediscovery refreshes existing rows by source ID, so archived clips stay archived instead of being re-added as fresh `needs_review` rows.
- `clipbot flush --status needs_review` only deletes the current review backlog; it does not remove approved or archived clips.
