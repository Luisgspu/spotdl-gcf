# Architecture

## System Overview

```
Client (curl / app)
        │  POST {"playlist_url": "..."}
        ▼
┌─────────────────────────────────────────────────────────┐
│          Cloud Function Gen2  (us-central1)             │
│                                                         │
│  Cold start                                             │
│  └─ static_ffmpeg.add_paths()                           │
│       Downloads static FFmpeg binary → /tmp             │
│       Mutates PATH — runs once per container instance   │
│                                                         │
│  Request handler: download_playlist()                   │
│  ├─ Validate JSON body → extract playlist_url           │
│  ├─ mkdir /tmp/spotdl_<job>_<uuid>/                     │
│  ├─ subprocess: python -m spotdl download ...           │
│  │     ├─ Calls Spotify Web API (metadata + BPM)        │
│  │     ├─ Searches YouTube via yt-dlp                   │
│  │     ├─ Downloads audio stream                        │
│  │     └─ FFmpeg re-encodes → MP3 320 kbps CBR          │
│  │           ID3 tags: Title, Artist, Album, BPM,       │
│  │           Album art, Genre, Year, ISRC               │
│  ├─ Collect *.mp3 from work dir                         │
│  ├─ ZIP (ZIP_STORED) → /tmp/<job>.zip                   │
│  ├─ Upload → GCS                                        │
│  └─ cleanup /tmp (finally block)                        │
│                                                         │
│  Timeout path (>3540 s)                                 │
│  └─ Partial ZIP of whatever downloaded → GCS            │
│     Returns HTTP 206 with warning                       │
└─────────────────────────────────────────────────────────┘
        │
        ▼
gs://dj-gig-tracks-2026/playlists/<job>.zip
```

## Component Breakdown

### Cloud Function (Gen2)
- **Runtime:** Python 3.11
- **Region:** us-central1
- **Memory:** 8192 MB (large playlists need headroom for yt-dlp + FFmpeg)
- **CPU:** 2 vCPU
- **Timeout:** 3600 s (hard GCP limit for Gen2)
- **Concurrency:** 1 (prevents `/tmp` space collisions between concurrent requests)
- **Instances:** 0–5 (scales to zero when idle)

### FFmpeg Strategy
- **Library:** `static-ffmpeg` (PyPI)
- **Mechanism:** Downloads a pre-built static Linux x86-64 binary on first cold start,
  caches it for the container lifetime. No buildpack, no Docker layer, no apt-get.
- **Why not a buildpack?** Buildpacks add deploy complexity and a ~200 MB layer.
  `static-ffmpeg` is simpler and self-contained in the Python dependency graph.

### spotDL
- **Version:** `>=4.2.10,<5`
- **Mode:** Subprocess (`python -m spotdl`) — not imported as a library.
  Reason: spotDL manages internal singleton state (event loop, yt-dlp sessions)
  that is not safe to share across requests in the same process.
- **Key flags:**
  - `--format mp3` — output container
  - `--bitrate 320k` — CBR via FFmpeg (highest quality lossy MP3)
  - `--threads 4` — concurrent yt-dlp workers
  - `--output {artist} - {title}.{output-ext}` — Rekordbox-compatible filename

### GCS Upload
- **Bucket:** `dj-gig-tracks-2026`
- **Path:** `playlists/<playlist_id>_<YYYYMMDDTHHMMSSz>.zip`
- **Content-Type:** `application/zip`
- **Retries:** 3 (built into the GCS client call)
- **Auth:** Application Default Credentials via the function's service account

## Data Flow — Timing Budget

| Phase | Typical time | Notes |
|---|---|---|
| Cold start (FFmpeg download) | 5–15 s | Only on first invocation per instance |
| spotDL warm-up | 2–5 s | Library import + Spotify auth |
| Per-track download + encode | 15–45 s | Depends on track length and YouTube speed |
| ZIP creation | 1–5 s | ZIP_STORED = no compression CPU cost |
| GCS upload | 5–30 s | Depends on total file size |

A 20-track playlist typically completes in 8–15 minutes.
The 3540 s timeout safely covers playlists up to ~80 tracks.

## Storage
- `/tmp` in Cloud Functions: **~512 MB usable** (8 GB memory allocation does not increase /tmp)
- A 320 kbps MP3 averages ~8 MB per track
- Safe limit: ~60 tracks before `/tmp` pressure
- For larger playlists, consider splitting into batches or upgrading to Cloud Run

## Security
- Function is deployed `--allow-unauthenticated` for easy curl access
- Credentials (Spotify) are injected as env vars at deploy time, never in source
- Service account only needs `roles/storage.objectAdmin` on the target bucket
- No user data is stored — `/tmp` is wiped after each request
