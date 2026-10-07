import importlib.util
import sys
from pathlib import Path

# Every function's source file is named main.py, so this one is loaded under a
# distinct module name to avoid colliding with tests/gtfs_fetch's `import main`.
_MAIN_PATH = Path(__file__).resolve().parents[2] / "src" / "arrivals_fetch" / "main.py"
_spec = importlib.util.spec_from_file_location("arrivals_main", _MAIN_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules["arrivals_main"] = _module
_spec.loader.exec_module(_module)
