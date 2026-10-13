"""Check an AI-drafted document claim by claim against the retrieved sources.

For every sentence the checker asks four questions:
  1. Does it make a factual claim without any citation?            -> UNCITED
  2. Does it cite an ID that was never retrieved?                    -> UNKNOWN_ID
     (and, for PMIDs, does that ID exist in PubMed at all?)          -> NONEXISTENT_PMID
  3. Does every number in the sentence appear in a cited source?    -> NUMBER_NOT_IN_SOURCE
  4. Do the sentence's key terms overlap with the cited source?     -> WEAK_SUPPORT
Sentences that pass all four are marked OK. Nothing here uses an LLM: the point is an
independent, reproducible check on what the LLM wrote.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import requests

CITE_RX = re.compile(r"\[((?:PMID|NCT):[^\]]+)\]")
ID_RX = re.compile(r"(PMID):\s*(\d+)|(NCT):\s*(NCT\d{8})")
NUM_RX = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?:\s?%)?")
STOP = set("""a an the and or of in for to with without by on at from as is are was were be been this that these those
which who whom than then into over under per vs versus also among across after before during between not no
may can could should would will patients patient study studies trial trials data evidence results showed""".split())

FACT_HINT = re.compile(r"\d|\b(improv|reduc|increas|prolong|associat|approv|recommend|demonstrat|show|report|"
                       r"benefit|risk|survival|response|toxicit|adverse|standard)", re.I)


@dataclass
class Finding:
    section: str
    text: str
    cites: list[str]
    status: str = "OK"
    notes: list[str] = field(default_factory=list)


def split_sentences(md: str) -> list[tuple[str, str]]:
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    section, out = "", []
    for line in md.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            section = s.lstrip("# ").strip()
            continue
        s = re.sub(r"^([-*]|\d+[.)]|[A-D][.)])\s+", "", s)
        if len(s) < 140 and not re.search(r"[.?!\]]$", s):  # sub-headings and labels such as "Gap 1: ..."
            continue
        if "question" in section.lower():  # a question, its options and its rationale are one unit
            out.append((section, s))
            continue
        for sent in re.split(r"(?<=[.\]])\s+(?=[A-Z(])", s):
            if len(sent) > 15:
                out.append((section, sent))
    return out


def parse_cites(sentence: str) -> list[str]:
    ids = []
    for block in CITE_RX.findall(sentence):
        for m in ID_RX.finditer(block):
            ids.append(f"PMID:{m.group(2)}" if m.group(1) else f"NCT:{m.group(4)}")
    return ids


UNITS = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                    "fourteen fifteen sixteen seventeen eighteen nineteen".split())}
TENS = {w: 10 * i for i, w in enumerate("_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()) if w != "_"}


def spelled_numbers(text: str) -> list[str]:
    """'Seven hundred eighteen patients' -> ['718'] (abstracts often spell out numbers at sentence start)."""
    out, cur, seen = [], 0, False
    for tok in re.findall(r"[a-z]+", text.lower()) + ["."]:
        if tok in UNITS:
            cur += UNITS[tok]; seen = True
        elif tok in TENS:
            cur += TENS[tok]; seen = True
        elif tok == "hundred" and seen:
            cur *= 100
        elif tok == "thousand" and seen:
            cur *= 1000
        elif tok == "and" and seen:
            continue
        else:
            if seen and cur >= 10:
                out.append(str(cur))
            cur, seen = 0, False
    return out


def numbers(text: str) -> set[str]:
    nums = set()
    clean = CITE_RX.sub(" ", text)
    for m in NUM_RX.finditer(clean):
        n = m.group(1)
        if re.fullmatch(r"(19|20)\d\d", n):  # years
            continue
        if "." not in n and int(n) < 10:     # small counts ("3 trials") are too noisy to check
            continue
        nums.add(n.rstrip("0").rstrip(".") if "." in n else n)
    return nums


def content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z][a-z0-9-]{3,}", CITE_RX.sub(" ", text).lower())
    return {w for w in words if w not in STOP}


def pubmed_title(pmid: str) -> str | None:
    """Title of a PMID, or None if PubMed has no such record."""
    r = requests.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                     params={"db": "pubmed", "id": pmid, "retmode": "json"}, timeout=30)
    rec = r.json().get("result", {}).get(pmid, {})
    if not rec or "error" in rec:
        return None
    return rec.get("title", "")


def verify(md: str, sources: dict[str, str], check_pubmed: bool = True) -> list[Finding]:
    """sources maps 'PMID:123' / 'NCT:NCT0...' to the text the claim must be supported by."""
    norm_sources = {k: v.replace("·", ".") for k, v in sources.items()}
    source_nums = {k: numbers(v) | set(spelled_numbers(v)) for k, v in norm_sources.items()}
    findings = []
    title_cache: dict[str, str | None] = {}
    for section, sent in split_sentences(md):
        cites = parse_cites(sent)
        f = Finding(section, sent, cites)
        is_objective = "objective" in section.lower()
        if not cites:
            if FACT_HINT.search(sent) and not is_objective and not sent.rstrip().endswith("?"):
                f.status = "UNCITED"
                f.notes.append("factual statement without a source")
            findings.append(f)
            continue
        unknown = [c for c in cites if c not in norm_sources]
        for c in unknown:
            extra = ""
            if c.startswith("PMID:") and check_pubmed:
                pid = c.split(":")[1]
                if pid not in title_cache:
                    title_cache[pid] = pubmed_title(pid)
                if title_cache[pid] is None:
                    f.status = "NONEXISTENT_PMID"
                    f.notes.append(f"{c} does not exist in PubMed")
                    continue
                extra = f' (it exists, but it is: "{title_cache[pid][:120]}")'
            if f.status == "OK":
                f.status = "UNKNOWN_ID"
            f.notes.append(f"{c} was not in the retrieved evidence set{extra}")
        known = [c for c in cites if c in norm_sources]
        if known:
            pool = set().union(*(source_nums[c] for c in known))
            # in multiple-choice items the wrong options are wrong on purpose: check only the rationale
            checked = sent.split("Rationale", 1)[1] if "question" in section.lower() and "Rationale" in sent else sent
            missing = sorted(numbers(checked) - pool)
            if missing:
                if f.status == "OK":
                    f.status = "NUMBER_NOT_IN_SOURCE"
                f.notes.append("not found in cited source(s): " + ", ".join(missing))
            words = content_words(sent)
            src_words = set().union(*(content_words(norm_sources[c]) for c in known))
            overlap = len(words & src_words) / max(len(words), 1)
            if overlap < 0.35 and f.status == "OK":
                f.status = "WEAK_SUPPORT"
                f.notes.append(f"only {overlap:.0%} of key terms appear in the cited source")
        findings.append(f)
    return findings


SEVERITY = ["NONEXISTENT_PMID", "UNKNOWN_ID", "NUMBER_NOT_IN_SOURCE", "UNCITED", "WEAK_SUPPORT", "OK"]
COLORS = {"OK": "#e7f6ec", "WEAK_SUPPORT": "#fff7d6", "UNCITED": "#fdebd3",
          "NUMBER_NOT_IN_SOURCE": "#fde0dc", "UNKNOWN_ID": "#fbd0d0", "NONEXISTENT_PMID": "#f6b5b5"}


def summary(findings: list[Finding]) -> dict[str, int]:
    return {s: sum(1 for f in findings if f.status == s) for s in SEVERITY}


def report_markdown(findings: list[Finding], title: str) -> str:
    s = summary(findings)
    lines = [f"# Verification report: {title}", "",
             "| Status | Sentences |", "|---|---|"] + [f"| {k} | {v} |" for k, v in s.items()] + [""]
    lines += ["## Flagged sentences", ""]
    for f in sorted(findings, key=lambda x: SEVERITY.index(x.status)):
        if f.status == "OK":
            continue
        lines.append(f"- **{f.status}** ({f.section}): {f.text}\n  - {'; '.join(f.notes)}")
    return "\n".join(lines)


def report_html(findings: list[Finding], title: str, sources_url: dict[str, str]) -> str:
    s = summary(findings)
    def link(c):
        return f'<a href="{sources_url.get(c, "#")}">{c}</a>' if c in sources_url else f"<b>{c}</b>"
    rows = "".join(
        f'<tr style="background:{COLORS[f.status]}"><td>{html.escape(f.section)}</td>'
        f"<td>{html.escape(CITE_RX.sub('', f.text)).strip()}</td><td>{' '.join(link(c) for c in f.cites)}</td>"
        f"<td><b>{f.status}</b><br>{html.escape('; '.join(f.notes))}</td></tr>"
        for f in findings)
    chips = " ".join(f'<span style="background:{COLORS[k]};padding:2px 8px;border-radius:8px">{k}: {v}</span>'
                     for k, v in s.items())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,Arial;margin:24px;max-width:1200px}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ddd;padding:6px;vertical-align:top;font-size:13px}}th{{background:#1f3a5f;color:#fff}}</style>
</head><body><h1>{html.escape(title)}</h1><p>{chips}</p>
<table><tr><th>Section</th><th>Sentence</th><th>Cited</th><th>Check</th></tr>{rows}</table></body></html>"""
