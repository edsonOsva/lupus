"""Build a reproducible inventory of candidate SCIN cutaneous-lupus images."""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

TARGET_CONDITION = "Cutaneous lupus"
CASE_ID_COLUMN = "case_id"
HEAD_OR_NECK_COLUMN = "body_parts_head_or_neck"
WEIGHTED_LABEL_COLUMN = "weighted_skin_condition_label"
IMAGE_PATH_COLUMNS = ("image_1_path", "image_2_path", "image_3_path")
IMAGE_SHOT_TYPE_COLUMNS = (
    "image_1_shot_type",
    "image_2_shot_type",
    "image_3_shot_type",
)
GRADABLE_COLUMNS = (
    "dermatologist_gradable_for_skin_condition_1",
    "dermatologist_gradable_for_skin_condition_2",
    "dermatologist_gradable_for_skin_condition_3",
)


class ScinInventoryError(ValueError):
    """Raised when SCIN metadata cannot be inventoried safely."""


def _read_csv(path: Path, required_columns: Sequence[str]) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = set(reader.fieldnames or ())
            missing = sorted(set(required_columns) - fieldnames)
            if missing:
                raise ScinInventoryError(
                    f"{path} is missing required columns: {', '.join(missing)}"
                )
            return [dict(row) for row in reader]
    except OSError as exc:
        raise ScinInventoryError(f"Could not read {path}: {exc}") from exc


def _index_unique_cases(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    indexed: dict[str, Mapping[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        case_id = (row.get(CASE_ID_COLUMN) or "").strip()
        if not case_id:
            raise ScinInventoryError(f"Blank case_id in cases CSV at row {row_number}")
        if case_id in indexed:
            raise ScinInventoryError(f"Duplicate case_id in cases CSV: {case_id}")
        indexed[case_id] = row
    return indexed


def _parse_boolean(value: str | None, field_name: str, case_id: str) -> bool:
    normalized = (value or "").strip().casefold()
    if normalized in {"true", "1", "yes", "y", "t", "si", "sí"}:
        return True
    if normalized in {"false", "0", "no", "n", "f", ""}:
        return False
    raise ScinInventoryError(
        f"Unsupported boolean value {value!r} for {field_name} in case {case_id}"
    )


def _parse_weighted_labels(value: str | None, case_id: str) -> dict[str, float]:
    serialized = (value or "").strip()
    if not serialized:
        return {}

    try:
        parsed = ast.literal_eval(serialized)
    except (SyntaxError, ValueError) as exc:
        raise ScinInventoryError(
            f"Malformed {WEIGHTED_LABEL_COLUMN} for case {case_id}"
        ) from exc

    if not isinstance(parsed, Mapping):
        raise ScinInventoryError(
            f"{WEIGHTED_LABEL_COLUMN} must be a mapping for case {case_id}"
        )

    weights: dict[str, float] = {}
    for label, raw_weight in parsed.items():
        if not isinstance(label, str) or not label.strip():
            raise ScinInventoryError(f"Invalid weighted label name for case {case_id}")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError) as exc:
            raise ScinInventoryError(
                f"Invalid weight for label {label!r} in case {case_id}"
            ) from exc
        if not math.isfinite(weight) or weight < 0:
            raise ScinInventoryError(
                f"Weight for label {label!r} must be finite and non-negative "
                f"in case {case_id}"
            )
        weights[label.strip()] = weight
    return weights


def _target_weight(weights: Mapping[str, float], target_condition: str) -> float | None:
    normalized_target = target_condition.strip().casefold()
    for label, weight in weights.items():
        if label.casefold() == normalized_target:
            return weight
    return None


def _images_for_case(case: Mapping[str, str]) -> list[dict[str, str]]:
    images: list[dict[str, str]] = []
    for index, path_column in enumerate(IMAGE_PATH_COLUMNS):
        image_path = (case.get(path_column) or "").strip()
        if not image_path:
            continue
        shot_column = IMAGE_SHOT_TYPE_COLUMNS[index]
        images.append(
            {
                "path": image_path,
                "shot_type": (case.get(shot_column) or "").strip(),
            }
        )
    return images


def build_inventory(
    cases_path: Path,
    labels_path: Path,
    *,
    target_condition: str = TARGET_CONDITION,
    minimum_weight: float = 0.0,
) -> dict[str, Any]:
    """Join SCIN metadata and select cases that require manual image review."""
    if not target_condition.strip():
        raise ScinInventoryError("target_condition cannot be blank")
    if not math.isfinite(minimum_weight) or minimum_weight < 0:
        raise ScinInventoryError("minimum_weight must be finite and non-negative")

    case_rows = _read_csv(
        cases_path,
        (CASE_ID_COLUMN, HEAD_OR_NECK_COLUMN, *IMAGE_PATH_COLUMNS),
    )
    label_rows = _read_csv(
        labels_path,
        (CASE_ID_COLUMN, WEIGHTED_LABEL_COLUMN, *GRADABLE_COLUMNS),
    )
    cases_by_id = _index_unique_cases(case_rows)

    summary = {
        "case_rows": len(case_rows),
        "label_rows": len(label_rows),
        "target_cases": 0,
        "target_images": 0,
        "target_head_or_neck_cases": 0,
        "target_head_or_neck_images": 0,
        "candidate_cases_for_manual_review": 0,
        "candidate_images_for_manual_review": 0,
        "target_cases_missing_metadata": 0,
        "target_cases_without_images": 0,
        "target_cases_without_gradable_vote": 0,
    }
    candidates: list[dict[str, Any]] = []
    seen_label_cases: set[str] = set()

    for row_number, label_row in enumerate(label_rows, start=2):
        case_id = (label_row.get(CASE_ID_COLUMN) or "").strip()
        if not case_id:
            raise ScinInventoryError(f"Blank case_id in labels CSV at row {row_number}")
        if case_id in seen_label_cases:
            raise ScinInventoryError(f"Duplicate case_id in labels CSV: {case_id}")
        seen_label_cases.add(case_id)

        weights = _parse_weighted_labels(
            label_row.get(WEIGHTED_LABEL_COLUMN),
            case_id,
        )
        weight = _target_weight(weights, target_condition)
        if weight is None or weight < minimum_weight:
            continue

        summary["target_cases"] += 1
        case = cases_by_id.get(case_id)
        if case is None:
            summary["target_cases_missing_metadata"] += 1
            continue

        images = _images_for_case(case)
        summary["target_images"] += len(images)
        if not images:
            summary["target_cases_without_images"] += 1

        head_or_neck = _parse_boolean(
            case.get(HEAD_OR_NECK_COLUMN),
            HEAD_OR_NECK_COLUMN,
            case_id,
        )
        if head_or_neck:
            summary["target_head_or_neck_cases"] += 1
            summary["target_head_or_neck_images"] += len(images)

        gradable_votes = sum(
            _parse_boolean(label_row.get(column), column, case_id)
            for column in GRADABLE_COLUMNS
        )
        if gradable_votes == 0:
            summary["target_cases_without_gradable_vote"] += 1

        if not head_or_neck or not images or gradable_votes == 0:
            continue

        candidates.append(
            {
                "case_id": case_id,
                "target_weight": weight,
                "gradable_votes": gradable_votes,
                "image_count": len(images),
                "images": images,
            }
        )

    summary["candidate_cases_for_manual_review"] = len(candidates)
    summary["candidate_images_for_manual_review"] = sum(
        candidate["image_count"] for candidate in candidates
    )

    return {
        "source": "SCIN",
        "target_condition": target_condition,
        "minimum_weight": minimum_weight,
        "selection_status": (
            "ready_for_manual_review" if candidates else "no_candidates_for_manual_review"
        ),
        "training_status": "not_approved",
        "summary": summary,
        "candidates": candidates,
    }


def write_json_report(report: Mapping[str, Any], destination: Path) -> None:
    """Write an inventory report without downloading source images."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_candidates_csv(report: Mapping[str, Any], destination: Path) -> None:
    """Write one row per candidate image for subsequent manual review."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = (
        "case_id",
        "image_path",
        "image_shot_type",
        "target_weight",
        "gradable_votes",
    )
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for candidate in report["candidates"]:
            for image in candidate["images"]:
                writer.writerow(
                    {
                        "case_id": candidate["case_id"],
                        "image_path": image["path"],
                        "image_shot_type": image["shot_type"],
                        "target_weight": candidate["target_weight"],
                        "gradable_votes": candidate["gradable_votes"],
                    }
                )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inventory SCIN cutaneous-lupus head/neck cases for manual review. "
            "This command never approves data for training."
        )
    )
    parser.add_argument("--cases", required=True, type=Path, help="Path to scin_cases.csv")
    parser.add_argument("--labels", required=True, type=Path, help="Path to scin_labels.csv")
    parser.add_argument(
        "--target-condition",
        default=TARGET_CONDITION,
        help=f"Weighted label to inventory (default: {TARGET_CONDITION})",
    )
    parser.add_argument(
        "--minimum-weight",
        default=0.0,
        type=float,
        help="Minimum weighted-label value to include",
    )
    parser.add_argument("--report", type=Path, help="Optional JSON report destination")
    parser.add_argument(
        "--candidates",
        type=Path,
        help="Optional candidate-image CSV destination",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        report = build_inventory(
            args.cases,
            args.labels,
            target_condition=args.target_condition,
            minimum_weight=args.minimum_weight,
        )
        if args.report:
            write_json_report(report, args.report)
        if args.candidates:
            write_candidates_csv(report, args.candidates)
    except ScinInventoryError as exc:
        parser.exit(2, f"error: {exc}\n")

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"selection_status: {report['selection_status']}")
    print("training_status: not_approved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
