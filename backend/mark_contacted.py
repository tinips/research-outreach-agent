import argparse

from .state import mark_contacted


def main() -> None:
    args = _parse_args()
    candidate_key = mark_contacted(
        person_key=args.person_key,
        paper_key=args.paper_key,
        name=args.name,
        institution=args.institution,
        paper_title=args.paper_title,
        paper_url=args.paper_url,
        status=args.status,
        notes=args.notes,
        author_url=args.author_url or "",
        email=args.email or "",
        linkedin_url=args.linkedin_url or "",
    )
    print(f"Updated contact tracking for candidate_key: {candidate_key}")
    print("No email was sent.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manually mark a candidate as contacted after human-reviewed outreach.",
    )
    parser.add_argument("--person-key", required=True)
    parser.add_argument("--paper-key", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--institution", required=True)
    parser.add_argument("--paper-title", required=True)
    parser.add_argument("--paper-url", required=True)
    parser.add_argument("--status", default="contacted")
    parser.add_argument("--notes", default="")
    parser.add_argument("--author-url")
    parser.add_argument("--email")
    parser.add_argument("--linkedin-url")
    return parser.parse_args()


if __name__ == "__main__":
    main()
