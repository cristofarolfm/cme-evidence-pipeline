"""Command-line entry point.

  python run.py fetch  --config topics/endometrial_dmmr.json      # PubMed + ClinicalTrials.gov -> evidence table
  python run.py draft  --config topics/endometrial_dmmr.json      # LLM draft (API) or prompt pack
  python run.py verify --config topics/endometrial_dmmr.json [--draft path]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import draft as drafting
from pipeline import evidence, sources, verify


def load(cfg_path: str) -> tuple[dict, Path]:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    out = Path("runs") / cfg["slug"]
    out.mkdir(parents=True, exist_ok=True)
    return cfg, out


def cmd_fetch(cfg: dict, out: Path) -> None:
    # take results round-robin across queries, so a cap on total papers never silences the last query
    per_query = [sources.search_pubmed(q, retmax=cfg.get("per_query", 15),
                                       mindate=cfg.get("mindate", ""), maxdate=cfg.get("maxdate", ""))
                 for q in cfg["pubmed_queries"]]
    pmids: list[str] = []
    for rank in range(max(map(len, per_query), default=0)):
        for ids in per_query:
            if rank < len(ids) and ids[rank] not in pmids:
                pmids.append(ids[rank])
    papers = sources.fetch_pubmed(pmids[: cfg.get("max_papers", 30)])
    papers = [p for p in papers if p.abstract]
    trials = []
    for term in cfg.get("trial_terms", []):
        for t in sources.search_trials(term, max_studies=cfg.get("max_trials", 10)):
            if t.nct not in {x.nct for x in trials}:
                trials.append(t)
    (out / "sources.json").write_text(json.dumps({"papers": sources.to_dict(papers),
                                                  "trials": sources.to_dict(trials)}, indent=1), encoding="utf-8")
    rows = evidence.evidence_rows(papers, trials)
    (out / "evidence_table.md").write_text(f"# Evidence table: {cfg['topic']}\n\n" + evidence.to_markdown(rows),
                                           encoding="utf-8")
    (out / "context.txt").write_text(evidence.to_prompt_context(papers, trials), encoding="utf-8")
    print(f"{len(papers)} papers, {len(trials)} trials -> {out}")


def _loaded(out: Path):
    data = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    papers = [sources.Paper(**p) for p in data["papers"]]
    trials = [sources.Trial(**t) for t in data["trials"]]
    return papers, trials


def cmd_draft(cfg: dict, out: Path) -> None:
    context = (out / "context.txt").read_text(encoding="utf-8")
    path = drafting.draft(cfg["topic"], cfg["audience"], context, out, model=cfg.get("model", "claude-opus-5-5"))
    if path:
        print(f"draft -> {path}")


def cmd_verify(cfg: dict, out: Path, draft_path: str | None) -> None:
    papers, trials = _loaded(out)
    src_text = {f"PMID:{p.pmid}": f"{p.title} {p.abstract}" for p in papers}
    src_text.update({f"NCT:{t.nct}": " ".join([t.title, t.phase, t.status, t.enrollment, *t.conditions,
                                              *t.interventions, *t.primary_outcomes]) for t in trials})
    urls = {f"PMID:{p.pmid}": p.url for p in papers} | {f"NCT:{t.nct}": t.url for t in trials}
    dpath = Path(draft_path) if draft_path else out / "draft.md"
    findings = verify.verify(dpath.read_text(encoding="utf-8"), src_text)
    stem = dpath.stem
    title = f"{cfg['topic']} ({dpath.name})"
    (out / f"{stem}_verification.md").write_text(verify.report_markdown(findings, title), encoding="utf-8")
    (out / f"{stem}_verification.html").write_text(verify.report_html(findings, title, urls), encoding="utf-8")
    print(json.dumps(verify.summary(findings)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["fetch", "draft", "verify"])
    ap.add_argument("--config", required=True)
    ap.add_argument("--draft")
    a = ap.parse_args()
    cfg, out = load(a.config)
    {"fetch": lambda: cmd_fetch(cfg, out), "draft": lambda: cmd_draft(cfg, out),
     "verify": lambda: cmd_verify(cfg, out, a.draft)}[a.step]()
