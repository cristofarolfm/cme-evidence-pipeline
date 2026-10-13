"""Draft a needs-assessment section with an LLM, constrained to the retrieved sources.

Two modes:
  * API mode: if ANTHROPIC_API_KEY is set, call the Anthropic Messages API directly.
  * Prompt-pack mode (default without a key): write the full prompt to disk so it can be
    run in any chat model (Claude, GPT, DeepSeek...) and the answer saved as draft.md.
Either way, the output goes through verify.py before anyone trusts it.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

SYSTEM = """You are a medical writer at an ACCME-accredited continuing medical education provider.
Write only from the SOURCES provided. Rules:
1. Every sentence that states a fact, number or recommendation must end with one or more citations
   in square brackets using the exact source IDs given, e.g. [PMID:12345678] or [NCT:NCT01234567].
2. Never cite an ID that is not in SOURCES. If the sources do not support a statement, do not make it;
   write it under 'Evidence gaps' instead.
3. Copy numbers exactly as they appear in the cited source (hazard ratios, percentages, medians, n).
4. Fair balance: report limitations and safety alongside efficacy. No promotional language, no brand
   superlatives, independence from any commercial interest (ACCME Standards for Integrity and Independence).
"""

TASK = """TOPIC: {topic}
AUDIENCE: {audience}

Write a needs assessment for an accredited CME activity, in Markdown, with these sections:
## Background and burden
## Current evidence
## Practice gaps (state each gap as: what clinicians should do vs. what the evidence suggests happens)
## Evidence gaps
## Proposed learning objectives (3, measurable, starting with a verb)
## Assessment questions (3 multiple-choice questions, 4 options each, correct answer and a one-line
   rationale with citation)

SOURCES:
{context}
"""


def build_prompt(topic: str, audience: str, context: str) -> str:
    return TASK.format(topic=topic, audience=audience, context=context)


def call_anthropic(prompt: str, model: str = "claude-opus-5-5", max_tokens: int = 4000) -> str:
    key = os.environ["ANTHROPIC_API_KEY"]
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": max_tokens, "system": SYSTEM,
              "messages": [{"role": "user", "content": prompt}]},
        timeout=300,
    )
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def draft(topic: str, audience: str, context: str, outdir: Path, model: str = "claude-opus-5-5") -> Path | None:
    prompt = build_prompt(topic, audience, context)
    (outdir / "prompt_pack.md").write_text(f"# System\n\n{SYSTEM}\n\n# User\n\n{prompt}", encoding="utf-8")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"No ANTHROPIC_API_KEY: prompt saved to {outdir / 'prompt_pack.md'}.\n"
              f"Run it in any model and save the answer as {outdir / 'draft.md'}, then run verify.")
        return None
    text = call_anthropic(prompt, model=model)
    path = outdir / "draft.md"
    path.write_text(text, encoding="utf-8")
    return path
