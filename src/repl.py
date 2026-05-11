"""REPL entry point: interactive loop for the Gaggia Helpdesk Policy Agent.

Invoked with: python -m src.repl
"""

from __future__ import annotations

import sys

from src.models.session import Session, SessionContext
from src.models.trace import Tracer
from src.pipeline.pipeline import Pipeline, PipelineResult

_GREETING = (
    "Gaggia Helpdesk Policy Agent\n"
    "I evaluate requests against company security policy.\n"
    "Type your request and press Enter. Type 'quit' or press Ctrl-D to exit.\n"
)


def process_request(request: str, session: Session, context: SessionContext, pipeline: Pipeline) -> str:
    """Run one request through the pipeline and update session history.

    Args:
        request: Raw user request string.
        session: In-memory session; request appended to history after processing.
        context: Live session signals for Trust Gate classification.
        pipeline: Configured Pipeline instance.

    Returns:
        The user_message_draft from the Reasoner Decision.
    """
    tracer = Tracer()
    result: PipelineResult = pipeline.run(request, session, context, tracer)
    session.request_history.append({"request": request, "action": result.decision.action})
    return result.decision.user_message_draft


def _default_context() -> SessionContext:
    """Build a default session context for the REPL demo environment."""
    return SessionContext(
        identity="repl_user",
        sso_age_hours=1.0,
        mfa_age_hours=0.5,
        device_type="managed",
    )


def main(pipeline: Pipeline, context: SessionContext | None = None) -> None:
    """Run the interactive REPL loop.

    Args:
        pipeline: Configured Pipeline instance.
        context: Session context; defaults to a demo managed-device context.
    """
    if context is None:
        context = _default_context()

    print(_GREETING)
    session = Session()

    while True:
        try:
            request = input("> ").strip()
        except EOFError:
            print("\nGoodbye.")
            break

        if not request:
            continue
        if request.lower() == "quit":
            print("Goodbye.")
            break

        reply = process_request(request, session, context, pipeline)
        print(reply)

        summary = (
            f"[action={session.request_history[-1]['action']} "
            f"turns={len(session.request_history)}]"
        )
        print(summary, file=sys.stderr)


if __name__ == "__main__":
    from src.pipeline.trust_gate import InMemoryBlocklist
    from src.pipeline.policy_retriever import ChromaDBRetriever
    from src.tools.reset_password import reset_password
    from src.tools.lookup_employee import lookup_employee
    from src.tools.grant_file_access import grant_file_access
    from src.tools.query_hr_database import query_hr_database
    from src.tools.escalate_to_human import escalate_to_human
    import pathlib

    policy_text = pathlib.Path("gaggia_helpdesk_policy.md").read_text()
    retriever = ChromaDBRetriever.from_policy_text(policy_text)
    registry = {
        "reset_password": reset_password,
        "lookup_employee": lookup_employee,
        "grant_file_access": grant_file_access,
        "query_hr_database": query_hr_database,
        "escalate_to_human": escalate_to_human,
    }
    p = Pipeline(
        blocklist=InMemoryBlocklist(blocked=set()),
        retriever=retriever,
        registry=registry,
    )
    main(p)
