# Setup And Personalization Guide

Use this guide after cloning the repository and before generating real outreach drafts. The goal is to make every draft reflect your identity, your background, and your review process without committing private data.

## 1. Create Your Local Environment

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a private `.env` file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Do not commit `.env`.

## 2. Fill In Your `.env`

Start with these identity fields:

```text
SENDER_NAME="Example Sender"
SENDER_BACKGROUND="a researcher/engineer working on reproducible AI systems"
SENDER_GITHUB=https://github.com/your-username
SENDER_LINKEDIN=https://www.linkedin.com/in/your-profile
CV_LINK=attached CV
SENDER_EMAIL=you@example.com
```

Use wording that is true and specific. Good `SENDER_BACKGROUND` examples:

- `a master's student working on trustworthy machine learning systems`
- `a software engineer interested in reproducible AI evaluation`
- `a research assistant building data pipelines for machine learning experiments`

Optional discovery and email lookup:

```text
OPENALEX_EMAIL=you@example.com
SERPAPI_API_KEY=your_serpapi_api_key_here
```

SMTP settings for reviewed sends:

```text
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your_smtp_username
SMTP_PASSWORD=your_smtp_password
SMTP_FROM=you@example.com
SMTP_TEST_RECIPIENT=test-recipient@example.com
```

Use an app password when your email provider requires it. Never commit SMTP credentials.

## 3. Personalize The Draft Template

Edit:

```text
prompts/email_template.md
```

The default template uses these placeholders:

- `{sender_name}`
- `{sender_background}`
- `{sender_github}`
- `{sender_linkedin}`
- `{cv_link}`
- `{recipient_name}`
- `{paper_title}`
- `{specific_interest}`
- `{contribution_angle}`
- `{optional_compute_sentence}`
- `{closing_question}`
- `{topic_or_area}`

Keep placeholder names exactly as written unless you also update `backend/draft_generator.py`.

Before using real drafts, check that the template:

- introduces you accurately
- does not exaggerate your role, credentials, or availability
- includes only links you want recipients to see
- mentions a CV only if you will attach or link one
- sounds like a short human note, not a mass email
- does not promise unpaid work, bulk availability, or guaranteed results

## 4. Prepare Your CV Or Links

If you want to attach a CV, keep the PDF outside Git-tracked files. The repo ignores:

```text
attachments/
cv/
*.pdf
```

You can pass a CV explicitly:

```bash
python main.py send --input outputs/latest/drafts.json --dry-run --cv path/to/your_cv.pdf
```

If you do not attach a CV, change `CV_LINK` and the template wording to something accurate, such as:

```text
CV_LINK=https://example.com/your-cv
```

or remove the CV line from `prompts/email_template.md`.

## 5. Generate A Small Test Batch

Start without public email lookup:

```bash
python main.py generate \
  --topics "LLM agents evaluation" "reproducible ML systems" \
  --limit 10 \
  --stretch-targets 1 \
  --realistic-targets 1 \
  --no-email-lookup
```

Review:

```text
outputs/latest/candidates.md
outputs/latest/drafts.md
```

The generated `outputs/` files are private local artifacts. Do not commit them.

## 6. Review Draft Quality

Before sending anything, check every draft for:

- correct sender name and background
- correct recipient name
- real paper title and topic
- no invented claims about your experience
- no invented contact details
- no stale links
- no private notes or internal workflow comments
- no generic wording that feels spammy

Generated drafts are starting points, not final emails.

## 7. Test SMTP Safely

Preview without sending:

```bash
python main.py send --input outputs/latest/drafts.json --dry-run
```

Send one reviewed draft to `SMTP_TEST_RECIPIENT`:

```bash
python main.py send --input outputs/latest/drafts.json --test --max-send 1
```

Only after checking the test email should you send to real recipients:

```bash
python main.py send --input outputs/latest/drafts.json --max-send 1
```

Increase `--max-send` slowly and deliberately.

## 8. Keep Private Data Out Of Git

Before committing, run:

```bash
git status --short
git ls-files | rg "^(data/.*\.(csv|json)|outputs/|.*\.env$|.*\.pdf$)"
```

Nothing private should be tracked. Keep these local only:

- `.env`
- candidate outputs
- seen-history files
- generated drafts
- logs
- CVs and attachments
- email lookup evidence
- personal notes about candidates

## 9. Suggested First Run Checklist

- [ ] `.env` exists locally and is not tracked.
- [ ] `SENDER_NAME` and `SENDER_BACKGROUND` are accurate.
- [ ] profile links and CV wording are correct.
- [ ] `SMTP_TEST_RECIPIENT` points to an inbox you control.
- [ ] `prompts/email_template.md` matches your style.
- [ ] a small `--no-email-lookup` generation run works.
- [ ] `outputs/latest/drafts.md` has been manually reviewed.
- [ ] `send --dry-run` looks correct.
- [ ] `send --test --max-send 1` sends only to the test inbox.
