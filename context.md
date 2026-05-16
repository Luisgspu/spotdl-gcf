# Project Context

## Goal
Automate downloading Spotify playlists as 320 kbps MP3s and storing them in GCS,
so tracks are immediately available for import into **Rekordbox** (Pioneer DJ software)
without any manual re-encoding or metadata cleanup.

## Owner
- **GitHub:** https://github.com/Luisgspu/spotdl-gcf
- **GCS bucket:** `dj-gig-tracks-2026`
- **Deploy region:** `us-central1`
- **Function name:** `download_playlist`

## Rekordbox Compatibility Requirements
These are non-negotiable — do not change without understanding the impact on Rekordbox import:

| Requirement | Implementation |
|---|---|
| 320 kbps CBR MP3 | `--bitrate 320k --format mp3` in spotDL |
| Filename: `Artist - Title.mp3` | `--output {artist} - {title}.{output-ext}` |
| ID3: Title, Artist, Album | Written by spotDL/mutagen automatically |
| ID3: BPM | spotDL fetches from Spotify metadata when available |
| ID3: Album art (APIC) | Embedded by spotDL from Spotify cover image |
| ID3: Genre, Year, ISRC | Written by spotDL automatically |

## Spotify API
- **Dashboard:** https://developer.spotify.com/dashboard
- **Flow used:** Client Credentials (no user login, no browser redirect)
- **Redirect URI registered:** `http://127.0.0.1:8888/callback` (required by form, never called at runtime)
- **Credentials:** stored as Cloud Function env vars `SPOTIFY_CLIENT_ID` / `SPOTIFY_CLIENT_SECRET`
- **Quota:** Default free tier is sufficient — spotDL only calls metadata endpoints, not streaming

## Known Limitations & Decisions

### Why subprocess instead of spotDL Python API?
spotDL's internal state (asyncio loop, yt-dlp downloader instances) is not designed
to be reused across multiple HTTP requests in the same process. Running it as a subprocess
gives clean isolation per request with no state leakage.

### Why ZIP_STORED and not ZIP_DEFLATED?
MP3 is a compressed audio format. Deflating it typically yields <1% size reduction
at significant CPU cost. ZIP_STORED copies bytes directly, making the archive faster
to create and producing files Rekordbox can extract without any quality change.

### Why static-ffmpeg instead of a buildpack?
A buildpack adds ~200 MB to the deploy artifact and requires changes to `app.yaml` or
`Procfile`. `static-ffmpeg` downloads a pre-built binary at cold start — no deploy changes,
no additional configuration, self-contained in the pip dependency graph.

### Why concurrency=1?
Cloud Function Gen2 supports concurrent requests on the same instance. `/tmp` is shared
across concurrent executions. Two simultaneous playlist downloads would exhaust `/tmp`
space (~512 MB). Concurrency=1 guarantees one job per instance; GCP scales instances
horizontally for parallel requests.

### /tmp space ceiling
Gen2 Cloud Functions: `/tmp` is **512 MB regardless of memory allocation**.
At 320 kbps (~8 MB/track), the safe limit is ~60 tracks per run.
For larger playlists, consider migrating to Cloud Run where `/tmp` can be increased
via `--execution-environment gen2 --add-volume` or a mounted GCS FUSE volume.

## Deployment Checklist
- [ ] `SPOTIFY_CLIENT_ID` set in shell env
- [ ] `SPOTIFY_CLIENT_SECRET` set in shell env
- [ ] `gcloud auth login` completed
- [ ] `gcloud config set project <PROJECT_ID>` set
- [ ] GCS bucket `dj-gig-tracks-2026` exists in `us-central1`
- [ ] Service account has `roles/storage.objectAdmin` on the bucket
- [ ] `bash deploy.sh` executed successfully

## Test Command (after deploy)
```bash
curl -X POST \
  $(gcloud functions describe download_playlist --region us-central1 --gen2 --format='value(serviceConfig.uri)') \
  -H "Content-Type: application/json" \
  -d '{"playlist_url": "https://open.spotify.com/playlist/1HcikGvh5kGDTkzTLZX3U4"}'
```

## Tidal Downloads (tidal-wave)

### Tool
`tidal-wave` v2025.11.1 is installed. Supports HiRes FLAC (24-bit/192kHz) and LOSSLESS FLAC
where available, making it the best quality source when tracks are found there.

### Token problem — browser JWT does not authorize streaming
The `TIDAL_ACCESS_TOKEN` in `.env` is a browser OAuth JWT (`cid: 8049`, TV/web client).
It works for reading metadata (albums, playlists, track info) but returns **401 Unauthorized**
on `GET /v1/tracks/{id}/playbackinfopostpaywall` — the endpoint that hands out the actual
audio stream URL. Tidal intentionally blocks streaming from web-session tokens.

**Evidence:** `tidal_debug.log` from 2026-05-14 shows successful metadata fetch for a playlist
("80s") but 401 on every `playbackinfopostpaywall` call → all 38 tracks downloaded as `null`.

### Fix: device-code login (one-time)
Run `tidal-wave` once; on first run without a saved session it triggers a **device code flow**
(open `link.tidal.com`, enter the code). The resulting session is saved to
`%APPDATA%\tidal-wave\` and is fully authorized for audio streaming.
The browser JWT in `.env` is NOT used by tidal-wave — it has its own session store.

### Subscription requirement
LOSSLESS requires **Tidal HiFi**; HiRes FLAC requires **Tidal HiFi Plus**.
Verify the account tier before expecting lossless downloads.

### Pending work for Tidal integration
- Complete device-code login to create a valid tidal-wave session
- Write a search step: CSV artist/title → Tidal track URL (via Tidal search API, using the
  browser JWT which is valid for metadata) → pass URL to tidal-wave for download
- Script: try Tidal first (HiRes/FLAC), fall back to Soulseek (sldl) if not found

## Future Improvements (not yet implemented)
- Webhook / Pub-Sub notification when download completes (for long playlists)
- Batch mode: accept a list of playlist URLs in one request
- GCS lifecycle rule to auto-delete ZIPs older than 30 days
- Cloud Run migration for playlists >60 tracks
