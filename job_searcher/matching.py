from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .utils import (
    NEGATIVE_TERMS,
    TITLE_BONUS,
    normalize_text,
    parse_bool,
    parse_salary_from_text,
    parse_optional_int,
)


def derive_resume_keywords(resume_text: str, max_terms: int = 40) -> Dict[str, float]:
    text = normalize_text(resume_text)
    tokens = [t for t in re.findall(r"[a-zA-Z#+]{3,}", text) if t not in STOPWORDS]
    counts = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1

    bigrams = {}
    for a, b in zip(tokens, tokens[1:]):
        phrase = f"{a} {b}"
        bigrams[phrase] = bigrams.get(phrase, 0) + 1

    candidates = {}
    for token, freq in counts.items():
        if freq > 1:
            candidates[token] = min(6.0, 1.0 + freq * 0.8)
    for phrase, freq in bigrams.items():
        if freq > 1 and len(phrase) > 6:
            candidates[phrase] = min(6.0, 1.5 + freq * 1.0)

    sorted_candidates = sorted(candidates.items(), key=lambda item: item[1], reverse=True)
    return {name: weight for name, weight in sorted_candidates[:max_terms]}


def derive_resume_title_bonus(resume_text: str) -> Dict[str, float]:
    text = normalize_text(resume_text)
    bonuses = {}
    for term, base in TITLE_BONUS.items():
        if term in text:
            bonuses[term] = min(base + 1.0, base * 1.25)
    if not bonuses:
        for term in ["engineer", "automation", "qa", "quality", "sdet"]:
            if term in text:
                bonuses[term] = 2.0
    return bonuses


STOPWORDS = {
    "and", "the", "for", "with", "that", "this", "have", "has", "from",
    "your", "are", "can", "will", "our", "not", "but", "you", "all",
    "their", "they", "them", "about", "more", "than", "also", "into",
    "role", "roles", "job", "jobs", "using", "used", "using", "work",
    "works", "working", "project", "projects", "management", "manager",
}


def overlap_score(job_min, job_max, desired_min, desired_max) -> float:
    if desired_min is None and desired_max is None:
        return 0.0
    if job_min is None and job_max is None:
        return 0.0
    if job_min is None:
        job_min = job_max
    if job_max is None:
        job_max = job_min
    if desired_min is None:
        desired_min = desired_max
    if desired_max is None:
        desired_max = desired_min
    if None in (job_min, job_max, desired_min, desired_max):
        return 0.0

    left = max(job_min, desired_min)
    right = min(job_max, desired_max)
    if right >= left:
        desired_span = max(1, desired_max - desired_min)
        overlap = right - left
        pct = min(1.0, overlap / desired_span if desired_span else 1.0)
        job_mid = (job_min + job_max) / 2
        desired_mid = (desired_min + desired_max) / 2
        distance = abs(job_mid - desired_mid)
        midpoint_bonus = max(0.0, 1.0 - distance / max(1, desired_span))
        return 12.0 * pct + 4.0 * midpoint_bonus

    below_gap = desired_min - job_max if job_max < desired_min else 0
    above_gap = job_min - desired_max if job_min > desired_max else 0
    gap = max(below_gap, above_gap)
    if gap <= 10000:
        return 4.0
    if gap <= 20000:
        return 1.5
    return -6.0


def term_hits(text: str, weighted_terms: Dict[str, float]):
    total = 0.0
    hits = {}
    for term, weight in weighted_terms.items():
        pattern = r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)"
        count = len(re.findall(pattern, text))
        if count > 0:
            hits[term] = count
            total += min(count, 3) * weight
    return total, hits


@dataclass
class JobMatch:
    title: str
    company: str
    location: str
    description: str
    url: str
    easy_apply: bool
    salary_min: Optional[int]
    salary_max: Optional[int]
    compensation_text: str
    score: float
    salary_score: float
    title_score: float
    keyword_score: float
    negative_score: float
    matching_terms: List[str] = field(default_factory=list)


class JobMatcher:
    def __init__(
        self,
        resume_text: str,
        desired_min: Optional[int],
        desired_max: Optional[int],
        remote_preference: bool = True,
        keywords: Optional[Dict[str, float]] = None,
        title_bonus: Optional[Dict[str, float]] = None,
        negative_terms: Optional[Dict[str, float]] = None,
    ):
        self.resume_text = normalize_text(resume_text)
        self.desired_min = desired_min
        self.desired_max = desired_max
        self.remote_preference = remote_preference
        self.keywords = keywords if keywords is not None else derive_resume_keywords(self.resume_text)
        self.title_bonus = title_bonus if title_bonus is not None else derive_resume_title_bonus(self.resume_text)
        self.negative_terms = negative_terms if negative_terms is not None else NEGATIVE_TERMS

    def score_row(self, row: pd.Series) -> JobMatch:
        title = str(row.get("title", "") or "")
        company = str(row.get("company", "") or "")
        location = str(row.get("location", "") or "")
        description = str(row.get("description", "") or "")
        url = str(row.get("url", "") or "")
        easy_apply = parse_bool(row.get("easy_apply", False))
        compensation_text = str(row.get("compensation_text", "") or "")

        salary_min = row.get("salary_min")
        salary_max = row.get("salary_max")
        salary_min = None if pd.isna(salary_min) else int(salary_min)
        salary_max = None if pd.isna(salary_max) else int(salary_max)
        if salary_min is None and salary_max is None:
            salary_min, salary_max = parse_salary_from_text(compensation_text)

        combined = normalize_text(f"{title} {company} {location} {description}")
        keyword_score, hits = term_hits(combined, self.keywords)
        title_score, _ = term_hits(normalize_text(title), self.title_bonus)
        negative_score, _ = term_hits(combined, self.negative_terms)
        if self.remote_preference and "remote" in combined:
            title_score += 1.5
        salary_score = overlap_score(salary_min, salary_max, self.desired_min, self.desired_max)

        score = keyword_score + title_score + salary_score + negative_score
        if easy_apply:
            score += 1.0

        return JobMatch(
            title=title,
            company=company,
            location=location,
            description=description,
            url=url,
            easy_apply=easy_apply,
            salary_min=salary_min,
            salary_max=salary_max,
            compensation_text=compensation_text,
            score=round(score, 2),
            salary_score=round(salary_score, 2),
            title_score=round(title_score, 2),
            keyword_score=round(keyword_score, 2),
            negative_score=round(negative_score, 2),
            matching_terms=sorted(hits.keys()),
        )

    def rank(self, df: pd.DataFrame):
        matches = [self.score_row(row) for _, row in df.iterrows()]
        matches.sort(key=lambda m: (m.score, m.salary_score, m.keyword_score), reverse=True)
        return matches


def matches_to_dataframe(matches):
    rows = []
    for m in matches:
        rows.append({
            "score": m.score,
            "title": m.title,
            "company": m.company,
            "location": m.location,
            "easy_apply": m.easy_apply,
            "salary_min": m.salary_min,
            "salary_max": m.salary_max,
            "compensation_text": m.compensation_text,
            "salary_score": m.salary_score,
            "title_score": m.title_score,
            "keyword_score": m.keyword_score,
            "negative_score": m.negative_score,
            "matching_terms": ", ".join(m.matching_terms),
            "url": m.url,
        })
    return pd.DataFrame(rows)
