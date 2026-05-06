from __future__ import annotations

import csv
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from pebench.utils.io import ensure_dir


OPENALEX_BASE = "https://api.openalex.org/works"
CROSSREF_BASE = "https://api.crossref.org/works"
ARXIV_BASE = "https://export.arxiv.org/api/query"

DEFAULT_QUERY_TERMS = [
    "flyback converter design",
    "isolated flyback converter",
    "active clamp flyback",
    "quasi-resonant flyback converter",
    "offline flyback converter",
    "primary-side regulated flyback",
    "synchronous rectified flyback",
    "planar flyback converter",
    "flyback transformer design",
    "multi-output flyback converter",
    "boundary conduction mode flyback",
    "discontinuous conduction mode flyback",
    "high efficiency flyback converter",
    "GaN flyback converter",
]

POSITIVE_TERMS = {
    "flyback": 18.0,
    "converter": 12.0,
    "design": 10.0,
    "power supply": 6.0,
    "isolated": 5.0,
    "ac-dc": 4.0,
    "dc-dc": 4.0,
    "transformer": 5.0,
    "magnetizing": 5.0,
    "turns ratio": 5.0,
    "switching frequency": 4.0,
    "efficiency": 5.0,
    "ripple": 5.0,
    "mosfet": 4.0,
    "diode": 4.0,
    "snubber": 3.0,
    "active clamp": 4.0,
    "quasi-resonant": 4.0,
    "primary-side": 3.0,
}

EXCLUSION_TERMS = {
    "cathode ray": 20.0,
    "television": 18.0,
    "display": 12.0,
    "x-ray": 12.0,
    "flash lamp": 12.0,
    "ignition": 10.0,
    "deflection": 10.0,
    "electrostatic precipitator": 10.0,
}

NUMERIC_SIGNAL_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:v|a|w|khz|mhz|%|mv|uv|ma)\b", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(slots=True)
class HarvestConfig:
    query_terms: list[str]
    openalex_max_records: int = 1500
    crossref_max_records: int = 1200
    arxiv_max_records: int = 300
    year_from: int = 1990
    polite_email: str | None = None
    sleep_seconds: float = 0.15


@dataclass(slots=True)
class HarvestResult:
    raw_records: list[dict[str, Any]]
    merged_records: list[dict[str, Any]]
    high_quality_records: list[dict[str, Any]]
    benchmark_seed_records: list[dict[str, Any]]
    summary: dict[str, Any]


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", html.unescape(value)).strip()


def _strip_tags(value: str | None) -> str:
    return _normalize_text(TAG_RE.sub(" ", value or ""))


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    cleaned = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip().lower()
    return cleaned or None


def normalize_title(value: str | None) -> str:
    text = _normalize_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def _decode_openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    if not inverted_index:
        return ""
    positions: dict[int, str] = {}
    for token, indexes in inverted_index.items():
        for index in indexes:
            positions[index] = token
    return " ".join(token for _, token in sorted(positions.items()))


def _fetch_json(url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def _fetch_xml(url: str, *, headers: dict[str, str] | None = None) -> ET.Element:
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=60) as response:
        return ET.fromstring(response.read())


def _fetch_xml_with_backoff(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retries: int = 4,
    initial_backoff: float = 3.5,
) -> ET.Element:
    backoff = initial_backoff
    for attempt in range(retries):
        try:
            return _fetch_xml(url, headers=headers)
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.7
                continue
            raise
        except URLError:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.7
                continue
            raise


def _crossref_headers(email: str | None) -> dict[str, str]:
    user_agent = "PEBenchLiteratureHarvester/0.1"
    if email:
        user_agent += f" (mailto:{email})"
    return {"User-Agent": user_agent}


def _openalex_headers(email: str | None) -> dict[str, str]:
    if not email:
        return {}
    return {"User-Agent": f"PEBenchLiteratureHarvester/0.1 (mailto:{email})"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _openalex_record(item: dict[str, Any], query: str) -> dict[str, Any]:
    location = item.get("best_oa_location") or {}
    primary_location = item.get("primary_location") or {}
    title = _normalize_text(item.get("display_name"))
    abstract = _normalize_text(_decode_openalex_abstract(item.get("abstract_inverted_index")))
    doi = normalize_doi(item.get("doi"))
    source = ((primary_location.get("source") or {}).get("display_name")) or ""
    return {
        "source_db": "openalex",
        "source_id": item.get("id"),
        "query": query,
        "title": title,
        "abstract": abstract,
        "doi": doi,
        "year": item.get("publication_year"),
        "venue": _normalize_text(source),
        "source_type": item.get("type"),
        "authors": [
            _normalize_text((authorship.get("author") or {}).get("display_name"))
            for authorship in item.get("authorships", [])
            if _normalize_text((authorship.get("author") or {}).get("display_name"))
        ],
        "citation_count": int(item.get("cited_by_count") or 0),
        "is_open_access": bool((item.get("open_access") or {}).get("is_oa")),
        "landing_page_url": location.get("landing_page_url") or item.get("id"),
        "pdf_url": location.get("pdf_url"),
        "fulltext_origin": location.get("source") or "",
        "raw": item,
    }


def _crossref_record(item: dict[str, Any], query: str) -> dict[str, Any]:
    title_list = item.get("title") or [""]
    abstract = _strip_tags(item.get("abstract"))
    authors = []
    for author in item.get("author", []):
        given = _normalize_text(author.get("given"))
        family = _normalize_text(author.get("family"))
        full = " ".join(part for part in [given, family] if part)
        if full:
            authors.append(full)
    container = item.get("container-title") or [""]
    published = (
        item.get("published-print")
        or item.get("published-online")
        or item.get("created")
        or {}
    )
    date_parts = published.get("date-parts") or [[None]]
    year = date_parts[0][0]
    link = item.get("link") or []
    pdf_url = None
    for entry in link:
        if str(entry.get("content-type", "")).lower() == "application/pdf":
            pdf_url = entry.get("URL")
            break
    doi = normalize_doi(item.get("DOI"))
    return {
        "source_db": "crossref",
        "source_id": doi or item.get("URL"),
        "query": query,
        "title": _normalize_text(title_list[0] if title_list else ""),
        "abstract": abstract,
        "doi": doi,
        "year": year,
        "venue": _normalize_text(container[0] if container else ""),
        "source_type": item.get("type"),
        "authors": authors,
        "citation_count": int(item.get("is-referenced-by-count") or 0),
        "is_open_access": bool(pdf_url),
        "landing_page_url": item.get("URL"),
        "pdf_url": pdf_url,
        "fulltext_origin": "crossref_link" if pdf_url else "",
        "raw": item,
    }


def _arxiv_record(entry: ET.Element, query: str) -> dict[str, Any]:
    ns = {"a": "http://www.w3.org/2005/Atom"}
    title = _normalize_text(entry.findtext("a:title", default="", namespaces=ns))
    abstract = _normalize_text(entry.findtext("a:summary", default="", namespaces=ns))
    authors = [
        _normalize_text(node.findtext("a:name", default="", namespaces=ns))
        for node in entry.findall("a:author", ns)
    ]
    pdf_url = None
    landing_page_url = entry.findtext("a:id", default="", namespaces=ns)
    for link in entry.findall("a:link", ns):
        if link.attrib.get("title") == "pdf":
            pdf_url = link.attrib.get("href")
            break
    published = entry.findtext("a:published", default="", namespaces=ns)
    year = int(published[:4]) if published[:4].isdigit() else None
    return {
        "source_db": "arxiv",
        "source_id": landing_page_url,
        "query": query,
        "title": title,
        "abstract": abstract,
        "doi": None,
        "year": year,
        "venue": "arXiv",
        "source_type": "preprint",
        "authors": [author for author in authors if author],
        "citation_count": 0,
        "is_open_access": True,
        "landing_page_url": landing_page_url,
        "pdf_url": pdf_url,
        "fulltext_origin": "arxiv_pdf" if pdf_url else "",
        "raw": {"entry_id": landing_page_url},
    }


def _base_quality_features(record: dict[str, Any]) -> dict[str, Any]:
    title = normalize_title(record.get("title"))
    abstract = _normalize_text(record.get("abstract")).lower()
    combined = " ".join(part for part in [title, abstract] if part).strip()

    positive_hits = [term for term in POSITIVE_TERMS if term in combined]
    exclusion_hits = [term for term in EXCLUSION_TERMS if term in combined]
    numeric_signals = NUMERIC_SIGNAL_RE.findall(combined)

    score = 0.0
    for term in positive_hits:
        score += POSITIVE_TERMS[term]
    for term in exclusion_hits:
        score -= EXCLUSION_TERMS[term]

    citations = int(record.get("citation_count") or 0)
    score += min(15.0, math.log1p(max(0, citations)) * 3.0)
    if record.get("is_open_access"):
        score += 5.0
    if record.get("pdf_url"):
        score += 4.0
    if abstract:
        score += 6.0
    if record.get("doi"):
        score += 2.0
    if numeric_signals:
        score += min(14.0, len(numeric_signals) * 2.0)

    year = record.get("year")
    if isinstance(year, int):
        if year >= 2020:
            score += 4.0
        elif year >= 2010:
            score += 2.0

    venue = _normalize_text(record.get("venue")).lower()
    if any(token in venue for token in ["ieee", "transactions", "journal", "conference"]):
        score += 6.0

    readiness = "low"
    if abstract and record.get("pdf_url") and len(numeric_signals) >= 2:
        readiness = "high"
    elif abstract and len(numeric_signals) >= 1:
        readiness = "medium"

    quality_bucket = "low"
    if score >= 60.0:
        quality_bucket = "high"
    elif score >= 38.0:
        quality_bucket = "medium"

    design_relevant = "flyback" in combined and not exclusion_hits and (
        "converter" in combined or "power supply" in combined or "transformer" in combined
    )

    return {
        "quality_score": round(max(0.0, min(100.0, score)), 2),
        "quality_bucket": quality_bucket,
        "task_readiness": readiness,
        "positive_term_hits": positive_hits,
        "exclusion_term_hits": exclusion_hits,
        "numeric_signal_count": len(numeric_signals),
        "design_relevant": design_relevant,
    }


def _merge_key(record: dict[str, Any]) -> str:
    doi = normalize_doi(record.get("doi"))
    if doi:
        return f"doi:{doi}"
    return f"title:{normalize_title(record.get('title'))}"


def _is_strict_flyback_seed(record: dict[str, Any]) -> bool:
    title = normalize_title(record.get("title"))
    return "flyback" in title and any(
        token in title for token in ["converter", "power supply", "transformer", "dc dc", "ac dc", "design"]
    )


def _merge_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        key = _merge_key(record)
        current = merged.get(key)
        if current is None:
            enriched = dict(record)
            enriched["query_terms"] = [record["query"]]
            merged[key] = enriched
            continue

        current["query_terms"] = sorted(set(current.get("query_terms", [])) | {record["query"]})
        if not current.get("abstract") and record.get("abstract"):
            current["abstract"] = record["abstract"]
        if not current.get("pdf_url") and record.get("pdf_url"):
            current["pdf_url"] = record["pdf_url"]
        if not current.get("doi") and record.get("doi"):
            current["doi"] = record["doi"]
        if not current.get("venue") and record.get("venue"):
            current["venue"] = record["venue"]
        if not current.get("landing_page_url") and record.get("landing_page_url"):
            current["landing_page_url"] = record["landing_page_url"]
        if record.get("citation_count", 0) > current.get("citation_count", 0):
            current["citation_count"] = record["citation_count"]
        current["is_open_access"] = bool(current.get("is_open_access") or record.get("is_open_access"))
        current["authors"] = sorted(set(current.get("authors", [])) | set(record.get("authors", [])))
        current["source_db"] = ",".join(sorted(set(str(current.get("source_db", "")).split(",")) | {record["source_db"]}))
    merged_records = list(merged.values())
    for record in merged_records:
        record.update(_base_quality_features(record))
    merged_records.sort(
        key=lambda item: (
            -float(item.get("quality_score", 0.0)),
            -int(item.get("citation_count", 0)),
            normalize_title(item.get("title")),
        )
    )
    return merged_records


def query_openalex(config: HarvestConfig) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    headers = _openalex_headers(config.polite_email)
    for query in config.query_terms:
        print(f"[openalex] query={query}")
        cursor = "*"
        per_page = 200
        collected = 0
        while collected < config.openalex_max_records:
            params = {
                "search": query,
                "cursor": cursor,
                "per-page": per_page,
                "filter": f"from_publication_date:{config.year_from}-01-01",
            }
            if config.polite_email:
                params["mailto"] = config.polite_email
            url = f"{OPENALEX_BASE}?{urllib.parse.urlencode(params)}"
            payload = _fetch_json(url, headers=headers)
            batch = payload.get("results", [])
            if not batch:
                break
            remaining = max(0, config.openalex_max_records - collected)
            for item in batch[:remaining]:
                results.append(_openalex_record(item, query))
            collected += min(len(batch), remaining)
            print(f"[openalex] query={query} collected={collected}")
            cursor = (payload.get("meta") or {}).get("next_cursor")
            if not cursor:
                break
            time.sleep(config.sleep_seconds)
    return results


def query_crossref(config: HarvestConfig) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    headers = _crossref_headers(config.polite_email)
    rows = 100
    for query in config.query_terms:
        print(f"[crossref] query={query}")
        cursor = "*"
        collected = 0
        while collected < config.crossref_max_records:
            params = {
                "query.bibliographic": query,
                "rows": rows,
                "cursor": cursor,
                "filter": f"from-pub-date:{config.year_from}-01-01",
            }
            url = f"{CROSSREF_BASE}?{urllib.parse.urlencode(params)}"
            payload = _fetch_json(url, headers=headers)
            items = (payload.get("message") or {}).get("items", [])
            if not items:
                break
            remaining = max(0, config.crossref_max_records - collected)
            for item in items[:remaining]:
                results.append(_crossref_record(item, query))
            collected += min(len(items), remaining)
            print(f"[crossref] query={query} collected={collected}")
            next_cursor = (payload.get("message") or {}).get("next-cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            time.sleep(config.sleep_seconds)
    return results


def query_arxiv(config: HarvestConfig) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    page_size = 100
    headers = {"User-Agent": "PEBenchLiteratureHarvester/0.1"}
    for query in config.query_terms:
        print(f"[arxiv] query={query}")
        start = 0
        while start < config.arxiv_max_records:
            params = {
                "search_query": f"all:{query}",
                "start": start,
                "max_results": page_size,
            }
            url = f"{ARXIV_BASE}?{urllib.parse.urlencode(params)}"
            root = _fetch_xml_with_backoff(url, headers=headers)
            entries = root.findall("a:entry", ns)
            if not entries:
                break
            remaining = max(0, config.arxiv_max_records - start)
            for entry in entries[:remaining]:
                results.append(_arxiv_record(entry, query))
            start += min(len(entries), remaining)
            print(f"[arxiv] query={query} collected={start}")
            time.sleep(max(config.sleep_seconds, 3.1))
    return results


def harvest_sources(config: HarvestConfig) -> HarvestResult:
    raw_records: list[dict[str, Any]] = []
    raw_records.extend(query_openalex(config))
    raw_records.extend(query_crossref(config))
    raw_records.extend(query_arxiv(config))
    merged_records = _merge_records(raw_records)
    high_quality_records = [
        record
        for record in merged_records
        if record["design_relevant"] and record["quality_bucket"] == "high"
    ]
    benchmark_seed_records = [
        record
        for record in high_quality_records
        if record["task_readiness"] in {"high", "medium"} and _is_strict_flyback_seed(record)
    ]
    summary = {
        "query_terms": config.query_terms,
        "source_counts_raw": {
            "openalex": sum(1 for record in raw_records if record["source_db"] == "openalex"),
            "crossref": sum(1 for record in raw_records if record["source_db"] == "crossref"),
            "arxiv": sum(1 for record in raw_records if record["source_db"] == "arxiv"),
        },
        "raw_record_count": len(raw_records),
        "merged_record_count": len(merged_records),
        "high_quality_count": len(high_quality_records),
        "benchmark_seed_count": len(benchmark_seed_records),
        "quality_bucket_counts": {
            bucket: sum(1 for record in merged_records if record["quality_bucket"] == bucket)
            for bucket in ["high", "medium", "low"]
        },
        "task_readiness_counts": {
            bucket: sum(1 for record in merged_records if record["task_readiness"] == bucket)
            for bucket in ["high", "medium", "low"]
        },
    }
    return HarvestResult(
        raw_records=raw_records,
        merged_records=merged_records,
        high_quality_records=high_quality_records,
        benchmark_seed_records=benchmark_seed_records,
        summary=summary,
    )


def _write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False))
            handle.write("\n")


def _csv_row(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": record.get("title"),
        "doi": record.get("doi"),
        "year": record.get("year"),
        "venue": record.get("venue"),
        "source_db": record.get("source_db"),
        "citation_count": record.get("citation_count"),
        "quality_score": record.get("quality_score"),
        "quality_bucket": record.get("quality_bucket"),
        "task_readiness": record.get("task_readiness"),
        "is_open_access": record.get("is_open_access"),
        "pdf_url": record.get("pdf_url"),
        "landing_page_url": record.get("landing_page_url"),
        "query_terms": "; ".join(record.get("query_terms", [])),
        "positive_term_hits": "; ".join(record.get("positive_term_hits", [])),
        "numeric_signal_count": record.get("numeric_signal_count"),
    }


def write_harvest_outputs(result: HarvestResult, output_root: str | Path) -> dict[str, Path]:
    output_dir = ensure_dir(output_root)
    raw_dir = ensure_dir(output_dir / "raw")
    merged_dir = ensure_dir(output_dir / "curated")

    _write_jsonl(result.raw_records, raw_dir / "raw_records.jsonl")
    _write_jsonl(result.merged_records, merged_dir / "merged_records.jsonl")
    _write_jsonl(result.high_quality_records, merged_dir / "high_quality_records.jsonl")
    _write_jsonl(result.benchmark_seed_records, merged_dir / "benchmark_seed_candidates.jsonl")

    csv_targets = {
        "merged_records.csv": result.merged_records,
        "high_quality_records.csv": result.high_quality_records,
        "benchmark_seed_candidates.csv": result.benchmark_seed_records,
    }
    fieldnames = list(_csv_row(result.merged_records[0]).keys()) if result.merged_records else [
        "title",
        "doi",
        "year",
        "venue",
        "source_db",
        "citation_count",
        "quality_score",
        "quality_bucket",
        "task_readiness",
        "is_open_access",
        "pdf_url",
        "landing_page_url",
        "query_terms",
        "positive_term_hits",
        "numeric_signal_count",
    ]
    for filename, records in csv_targets.items():
        with (merged_dir / filename).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                writer.writerow(_csv_row(record))

    with (output_dir / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(result.summary, handle, indent=2, sort_keys=True)

    return {
        "output_dir": output_dir,
        "summary": output_dir / "summary.json",
        "merged_jsonl": merged_dir / "merged_records.jsonl",
        "high_quality_jsonl": merged_dir / "high_quality_records.jsonl",
        "benchmark_seed_jsonl": merged_dir / "benchmark_seed_candidates.jsonl",
        "merged_csv": merged_dir / "merged_records.csv",
        "high_quality_csv": merged_dir / "high_quality_records.csv",
        "benchmark_seed_csv": merged_dir / "benchmark_seed_candidates.csv",
    }
