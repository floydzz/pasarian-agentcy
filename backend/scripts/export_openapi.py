"""Regenerate the public API contract without connecting to a provider."""
import json
from pathlib import Path
import sys

backend = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend))
from app.main import app

destination = backend.parent / "docs" / "api" / "openapi.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(f"API contract updated: {destination}")
