"""
deezer-download.py
Lee Argentina_Mundial_26_Mix.csv, busca cada track en Deezer y lo descarga
en MP3 320kbps usando deemix.

Requisitos:
    pip install deemix requests

Uso:
    python deezer-download.py

Configuración:
    Editar ARL y OUTPUT_DIR abajo, o pasar por variable de entorno:
        set DEEZER_ARL=tu_arl
        python deezer-download.py
"""

import csv
import os
import subprocess
import sys
import time
import requests
from pathlib import Path

# ── Configuración ────────────────────────────────────────────────────────────
ARL = os.environ.get("DEEZER_ARL", "")

CSV_PATH = Path(__file__).parent / "playlists csv" / "Argentina_Mundial_26_Mix.csv"
OUTPUT_DIR = Path(__file__).parent / "downloads"
MISSING_LOG = Path(__file__).parent / "missing_deezer_Argentina_Mundial_26_Mix.txt"

BITRATE = "320"   # 128 | 320 | FLAC
SEARCH_URL = "https://api.deezer.com/search"
DELAY = 1.0       # segundos entre búsquedas (respetar rate limit)
# ─────────────────────────────────────────────────────────────────────────────


def search_deezer(artist: str, title: str) -> str | None:
    """Devuelve la URL del primer resultado en Deezer o None si no encontró."""
    # Intentar búsqueda exacta primero, luego relajada
    queries = [
        f'artist:"{artist}" track:"{title}"',
        f"{artist} {title}",
    ]
    for q in queries:
        try:
            resp = requests.get(SEARCH_URL, params={"q": q, "limit": 5}, timeout=10)
            data = resp.json()
            if data.get("data"):
                return data["data"][0]["link"]
        except Exception as e:
            print(f"  [!] Error buscando '{artist} - {title}': {e}")
    return None


def setup_arl(config_dir: Path) -> None:
    """Escribe el ARL en el archivo de config de deemix."""
    config_dir.mkdir(parents=True, exist_ok=True)
    arl_file = config_dir / ".arl"
    arl_file.write_text(ARL, encoding="utf-8")


def download_track(url: str, output_dir: Path, config_dir: Path) -> bool:
    """Descarga un track con deemix. Devuelve True si tuvo éxito."""
    cmd = [
        sys.executable, "-m", "deemix",
        "-b", BITRATE,
        "-p", str(output_dir),
        url,
    ]
    # Apuntamos la variable de entorno al config dir para que deemix encuentre el .arl
    env = {**os.environ, "DEEMIX_CONFIG_FOLDER": str(config_dir)}
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"  [!] deemix error: {result.stderr.strip()}")
        return False
    return True


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Config dir: en Windows deemix busca en %APPDATA%\deemix
    # Usamos una carpeta local al script para no tocar la config del sistema
    config_dir = Path(__file__).parent / ".deemix-config" / "deemix"
    setup_arl(config_dir)

    missing = []

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tracks = list(reader)

    total = len(tracks)
    print(f"Playlist: {CSV_PATH.stem} — {total} tracks\n")

    for i, row in enumerate(tracks, 1):
        title = row["Track Name"].strip()
        # Tomar solo el primer artista si hay varios separados por ";"
        artist = row["Artist Name(s)"].split(";")[0].strip()

        print(f"[{i}/{total}] {artist} — {title}")

        url = search_deezer(artist, title)
        if not url:
            print(f"  ✗ No encontrado en Deezer")
            missing.append(f"{artist} — {title}")
            time.sleep(DELAY)
            continue

        print(f"  → {url}")
        ok = download_track(url, OUTPUT_DIR, config_dir)
        if ok:
            print(f"  ✓ Descargado")
        else:
            missing.append(f"{artist} — {title}")

        time.sleep(DELAY)

    print(f"\n{'─'*50}")
    print(f"Completado: {total - len(missing)}/{total} descargados")

    if missing:
        MISSING_LOG.write_text("\n".join(missing), encoding="utf-8")
        print(f"Faltantes ({len(missing)}): guardados en {MISSING_LOG.name}")


if __name__ == "__main__":
    main()
