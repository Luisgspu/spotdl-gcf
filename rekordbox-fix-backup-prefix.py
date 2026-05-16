"""
Segundo pase: inserta 'Backup_Unidad de USB_24_04_2025/' en rutas X:/ que lo perdieron.
Ejemplo: X:/Musik/... → X:/Backup_Unidad de USB_24_04_2025/Musik/...

Uso: python rekordbox-fix-backup-prefix.py [--dry-run]
"""

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

DB_PATH = Path(os.environ["APPDATA"]) / "Pioneer" / "rekordbox" / "master.db"

BACKUP_FOLDER = "Backup_Unidad de USB_24_04_2025"

# Carpetas raíz del USB que necesitan el prefijo de backup
ROOT_FOLDERS_ON_USB = [
    "Musik",
    "Terraza Latin Tech",
    "reguetonchito wiki wiki",
    "Keloko",
]

PREFIXES_TO_FIX = [f"X:/{folder}/" for folder in ROOT_FOLDERS_ON_USB]


def needs_fix(path: str) -> bool:
    if not path:
        return False
    return any(path.startswith(p) for p in PREFIXES_TO_FIX)


def fix_path(path: str) -> str:
    # X:/Musik/... → X:/Backup_Unidad de USB_24_04_2025/Musik/...
    return f"X:/{BACKUP_FOLDER}/" + path[len("X:/"):]


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        from pyrekordbox import Rekordbox6Database
        from pyrekordbox.db6.tables import DjmdContent
    except ImportError:
        print("pip install pyrekordbox")
        sys.exit(1)

    print(f"Base de datos: {DB_PATH}")
    print(f"Insertando '{BACKUP_FOLDER}/' en rutas X:/ sin ese prefijo")
    if dry_run:
        print("MODO DRY-RUN — no se escribirá nada\n")
    else:
        print()

    if not dry_run:
        backup = DB_PATH.parent / f"master_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        shutil.copy2(DB_PATH, backup)
        print(f"Backup guardado en: {backup}\n")

    db = Rekordbox6Database()
    session = db.session
    rows = session.query(DjmdContent).all()

    to_fix = [r for r in rows if needs_fix(r.FolderPath)]
    print(f"Filas a corregir: {len(to_fix)}")

    if dry_run:
        from collections import Counter
        by_prefix = Counter()
        for r in to_fix:
            for p in PREFIXES_TO_FIX:
                if r.FolderPath.startswith(p):
                    by_prefix[p] += 1
        print("\nDesglose:")
        for prefix, count in sorted(by_prefix.items()):
            print(f"  {prefix!r}  →  {count} filas")
        print("\nEjemplos (primeras 3):")
        for r in to_fix[:3]:
            print(f"  ANTES: {r.FolderPath[:100]}")
            print(f"  DESPUES: {fix_path(r.FolderPath)[:100]}")
            print()
        print("Nada fue modificado.")
        return

    for r in to_fix:
        r.FolderPath = fix_path(r.FolderPath)

    session.commit()
    print(f"\nListo — {len(to_fix)} rutas corregidas.")
    print("Cerrá y reabrí Rekordbox para que tome los cambios.")


if __name__ == "__main__":
    main()
