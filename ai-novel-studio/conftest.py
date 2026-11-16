"""Make the backend importable when pytest is invoked from the repository root.

The canonical invocation is ``cd backend && pytest``; this shim only exists so
``pytest`` or ``pytest backend/tests`` from the repo root does not fail with an
unhelpful ``ModuleNotFoundError: No module named 'app'``.
"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent / "backend"
if BACKEND.is_dir() and str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))