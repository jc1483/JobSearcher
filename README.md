# LinkedIn Job Matcher (safe/manual-review version)

This utility logs in to LinkedIn, scrapes job postings, and ranks them against your resume and target compensation.
It does not auto-submit applications.

## What it does
- Scrapes LinkedIn job listings after logging in with your LinkedIn credentials.
- Scores jobs against your resume keywords and target salary range.
- Separates jobs into:
  - `ranked_easy_apply_jobs.csv` (jobs marked Easy Apply)
  - `ranked_manual_review_jobs.csv` (strong matches that are not Easy Apply)
- Optionally opens the top Easy Apply job URLs in your browser tabs for manual review.

## Usage
Run the script with an encrypted credentials file and a resume file:

```bash
python linkedin_job_matcher.py \
  --credentials-file linkedin_credentials.json \
  --credentials-passphrase your-passphrase \
  --linkedin-query "QA automation" \
  --resume resume.pdf
```

You can optionally provide a JSON config file for salary range and LinkedIn defaults. The resume itself now drives keyword and title scoring weights automatically, and the web UI auto-generates the LinkedIn search query from the resume.

```bash
python linkedin_job_matcher.py \
  --credentials-file linkedin_credentials.json \
  --credentials-passphrase your-passphrase \
  --resume resume.pdf \
  --config-file job_match_config.json
```

Add `--remote-only` to search remote roles only, or omit it to search all roles in the configured location.

Sample `job_match_config.json`:

```json
{
  "credentials_file": "linkedin_credentials.json",
  "linkedin_location": "United States",
  "linkedin_pages": 2,
  "resume": "resume.pdf",
  "output_dir": "job_match_outputs",
  "top": 25,
  "min_salary": 120000,
  "max_salary": 150000,
  "remote_only": false,
  "chrome_binary_path": ""
}
```

> Note: secure LinkedIn credentials are stored separately in an encrypted credentials file. Do not keep `linkedin_email` or `linkedin_password` in plain text within your config.

If Chrome/Chromium is not installed in a standard location, set `chrome_binary_path` to the browser executable path or export `CHROME_BINARY_PATH`.

### Web UI
Launch the local web UI with:

```bash
python linkedin_job_matcher.py --webui
```

This will start a local Flask server and print the URL in the terminal. By default the app listens on `http://127.0.0.1:5000/`.

Open that URL in your browser, then use the form to:
- choose whether to search remote roles only or all roles in the selected location
- choose resume and output paths
- set salary minimum/maximum
- provide LinkedIn email, password, and a credentials passphrase if encrypted credentials are missing
- run the job search and view ranked results

The web UI automatically generates the LinkedIn query from your resume text, so you do not need to enter a search query manually. It also generates `job_match_config.json` on first launch if it does not already exist, and will prompt for LinkedIn email, password, and a passphrase if encrypted credentials are missing.

To customize host or port, use:

```bash
python linkedin_job_matcher.py --webui --host 0.0.0.0 --port 8080
```

If Selenium cannot locate your browser, install Google Chrome or Chromium and then start the app with an explicit binary path. If `chrome_binary_path` is left blank, the app will still search common default locations and standard PATH entries first.

On Windows, the default Chrome executable path is usually:
`C:\Program Files\Google\Chrome\Application\chrome.exe`

```bash
python linkedin_job_matcher.py --webui --chrome-binary "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

If you do not have Chrome installed, download it from https://www.google.com/chrome/.

Then open the printed host URL in your browser to use the app.

To create or update the encrypted credentials file using the built-in mode:

```bash
python linkedin_job_matcher.py \
  --create-credentials \
  --credentials-file linkedin_credentials.json \
  --credentials-passphrase your-passphrase \
  --linkedin-email you@example.com \
  --linkedin-password yourpassword
```

If you omit `--linkedin-password` or `--credentials-passphrase`, the command will prompt securely for them.

Or use the standalone helper script:

```bash
python create_linkedin_credentials.py \
  --credentials-file linkedin_credentials.json \
  --credentials-passphrase your-passphrase \
  --linkedin-email you@example.com
```

If you omit `--linkedin-password`, the script will prompt securely for it.

The helper script will prompt securely for the password and passphrase if they are omitted.

## Supported resume formats
- `.txt`
- `.md`
- `.rtf`
- `.pdf`
- `.docx`

PDF support requires `PyPDF2`.
Word (.docx) support requires `python-docx`.
Encrypted credentials require `cryptography`.
Web UI support requires `Flask`.

Install runtime dependencies with:

```bash
pip install -r requirements.txt
```

## Notes
The script no longer accepts CSV or JSON job input; it only works by scraping LinkedIn directly.
``