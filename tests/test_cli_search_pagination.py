import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import cli_search
from backend import state as state_module


def _make_work(work_number: int) -> dict:
    work_id = f"https://openalex.org/W{work_number}"
    author_id = f"https://openalex.org/A{work_number}"
    return {
        "id": work_id,
        "display_name": f"Paper {work_number}",
        "title": f"Paper {work_number}",
        "publication_year": 2025,
        "cited_by_count": max(1, 200 - work_number),
        "abstract": f"benchmark evaluation tooling paper {work_number}",
        "authorships": [
            {
                "author_position": "first",
                "author": {
                    "id": author_id,
                    "display_name": f"Author {work_number}",
                },
                "institutions": [{"display_name": f"University {work_number}"}],
                "raw_affiliation_strings": [f"University {work_number}"],
            }
        ],
        "primary_location": {
            "landing_page_url": f"https://example.org/paper-{work_number}",
            "pdf_url": f"https://example.org/paper-{work_number}.pdf",
        },
        "open_access": {"oa_url": f"https://example.org/paper-{work_number}.pdf"},
    }


class SearchTopicsPaginationTests(unittest.TestCase):
    def test_search_topics_uses_second_page_and_only_selected_candidates_are_written_seen(self) -> None:
        old_works = [_make_work(number) for number in range(1, 9)]
        new_works = [_make_work(number) for number in range(101, 109)]

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            self._write_seen_rows(data_dir / "seen_candidates.csv", old_works)

            def fake_search_works(*, page: int, **kwargs):
                if page == 1:
                    return old_works
                if page == 2:
                    return new_works
                return []

            with patch("backend.cli_search.search_works", side_effect=fake_search_works), patch(
                "backend.cli_search.enrich_candidate_emails", side_effect=lambda candidates: candidates
            ), patch("backend.cli_search.load_state", side_effect=lambda: state_module.load_state(data_dir)):
                selected = cli_search.search_topics(
                    topics=["multimodal AI agents"],
                    limit=40,
                    stretch_targets=3,
                    realistic_targets=3,
                    from_year=2024,
                    sort_by="relevance",
                    max_authors_per_paper=1,
                    max_candidates_per_institution=10,
                    seen_cooldown_days=60,
                    max_pages=2,
                )

            self.assertEqual(len(selected), 6)
            self.assertTrue(all(candidate.paper_id in {work["id"] for work in new_works} for candidate in selected))

            state_module.write_seen_tracking(
                selected,
                selected_candidate_keys={candidate.candidate_key or "" for candidate in selected},
                data_dir=data_dir,
            )

            with (data_dir / "seen_candidates.csv").open(encoding="utf-8", newline="") as csv_file:
                rows = list(csv.DictReader(csv_file))
            self.assertEqual(len(rows), 14)
            selected_keys = {candidate.candidate_key for candidate in selected}
            stored_shortlisted_keys = {
                row["candidate_key"]
                for row in rows
                if row.get("status") == "shortlisted" and row.get("candidate_key") in selected_keys
            }
            self.assertEqual(stored_shortlisted_keys, selected_keys)

    def test_email_lookup_receives_only_first_six_final_selected_candidates(self) -> None:
        works = [_make_work(number) for number in range(1, 13)]

        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            captured_lookup_candidates = []

            def fake_search_works(*, page: int, **kwargs):
                if page == 1:
                    return works
                return []

            def fake_enrich(candidates, **kwargs):
                captured_lookup_candidates.extend(candidates)
                return candidates

            with patch("backend.cli_search.search_works", side_effect=fake_search_works), patch(
                "backend.cli_search.enrich_candidate_emails", side_effect=fake_enrich
            ), patch("backend.cli_search.load_state", side_effect=lambda: state_module.load_state(data_dir)):
                selected = cli_search.search_topics(
                    topics=["multimodal AI agents"],
                    limit=40,
                    stretch_targets=4,
                    realistic_targets=4,
                    from_year=2024,
                    sort_by="relevance",
                    max_authors_per_paper=1,
                    max_candidates_per_institution=20,
                    seen_cooldown_days=60,
                    max_pages=1,
                    email_lookup=True,
                )

            self.assertEqual(len(selected), 8)
            self.assertEqual(len(captured_lookup_candidates), 6)
            self.assertEqual(
                [candidate.candidate_key for candidate in captured_lookup_candidates],
                [candidate.candidate_key for candidate in selected[:6]],
            )

    def _write_seen_rows(self, path: Path, works: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = state_module.SEEN_CANDIDATES_FIELDS
        with path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for work in works:
                author_id = work["authorships"][0]["author"]["id"]
                person_key = f"openalex:{author_id.rsplit('/', 1)[-1]}"
                paper_key = f"openalex:{work['id'].rsplit('/', 1)[-1]}"
                writer.writerow(
                    {
                        "candidate_key": f"{person_key}::{paper_key}",
                        "person_key": person_key,
                        "paper_key": paper_key,
                        "name": work["authorships"][0]["author"]["display_name"],
                        "institution": work["authorships"][0]["institutions"][0]["display_name"],
                        "paper_title": work["display_name"],
                        "paper_url": work["primary_location"]["landing_page_url"],
                        "first_seen_at": "2026-05-13T00:00:00+00:00",
                        "last_seen_at": "2026-05-13T00:00:00+00:00",
                        "times_seen": "1",
                        "last_score": "0.900",
                        "last_group": "stretch",
                        "status": "shortlisted",
                        "notes": "",
                    }
                )


if __name__ == "__main__":
    unittest.main()
