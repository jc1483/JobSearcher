from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_KEYWORDS: Dict[str, float] = {
    "qa": 3.0,
    "quality assurance": 3.5,
    "qa automation": 5.0,
    "automation": 4.0,
    "automation engineer": 4.5,
    "sdet": 5.0,
    "test automation": 5.0,
    "regression": 3.0,
    "smoke testing": 2.5,
    "integration testing": 3.5,
    "api testing": 4.0,
    "database": 2.0,
    "validation": 1.5,
    "debugging": 2.0,
    "selenium": 5.0,
    "cucumber": 4.0,
    "java": 4.0,
    "python": 4.0,
    "c#": 3.0,
    "testcomplete": 3.5,
    "tosca": 3.0,
    "oop": 2.0,
    "agile": 2.0,
    "scrum": 1.5,
    "kanban": 1.0,
    "ci/cd": 3.0,
    "lead": 2.0,
    "leadership": 2.0,
    "mentor": 1.5,
    "mentoring": 1.5,
    "ai": 2.0,
    "remote": 1.0,
}

TITLE_BONUS: Dict[str, float] = {
    "senior": 2.0,
    "lead": 2.0,
    "principal": 2.0,
    "staff": 1.5,
    "qa": 3.0,
    "quality": 2.0,
    "automation": 3.0,
    "sdet": 4.0,
    "test": 1.5,
    "engineer": 1.5,
}

NEGATIVE_TERMS: Dict[str, float] = {
    "intern": -8.0,
    "junior": -4.0,
    "manual only": -6.0,
    "onsite only": -3.0,
    "commission": -5.0,
}

SALARY_REGEXES = [
    re.compile(r"\$?\s*([0-9]{2,3})(?:\s*[kK])\s*[-–to]{1,3}\s*\$?\s*([0-9]{2,3})(?:\s*[kK])"),
    re.compile(r"\$\s*([0-9]{2,3}),?([0-9]{3})\s*[-–to]{1,3}\s*\$\s*([0-9]{2,3}),?([0-9]{3})"),
]

DEFAULT_CONFIG_FILE = Path("job_match_config.json")


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    return re.sub(r"\s+", " ", text).strip()


SEARCH_QUERY_STOPWORDS = {
    "and", "the", "for", "with", "that", "this", "have", "has", "from",
    "your", "are", "can", "will", "our", "not", "but", "you", "all",
    "their", "they", "them", "about", "more", "than", "also", "into",
    "role", "roles", "job", "jobs", "using", "used", "working", "work",
    "project", "projects", "management", "manager", "experience", "experiences",
}


def derive_search_query(resume_text: str, max_terms: int = 6) -> str:
    text = normalize_text(resume_text)
    tokens = [t for t in re.findall(r"[a-zA-Z#+]{3,}", text) if t not in SEARCH_QUERY_STOPWORDS]
    if not tokens:
        return "software engineer"

    token_counts = {}
    for token in tokens:
        token_counts[token] = token_counts.get(token, 0) + 1

    bigram_counts = {}
    for a, b in zip(tokens, tokens[1:]):
        phrase = f"{a} {b}"
        if phrase not in SEARCH_QUERY_STOPWORDS:
            bigram_counts[phrase] = bigram_counts.get(phrase, 0) + 1

    term_scores = {}
    for term, count in token_counts.items():
        term_scores[term] = term_scores.get(term, 0) + count
    for phrase, count in bigram_counts.items():
        if count > 1:
            term_scores[phrase] = term_scores.get(phrase, 0) + count * 2

    sorted_terms = sorted(term_scores.items(), key=lambda item: (-item[1], item[0]))
    query_terms = [term for term, _ in sorted_terms[:max_terms]]
    if not query_terms:
        return "software engineer"
    return " ".join(query_terms)


def parse_bool(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "easy apply", "easyapply"}


def parse_salary_from_text(text: str) -> Tuple[Optional[int], Optional[int]]:
    if not text:
        return None, None
    for pattern in SALARY_REGEXES:
        m = pattern.search(str(text))
        if not m:
            continue
        nums = [g for g in m.groups() if g is not None]
        if len(nums) == 2:
            lo, hi = int(nums[0]) * 1000, int(nums[1]) * 1000
            return min(lo, hi), max(lo, hi)
        if len(nums) == 4:
            lo = int(nums[0]) * 1000 + int(nums[1])
            hi = int(nums[2]) * 1000 + int(nums[3])
            return min(lo, hi), max(lo, hi)
    return None, None


def parse_optional_int(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None
