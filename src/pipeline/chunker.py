"""Chunker: parse policy markdown into clause-level PolicyChunk objects."""

import re
from dataclasses import dataclass, field


@dataclass
class PolicyChunk:
    """A single retrievable policy unit with a stable clause ID."""

    id: str
    text: str
    tags: list[str] = field(default_factory=list)


_SECTION_RE = re.compile(r"^### (\d+) (.+)$", re.MULTILINE)
_CLAUSE_LINE_RE = re.compile(r"^[ \t]*(\d+\.\d+(?:\.[a-z])?)\.\s+(.+)")
_TAGS_RE = re.compile(r"\*\*Tags:\*\*\s*(.+)")
_APPLIES_RE = re.compile(r"\*\*Applies to:\*\*\s*(.+)")
_RELATED_RE = re.compile(r"\*\*Related sections:\*\*\s*(.+)")


def _parse_tags(section_text: str) -> list[str]:
    m = _TAGS_RE.search(section_text)
    return [t.strip() for t in m.group(1).split(",")] if m else []


def _build_prefix(section_num: str, section_title: str, section_text: str) -> str:
    parts = [f"### {section_num} {section_title}"]
    for pattern, label in ((_TAGS_RE, "Tags"), (_APPLIES_RE, "Applies to"), (_RELATED_RE, "Related sections")):
        m = pattern.search(section_text)
        if m:
            parts.append(f"**{label}:** {m.group(1)}")
    return "\n".join(parts) + "\n\n"


def chunk_policy(policy_text: str) -> list[PolicyChunk]:
    """Parse policy markdown into clause-level chunks.

    Args:
        policy_text: Raw markdown content of the policy document.

    Returns:
        List of PolicyChunk objects, one per numbered clause (X.Y and X.Y.z level).
    """
    chunks: list[PolicyChunk] = []
    section_matches = list(_SECTION_RE.finditer(policy_text))

    for i, sec_match in enumerate(section_matches):
        section_num = sec_match.group(1)
        section_title = sec_match.group(2).strip()
        sec_start = sec_match.start()
        sec_end = section_matches[i + 1].start() if i + 1 < len(section_matches) else len(policy_text)
        section_text = policy_text[sec_start:sec_end]

        tags = _parse_tags(section_text)
        prefix = _build_prefix(section_num, section_title, section_text)

        for line in section_text.splitlines():
            m = _CLAUSE_LINE_RE.match(line)
            if not m:
                continue
            clause_id = m.group(1)
            # Only emit clauses that belong to this section
            if not clause_id.startswith(section_num + "."):
                continue
            clause_text = m.group(2).strip()
            chunks.append(PolicyChunk(id=clause_id, text=prefix + clause_text, tags=tags))

    return chunks
