"""Session model: in-memory conversation state for a single session."""

import uuid
from pydantic import BaseModel, Field


class Session(BaseModel):
    """Accumulates request history for one conversation; passed into Trust Gate and Reasoner."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_history: list[dict] = Field(default_factory=list)
