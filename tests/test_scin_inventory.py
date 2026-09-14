"""Tests for the SCIN metadata inventory."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from lupus_vision.data.scin_inventory import (
    ScinInventoryError,
    build_inventory,
    write_candidates_csv,
)

CASE_FIELDS = [
    "case_id",
    "body_parts_head_or_neck",
    "image_1_path",
    "image_2_path",
    "image_3_path",
    "image_1_shot_type",
    "image_2_shot_type",
    "image_3_shot_type",
]
LABEL_FIELDS = [
    "case_id",
    "weighted_skin_condition_label",
    "dermatologist_gradable_for_skin_condition_1",
    "dermatologist_gradable_for_skin_condition_2",
    "dermatologist_gradable_for_skin_condition_3",
]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ScinInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.cases_path = self.root / "scin_cases.csv"
        self.labels_path = self.root / "scin_labels.csv"

        _write_csv(
            self.cases_path,
            CASE_FIELDS,
            [
                {
                    "case_id": "case-1",
                    "body_parts_head_or_neck": "YES",
                    "image_1_path": "images/one.jpg",
                    "image_2_path": "images/two.jpg",
                    "image_1_shot_type": "CLOSE_UP",
                    "image_2_shot_type": "OVERVIEW",
                },
                {
                    "case_id": "case-2",
                    "body_parts_head_or_neck": "NO",
                    "image_1_path": "images/three.jpg",
                },
                {
                    "case_id": "case-3",
                    "body_parts_head_or_neck": "YES",
                    "image_1_path": "images/four.jpg",
                },
                {
                    "case_id": "case-4",
                    "body_parts_head_or_neck": "true",
                    "image_1_path": "images/five.jpg",
                },
            ],
        )
        _write_csv(
            self.labels_path,
            LABEL_FIELDS,
            [
                {
                    "case_id": "case-1",
                    "weighted_skin_condition_label": "{'Cutaneous lupus': 0.8}",
                    "dermatologist_gradable_for_skin_condition_1": "YES",
                    "dermatologist_gradable_for_skin_condition_2": "NO",
                    "dermatologist_gradable_for_skin_condition_3": "NO",
                },
                {
                    "case_id": "case-2",
                    "weighted_skin_condition_label": "{'Cutaneous lupus': 0.6}",
                    "dermatologist_gradable_for_skin_condition_1": "YES",
                },
                {
                    "case_id": "case-3",
                    "weighted_skin_condition_label": "{'Rosacea': 1.0}",
                    "dermatologist_gradable_for_skin_condition_1": "YES",
                },
                {
                    "case_id": "case-4",
                    "weighted_skin_condition_label": "{'Cutaneous lupus': 0.4}",
                    "dermatologist_gradable_for_skin_condition_1": "false",
                    "dermatologist_gradable_for_skin_condition_2": "false",
                    "dermatologist_gradable_for_skin_condition_3": "false",
                },
            ],
        )

    def test_filters_target_location_images_and_gradability(self) -> None:
        report = build_inventory(self.cases_path, self.labels_path)

        self.assertEqual(
            report["summary"],
            {
                "case_rows": 4,
                "label_rows": 4,
                "target_cases": 3,
                "target_images": 4,
                "target_head_or_neck_cases": 2,
                "target_head_or_neck_images": 3,
                "candidate_cases_for_manual_review": 1,
                "candidate_images_for_manual_review": 2,
                "target_cases_missing_metadata": 0,
                "target_cases_without_images": 0,
                "target_cases_without_gradable_vote": 1,
            },
        )
        self.assertEqual(report["selection_status"], "ready_for_manual_review")
        self.assertEqual(report["training_status"], "not_approved")
        self.assertEqual(report["candidates"][0]["case_id"], "case-1")

    def test_minimum_weight_is_applied(self) -> None:
        report = build_inventory(
            self.cases_path,
            self.labels_path,
            minimum_weight=0.7,
        )

        self.assertEqual(report["summary"]["target_cases"], 1)
        self.assertEqual(report["summary"]["candidate_cases_for_manual_review"], 1)

    def test_writes_one_csv_row_per_candidate_image(self) -> None:
        report = build_inventory(self.cases_path, self.labels_path)
        destination = self.root / "candidates.csv"

        write_candidates_csv(report, destination)

        with destination.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["case_id"] for row in rows}, {"case-1"})
        self.assertEqual(
            {row["image_path"] for row in rows},
            {"images/one.jpg", "images/two.jpg"},
        )

    def test_rejects_malformed_weighted_labels(self) -> None:
        _write_csv(
            self.labels_path,
            LABEL_FIELDS,
            [
                {
                    "case_id": "case-1",
                    "weighted_skin_condition_label": "not-a-dictionary",
                    "dermatologist_gradable_for_skin_condition_1": "YES",
                }
            ],
        )

        with self.assertRaisesRegex(ScinInventoryError, "Malformed"):
            build_inventory(self.cases_path, self.labels_path)

    def test_rejects_duplicate_case_ids(self) -> None:
        duplicate = {
            "case_id": "case-1",
            "body_parts_head_or_neck": "YES",
            "image_1_path": "images/duplicate.jpg",
        }
        _write_csv(self.cases_path, CASE_FIELDS, [duplicate, duplicate])

        with self.assertRaisesRegex(ScinInventoryError, "Duplicate case_id"):
            build_inventory(self.cases_path, self.labels_path)


if __name__ == "__main__":
    unittest.main()
