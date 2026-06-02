from __future__ import annotations

import logging
import datetime
import json
import urllib.request
import zipfile
import tempfile
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import pandas as pd

try:
    from selenium import webdriver
    from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager, ChromeType
    from .config import load_config, save_config
    from .utils import DEFAULT_CONFIG_FILE
except ImportError:
    webdriver = None
    Service = None
    By = None
    EC = None
    WebDriverWait = None
    ChromeDriverManager = None
    NoSuchElementException = Exception
    TimeoutException = Exception
    WebDriverException = Exception


def ensure_selenium_available() -> None:
    if webdriver is None or ChromeDriverManager is None:
        raise ImportError(
            "LinkedIn scraping requires selenium and webdriver-manager. "
            "Install them with: pip install selenium webdriver-manager"
        )

logger = logging.getLogger(__name__)


def log_driver_state(driver, context: str) -> None:
    if not driver:
        logger.debug("Driver unavailable while logging state for %s", context)
        return
    try:
        current_url = driver.current_url
    except Exception as exc:
        current_url = f"<unable to retrieve current_url: {exc}>"
    try:
        title = driver.title
    except Exception as exc:
        title = f"<unable to retrieve title: {exc}>"
    try:
        page_source = driver.page_source[:1000].replace("\n", " ")
    except Exception as exc:
        page_source = f"<unable to retrieve page_source: {exc}>"
    logger.error(
        "Driver state during %s: current_url=%s title=%s page_source_start=%s",
        context,
        current_url,
        title,
        page_source,
    )

def _save_driver_screenshot(driver, context: str) -> Optional[str]:
    try:
        outdir = Path.home() / ".job_searcher" / "logs"
        outdir.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        fname = outdir / f"screenshot_{context}_{ts}.png"
        driver.save_screenshot(str(fname))
        logger.info("Saved driver screenshot to %s", fname)
        return str(fname)
    except Exception:
        logger.exception("Failed to save driver screenshot for %s", context)
    return None


def locate_chrome_binary(chrome_binary_path: Optional[str] = None) -> str:
    if chrome_binary_path:
        candidate = Path(chrome_binary_path)
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(
            f"Chrome binary not found at configured path: {chrome_binary_path}. "
            "Install Google Chrome or Chromium and point `chrome_binary_path` to the executable, "
            "for example `C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`."
        )

    env_path = os.environ.get("CHROME_BINARY_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(
            f"Chrome binary not found at CHROME_BINARY_PATH: {env_path}. "
            "Download Chrome/Chromium if needed and set CHROME_BINARY_PATH to the executable path, "
            "for example `C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`."
        )

    for binary in ["chrome", "chrome.exe", "google-chrome", "chromium", "chromium-browser"]:
        found = shutil.which(binary)
        if found:
            return found

    common_locations = []
    if os.name == "nt":
        common_locations = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files\Chromium\Application\chrome.exe",
            r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\Application\chrome.exe",
        ]
    elif sys.platform == "darwin":
        common_locations = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    else:
        common_locations = [
            "/usr/bin/google-chrome",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
        ]

    for location in common_locations:
        candidate = Path(location.replace("%USERNAME%", os.environ.get("USERNAME", "")))
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(
        "Chrome binary not found. Install Chrome (https://www.google.com/chrome/) or Chromium, "
        "then either add it to your PATH, set CHROME_BINARY_PATH, or add `chrome_binary_path` in config. "
        "On Windows the default path is `C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe`."
    )


def get_browser_version(chrome_binary_path: str) -> Optional[str]:
    try:
        result = subprocess.run(
            [chrome_binary_path, "--version"],
            capture_output=True,
            text=True,
            check=True,
        )
        match = re.search(r"(\d+\.\d+\.\d+\.\d+)", result.stdout)
        if match:
            return match.group(1)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return None


def _download_chromedriver_from_cft(browser_version: str, short_version: Optional[str] = None) -> Optional[str]:
    """Download a matching chromedriver from Chrome-for-Testing JSON API.

    Returns the path to the downloaded chromedriver executable, or None.
    """
    try:
        url = "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        logger.debug("Fetching CFT metadata from %s", url)
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
        versions = data.get("versions", [])
        candidates = []
        if browser_version:
            for v in versions:
                ver = v.get("version", "")
                if browser_version in ver or (short_version and short_version in ver):
                    candidates.append(v)
        if not candidates:
            return None
        chosen = candidates[-1]
        downloads = chosen.get("downloads", {}).get("chromedriver", [])
        # choose platform
        platform_preference = []
        if os.name == "nt":
            platform_preference = ["win64", "win32"]
        elif sys.platform == "darwin":
            platform_preference = ["mac-arm64", "mac-x64", "mac64_m1"]
        else:
            platform_preference = ["linux64", "linux64_x64"]

        download_url = None
        for p in platform_preference:
            for d in downloads:
                if d.get("platform") == p:
                    download_url = d.get("url")
                    break
            if download_url:
                break

        if not download_url:
            return None

        tmpdir = Path(tempfile.mkdtemp())
        zip_path = tmpdir / "driver.zip"
        logger.debug("Downloading chromedriver from %s", download_url)
        urllib.request.urlretrieve(download_url, str(zip_path))
        extract_dir = Path.home() / ".job_searcher" / "chromedriver" / chosen.get("version", "unknown")
        extract_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(str(zip_path), "r") as z:
            z.extractall(path=str(extract_dir))

        exe_name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
        for p in extract_dir.rglob(exe_name):
            p.chmod(0o755)
            return str(p)
    except Exception:
        logger.exception("Failed to download chromedriver from CFT")
    return None


def locate_chromedriver_binary() -> Optional[str]:
    env_path = os.environ.get("CHROMEDRIVER_PATH")
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return str(candidate)
    found = shutil.which("chromedriver")
    if found:
        return found
    return None


def create_chrome_driver(headless: bool = True, chrome_binary_path: Optional[str] = None):
    ensure_selenium_available()
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-blink-features=AutomationControlled")
    binary_path = locate_chrome_binary(chrome_binary_path)
    options.binary_location = binary_path

    # Prefer explicit chromedriver path from config, then env/system chromedriver
    local_driver_path = None
    try:
        if DEFAULT_CONFIG_FILE.exists():
            cfg = load_config(DEFAULT_CONFIG_FILE)
            cfg_path = cfg.get("chromedriver_path")
            if cfg_path:
                c = Path(cfg_path)
                if c.exists():
                    local_driver_path = str(c)
    except Exception:
        logger.exception("Failed to read chromedriver_path from config")

    if not local_driver_path:
        local_driver_path = locate_chromedriver_binary()

    if local_driver_path:
        drv = webdriver.Chrome(service=Service(local_driver_path), options=options)
        try:
            drv.set_page_load_timeout(60)
            drv.implicitly_wait(10)
        except Exception:
            logger.exception("Failed to set driver timeouts")
        return drv

    browser_version = get_browser_version(binary_path)
    chrome_type = ChromeType.GOOGLE
    if "brave" in binary_path.lower():
        chrome_type = ChromeType.GOOGLE

    driver_version_candidates = []
    if browser_version:
        driver_version_candidates.append(browser_version)
        short_version = ".".join(browser_version.split(".")[:3])
        if short_version != browser_version:
            driver_version_candidates.append(short_version)
        major_match = re.match(r"(\d+)", browser_version)
        if major_match:
            driver_version_candidates.append(major_match.group(1))

    logger.debug("Chrome binary path: %s", binary_path)
    logger.debug("Detected browser version: %s", browser_version)
    logger.debug("Driver version candidates: %s", driver_version_candidates)
    logger.debug("Chrome type: %s", chrome_type)

    service = None
    for candidate in driver_version_candidates:
        try:
            service = Service(ChromeDriverManager(driver_version=candidate, chrome_type=chrome_type).install())
            break
        except Exception:
            continue

    if service is None:
        logger.error(
            "Failed to install matching ChromeDriver. Tried candidates: %s; chrome_type=%s; binary=%s",
            driver_version_candidates,
            chrome_type,
            binary_path,
        )

        # Attempt to download matching driver directly from Chrome-for-Testing JSON API
        try:
            short_version = ".".join(browser_version.split(".")[:3]) if browser_version else None
            downloaded = None
            if browser_version:
                downloaded = _download_chromedriver_from_cft(browser_version, short_version)
            if downloaded:
                logger.info("Downloaded chromedriver to %s", downloaded)
                # persist to default config
                try:
                    cfg = load_config(DEFAULT_CONFIG_FILE) if DEFAULT_CONFIG_FILE.exists() else {}
                    cfg["chromedriver_path"] = str(downloaded)
                    save_config(DEFAULT_CONFIG_FILE, cfg)
                except Exception:
                    logger.exception("Failed to persist chromedriver_path to config")
                service = Service(str(downloaded))
            else:
                raise RuntimeError(
                    "Unable to install a matching ChromeDriver. Please install a compatible Chrome/Chromium driver manually or set CHROMEDRIVER_PATH to the driver executable. "
                    f"Attempted versions: {driver_version_candidates}. Verify your browser version and `chrome_binary_path` configuration."
                )
        except Exception as exc:
            logger.exception("Automatic chromedriver download failed: %s", exc)
            raise

    return webdriver.Chrome(service=service, options=options)


def safe_find_text(parent, selector: str) -> str:
    try:
        return parent.find_element(By.CSS_SELECTOR, selector).text.strip()
    except NoSuchElementException:
        return ""


def linkedin_login(driver, email: str, password: str) -> None:
    logger.debug("Navigating to LinkedIn login page")
    driver.get("https://www.linkedin.com/login")
    wait = WebDriverWait(driver, 30)
    try:
        wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))
    except Exception as exc:
        logger.exception("No input elements present after loading login page: %s", exc)
        log_driver_state(driver, "linkedin_login_page_load")
        _save_driver_screenshot(driver, "login_page_load")
        raise RuntimeError("LinkedIn login page did not load correctly.") from exc

    logger.debug("Attempting to locate email input using multiple selectors")
    email_input = None
    email_selectors = [
        (By.ID, "username"),
        (By.NAME, "session_key"),
        (By.CSS_SELECTOR, "input[aria-label*='Email']"),
        (By.CSS_SELECTOR, "input[aria-label*='email']"),
        (By.CSS_SELECTOR, "input[placeholder*='Email']"),
        (By.CSS_SELECTOR, "input[placeholder*='Email or phone']"),
    ]
    for by, sel in email_selectors:
        try:
            el = driver.find_element(by, sel)
            if el and el.is_displayed():
                email_input = el
                break
        except Exception:
            continue

    # Fallback: pick the first visible text/email input
    if email_input is None:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email'], input:not([type])")
            for c in candidates:
                try:
                    if c.is_displayed():
                        email_input = c
                        break
                except Exception:
                    continue
        except Exception:
            pass

    if email_input is None:
        logger.exception("Username field not present after loading login page: no selector matched")
        log_driver_state(driver, "linkedin_login_page_load")
        _save_driver_screenshot(driver, "login_page_load")
        raise RuntimeError("LinkedIn login page did not load correctly.")

    logger.debug("Attempting to locate password input using multiple selectors")
    password_input = None
    password_selectors = [
        (By.ID, "password"),
        (By.NAME, "session_password"),
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.CSS_SELECTOR, "input[aria-label*='Password']"),
    ]
    for by, sel in password_selectors:
        try:
            el = driver.find_element(by, sel)
            if el and el.is_displayed():
                password_input = el
                break
        except Exception:
            continue

    if password_input is None:
        try:
            candidates = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
            for c in candidates:
                try:
                    if c.is_displayed():
                        password_input = c
                        break
                except Exception:
                    continue
        except Exception:
            pass

    if password_input is None:
        logger.exception("Password field not present after loading login page: no selector matched")
        log_driver_state(driver, "linkedin_login_page_load")
        _save_driver_screenshot(driver, "login_page_load")
        raise RuntimeError("LinkedIn login page did not load correctly.")

    try:
        logger.debug("Filling login form and submitting")
        # Use send_keys where possible, fallback to JS assignment
        try:
            email_input.clear()
            email_input.send_keys(email)
        except Exception:
            try:
                js_set = (
                    "arguments[0].focus();"
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
                )
                driver.execute_script(js_set, email_input, email)
            except Exception:
                logger.exception("Failed to set email input value")

        # verify email value
        try:
            actual_email = None
            try:
                actual_email = driver.execute_script("return arguments[0].value;", email_input)
            except Exception:
                actual_email = email_input.get_attribute("value")
            logger.debug("Email input value after set: %s", actual_email)
            if (actual_email or "") != (email or ""):
                logger.warning("Email field value mismatch after set: expected=%s actual=%s", email, actual_email)
        except Exception:
            logger.exception("Failed to verify email input value")

        try:
            password_input.clear()
            password_input.send_keys(password)
        except Exception:
            try:
                js_set_pw = (
                    "arguments[0].focus();"
                    "arguments[0].value = arguments[1];"
                    "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
                    "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));"
                )
                driver.execute_script(js_set_pw, password_input, password)
            except Exception:
                logger.exception("Failed to set password input value")

        # verify password value (may be masked but value attribute should be set)
        try:
            actual_pw = None
            try:
                actual_pw = driver.execute_script("return arguments[0].value;", password_input)
            except Exception:
                actual_pw = password_input.get_attribute("value")
            logger.debug("Password input value length after set: %s", len(actual_pw or ""))
            if not actual_pw:
                logger.warning("Password field appears empty after setting value")
        except Exception:
            logger.exception("Failed to verify password input value")

        # Try several ways to submit the form
        submitted = False
        btn = None
        try:
            btn = driver.find_element(By.XPATH, "//button[@type='submit']")
        except Exception:
            try:
                btn = driver.find_element(By.CSS_SELECTOR, "button")
            except Exception:
                btn = None

        if btn is not None:
            try:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                except Exception:
                    pass
                try:
                    ActionChains(driver).move_to_element(btn).click(btn).perform()
                    submitted = True
                except Exception:
                    try:
                        btn.click()
                        submitted = True
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", btn)
                            submitted = True
                        except Exception:
                            logger.exception("Failed clicking submit button via any method")
            except Exception:
                logger.exception("Unexpected error while attempting to locate/click submit button")

        # If clicking didn't work, try pressing Enter on the password input
        if not submitted:
            try:
                try:
                    password_input.send_keys(Keys.ENTER)
                    submitted = True
                except Exception:
                    try:
                        driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', {'key':'Enter'}));", password_input)
                        submitted = True
                    except Exception:
                        pass
            except Exception:
                logger.exception("Failed to submit form via Enter key on password input")

        # Save a screenshot after submit attempts for diagnostics
        try:
            _save_driver_screenshot(driver, "login_after_submit_attempt")
        except Exception:
            logger.exception("Failed to save screenshot after submit attempt")

        if not submitted:
            try:
                # Last resort: submit the form via JS
                driver.execute_script("if(arguments[0] && arguments[0].form) arguments[0].form.submit();", email_input)
                submitted = True
            except Exception:
                try:
                    driver.execute_script("var f = document.querySelector('form'); if(f) f.submit();")
                    submitted = True
                except Exception:
                    logger.exception("Failed to submit login form via JS")

    except Exception as exc:
        logger.exception("Error while filling/submitting login form: %s", exc)
        log_driver_state(driver, "linkedin_login_form_submit")
        _save_driver_screenshot(driver, "login_form_submit")
        raise

    # Wait for signs of a successful login. LinkedIn uses dynamic DOMs; accept any
    # of: URL changed away from /login, search input present, or the Jobs nav link visible.
    post_login_ok = False
    start = time.time()
    timeout = 30
    selectors = [
        "input[aria-label*='Search']",
        "input[placeholder*='Search']",
        "input[placeholder*=\"I'm looking for\"]",
        "a[href*='/jobs']",
        "nav",
    ]
    while time.time() - start < timeout:
        try:
            cur = driver.current_url
        except Exception:
            cur = None
        # URL moved away from /login
        if cur and "/login" not in cur:
            post_login_ok = True
            logger.debug("Login appears successful based on URL change: %s", cur)
            break

        # Check for any of the selectors
        for sel in selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    for e in els:
                        try:
                            if e.is_displayed():
                                post_login_ok = True
                                logger.debug("Login appears successful based on selector match: %s", sel)
                                break
                        except Exception:
                            continue
                if post_login_ok:
                    break
            except Exception:
                continue

        if post_login_ok:
            break
        time.sleep(0.5)

    if not post_login_ok:
        logger.exception("Timeout waiting for post-login indicators")
        log_driver_state(driver, "linkedin_login_timeout")
        screenshot = _save_driver_screenshot(driver, "login_timeout")
        current_url = None
        try:
            current_url = driver.current_url
        except Exception:
            current_url = "<unknown>"
        if "login" in (current_url or "") or "checkpoint" in (current_url or ""):
            msg = "LinkedIn login failed. Check your credentials or additional verification."
        else:
            msg = f"LinkedIn login did not complete. Current URL: {current_url}. Screenshot: {screenshot}"
        raise RuntimeError(msg)


def scrape_linkedin_jobs(
    email: str,
    password: str,
    query: str,
    location: Optional[str] = None,
    pages: int = 2,
    headless: bool = True,
    remote_only: bool = False,
    chrome_binary_path: Optional[str] = None,
) -> pd.DataFrame:
    ensure_selenium_available()
    driver = None
    try:
        driver = create_chrome_driver(headless=headless, chrome_binary_path=chrome_binary_path)
        linkedin_login(driver, email, password)

        search_url = (
            "https://www.linkedin.com/jobs/search/?"
            f"keywords={quote_plus(query)}"
        )
        if remote_only:
            search_url += "&f_WT=2"
        elif location:
            search_url += f"&location={quote_plus(location)}"

        driver.get(search_url)
        wait = WebDriverWait(driver, 20)

        # LinkedIn DOM varies; accept any of several job-list selectors. Retry once by
        # clicking the Jobs nav link if nothing appears. Also perform small scrolls
        # to trigger lazy-loading of results.
        job_list_selectors = [
            "ul.jobs-search__results-list li",
            "ul.jobs-search-results__list li",
            "li.job-card-container",
            "div.jobs-search-results__list li",
            "div.base-card",
            "li.jobs-search-results__list-item",
            "div.job-card-search__content",
            "div.jobs-search-two-pane__results-list li",
        ]

        def find_job_cards():
            cards = []
            for sel in job_list_selectors:
                try:
                    els = driver.find_elements(By.CSS_SELECTOR, sel)
                    if els:
                        cards.extend([el for el in els if el.is_displayed()])
                        if cards:
                            return cards
                except Exception:
                    continue

            try:
                anchors = driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
                cards.extend([a for a in anchors if a.is_displayed()])
                if cards:
                    return cards
            except Exception:
                pass

            return []

        # Wait for any job card to appear
        start = time.time()
        cards = []
        while time.time() - start < 20:
            cards = find_job_cards()
            if cards:
                break
            time.sleep(0.5)

        # If still empty, try clicking the top Jobs nav link then retry
        if not cards:
            try:
                jobs_nav = driver.find_element(By.CSS_SELECTOR, "a[href*='/jobs']")
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", jobs_nav)
                except Exception:
                    pass
                try:
                    ActionChains(driver).move_to_element(jobs_nav).click(jobs_nav).perform()
                except Exception:
                    try:
                        jobs_nav.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", jobs_nav)
                time.sleep(1)
                driver.get(search_url)
            except Exception:
                logger.debug("Could not click Jobs nav link as retry")

            # retry finding cards with a slightly longer wait
            start = time.time()
            while time.time() - start < 25:
                cards = find_job_cards()
                if cards:
                    break
                # small scroll to trigger lazy load
                try:
                    driver.execute_script("window.scrollBy(0, 400);")
                except Exception:
                    pass
                time.sleep(0.5)

        time.sleep(1)

        job_cards = cards
        jobs = []
        seen_urls = set()
        for card in job_cards[: max(1, pages * 25)]:
            try:
                title = safe_find_text(
                    card,
                    "a.job-card-list__title, a.base-card__full-link, h3.base-search-card__title, h3.job-card-list__title, span[aria-hidden='true']",
                )
                url = None
                if card.tag_name.lower() == "a":
                    url = card.get_attribute("href")
                else:
                    for sel in [
                        "a.job-card-list__title",
                        "a.base-card__full-link",
                        "a[href*='/jobs/view/']",
                    ]:
                        try:
                            link = card.find_element(By.CSS_SELECTOR, sel)
                            url = link.get_attribute("href")
                            if url:
                                break
                        except Exception:
                            continue

                if not title or not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                company = safe_find_text(
                    card,
                    "h4.job-card-container__company-name, a.job-card-container__company-name, h4.base-search-card__subtitle, span.base-search-card__subtitle, p.job-card-container__company-name",
                )
                location_text = safe_find_text(
                    card,
                    "span.job-card-container__metadata-item, span.job-search-card__location, span.base-search-card__metadata, span.job-card-container__metadata-item",
                )
                easy_apply = "easy apply" in safe_find_text(card, ".job-card-container__apply-method, .jobs-apply-button, .job-card-container__easy-apply, .apply-button").lower()
                compensation_text = safe_find_text(card, ".job-card-container__salary-info, span.jobs-search-card__salary-info, div.salary, span.salary, span.base-search-card__meta").strip()
                jobs.append(
                    {
                        "title": title,
                        "company": company,
                        "location": location_text,
                        "description": "",
                        "url": url,
                        "easy_apply": easy_apply,
                        "salary_min": None,
                        "salary_max": None,
                        "compensation_text": compensation_text,
                    }
                )
            except Exception:
                continue

        for job in jobs:
            driver.get(job["url"])
            try:
                wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "div.show-more-less-html__markup, div.jobs-description-content__text",
                        )
                    )
                )
                job["description"] = safe_find_text(driver, "div.show-more-less-html__markup, div.jobs-description-content__text")
                if not job["description"]:
                    job["description"] = safe_find_text(driver, "div.description__text")
                easy_apply_label = safe_find_text(driver, "button.jobs-apply-button, span.jobs-apply-button__text")
                job["easy_apply"] = job["easy_apply"] or "easy apply" in easy_apply_label.lower()
                if not job["compensation_text"]:
                    job["compensation_text"] = safe_find_text(driver, "span.jobs-unified-top-card__salary, div.salary, span.salary")
            except TimeoutException:
                continue
            time.sleep(1)

        df = pd.DataFrame(jobs)
        if df.empty:
            raise RuntimeError("LinkedIn scraping returned no jobs. Check your query, location, and login state.")

        for col in ["location", "easy_apply", "salary_min", "salary_max", "compensation_text"]:
            if col not in df.columns:
                df[col] = None
        return df
    except Exception as exc:
        logger.exception("LinkedIn scraping failed: %s", exc)
        if driver:
            log_driver_state(driver, "linkedin_scraping_failure")
        raise
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as quit_exc:
                logger.exception("Failed to quit Chrome driver after scraping: %s", quit_exc)
