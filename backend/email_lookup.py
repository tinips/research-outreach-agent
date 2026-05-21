import html
import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import Candidate


LOGGER = logging.getLogger(__name__)
SERPAPI_URL = "https://serpapi.com/search.json"
USER_AGENT = "ResearchOutreachAgent/1.0 (+public email lookup; no email sending)"
SEARCH_TIMEOUT_SECONDS = 8
FETCH_TIMEOUT_SECONDS = 5
MAX_FETCH_BYTES = 200_000
MAX_CANDIDATES_PER_RUN = 6
EMAIL_NOT_FOUND_NOTE = "Email not found — verify manually or use LinkedIn."

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
MAILTO_PATTERN = re.compile(r"mailto:([^\"'?#\s>]+)", re.IGNORECASE)
OBFUSCATED_EMAIL_PATTERN = re.compile(
    r"\b([A-Za-z0-9._%+-]+)\s*(?:@|\(at\)|\[at\]|\{at\}|\sat\s)\s*"
    r"([A-Za-z0-9.-]+(?:\s*(?:\.|\(dot\)|\[dot\]|\{dot\}|\sdot\s)\s*[A-Za-z0-9.-]+)+)\b",
    re.IGNORECASE,
)
PRIVATE_OR_LOW_SIGNAL_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "localhost",
    "invalid",
}
SUSPICIOUS_LOCAL_PARTS = {
    "abuse",
    "admin",
    "donotreply",
    "info",
    "marketing",
    "newsletter",
    "no-reply",
    "noreply",
    "office",
    "postmaster",
    "privacy",
    "sales",
    "security",
    "support",
    "webmaster",
}
AGGREGATOR_DOMAINS = (
    "orcid.org",
    "scholar.google.",
    "semanticscholar.org",
)


@dataclass(frozen=True)
class EmailHit:
    email: str
    confidence: str
    source: str
    evidence: str
    source_rank: int
    name_score: int


def enrich_candidate_emails(
    candidates: Iterable[Candidate],
    *,
    enabled: bool = False,
    provider: str = "serpapi",
    max_results: int = 5,
    api_key: Optional[str] = None,
) -> list[Candidate]:
    candidate_list = list(candidates)
    if not enabled:
        return candidate_list

    remaining_candidates = candidate_list[MAX_CANDIDATES_PER_RUN:]
    if len(candidate_list) > MAX_CANDIDATES_PER_RUN:
        LOGGER.info("Email lookup: capped at 6 final candidates")
        candidate_list = candidate_list[:MAX_CANDIDATES_PER_RUN]

    if provider != "serpapi":
        LOGGER.warning("Email lookup provider %s is not supported; skipping lookup.", provider)
        return [
            _mark_lookup_skipped(candidate, f"Email lookup skipped; unsupported provider: {provider}.")
            for candidate in candidate_list + remaining_candidates
        ]

    serpapi_key = api_key or os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
        LOGGER.warning("SERPAPI_API_KEY is missing; skipping optional email lookup.")
        return [
            _mark_lookup_skipped(candidate, "Email lookup skipped because SERPAPI_API_KEY is missing.")
            for candidate in candidate_list + remaining_candidates
        ]

    LOGGER.info("Email lookup: checking %s final selected candidates", len(candidate_list))
    enriched: list[Candidate] = []
    cache: dict[str, dict] = {}
    page_cache: dict[str, str] = {}
    max_results = max(1, min(max_results, 10))

    for candidate in candidate_list:
        if _has_reliable_email(candidate):
            LOGGER.info("Email lookup: skipped because candidate already has reliable email")
            enriched.append(candidate)
            continue
        enriched.append(
            _lookup_candidate_email(
                candidate,
                api_key=serpapi_key,
                max_results=max_results,
                cache=cache,
                page_cache=page_cache,
            )
        )

    enriched.extend(
        _mark_lookup_skipped(candidate, "Email lookup skipped; maximum 6 candidates per run.")
        for candidate in remaining_candidates
    )
    return enriched


def _has_reliable_email(candidate: Candidate) -> bool:
    email = _normalize_email(candidate.email or "")
    if not email or _is_suspicious_email(email):
        return False

    confidence = (candidate.email_confidence or "").strip().lower()
    if confidence in {"high", "verified"}:
        return True
    if confidence == "medium":
        return True
    return False


def _lookup_candidate_email(
    candidate: Candidate,
    *,
    api_key: str,
    max_results: int,
    cache: dict[str, dict],
    page_cache: dict[str, str],
) -> Candidate:
    hits: list[EmailHit] = []
    possible: list[str] = []
    existing_email = _normalize_email(candidate.email or "")
    if existing_email and not _is_suspicious_email(existing_email):
        possible.append(f"{existing_email} | existing candidate metadata | requires SerpAPI/public-page verification")
    elif candidate.email:
        possible.append(str(candidate.email).strip())

    for query in _search_queries(candidate):
        payload = cache.get(query)
        if payload is None:
            payload = _serpapi_search(query, api_key=api_key, max_results=max_results)
            cache[query] = payload
        hits.extend(_hits_from_search_results(candidate, payload, page_cache=page_cache, max_pages=max_results))

    hits = _dedupe_hits(hits)
    reliable = [hit for hit in hits if hit.confidence in {"high", "medium"}]
    low_confidence = [hit for hit in hits if hit.confidence == "low"]
    possible.extend(_format_possible_email(hit) for hit in low_confidence)

    if reliable:
        best = sorted(reliable, key=_hit_sort_key, reverse=True)[0]
        notes = _verification_note_for(best)
        return _copy_candidate(
            candidate,
            {
                "email": best.email,
                "email_source": best.source,
                "email_confidence": best.confidence,
                "email_evidence": best.evidence,
                "possible_emails": _dedupe_strings(item for item in possible if not item.startswith(best.email)),
                "email_verification_notes": notes,
            },
        )

    return _copy_candidate(
        candidate,
        {
            "email": "",
            "email_source": "",
            "email_confidence": "not_found",
            "email_evidence": "",
            "possible_emails": _dedupe_strings(possible),
            "email_verification_notes": EMAIL_NOT_FOUND_NOTE,
        },
    )


def _search_queries(candidate: Candidate) -> list[str]:
    name = (candidate.name or "").strip()
    institution = (candidate.institution or "").strip()
    paper_title = (candidate.paper_title or "").strip()
    queries: list[str] = []
    if name and institution:
        queries.append(f'"{name}" "{institution}" email')
    if name and paper_title:
        queries.append(f'"{name}" "{paper_title}" email')
    if name and institution:
        queries.append(f'"{name}" "{institution}" lab')
        queries.append(f'"{name}" "{institution}" personal website')
    if name and paper_title:
        queries.append(f'"{name}" "{paper_title}" author email')
    return queries


def _serpapi_search(query: str, *, api_key: str, max_results: int) -> dict:
    params = urlencode({"engine": "google", "q": query, "num": max_results, "api_key": api_key})
    request = Request(f"{SERPAPI_URL}?{params}", headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=SEARCH_TIMEOUT_SECONDS) as response:
            return json.loads(response.read(MAX_FETCH_BYTES).decode("utf-8", errors="replace"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        LOGGER.warning("SerpAPI email lookup failed for query %r: %s", query, exc)
        return {}


def _hits_from_search_results(
    candidate: Candidate,
    payload: dict,
    *,
    page_cache: dict[str, str],
    max_pages: int,
) -> list[EmailHit]:
    hits: list[EmailHit] = []
    fetched_pages = 0
    for result in payload.get("organic_results") or []:
        if not isinstance(result, dict):
            continue
        title = _plain_text(result.get("title"))
        snippet = _plain_text(_result_text(result))
        link = str(result.get("link") or "")
        source_text = " ".join(part for part in [title, snippet, link] if part)
        source_rank = _source_rank(candidate, title=title, snippet=snippet, url=link)
        hits.extend(
            _email_hits_from_text(
                candidate,
                text=source_text,
                source=link or title or "SerpAPI snippet",
                source_rank=source_rank,
                evidence_prefix="SerpAPI result",
            )
        )
        if fetched_pages >= min(3, max_pages):
            continue
        if not _should_fetch_result(candidate, title=title, snippet=snippet, url=link):
            continue
        page_text = page_cache.get(link)
        if page_text is None:
            page_text = _fetch_public_page(link)
            page_cache[link] = page_text
        fetched_pages += 1
        hits.extend(
            _email_hits_from_text(
                candidate,
                text=page_text,
                source=link,
                source_rank=source_rank,
                evidence_prefix="Public page",
            )
        )
    return hits


def _result_text(result: dict) -> str:
    parts = [result.get("snippet"), result.get("displayed_link"), result.get("source")]
    rich_snippet = result.get("rich_snippet")
    if isinstance(rich_snippet, dict):
        parts.append(json.dumps(rich_snippet, ensure_ascii=False))
    return " ".join(str(part) for part in parts if part)


def _fetch_public_page(url: str) -> str:
    if not url.lower().startswith(("http://", "https://")):
        return ""
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "text/plain" not in content_type and "application/xhtml" not in content_type:
                return ""
            body = response.read(MAX_FETCH_BYTES)
    except (OSError, URLError):
        return ""
    return html.unescape(body.decode("utf-8", errors="replace"))


def _email_hits_from_text(
    candidate: Candidate,
    *,
    text: str,
    source: str,
    source_rank: int,
    evidence_prefix: str,
) -> list[EmailHit]:
    if not text:
        return []
    hits: list[EmailHit] = []
    for email in _extract_emails(text):
        if _is_suspicious_email(email):
            continue
        confidence = _confidence(candidate, text=text, source_rank=source_rank)
        evidence = _short_evidence(candidate, text=text, prefix=evidence_prefix)
        hits.append(
            EmailHit(
                email=email,
                confidence=confidence,
                source=source,
                evidence=evidence,
                source_rank=source_rank,
                name_score=_email_name_score(candidate, email),
            )
        )
    return hits


def _extract_emails(text: str) -> list[str]:
    emails: list[str] = []
    for raw in MAILTO_PATTERN.findall(text):
        normalized = _normalize_email(raw)
        if normalized:
            emails.append(normalized)
    for raw in EMAIL_PATTERN.findall(text):
        normalized = _normalize_email(raw)
        if normalized:
            emails.append(normalized)
    for local_part, domain in OBFUSCATED_EMAIL_PATTERN.findall(text):
        normalized_domain = re.sub(
            r"\s*(?:\.|\(dot\)|\[dot\]|\{dot\}|\sdot\s)\s*",
            ".",
            domain,
            flags=re.IGNORECASE,
        )
        normalized = _normalize_email(f"{local_part}@{normalized_domain}")
        if normalized:
            emails.append(normalized)
    return _dedupe_strings(emails)


def _confidence(candidate: Candidate, *, text: str, source_rank: int) -> str:
    if source_rank >= 9:
        return "low"
    full_name = _full_name_matches(candidate.name, text)
    institution = _context_matches(candidate.institution, text)
    paper = _context_matches(candidate.paper_title, text, minimum_terms=3)
    lab_or_project_source = source_rank in {1, 3}
    academic_source = source_rank in {0, 1, 2, 3, 4}
    if full_name and (institution or paper or lab_or_project_source):
        return "high"
    if full_name and academic_source:
        return "medium"
    return "low"


def _should_fetch_result(candidate: Candidate, *, title: str, snippet: str, url: str) -> bool:
    if not url or _is_aggregator_url(url):
        return False
    text = f"{title} {snippet} {url}"
    if not _full_name_matches(candidate.name, text):
        return False
    return _context_matches(candidate.institution, text) or _context_matches(candidate.paper_title, text, minimum_terms=3)


def _source_rank(candidate: Candidate, *, title: str, snippet: str, url: str) -> int:
    if _is_aggregator_url(url):
        return 9
    text = f"{title} {snippet} {url}".lower()
    institution_match = _context_matches(candidate.institution, text)
    if institution_match and re.search(r"\b(profile|people|person|faculty|staff|directory)\b", text):
        return 0
    if institution_match and re.search(r"\b(lab|group|research)\b", text):
        return 1
    if re.search(r"\b(homepage|personal|website|cv|professor)\b", text) or "github.io" in text:
        return 2
    if re.search(r"\b(project|software|code|dataset)\b", text):
        return 3
    if _context_matches(candidate.paper_title, text, minimum_terms=3) or re.search(r"\b(paper|publication|author|contact)\b", text):
        return 4
    return 5


def _full_name_matches(name: str, text: str) -> bool:
    tokens = _significant_terms(name)
    if len(tokens) < 2:
        return bool(tokens and tokens[0] in text.lower())
    lowered = text.lower()
    return tokens[0] in lowered and tokens[-1] in lowered


def _context_matches(value: Optional[str], text: str, *, minimum_terms: int = 2) -> bool:
    terms = _significant_terms(value or "")
    if not terms:
        return False
    lowered = text.lower()
    matched = sum(1 for term in terms if term in lowered)
    return matched >= min(minimum_terms, len(terms))


def _significant_terms(value: str) -> list[str]:
    stopwords = {
        "and",
        "for",
        "from",
        "the",
        "with",
        "university",
        "department",
        "institute",
        "school",
        "college",
        "center",
        "centre",
    }
    return [
        term
        for term in re.findall(r"[a-z0-9]+", value.lower())
        if len(term) >= 3 and term not in stopwords
    ][:8]


def _short_evidence(candidate: Candidate, *, text: str, prefix: str) -> str:
    cleaned = re.sub(r"\s+", " ", _plain_text(text)).strip()
    lowered = cleaned.lower()
    anchors = [candidate.name, candidate.institution or "", candidate.paper_title or ""]
    start = 0
    for anchor in anchors:
        terms = _significant_terms(anchor)
        positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
        if positions:
            start = max(0, min(positions) - 80)
            break
    excerpt = cleaned[start : start + 260].strip()
    return f"{prefix}: {excerpt}"


def _plain_text(value) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_email(value: str) -> Optional[str]:
    cleaned = html.unescape(value or "").strip().strip(".,;:()[]{}<>\"'")
    if not EMAIL_PATTERN.fullmatch(cleaned):
        return None
    return cleaned.lower()


def _is_suspicious_email(email: str) -> bool:
    local_part, domain = email.rsplit("@", 1)
    domain = domain.lower().strip(".")
    if domain in PRIVATE_OR_LOW_SIGNAL_DOMAINS or domain.endswith(".invalid"):
        return True
    if local_part.lower() in SUSPICIOUS_LOCAL_PARTS:
        return True
    if len(local_part) <= 1 or ".." in email:
        return True
    return False


def _is_aggregator_url(url: str) -> bool:
    lowered = url.lower()
    return any(domain in lowered for domain in AGGREGATOR_DOMAINS)


def _email_name_score(candidate: Candidate, email: str) -> int:
    local_part = email.split("@", 1)[0].lower()
    tokens = _significant_terms(candidate.name)
    if not tokens:
        return 0
    score = 0
    if tokens[0] in local_part:
        score += 2
    if tokens[-1] in local_part:
        score += 3
    if len(tokens) >= 2 and f"{tokens[0][0]}{tokens[-1]}" in re.sub(r"[^a-z0-9]", "", local_part):
        score += 1
    return score


def _hit_sort_key(hit: EmailHit) -> tuple[int, int, int, int]:
    confidence_score = {"high": 3, "medium": 2, "low": 1}.get(hit.confidence, 0)
    return (confidence_score, -hit.source_rank, hit.name_score, len(hit.evidence))


def _verification_note_for(hit: EmailHit) -> str:
    if hit.confidence == "high":
        return "Email found with high-confidence public evidence. Verify manually before outreach."
    return "Email found with medium-confidence public evidence. Verify manually before outreach."


def _format_possible_email(hit: EmailHit) -> str:
    return f"{hit.email} | low confidence | {hit.source}"


def _dedupe_hits(hits: Iterable[EmailHit]) -> list[EmailHit]:
    best_by_email: dict[str, EmailHit] = {}
    for hit in hits:
        current = best_by_email.get(hit.email)
        if current is None or _hit_sort_key(hit) > _hit_sort_key(current):
            best_by_email[hit.email] = hit
    return list(best_by_email.values())


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


def _mark_lookup_skipped(candidate: Candidate, note: str) -> Candidate:
    return _copy_candidate(candidate, {"email_verification_notes": candidate.email_verification_notes or note})


def _copy_candidate(candidate: Candidate, update: dict) -> Candidate:
    if hasattr(candidate, "model_copy"):
        return candidate.model_copy(update=update)
    return candidate.copy(update=update)
