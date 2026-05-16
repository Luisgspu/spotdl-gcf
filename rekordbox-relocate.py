"""
Rekordbox 6 path relocator — usa pyrekordbox para manejar el cifrado de master.db
Uso: python rekordbox-relocate.py [--dry-run]

Requiere: pip install pyrekordbox
"""

import sys
import os
import shutil
from pathlib import Path
from datetime import datetime

# Todos los drives que fueron el USB en distintos momentos → ahora es X:
USB_DRIVES = ["E:/", "F:/", "G:/"]
NEW_PREFIX = "X:/"

DB_PATH = Path(os.environ["APPDATA"]) / "Pioneer" / "rekordbox" / "master.db"


def remap(path: str) -> str | None:
    """Devuelve la ruta remapeada si aplica, o None si no hay cambio."""
    if not path:
        return None
    for old in USB_DRIVES:
        if path.startswith(old):
            return NEW_PREFIX + path[len(old):]
    return None


def main():
    dry_run = "--dry-run" in sys.argv

    try:
        from pyrekordbox import Rekordbox6Database
        from pyrekordbox.db6.tables import DjmdContent
    except ImportError:
        print("Falta pyrekordbox. Instalalo con:")
        print("  pip install pyrekordbox")
        sys.exit(1)

    print(f"Base de datos: {DB_PATH}")
    print(f"Drives USB a remapear: {USB_DRIVES}  →  {NEW_PREFIX}")
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

    to_update = [r for r in rows if remap(r.FolderPath) is not None]

    print(f"Filas a actualizar: {len(to_update)}")

    if dry_run:
        from collections import Counter
        by_drive = Counter(r.FolderPath[:3] for r in to_update)
        print("\nDesglose por drive:")
        for drive, count in sorted(by_drive.items()):
            print(f"  {drive}  →  {count} filas")
        print("\nEjemplos (primeras 3 de cada drive):")
        shown = Counter()
        for r in to_update:
            drive = r.FolderPath[:3]
            if shown[drive] < 3:
                print(f"  {r.FolderPath[:100]}")
                shown[drive] += 1
        print("\nNada fue modificado.")
        return

    for r in to_update:
        new_path = remap(r.FolderPath)
        if new_path:
            r.FolderPath = new_path

    session.commit()
    print(f"\nListo — {len(to_update)} rutas actualizadas.")
    print("Abri Rekordbox y verificá en File Manager que las tracks ya no aparezcan como missing.")


if __name__ == "__main__":
    main()
