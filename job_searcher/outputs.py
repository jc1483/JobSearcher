from __future__ import annotations

import webbrowser
from pathlib import Path

import pandas as pd

from .matching import matches_to_dataframe


def get_output_files(output_dir: Path) -> list[str]:
    files = []
    if output_dir.exists() and output_dir.is_dir():
        for name in [
            "ranked_jobs_all.csv",
            "ranked_easy_apply_jobs.csv",
            "ranked_manual_review_jobs.csv",
        ]:
            if (output_dir / name).exists():
                files.append(name)
    return files


def serialize_matches(matches):
    serialized = []
    for m in matches:
        serialized.append(
            {
                "title": m.title,
                "company": m.company,
                "location": m.location,
                "score": m.score,
                "easy_apply": m.easy_apply,
                "url": m.url,
                "salary_min": m.salary_min,
                "salary_max": m.salary_max,
                "matching_terms": ", ".join(m.matching_terms),
            }
        )
    return serialized


def write_outputs(matches, output_dir: Path, top_n: int):
    output_dir.mkdir(parents=True, exist_ok=True)
    ranked_df = matches_to_dataframe(matches)
    easy_apply_df = ranked_df[ranked_df["easy_apply"] == True].head(top_n)
    manual_df = ranked_df[ranked_df["easy_apply"] != True].head(top_n)

    ranked_df.to_csv(output_dir / "ranked_jobs_all.csv", index=False)
    easy_apply_df.to_csv(output_dir / "ranked_easy_apply_jobs.csv", index=False)
    manual_df.to_csv(output_dir / "ranked_manual_review_jobs.csv", index=False)


def open_top_easy_apply(matches, limit: int):
    opened = 0
    for m in matches:
        if m.easy_apply and m.url:
            webbrowser.open_new_tab(m.url)
            opened += 1
            if opened >= limit:
                break
