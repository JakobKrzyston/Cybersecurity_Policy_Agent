"""Trust Gate: classifies session trust tier and risk before any LLM reasoning."""

from typing import Literal, Protocol, runtime_checkable

from src.models.session import Session, SessionContext

RiskClassification = Literal["red", "grey", "blue"]
TrustTier = Literal["anonymous", "verified_employee", "managed_device"]

# Policy thresholds from §15.2
_SSO_MAX_AGE_HOURS = 8
_MFA_MAX_AGE_HOURS = 1


@runtime_checkable
class Blocklist(Protocol):
    """Interface for blocklist/watchlist lookups; injectable for testing."""

    def lookup(self, identity: str) -> RiskClassification:
        ...


class InMemoryBlocklist:
    """Mock in-memory blocklist register for Slice 2.

    Args:
        blocked: Identities that return 'red' (blocklisted).
        watchlist: Identities that return 'grey' (elevated caution).
    """

    def __init__(self, blocked: set[str], watchlist: set[str] = frozenset()):
        self._blocked = blocked
        self._watchlist = watchlist

    def lookup(self, identity: str) -> RiskClassification:
        """Return the risk classification for this identity."""
        if identity in self._blocked:
            return "red"
        if identity in self._watchlist:
            return "grey"
        return "blue"


def _classify_trust_tier(context: SessionContext) -> TrustTier:
    if context.device_type == "unenrolled":
        return "anonymous"
    if context.sso_age_hours > _SSO_MAX_AGE_HOURS:
        return "anonymous"
    if context.device_type == "byod" and context.mfa_age_hours > _MFA_MAX_AGE_HOURS:
        return "anonymous"
    if context.device_type == "managed" and context.mfa_age_hours > _MFA_MAX_AGE_HOURS:
        return "verified_employee"
    if context.device_type == "managed":
        return "managed_device"
    return "verified_employee"  # byod with valid mfa


def run(
    session: Session,
    context: SessionContext,
    blocklist: Blocklist,
    tracer,
) -> tuple[TrustTier, RiskClassification]:
    """Classify the session trust tier and risk classification.

    Args:
        session: In-memory session accumulating request history.
        context: Live signals (SSO age, MFA recency, device type, identity).
        blocklist: Blocklist register to consult for risk classification.
        tracer: Pipeline trace context (span appended on completion).

    Returns:
        Tuple of (trust_tier, risk_classification). Fails safe to 'red' on
        blocklist lookup failure rather than passing through.
    """
    trust_tier = _classify_trust_tier(context)

    try:
        risk = blocklist.lookup(context.identity)
    except Exception:
        risk = "red"

    return trust_tier, risk
