"""LLM-as-judge: scores Reasoner Decisions against policy for evaluation coverage."""


def score(decision, policy_chunks: list, tracer) -> dict:
    raise NotImplementedError
