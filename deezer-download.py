"""
deezer-download.py
Lee un CSV de Exportify, busca cada track en Deezer y lo descarga en MP3 320kbps.

Uso:
    python deezer-download.py "playlists csv/MiPlaylist.csv"
    python deezer-download.py                          # usa Argentina_Mundial_26_Mix.csv por defecto
"""

import csv
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

# ── Configuración ────────────────────────────────────────────────────────────
ARL = os.environ.get(
    "DEEZER_ARL",
    "aec6a9d36adf864ee610c8ba634073df04ab85347dc5ff6ac98e14df3371a6569fc2f28029147a41e823d14cf226e35e4016ac1e42a1691c64d761b8c7948c70234eeedc2e5db66ba0ea24fea747b8b21982002467472cd0d52e683b16059d4d"
)

_default_csv = Path(__file__).parent / "playlists csv" / "Argentina_Mundial_26_Mix.csv"
CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_csv
OUTPUT_DIR = Path(__file__).parent / "downloads"
MISSING_LOG = Path(__file__).parent / f"missing_deezer_{CSV_PATH.stem}.txt"

BITRATE = "320"   # 128 | 320 | FLAC
SEARCH_URL = "https://api.deezer.com/search"
DELAY = 1.0       # segundos entre búsquedas (respetar rate limit)
# ─────────────────────────────────────────────────────────────────────────────


def search_deezer(artist: str, title: str) -> str | None:
    """Devuelve la URL del primer resultado en Deezer o None si no encontró."""
    queries = [
        f'artist:"{artist}" track:"{title}"',
        f"{artist} {title}",
    ]
    last_error = None
    for q in queries:
        try:
            resp = requests.get(SEARCH_URL, params={"q": q, "limit": 5}, timeout=10)
            data = resp.json()
            if data.get("data"):
                return data["data"][0]["link"]
        except Exception as e:
            last_error = e
    if last_error:
        print(f"  [!] Error de red: {last_error}")
    return None


def download_track(url: str, output_dir: Path, config_dir: Path) -> bool:
    """Descarga un track con deemix. Devuelve True si tuvo éxito."""
    cmd = [
        sys.executable, "-m", "deemix",
        "-b", BITRATE,
        "-p", str(output_dir),
        url,
    ]
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Config dir: en Windows deemix busca en %APPDATA%\deemix
    # Usamos una carpeta local al script para no tocar la config del sistema
    config_dir = Path(__file__).parent / ".deemix-config" / "deemix"
    missing = []

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tracks = list(reader)

    total = len(tracks)
    print(f"Playlist: {CSV_PATH.stem} — {total} tracks\n", flush=True)

    for i, row in enumerate(tracks, 1):
        title = row["Track Name"].strip()
        # Tomar solo el primer artista si hay varios separados por ";"
        artist = row["Artist Name(s)"].split(";")[0].strip()

        print(f"[{i}/{total}] {artist} — {title}", flush=True)

        url = search_deezer(artist, title)
        if not url:
            print(f"  NOT FOUND en Deezer", flush=True)
            missing.append(f"{artist} — {title}")
            time.sleep(DELAY)
            continue

        print(f"  -> {url}", flush=True)
        ok = download_track(url, OUTPUT_DIR, config_dir)
        if ok:
            print(f"  OK Descargado", flush=True)
        else:
            missing.append(f"{artist} — {title}")

        time.sleep(DELAY)

    print(f"\n{'-'*50}")
    print(f"Completado: {total - len(missing)}/{total} descargados")

    if missing:
        MISSING_LOG.write_text("\n".join(missing), encoding="utf-8")
        print(f"Faltantes ({len(missing)}): guardados en {MISSING_LOG.name}")


if __name__ == "__main__":
    main()