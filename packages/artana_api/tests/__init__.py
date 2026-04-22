from __future__ import annotations

import sys
from pathlib import Path

PROJECT_SRC = Path(__file__).resolve().parents[1] / "src"
PROJECT_TESTS = Path(__file__).resolve().parent
if str(PROJECT_SRC) not in sys.path:
    sys.path.insert(0, str(PROJECT_SRC))
if str(PROJECT_TESTS) not in sys.path:
    sys.path.insert(0, str(PROJECT_TESTS))
