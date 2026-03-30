# Project Plan

This file tracks what is already done, what is stable enough to build on, and which future phases are still undecided.

## Phase 0: Foundations

- [x] Create Python project scaffold
- [x] Add CLI entrypoint
- [x] Add SQLite storage for discovered candidates
- [x] Add config template for source discovery
- [x] Add README with setup and workflow notes

## Phase 1: Discovery And Review

- [x] Discover Reddit candidates from configured feeds
- [x] Discover YouTube candidates from the YouTube Data API
- [x] Score candidates using engagement, duration, freshness, keyword, vertical, and rights heuristics
- [x] Store candidate metadata and refresh existing rows on rediscovery
- [x] Support review states: `needs_review`, `approved`, `rejected`
- [x] Keep approvals and notes across `discover` reruns

## Phase 2: Asset Handling

- [x] Support attaching local media files to approved candidates
- [x] Support temporary remote downloads for approved clips with direct media URLs
- [x] Clean up temporary downloaded files after rendering
- [x] Prevent generic YouTube scraping in the remote download path
- [x] Preserve Reddit audio by preferring DASH-based download paths

## Phase 3: Compilation And Render

- [x] Build a `top5` or regular compilation plan from approved clips
- [x] Keep planned output within 180 seconds
- [x] Support local intro and outro clips
- [x] Generate PowerShell render scripts for FFmpeg
- [x] Normalize clips into 1080x1920 Shorts format
- [x] Preserve clip audio when present
- [x] Add silent fallback audio when a clip truly has no audio stream
- [x] Fix concat file generation so FFmpeg can read it reliably
- [x] Improve playback compatibility by normalizing final output audio handling

## Phase 4: Export Handoff

- [x] Produce a final exported video file for manual upload
- [x] Keep plan metadata alongside the exported video for later reference
- [x] Archive clips from a completed plan so they are not selected again by default

## Phase 5: Future Upload Work

- [ ] Upload a rendered compilation to YouTube using the Data API
- [ ] Read upload metadata from the generated plan file
- [ ] Support private upload defaults and future scheduling

## Phase 6: Open Decisions

- [x] Decide how completed/used clips should be tracked after a compilation is rendered
- [x] Decide whether compiled clips should be archived, hidden, or removed from future selection
- [ ] Decide whether to add a one-command flow for `plan + render + upload`
- [ ] Decide whether to add richer review commands such as `show`, `open`, or `attach`
- [ ] Decide whether to add better duplicate prevention across past compilations
- [ ] Decide whether to add background music, subtitles, overlays, or captions

## Working Notes

- Current stable flow: `discover -> list -> approve -> plan -> render`
- Current practical scope ends at exporting the final video for manual upload
- Current post-render archive flow: `archive-plan`
- Approved clips remain in the database across rediscovery
- Archived clips remain in the database for traceability and are excluded from future planning because planning only uses `approved`
- `plan` can reuse older approved clips, not just the newest discovery run
- Remote render/download depends on the source still being reachable at render time
- Playback compatibility is better when final audio is normalized instead of stream-copied

## Candidate Future Phase Slots

Use this section after we decide what the next milestone should be.

### Phase 7

- [ ] TBD

### Phase 8

- [ ] TBD
