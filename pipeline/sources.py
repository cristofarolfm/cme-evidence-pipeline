"""Retrieve primary evidence from PubMed (NCBI E-utilities) and ClinicalTrials.gov (API v2).

Everything downstream is anchored to the records fetched here: a claim can only be
"verified" if it cites a PMID or NCT ID that this module actually retrieved.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
CTGOV = "https://clinicaltrials.gov/api/v2/studies"
HEADERS = {"User-Agent": "cme-evidence-pipeline/0.1 (research use)"}


@dataclass
class Paper:
    pmid: str
    title: str
    journal: str
    year: str
    authors: str
    pub_types: list[str]
    abstract: str
    doi: str = ""

    @property
    def url(self) -> str:
        return f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    @property
    def citation(self) -> str:
        doi = f" doi:{self.doi}" if self.doi else ""
        return f"{self.authors}. {self.title} {self.journal}. {self.year}.{doi} PMID: {self.pmid}"


@dataclass
class Trial:
    nct: str
    title: str
    phase: str
    status: str
    enrollment: str
    conditions: list[str] = field(default_factory=list)
    interventions: list[str] = field(default_factory=list)
    primary_outcomes: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"https://clinicaltrials.gov/study/{self.nct}"


def _get(url: str, params: dict) -> requests.Response:
    for attempt in range(3):
        r = requests.get(url, params=params, headers=HEADERS, timeout=30)
        if r.status_code == 429:  # NCBI rate limit without an API key: 3 requests/s
            time.sleep(1 + attempt)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def search_pubmed(query: str, retmax: int = 40, mindate: str = "", maxdate: str = "") -> list[str]:
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": retmax, "sort": "relevance"}
    if mindate:
        params.update(datetype="pdat", mindate=mindate, maxdate=maxdate or "3000")
    return _get(f"{EUTILS}/esearch.fcgi", params).json()["esearchresult"]["idlist"]


def fetch_pubmed(pmids: list[str]) -> list[Paper]:
    if not pmids:
        return []
    xml = _get(f"{EUTILS}/efetch.fcgi", {"db": "pubmed", "id": ",".join(pmids), "retmode": "xml"}).text
    papers = []
    for art in ET.fromstring(xml).iter("PubmedArticle"):
        cit = art.find("MedlineCitation")
        a = cit.find("Article")
        abstract = " ".join(
            ((t.get("Label") + ": ") if t.get("Label") else "") + "".join(t.itertext())
            for t in a.findall("Abstract/AbstractText")
        )
        names = []
        for au in a.findall("AuthorList/Author")[:3]:
            last, ini = au.findtext("LastName"), au.findtext("Initials")
            if last:
                names.append(f"{last} {ini or ''}".strip())
        if len(a.findall("AuthorList/Author")) > 3:
            names.append("et al")
        year = a.findtext("Journal/JournalIssue/PubDate/Year") or (
            a.findtext("Journal/JournalIssue/PubDate/MedlineDate") or ""
        )[:4]
        doi = next((e.text for e in art.findall("PubmedData/ArticleIdList/ArticleId") if e.get("IdType") == "doi"), "")
        papers.append(Paper(
            pmid=cit.findtext("PMID"),
            title="".join(a.find("ArticleTitle").itertext()).strip(),
            journal=a.findtext("Journal/ISOAbbreviation") or a.findtext("Journal/Title") or "",
            year=year,
            authors=", ".join(names),
            pub_types=[p.text for p in a.findall("PublicationTypeList/PublicationType")],
            abstract=abstract.strip(),
            doi=doi or "",
        ))
    return papers


def search_trials(term: str, max_studies: int = 20) -> list[Trial]:
    fields = ("NCTId,BriefTitle,Phase,OverallStatus,EnrollmentCount,Condition,"
              "InterventionName,PrimaryOutcomeMeasure")
    data = _get(CTGOV, {"query.term": term, "pageSize": max_studies, "fields": fields}).json()
    trials = []
    for s in data.get("studies", []):
        p = s.get("protocolSection", {})
        ident, status = p.get("identificationModule", {}), p.get("statusModule", {})
        design = p.get("designModule", {})
        trials.append(Trial(
            nct=ident.get("nctId", ""),
            title=ident.get("briefTitle", ""),
            phase=", ".join(design.get("phases", []) or ["NA"]),
            status=status.get("overallStatus", ""),
            enrollment=str(design.get("enrollmentInfo", {}).get("count", "")),
            conditions=p.get("conditionsModule", {}).get("conditions", []),
            interventions=[i.get("name", "") for i in p.get("armsInterventionsModule", {}).get("interventions", [])],
            primary_outcomes=[o.get("measure", "") for o in p.get("outcomesModule", {}).get("primaryOutcomes", [])],
        ))
    return trials


def to_dict(items) -> list[dict]:
    return [asdict(i) for i in items]
