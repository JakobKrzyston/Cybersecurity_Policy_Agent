"""Session model: in-memory conversation state for a single session."""

import uuid
from typing import Literal
from pydantic import BaseModel, Field


class Session(BaseModel):
    """Accumulates request history for one conversation; passed into Trust Gate and Reasoner."""

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request_history: list[dict] = Field(default_factory=list)


class SessionContext(BaseModel):
    """Live session signals read by the Trust Gate on each request.

    Args:
        identity: Requester identity string used for blocklist lookup.
        sso_age_hours: Hours since SSO assertion was issued (§15.2 threshold: 8).
        mfa_age_hours: Hours since MFA challenge (§15.2 threshold: 1 for sensitive actions).
        device_type: Endpoint enrollment class; governs trust tier ceiling.
    """

    identity: str
    sso_age_hours: float
    mfa_age_hours: float
    device_type: Literal["managed", "byod", "unenrolled"]
