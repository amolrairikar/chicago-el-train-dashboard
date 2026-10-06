import sys
from pathlib import Path

# Make the function's source importable as `main`, matching how Cloud Functions loads it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "gtfs_fetch"))
