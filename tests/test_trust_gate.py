"""Trust Gate unit tests: trust tier and risk classification behaviors."""

from src.models.session import Session, SessionContext
from src.pipeline.trust_gate import InMemoryBlocklist, run


def _managed_ctx(identity: str = "alice", sso_age: float = 1.0, mfa_age: float = 0.5) -> SessionContext:
    return SessionContext(identity=identity, sso_age_hours=sso_age, mfa_age_hours=mfa_age, device_type="managed")


def test_blocklisted_identity_returns_red_risk():
    context = _managed_ctx(identity="mallory")
    blocklist = InMemoryBlocklist(blocked={"mallory"})
    _, risk = run(Session(), context, blocklist, tracer=None)
    assert risk == "red"


def test_clean_identity_returns_blue_risk():
    context = _managed_ctx(identity="alice")
    blocklist = InMemoryBlocklist(blocked=set())
    _, risk = run(Session(), context, blocklist, tracer=None)
    assert risk == "blue"


class _FailingBlocklist:
    def lookup(self, identity: str) -> str:
        raise RuntimeError("register unreachable")


def test_blocklist_failure_fails_safe_to_red():
    context = _managed_ctx(identity="alice")
    _, risk = run(Session(), context, _FailingBlocklist(), tracer=None)
    assert risk == "red"


def test_expired_mfa_on_managed_device_downgrades_tier():
    # MFA > 1 hour on a managed device: managed_device → verified_employee (§15.6)
    context = SessionContext(identity="alice", sso_age_hours=1.0, mfa_age_hours=2.0, device_type="managed")
    blocklist = InMemoryBlocklist(blocked=set())
    tier, _ = run(Session(), context, blocklist, tracer=None)
    assert tier == "verified_employee"


def test_valid_managed_session_gets_managed_device_tier():
    # Baseline: valid SSO + valid MFA + managed device = full trust
    context = _managed_ctx()
    blocklist = InMemoryBlocklist(blocked=set())
    tier, _ = run(Session(), context, blocklist, tracer=None)
    assert tier == "managed_device"


def test_byod_device_caps_tier_at_verified_employee():
    # BYOD with valid credentials is bounded to verified_employee, not managed_device (§8, §10.3)
    context = SessionContext(identity="alice", sso_age_hours=1.0, mfa_age_hours=0.5, device_type="byod")
    blocklist = InMemoryBlocklist(blocked=set())
    tier, _ = run(Session(), context, blocklist, tracer=None)
    assert tier == "verified_employee"
