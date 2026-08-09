#!/usr/bin/env python3
"""
Calibrate Phase-1 Deepen / Grow / Defend scores onto comparable percentiles.

The script preserves the transparent Phase-1 raw scores and adds three distinct
ranking views:

1. Common-reference percentiles:
   calculated only for COMPLETE companies and used for cross-dimension
   Primary / Priority comparison.
2. Dimension percentiles:
   calculated for every company with a valid score in that dimension and used
   for the three independent leaderboards.
3. Cluster percentiles:
   optional contextual peer ranks. They never add to or subtract from the
   calibrated global scores.

Evidence tier controls neither score level nor score direction. PARTIAL
companies may enter an available dimension leaderboard but are not assigned a
three-way calibrated Primary / Priority.

This is distributional rank calibration, not probability calibration and not
a verified prediction of Lloyds product demand.
"""

from __future__ import annotations

import argparse
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
DEFAULT_BASE_RESULTS_PREFIX = (
    "models/financial_scoring/phase1_basic-mark/results"
)
DEFAULT_CLUSTER_RESULTS_PREFIX = (
    "processed/financial_clustering/k_selection_v2"
)
DEFAULT_CONFIG_KEY = (
    "models/financial_scoring/phase1_basic-mark/config/"
    "calibration_config.json"
)
DEFAULT_OUTPUT_PREFIX = (
    "models/financial_scoring/phase1_basic-mark/calibrated-results"
)
COMPANY_KEY = "CompanyNumber_norm"
BASE_FILENAME = "financial_base_scores.csv"
CLUSTER_FILENAME = "company_cluster_assignments.csv"

DEFAULT_OUTPUT_COLUMNS = [
    COMPANY_KEY,
    "CompanyName",
    "primary_sector",
    "Accounts_AccountCategory",
    "latest_period_end",
    "latest_available_date",
    "financial_evidence_tier",
    "accounts_age_days_at_snapshot",
    "accounts_older_than_24m_flag",
    "main_cohort_flag",
    "deepen_base_score",
    "grow_base_score",
    "defend_base_score",
    "deepen_coverage",
    "grow_coverage",
    "defend_coverage",
    "priority_base_score",
    "primary_dimension",
    "secondary_dimension",
    "top_reason_codes",
    "peer_scope_used",
    "score_status",
    "rule_version",
    "reporting_scenario",
    "deepen_global_rank",
    "deepen_peer_rank",
    "grow_global_rank",
    "grow_peer_rank",
    "defend_global_rank",
    "defend_peer_rank",
    "priority_global_rank",
]

CLUSTER_COLUMNS = [
    COMPANY_KEY,
    "financial_cluster_id",
    "cluster_number",
    "cluster_name_auto",
    "cluster_assignment_confidence",
    "assignment_margin",
    "cluster_distance",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Calibrate Phase-1 Deepen/Grow/Defend scores to empirical "
            "percentiles."
        )
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument(
        "--base-results-prefix", default=DEFAULT_BASE_RESULTS_PREFIX
    )
    parser.add_argument(
        "--cluster-results-prefix",
        default=DEFAULT_CLUSTER_RESULTS_PREFIX,
    )
    parser.add_argument("--base-score-key")
    parser.add_argument("--cluster-key")
    parser.add_argument("--config-key", default=DEFAULT_CONFIG_KEY)
    parser.add_argument(
        "--output-prefix", default=DEFAULT_OUTPUT_PREFIX
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
        / "financial_score_calibration",
    )
    parser.add_argument("--local-base-score-path", type=Path)
    parser.add_argument("--local-cluster-path", type=Path)
    parser.add_argument("--local-config-path", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--no-cluster",
        action="store_true",
        help="Skip contextual cluster percentiles.",
    )
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


def normalise_company_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


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
            key = item["Key"]
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


def validate_config(config: dict[str, Any]) -> None:
    required = [
        "calibration_id",
        "version",
        "dimensions",
        "common_reference",
        "percentile_method",
        "cluster_context",
        "evidence_tier",
        "primary_assignment",
        "action_thresholds",
    ]
    missing = [name for name in required if name not in config]
    if missing:
        raise ValueError(
            f"Calibration config is missing required sections: {missing}"
        )
    if config["percentile_method"]["name"] != "empirical_midrank":
        raise ValueError("Only empirical_midrank is implemented in v1.0")
    if config["cluster_context"]["adjust_global_calibrated_score"]:
        raise ValueError(
            "Cluster score adjustment is prohibited in calibration v1.0"
        )
    if config["evidence_tier"]["adjust_score"]:
        raise ValueError(
            "Evidence-tier score adjustment is prohibited in v1.0"
        )
    if config["action_thresholds"]["enabled"]:
        raise ValueError(
            "Action thresholds require separate approved configuration"
        )


def read_csv_checked(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(
        path,
        dtype={COMPANY_KEY: "string"},
        low_memory=False,
    )
    if COMPANY_KEY not in frame.columns:
        raise ValueError(f"{path.name} is missing {COMPANY_KEY}")
    frame[COMPANY_KEY] = normalise_company_id(frame[COMPANY_KEY])
    duplicate_count = int(frame[COMPANY_KEY].duplicated().sum())
    if duplicate_count:
        raise ValueError(
            f"{path.name} contains {duplicate_count:,} duplicate company IDs"
        )
    return frame


def empirical_midrank(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    result = pd.Series(np.nan, index=series.index, dtype="float64")
    valid = numeric.notna()
    count = int(valid.sum())
    if count == 0:
        return result
    ranks = numeric.loc[valid].rank(method="average")
    result.loc[valid] = 100.0 * (ranks - 0.5) / count
    return result


def grouped_empirical_midrank(
    frame: pd.DataFrame,
    score_column: str,
    group_column: str,
    minimum_group_size: int,
) -> tuple[pd.Series, pd.Series]:
    result = pd.Series(np.nan, index=frame.index, dtype="float64")
    reference_count = pd.Series(
        pd.NA, index=frame.index, dtype="Int64"
    )
    eligible = (
        frame[score_column].notna() & frame[group_column].notna()
    )
    if not eligible.any():
        return result, reference_count
    subset = frame.loc[eligible, [group_column, score_column]].copy()
    group_counts = subset.groupby(group_column)[score_column].transform(
        "count"
    )
    group_ranks = subset.groupby(group_column)[score_column].rank(
        method="average"
    )
    percentiles = 100.0 * (group_ranks - 0.5) / group_counts
    sufficiently_large = group_counts.ge(minimum_group_size)
    valid_index = subset.index[sufficiently_large]
    result.loc[valid_index] = percentiles.loc[valid_index]
    reference_count.loc[valid_index] = (
        group_counts.loc[valid_index].astype("Int64")
    )
    return result, reference_count


def join_cluster_data(
    scores: pd.DataFrame,
    clusters: pd.DataFrame | None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    if clusters is None:
        return scores.copy(), {
            "cluster_source_rows": 0,
            "cluster_matched_companies": 0,
        }
    available_columns = [
        column for column in CLUSTER_COLUMNS if column in clusters.columns
    ]
    if "financial_cluster_id" not in available_columns:
        raise ValueError(
            "Cluster source must contain financial_cluster_id"
        )
    merged = scores.merge(
        clusters[available_columns],
        on=COMPANY_KEY,
        how="left",
        validate="one_to_one",
    )
    diagnostics = {
        "cluster_source_rows": int(len(clusters)),
        "cluster_matched_companies": int(
            merged["financial_cluster_id"].notna().sum()
        ),
    }
    return merged, diagnostics


def assign_primary_and_priority(
    output: pd.DataFrame,
    comparison_columns: dict[str, str],
    raw_columns: dict[str, str],
    eligible: pd.Series,
    no_active_signal_label: str,
    tie_label_prefix: str,
) -> None:
    labels = list(comparison_columns)
    values = output[list(comparison_columns.values())].to_numpy(
        dtype="float64"
    )
    raw_values = output[
        [raw_columns[label] for label in labels]
    ].to_numpy(dtype="float64")
    primary = pd.Series(pd.NA, index=output.index, dtype="string")
    secondary = pd.Series(pd.NA, index=output.index, dtype="string")
    priority = pd.Series(np.nan, index=output.index, dtype="float64")
    margin = pd.Series(np.nan, index=output.index, dtype="float64")
    tie_flag = pd.Series(pd.NA, index=output.index, dtype="boolean")
    assignment_status = pd.Series(
        "NOT_THREE_WAY_ELIGIBLE",
        index=output.index,
        dtype="string",
    )

    eligible_positions = np.flatnonzero(eligible.to_numpy())
    for position in eligible_positions:
        row = values[position].copy()
        active = raw_values[position] > 0
        active_count = int(active.sum())
        if active_count == 0:
            primary.iat[position] = no_active_signal_label
            priority.iat[position] = 0.0
            tie_flag.iat[position] = False
            assignment_status.iat[position] = "NO_ACTIVE_SIGNAL"
            continue
        row[~active] = np.nan
        order = np.argsort(
            -np.nan_to_num(row, nan=-np.inf),
            kind="stable",
        )
        top_index = int(order[0])
        top_value = float(row[top_index])
        priority.iat[position] = top_value
        if active_count == 1:
            primary.iat[position] = labels[top_index]
            tie_flag.iat[position] = False
            assignment_status.iat[position] = "ASSIGNED"
            continue
        second_index = int(order[1])
        second_value = float(row[second_index])
        is_tie = bool(np.isclose(top_value, second_value, atol=1e-12))
        margin.iat[position] = top_value - second_value
        tie_flag.iat[position] = is_tie
        if is_tie:
            tied_labels = [
                labels[index]
                for index, value in enumerate(row)
                if np.isfinite(value)
                and np.isclose(value, top_value, atol=1e-12)
            ]
            primary.iat[position] = (
                f"{tie_label_prefix}:" + "|".join(tied_labels)
            )
            assignment_status.iat[position] = "MIXED_TIE"
        else:
            primary.iat[position] = labels[top_index]
            secondary.iat[position] = labels[second_index]
            assignment_status.iat[position] = "ASSIGNED"

    output["primary_dimension_calibrated"] = primary
    output["secondary_dimension_calibrated"] = secondary
    output["priority_calibrated"] = priority
    output["primary_margin"] = margin
    output["primary_tie_flag"] = tie_flag
    output["primary_assignment_status"] = assignment_status


def make_distribution_summary(
    output: pd.DataFrame,
    dimensions: dict[str, str],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    scopes = {
        "common_complete": "_comparison_percentile",
        "dimension_all_valid": "_dimension_percentile",
        "cluster_context": "_cluster_percentile",
    }
    for scope, suffix in scopes.items():
        for label in dimensions:
            column = f"{label.lower()}{suffix}"
            if column not in output:
                continue
            values = output[column].dropna()
            rows.append(
                {
                    "scope": scope,
                    "dimension": label,
                    "company_count": int(len(values)),
                    "coverage_rate": float(len(values) / len(output)),
                    "mean": float(values.mean()) if len(values) else np.nan,
                    "standard_deviation": (
                        float(values.std(ddof=0))
                        if len(values)
                        else np.nan
                    ),
                    "p10": (
                        float(values.quantile(0.10))
                        if len(values)
                        else np.nan
                    ),
                    "median": (
                        float(values.quantile(0.50))
                        if len(values)
                        else np.nan
                    ),
                    "p90": (
                        float(values.quantile(0.90))
                        if len(values)
                        else np.nan
                    ),
                    "minimum": (
                        float(values.min()) if len(values) else np.nan
                    ),
                    "maximum": (
                        float(values.max()) if len(values) else np.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def build_calibrated_output(
    base_scores: pd.DataFrame,
    clusters: pd.DataFrame | None,
    config: dict[str, Any],
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, Any],
]:
    dimensions: dict[str, str] = config["dimensions"]
    required_columns = [
        config["common_reference"]["score_status_column"],
        *dimensions.values(),
    ]
    missing = [
        column for column in required_columns
        if column not in base_scores.columns
    ]
    if missing:
        raise ValueError(
            f"Base score file is missing required columns: {missing}"
        )

    merged, cluster_diagnostics = join_cluster_data(
        base_scores, clusters
    )
    output_columns = [
        column
        for column in DEFAULT_OUTPUT_COLUMNS + CLUSTER_COLUMNS[1:]
        if column in merged.columns
    ]
    output = merged[output_columns].copy()

    output["priority_raw_max"] = output.get("priority_base_score")
    output["primary_dimension_raw"] = output.get("primary_dimension")
    dimension_available = output[
        list(dimensions.values())
    ].notna().sum(axis=1)
    output["dimension_available_count"] = dimension_available.astype(
        "Int64"
    )
    output["active_dimension_count"] = output[
        list(dimensions.values())
    ].gt(0).sum(axis=1).astype("Int64")

    status_column = config["common_reference"]["score_status_column"]
    eligible_value = config["common_reference"]["eligible_value"]
    common_eligible = (
        output[status_column].eq(eligible_value)
        & output[list(dimensions.values())].notna().all(axis=1)
    )
    output["three_way_calibration_eligible"] = common_eligible
    output["calibration_status"] = np.select(
        [
            common_eligible,
            dimension_available.gt(0),
        ],
        [
            "THREE_WAY_COMPLETE",
            "PARTIAL_DIMENSION_ONLY",
        ],
        default="INSUFFICIENT_EVIDENCE",
    )

    comparison_columns: dict[str, str] = {}
    for label, raw_column in dimensions.items():
        stem = label.lower()
        comparison_column = f"{stem}_comparison_percentile"
        dimension_column = f"{stem}_dimension_percentile"
        output[comparison_column] = np.nan
        output.loc[common_eligible, comparison_column] = (
            empirical_midrank(
                output.loc[common_eligible, raw_column]
            )
        )
        output[dimension_column] = empirical_midrank(output[raw_column])
        comparison_columns[label] = comparison_column

    assign_primary_and_priority(
        output,
        comparison_columns,
        dimensions,
        common_eligible,
        config["primary_assignment"]["no_active_signal_label"],
        config["primary_assignment"]["tie_label_prefix"],
    )

    output["priority_queue_rank"] = pd.Series(
        pd.NA, index=output.index, dtype="Int64"
    )
    output["priority_queue_percentile"] = np.nan
    complete_priority = output.loc[
        common_eligible, "priority_calibrated"
    ]
    output.loc[
        common_eligible, "priority_queue_rank"
    ] = (
        complete_priority.rank(
            method="min",
            ascending=False,
        )
        .astype("Int64")
    )
    output.loc[
        common_eligible, "priority_queue_percentile"
    ] = empirical_midrank(complete_priority)

    cluster_minimum = int(
        config["cluster_context"]["minimum_group_size"]
    )
    if (
        clusters is not None
        and "financial_cluster_id" in output.columns
        and config["cluster_context"]["enabled"]
    ):
        for label, raw_column in dimensions.items():
            percentile, reference_count = grouped_empirical_midrank(
                output,
                raw_column,
                "financial_cluster_id",
                cluster_minimum,
            )
            stem = label.lower()
            output[f"{stem}_cluster_percentile"] = percentile
            output[f"{stem}_cluster_reference_count"] = reference_count
    else:
        for label in dimensions:
            stem = label.lower()
            output[f"{stem}_cluster_percentile"] = np.nan
            output[f"{stem}_cluster_reference_count"] = pd.Series(
                pd.NA, index=output.index, dtype="Int64"
            )

    output["calibration_version"] = (
        f"{config['calibration_id']}_V{config['version']}"
    )
    output["action_threshold_status"] = "NOT_ENABLED"

    distribution = make_distribution_summary(output, dimensions)
    queue_values = output["priority_queue_percentile"].dropna()
    queue_distribution = pd.DataFrame(
        [
            {
                "scope": "complete_queue",
                "dimension": "PriorityQueue",
                "company_count": int(len(queue_values)),
                "coverage_rate": float(
                    len(queue_values) / len(output)
                ),
                "mean": (
                    float(queue_values.mean())
                    if len(queue_values)
                    else np.nan
                ),
                "standard_deviation": (
                    float(queue_values.std(ddof=0))
                    if len(queue_values)
                    else np.nan
                ),
                "p10": (
                    float(queue_values.quantile(0.10))
                    if len(queue_values)
                    else np.nan
                ),
                "median": (
                    float(queue_values.quantile(0.50))
                    if len(queue_values)
                    else np.nan
                ),
                "p90": (
                    float(queue_values.quantile(0.90))
                    if len(queue_values)
                    else np.nan
                ),
                "minimum": (
                    float(queue_values.min())
                    if len(queue_values)
                    else np.nan
                ),
                "maximum": (
                    float(queue_values.max())
                    if len(queue_values)
                    else np.nan
                ),
            }
        ]
    )
    distribution = pd.concat(
        [distribution, queue_distribution],
        ignore_index=True,
    )
    primary_distribution = (
        output.loc[common_eligible, "primary_dimension_calibrated"]
        .value_counts(dropna=False)
        .rename_axis("primary_dimension_calibrated")
        .reset_index(name="companies")
    )
    primary_distribution["company_share"] = (
        primary_distribution["companies"] / common_eligible.sum()
    )

    comparable = (
        common_eligible
        & output["primary_dimension_raw"].notna()
        & output["primary_dimension_calibrated"].notna()
    )
    raw_normalised = (
        output["primary_dimension_raw"]
        .astype("string")
        .str.strip()
        .str.title()
    )
    calibrated_primary = (
        output["primary_dimension_calibrated"]
        .astype("string")
        .str.split(":")
        .str[0]
    )
    switched = comparable & raw_normalised.ne(calibrated_primary)
    priority_pairs = output.loc[
        common_eligible,
        ["priority_raw_max", "priority_calibrated"],
    ].dropna()
    priority_spearman = (
        float(
            priority_pairs["priority_raw_max"].corr(
                priority_pairs["priority_calibrated"],
                method="spearman",
            )
        )
        if len(priority_pairs) >= 2
        else np.nan
    )
    diagnostics = {
        "companies_total": int(len(output)),
        "three_way_calibration_eligible": int(common_eligible.sum()),
        "partial_dimension_only": int(
            output["calibration_status"]
            .eq("PARTIAL_DIMENSION_ONLY")
            .sum()
        ),
        "insufficient_evidence": int(
            output["calibration_status"]
            .eq("INSUFFICIENT_EVIDENCE")
            .sum()
        ),
        "raw_vs_calibrated_primary_comparable": int(comparable.sum()),
        "raw_vs_calibrated_primary_switches": int(switched.sum()),
        "raw_vs_calibrated_primary_switch_rate": (
            float(switched.sum() / comparable.sum())
            if comparable.sum()
            else np.nan
        ),
        "raw_vs_calibrated_priority_spearman": priority_spearman,
        "action_thresholds_enabled": False,
        "priority_queue_reference_count": int(
            output["priority_queue_percentile"].notna().sum()
        ),
        **cluster_diagnostics,
    }
    return output, distribution, primary_distribution, diagnostics


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
    destination = (
        f"{normalise_prefix(output_prefix)}/run_id={run_id}"
    )
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
        args.local_base_score_path is None
        or args.local_config_path is None
        or (
            not args.no_cluster
            and args.local_cluster_path is None
        )
        or not args.no_upload
    )
    s3 = get_s3_client() if needs_s3 else None

    base_source: str
    if args.local_base_score_path:
        base_path = args.local_base_score_path.resolve()
        base_source = str(base_path)
    else:
        base_key = args.base_score_key or find_latest_s3_key(
            s3,
            args.bucket,
            args.base_results_prefix,
            BASE_FILENAME,
        )
        base_path = download_s3_file(
            s3,
            args.bucket,
            base_key,
            input_dir / BASE_FILENAME,
        )
        base_source = f"s3://{args.bucket}/{base_key}"

    config_source: str
    if args.local_config_path:
        config_path = args.local_config_path.resolve()
        config_source = str(config_path)
    else:
        config_path = download_s3_file(
            s3,
            args.bucket,
            args.config_key,
            input_dir / "calibration_config.json",
        )
        config_source = f"s3://{args.bucket}/{args.config_key}"

    cluster_path: Path | None = None
    cluster_source: str | None = None
    if not args.no_cluster:
        if args.local_cluster_path:
            cluster_path = args.local_cluster_path.resolve()
            cluster_source = str(cluster_path)
        else:
            cluster_key = args.cluster_key or find_latest_s3_key(
                s3,
                args.bucket,
                args.cluster_results_prefix,
                CLUSTER_FILENAME,
            )
            cluster_path = download_s3_file(
                s3,
                args.bucket,
                cluster_key,
                input_dir / CLUSTER_FILENAME,
            )
            cluster_source = f"s3://{args.bucket}/{cluster_key}"

    config = load_json(config_path)
    validate_config(config)
    base_scores = read_csv_checked(base_path)
    clusters = (
        read_csv_checked(cluster_path)
        if cluster_path is not None
        else None
    )
    (
        calibrated,
        distribution,
        primary_distribution,
        diagnostics,
    ) = build_calibrated_output(base_scores, clusters, config)

    score_path = output_dir / "financial_calibrated_scores.csv"
    distribution_path = (
        output_dir / "calibrated_score_distribution.csv"
    )
    primary_path = (
        output_dir / "calibrated_primary_distribution.csv"
    )
    write_csv(calibrated, score_path)
    write_csv(distribution, distribution_path)
    write_csv(primary_distribution, primary_path)

    manifest = {
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "calibration_id": config["calibration_id"],
        "calibration_version": str(config["version"]),
        "calibration_type": "distributional_empirical_midrank",
        "base_score_source": base_source,
        "cluster_source": cluster_source,
        "config_source": config_source,
        "bucket": args.bucket,
        "output_prefix": normalise_prefix(args.output_prefix),
        "diagnostics": diagnostics,
        "score_semantics": config["semantics"],
        "cluster_adjusts_global_score": False,
        "evidence_tier_adjusts_score": False,
        "action_thresholds_enabled": False,
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "local_outputs": [
            "financial_calibrated_scores.csv",
            "calibrated_score_distribution.csv",
            "calibrated_primary_distribution.csv",
            "financial_calibration_manifest.json",
        ],
    }
    manifest_path = (
        output_dir / "financial_calibration_manifest.json"
    )
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
    logging.info("Financial score calibration completed")
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
