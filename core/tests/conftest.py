import os
import sys
from pathlib import Path

# Configure an isolated data dir BEFORE importing aitrader modules.
_ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("AI_TRADER_HOME", str(Path(os.environ.get("TEMP", "/tmp")) / "aitrader_tests"))
os.environ.setdefault("AI_TRADER_SKILLS", str(_ROOT / "skills"))

sys.path.insert(0, str(_ROOT / "core"))
