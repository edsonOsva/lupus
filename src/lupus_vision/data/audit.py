"""Audit an image manifest before any model is allowed to train."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

REQUIRED_COLUMNS = (
    "image_id",
    "subject_id",
    "label",
    "clinical_label",
    "annotation_basis",
    "source_name",
    "source_url",
    "license_name",
    "license_url",
    "ai_use_allowed",
    "consent_status",
    "has_watermark",
    "face_occluded",
    "split",
    "relative_path",
    "sha256",
    "notes",
)

ALLOWED_LABELS = {"control", "pattern_compatible"}
ALLOWED_SPLITS = {"train", "validation", "test", "unassigned"}
ALLOWED_CONSENT = {"licensed_public", "research_consent", "synthetic"}
YES_NO_UNKNOWN = {"yes", "no", "unknown"}


@dataclass(frozen=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    image_id: str | None = None


@dataclass
class ImageRecord:
    row_number: int
    values: dict[str, str]
    path: Path | None = None
    computed_sha256: str | None = None
    perceptual_hash: int | None = None
    width: int | None = None
    height: int | None = None

    @property
    def image_id(self) -> str:
        return self.values.get("image_id", "")

    @property
    def subject_id(self) -> str:
        return self.values.get("subject_id", "")

    @property
    def label(self) -> str:
        return self.values.get("label", "")

    @property
    def split(self) -> str:
        return self.values.get("split", "")


def _issue(
    issues: list[AuditIssue],
    severity: str,
    code: str,
    message: str,
    record: ImageRecord | None = None,
) -> None:
    issues.append(
        AuditIssue(
            severity=severity,
            code=code,
            message=message,
            image_id=record.image_id or None if record else None,
        )
    )


def _valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _difference_hash(image: Image.Image) -> int:
    grayscale = image.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
    pixels = grayscale.tobytes()
    value = 0
    for row in range(8):
        offset = row * 9
        for column in range(8):
            value = (value << 1) | int(pixels[offset + column + 1] > pixels[offset + column])
    return value


def _load_manifest(manifest_path: Path) -> tuple[list[ImageRecord], list[AuditIssue]]:
    issues: list[AuditIssue] = []
    with manifest_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        columns = tuple(reader.fieldnames or ())
        missing_columns = sorted(set(REQUIRED_COLUMNS) - set(columns))
        if missing_columns:
            _issue(
                issues,
                "error",
                "missing_columns",
                f"Manifest is missing columns: {', '.join(missing_columns)}",
            )
            return [], issues

        records = []
        for row_number, row in enumerate(reader, start=2):
            values = {key: (value or "").strip() for key, value in row.items()}
            records.append(ImageRecord(row_number=row_number, values=values))
    return records, issues


def _validate_row(
    record: ImageRecord,
    data_root: Path,
    issues: list[AuditIssue],
    minimum_dimension: int,
) -> None:
    required_values = (
        "image_id",
        "subject_id",
        "label",
        "annotation_basis",
        "source_name",
        "source_url",
        "license_name",
        "license_url",
        "ai_use_allowed",
        "consent_status",
        "has_watermark",
        "face_occluded",
        "split",
        "relative_path",
        "sha256",
    )
    for field_name in required_values:
        if not record.values.get(field_name):
            _issue(
                issues,
                "error",
                "missing_value",
                f"Row {record.row_number}: '{field_name}' is required.",
                record,
            )

    if record.label and record.label not in ALLOWED_LABELS:
        _issue(
            issues,
            "error",
            "invalid_label",
            f"Label '{record.label}' is not one of {sorted(ALLOWED_LABELS)}.",
            record,
        )

    if record.split and record.split not in ALLOWED_SPLITS:
        _issue(
            issues,
            "error",
            "invalid_split",
            f"Split '{record.split}' is not one of {sorted(ALLOWED_SPLITS)}.",
            record,
        )
    elif record.split == "unassigned":
        _issue(issues, "error", "unassigned_split", "A final split is required.", record)

    ai_use_allowed = record.values.get("ai_use_allowed", "")
    if ai_use_allowed not in YES_NO_UNKNOWN:
        _issue(issues, "error", "invalid_ai_permission", "Use yes, no, or unknown.", record)
    elif ai_use_allowed != "yes":
        _issue(
            issues,
            "error",
            "ai_use_not_allowed",
            "The source does not have verified permission for AI training and testing.",
            record,
        )

    consent_status = record.values.get("consent_status", "")
    if consent_status and consent_status not in ALLOWED_CONSENT:
        _issue(
            issues,
            "error",
            "invalid_consent_status",
            f"Consent status must be one of {sorted(ALLOWED_CONSENT)}.",
            record,
        )

    for field_name in ("has_watermark", "face_occluded"):
        value = record.values.get(field_name, "")
        if value not in YES_NO_UNKNOWN:
            _issue(
                issues,
                "error",
                f"invalid_{field_name}",
                f"'{field_name}' must be yes, no, or unknown.",
                record,
            )
        elif value != "no":
            _issue(
                issues,
                "error",
                field_name,
                f"'{field_name}' must be verified as no for the baseline dataset.",
                record,
            )

    for field_name in ("source_url", "license_url"):
        value = record.values.get(field_name, "")
        if value and not _valid_url(value):
            _issue(
                issues,
                "error",
                "invalid_url",
                f"'{field_name}' must be an absolute HTTP(S) URL.",
                record,
            )

    relative_path = Path(record.values.get("relative_path", ""))
    if not str(relative_path):
        return
    if relative_path.is_absolute() or ".." in relative_path.parts:
        _issue(
            issues,
            "error",
            "unsafe_path",
            "relative_path must stay inside data-root.",
            record,
        )
        return

    resolved_root = data_root.resolve()
    resolved_path = (resolved_root / relative_path).resolve()
    if not resolved_path.is_relative_to(resolved_root):
        _issue(issues, "error", "unsafe_path", "Resolved path escapes data-root.", record)
        return

    record.path = resolved_path
    if not resolved_path.is_file():
        _issue(issues, "error", "missing_file", f"File not found: {relative_path}", record)
        return

    try:
        record.computed_sha256 = _sha256(resolved_path)
        expected_sha256 = record.values.get("sha256", "").lower()
        if expected_sha256 and expected_sha256 != record.computed_sha256:
            _issue(issues, "error", "checksum_mismatch", "SHA-256 does not match.", record)

        with Image.open(resolved_path) as image:
            image.verify()
        with Image.open(resolved_path) as image:
            record.width, record.height = image.size
            record.perceptual_hash = _difference_hash(image)
            exif = image.getexif()
            if exif and exif.get(34853):
                _issue(
                    issues,
                    "error",
                    "embedded_gps",
                    "Image contains embedded GPS metadata.",
                    record,
                )
            if min(image.size) < minimum_dimension:
                _issue(
                    issues,
                    "warning",
                    "small_image",
                    f"Image size {image.width}x{image.height} is below the target dimension.",
                    record,
                )
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        _issue(
            issues,
            "error",
            "invalid_image",
            f"Image cannot be decoded safely: {exc}",
            record,
        )


def _validate_collection(
    records: list[ImageRecord],
    issues: list[AuditIssue],
    perceptual_distance: int,
) -> None:
    image_ids: dict[str, ImageRecord] = {}
    for record in records:
        if record.image_id in image_ids:
            _issue(issues, "error", "duplicate_image_id", "image_id is duplicated.", record)
        else:
            image_ids[record.image_id] = record

    by_subject: dict[str, list[ImageRecord]] = defaultdict(list)
    by_checksum: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        if record.subject_id:
            by_subject[record.subject_id].append(record)
        if record.computed_sha256:
            by_checksum[record.computed_sha256].append(record)

    for subject_id, subject_records in by_subject.items():
        labels = {record.label for record in subject_records if record.label}
        splits = {record.split for record in subject_records if record.split != "unassigned"}
        if len(labels) > 1:
            _issue(
                issues,
                "error",
                "subject_label_conflict",
                f"Subject '{subject_id}' has inconsistent labels: {sorted(labels)}.",
            )
        if len(splits) > 1:
            _issue(
                issues,
                "error",
                "subject_split_leakage",
                f"Subject '{subject_id}' appears in multiple splits: {sorted(splits)}.",
            )

    for checksum, duplicate_records in by_checksum.items():
        if len(duplicate_records) > 1:
            ids = [record.image_id for record in duplicate_records]
            _issue(
                issues,
                "error",
                "exact_duplicate",
                f"The same file is registered more than once: {ids}; sha256={checksum}.",
            )

    required_splits = {"train", "validation", "test"}
    records_by_split: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        records_by_split[record.split].append(record)
    for split in sorted(required_splits):
        if split not in records_by_split:
            _issue(
                issues,
                "error",
                "missing_split",
                f"Required split '{split}' has no images.",
            )
            continue
        labels = {record.label for record in records_by_split[split] if record.label}
        missing_labels = sorted(ALLOWED_LABELS - labels)
        if missing_labels:
            _issue(
                issues,
                "error",
                "split_missing_label",
                f"Split '{split}' is missing labels: {missing_labels}.",
            )

    records_by_source: dict[str, list[ImageRecord]] = defaultdict(list)
    for record in records:
        source_name = record.values.get("source_name", "")
        if source_name:
            records_by_source[source_name].append(record)
    for source_name, source_records in sorted(records_by_source.items()):
        labels = {record.label for record in source_records if record.label}
        if len(source_records) >= 2 and len(labels) == 1:
            _issue(
                issues,
                "warning",
                "source_label_confounding",
                f"Source '{source_name}' contributes only to label '{next(iter(labels))}'.",
            )

    hashed_records = [record for record in records if record.perceptual_hash is not None]
    for index, left in enumerate(hashed_records):
        for right in hashed_records[index + 1 :]:
            if left.computed_sha256 == right.computed_sha256:
                continue
            distance = (left.perceptual_hash ^ right.perceptual_hash).bit_count()
            if distance > perceptual_distance:
                continue
            severity = "error" if left.split != right.split else "warning"
            _issue(
                issues,
                severity,
                "near_duplicate",
                (
                    f"Images '{left.image_id}' and '{right.image_id}' are visually similar "
                    f"(dHash distance={distance})."
                ),
            )


def _summary(records: Iterable[ImageRecord]) -> dict[str, Any]:
    records = list(records)
    labels = Counter(record.label for record in records if record.label)
    splits = Counter(record.split for record in records if record.split)
    subjects_by_label: dict[str, set[str]] = defaultdict(set)
    for record in records:
        if record.label and record.subject_id:
            subjects_by_label[record.label].add(record.subject_id)
    return {
        "rows": len(records),
        "subjects": len({record.subject_id for record in records if record.subject_id}),
        "images_by_label": dict(sorted(labels.items())),
        "subjects_by_label": {
            label: len(subjects) for label, subjects in sorted(subjects_by_label.items())
        },
        "images_by_split": dict(sorted(splits.items())),
    }


def audit_manifest(
    manifest_path: Path,
    data_root: Path,
    *,
    minimum_dimension: int = 224,
    perceptual_distance: int = 4,
) -> dict[str, Any]:
    """Return a JSON-serializable audit report."""
    manifest_path = Path(manifest_path)
    data_root = Path(data_root)
    records, issues = _load_manifest(manifest_path)

    for record in records:
        _validate_row(record, data_root, issues, minimum_dimension)
    _validate_collection(records, issues, perceptual_distance)

    severity_counts = Counter(issue.severity for issue in issues)
    report = {
        "ready_for_training": severity_counts["error"] == 0 and bool(records),
        "summary": _summary(records),
        "issue_counts": dict(sorted(severity_counts.items())),
        "issues": [asdict(issue) for issue in issues],
    }
    if not records and not any(issue.code == "missing_columns" for issue in issues):
        report["issues"].append(
            asdict(AuditIssue("error", "empty_manifest", "Manifest has no image rows."))
        )
        report["issue_counts"]["error"] = report["issue_counts"].get("error", 0) + 1
        report["ready_for_training"] = False
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--minimum-dimension", type=int, default=224)
    parser.add_argument("--perceptual-distance", type=int, default=4)
    parser.add_argument("--fail-on-warning", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    report = audit_manifest(
        args.manifest,
        args.data_root,
        minimum_dimension=args.minimum_dimension,
        perceptual_distance=args.perceptual_distance,
    )

    rendered = json.dumps(report, indent=2, ensure_ascii=False)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")

    if not report["ready_for_training"]:
        return 2
    if args.fail_on_warning and report["issue_counts"].get("warning", 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
