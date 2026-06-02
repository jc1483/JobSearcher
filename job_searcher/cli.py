from __future__ import annotations

import argparse
import getpass
from pathlib import Path

from .config import load_config
from .credentials import create_encrypted_credentials, load_credentials
from .linkedin_scraper import scrape_linkedin_jobs
from .matching import JobMatcher
from .outputs import open_top_easy_apply, write_outputs
from .resume_parser import extract_resume_text
from .utils import derive_search_query
from .webui import run_webui


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume", help="Resume file path (.txt, .md, .rtf, .pdf, .docx).")
    parser.add_argument("--output-dir", default="job_match_outputs")
    parser.add_argument("--min-salary", type=int, default=None)
    parser.add_argument("--max-salary", type=int, default=None)
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--open-easy-apply", action="store_true")
    parser.add_argument("--open-limit", type=int, default=10)
    parser.add_argument("--credentials-file", help="Encrypted credentials file containing LinkedIn email and password.")
    parser.add_argument("--credentials-passphrase", help="Passphrase used to decrypt the credentials file.")
    parser.add_argument("--linkedin-query", help="Optional LinkedIn search keywords override; otherwise derived automatically from the resume.")
    parser.add_argument("--linkedin-location", default="United States", help="LinkedIn search location.")
    parser.add_argument("--linkedin-pages", type=int, default=2, help="How many LinkedIn result pages to scrape.")
    parser.add_argument("--remote-only", action="store_true", help="Search remote roles only instead of all roles in the chosen location.")
    parser.add_argument("--no-headless", action="store_true", help="Run LinkedIn scraping in a visible browser window.")
    parser.add_argument("--chrome-binary", help="Path to the Chrome/Chromium browser executable.")
    parser.add_argument("--config-file", help="JSON config file that defines salary and LinkedIn connection defaults.")
    parser.add_argument("--webui", action="store_true", help="Launch a local web UI for changing parameters and viewing results.")
    parser.add_argument("--host", default="127.0.0.1", help="Host address for the web UI.")
    parser.add_argument("--port", type=int, default=5000, help="Port for the web UI.")
    parser.add_argument("--create-credentials", action="store_true", help="Create/update the encrypted credentials file and exit.")
    parser.add_argument("--linkedin-email", help="LinkedIn login email used only with --create-credentials.")
    parser.add_argument("--linkedin-password", help="LinkedIn login password used only with --create-credentials.")
    args = parser.parse_args()

    if args.webui:
        run_webui(host=args.host, port=args.port)
        return

    if args.create_credentials:
        email = args.linkedin_email or input("LinkedIn email: ").strip()
        password = args.linkedin_password or getpass.getpass("LinkedIn password: ")
        passphrase = args.credentials_passphrase or getpass.getpass("Credentials passphrase: ")
        if not args.credentials_file or not passphrase:
            parser.error("--create-credentials requires --credentials-file and a credentials passphrase")
        if not email or not password:
            parser.error("--create-credentials requires LinkedIn email and password")
        create_encrypted_credentials(
            Path(args.credentials_file),
            email,
            password,
            passphrase,
        )
        print(f"Encrypted credentials file created at {args.credentials_file}")
        return

    missing = [
        name
        for name, value in [
            ("--resume", args.resume),
            ("--credentials-file", args.credentials_file),
            ("--credentials-passphrase", args.credentials_passphrase),
        ]
        if not value
    ]
    if missing:
        parser.error("Missing required arguments: " + ", ".join(missing))

    email, password = load_credentials(Path(args.credentials_file), args.credentials_passphrase)
    config = load_config(Path(args.config_file)) if args.config_file else None
    desired_min = args.min_salary if args.min_salary is not None else (config.get("salary_min") if config else None)
    desired_max = args.max_salary if args.max_salary is not None else (config.get("salary_max") if config else None)
    remote_only = args.remote_only or (config.get("remote_only") if config else False)

    resume_text = extract_resume_text(Path(args.resume))
    query = args.linkedin_query or (config.get("linkedin_query") if config else None)
    if not query:
        query = derive_search_query(resume_text)

    df = scrape_linkedin_jobs(
        email=email,
        password=password,
        query=query,
        location=args.linkedin_location,
        pages=args.linkedin_pages,
        headless=not args.no_headless,
        remote_only=remote_only,
        chrome_binary_path=args.chrome_binary,
    )

    matcher = JobMatcher(
        resume_text,
        desired_min,
        desired_max,
    )
    matches = matcher.rank(df)
    write_outputs(matches, Path(args.output_dir), args.top)

    if args.open_easy_apply:
        open_top_easy_apply(matches, args.open_limit)
