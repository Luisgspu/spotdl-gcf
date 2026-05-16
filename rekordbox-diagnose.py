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
null_count = 0
for r in rows:
    path = r.FolderPath
    if not path:
        null_count += 1
        continue
    # Tomar los primeros 4 caracteres como prefijo (ej: "G:/B", "G:\B", "X:/B")
    prefixes[path[:4]] += 1

print("Distribución de prefijos en FolderPath:")
for prefix, count in prefixes.most_common(20):
    print(f"  {prefix!r}  →  {count} filas")

print(f"\n  (null/vacío)  →  {null_count} filas")

# Mostrar 3 ejemplos de cada prefijo único
seen = set()
print("\nEjemplos por prefijo:")
for r in rows:
    path = r.FolderPath
    if not path:
        continue
    p = path[:4]
    if p not in seen:
        seen.add(p)
        print(f"\n  Prefijo {p!r}:")
        print(f"    FolderPath: {path[:120]}")
