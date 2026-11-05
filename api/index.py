"""Vercel entry point. Vercel's Python runtime serves the ASGI `app` defined here.

Local run:  uvicorn api.index:app --reload
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from neobank.api import create_app  # noqa: E402

app = create_app()
