from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Literal


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = "outputs/latest/drafts.json"
TEST_RECIPIENT_ENV = "SMTP_TEST_RECIPIENT"
SAFE_CONFIDENCES = {"high", "medium"}
UNVERIFIED_CONFIDENCES = {"low", "suspicious", "not_found"}
REQUIRED_SMTP_VARS = ["SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"]
Mode = Literal["dry-run", "test", "send"]


@dataclass(frozen=True)
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str


@dataclass(frozen=True)
class Draft:
    index: int
    candidate_name: str
    group: str
    email: str
    email_confidence: str
    subject: str
    body: str


@dataclass(frozen=True)
class DraftResult:
    index: int
    candidate_name: str | None
    email: str | None
    email_confidence: str | None
    draft: Draft | None
    skip_reason: str | None

    @property
    def is_valid(self) -> bool:
        return self.draft is not None and self.skip_reason is None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local SMTP sender for prepared outreach drafts.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"Path to drafts JSON. Default: {DEFAULT_INPUT}.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print what would be sent and send nothing.")
    mode.add_argument("--test", action="store_true", help=f"Send valid drafts to {TEST_RECIPIENT_ENV} only.")
    mode.add_argument("--send", action="store_true", help="Send valid drafts to real candidate recipients.")
    parser.add_argument("--cv", help="Optional CV PDF path to attach to each outgoing email.")
    parser.add_argument("--include-unverified", action="store_true", help="Include low/suspicious/not_found drafts.")
    parser.add_argument("--max-send", type=int, default=6, help="Maximum emails to send. Default: 6.")
    parser.add_argument("--delay-seconds", type=float, default=10, help="Seconds to wait between sends. Default: 10.")
    return parser


def add_sender_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"Path to drafts JSON. Default: {DEFAULT_INPUT}.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print what would be sent and send nothing.")
    mode.add_argument("--test", action="store_true", help=f"Send valid drafts to {TEST_RECIPIENT_ENV} only.")
    parser.add_argument("--cv", help="Optional CV PDF path to attach to each outgoing email.")
    parser.add_argument("--include-unverified", action="store_true", help="Include low/suspicious/not_found drafts.")
    parser.add_argument("--max-send", type=int, default=6, help="Maximum emails to send. Default: 6.")
    parser.add_argument("--delay-seconds", type=float, default=10, help="Seconds to wait between sends. Default: 10.")


def load_dotenv(path: Path | None = None) -> None:
    env_paths = [path] if path else [PROJECT_ROOT / ".env", Path.cwd() / ".env"]
    env_paths = [env_path.resolve() for env_path in env_paths if env_path]
    seen: set[Path] = set()
    env_paths = [env_path for env_path in env_paths if not (env_path in seen or seen.add(env_path))]

    for env_path in env_paths:
        load_dotenv_file(env_path)


def load_dotenv_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv as dotenv_load
    except ImportError:
        dotenv_load = None
    if dotenv_load:
        dotenv_load(env_path, override=False)
        if all(os.environ.get(name) for name in REQUIRED_SMTP_VARS):
            return
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def get_smtp_config() -> SMTPConfig:
    load_dotenv()
    missing = [name for name in REQUIRED_SMTP_VARS if not os.environ.get(name)]
    if missing:
        raise ValueError(f"Missing required SMTP environment variables: {', '.join(missing)}")
    try:
        port = int(os.environ["SMTP_PORT"])
    except ValueError as exc:
        raise ValueError("SMTP_PORT must be an integer") from exc
    return SMTPConfig(
        host=os.environ["SMTP_HOST"],
        port=port,
        username=os.environ["SMTP_USERNAME"],
        password=os.environ["SMTP_PASSWORD"],
        from_address=os.environ["SMTP_FROM"],
    )


def get_test_recipient() -> str:
    load_dotenv()
    recipient = os.environ.get(TEST_RECIPIENT_ENV, "").strip()
    if not recipient:
        raise ValueError(f"Missing required test recipient environment variable: {TEST_RECIPIENT_ENV}")
    if not is_valid_email(recipient):
        raise ValueError(f"{TEST_RECIPIENT_ENV} must be a valid email address")
    return recipient


def resolve_path(path_value: str) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def resolve_cv_path(path_value: str | None) -> Path | None:
    if path_value:
        cv_path = resolve_path(path_value)
    else:
        cv_path = auto_detect_cv_path()
        if cv_path is None:
            return None
    if not cv_path.exists():
        raise FileNotFoundError(f"CV attachment not found: {cv_path}")
    if not cv_path.is_file():
        raise ValueError(f"CV path is not a file: {cv_path}")
    if cv_path.suffix.lower() != ".pdf":
        raise ValueError(f"CV attachment must be a PDF: {cv_path}")
    return cv_path


def auto_detect_cv_path() -> Path | None:
    candidates: list[Path] = []
    for folder_name in ("attachments", "cv"):
        folder = PROJECT_ROOT / folder_name
        if folder.exists():
            candidates.extend(sorted(folder.glob("*.pdf")))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0].resolve()
    choices = ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in candidates)
    raise ValueError(f"Multiple CV PDFs found ({choices}). Pass --cv to choose one.")


def load_drafts(path_value: str, include_unverified: bool) -> list[DraftResult]:
    path = resolve_path(path_value)
    if not path.exists():
        raise FileNotFoundError(f"Input drafts file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Input path is not a file: {path}")
    with path.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)
    if isinstance(payload, dict) and isinstance(payload.get("drafts"), list):
        raw_drafts = payload["drafts"]
    elif isinstance(payload, list):
        raw_drafts = payload
    else:
        raise ValueError('Input JSON must be a list or an object with a top-level "drafts" list')
    return [validate_draft(index, raw_draft, include_unverified) for index, raw_draft in enumerate(raw_drafts, 1)]


def validate_draft(index: int, raw_draft: Any, include_unverified: bool) -> DraftResult:
    if not isinstance(raw_draft, dict):
        return skipped(index, None, None, None, "draft is not an object")
    candidate_name = optional_string(raw_draft.get("candidate_name")) or optional_string(raw_draft.get("name")) or "<missing>"
    group = optional_string(raw_draft.get("group")) or ""
    email = optional_string(raw_draft.get("email"))
    subject = optional_string(raw_draft.get("subject"))
    body = optional_string(raw_draft.get("body")) or optional_string(raw_draft.get("draft_body"))
    email_confidence = optional_string(raw_draft.get("email_confidence")) or "<missing>"
    if not email:
        return skipped(index, candidate_name, email, email_confidence, "missing email")
    if not subject:
        return skipped(index, candidate_name, email, email_confidence, "missing subject")
    if not body:
        return skipped(index, candidate_name, email, email_confidence, "missing body")
    confidence_key = email_confidence.strip().lower()
    if confidence_key in UNVERIFIED_CONFIDENCES and not include_unverified:
        return skipped(index, candidate_name, email, email_confidence, f"email_confidence is {email_confidence}")
    if confidence_key not in SAFE_CONFIDENCES | UNVERIFIED_CONFIDENCES:
        return skipped(index, candidate_name, email, email_confidence, f"unsupported email_confidence {email_confidence}")
    if not is_valid_email(email):
        return skipped(index, candidate_name, email, email_confidence, "invalid email")
    body = normalize_body_text(body)
    body = ensure_cv_attached_line(body)
    draft = Draft(index, candidate_name, group, email, email_confidence, subject, body)
    return DraftResult(index, candidate_name, email, email_confidence, draft, None)


def optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def skipped(
    index: int,
    candidate_name: str | None,
    email: str | None,
    email_confidence: str | None,
    reason: str,
) -> DraftResult:
    return DraftResult(index, candidate_name, email, email_confidence, None, reason)


def is_valid_email(email: str) -> bool:
    if email != email.strip() or any(char.isspace() for char in email):
        return False
    if "," in email or ";" in email or email.count("@") != 1:
        return False
    local, domain = email.split("@", 1)
    return bool(local and domain and "." in domain)


def ensure_cv_attached_line(body: str) -> str:
    lines = body.strip().splitlines()
    cv_pattern = re.compile(r"^\s*CV\s*:", re.IGNORECASE)
    for index, line in enumerate(lines):
        if cv_pattern.match(line):
            lines[index] = "CV: attached"
            return "\n".join(lines).strip()
    insert_at = find_cv_insert_index(lines)
    lines.insert(insert_at, "CV: attached")
    return "\n".join(lines).strip()


def normalize_body_text(body: str) -> str:
    """Convert common escaped newline sequences from generated JSON into plain text."""
    normalized = body.strip()
    if "\\n" in normalized or "\\r" in normalized:
        normalized = (
            normalized.replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\r", "\n")
        )
    return normalized


def find_cv_insert_index(lines: list[str]) -> int:
    closing_pattern = re.compile(r"^\s*(Best|Regards|Sincerely|Thank you),?\s*$", re.IGNORECASE)
    question_pattern = re.compile(r"\?\s*$")
    for index, line in enumerate(lines):
        if closing_pattern.match(line):
            if index > 0 and lines[index - 1].strip():
                return index
            return index
    for index, line in enumerate(lines):
        if question_pattern.search(line):
            return index
    return len(lines)


def build_message(config: SMTPConfig, draft: Draft, mode: Mode, cv_path: Path | None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = config.from_address
    test_recipient = get_test_recipient() if mode == "test" else ""
    message["To"] = test_recipient if mode == "test" else draft.email
    subject = draft.subject
    body = draft.body
    if mode == "test":
        subject = f"[TEST] {subject}"
        body = (
            "[TEST MODE]\n"
            f"Original recipient: {draft.email}\n"
            f"Candidate: {draft.candidate_name}\n"
            f"Group: {draft.group or '<missing>'}\n\n"
            f"{draft.body}"
        )
    message["Subject"] = subject
    message.set_content(body)
    if cv_path:
        attach_pdf(message, cv_path)
    return message


def attach_pdf(message: EmailMessage, cv_path: Path) -> None:
    content_type, _ = mimetypes.guess_type(cv_path.name)
    if content_type:
        maintype, subtype = content_type.split("/", 1)
    else:
        maintype, subtype = "application", "pdf"
    message.add_attachment(
        cv_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=cv_path.name,
    )


def send_message(config: SMTPConfig, message: EmailMessage) -> None:
    with smtplib.SMTP(config.host, config.port, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(config.username, config.password)
        smtp.send_message(message)


def print_summary(results: list[DraftResult], mode: Mode, max_send: int, cv_path: Path | None) -> None:
    valid_results = [result for result in results if result.is_valid]
    skipped_results = [result for result in results if not result.is_valid]
    title = {"dry-run": "Dry Run", "test": "Test Send", "send": "Real Send"}[mode]
    print(f"\n=== SMTP {title} Summary ===")
    print(f"Drafts loaded: {len(results)}")
    print(f"Valid: {len(valid_results)}")
    print(f"Skipped: {len(skipped_results)}")
    print(f"CV attachment: {cv_path if cv_path else '<none>'}")
    if mode != "dry-run":
        print(f"Send cap: {max_send}")
    test_recipient = get_test_recipient() if mode == "test" else ""
    for result in results:
        if not result.is_valid:
            print(
                f"SKIP #{result.index}: {result.email or '<missing email>'} "
                f"candidate={result.candidate_name or '<missing>'} "
                f"confidence={result.email_confidence or '<missing>'} reason={result.skip_reason}"
            )
            continue
        assert result.draft is not None
        prefix = "WOULD SEND" if mode == "dry-run" else "READY"
        recipient = test_recipient if mode == "test" else result.draft.email
        subject = f"[TEST] {result.draft.subject}" if mode == "test" else result.draft.subject
        print(
            f"{prefix} #{result.index}: to={recipient} candidate={result.draft.candidate_name} "
            f"confidence={result.draft.email_confidence} subject={subject}"
        )


def ensure_not_github_actions(mode: Mode) -> None:
    if mode != "dry-run" and os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        raise RuntimeError("Refusing to send from GitHub Actions. This script is local-only.")


def run_smtp_workflow(
    *,
    input_path: str = DEFAULT_INPUT,
    mode: Mode = "send",
    cv_path: str | None = None,
    include_unverified: bool = False,
    max_send: int = 6,
    delay_seconds: float = 10,
) -> int:
    if mode not in {"dry-run", "test", "send"}:
        raise ValueError(f"Unsupported mode: {mode}")
    if max_send < 1:
        raise ValueError("--max-send must be at least 1")
    if delay_seconds < 0:
        raise ValueError("--delay-seconds must not be negative")

    attachment_path = resolve_cv_path(cv_path)
    results = load_drafts(input_path, include_unverified)
    valid_results = [result for result in results if result.is_valid]
    print_summary(results, mode, max_send, attachment_path)

    if mode == "dry-run":
        print("Dry run only. No email sent.")
        return 0

    ensure_not_github_actions(mode)
    if not valid_results:
        print("No valid emails to send.")
        return 0
    if len(valid_results) > max_send:
        raise RuntimeError(f"{len(valid_results)} valid drafts exceeds --max-send {max_send}. No emails sent.")

    config = get_smtp_config()
    for offset, result in enumerate(valid_results, start=1):
        assert result.draft is not None
        message = build_message(config, result.draft, mode, attachment_path)
        send_message(config, message)
        print(f"SENT #{result.index}: to={message['To']} subject={message['Subject']}")
        if offset < len(valid_results) and delay_seconds:
            time.sleep(delay_seconds)
    print(f"Sent {len(valid_results)} email(s).")
    return 0


def mode_from_args(args: argparse.Namespace) -> Mode:
    if args.dry_run:
        return "dry-run"
    if args.test:
        return "test"
    return "send"


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run_smtp_workflow(
            input_path=args.input,
            mode=mode_from_args(args),
            cv_path=args.cv,
            include_unverified=args.include_unverified,
            max_send=args.max_send,
            delay_seconds=args.delay_seconds,
        )
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
