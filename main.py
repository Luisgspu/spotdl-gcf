"""
Cloud Function — Spotify playlist → 320 kbps MP3 → GCS

POST body: {"playlist_url": "https://open.spotify.com/playlist/..."}

Required env vars (set in .env locally, Cloud Function env vars in prod):
    SPOTIFY_CLIENT_ID      Spotify developer app credentials
    SPOTIFY_CLIENT_SECRET  Spotify developer app credentials

Optional env vars:
    GCS_BUCKET            Override target bucket (default: dj-gig-tracks-2026)
    TIDAL_ACCESS_TOKEN    Windows Bearer token for tidal-wave HiRes downloads

FFmpeg strategy:
    `static-ffmpeg` downloads a self-contained Linux binary on the first
    cold start and caches it for the lifetime of the container instance.
    No layer / buildpack changes needed.

Rekordbox-ready metadata embedded by spotDL by default:
    Title · Artist(s) · Album · BPM · Album art · Genre · Year · ISRC
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import functions_framework
from dotenv import load_dotenv
from google.cloud import storage

# Load .env for local development; no-op in Cloud Functions (no .env file).
load_dotenv()

# ── Logging ────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────
BUCKET_NAME = os.environ.get("GCS_BUCKET", "dj-gig-tracks-2026")

# Leave a 60-second buffer before the Gen2 max 3600 s hard limit.
# Set --timeout 3600 in your deploy command; adjust here to match.
DOWNLOAD_TIMEOUT = 3540  # seconds

# ── Cold-start: wire a static FFmpeg binary into PATH ──────────────────────────
# This runs once per container instance. Subsequent warm invocations are free.
def _setup_ffmpeg() -> None:
    # Ensure a writable HOME so static-ffmpeg and yt-dlp can cache files.
    os.environ.setdefault("HOME", "/tmp")

    try:
        import static_ffmpeg  # type: ignore[import]

        static_ffmpeg.add_paths()  # downloads binary + mutates os.environ["PATH"]
        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            logger.info("FFmpeg ready: %s", ffmpeg_bin)
        else:
            logger.error("static_ffmpeg.add_paths() ran but ffmpeg not found in PATH")
    except Exception:
        logger.exception("FFmpeg cold-start setup failed — encoding will not work")


_setup_ffmpeg()


# ── Entry point ────────────────────────────────────────────────────────────────
@functions_framework.http
def download_playlist(request):  # noqa: ANN001
    """HTTP trigger: download playlist, zip MP3s, upload to GCS."""
    if request.method != "POST":
        return _resp({"error": "Method not allowed — use POST"}, 405)

    body = request.get_json(silent=True) or {}
    playlist_url: str = body.get("playlist_url", "").strip()
    if not playlist_url:
        return _resp({"error": "Missing 'playlist_url' in JSON body"}, 400)

    playlist_id = _extract_playlist_id(playlist_url)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_name = f"playlist_{playlist_id}_{ts}"

    work_dir = Path(tempfile.mkdtemp(prefix=f"spotdl_{job_name}_"))
    zip_path: Path | None = None

    try:
        logger.info("Job %s — starting download of %s", job_name, playlist_url)
        _run_spotdl(playlist_url, work_dir)

        mp3s = list(work_dir.glob("**/*.mp3"))
        logger.info("Job %s — %d MP3(s) collected", job_name, len(mp3s))

        if not mp3s:
            return _resp(
                {"error": "No MP3s produced — check Spotify credentials and playlist URL"},
                422,
            )

        zip_path = _zip_tracks(mp3s, work_dir, job_name)
        gcs_object = f"playlists/{job_name}.zip"
        _upload_to_gcs(zip_path, BUCKET_NAME, gcs_object)

        return _resp(
            {
                "status": "success",
                "job": job_name,
                "mp3_count": len(mp3s),
                "gcs_uri": f"gs://{BUCKET_NAME}/{gcs_object}",
            },
            200,
        )

    except subprocess.TimeoutExpired:
        logger.error("Job %s timed out after %ds", job_name, DOWNLOAD_TIMEOUT)
        # Attempt a partial upload so nothing is lost.
        mp3s = list(work_dir.glob("**/*.mp3"))
        if mp3s and zip_path is None:
            try:
                zip_path = _zip_tracks(mp3s, work_dir, f"{job_name}_partial")
                gcs_object = f"playlists/{job_name}_partial.zip"
                _upload_to_gcs(zip_path, BUCKET_NAME, gcs_object)
                return _resp(
                    {
                        "status": "partial",
                        "job": job_name,
                        "mp3_count": len(mp3s),
                        "gcs_uri": f"gs://{BUCKET_NAME}/{gcs_object}",
                        "warning": "Timed out — partial results saved",
                    },
                    206,
                )
            except Exception:
                logger.exception("Partial upload also failed")
        return _resp({"error": "Download timed out; try a shorter playlist"}, 504)

    except Exception:
        logger.exception("Job %s — unexpected error", job_name)
        return _resp({"error": "Internal error — see Cloud Logging for details"}, 500)

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
        if zip_path and zip_path.exists():
            zip_path.unlink(missing_ok=True)


# ── Helpers ────────────────────────────────────────────────────────────────────
def _extract_playlist_id(url: str) -> str:
    try:
        return url.split("?")[0].rstrip("/").split("/")[-1]
    except Exception:
        return "unknown"


def _run_spotdl(playlist_url: str, output_dir: Path) -> None:
    """
    Run spotDL as a child process.

    --format mp3   — container format
    --bitrate 320k — CBR 320 kbps via FFmpeg (highest quality lossy MP3)
    --threads 4    — concurrent yt-dlp workers (safe for Gen2 2-vCPU instances)

    ID3 tags written by spotDL automatically:
        TIT2 (Title), TPE1 (Artists), TALB (Album), TBPM (BPM),
        APIC (Album art), TCON (Genre), TDRC (Year), TSRC (ISRC)

    Output filename: "{artist} - {title}.mp3" — matches Rekordbox import
    expectations without double-artist duplication.
    """
    client_id = os.environ.get("SPOTIFY_CLIENT_ID", "")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET", "")

    # spotDL output template — curly braces are spotDL placeholders, not f-string
    output_template = str(output_dir) + "/{artist} - {title}.{output-ext}"

    cmd = [
        sys.executable, "-m", "spotdl",
        "download", playlist_url,
        "--output", output_template,
        "--format", "mp3",
        "--bitrate", "320k",
        "--threads", "4",
        "--log-level", "INFO",
        "--save-errors", str(output_dir / "download_errors.txt"),
    ]
    if client_id and client_secret:
        cmd += ["--client-id", client_id, "--client-secret", client_secret]

    env = {**os.environ, "HOME": "/tmp"}

    logger.info("Executing: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        cwd=str(output_dir),
        env=env,
        timeout=DOWNLOAD_TIMEOUT,
        check=False,  # non-zero exit = partial failure; we upload whatever downloaded
    )
    if result.returncode != 0:
        logger.warning(
            "spotDL exited %d — partial results may exist (errors logged to %s)",
            result.returncode,
            output_dir / "download_errors.txt",
        )


def _zip_tracks(mp3_files: list[Path], source_dir: Path, archive_name: str) -> Path:
    """
    Pack MP3s into a ZIP using ZIP_STORED.

    MP3 is already compressed audio; deflating it wastes CPU with <1% size gain.
    ZIP_STORED gives identical byte-perfect files that Rekordbox can read directly
    after extraction without any re-encoding.
    """
    zip_path = Path(tempfile.gettempdir()) / f"{archive_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        for mp3 in sorted(mp3_files):
            zf.write(mp3, arcname=mp3.relative_to(source_dir))
        # Include the error log if present so the caller can audit failures
        err_log = source_dir / "download_errors.txt"
        if err_log.exists() and err_log.stat().st_size > 0:
            zf.write(err_log, arcname="download_errors.txt")

    size_mb = zip_path.stat().st_size / 1_048_576
    logger.info("Archive: %s — %.1f MB (%d tracks)", zip_path.name, size_mb, len(mp3_files))
    return zip_path


def _upload_to_gcs(local_path: Path, bucket_name: str, object_name: str) -> None:
    client = storage.Client()
    blob = client.bucket(bucket_name).blob(object_name)
    blob.upload_from_filename(
        str(local_path),
        content_type="application/zip",
        num_retries=3,
    )
    logger.info("Uploaded → gs://%s/%s", bucket_name, object_name)


def _resp(body: dict, status: int):  # noqa: ANN001
    return (json.dumps(body), status, {"Content-Type": "application/json"})
