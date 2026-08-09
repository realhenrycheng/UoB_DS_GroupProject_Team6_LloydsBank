#!/usr/bin/env python3
"""
Build transparent Deepen / Grow / Defend financial base scores.

The script is designed for an AWS runtime with IAM access to the project S3
bucket. It downloads the five financial feature tables and the versioned rule
configuration, builds scores for every registered weight scenario, writes
auditable CSV/JSON outputs, and uploads the results to a timestamped S3 prefix.

Important modelling boundary:
    These scores are public-data proxies. They are not verified Lloyds product
    demand probabilities or formal credit decisions. Cluster, evidence tier,
    news and hiring data do not change the Phase-1 base score.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


DEFAULT_BUCKET = "team6-project-288469846191-eu-north-1-an"
DEFAULT_INPUT_PREFIX = "processed/financial_features"
DEFAULT_PHASE_PREFIX = "models/financial_scoring/phase1_basic-mark"
SOURCE_TABLES = [
    "01_financial_status_labels_100k.csv",
    "02_financial_scale_labels_100k.csv",
    "03_financial_change_labels.csv",
    "04_financial_transition_labels.csv",
    "05_financial_data_quality_labels_100k.csv",
]
CONFIG_FILES = ["model.yaml", "signals.csv", "weight_scenarios.csv"]
COMPANY_KEY = "CompanyNumber_norm"
PAIR_KEY = [COMPANY_KEY, "period_t", "period_t_plus_1"]
DIMENSIONS = ["Deepen", "Grow", "Defend"]
SCOPES = ["sector_account_category", "sector", "global"]

STATUS_COLUMNS = [
    COMPANY_KEY,
    "CompanyName",
    "primary_sector",
    "Accounts_AccountCategory",
    "latest_period_end",
    "latest_available_date",
    "cash_to_creditors_ratio",
    "debtors_to_current_assets_ratio",
    "creditors_to_disclosed_assets_ratio",
    "fixed_assets_to_disclosed_assets_ratio",
    "employees_per_million_disclosed_assets",
    "negative_equity_eligible",
    "negative_equity_flag",
    "positive_equity_flag",
    "working_capital_deficit_eligible",
    "working_capital_deficit_flag",
    "creditors_cover_eligible",
    "creditors_exceed_current_assets_flag",
    "cash_coverage_eligible",
    "receivables_intensity_eligible",
    "creditor_intensity_eligible",
    "asset_intensity_eligible",
    "employee_intensity_eligible",
]

SCALE_COLUMNS = [
    COMPANY_KEY,
    "current_assets",
    "fixed_assets",
    "creditors_total",
    "employees",
    "total_assets_less_current_liabilities",
    "current_assets_scale_eligible",
    "fixed_assets_scale_eligible",
    "creditors_scale_eligible",
    "employee_scale_eligible",
    "total_assets_scale_eligible",
]

CHANGE_METRICS = [
    "current_assets",
    "fixed_assets",
    "creditors_total",
    "equity",
    "net_assets_liabilities",
    "cash",
    "debtors",
    "employees",
    "total_assets_less_current_liabilities",
]
CHANGE_COLUMNS = [
    COMPANY_KEY,
    "period_t",
    "period_t_plus_1",
    "available_date_t",
    "available_date_t_plus_1",
    "gap_days",
    "change_available_field_count",
]
for _metric in CHANGE_METRICS:
    CHANGE_COLUMNS.extend(
        [f"{_metric}_change_eligible", f"{_metric}_signed_log_change"]
    )

TRANSITION_DOMAINS = [
    "negative_equity",
    "working_capital_deficit",
    "creditor_pressure",
]
TRANSITION_COLUMNS = [
    COMPANY_KEY,
    "period_t",
    "period_t_plus_1",
    "available_date_t",
    "available_date_t_plus_1",
    "gap_days",
]
for _domain in TRANSITION_DOMAINS:
    _transition_prefix = (
        "working_capital"
        if _domain == "working_capital_deficit"
        else _domain
    )
    TRANSITION_COLUMNS.append(f"{_transition_prefix}_transition_eligible")
    for _event in ["onset", "recovery", "persistent"]:
        TRANSITION_COLUMNS.extend(
            [f"{_domain}_{_event}_eligible", f"{_domain}_{_event}_flag"]
        )

QUALITY_COLUMNS = [
    COMPANY_KEY,
    "financial_evidence_tier",
    "useful_financial_evidence_flag",
    "core_fields_complete_flag",
    "accounts_age_days_at_snapshot",
    "accounts_older_than_24m_flag",
    "impossible_negative_value_flag",
    "extreme_amount_p999_flag",
]


@dataclass(frozen=True)
class RunPaths:
    work_dir: Path
    input_dir: Path
    config_dir: Path
    output_dir: Path
    run_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Phase-1 Deepen/Grow/Defend financial base scores."
    )
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--input-prefix", default=DEFAULT_INPUT_PREFIX)
    parser.add_argument(
        "--config-prefix", default=f"{DEFAULT_PHASE_PREFIX}/config"
    )
    parser.add_argument(
        "--output-prefix", default=f"{DEFAULT_PHASE_PREFIX}/results"
    )
    parser.add_argument(
        "--reporting-scenario",
        default="BASE",
        help="Scenario copied to canonical *_base_score columns.",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path(os.environ.get("TMPDIR", tempfile.gettempdir()))
        / "financial_base_scoring",
    )
    parser.add_argument(
        "--local-input-dir",
        type=Path,
        help="Use local five-table directory instead of downloading inputs.",
    )
    parser.add_argument(
        "--local-config-dir",
        type=Path,
        help="Use local rule configuration directory instead of S3.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Local output directory. Defaults to <work-dir>/output.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Development-only: score the first N companies.",
    )
    parser.add_argument(
        "--no-upload",
        action="store_true",
        help="Write local outputs but do not upload them to S3.",
    )
    parser.add_argument(
        "--write-signal-audit",
        action="store_true",
        help="Also write the large company-by-signal audit CSV.",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def normalise_prefix(prefix: str) -> str:
    return prefix.strip("/")


def make_run_paths(args: argparse.Namespace) -> RunPaths:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    work_dir = args.work_dir.resolve()
    input_dir = (
        args.local_input_dir.resolve()
        if args.local_input_dir
        else work_dir / "input"
    )
    config_dir = (
        args.local_config_dir.resolve()
        if args.local_config_dir
        else work_dir / "config"
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else work_dir / "output" / f"run_id={run_id}"
    )
    for path in [work_dir, input_dir, config_dir, output_dir]:
        path.mkdir(parents=True, exist_ok=True)
    return RunPaths(work_dir, input_dir, config_dir, output_dir, run_id)


def get_s3_client():
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3 download/upload. Install it with "
            "`python -m pip install boto3`, or use local directories with "
            "--no-upload."
        ) from exc
    return boto3.client("s3")


def download_files(
    s3,
    bucket: str,
    prefix: str,
    names: Iterable[str],
    destination: Path,
) -> None:
    prefix = normalise_prefix(prefix)
    for name in names:
        target = destination / name
        key = f"{prefix}/{name}"
        logging.info("Downloading s3://%s/%s", bucket, key)
        s3.download_file(bucket, key, str(target))


def upload_outputs(
    s3, bucket: str, output_prefix: str, run_id: str, output_dir: Path
) -> list[str]:
    destination = f"{normalise_prefix(output_prefix)}/run_id={run_id}"
    uploaded = []
    for path in sorted(output_dir.iterdir()):
        if not path.is_file():
            continue
        key = f"{destination}/{path.name}"
        logging.info("Uploading %s to s3://%s/%s", path.name, bucket, key)
        s3.upload_file(str(path), bucket, key)
        uploaded.append(f"s3://{bucket}/{key}")
    return uploaded


def as_bool(series: pd.Series) -> pd.Series:
    if isinstance(series.dtype, pd.BooleanDtype) or pd.api.types.is_bool_dtype(
        series
    ):
        return series.astype("boolean")
    return (
        series.astype("string")
        .str.strip()
        .str.lower()
        .map(
            {
                "true": True,
                "false": False,
                "1": True,
                "0": False,
                "yes": True,
                "no": False,
            }
        )
        .astype("boolean")
    )


def normalise_company_id(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def read_csv_checked(
    path: Path,
    usecols: list[str] | None = None,
    nrows: int | None = None,
) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    header = pd.read_csv(path, nrows=0).columns.tolist()
    if usecols is not None:
        missing = sorted(set(usecols) - set(header))
        if missing:
            raise ValueError(f"{path.name} is missing columns: {missing}")
    frame = pd.read_csv(
        path,
        usecols=usecols,
        dtype={COMPANY_KEY: "string"},
        low_memory=False,
        nrows=nrows,
    )
    frame[COMPANY_KEY] = normalise_company_id(frame[COMPANY_KEY])
    return frame


def assert_unique(frame: pd.DataFrame, keys: list[str], label: str) -> None:
    duplicate_count = int(frame.duplicated(keys).sum())
    if duplicate_count:
        raise ValueError(
            f"{label} contains {duplicate_count:,} duplicate rows for {keys}"
        )


def load_rules(config_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    signals = pd.read_csv(config_dir / "signals.csv")
    weights = pd.read_csv(config_dir / "weight_scenarios.csv")
    required_signal_cols = {
        "rule_id",
        "dimension",
        "block_id",
        "source_table",
        "source_field",
        "transformation",
        "activation_condition",
        "within_block_weight",
        "critical_flag",
        "minimum_block_coverage",
        "reason_code",
        "version",
    }
    required_weight_cols = {
        "scenario_id",
        "dimension",
        "block_id",
        "block_weight",
        "status",
        "version",
    }
    if missing := required_signal_cols - set(signals.columns):
        raise ValueError(f"signals.csv missing columns: {sorted(missing)}")
    if missing := required_weight_cols - set(weights.columns):
        raise ValueError(
            f"weight_scenarios.csv missing columns: {sorted(missing)}"
        )
    signals["within_block_weight"] = pd.to_numeric(
        signals["within_block_weight"], errors="raise"
    )
    signals["minimum_block_coverage"] = pd.to_numeric(
        signals["minimum_block_coverage"], errors="raise"
    )
    signals["critical_flag"] = as_bool(signals["critical_flag"]).fillna(False)
    weights = weights.loc[
        weights["status"].astype("string").str.lower().eq("active")
    ].copy()
    weights["block_weight"] = pd.to_numeric(
        weights["block_weight"], errors="raise"
    )
    if signals["rule_id"].duplicated().any():
        raise ValueError("signals.csv contains duplicate rule_id values")
    weight_sums = weights.groupby(["scenario_id", "dimension"])[
        "block_weight"
    ].sum()
    bad_weights = weight_sums.loc[~np.isclose(weight_sums, 1.0, atol=1e-6)]
    if not bad_weights.empty:
        raise ValueError(
            f"Scenario block weights do not sum to one: {bad_weights.to_dict()}"
        )
    signal_weight_sums = signals.groupby("block_id")[
        "within_block_weight"
    ].sum()
    bad_signal_weights = signal_weight_sums.loc[
        ~np.isclose(signal_weight_sums, 1.0, atol=1e-6)
    ]
    if not bad_signal_weights.empty:
        raise ValueError(
            "Within-block weights do not sum to one: "
            f"{bad_signal_weights.to_dict()}"
        )
    return signals, weights


def select_latest_aligned_pair(
    pair_frame: pd.DataFrame,
    master_dates: pd.DataFrame,
    label: str,
) -> pd.DataFrame:
    pair_frame = pair_frame.copy()
    for col in [
        "period_t",
        "period_t_plus_1",
        "available_date_t",
        "available_date_t_plus_1",
    ]:
        pair_frame[col] = pd.to_datetime(pair_frame[col], errors="coerce")
    dates = master_dates.copy()
    dates["latest_period_end"] = pd.to_datetime(
        dates["latest_period_end"], errors="coerce"
    )
    dates["latest_available_date"] = pd.to_datetime(
        dates["latest_available_date"], errors="coerce"
    )
    pair_frame = pair_frame.merge(
        dates, on=COMPANY_KEY, how="inner", validate="many_to_one"
    )
    aligned = pair_frame.loc[
        pair_frame["gap_days"].between(270, 550)
        & pair_frame["period_t_plus_1"].eq(
            pair_frame["latest_period_end"]
        )
        & pair_frame["available_date_t_plus_1"].le(
            pair_frame["latest_available_date"]
        )
    ].copy()
    aligned = aligned.sort_values(
        [COMPANY_KEY, "period_t_plus_1", "available_date_t_plus_1"]
    ).drop_duplicates(COMPANY_KEY, keep="last")
    assert_unique(aligned, [COMPANY_KEY], f"aligned {label}")
    logging.info(
        "Aligned %s pairs: %s companies", label, f"{len(aligned):,}"
    )
    return aligned


def load_and_align_data(
    input_dir: Path, sample_size: int | None
) -> tuple[pd.DataFrame, dict[str, int]]:
    status = read_csv_checked(
        input_dir / SOURCE_TABLES[0],
        STATUS_COLUMNS,
        nrows=sample_size,
    )
    assert_unique(status, [COMPANY_KEY], SOURCE_TABLES[0])
    selected_ids = set(status[COMPANY_KEY].dropna())

    def company_filter(frame: pd.DataFrame) -> pd.DataFrame:
        return frame.loc[frame[COMPANY_KEY].isin(selected_ids)].copy()

    scale = company_filter(
        read_csv_checked(input_dir / SOURCE_TABLES[1], SCALE_COLUMNS)
    )
    quality = company_filter(
        read_csv_checked(input_dir / SOURCE_TABLES[4], QUALITY_COLUMNS)
    )
    assert_unique(scale, [COMPANY_KEY], SOURCE_TABLES[1])
    assert_unique(quality, [COMPANY_KEY], SOURCE_TABLES[4])

    master = status.merge(
        scale,
        on=COMPANY_KEY,
        how="left",
        validate="one_to_one",
        suffixes=("", "_scale"),
    ).merge(
        quality,
        on=COMPANY_KEY,
        how="left",
        validate="one_to_one",
        suffixes=("", "_quality"),
    )

    raw_change = company_filter(
        read_csv_checked(input_dir / SOURCE_TABLES[2], CHANGE_COLUMNS)
    )
    raw_transition = company_filter(
        read_csv_checked(
            input_dir / SOURCE_TABLES[3], TRANSITION_COLUMNS
        )
    )
    assert_unique(raw_change, PAIR_KEY, SOURCE_TABLES[2])
    assert_unique(raw_transition, PAIR_KEY, SOURCE_TABLES[3])

    master_dates = master[
        [COMPANY_KEY, "latest_period_end", "latest_available_date"]
    ]
    change = select_latest_aligned_pair(
        raw_change, master_dates, "change"
    )
    transition = select_latest_aligned_pair(
        raw_transition, master_dates, "transition"
    )

    change_drop = [
        "latest_period_end",
        "latest_available_date",
    ]
    transition_drop = change_drop + [
        "available_date_t",
        "available_date_t_plus_1",
        "gap_days",
    ]
    master = master.merge(
        change.drop(columns=change_drop),
        on=COMPANY_KEY,
        how="left",
        validate="one_to_one",
    )
    master = master.merge(
        transition.drop(columns=transition_drop),
        on=PAIR_KEY,
        how="left",
        validate="one_to_one",
        suffixes=("", "_transition"),
    )
    master = master.reset_index(drop=True)
    counts = {
        "status_rows": len(status),
        "scale_rows_selected": len(scale),
        "quality_rows_selected": len(quality),
        "aligned_change_companies": len(change),
        "aligned_transition_companies": len(transition),
    }
    return master, counts


def activation_eligible_field(condition: str) -> str:
    condition = str(condition).strip()
    if " AND " in condition or not condition.endswith("=True"):
        raise ValueError(
            f"Cannot parse direct activation condition: {condition}"
        )
    return condition[: -len("=True")].strip()


def peer_percentile(
    values: pd.Series,
    eligible: pd.Series,
    sector: pd.Series,
    account_category: pd.Series,
    minimum_group_size: int = 30,
) -> tuple[pd.Series, pd.Series]:
    values = pd.to_numeric(values, errors="coerce")
    eligible = eligible.fillna(False) & values.notna()
    percentile = pd.Series(np.nan, index=values.index, dtype="float64")
    scope = pd.Series(pd.NA, index=values.index, dtype="string")

    reference = pd.DataFrame(
        {
            "value": values,
            "sector": sector.astype("string").fillna("<MISSING>"),
            "account": account_category.astype("string").fillna("<MISSING>"),
            "eligible": eligible,
        },
        index=values.index,
    )
    eligible_rows = reference.loc[eligible].copy()
    if eligible_rows.empty:
        return percentile, scope

    fine_group = eligible_rows.groupby(
        ["sector", "account"], dropna=False
    )["value"]
    fine_count = fine_group.transform("count")
    fine_rank = fine_group.rank(method="average", pct=True)
    fine_ok = fine_count >= minimum_group_size
    percentile.loc[fine_rank.index[fine_ok]] = fine_rank.loc[fine_ok]
    scope.loc[fine_rank.index[fine_ok]] = SCOPES[0]

    remaining = eligible & percentile.isna()
    if remaining.any():
        sector_rows = reference.loc[remaining | eligible].loc[eligible].copy()
        sector_group = sector_rows.groupby("sector", dropna=False)["value"]
        sector_count = sector_group.transform("count")
        sector_rank = sector_group.rank(method="average", pct=True)
        sector_ok = (
            sector_count >= minimum_group_size
        ) & sector_rank.index.to_series().map(remaining).fillna(False)
        percentile.loc[sector_rank.index[sector_ok]] = sector_rank.loc[
            sector_ok
        ]
        scope.loc[sector_rank.index[sector_ok]] = SCOPES[1]

    remaining = eligible & percentile.isna()
    if remaining.any():
        global_rank = values.loc[eligible].rank(
            method="average", pct=True
        )
        percentile.loc[remaining] = global_rank.loc[remaining]
        scope.loc[remaining] = SCOPES[2]
    return percentile, scope


def transform_percentile(
    percentile: pd.Series, transformation: str, raw_values: pd.Series
) -> pd.Series:
    high = (200.0 * (percentile - 0.5)).clip(lower=0.0, upper=100.0)
    low = (200.0 * (0.5 - percentile)).clip(lower=0.0, upper=100.0)
    if transformation == "HIGH":
        return high
    if transformation == "LOW":
        return low
    if transformation == "UP":
        return high.where(pd.to_numeric(raw_values, errors="coerce") > 0, 0.0)
    if transformation == "DOWN":
        return low.where(pd.to_numeric(raw_values, errors="coerce") < 0, 0.0)
    raise ValueError(f"Unsupported percentile transformation: {transformation}")


def weighted_signal_block(
    rules: pd.DataFrame,
    signal_scores: pd.DataFrame,
    special_current_stress: bool = False,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    ids = rules["rule_id"].tolist()
    weights = rules.set_index("rule_id")["within_block_weight"].reindex(ids)
    values = signal_scores[ids]
    available = values.notna()
    available_weight = available.mul(weights, axis=1).sum(axis=1)
    weighted_sum = values.fillna(0).mul(weights, axis=1).sum(axis=1)
    weighted_mean = weighted_sum.div(available_weight.replace(0, np.nan))
    minimum_coverage = float(rules["minimum_block_coverage"].max())

    critical_ids = rules.loc[rules["critical_flag"], "rule_id"].tolist()
    critical_available = (
        available[critical_ids].any(axis=1)
        if critical_ids
        else pd.Series(True, index=values.index)
    )
    valid = (
        available_weight.ge(minimum_coverage)
        & critical_available
        & available.any(axis=1)
    )
    if special_current_stress:
        maximum = values.max(axis=1, skipna=True)
        score = 0.5 * weighted_mean + 0.5 * maximum
    else:
        score = weighted_mean
    return score.where(valid), available_weight, valid


def build_direct_signals(
    frame: pd.DataFrame,
    rules: pd.DataFrame,
    main_cohort: pd.Series,
    clean_continuous: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_scores = pd.DataFrame(index=frame.index, dtype="float64")
    peer_scopes = pd.DataFrame(index=frame.index, dtype="string")
    direct_rules = rules.loc[rules["source_table"].ne("derived")]

    for rule in direct_rules.itertuples(index=False):
        if rule.transformation == "TRAJECTORY_MAP":
            domain = {
                "F-T01": "negative_equity",
                "F-T02": "working_capital_deficit",
                "F-T03": "creditor_pressure",
            }[rule.rule_id]
            transition_prefix = (
                "working_capital"
                if domain == "working_capital_deficit"
                else domain
            )
            eligible = (
                as_bool(
                    frame[f"{transition_prefix}_transition_eligible"]
                ).fillna(False)
                & main_cohort
            )
            onset = as_bool(frame[f"{domain}_onset_flag"]).fillna(False)
            persistent = as_bool(
                frame[f"{domain}_persistent_flag"]
            ).fillna(False)
            recovery = as_bool(frame[f"{domain}_recovery_flag"]).fillna(False)
            persistent_score = 75.0 if rule.rule_id == "F-T03" else 80.0
            score = pd.Series(0.0, index=frame.index)
            score.loc[recovery] = 20.0
            score.loc[persistent] = persistent_score
            score.loc[onset] = 100.0
            signal_scores[rule.rule_id] = score.where(eligible)
            peer_scopes[rule.rule_id] = pd.Series(
                "not_applicable", index=frame.index, dtype="string"
            ).where(eligible)
            continue

        eligible_field = activation_eligible_field(
            rule.activation_condition
        )
        eligible = as_bool(frame[eligible_field]).fillna(False) & main_cohort
        values = frame[rule.source_field]
        if rule.transformation == "BINARY":
            boolean_values = as_bool(values)
            score = boolean_values.map({True: 100.0, False: 0.0})
            signal_scores[rule.rule_id] = score.where(
                eligible & boolean_values.notna()
            )
            peer_scopes[rule.rule_id] = pd.Series(
                "not_applicable", index=frame.index, dtype="string"
            ).where(signal_scores[rule.rule_id].notna())
            continue

        eligible = eligible & clean_continuous
        percentile, scope = peer_percentile(
            values,
            eligible,
            frame["primary_sector"],
            frame["Accounts_AccountCategory"],
        )
        signal_scores[rule.rule_id] = transform_percentile(
            percentile, rule.transformation, values
        ).where(eligible)
        peer_scopes[rule.rule_id] = scope.where(eligible)
    return signal_scores, peer_scopes


def make_helper_change_signal(
    frame: pd.DataFrame,
    metric: str,
    direction: str,
    main_cohort: pd.Series,
    clean_continuous: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    eligible = (
        as_bool(frame[f"{metric}_change_eligible"]).fillna(False)
        & main_cohort
        & clean_continuous
    )
    values = frame[f"{metric}_signed_log_change"]
    percentile, scope = peer_percentile(
        values,
        eligible,
        frame["primary_sector"],
        frame["Accounts_AccountCategory"],
    )
    return (
        transform_percentile(percentile, direction, values).where(eligible),
        scope.where(eligible),
    )


def build_all_signals(
    frame: pd.DataFrame,
    rules: pd.DataFrame,
    main_cohort: pd.Series,
    clean_continuous: pd.Series,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    signal_scores, peer_scopes = build_direct_signals(
        frame, rules, main_cohort, clean_continuous
    )

    g1_rules = rules.loc[rules["block_id"].eq("G1_EXPANSION")]
    g1_score, _, _ = weighted_signal_block(g1_rules, signal_scores)
    real_expansion_rules = g1_rules.loc[g1_rules["rule_id"].ne("G-E05")]
    real_expansion, _, _ = weighted_signal_block(
        real_expansion_rules.assign(
            within_block_weight=real_expansion_rules[
                "within_block_weight"
            ]
            / real_expansion_rules["within_block_weight"].sum()
        ),
        signal_scores,
    )
    creditor_up, creditor_scope = make_helper_change_signal(
        frame,
        "creditors_total",
        "UP",
        main_cohort,
        clean_continuous,
    )

    cash_down = signal_scores["F-D03"]
    cash_negative = pd.to_numeric(
        frame["cash_signed_log_change"], errors="coerce"
    ).lt(0)
    gf01_available = (
        g1_score.notna() & cash_down.notna() & cash_negative
    )
    signal_scores["G-F01"] = np.sqrt(g1_score * cash_down).where(
        gf01_available
    )
    peer_scopes["G-F01"] = "derived"
    peer_scopes.loc[~gf01_available, "G-F01"] = pd.NA

    wc_pressure = signal_scores["F-S02"]
    liquidity_pressure = pd.concat(
        [cash_down, wc_pressure], axis=1
    ).max(axis=1, skipna=True)
    liquidity_available = cash_down.notna() | wc_pressure.notna()
    debtors_up = signal_scores["G-E05"]
    debtors_positive = pd.to_numeric(
        frame["debtors_signed_log_change"], errors="coerce"
    ).gt(0)
    gf02_available = (
        debtors_up.notna() & liquidity_available & debtors_positive
    )
    signal_scores["G-F02"] = np.sqrt(
        debtors_up * liquidity_pressure
    ).where(gf02_available)
    peer_scopes["G-F02"] = "derived"
    peer_scopes.loc[~gf02_available, "G-F02"] = pd.NA

    creditors_positive = pd.to_numeric(
        frame["creditors_total_signed_log_change"], errors="coerce"
    ).gt(0)
    gf03_available = (
        creditor_up.notna()
        & real_expansion.notna()
        & creditors_positive
        & real_expansion.gt(0)
    )
    signal_scores["G-F03"] = np.sqrt(
        creditor_up * real_expansion
    ).where(gf03_available)
    peer_scopes["G-F03"] = "derived"
    peer_scopes.loc[~gf03_available, "G-F03"] = pd.NA

    balance_sheet_weakening = pd.concat(
        [signal_scores["F-D01"], signal_scores["F-D02"]], axis=1
    ).max(axis=1, skipna=True)
    weakening_available = (
        signal_scores["F-D01"].notna()
        | signal_scores["F-D02"].notna()
    )
    fd06_available = (
        creditor_up.notna()
        & weakening_available
        & creditors_positive
        & balance_sheet_weakening.gt(0)
    )
    signal_scores["F-D06"] = np.sqrt(
        creditor_up * balance_sheet_weakening
    ).where(fd06_available)
    peer_scopes["F-D06"] = "derived"
    peer_scopes.loc[~fd06_available, "F-D06"] = pd.NA

    configured_ids = rules["rule_id"].tolist()
    missing = sorted(set(configured_ids) - set(signal_scores.columns))
    if missing:
        raise ValueError(f"Signals not implemented: {missing}")
    return signal_scores[configured_ids], peer_scopes[configured_ids]


def build_blocks(
    rules: pd.DataFrame, signal_scores: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    block_scores = pd.DataFrame(index=signal_scores.index)
    block_coverage = pd.DataFrame(index=signal_scores.index)
    for block_id, block_rules in rules.groupby("block_id", sort=False):
        score, coverage, _ = weighted_signal_block(
            block_rules,
            signal_scores,
            special_current_stress=(block_id == "F1_CURRENT_STRESS"),
        )
        block_scores[block_id] = score
        block_coverage[block_id] = coverage
    return block_scores, block_coverage


def dimension_score(
    block_scores: pd.DataFrame,
    scenario_weights: pd.DataFrame,
    dimension: str,
) -> tuple[pd.Series, pd.Series]:
    selected = scenario_weights.loc[
        scenario_weights["dimension"].eq(dimension)
    ].set_index("block_id")
    blocks = selected.index.tolist()
    weights = selected["block_weight"]
    values = block_scores[blocks]
    available = values.notna()
    available_weight = available.mul(weights, axis=1).sum(axis=1)
    weighted_sum = values.fillna(0).mul(weights, axis=1).sum(axis=1)
    score = weighted_sum.div(available_weight.replace(0, np.nan))

    mandatory = {
        "Deepen": "D1_SCALE_COMPLEXITY",
        "Grow": "G1_EXPANSION",
        "Defend": "F1_CURRENT_STRESS",
    }[dimension]
    minimum_additional = {"Deepen": 1, "Grow": 0, "Defend": 1}[dimension]
    additional_count = available.drop(columns=[mandatory]).sum(axis=1)
    valid = (
        available_weight.ge(0.65)
        & available[mandatory]
        & additional_count.ge(minimum_additional)
    )
    return score.where(valid), available_weight


def build_scenarios(
    block_scores: pd.DataFrame, weights: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = pd.DataFrame(index=block_scores.index)
    coverage = pd.DataFrame(index=block_scores.index)
    for scenario_id, scenario_weights in weights.groupby(
        "scenario_id", sort=False
    ):
        for dimension in DIMENSIONS:
            score, dimension_coverage = dimension_score(
                block_scores, scenario_weights, dimension
            )
            key = f"{dimension.lower()}__{scenario_id}"
            scores[key] = score
            coverage[f"{key}_coverage"] = dimension_coverage
    return scores, coverage


def descending_rank(series: pd.Series) -> pd.Series:
    return series.rank(method="min", ascending=False, na_option="keep")


def within_peer_rank(
    score: pd.Series, sector: pd.Series, account_category: pd.Series
) -> pd.Series:
    work = pd.DataFrame(
        {
            "score": score,
            "sector": sector.astype("string").fillna("<MISSING>"),
            "account": account_category.astype("string").fillna("<MISSING>"),
        }
    )
    return work.groupby(["sector", "account"], dropna=False)[
        "score"
    ].rank(method="min", ascending=False, na_option="keep")


def dimension_order(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    ordered_names = np.array(DIMENSIONS)
    values = frame[
        [f"{d.lower()}_base_score" for d in DIMENSIONS]
    ].to_numpy(dtype=float)
    safe = np.where(np.isnan(values), -np.inf, values)
    order = np.argsort(-safe, axis=1, kind="stable")
    primary = pd.Series(ordered_names[order[:, 0]], index=frame.index)
    secondary = pd.Series(ordered_names[order[:, 1]], index=frame.index)
    none_available = np.isneginf(safe).all(axis=1)
    primary.loc[none_available] = pd.NA
    secondary.loc[none_available] = pd.NA
    return primary.astype("string"), secondary.astype("string")


def summarise_peer_scope(peer_scopes: pd.DataFrame) -> pd.Series:
    continuous = peer_scopes.where(peer_scopes.isin(SCOPES))
    counts = pd.DataFrame(
        {
            scope: continuous.eq(scope).sum(axis=1)
            for scope in SCOPES
        }
    )
    nonzero = counts.gt(0).sum(axis=1)
    result = pd.Series("none", index=peer_scopes.index, dtype="string")
    for scope in SCOPES:
        result.loc[(nonzero == 1) & counts[scope].gt(0)] = scope
    result.loc[nonzero.gt(1)] = "mixed"
    return result


def top_reason_codes(
    signal_scores: pd.DataFrame,
    rules: pd.DataFrame,
    top_n: int = 3,
) -> pd.Series:
    code_map = rules.set_index("rule_id")["reason_code"].to_dict()
    ids = signal_scores.columns.to_numpy()
    values = signal_scores.fillna(-np.inf).to_numpy(dtype=float)
    top_positions = np.argsort(-values, axis=1, kind="stable")[:, :top_n]
    output: list[str] = []
    for row_number, positions in enumerate(top_positions):
        reasons = []
        for position in positions:
            value = values[row_number, position]
            if not np.isfinite(value) or value <= 0:
                continue
            rule_id = ids[position]
            reasons.append(f"{code_map[rule_id]}:{value:.1f}")
        output.append("|".join(reasons))
    return pd.Series(output, index=signal_scores.index, dtype="string")


def build_outputs(
    frame: pd.DataFrame,
    rules: pd.DataFrame,
    weights: pd.DataFrame,
    reporting_scenario: str,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    dict[str, int],
]:
    if reporting_scenario not in set(weights["scenario_id"]):
        raise ValueError(
            f"Unknown reporting scenario {reporting_scenario}; "
            f"choose from {sorted(weights['scenario_id'].unique())}"
        )
    useful = as_bool(
        frame["useful_financial_evidence_flag"]
    ).fillna(False)
    change_ready = (
        pd.to_numeric(
            frame["change_available_field_count"], errors="coerce"
        )
        .fillna(0)
        .ge(4)
    )
    pair_aligned = (
        frame["period_t"].notna()
        & frame["period_t_plus_1"].notna()
        & pd.to_numeric(frame["gap_days"], errors="coerce").between(
            270, 550
        )
    )
    main_cohort = useful & change_ready & pair_aligned
    impossible = as_bool(
        frame["impossible_negative_value_flag"]
    ).fillna(False)
    extreme = as_bool(frame["extreme_amount_p999_flag"]).fillna(False)
    clean_continuous = ~impossible & ~extreme

    signal_scores, peer_scopes = build_all_signals(
        frame, rules, main_cohort, clean_continuous
    )
    block_scores, block_coverage = build_blocks(rules, signal_scores)
    scenario_scores, scenario_coverage = build_scenarios(
        block_scores, weights
    )

    output = frame[
        [
            COMPANY_KEY,
            "CompanyName",
            "primary_sector",
            "Accounts_AccountCategory",
            "latest_period_end",
            "latest_available_date",
            "financial_evidence_tier",
            "period_t",
            "period_t_plus_1",
            "available_date_t",
            "available_date_t_plus_1",
            "gap_days",
            "change_available_field_count",
            "useful_financial_evidence_flag",
            "core_fields_complete_flag",
            "accounts_age_days_at_snapshot",
            "accounts_older_than_24m_flag",
            "impossible_negative_value_flag",
            "extreme_amount_p999_flag",
        ]
    ].copy()
    output["main_cohort_flag"] = main_cohort
    output = pd.concat([output, scenario_scores, scenario_coverage], axis=1)

    for dimension in DIMENSIONS:
        lower = dimension.lower()
        output[f"{lower}_base_score"] = output[
            f"{lower}__{reporting_scenario}"
        ]
        output[f"{lower}_coverage"] = output[
            f"{lower}__{reporting_scenario}_coverage"
        ]
    output["priority_base_score"] = output[
        [f"{d.lower()}_base_score" for d in DIMENSIONS]
    ].max(axis=1, skipna=True)
    all_dimension_missing = output[
        [f"{d.lower()}_base_score" for d in DIMENSIONS]
    ].isna().all(axis=1)
    output.loc[all_dimension_missing, "priority_base_score"] = np.nan
    output["primary_dimension"], output["secondary_dimension"] = (
        dimension_order(output)
    )
    output["top_reason_codes"] = top_reason_codes(signal_scores, rules)
    output["peer_scope_used"] = summarise_peer_scope(peer_scopes)
    output["score_status"] = np.select(
        [
            output[
                [f"{d.lower()}_base_score" for d in DIMENSIONS]
            ].notna().all(axis=1),
            output[
                [f"{d.lower()}_base_score" for d in DIMENSIONS]
            ].notna().any(axis=1),
        ],
        ["COMPLETE", "PARTIAL"],
        default="INSUFFICIENT_EVIDENCE",
    )
    output["rule_version"] = str(rules["version"].iloc[0])
    output["reporting_scenario"] = reporting_scenario

    for dimension in DIMENSIONS:
        lower = dimension.lower()
        output[f"{lower}_global_rank"] = descending_rank(
            output[f"{lower}_base_score"]
        ).astype("Int64")
        output[f"{lower}_peer_rank"] = within_peer_rank(
            output[f"{lower}_base_score"],
            output["primary_sector"],
            output["Accounts_AccountCategory"],
        ).astype("Int64")
    output["priority_global_rank"] = descending_rank(
        output["priority_base_score"]
    ).astype("Int64")

    block_audit = pd.concat(
        [
            frame[[COMPANY_KEY]],
            block_scores.add_suffix("__score"),
            block_coverage.add_suffix("__coverage"),
        ],
        axis=1,
    )
    signal_audit = pd.concat(
        [
            frame[[COMPANY_KEY]],
            signal_scores.add_suffix("__score"),
            peer_scopes.add_suffix("__peer_scope"),
        ],
        axis=1,
    )
    summary_rows = []
    for column in scenario_scores.columns:
        dimension, scenario = column.split("__", 1)
        values = scenario_scores[column].dropna()
        summary_rows.append(
            {
                "scenario_id": scenario,
                "dimension": dimension.capitalize(),
                "eligible_count": int(values.size),
                "coverage_rate": float(values.size / len(output)),
                "mean": float(values.mean()) if len(values) else np.nan,
                "standard_deviation": (
                    float(values.std()) if len(values) else np.nan
                ),
                "p10": (
                    float(values.quantile(0.10)) if len(values) else np.nan
                ),
                "median": (
                    float(values.quantile(0.50)) if len(values) else np.nan
                ),
                "p90": (
                    float(values.quantile(0.90)) if len(values) else np.nan
                ),
                "minimum": float(values.min()) if len(values) else np.nan,
                "maximum": float(values.max()) if len(values) else np.nan,
            }
        )
    distribution = pd.DataFrame(summary_rows)
    cohort_counts = {
        "companies_total": int(len(frame)),
        "useful_financial_evidence": int(useful.sum()),
        "change_ready": int(change_ready.sum()),
        "aligned_pair": int(pair_aligned.sum()),
        "main_cohort": int(main_cohort.sum()),
        "continuous_quality_clean": int(clean_continuous.sum()),
        "score_complete": int(output["score_status"].eq("COMPLETE").sum()),
        "score_partial": int(output["score_status"].eq("PARTIAL").sum()),
        "score_insufficient": int(
            output["score_status"].eq("INSUFFICIENT_EVIDENCE").sum()
        ),
    }
    return output, block_audit, signal_audit, distribution, cohort_counts


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8")
    logging.info("Wrote %s (%s rows)", path.name, f"{len(frame):,}")


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    paths = make_run_paths(args)
    s3 = None
    if not args.local_input_dir or not args.local_config_dir:
        s3 = get_s3_client()
    if not args.local_input_dir:
        download_files(
            s3,
            args.bucket,
            args.input_prefix,
            SOURCE_TABLES,
            paths.input_dir,
        )
    if not args.local_config_dir:
        download_files(
            s3,
            args.bucket,
            args.config_prefix,
            CONFIG_FILES,
            paths.config_dir,
        )

    signals, weights = load_rules(paths.config_dir)
    data, input_counts = load_and_align_data(
        paths.input_dir, args.sample_size
    )
    (
        scores,
        block_audit,
        signal_audit,
        distribution,
        cohort_counts,
    ) = build_outputs(
        data, signals, weights, args.reporting_scenario
    )

    score_path = paths.output_dir / "financial_base_scores.csv"
    block_path = paths.output_dir / "financial_block_scores.csv"
    distribution_path = (
        paths.output_dir / "scenario_score_distribution.csv"
    )
    write_csv(scores, score_path)
    write_csv(block_audit, block_path)
    write_csv(distribution, distribution_path)
    if args.write_signal_audit:
        write_csv(
            signal_audit,
            paths.output_dir / "financial_signal_scores.csv",
        )

    manifest = {
        "run_id": paths.run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model_id": "FIN_BASE",
        "rule_version": str(signals["version"].iloc[0]),
        "reporting_scenario": args.reporting_scenario,
        "sample_size": args.sample_size,
        "bucket": args.bucket,
        "input_prefix": normalise_prefix(args.input_prefix),
        "config_prefix": normalise_prefix(args.config_prefix),
        "output_prefix": normalise_prefix(args.output_prefix),
        "input_counts": input_counts,
        "cohort_counts": cohort_counts,
        "scenario_ids": weights["scenario_id"].drop_duplicates().tolist(),
        "score_semantics": {
            "priority_base_score": (
                "maximum of available Deepen/Grow/Defend scores; "
                "used for queue ordering without averaging unlike actions"
            ),
            "primary_dimension": "dimension with highest base score",
            "peer_normalisation": (
                "sector + account category when n>=30; sector then global"
            ),
            "cluster_adjustment": False,
            "evidence_tier_adjustment": False,
            "news_adjustment": False,
            "hiring_adjustment": False,
        },
        "derived_signal_definitions": {
            "G-F01": "sqrt(G1_EXPANSION * cash_down_signal)",
            "G-F02": (
                "sqrt(debtors_up_signal * max(cash_down, "
                "working_capital_deficit))"
            ),
            "G-F03": (
                "sqrt(creditors_up_signal * real_expansion), where "
                "real_expansion excludes debtors"
            ),
            "F-D06": (
                "sqrt(creditors_up_signal * max(equity_down, "
                "net_assets_down))"
            ),
        },
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
        "local_outputs": [
            "financial_base_scores.csv",
            "financial_block_scores.csv",
            "scenario_score_distribution.csv",
            *(
                ["financial_signal_scores.csv"]
                if args.write_signal_audit
                else []
            ),
            "financial_scoring_manifest.json",
        ],
    }
    manifest_path = paths.output_dir / "financial_scoring_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    uploaded: list[str] = []
    if not args.no_upload:
        if s3 is None:
            s3 = get_s3_client()
        uploaded = upload_outputs(
            s3,
            args.bucket,
            args.output_prefix,
            paths.run_id,
            paths.output_dir,
        )
    logging.info("Financial base scoring completed")
    logging.info("Local output directory: %s", paths.output_dir)
    if uploaded:
        logging.info(
            "S3 output directory: s3://%s/%s/run_id=%s/",
            args.bucket,
            normalise_prefix(args.output_prefix),
            paths.run_id,
        )


if __name__ == "__main__":
    main()
