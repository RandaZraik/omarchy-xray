from __future__ import annotations


def explanation(
    *,
    identifier: str,
    tone: str,
    title: str,
    why: str,
    evidence: list[str],
    next_step: str,
    domain: str,
    evidence_count: int | None = None,
    status: str = "Found",
) -> dict[str, object]:
    return {
        "id": identifier,
        "tone": tone,
        "status": status,
        "title": title,
        "why": why,
        "evidence": evidence,
        "evidenceCount": evidence_count
        if evidence_count is not None
        else len(evidence),
        "nextStep": next_step,
        "domain": domain,
    }
