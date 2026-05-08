# Research Outreach Agent

Research Outreach Agent is an MVP for AI research opportunity discovery across broad AI areas, prioritizing strong labs, recent papers, project activity, and contactable researchers.

The project combines a Custom GPT conversational interface with local OpenAlex search tooling. FastAPI/GPT Actions remain available, but the project can also run entirely outside ChatGPT and export files that a Custom GPT can read from GitHub.

## Public Repository Notice

This public repository contains the source code, documentation, prompts, templates, and fake/example outputs for the Research Outreach Agent. Real generated candidates, outreach drafts, contact tracking files, API keys, and private workflow outputs are kept outside this public repository.

The tool is designed for human-reviewed outreach. It does not send emails automatically.

## Architecture

```text
Custom GPT -> GPT Actions -> FastAPI backend -> OpenAlex
```

## Current MVP Features

- FastAPI backend with `/health` and `/search_researchers`.
- Broad AI discovery using OpenAlex `/works`.
- Relevance-first discovery with optional citation or recency sorting.
- Paper-author flattening into researcher candidate rows.
- Paper-diverse candidate selection that avoids returning many authors from the same paper by default.
- One recommended contact per paper by default, configurable with `max_authors_per_paper`.
- Deduplication by OpenAlex author ID or normalized author name.
- Rule-based scoring for lab signal, paper signal, project activity, contactability, contribution angle, and weak profile fit.
- CLI search workflow that exports CSV, JSON, and Markdown to `outputs/latest`.
- Optional API CSV export to `outputs/candidates.csv`.
- GPT Actions OpenAPI schema.
- Custom GPT instructions for human-reviewed outreach drafting.

## Planned Features

- Semantic Scholar and arXiv search actions.
- Better public project, GitHub, dataset, demo, and benchmark detection.
- Better candidate role detection for PhD students, postdocs, assistant professors, and research scientists.
- Editable outreach draft generation.
- Google Sheets export.
- API key authentication before public deployment.

This project does not implement automatic email sending, bulk outreach, LinkedIn automation, scraping, Gmail integration, authentication, or a database.

## Setup On Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Optionally copy `.env.example` to `.env` and set `OPENALEX_EMAIL` so OpenAlex receives a polite `mailto` parameter.

## Optional Unix/macOS Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

The API will run at:

```text
http://127.0.0.1:8000
```

## Test

Open the interactive API docs:

```text
http://127.0.0.1:8000/docs
```

Example request body:

```json
{
  "topic": "artificial intelligence",
  "limit": 5,
  "save_csv": true,
  "max_authors_per_paper": 1,
  "from_year": 2023,
  "sort_by": "relevance"
}
```

`sort_by` can be:

- `relevance`: let OpenAlex relevance drive the paper search.
- `citations`: sort works by citation count descending.
- `recent`: sort works by publication date descending.

Broad AI discovery works best with targeted queries rather than one generic query. `artificial intelligence` is useful as a smoke test, but it is very broad and may return surveys, historical papers, or unrelated high-level work.

Try several focused searches, then compare the resulting candidates:

- `LLM agents evaluation`
- `AI agents tool use benchmark`
- `multimodal foundation models`
- `AI for science foundation models`
- `data-centric AI benchmark`
- `robot learning foundation models`
- `AI safety evaluation`
- `scientific machine learning`
- `ML systems for LLMs`

## Workflow Without Custom GPT Actions

Use this workflow when Custom GPT Actions or MCP are unavailable in your ChatGPT workspace.

1. Run a local CLI search.
2. Review `outputs/latest/candidates.md`.
3. Commit selected output files to GitHub.
4. Ask the Custom GPT to read the GitHub repo files and generate rankings or editable outreach drafts.

Windows PowerShell example:

```powershell
.venv\Scripts\Activate.ps1
python -m backend.cli_search --topics "LLM agents evaluation" "AI for science foundation models" "multimodal AI agents" --limit 10 --from-year 2023 --output-dir outputs/latest
```

The CLI writes:

- `outputs/latest/candidates.csv`
- `outputs/latest/candidates.json`
- `outputs/latest/candidates.md`

The Markdown file is optimized for Custom GPT reading. It includes search context, candidate metadata, scores, why each candidate is interesting, opportunity angles, suggested outreach angles, and verification notes. No email extraction or outreach sending is performed.

To generate editable local draft skeletons and mark candidates as drafted:

```powershell
python -m backend.cli_agent --topics "LLM agents evaluation" "AI for science foundation models" "multimodal AI agents" --limit 10 --from-year 2023 --sort-by relevance --max-authors-per-paper 1 --output-dir outputs/latest
```

This also writes `outputs/latest/drafts.md`. It does not send anything.

## Contact Tracking And Deduplication

The workflow uses simple CSV state files in `data/` to avoid repeatedly drafting or contacting the same people and papers:

- `data/contacted_people.csv`
- `data/contacted_papers.csv`
- `data/drafted_candidates.csv`
- `data/blocked_candidates.csv`

Candidate outputs include `person_key`, `paper_key`, `candidate_key`, and `status`. By default, `backend.cli_search` and `backend.cli_agent` exclude candidates that were already drafted, contacted, used for contact, rejected, replied, or blocked.

Generated drafts are marked as `drafted`, not contacted. After you manually send an email, run:

```powershell
python -m backend.mark_contacted --person-key PERSON_KEY --paper-key PAPER_KEY --name "Name" --institution "Institution" --paper-title "Paper Title" --paper-url "URL" --status contacted --notes "Sent manually by email"
```

You can also update the CSV files by hand. No emails are sent automatically.

For a public repository, keep `email`, `linkedin_url`, and sensitive notes blank unless they are public metadata and you have intentionally reviewed them. Use `data/private/` for local-only private tracking.

## Automated Workflow Without Custom GPT Actions

GitHub Actions can run discovery automatically without Custom GPT Actions, MCP, or a live local API connection. In this public repository, the workflow is provided only as an example and is not active.

The example workflow in `examples/github_actions_discovery.example.yml`:

- Runs weekly and can also be started manually.
- Searches OpenAlex with broad AI topic queries.
- Scores and deduplicates candidates.
- Saves results to `outputs/latest`.
- Commits `candidates.md`, `candidates.csv`, and `candidates.json` back to the repository only when they change.

For real automation, copy the example workflow into `.github/workflows/discover.yml` in your private repository, not this public demo repository. Then run it manually from GitHub:

```text
Actions -> AI Research Discovery -> Run workflow
```

Then ask the Custom GPT:

```text
Read outputs/latest/candidates.md from this repo and rank the top 5 candidates. Then generate editable outreach drafts for the top 3. Do not send anything.
```

This avoids needing Custom GPT Actions or MCP. The Custom GPT reads the committed Markdown or JSON outputs from GitHub and helps with ranking and draft generation only.

## Expose Later With ngrok

```bash
ngrok http 8000
```

ngrok creates a temporary public URL that forwards requests to the local FastAPI server, allowing Custom GPT Actions to call the local backend during development.

## Connect To Custom GPT Actions

1. Expose the backend with ngrok or deploy it.
2. Replace `https://YOUR_NGROK_OR_DEPLOYED_URL` in `schemas/openapi.yaml`.
3. In GPT Builder, create a new action.
4. Paste or import the OpenAPI schema.
5. Use Authentication: None for the MVP.

## Safety

This project is designed for high-quality, human-reviewed academic outreach and does not support automatic bulk email sending.
