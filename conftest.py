import sys
import os

# Ensure the project root is on sys.path so `uv run python tests/...` and
# `uv run pytest` both resolve `src.*` imports correctly.
sys.path.insert(0, os.path.dirname(__file__))
