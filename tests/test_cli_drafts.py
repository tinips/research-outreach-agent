import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.cli_drafts import run_drafts


class CliDraftsTests(unittest.TestCase):
    def test_run_drafts_generates_outputs_from_existing_candidates_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            candidates_path = root / "candidates.json"
            output_dir = root / "out"
            candidates_path.write_text(
                json.dumps(
                    {
                        "topics": ["LLM agents evaluation"],
                        "candidates": [
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
                        ],
                    }
                ),
                encoding="utf-8",
            )

            drafts_json = run_drafts(
                SimpleNamespace(
                    input=candidates_path.as_posix(),
                    output_dir=output_dir.as_posix(),
                    limit=None,
                    template="prompts/email_template.md",
                )
            )

            payload = json.loads(Path(drafts_json).read_text(encoding="utf-8"))
            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["topics"], ["LLM agents evaluation"])
            self.assertEqual(payload["drafts"][0]["candidate_name"], "Jane Researcher")
            self.assertTrue((output_dir / "drafts.md").exists())
            self.assertTrue((output_dir / "drafts.csv").exists())


if __name__ == "__main__":
    unittest.main()
