# CLAUDE.md — Working Rules for This Repo

## What This Project Does
Google Cloud Function (Gen2, Python 3.11) that accepts a Spotify playlist URL via HTTP POST,
downloads every track as a 320 kbps MP3 using spotDL, zips the result, and uploads it to GCS.

## Key Files
| File | Purpose |
|---|---|
| `main.py` | Single-file Cloud Function — entry point is `download_playlist(request)` |
| `requirements.txt` | Runtime deps: spotdl, static-ffmpeg, google-cloud-storage, functions-framework |
| `deploy.sh` | One-shot `gcloud functions deploy` with all flags pre-configured |
| `architecture.md` | System design, data flow, resource limits |
| `context.md` | Project background, credentials, GCS bucket, Rekordbox goals |
| `slsk-download.ps1` | Local Soulseek downloader — accepts Exportify CSV, Spotify URL, or single track |
| `sldl.conf` | sldl config — FLAC/WAV preferred, MP3 320 kbps fallback, format whitelist |
| `check-downloads.ps1` | Verify downloads vs CSV, detect cross-playlist duplicates, export missing CSV |

## Environment Variables (required at deploy time)
| Variable | Description |
|---|---|
| `SPOTIFY_CLIENT_ID` | From Spotify Developer Dashboard |
| `SPOTIFY_CLIENT_SECRET` | From Spotify Developer Dashboard |
| `GCS_BUCKET` | Optional override — defaults to `dj-gig-tracks-2026` |

## Rules for Code Changes

### Never break these invariants
- FFmpeg MUST be set up via `static_ffmpeg.add_paths()` at module load (cold-start), not inside the handler.
- spotDL MUST run as a subprocess (`sys.executable -m spotdl`), not imported as a library — it manages its own process state.
- Temp directories MUST be cleaned up in the `finally` block of `download_playlist`.
- On timeout, attempt a partial ZIP upload before returning 504.
- ZIP compression MUST stay `ZIP_STORED` — MP3s are already compressed; deflating wastes CPU.

### Constraints
- `/tmp` is the only writable directory in Cloud Functions — all paths must be under it.
- `HOME` must be set to `/tmp` in the subprocess env so yt-dlp and spotDL can cache files.
- Memory: 8192 MB, CPU: 2 vCPU, Timeout: 3600 s (DOWNLOAD_TIMEOUT = 3540 s in code).
- Concurrency is set to 1 — one playlist per instance to avoid `/tmp` collisions.

### When editing main.py
- Do not add new top-level imports without adding them to `requirements.txt`.
- Do not change the output filename template `{artist} - {title}.{output-ext}` — Rekordbox expects this format.
- The `--bitrate 320k` and `--format mp3` flags must never be removed or made configurable via request body.

## Local Soulseek Download Workflow

### Descargar un playlist completo
Exportar el playlist desde [exportify.net](https://exportify.net) como CSV y guardarlo en `playlists csv\`, luego:
```powershell
.\slsk-download.ps1 ".\playlists csv\MiPlaylist.csv"
```
Descarga en `downloads\` con formato `Artist - Title.flac` (o `.mp3` si no hay FLAC).

### Verificar qué se descargó
```powershell
# Ver qué falta de un CSV
.\check-downloads.ps1 ".\playlists csv\MiPlaylist.csv"

# Verificar múltiples playlists y detectar duplicados entre ellas
.\check-downloads.ps1 ".\playlists csv\Playlist1.csv",".\playlists csv\Playlist2.csv"

# Exportar CSV con solo los faltantes
.\check-downloads.ps1 ".\playlists csv\MiPlaylist.csv" -ExportMissing
# → genera missing_MiPlaylist.csv en la raíz del proyecto

# Exportar Y descargar los faltantes en un solo paso
.\check-downloads.ps1 ".\playlists csv\MiPlaylist.csv" -ExportMissing -Run
```

### Re-intentar tracks fallidos
```powershell
# check-downloads genera missing_<nombre>.csv automáticamente
.\check-downloads.ps1 ".\playlists csv\MiPlaylist.csv" -ExportMissing -Run

# O manualmente si ya tenés el CSV de faltantes
.\slsk-download.ps1 ".\missing_MiPlaylist.csv"
```

### Detección de duplicados entre playlists
Pasar múltiples CSVs a `check-downloads.ps1` detecta canciones que aparecen en más
de un playlist. Si ya están en `downloads\`, no se vuelven a descargar.

### Notas de sldl.conf
- `format = flac,wav,mp3` — whitelist; sin este orden, sldl rechaza FLAC antes de aplicar `pref-format`
- `pref-format = flac,wav` — prioriza lossless cuando está disponible
- `min-bitrate = 320` — rechaza MP3 por debajo de 320 kbps
- `fast-search = false` en el config file (no como flag CLI — sería interpretado como booleano true)

## Local Testing (Cloud Function)
```bash
# Install deps
pip install -r requirements.txt

# Run locally (functions-framework)
export SPOTIFY_CLIENT_ID=your_id
export SPOTIFY_CLIENT_SECRET=your_secret
functions-framework --target download_playlist --port 8080

# Test
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"playlist_url": "https://open.spotify.com/playlist/..."}'
```

## Deploy
```bash
export SPOTIFY_CLIENT_ID=your_id
export SPOTIFY_CLIENT_SECRET=your_secret
bash deploy.sh
```

## GCS Output Path
`gs://dj-gig-tracks-2026/playlists/<playlist_id>_<timestamp>.zip`
