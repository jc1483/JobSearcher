#!/usr/bin/env python3
"""
linkedin_job_matcher.py

A small CLI entrypoint that delegates job matching logic to helper modules.
"""

from __future__ import annotations

from job_searcher.cli import main


if __name__ == "__main__":
    main()
