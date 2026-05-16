"""
Muestra los paths reales de cada categoría faltante agrupados por subcarpeta de Musik.
Uso: python rekordbox-missing-folders.py
"""

import sys
from pathlib import Path
from collections import defaultdict

try:
    from pyrekordbox import Rekordbox6Database
    from pyrekordbox.db6.tables import DjmdContent
except ImportError:
    print("pip install pyrekordbox")
    sys.exit(1)

MUSIK = "X:/Backup_Unidad de USB_24_04_2025/Musik/"

db = Rekordbox6Database()
session = db.session
rows = session.query(DjmdContent).all()

missing = []
for r in rows:
    path = r.FolderPath
    if not path or not path.startswith("X:/"):
        continue
    if not Path(path.replace("/", "\\")).exists():
        missing.append(path)

# Agrupar por primer nivel dentro de Musik/
groups = defaultdict(list)
for path in missing:
    if path.startswith(MUSIK):
        rest = path[len(MUSIK):]
        top = rest.split("/")[0]
    else:
        top = "(sin Musik prefix)"
    groups[top].append(path)

print(f"Total faltantes: {len(missing)}\n")
print("=" * 60)

for top, paths in sorted(groups.items(), key=lambda x: -len(x[1])):
    print(f"\n[{top}]  —  {len(paths)} tracks")
    for p in paths[:3]:
        print(f"  {p[:110]}")
    if len(paths) > 3:
        print(f"  ... y {len(paths)-3} más")

# Mostrar solo primer nivel de Musik (sin rglob)
print("\n" + "=" * 60)
print("\nSubcarpetas en X:\\Backup_Unidad de USB_24_04_2025\\Musik\\:")
musik_path = Path("X:\\Backup_Unidad de USB_24_04_2025\\Musik")
if musik_path.exists():
    for d in sorted(musik_path.iterdir()):
        if d.is_dir():
            print(f"  {d.name}/")
