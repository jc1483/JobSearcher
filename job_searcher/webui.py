from __future__ import annotations

import threading
from pathlib import Path

try:
    from flask import Flask, render_template_string, request, send_from_directory
except ImportError:
    Flask = None
    render_template_string = None
    request = None
    send_from_directory = None

from .config import (
    DEFAULT_CONFIG_FILE,
    apply_config_defaults,
    create_default_config,
    ensure_credentials_from_config,
    load_config,
    save_config,
)
from .credentials import create_encrypted_credentials, load_credentials
from .linkedin_scraper import scrape_linkedin_jobs
from .matching import JobMatcher
from .outputs import get_output_files, serialize_matches, write_outputs
from .resume_parser import extract_resume_text
from .utils import derive_search_query

WEBUI_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>LinkedIn Job Matcher Web UI</title>
  <style>
    body {
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      margin: 0;
      background: linear-gradient(135deg, #0f172a 0%, #1e293b 60%, #334155 100%);
      color: #e2e8f0;
    }
    .page-wrapper {
      max-width: 1080px;
      margin: 0 auto;
      padding: 28px;
    }
    h1 {
      margin: 0 0 16px;
      font-size: 2.4rem;
      letter-spacing: -0.03em;
      color: #f8fafc;
    }
    p.lead {
      max-width: 760px;
      color: #cbd5e1;
      margin-top: 0;
    }
    label {
      display: block;
      margin-top: 12px;
      font-weight: 600;
    }
    input[type=text], input[type=password], input[type=number] {
      width: 100%;
      max-width: 100%;
      padding: 10px 14px;
      margin-top: 6px;
      border: 1px solid #334155;
      border-radius: 10px;
      background: #0f172a;
      color: #e2e8f0;
    }
    input[type=number] {
      max-width: 240px;
    }
    button {
      margin-top: 18px;
      padding: 14px 22px;
      border: none;
      border-radius: 12px;
      background: #38bdf8;
      color: #0f172a;
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
      box-shadow: 0 12px 24px rgba(56, 189, 248, 0.25);
    }
    button:hover {
      transform: translateY(-1px);
      box-shadow: 0 16px 28px rgba(56, 189, 248, 0.28);
    }
    .section {
      margin-bottom: 28px;
      padding: 24px;
      border-radius: 22px;
      background: rgba(15, 23, 42, 0.92);
      box-shadow: 0 18px 40px rgba(15, 23, 42, 0.18);
    }
    .section h2 {
      margin-top: 0;
      color: #f8fafc;
    }
    table {
      border-collapse: collapse;
      width: 100%;
      margin-top: 16px;
      background: rgba(15, 23, 42, 0.96);
    }
    th, td {
      border: 1px solid #334155;
      padding: 14px 12px;
      text-align: left;
      color: #e2e8f0;
    }
    th {
      background: #1e293b;
      color: #f8fafc;
    }
    .error {
      color: #fda4af;
      margin-top: 12px;
    }
    .success {
      color: #a7f3d0;
      margin-top: 12px;
    }
    .link-list a {
      display: block;
      margin-bottom: 6px;
      color: #38bdf8;
      text-decoration: none;
    }
    .link-list a:hover {
      text-decoration: underline;
    }
    .progress-panel {
      display: none;
      margin-bottom: 20px;
      padding: 18px;
      border-radius: 18px;
      background: rgba(51, 65, 85, 0.92);
    }
    .progress-bar-shell {
      height: 18px;
      background: #1e293b;
      border-radius: 12px;
      overflow: hidden;
      margin-top: 12px;
    }
    .progress-bar-fill {
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, #38bdf8, #0ea5e9);
      transition: width 0.3s ease;
    }
    .status-detail {
      margin-top: 12px;
      color: #cbd5e1;
      font-size: 0.98rem;
    }
  </style>
</head>
<body>
  <div class="page-wrapper">
    <h1>LinkedIn Job Matcher</h1>
    <p class="lead">Run a targeted LinkedIn job search with resume-based scoring and instant ranked output files.</p>
    <form method="post" action="{{ url_for('run_job_search') }}">
    <div class="section">
      <h2>Credentials</h2>
      {% if params.get('credentials_available') %}
      <p>Stored credentials were found. Enter your passphrase to decrypt and autofill the saved email and password.</p>
      {% elif params.get('credentials_required') %}
      <p>Encrypted credentials are missing. Enter LinkedIn email, password, and a passphrase to generate them now.</p>
      {% else %}
      <p>Enter the passphrase to decrypt stored credentials, or supply email/password to regenerate the encrypted file.</p>
      {% endif %}
      <label>LinkedIn email
        <input type="text" name="linkedin_email" value="{{ params.get('linkedin_email','') }}" {% if params.get('credentials_required') and not params.get('credentials_available') %}required{% endif %} />
      </label>
      <label>LinkedIn password
        <input type="password" name="linkedin_password" value="{{ params.get('linkedin_password','') }}" {% if params.get('credentials_required') and not params.get('credentials_available') %}required{% endif %} />
      </label>
      <label>Credentials passphrase
        <input type="password" name="credentials_passphrase" value="{{ params.get('credentials_passphrase','') }}" required />
      </label>
    </div>
    <div class="section">
      <h2>Search settings</h2>
      <label><input type="checkbox" name="remote_only" {% if params.get('remote_only') %}checked{% endif %} /> Search remote roles only</label>
      <label>LinkedIn location (ignored for remote-only searches)
        <input type="text" name="linkedin_location" value="{{ params.get('linkedin_location','United States') }}" />
      </label>
      <label>Result pages
        <input type="number" name="linkedin_pages" value="{{ params.get('linkedin_pages',2) }}" min="1" max="10" />
      </label>
      <label>Resume file path
        <input type="text" name="resume" value="{{ params.get('resume','') }}" required />
      </label>
      <label>Output directory
        <input type="text" name="output_dir" value="{{ params.get('output_dir','job_match_outputs') }}" />
      </label>
      <label>Chrome / Chromium binary path (optional)
        <input type="text" name="chrome_binary_path" value="{{ params.get('chrome_binary_path','') }}" />
      </label>
      <label>Top results
        <input type="number" name="top" value="{{ params.get('top',25) }}" min="1" max="100" />
      </label>
      <label>Minimum salary override
        <input type="number" name="min_salary" value="{{ params.get('min_salary','') }}" />
      </label>
      <label>Maximum salary override
        <input type="number" name="max_salary" value="{{ params.get('max_salary','') }}" />
      </label>
      <label><input type="checkbox" name="no_headless" {% if params.get('no_headless') %}checked{% endif %} /> Run browser visible</label>
    </div>
    <button type="submit">Run job search</button>
  </form>

  <div id="progress-panel" class="progress-panel">
    <strong>Job search in progress</strong>
    <div class="progress-bar-shell">
      <div id="progress-bar" class="progress-bar-fill"></div>
    </div>
    <div id="progress-text" class="status-detail">Preparing search...</div>
  </div>

  {% if error %}
  <div class="error">{{ error }}</div>
  {% endif %}

  {% if matches %}
  <div class="section">
    <h2>Output files</h2>
    <div class="link-list">
      {% for file in output_files %}
        <a href="{{ url_for('download_output', filename=file) }}">{{ file }}</a>
      {% endfor %}
    </div>
  </div>
  <div class="section">
    <h2>Matching jobs</h2>
    <table>
      <thead>
        <tr>
          <th>Title</th>
          <th>Company</th>
          <th>Location</th>
          <th>Score</th>
          <th>Easy Apply</th>
          <th>Link</th>
        </tr>
      </thead>
      <tbody>
      {% for match in matches %}
        <tr>
          <td>{{ match.title }}</td>
          <td>{{ match.company }}</td>
          <td>{{ match.location }}</td>
          <td>{{ match.score }}</td>
          <td>{{ 'Yes' if match.easy_apply else 'No' }}</td>
          <td><a href="{{ match.url }}" target="_blank">View</a></td>
        </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>
  {% endif %}
  <script>
    const form = document.querySelector('form');
    const progressPanel = document.getElementById('progress-panel');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    const errorContainer = document.querySelector('.error');
    let progressTimer = null;

    function setProgress(value, message) {
      progressBar.style.width = `${value}%`;
      progressText.textContent = message;
    }

    async function fetchProgress() {
      try {
        const response = await fetch('/progress');
        if (!response.ok) {
          throw new Error('Unable to retrieve progress status.');
        }
        const data = await response.json();
        if (data.error) {
          setProgress(100, data.status_text || 'Error encountered.');
          return data;
        }
        setProgress(data.progress || 0, data.status_text || 'Starting...');
        return data;
      } catch (error) {
        setProgress(100, error.message);
        return { in_progress: false, error: error.message };
      }
    }

    function startProgressPolling() {
      progressPanel.style.display = 'block';
      setProgress(5, 'Initializing job search...');
      progressTimer = setInterval(async () => {
        const data = await fetchProgress();
        if (!data.in_progress) {
          clearInterval(progressTimer);
          progressTimer = null;
        }
      }, 1200);
    }

    async function waitForCompletion() {
      let data = await fetchProgress();
      while (data.in_progress) {
        await new Promise((resolve) => setTimeout(resolve, 1200));
        data = await fetchProgress();
      }
      return data;
    }

    async function submitSearch(event) {
      event.preventDefault();
      if (progressTimer) {
        clearInterval(progressTimer);
      }
      progressPanel.style.display = 'block';
      setProgress(5, 'Starting job search...');
      startProgressPolling();

      const formData = new FormData(form);
      try {
        const response = await fetch('/run', {
          method: 'POST',
          body: formData,
        });
        const result = await response.json();
        if (!result.success) {
          clearInterval(progressTimer);
          progressTimer = null;
          setProgress(100, result.error || 'Job search failed.');
          if (errorContainer) {
            errorContainer.textContent = result.error || 'Job search failed.';
          }
          return;
        }

        const finalStatus = await waitForCompletion();
        if (finalStatus.error) {
          clearInterval(progressTimer);
          progressTimer = null;
          setProgress(100, finalStatus.error);
          if (errorContainer) {
            errorContainer.textContent = finalStatus.error;
          }
          return;
        }

        window.location.reload();
      } catch (error) {
        clearInterval(progressTimer);
        progressTimer = null;
        setProgress(100, error.message);
        if (errorContainer) {
          errorContainer.textContent = error.message;
        }
      }
    }

    form.addEventListener('submit', submitSearch);
  </script>
</body>
</html>
"""


def ensure_flask_available() -> None:
    if Flask is None:
        raise ImportError(
            "Web UI requires Flask. Install it with: pip install flask"
        )


def create_webui_app():
    ensure_flask_available()
    app = Flask(__name__)
    state = {
        "params": {},
        "matches": [],
        "output_dir": Path("job_match_outputs"),
        "output_files": [],
        "error": None,
        "progress": 0,
        "status_text": "Idle",
        "in_progress": False,
        "credentials_required": False,
    }

    @app.route("/", methods=["GET"])
    def index():
        if not state["params"]:
            try:
                create_default_config(DEFAULT_CONFIG_FILE)
                config = load_config(DEFAULT_CONFIG_FILE)
                state["params"]["config_file"] = str(DEFAULT_CONFIG_FILE)
                apply_config_defaults(state["params"], config)
                ensure_credentials_from_config(config)
                credentials_path = Path(state["params"].get("credentials_file", str(DEFAULT_CONFIG_FILE.with_name("linkedin_credentials.json"))))
                state["params"]["credentials_available"] = credentials_path.exists()
                state["params"]["credentials_required"] = True
                if credentials_path.exists():
                    if state["params"].get("credentials_passphrase"):
                        try:
                            email, password = load_credentials(credentials_path, state["params"].get("credentials_passphrase", ""))
                            state["params"]["linkedin_email"] = email
                            state["params"]["linkedin_password"] = password
                        except Exception:
                            # Leave the fields blank until a valid passphrase is provided
                            state["params"]["linkedin_email"] = ""
                            state["params"]["linkedin_password"] = ""
                    else:
                        state["params"]["linkedin_email"] = ""
                        state["params"]["linkedin_password"] = ""
            except Exception as exc:
                state["error"] = f"Unable to load default config: {exc}"
            state["params"].setdefault("credentials_file", str(DEFAULT_CONFIG_FILE.with_name("linkedin_credentials.json")))
            state["params"].setdefault("linkedin_location", "United States")
            state["params"].setdefault("linkedin_pages", "2")
            state["params"].setdefault("output_dir", "job_match_outputs")
            state["params"].setdefault("chrome_binary_path", "")
            state["params"].setdefault("top", "25")
            state["params"].setdefault("credentials_required", True)
            state["params"].setdefault("credentials_available", False)

        return render_template_string(
            WEBUI_TEMPLATE,
            params=state["params"],
            matches=state["matches"],
            output_files=state["output_files"],
            error=state["error"],
        )

    def _run_job_search_background_obsolete():
        state["error"] = None
        state["params"] = {
            "config_file": "",
            "credentials_file": "",
            "credentials_passphrase": request.form.get("credentials_passphrase", ""),
            "linkedin_email": request.form.get("linkedin_email", ""),
            "linkedin_password": request.form.get("linkedin_password", ""),
            "linkedin_location": request.form.get("linkedin_location", "United States"),
            "linkedin_pages": request.form.get("linkedin_pages", "2"),
            "remote_only": request.form.get("remote_only") == "on",
            "resume": request.form.get("resume", ""),
            "output_dir": request.form.get("output_dir", "job_match_outputs"),
            "chrome_binary_path": request.form.get("chrome_binary_path", ""),
            "top": request.form.get("top", "25"),
            "min_salary": request.form.get("min_salary", ""),
            "max_salary": request.form.get("max_salary", ""),
            "no_headless": request.form.get("no_headless") == "on",
        }

        try:
            if not state["params"].get("config_file"):
                create_default_config(DEFAULT_CONFIG_FILE)
                state["params"]["config_file"] = str(DEFAULT_CONFIG_FILE)

            state["progress"] = 5
            state["status_text"] = "Loading config and credentials..."
            state["in_progress"] = True

            config = load_config(Path(state["params"]["config_file"]))
            apply_config_defaults(state["params"], config)
            save_config(Path(state["params"]["config_file"]), state["params"])
            ensure_credentials_from_config(config)

            state["progress"] = 15
            state["status_text"] = "Preparing encrypted credentials..."

            if not state["params"].get("credentials_file"):
                state["params"]["credentials_file"] = str(
                    Path(state["params"]["config_file"]).with_name("linkedin_credentials.json")
                )

            credentials_path = Path(state["params"]["credentials_file"])
            if not credentials_path.exists():
                email = state["params"].get("linkedin_email", "").strip()
                password = state["params"].get("linkedin_password", "").strip()
                passphrase = state["params"].get("credentials_passphrase", "").strip()
                if email and password and passphrase:
                    create_encrypted_credentials(credentials_path, email, password, passphrase)
                    state["status_text"] = "Encrypted credentials generated."
                else:
                    raise RuntimeError(
                        "Encrypted credentials not found. Provide LinkedIn email, password, and passphrase to create them."
                    )

            state["progress"] = 35
            state["status_text"] = "Decrypting stored LinkedIn credentials..."

            if credentials_path.exists():
                passphrase = state["params"].get("credentials_passphrase", "").strip()
                if not passphrase:
                    raise RuntimeError(
                        "Enter the credentials passphrase to decrypt your existing LinkedIn credentials."
                    )
                email, password = load_credentials(
                    credentials_path,
                    passphrase,
                )
                state["params"]["linkedin_email"] = email
                state["params"]["linkedin_password"] = password
            else:
                email = state["params"].get("linkedin_email", "").strip()
                password = state["params"].get("linkedin_password", "").strip()

            state["progress"] = 40
            state["status_text"] = "Extracting resume content..."
            resume_text = extract_resume_text(Path(state["params"]["resume"]))
            search_query = derive_search_query(resume_text)

            desired_min = None
            desired_max = None
            if state["params"].get("min_salary"):
                desired_min = int(state["params"]["min_salary"])
            if state["params"].get("max_salary"):
                desired_max = int(state["params"]["max_salary"])
            if desired_min is None and config:
                desired_min = config.get("salary_min")
            if desired_max is None and config:
                desired_max = config.get("salary_max")

            state["progress"] = 45
            state["status_text"] = "Logging in and scraping LinkedIn jobs..."

            df = scrape_linkedin_jobs(
                email=email,
                password=password,
                query=search_query,
                location=state["params"]["linkedin_location"],
                pages=int(state["params"]["linkedin_pages"]),
                headless=not state["params"]["no_headless"],
                remote_only=state["params"].get("remote_only", False),
                chrome_binary_path=state["params"].get("chrome_binary_path", ""),
            )

            state["progress"] = 55
            state["status_text"] = "Scoring jobs against your resume and salary range..."
            matcher = JobMatcher(
                resume_text,
                desired_min,
                desired_max,
            )
            matches = matcher.rank(df)

            state["progress"] = 85
            state["status_text"] = "Writing ranked outputs..."
            state["output_dir"] = Path(state["params"]["output_dir"])
            write_outputs(matches, state["output_dir"], int(state["params"]["top"]))
            state["output_files"] = get_output_files(state["output_dir"])
            state["matches"] = serialize_matches(matches)

            state["progress"] = 100
            state["status_text"] = "Job search complete."
            state["in_progress"] = False
            state["error"] = None
        except Exception as exc:
            state["error"] = str(exc)
            state["matches"] = []
            state["output_files"] = []
            state["progress"] = 100
            state["status_text"] = "Error encountered."
            state["in_progress"] = False

    def run_job_search_background():
        try:
            config = load_config(Path(state["params"]["config_file"]))
            apply_config_defaults(state["params"], config)
            save_config(Path(state["params"]["config_file"]), state["params"])
            ensure_credentials_from_config(config)

            state["progress"] = 15
            state["status_text"] = "Preparing encrypted credentials..."

            if not state["params"].get("credentials_file"):
                state["params"]["credentials_file"] = str(
                    Path(state["params"]["config_file"]).with_name("linkedin_credentials.json")
                )

            credentials_path = Path(state["params"]["credentials_file"])
            if not credentials_path.exists():
                email = state["params"].get("linkedin_email", "").strip()
                password = state["params"].get("linkedin_password", "").strip()
                passphrase = state["params"].get("credentials_passphrase", "").strip()
                if email and password and passphrase:
                    create_encrypted_credentials(credentials_path, email, password, passphrase)
                    state["status_text"] = "Encrypted credentials generated."
                else:
                    raise RuntimeError(
                        "Encrypted credentials not found. Provide LinkedIn email, password, and passphrase to create them."
                    )

            state["progress"] = 35
            state["status_text"] = "Decrypting stored LinkedIn credentials..."

            if credentials_path.exists():
                passphrase = state["params"].get("credentials_passphrase", "").strip()
                if not passphrase:
                    raise RuntimeError(
                        "Enter the credentials passphrase to decrypt your existing LinkedIn credentials."
                    )
                email, password = load_credentials(
                    credentials_path,
                    passphrase,
                )
                state["params"]["linkedin_email"] = email
                state["params"]["linkedin_password"] = password
            else:
                email = state["params"].get("linkedin_email", "").strip()
                password = state["params"].get("linkedin_password", "").strip()

            state["progress"] = 40
            state["status_text"] = "Extracting resume content..."
            resume_text = extract_resume_text(Path(state["params"]["resume"]))
            search_query = derive_search_query(resume_text)

            desired_min = None
            desired_max = None
            if state["params"].get("min_salary"):
                desired_min = int(state["params"].get("min_salary"))
            if state["params"].get("max_salary"):
                desired_max = int(state["params"].get("max_salary"))
            if desired_min is None and config:
                desired_min = config.get("salary_min")
            if desired_max is None and config:
                desired_max = config.get("salary_max")

            state["progress"] = 45
            state["status_text"] = "Logging in and scraping LinkedIn jobs..."

            df = scrape_linkedin_jobs(
                email=email,
                password=password,
                query=search_query,
                location=state["params"]["linkedin_location"],
                pages=int(state["params"]["linkedin_pages"]),
                headless=not state["params"]["no_headless"],
                remote_only=state["params"].get("remote_only", False),
                chrome_binary_path=state["params"].get("chrome_binary_path", ""),
            )

            state["progress"] = 55
            state["status_text"] = "Scoring jobs against your resume and salary range..."
            matcher = JobMatcher(
                resume_text,
                desired_min,
                desired_max,
            )
            matches = matcher.rank(df)

            state["progress"] = 85
            state["status_text"] = "Writing ranked outputs..."
            state["output_dir"] = Path(state["params"]["output_dir"])
            write_outputs(matches, state["output_dir"], int(state["params"]["top"]))
            state["output_files"] = get_output_files(state["output_dir"])
            state["matches"] = serialize_matches(matches)

            state["progress"] = 100
            state["status_text"] = "Job search complete."
            state["in_progress"] = False
            state["error"] = None
        except Exception as exc:
            state["error"] = str(exc)
            state["matches"] = []
            state["output_files"] = []
            state["progress"] = 100
            state["status_text"] = "Error encountered."
            state["in_progress"] = False

    @app.route("/run", methods=["POST"])
    def run_job_search():
        if state["in_progress"]:
            return {"success": False, "error": "A job search is already in progress."}

        state["error"] = None
        state["params"] = {
            "config_file": "",
            "credentials_file": "",
            "credentials_passphrase": request.form.get("credentials_passphrase", ""),
            "linkedin_email": request.form.get("linkedin_email", ""),
            "linkedin_password": request.form.get("linkedin_password", ""),
            "linkedin_location": request.form.get("linkedin_location", "United States"),
            "linkedin_pages": request.form.get("linkedin_pages", "2"),
            "remote_only": request.form.get("remote_only") == "on",
            "resume": request.form.get("resume", ""),
            "output_dir": request.form.get("output_dir", "job_match_outputs"),
            "chrome_binary_path": request.form.get("chrome_binary_path", ""),
            "top": request.form.get("top", "25"),
            "min_salary": request.form.get("min_salary", ""),
            "max_salary": request.form.get("max_salary", ""),
            "no_headless": request.form.get("no_headless") == "on",
        }

        if not state["params"].get("config_file"):
            create_default_config(DEFAULT_CONFIG_FILE)
            state["params"]["config_file"] = str(DEFAULT_CONFIG_FILE)

        state["progress"] = 5
        state["status_text"] = "Loading config and credentials..."
        state["in_progress"] = True

        worker = threading.Thread(target=run_job_search_background, daemon=True)
        worker.start()
        return {"success": True, "message": "Job search started."}

    @app.route("/progress", methods=["GET"])
    def progress():
        return {
            "progress": state["progress"],
            "status_text": state["status_text"],
            "in_progress": state["in_progress"],
            "error": state["error"],
        }

    @app.route("/outputs/<path:filename>")
    def download_output(filename: str):
        return send_from_directory(state["output_dir"], filename, as_attachment=True)

    return app


def run_webui(host: str = "127.0.0.1", port: int = 5000) -> None:
    app = create_webui_app()
    print(f"Starting web UI on http://{host}:{port}/")
    app.run(host=host, port=port)
