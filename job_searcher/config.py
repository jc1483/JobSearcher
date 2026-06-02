from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from .utils import (
    DEFAULT_CONFIG_FILE,
    parse_optional_int,
)


def load_config(config_path: Path) -> Dict[str, object]:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return {
        "salary_min": parse_optional_int(data.get("salary_min")),
        "salary_max": parse_optional_int(data.get("salary_max")),
        "credentials_file": data.get("credentials_file", str(config_path.with_name("linkedin_credentials.json"))),
        "linkedin_query": data.get("linkedin_query", ""),
        "linkedin_location": data.get("linkedin_location", "United States"),
        "linkedin_pages": parse_optional_int(data.get("linkedin_pages")) or 2,
        "resume": data.get("resume", ""),
        "remote_only": bool(data.get("remote_only", False)),
        "output_dir": data.get("output_dir", "job_match_outputs"),
        "top": parse_optional_int(data.get("top")) or 25,
        "min_salary": parse_optional_int(data.get("min_salary")),
        "max_salary": parse_optional_int(data.get("max_salary")),
        "no_headless": bool(data.get("no_headless", False)),
        "chrome_binary_path": data.get("chrome_binary_path", ""),
        "chromedriver_path": data.get("chromedriver_path", ""),
        "config_file": str(config_path),
    }


def create_default_config(config_path: Path = DEFAULT_CONFIG_FILE) -> None:
    if config_path.exists():
        return
    default_config = {
        "credentials_file": str(config_path.with_name("linkedin_credentials.json")),
        "linkedin_query": "",
        "linkedin_location": "United States",
        "linkedin_pages": 2,
        "resume": "resume.pdf",
        "output_dir": "job_match_outputs",
        "top": 25,
        "min_salary": None,
        "max_salary": None,
        "remote_only": False,
        "chrome_binary_path": "",
        "chromedriver_path": "",
    }
    config_path.write_text(json.dumps(default_config, indent=2), encoding="utf-8")


def apply_config_defaults(params: Dict[str, str], config: Dict[str, object]) -> None:
    defaults = {
        "credentials_file": config.get("credentials_file", "").strip(),
        "linkedin_query": config.get("linkedin_query", ""),
        "linkedin_location": config.get("linkedin_location", "United States"),
        "linkedin_pages": str(config.get("linkedin_pages", 2)),
        "remote_only": "checked" if config.get("remote_only") else "",
        "config_file": config.get("config_file", ""),
        "resume": config.get("resume", ""),
        "output_dir": config.get("output_dir", "job_match_outputs"),
        "top": str(config.get("top", 25)),
        "min_salary": str(config["salary_min"]) if config.get("salary_min") is not None else "",
        "max_salary": str(config["salary_max"]) if config.get("max_salary") is not None else "",
        "no_headless": "checked" if config.get("no_headless") else "",
        "chrome_binary_path": config.get("chrome_binary_path", ""),
        "chromedriver_path": config.get("chromedriver_path", ""),
    }
    for key, value in defaults.items():
        if not params.get(key) and value is not None:
            params[key] = value


def save_config(config_path: Path, config: Dict[str, object]) -> None:
    data = {
        "credentials_file": config.get("credentials_file", str(config_path.with_name("linkedin_credentials.json"))),
        "linkedin_query": config.get("linkedin_query", ""),
        "linkedin_location": config.get("linkedin_location", "United States"),
        "linkedin_pages": int(config.get("linkedin_pages") or 2),
        "resume": config.get("resume", ""),
        "output_dir": config.get("output_dir", "job_match_outputs"),
        "top": int(config.get("top") or 25),
        "min_salary": parse_optional_int(config.get("min_salary")),
        "max_salary": parse_optional_int(config.get("max_salary")),
        "remote_only": bool(config.get("remote_only", False)),
        "no_headless": bool(config.get("no_headless", False)),
        "chrome_binary_path": config.get("chrome_binary_path", ""),
        "chromedriver_path": config.get("chromedriver_path", ""),
    }
    config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_credentials_from_config(config: Dict[str, object]) -> None:
    credentials_file = config.get("credentials_file")
    if not credentials_file:
        return

    credentials_path = Path(credentials_file)
    if credentials_path.exists():
        return

    # If the encrypted credentials file is missing, the web UI will prompt for
    # LinkedIn email, password, and a passphrase at runtime and generate it.
    return
