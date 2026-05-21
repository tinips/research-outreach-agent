import unittest

from backend.draft_generator import COMPUTE_SENTENCE, generate_drafts


class DraftGeneratorTests(unittest.TestCase):
    def test_generates_template_draft_without_professor_guess(self) -> None:
        drafts = generate_drafts(
            [
                {
                    "candidate_key": "candidate-1",
                    "person_key": "person-1",
                    "paper_key": "paper-1",
                    "name": "Jane Researcher",
                    "institution": "Example University",
                    "inferred_role": "first author; exact role unknown",
                    "paper_title": "A Synthetic Study of Reproducible Agent Benchmarks",
                    "paper_url": "https://example.com/paper",
                    "opportunity_angle": "Evaluation and reproducibility support.",
                }
            ]
        )

        self.assertEqual(len(drafts), 1)
        draft = drafts[0]
        self.assertEqual(draft.subject, "Research collaboration around Synthetic Study Reproducible Agent")
        self.assertTrue(draft.draft_body.startswith("Dear Jane,"))
        self.assertNotIn("Professor", draft.draft_body)
        self.assertIn('"A Synthetic Study of Reproducible Agent Benchmarks"', draft.draft_body)
        self.assertIn(COMPUTE_SENTENCE, draft.draft_body)
        self.assertIn("LinkedIn:", draft.draft_body)
        self.assertIn("CV: attached CV", draft.draft_body)
        self.assertEqual(draft.verification_notes, "passed deterministic template checks")

    def test_uses_professor_title_only_when_explicit(self) -> None:
        drafts = generate_drafts(
            [
                {
                    "candidate_key": "candidate-2",
                    "name": "Riley Scholar",
                    "inferred_role": "Professor of Computer Science",
                    "paper_title": "A Synthetic Paper About Reliable AI Systems",
                    "opportunity_angle": "Research tooling.",
                }
            ]
        )

        self.assertTrue(drafts[0].draft_body.startswith("Dear Professor Scholar,"))


if __name__ == "__main__":
    unittest.main()
