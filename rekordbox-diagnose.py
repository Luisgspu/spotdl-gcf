"""
Diagnóstico: inspecciona los formatos de ruta en master.db de Rekordbox
Uso: python rekordbox-diagnose.py
"""

import sys
from collections import Counter

try:
    from pyrekordbox import Rekordbox6Database
    from pyrekordbox.db6.tables import DjmdContent
except ImportError:
    print("pip install pyrekordbox")
    sys.exit(1)

db = Rekordbox6Database()
session = db.session
rows = session.query(DjmdContent).all()

print(f"Total filas en DjmdContent: {len(rows)}\n")

prefixes = Counter()
for r in rows:
    path = r.FolderPath
    if path:
        prefixes[path[:5]] += 1

print("Distribución de prefijos (5 chars) en FolderPath:")
for prefix, count in prefixes.most_common(30):
    print(f"  {prefix!r}  →  {count} filas")

# Mostrar un ejemplo de cada prefijo único
seen = set()
print("\nEjemplos:")
for r in rows:
    path = r.FolderPath
    if not path:
        continue
    p = path[:5]
    if p not in seen:
        seen.add(p)
        print(f"  {p!r}: {path[:120]}")
