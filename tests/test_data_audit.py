from __future__ import annotations

import csv
import hashlib
import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from lupus_vision.data.audit import REQUIRED_COLUMNS, audit_manifest


class DataAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.data_root = self.root / "dataset"
        self.data_root.mkdir()
        self.manifest_path = self.root / "manifest.csv"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _create_image(self, name: str, color: tuple[int, int, int]) -> tuple[str, str]:
        path = self.data_root / name
        generator = random.Random(f"{name}:{color}")
        pixels = [generator.randrange(256) for _ in range(9 * 8)]
        fixture = Image.new("L", (9, 8))
        fixture.putdata(pixels)
        fixture.resize((224, 224), Image.Resampling.NEAREST).convert("RGB").save(path)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        return name, checksum

    def _row(
        self,
        image_id: str,
        subject_id: str,
        label: str,
        split: str,
        relative_path: str,
        sha256: str,
        **overrides: str,
    ) -> dict[str, str]:
        row = {
            "image_id": image_id,
            "subject_id": subject_id,
            "label": label,
            "clinical_label": "not_applicable" if label == "control" else "reviewed_pattern",
            "annotation_basis": "independent expert review",
            "source_name": "test-fixture",
            "source_url": "https://example.org/source",
            "license_name": "test-only",
            "license_url": "https://example.org/license",
            "ai_use_allowed": "yes",
            "consent_status": "synthetic",
            "has_watermark": "no",
            "face_occluded": "no",
            "split": split,
            "relative_path": relative_path,
            "sha256": sha256,
            "notes": "synthetic unit-test image",
        }
        row.update(overrides)
        return row

    def _write_manifest(self, rows: list[dict[str, str]]) -> None:
        with self.manifest_path.open("w", encoding="utf-8", newline="") as destination:
            writer = csv.DictWriter(destination, fieldnames=REQUIRED_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def _issue_codes(self, report: dict) -> set[str]:
        return {issue["code"] for issue in report["issues"]}

    def test_valid_manifest_is_ready(self) -> None:
        fixtures = [
            ("control-train.png", (0, 0, 0), "c1", "control", "train"),
            ("pattern-train.png", (255, 0, 0), "p1", "pattern_compatible", "train"),
            ("control-validation.png", (0, 255, 0), "c2", "control", "validation"),
            (
                "pattern-validation.png",
                (0, 0, 255),
                "p2",
                "pattern_compatible",
                "validation",
            ),
            ("control-test.png", (255, 255, 0), "c3", "control", "test"),
            ("pattern-test.png", (0, 255, 255), "p3", "pattern_compatible", "test"),
        ]
        rows = []
        for index, (name, color, subject, label, split) in enumerate(fixtures):
            relative_path, checksum = self._create_image(name, color)
            rows.append(
                self._row(f"image-{index}", subject, label, split, relative_path, checksum)
            )
        self._write_manifest(rows)

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertTrue(report["ready_for_training"], report["issues"])
        self.assertEqual(report["summary"]["subjects"], 6)

    def test_subject_cannot_cross_splits(self) -> None:
        first_path, first_hash = self._create_image("first.png", (10, 20, 30))
        second_path, second_hash = self._create_image("second.png", (40, 50, 60))
        self._write_manifest(
            [
                self._row("first", "same-subject", "control", "train", first_path, first_hash),
                self._row(
                    "second", "same-subject", "control", "validation", second_path, second_hash
                ),
            ]
        )

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertFalse(report["ready_for_training"])
        self.assertIn("subject_split_leakage", self._issue_codes(report))

    def test_exact_duplicate_is_rejected(self) -> None:
        first_path, first_hash = self._create_image("first.png", (10, 20, 30))
        duplicate_path = self.data_root / "duplicate.png"
        duplicate_path.write_bytes((self.data_root / first_path).read_bytes())
        duplicate_hash = hashlib.sha256(duplicate_path.read_bytes()).hexdigest()
        self._write_manifest(
            [
                self._row("first", "subject-1", "control", "train", first_path, first_hash),
                self._row(
                    "duplicate",
                    "subject-2",
                    "control",
                    "validation",
                    duplicate_path.name,
                    duplicate_hash,
                ),
            ]
        )

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertFalse(report["ready_for_training"])
        self.assertIn("exact_duplicate", self._issue_codes(report))

    def test_unverified_ai_permission_is_rejected(self) -> None:
        relative_path, checksum = self._create_image("image.png", (10, 20, 30))
        self._write_manifest(
            [
                self._row(
                    "image",
                    "subject",
                    "control",
                    "train",
                    relative_path,
                    checksum,
                    ai_use_allowed="unknown",
                )
            ]
        )

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertFalse(report["ready_for_training"])
        self.assertIn("ai_use_not_allowed", self._issue_codes(report))

    def test_path_traversal_is_rejected(self) -> None:
        _, checksum = self._create_image("inside.png", (10, 20, 30))
        self._write_manifest(
            [self._row("image", "subject", "control", "train", "../outside.png", checksum)]
        )

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertFalse(report["ready_for_training"])
        self.assertIn("unsafe_path", self._issue_codes(report))

    def test_split_must_contain_both_labels(self) -> None:
        rows = []
        for index, split in enumerate(("train", "validation", "test")):
            relative_path, checksum = self._create_image(
                f"control-{split}.png", (index * 40, 10, 20)
            )
            rows.append(
                self._row(
                    f"control-{split}",
                    f"subject-{split}",
                    "control",
                    split,
                    relative_path,
                    checksum,
                )
            )
        self._write_manifest(rows)

        report = audit_manifest(self.manifest_path, self.data_root)

        self.assertFalse(report["ready_for_training"])
        self.assertIn("split_missing_label", self._issue_codes(report))


if __name__ == "__main__":
    unittest.main()
