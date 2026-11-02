"""Text utilities shared by retrieval, the mock generator and deterministic evaluation metrics."""

import re
from collections import Counter

from app.ai.providers.mock import _stem, tokenize

_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def terms(text: str) -> list[str]:
    return [_stem(t) for t in tokenize(text)]


def sentences(text: str) -> list[str]:
    out = []
    for block in re.split(r"\n\s*\n|\n(?=[-*•]\s)", text):
        block = " ".join(block.split())
        if not block:
            continue
        out.extend(s.strip() for s in _SENT.split(block) if len(s.strip()) > 3)
    return out


def coverage(query: str, text: str) -> float:
    q = set(terms(query))
    if not q:
        return 0.0
    return len(q & set(terms(text))) / len(q)


def token_f1(pred: str, ref: str, recall_only: bool = False) -> float:
    p, r = Counter(terms(pred)), Counter(terms(ref))
    if not p or not r:
        return 0.0
    common = sum((p & r).values())
    if common == 0:
        return 0.0
    precision, recall = common / sum(p.values()), common / sum(r.values())
    if recall_only:
        return min(1.0, common / sum(p.values()))
    return 2 * precision * recall / (precision + recall)


def support_ratio(answer: str, context: str, threshold: float = 0.6) -> float:
    """Share of answer sentences whose content terms are mostly present in the context (faithfulness proxy)."""
    ctx = set(terms(context))
    sents = [s for s in sentences(re.sub(r"\[\d+\]", "", answer)) if terms(s)]
    if not sents:
        return 0.0
    supported = sum(1 for s in sents if len(set(terms(s)) & ctx) / len(set(terms(s))) >= threshold)
    return supported / len(sents)
