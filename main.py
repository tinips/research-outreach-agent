from __future__ import annotations

import argparse
import logging
import sys

from backend import cli_search
from backend import cli_drafts
from backend import send_emails_smtp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate research outreach drafts and send reviewed drafts over SMTP.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate candidates and drafts only.")
    cli_search.add_generation_arguments(generate_parser)

    drafts_parser = subparsers.add_parser("drafts", help="Generate drafts from an existing candidates.json only.")
    cli_drafts.add_drafts_arguments(drafts_parser)

    send_parser = subparsers.add_parser("send", help="Send existing drafts only.")
    send_emails_smtp.add_sender_arguments(send_parser)

    run_parser = subparsers.add_parser("run", help="Generate drafts, then send those generated drafts.")
    cli_search.add_generation_arguments(run_parser)
    add_run_sender_arguments(run_parser)

    return parser


def add_run_sender_arguments(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Print what would be sent and send nothing.")
    mode.add_argument(
        "--test",
        action="store_true",
        help=f"Send valid drafts to {send_emails_smtp.TEST_RECIPIENT_ENV} only.",
    )
    parser.add_argument("--cv", help="Optional CV PDF path to attach to each outgoing email.")
    parser.add_argument("--include-unverified", action="store_true", help="Include low/suspicious/not_found drafts.")
    parser.add_argument("--max-send", type=int, default=6, help="Maximum emails to send. Default: 6.")
    parser.add_argument("--delay-seconds", type=float, default=10, help="Seconds to wait between sends. Default: 10.")


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    try:
        if args.command == "generate":
            cli_search.run_generation(args)
            return 0
        if args.command == "drafts":
            cli_drafts.run_drafts(args)
            return 0
        if args.command == "send":
            return send_emails_smtp.run_smtp_workflow(
                input_path=args.input,
                mode=send_emails_smtp.mode_from_args(args),
                cv_path=args.cv,
                include_unverified=args.include_unverified,
                max_send=args.max_send,
                delay_seconds=args.delay_seconds,
            )
        if args.command == "run":
            drafts_path = cli_search.run_generation(args)
            return send_emails_smtp.run_smtp_workflow(
                input_path=drafts_path,
                mode=send_emails_smtp.mode_from_args(args),
                cv_path=args.cv,
                include_unverified=args.include_unverified,
                max_send=args.max_send,
                delay_seconds=args.delay_seconds,
            )
        parser.error(f"Unknown command: {args.command}")
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
