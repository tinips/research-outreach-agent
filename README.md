# Research Outreach Agent

Research Outreach Agent is a local, human-reviewed workflow for finding research outreach candidates, exporting shortlists, generating editable draft emails, and optionally sending reviewed drafts over SMTP.

It is designed for personal research outreach workflows. It does not automate social networks, does not send from GitHub Actions, and should not be used for unreviewed bulk email.

## What It Does

- Searches OpenAlex for recent papers around user-provided research topics.
- Scores and deduplicates candidate authors.
- Optionally performs limited public email lookup with SerpAPI.
- Writes candidate shortlists as Markdown, CSV, and JSON.
- Generates deterministic editable email drafts from `prompts/email_template.md`.
- Supports local SMTP dry runs, test sends, and capped real sends.

Generated candidates, seen history, drafts, logs, CVs, attachments, and credentials are local/private artifacts. Do not commit them to a public repository.

For a step-by-step guide to configuring the tool and personalizing draft emails, see [SETUP_AND_PERSONALIZATION.md](SETUP_AND_PERSONALIZATION.md).

## Setup

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

Create a local `.env` from the placeholder template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## Configuration

All values in `.env.example` are placeholders. Put real values only in your local `.env`.

Useful variables:

- `OPENALEX_EMAIL`: optional contact email for polite OpenAlex requests.
- `SERPAPI_API_KEY`: optional key for public email lookup.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`: SMTP sending settings.
- `SMTP_TEST_RECIPIENT`: where `--test` sends reviewed draft emails.
- `SENDER_NAME`, `SENDER_BACKGROUND`, `SENDER_GITHUB`, `SENDER_LINKEDIN`, `CV_LINK`: values used by the draft template.

Never commit `.env`, API keys, SMTP passwords, app passwords, CV files, attachments, candidate lists, generated drafts, logs, or seen-history files.

After editing `.env`, review `prompts/email_template.md` so the generated drafts match your background, links, and outreach style. The full checklist is in [SETUP_AND_PERSONALIZATION.md](SETUP_AND_PERSONALIZATION.md).

## Generate Candidates And Drafts

Generate a fresh shortlist and editable drafts without public email lookup:

```bash
python main.py generate --no-email-lookup
```

Generate with public email lookup enabled:

```bash
python main.py generate --email-lookup --email-lookup-provider serpapi
```

Use custom topics:

```bash
python main.py generate \
  --topics "LLM agents evaluation" "AI safety evaluation" "reproducible ML systems" \
  --limit 40 \
  --stretch-targets 3 \
  --realistic-targets 3 \
  --from-year 2023 \
  --output-dir outputs/latest
```

Outputs are written under `outputs/latest/`:

- `candidates.md`, `candidates.csv`, `candidates.json`
- `drafts.md`, `drafts.csv`, `drafts.json`

The `outputs/` directory is ignored except for `outputs/.gitkeep`.

## Regenerate Drafts From Candidates

Use this when you already have a candidate JSON file:

```bash
python main.py drafts --input examples/sample_candidates.json --output-dir outputs/example
```

By default, `drafts` reads `outputs/latest/candidates.json` and writes draft files to `outputs/latest/`.

## Review And Send Safely

Always review `drafts.md` or `drafts.json` before sending.

Preview without sending:

```bash
python main.py send --input outputs/latest/drafts.json --dry-run
```

Send valid drafts to `SMTP_TEST_RECIPIENT` only:

```bash
python main.py send --input outputs/latest/drafts.json --test --max-send 1
```

Send reviewed drafts to real recipients:

```bash
python main.py send --input outputs/latest/drafts.json --max-send 3
```

Attach a CV explicitly when needed:

```bash
python main.py send --input outputs/latest/drafts.json --dry-run --cv path/to/your_cv.pdf
```

If `--cv` is omitted, the sender looks for exactly one PDF in `attachments/` or `cv/`. Those directories are ignored by Git.

## API Mode

Run the FastAPI app locally:

```bash
uvicorn backend.main:app --reload
```

Open:

```text
http://localhost:8000/docs
```

The OpenAPI schema in `schemas/openapi.yaml` uses `http://localhost:8000` by default.

## Examples

The `examples/` directory contains synthetic files only:

- `sample_request.json`
- `sample_response.json`
- `sample_candidates.json`
- `sample_candidates.md`
- `sample_drafts.json`
- `sample_drafts.md`

They use fake names, fake institutions, and example domains. They are safe to commit.

## Development

Run tests:

```bash
python -m unittest discover
```

Check CLI help:

```bash
python main.py --help
python main.py generate --help
python main.py drafts --help
python main.py send --help
python main.py run --help
```

## Privacy Checklist

Before publishing or committing, confirm that these are not tracked:

- `.env` or other secret files
- `outputs/latest/` or any generated output files
- `data/*.csv` or `data/*.json`
- real candidate shortlists or seen history
- generated outreach drafts
- logs, screenshots, caches, CVs, attachments
- personal email addresses, profile links, or private workflow notes

This repository should contain the reusable tool and synthetic examples only.
