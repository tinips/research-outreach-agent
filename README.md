# Research Outreach Agent

Research Outreach Agent is a lightweight system for discovering relevant AI researchers, ranking potential fit, and generating personalized, editable outreach drafts for research internship applications.

The system is designed around a human-in-the-loop workflow: it can discover candidates and generate draft messages, but it does not automatically send first-contact emails. Drafts are reviewed and edited before being sent.

## Features

- Search academic works and researchers using public research APIs
- Extract candidate metadata such as name, institution, papers, and profile URLs
- Rank researchers based on fit with a user research profile
- Generate personalized email and LinkedIn outreach drafts
- Integrate with a Custom GPT through GPT Actions
- Optionally create Gmail drafts for manual review

## Architecture

```text
Custom GPT
  ↓ GPT Actions
FastAPI backend
  ↓
Academic APIs
  ↓
Fit scoring + draft generation
  ↓
CSV / Google Sheets / Gmail drafts
```
