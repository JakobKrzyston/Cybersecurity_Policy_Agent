"""Runtime configuration loader; exposes model IDs and pricing data."""

import json
import os
from pathlib import Path

_PRICES_PATH = Path(__file__).parent / "model_prices.json"

_DEFAULT_REASONER_MODEL = "claude-sonnet-4-6"
_DEFAULT_JUDGE_MODEL = "claude-haiku-4-5-20251001"


def load_model_prices() -> dict:
    """Load model pricing data from model_prices.json."""
    with _PRICES_PATH.open() as f:
        return json.load(f)


def get_reasoner_model_id() -> str:
    """Return the Reasoner model ID from env or default."""
    return os.environ.get("REASONER_MODEL_ID", _DEFAULT_REASONER_MODEL)


def get_judge_model_id() -> str:
    """Return the judge model ID from env or default."""
    return os.environ.get("JUDGE_MODEL_ID", _DEFAULT_JUDGE_MODEL)
