"""
Remapea carpetas específicas en FolderPath cuando el nombre cambió en disco.
Editar FOLDER_REMAPS con los pares (ruta_en_db, ruta_real_en_disco).
Uso: python rekordbox-remap-folders.py [--dry-run]
"""

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(os.environ["APPDATA"]) / "Pioneer" / "rekordbox" / "master.db"

BASE = "X:/Backup_Unidad de USB_24_04_2025/Musik/"

# (prefijo_en_db, prefijo_real_en_disco)
# Agregar más líneas según lo que el usuario confirme
FOLDER_REMAPS = [
    (BASE + "Cachengue Mix/",  BASE + "Arg/Cachengue Mix/"),
    (BASE + "Feid/",           BASE + "Dembow-Reggaeton/Feid/"),
]


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        from pyrekordbox import Rekordbox6Database
        from pyrekordbox.db6.tables import DjmdContent
    except ImportError:
        print("pip install pyrekordbox")
        sys.exit(1)

    if dry_run:
        print("MODO DRY-RUN\n")
    elif not dry_run:
        backup = DB_PATH.parent / f"master_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup: {backup}\n")

    db = Rekordbox6Database()
    session = db.session
    rows = session.query(DjmdContent).all()

    total = 0
    for old_prefix, new_prefix in FOLDER_REMAPS:
        matches = [r for r in rows if r.FolderPath and r.FolderPath.startswith(old_prefix)]
        print(f"{old_prefix.split('/')[-2]}  →  {new_prefix.split('/')[-2]}:  {len(matches)} tracks")

        if dry_run:
            for r in matches[:2]:
                new_path = new_prefix + r.FolderPath[len(old_prefix):]
                print(f"  ANTES:   {r.FolderPath[:100]}")
                print(f"  DESPUES: {new_path[:100]}")
                exists = Path(new_path.replace("/", "\\")).exists()
                print(f"  Existe en disco: {exists}")
            continue

        for r in matches:
            r.FolderPath = new_prefix + r.FolderPath[len(old_prefix):]
        total += len(matches)

    if not dry_run:
        session.commit()
        print(f"\nListo — {total} rutas actualizadas.")
    else:
        print("\nNada modificado (dry-run).")


if __name__ == "__main__":
    main()
