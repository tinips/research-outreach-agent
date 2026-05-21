import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from backend.draft_generator import generate_drafts
from backend.drafts_export import archive_existing_drafts_json, save_drafts_json
from backend.send_emails_smtp import (
    DEFAULT_INPUT,
    PROJECT_ROOT,
    TEST_RECIPIENT_ENV,
    Draft,
    SMTPConfig,
    build_message,
    resolve_path,
)


class MailerIntegrationTests(unittest.TestCase):
    def test_generated_drafts_json_includes_sender_required_fields(self) -> None:
        drafts = generate_drafts(
            [
                {
                    "candidate_key": "candidate-1",
                    "person_key": "person-1",
                    "paper_key": "paper-1",
                    "name": "Jane Researcher",
                    "group": "stretch",
                    "email": "researcher@example.edu",
                    "email_confidence": "high",
                    "institution": "Example University",
                    "paper_title": "A Synthetic Study of Reproducible Agent Benchmarks",
                    "paper_url": "https://example.com/paper",
                    "opportunity_angle": "Evaluation and reproducibility support.",
                }
            ]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "drafts.json"
            save_drafts_json(drafts, ["LLM agents evaluation"], output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        draft = payload["drafts"][0]
        self.assertEqual(draft["candidate_name"], "Jane Researcher")
        self.assertEqual(draft["group"], "stretch")
        self.assertEqual(draft["email"], "researcher@example.edu")
        self.assertEqual(draft["email_confidence"], "high")
        self.assertEqual(draft["body"], draft["draft_body"])
        self.assertTrue(draft["subject"])

    def test_archive_existing_drafts_json_moves_file_to_old_drafts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            drafts_path = Path(temp_dir) / "outputs" / "latest" / "drafts.json"
            drafts_path.parent.mkdir(parents=True)
            drafts_path.write_text('{"drafts": []}', encoding="utf-8")

            archived_path = archive_existing_drafts_json(
                drafts_path,
                now=datetime(2026, 5, 19, 14, 30, 0, tzinfo=timezone.utc),
            )

            self.assertFalse(drafts_path.exists())
            self.assertIsNotNone(archived_path)
            archived = Path(archived_path)
            self.assertEqual(archived.name, "drafts_20260519_143000.json")
            self.assertEqual(archived.parent.name, "old_drafts")
            self.assertEqual(archived.read_text(encoding="utf-8"), '{"drafts": []}')

    def test_test_mode_message_uses_test_recipient_and_preserves_original_recipient(self) -> None:
        config = SMTPConfig(
            host="smtp.example.test",
            port=587,
            username="user",
            password="secret",
            from_address="sender@example.test",
        )
        draft = Draft(
            index=1,
            candidate_name="Jane Researcher",
            group="stretch",
            email="researcher@example.edu",
            email_confidence="high",
            subject="Research collaboration",
            body="Dear Jane,\n\nCV: attached\n\nBest,\nExample Sender",
        )

        with patch.dict("os.environ", {TEST_RECIPIENT_ENV: "test-recipient@example.com"}):
            message = build_message(config, draft, "test", None)

        self.assertEqual(message["To"], "test-recipient@example.com")
        self.assertEqual(message["Subject"], "[TEST] Research collaboration")
        body = message.get_content()
        self.assertIn("[TEST MODE]", body)
        self.assertIn("Original recipient: researcher@example.edu", body)
        self.assertIn("Candidate: Jane Researcher", body)

    def test_default_input_resolves_under_project_root(self) -> None:
        self.assertEqual(resolve_path(DEFAULT_INPUT), (PROJECT_ROOT / "outputs" / "latest" / "drafts.json").resolve())


if __name__ == "__main__":
    unittest.main()
