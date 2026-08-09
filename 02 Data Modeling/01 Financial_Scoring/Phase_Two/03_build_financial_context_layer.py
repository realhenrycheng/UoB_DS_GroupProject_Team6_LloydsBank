#!/usr/bin/env python3
"""
Build the Phase-1.5 financial context layer.

The script reads the frozen Phase-1 calibrated company table and appends
explanation-only fields:

* the global percentile for the calibrated Primary dimension;
* the corresponding within-cluster percentile;
* the cluster-minus-global peer gap;
* the selected cluster reference count;
* bilingual peer and evidence summaries.

It never changes the existing Deepen, Grow or Defend scores, calibrated
Primary, Priority, or queue ranking. Cluster and evidence tier are context,
not business-need labels, score multipliers, or probabilities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_BUCKET = "team6-project-288469846191-eu-north-1-an"
DEFAULT_INPUT_PREFIX = (
    "models/financial_scoring/phase1_basic-mark/calibrated-results"
)
DEFAULT_CONFIG_KEY = (
    "models/financial_scoring/phase1_context-layer/config/"
    "context_config.json"
)
DEFAULT_OUTPUT_PREFIX = (
    "models/financial_scoring/phase1_context-layer/results"
)
INPUT_FILENAME = "financial_calibrated_scores.csv"
COMPANY_KEY = "CompanyNumber_norm"
NORMAL_PRIMARY_DIMENSIONS = ("Deepen", "Grow", "Defend")

CONTEXT_COLUMNS = [
    "primary_global_percentile",
    "primary_cluster_percentile",
    "primary_peer_gap",
    "primary_cluster_reference_count",
    "primary_dimension_coverage",
    "peer_context_status",
    "peer_context_summary_en",
    "peer_context_summary_cn",
    "evidence_context_summary_en",
    "evidence_context_summary_cn",
    "context_layer_version",
    "context_score_adjustment_status",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Append Cluster peer context and evidence explanations to the "
            "frozen Phase-1 calibrated financial table."
        )
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--calibrated-results-prefix", default=DEFAULT_INPUT_PREFIX)
    parser.add_argument("--calibrated-score-key")
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
        / "financial_context_layer",
    )
    parser.add_argument("--local-score-path", type=Path)
    parser.add_argument("--local-config-path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Write local outputs but do not upload them to S3.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
    )


def normalise_prefix(prefix: str) -> str:
    return prefix.strip().strip("/")


def get_s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3 mode. Install it with "
            "`python -m pip install boto3`, or use local paths with "
            "--no-upload."
        ) from exc
    return boto3.client("s3")


def find_latest_s3_key(
    s3,
    bucket: str,
    prefix: str,
    filename: str,
) -> str:
    prefix = normalise_prefix(prefix)
    paginator = s3.get_paginator("list_objects_v2")
    candidates: list[dict[str, Any]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
        for item in page.get("Contents", []):
            key = str(item["Key"])
            if key.endswith(f"/{filename}") or key == f"{prefix}/{filename}":
                candidates.append(item)
    if not candidates:
        raise FileNotFoundError(
            f"No {filename} found under s3://{bucket}/{prefix}/"
        )
    latest = max(candidates, key=lambda item: item["LastModified"])
    return str(latest["Key"])


def download_s3_file(
    s3,
    bucket: str,
    key: str,
    target: Path,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    logging.info("Downloading s3://%s/%s", bucket, key)
    s3.download_file(bucket, key, str(target))
    return target


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv_checked(path: Path) -> pd.DataFrame:
    logging.info("Reading %s", path)
    frame = pd.read_csv(path, low_memory=False)
    if COMPANY_KEY not in frame.columns:
        raise ValueError(f"Input is missing company key {COMPANY_KEY}")
    frame[COMPANY_KEY] = (
        frame[COMPANY_KEY].astype("string").str.strip().str.upper()
    )
    if frame[COMPANY_KEY].isna().any():
        raise ValueError("Company key contains missing values")
    if frame[COMPANY_KEY].duplicated().any():
        raise ValueError("Company key contains duplicate values")
    return frame


def to_bool(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalised = series.astype("string").str.strip().str.lower()
    valid = normalised.isin(["true", "false"]) | normalised.isna()
    if not valid.all():
        bad = sorted(normalised.loc[~valid].dropna().unique().tolist())
        raise ValueError(f"Boolean column contains invalid values: {bad[:10]}")
    return normalised.eq("true")


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "context_layer_id",
        "version",
        "input_contract",
        "dimensions",
        "primary_column",
        "priority_queue_percentile_column",
        "cluster",
        "evidence",
        "policy",
        "text",
        "semantics",
    ]
    missing = [key for key in required if key not in config]
    if missing:
        raise ValueError(f"Context config is missing keys: {missing}")
    if tuple(config["dimensions"].keys()) != NORMAL_PRIMARY_DIMENSIONS:
        raise ValueError(
            "Config dimensions must be ordered as Deepen, Grow, Defend"
        )
    forbidden_true = [
        key for key, value in config["policy"].items() if bool(value)
    ]
    if forbidden_true:
        raise ValueError(
            "FIN_CONTEXT_V1.0 is explanation-only; policy flags must all "
            f"be false. Invalid true flags: {forbidden_true}"
        )


def required_input_columns(config: dict[str, Any]) -> list[str]:
    required = [
        config["input_contract"]["company_key"],
        config["input_contract"]["eligible_column"],
        config["primary_column"],
        config["priority_queue_percentile_column"],
        config["cluster"]["id_column"],
        config["cluster"]["name_column"],
        config["cluster"]["assignment_confidence_column"],
        config["evidence"]["tier_column"],
        config["evidence"]["accounts_age_column"],
        config["evidence"]["calibration_status_column"],
        "calibration_version",
    ]
    for fields in config["dimensions"].values():
        required.extend(fields.values())
    return list(dict.fromkeys(required))


def validate_input(frame: pd.DataFrame, config: dict[str, Any]) -> None:
    missing = [
        column for column in required_input_columns(config)
        if column not in frame.columns
    ]
    if missing:
        raise ValueError(f"Calibrated score file is missing columns: {missing}")
    collisions = [column for column in CONTEXT_COLUMNS if column in frame]
    if collisions:
        raise ValueError(
            "Input already contains context-layer columns; refusing to "
            f"overwrite: {collisions}"
        )
    expected_version = config["input_contract"][
        "required_calibration_version"
    ]
    versions = set(
        frame["calibration_version"].dropna().astype(str).unique().tolist()
    )
    if versions != {expected_version}:
        raise ValueError(
            "Unexpected calibration_version values. "
            f"Expected only {expected_version}, found {sorted(versions)}"
        )


def select_primary_values(
    output: pd.DataFrame,
    primary: pd.Series,
    config: dict[str, Any],
    field_name: str,
) -> pd.Series:
    selected = pd.Series(np.nan, index=output.index, dtype="float64")
    for label, fields in config["dimensions"].items():
        mask = primary.eq(label)
        selected.loc[mask] = pd.to_numeric(
            output.loc[mask, fields[field_name]],
            errors="coerce",
        )
    return selected


def format_number(value: Any, decimals: int) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{float(value):.{decimals}f}"


def format_integer(value: Any) -> str:
    if value is None or pd.isna(value):
        return "N/A"
    return f"{int(round(float(value))):,}"


def build_peer_summary(
    row: pd.Series,
    language: str,
    decimals: int,
) -> str:
    status = str(row["peer_context_status"])
    primary = str(row.get("_context_primary", ""))
    global_value = row["primary_global_percentile"]
    cluster_value = row["primary_cluster_percentile"]
    gap = row["primary_peer_gap"]
    reference_count = row["primary_cluster_reference_count"]
    cluster_id = row.get("_context_cluster_id")

    if language == "en":
        if status == "AVAILABLE":
            return (
                f"{primary} global P{format_number(global_value, decimals)}; "
                f"{cluster_id} peer P{format_number(cluster_value, decimals)}; "
                f"gap {float(gap):+.{decimals}f}; peer reference "
                f"n={format_integer(reference_count)}."
            )
        if status == "GLOBAL_ONLY_NO_CLUSTER":
            return (
                f"{primary} global P{format_number(global_value, decimals)}; "
                "no Cluster peer percentile is available."
            )
        if status == "CLUSTER_PERCENTILE_UNAVAILABLE":
            return (
                f"{primary} global P{format_number(global_value, decimals)}; "
                f"{cluster_id} is assigned but its {primary} peer percentile "
                "is unavailable."
            )
        if status == "MIXED_PRIMARY":
            return (
                "Mixed calibrated Primary; use the separate dimension-level "
                "global and Cluster percentiles."
            )
        if status == "NO_ACTIVE_SIGNAL":
            return "No active Deepen, Grow or Defend signal."
        return "Not eligible for three-way Primary peer context."

    if status == "AVAILABLE":
        return (
            f"{primary}总体P{format_number(global_value, decimals)}；"
            f"{cluster_id}同类P{format_number(cluster_value, decimals)}；"
            f"差值{float(gap):+.{decimals}f}；同类参考公司"
            f"{format_integer(reference_count)}家。"
        )
    if status == "GLOBAL_ONLY_NO_CLUSTER":
        return (
            f"{primary}总体P{format_number(global_value, decimals)}；"
            "没有可用的Cluster同类百分位。"
        )
    if status == "CLUSTER_PERCENTILE_UNAVAILABLE":
        return (
            f"{primary}总体P{format_number(global_value, decimals)}；"
            f"公司已归入{cluster_id}，但该维度同类百分位不可用。"
        )
    if status == "MIXED_PRIMARY":
        return "Primary为混合并列；请分别查看三维总体和Cluster百分位。"
    if status == "NO_ACTIVE_SIGNAL":
        return "Deepen、Grow和Defend均无活跃信号。"
    return "不满足三维Primary同类解释条件。"


def build_evidence_summary(
    row: pd.Series,
    language: str,
    coverage_decimals: int,
) -> str:
    tier = row.get("_context_tier")
    age = row.get("_context_accounts_age")
    calibration_status = row.get("_context_calibration_status")
    confidence = row.get("_context_cluster_confidence")

    def coverage_text(column: str) -> str:
        value = row.get(column)
        if value is None or pd.isna(value):
            return "N/A"
        return f"{100 * float(value):.{coverage_decimals}f}%"

    deepen_coverage = coverage_text("deepen_coverage")
    grow_coverage = coverage_text("grow_coverage")
    defend_coverage = coverage_text("defend_coverage")
    tier_text = "N/A" if tier is None or pd.isna(tier) else str(tier)
    age_text = format_integer(age)
    status_text = (
        "N/A"
        if calibration_status is None or pd.isna(calibration_status)
        else str(calibration_status)
    )
    confidence_text = (
        "N/A"
        if confidence is None or pd.isna(confidence)
        else str(confidence)
    )
    if language == "en":
        return (
            f"Evidence {tier_text}; coverage Deepen {deepen_coverage}, "
            f"Grow {grow_coverage}, Defend {defend_coverage}; accounts age "
            f"{age_text} days; calibration status {status_text}; Cluster "
            f"assignment confidence {confidence_text}."
        )
    return (
        f"证据等级{tier_text}；覆盖率Deepen {deepen_coverage}、"
        f"Grow {grow_coverage}、Defend {defend_coverage}；"
        f"账户年龄{age_text}天；校准状态{status_text}；"
        f"Cluster归属置信度{confidence_text}。"
    )


def build_company_context(
    calibrated: pd.DataFrame,
    config: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    output = calibrated.copy()
    original_columns = calibrated.columns.tolist()
    eligible_column = config["input_contract"]["eligible_column"]
    eligible = to_bool(output[eligible_column])
    primary_column = config["primary_column"]
    primary = output[primary_column].astype("string").str.strip()
    normal_primary = primary.isin(NORMAL_PRIMARY_DIMENSIONS)
    mixed_primary = primary.str.startswith("MIXED:", na=False)
    no_active_signal = primary.eq("UNKNOWN_NO_ACTIVE_SIGNAL")

    cluster_id_column = config["cluster"]["id_column"]
    cluster_id = output[cluster_id_column].astype("string").str.strip()
    cluster_available = cluster_id.notna() & cluster_id.ne("")

    output["primary_global_percentile"] = select_primary_values(
        output, primary, config, "global_percentile"
    )
    output["primary_cluster_percentile"] = select_primary_values(
        output, primary, config, "cluster_percentile"
    )
    output["primary_peer_gap"] = (
        output["primary_cluster_percentile"]
        - output["primary_global_percentile"]
    )
    output["primary_cluster_reference_count"] = select_primary_values(
        output, primary, config, "cluster_reference_count"
    )
    output["primary_dimension_coverage"] = select_primary_values(
        output, primary, config, "coverage"
    )

    status = pd.Series(
        "NOT_THREE_WAY_ELIGIBLE",
        index=output.index,
        dtype="string",
    )
    status.loc[eligible & no_active_signal] = "NO_ACTIVE_SIGNAL"
    status.loc[eligible & mixed_primary] = "MIXED_PRIMARY"
    status.loc[eligible & normal_primary & ~cluster_available] = (
        "GLOBAL_ONLY_NO_CLUSTER"
    )
    cluster_missing_percentile = (
        eligible
        & normal_primary
        & cluster_available
        & output["primary_cluster_percentile"].isna()
    )
    status.loc[cluster_missing_percentile] = (
        "CLUSTER_PERCENTILE_UNAVAILABLE"
    )
    available = (
        eligible
        & normal_primary
        & cluster_available
        & output["primary_global_percentile"].notna()
        & output["primary_cluster_percentile"].notna()
        & output["primary_cluster_reference_count"].notna()
    )
    status.loc[available] = "AVAILABLE"
    output["peer_context_status"] = status

    helper_columns = {
        "_context_primary": primary,
        "_context_cluster_id": cluster_id,
        "_context_tier": output[config["evidence"]["tier_column"]],
        "_context_accounts_age": output[
            config["evidence"]["accounts_age_column"]
        ],
        "_context_calibration_status": output[
            config["evidence"]["calibration_status_column"]
        ],
        "_context_cluster_confidence": output[
            config["cluster"]["assignment_confidence_column"]
        ],
    }
    for column, values in helper_columns.items():
        output[column] = values

    percentile_decimals = int(config["text"]["percentile_decimals"])
    coverage_decimals = int(config["text"]["coverage_decimals"])
    output["peer_context_summary_en"] = output.apply(
        build_peer_summary,
        axis=1,
        language="en",
        decimals=percentile_decimals,
    )
    output["peer_context_summary_cn"] = output.apply(
        build_peer_summary,
        axis=1,
        language="cn",
        decimals=percentile_decimals,
    )
    output["evidence_context_summary_en"] = output.apply(
        build_evidence_summary,
        axis=1,
        language="en",
        coverage_decimals=coverage_decimals,
    )
    output["evidence_context_summary_cn"] = output.apply(
        build_evidence_summary,
        axis=1,
        language="cn",
        coverage_decimals=coverage_decimals,
    )
    output.drop(columns=list(helper_columns), inplace=True)

    output["context_layer_version"] = (
        f"{config['context_layer_id']}_V{config['version']}"
    )
    output["context_score_adjustment_status"] = "NOT_APPLIED"

    expected_columns = original_columns + CONTEXT_COLUMNS
    if output.columns.tolist() != expected_columns:
        raise AssertionError("Context columns were not appended as expected")
    pd.testing.assert_frame_equal(
        output[original_columns],
        calibrated[original_columns],
        check_dtype=True,
        check_exact=True,
    )

    valid_peer = output["peer_context_status"].eq("AVAILABLE")
    diagnostics = {
        "companies_total": int(len(output)),
        "original_columns": int(len(original_columns)),
        "output_columns": int(len(output.columns)),
        "three_way_eligible": int(eligible.sum()),
        "peer_context_available": int(valid_peer.sum()),
        "peer_context_status_counts": {
            str(key): int(value)
            for key, value in output["peer_context_status"]
            .value_counts(dropna=False)
            .items()
        },
        "peer_gap_mean": float(
            output.loc[valid_peer, "primary_peer_gap"].mean()
        ),
        "peer_gap_median": float(
            output.loc[valid_peer, "primary_peer_gap"].median()
        ),
        "peer_gap_minimum": float(
            output.loc[valid_peer, "primary_peer_gap"].min()
        ),
        "peer_gap_maximum": float(
            output.loc[valid_peer, "primary_peer_gap"].max()
        ),
        "score_adjustments_applied": 0,
    }
    return output, diagnostics


def safe_share(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return numerator.div(denominator.replace(0, np.nan))


def build_cluster_score_profiles(
    company_context: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    cluster_id_column = config["cluster"]["id_column"]
    cluster_name_column = config["cluster"]["name_column"]
    confidence_column = config["cluster"]["assignment_confidence_column"]
    eligible = to_bool(
        company_context[config["input_contract"]["eligible_column"]]
    )
    clustered = company_context[cluster_id_column].notna()
    data = company_context.loc[clustered].copy()
    data["_eligible"] = eligible.loc[data.index]
    data["_is_deepen"] = data[config["primary_column"]].eq("Deepen")
    data["_is_grow"] = data[config["primary_column"]].eq("Grow")
    data["_is_defend"] = data[config["primary_column"]].eq("Defend")
    data["_is_unknown"] = data[config["primary_column"]].eq(
        "UNKNOWN_NO_ACTIVE_SIGNAL"
    )
    data["_is_mixed"] = data[config["primary_column"]].astype(
        "string"
    ).str.startswith("MIXED:", na=False)
    data["_is_top_decile"] = (
        data[config["priority_queue_percentile_column"]] >= 90
    )
    data["_confidence_high"] = data[confidence_column].eq("High")
    data["_confidence_medium"] = data[confidence_column].eq("Medium")
    data["_confidence_low"] = data[confidence_column].eq("Low")
    complete_only_columns = [
        "priority_calibrated",
        "primary_peer_gap",
        "deepen_comparison_percentile",
        "deepen_cluster_percentile",
        "grow_comparison_percentile",
        "grow_cluster_percentile",
        "defend_comparison_percentile",
        "defend_cluster_percentile",
    ]
    for column in complete_only_columns:
        data[f"_complete_{column}"] = pd.to_numeric(
            data[column], errors="coerce"
        ).where(data["_eligible"])

    grouped = data.groupby(cluster_id_column, sort=True, dropna=False)
    profile = grouped.agg(
        cluster_name=(cluster_name_column, "first"),
        companies=(COMPANY_KEY, "size"),
        complete_companies=("_eligible", "sum"),
        high_confidence_companies=("_confidence_high", "sum"),
        medium_confidence_companies=("_confidence_medium", "sum"),
        low_confidence_companies=("_confidence_low", "sum"),
        deepen_primary_companies=("_is_deepen", "sum"),
        grow_primary_companies=("_is_grow", "sum"),
        defend_primary_companies=("_is_defend", "sum"),
        unknown_primary_companies=("_is_unknown", "sum"),
        mixed_primary_companies=("_is_mixed", "sum"),
        global_top_decile_companies=("_is_top_decile", "sum"),
        priority_mean=("_complete_priority_calibrated", "mean"),
        priority_median=("_complete_priority_calibrated", "median"),
        primary_peer_gap_mean=("_complete_primary_peer_gap", "mean"),
        primary_peer_gap_median=("_complete_primary_peer_gap", "median"),
        deepen_global_median=(
            "_complete_deepen_comparison_percentile",
            "median",
        ),
        deepen_cluster_median=(
            "_complete_deepen_cluster_percentile",
            "median",
        ),
        grow_global_median=(
            "_complete_grow_comparison_percentile",
            "median",
        ),
        grow_cluster_median=(
            "_complete_grow_cluster_percentile",
            "median",
        ),
        defend_global_median=(
            "_complete_defend_comparison_percentile",
            "median",
        ),
        defend_cluster_median=(
            "_complete_defend_cluster_percentile",
            "median",
        ),
    ).reset_index()

    profile["complete_rate"] = safe_share(
        profile["complete_companies"], profile["companies"]
    )
    for label in ["deepen", "grow", "defend", "unknown", "mixed"]:
        profile[f"{label}_primary_share_of_complete"] = safe_share(
            profile[f"{label}_primary_companies"],
            profile["complete_companies"],
        )
    profile["global_top_decile_share_of_complete"] = safe_share(
        profile["global_top_decile_companies"],
        profile["complete_companies"],
    )
    for label in ["high", "medium", "low"]:
        profile[f"{label}_confidence_share"] = safe_share(
            profile[f"{label}_confidence_companies"],
            profile["companies"],
        )
    return profile


def build_cluster_evidence_profiles(
    company_context: pd.DataFrame,
    config: dict[str, Any],
) -> pd.DataFrame:
    cluster_id_column = config["cluster"]["id_column"]
    cluster_name_column = config["cluster"]["name_column"]
    tier_column = config["evidence"]["tier_column"]
    confidence_column = config["cluster"]["assignment_confidence_column"]
    eligible = to_bool(
        company_context[config["input_contract"]["eligible_column"]]
    )
    data = company_context.copy()
    data["_cluster_group"] = (
        data[cluster_id_column].astype("string").fillna("NO_CLUSTER")
    )
    data["_tier_group"] = (
        data[tier_column].astype("string").fillna("NO_TIER")
    )
    data["_eligible"] = eligible
    data["_confidence_high"] = data[confidence_column].eq("High")
    data["_confidence_medium"] = data[confidence_column].eq("Medium")
    data["_confidence_low"] = data[confidence_column].eq("Low")

    grouped = data.groupby(
        ["_cluster_group", "_tier_group"],
        sort=True,
        dropna=False,
    )
    profile = grouped.agg(
        cluster_name=(cluster_name_column, "first"),
        companies=(COMPANY_KEY, "size"),
        complete_companies=("_eligible", "sum"),
        deepen_coverage_mean=("deepen_coverage", "mean"),
        grow_coverage_mean=("grow_coverage", "mean"),
        defend_coverage_mean=("defend_coverage", "mean"),
        accounts_age_days_median=(
            config["evidence"]["accounts_age_column"],
            "median",
        ),
        high_confidence_companies=("_confidence_high", "sum"),
        medium_confidence_companies=("_confidence_medium", "sum"),
        low_confidence_companies=("_confidence_low", "sum"),
    ).reset_index()
    profile.rename(
        columns={
            "_cluster_group": "financial_cluster_id",
            "_tier_group": "financial_evidence_tier",
        },
        inplace=True,
    )
    profile["complete_rate"] = safe_share(
        profile["complete_companies"], profile["companies"]
    )
    for label in ["high", "medium", "low"]:
        profile[f"{label}_confidence_share"] = safe_share(
            profile[f"{label}_confidence_companies"],
            profile["companies"],
        )
    return profile


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8")
    logging.info("Wrote %s (%s rows)", path.name, f"{len(frame):,}")


def upload_outputs(
    s3,
    bucket: str,
    output_prefix: str,
    run_id: str,
    output_dir: Path,
) -> list[str]:
    destination = f"{normalise_prefix(output_prefix)}/run_id={run_id}"
    uploaded: list[str] = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file():
            continue
        key = f"{destination}/{path.name}"
        logging.info("Uploading %s to s3://%s/%s", path.name, bucket, key)
        s3.upload_file(str(path), bucket, key)
        uploaded.append(f"s3://{bucket}/{key}")
    return uploaded


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work_dir = args.work_dir.resolve()
    input_dir = work_dir / "input"
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else work_dir / "output" / f"run_id={run_id}"
    )
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    needs_s3 = (
        args.local_score_path is None
        or args.local_config_path is None
        or not args.no_upload
    )
    s3 = get_s3_client() if needs_s3 else None

    if args.local_score_path:
        score_path = args.local_score_path.resolve()
        score_source = str(score_path)
    else:
        score_key = args.calibrated_score_key or find_latest_s3_key(
            s3,
            args.bucket,
            args.calibrated_results_prefix,
            INPUT_FILENAME,
        )
        score_path = download_s3_file(
            s3,
            args.bucket,
            score_key,
            input_dir / INPUT_FILENAME,
        )
        score_source = f"s3://{args.bucket}/{score_key}"

    if args.local_config_path:
        config_path = args.local_config_path.resolve()
        config_source = str(config_path)
    else:
        config_path = download_s3_file(
            s3,
            args.bucket,
            args.config_key,
            input_dir / "context_config.json",
        )
        config_source = f"s3://{args.bucket}/{args.config_key}"

    config = load_json(config_path)
    validate_config(config)
    calibrated = read_csv_checked(score_path)
    validate_input(calibrated, config)
    company_context, diagnostics = build_company_context(
        calibrated,
        config,
    )
    cluster_scores = build_cluster_score_profiles(
        company_context,
        config,
    )
    cluster_evidence = build_cluster_evidence_profiles(
        company_context,
        config,
    )

    company_path = output_dir / "financial_company_context.csv"
    cluster_score_path = output_dir / "cluster_score_profiles.csv"
    cluster_evidence_path = output_dir / "cluster_evidence_profiles.csv"
    write_csv(company_context, company_path)
    write_csv(cluster_scores, cluster_score_path)
    write_csv(cluster_evidence, cluster_evidence_path)

    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "context_layer_id": config["context_layer_id"],
        "context_layer_version": str(config["version"]),
        "context_type": "cluster_peer_and_evidence_explanation_only",
        "score_source": score_source,
        "score_source_sha256": sha256_file(score_path),
        "config_source": config_source,
        "config_sha256": sha256_file(config_path),
        "bucket": args.bucket,
        "output_prefix": normalise_prefix(args.output_prefix),
        "diagnostics": diagnostics,
        "policy": config["policy"],
        "semantics": config["semantics"],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "local_outputs": [
            "financial_company_context.csv",
            "cluster_score_profiles.csv",
            "cluster_evidence_profiles.csv",
            "financial_context_manifest.json",
        ],
    }
    manifest_path = output_dir / "financial_context_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    uploaded: list[str] = []
    if not args.no_upload:
        uploaded = upload_outputs(
            s3,
            args.bucket,
            args.output_prefix,
            run_id,
            output_dir,
        )
    logging.info("Financial context layer completed")
    logging.info("Local output directory: %s", output_dir)
    if uploaded:
        logging.info(
            "S3 output directory: s3://%s/%s/run_id=%s/",
            args.bucket,
            normalise_prefix(args.output_prefix),
            run_id,
        )


if __name__ == "__main__":
    main()
