"""Turn retrieved records into a source-linked evidence table.

The table is deliberately simple and deterministic (regular expressions, no LLM), so a
reviewer can see exactly where every extracted number came from.
"""
from __future__ import annotations

import re

from .sources import Paper, Trial

DESIGN_RULES = [
    ("Phase 3 RCT", r"phase (3|iii)\b.*random|random\w*.*phase (3|iii)\b"),
    ("Phase 2", r"phase (2|ii)\b"),
    ("Meta-analysis", r"meta-analys"),
    ("Systematic review", r"systematic review"),
    ("RCT", r"randomi[sz]ed"),
    ("Real-world / cohort", r"real-world|retrospective|cohort|registry|seer|national cancer database"),
    ("Review", r"\breview\b"),
    ("Guideline / consensus", r"guideline|consensus|recommendation"),
]

NUM_PATTERNS = {
    "HR": r"\bHR\b[^0-9]{0,15}(0?\.\d+|\d\.\d+)",
    "n": r"\b(?:n\s*=\s*|enrolled\s+|included\s+|randomi[sz]ed\s+)(\d{2,5})\b",
    "median": r"median[^.;]{0,60}?(\d+(?:\.\d+)?)\s*(?:months|mo)\b",
    "%": r"(\d+(?:\.\d+)?)\s?%(?!\s*(?:CI|confidence))",
}


def classify_design(p: Paper) -> str:
    pt = " ".join(p.pub_types).lower()
    if "meta-analysis" in pt:
        return "Meta-analysis"
    if "randomized controlled trial" in pt and re.search(r"phase (3|iii)", p.abstract.lower()):
        return "Phase 3 RCT"
    if "practice guideline" in pt or "guideline" in pt:
        return "Guideline / consensus"
    text = (p.title + " " + p.abstract).lower()
    for label, rx in DESIGN_RULES:
        if re.search(rx, text):
            return label
    return "Other"


def key_numbers(text: str, limit: int = 6) -> str:
    found = []
    for label, rx in NUM_PATTERNS.items():
        for m in re.finditer(rx, text, flags=re.I):
            found.append(f"{label} {m.group(1)}")
            if len(found) >= limit:
                return "; ".join(found)
    return "; ".join(found)


def evidence_rows(papers: list[Paper], trials: list[Trial]) -> list[dict]:
    rows = []
    for p in papers:
        rows.append({
            "id": f"PMID:{p.pmid}",
            "url": p.url,
            "year": p.year,
            "design": classify_design(p),
            "source": f"{p.authors} - {p.journal}",
            "title": p.title,
            "key_numbers": key_numbers(p.abstract),
        })
    for t in trials:
        rows.append({
            "id": f"NCT:{t.nct}",
            "url": t.url,
            "year": "",
            "design": f"Registered trial ({t.phase}, {t.status})",
            "source": f"n={t.enrollment}; {', '.join(t.interventions[:3])}",
            "title": t.title,
            "key_numbers": "; ".join(t.primary_outcomes[:2]),
        })
    return rows


def to_markdown(rows: list[dict]) -> str:
    out = ["| ID | Year | Design | Title | Key numbers (from abstract/registry) |",
           "|---|---|---|---|---|"]
    for r in rows:
        title = r["title"].replace("|", "/")[:140]
        out.append(f"| [{r['id']}]({r['url']}) | {r['year']} | {r['design']} | {title} | {r['key_numbers'].replace('|', '/')} |")
    return "\n".join(out)


def to_prompt_context(papers: list[Paper], trials: list[Trial], max_chars: int = 1800) -> str:
    """Compact, citable context for the drafting model: one block per source, ID first."""
    blocks = []
    for p in papers:
        blocks.append(f"[PMID:{p.pmid}] {p.title} ({p.journal}, {p.year}; {classify_design(p)})\n"
                      f"{p.abstract[:max_chars]}")
    for t in trials:
        blocks.append(f"[NCT:{t.nct}] {t.title} | phase {t.phase} | {t.status} | enrollment {t.enrollment} | "
                      f"interventions: {', '.join(t.interventions)} | primary outcomes: {'; '.join(t.primary_outcomes)}")
    return "\n\n".join(blocks)
