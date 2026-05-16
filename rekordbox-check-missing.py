"""
Verifica qué rutas X:/Backup_Unidad... no existen en disco.
Muestra ejemplos para identificar el patrón de las faltantes.
Uso: python rekordbox-check-missing.py
"""

import sys
import os
from pathlib import Path

try:
    from pyrekordbox import Rekordbox6Database
    from pyrekordbox.db6.tables import DjmdContent
except ImportError:
    print("pip install pyrekordbox")
    sys.exit(1)

db = Rekordbox6Database()
session = db.session
rows = session.query(DjmdContent).all()

found = []
missing = []

for r in rows:
    path = r.FolderPath
    if not path or not path.startswith("X:/"):
        continue
    # Convertir a ruta de Windows
    win_path = path.replace("/", "\\")
    if os.path.exists(win_path):
        found.append(path)
    else:
        missing.append(path)

print(f"Tracks X:/ encontrados en disco: {len(found)}")
print(f"Tracks X:/ NO encontrados en disco: {len(missing)}")

if missing:
    print("\nPrimeros 10 faltantes:")
    for p in missing[:10]:
        print(f"  {p[:120]}")

    # Buscar el directorio más cercano que sí existe
    print("\nVerificando dónde se corta la ruta (primeros 3):")
    for p in missing[:3]:
        parts = p.replace("/", "\\").split("\\")
        for i in range(len(parts), 0, -1):
            partial = "\\".join(parts[:i])
            if os.path.exists(partial):
                print(f"  Existe hasta: {partial}")
                print(f"  Ruta completa: {p[:100]}")
                # Mostrar qué hay en ese directorio
                try:
                    entries = os.listdir(partial)[:5]
                    print(f"  Contenido de ese dir: {entries}")
                except Exception:
                    pass
                break
        print()
