"""Generate company-level Forward Deepen / Relative Grow / Defend V3 scores.

The script implements the frozen rules in
Forward_Deepen_Grow_Defend_Score_Rules_V3_.md.
It has no external model dependencies: isotonic regression is fitted with a
weighted pool-adjacent-violators implementation on OOF predictions only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


VERSION = "V3.0"
CALIBRATION_VERSION = "V3.0_oof_all_pairs"
PREDICTION_BATCH = "2026-08-23"
METRICS = [
    "cash",
    "creditors_total",
    "current_assets",
    "debtors",
    "equity",
    "fixed_assets",
    "net_assets_liabilities",
    "net_current_assets_liabilities",
    "total_assets_less_current_liabilities",
]


def sorted_reference(values: pd.Series) -> np.ndarray:
    reference = np.sort(values.dropna().to_numpy(dtype=float))
    if not len(reference):
        raise ValueError("Cannot create a reference distribution from an empty series.")
    return reference


def empirical_cdf(values: Sequence[float], reference: np.ndarray) -> np.ndarray:
    values_array = np.asarray(values, dtype=float)
    result = np.full(values_array.shape, np.nan, dtype=float)
    valid = np.isfinite(values_array)
    result[valid] = np.searchsorted(reference, values_array[valid], side="right") / len(reference)
    return result


def upper_tail(percentile: np.ndarray) -> np.ndarray:
    result = np.zeros(percentile.shape, dtype=float)
    valid = np.isfinite(percentile)
    band_1 = valid & (percentile > 0.75) & (percentile < 0.85)
    band_2 = valid & (percentile >= 0.85) & (percentile < 0.90)
    band_3 = valid & (percentile >= 0.90)
    result[band_1] = 5.0 * (percentile[band_1] - 0.75)
    result[band_2] = 0.5
    result[band_3] = 0.5 + 5.0 * (percentile[band_3] - 0.90)
    result[~valid] = np.nan
    return result


def weighted_block(
    signals: Mapping[str, np.ndarray],
    names: Sequence[str],
    weights: Sequence[float],
    min_weight: float,
    require_any: Sequence[str] | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    matrix = np.column_stack([signals[name] for name in names])
    weights_array = np.asarray(weights, dtype=float)
    available = np.isfinite(matrix)
    available_weight = (available * weights_array).sum(axis=1)
    numerator = np.nansum(matrix * weights_array, axis=1)
    score = np.divide(
        numerator,
        available_weight,
        out=np.full(len(matrix), np.nan, dtype=float),
        where=available_weight > 0,
    )
    eligible = available_weight >= min_weight - 1e-12
    if require_any:
        eligible &= np.isfinite(np.column_stack([signals[name] for name in require_any])).any(axis=1)
    score[~eligible] = np.nan
    return score, available_weight, available.sum(axis=1)


def mean_if_available(values: Sequence[np.ndarray], min_count: int) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.column_stack(values)
    count = np.isfinite(matrix).sum(axis=1)
    score = np.divide(
        np.nansum(matrix, axis=1),
        count,
        out=np.full(len(matrix), np.nan, dtype=float),
        where=count > 0,
    )
    score[count < min_count] = np.nan
    return score, count


def combine_available(values: Sequence[np.ndarray], weights: Sequence[float]) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.column_stack(values)
    weights_array = np.asarray(weights, dtype=float)
    available_weight = (np.isfinite(matrix) * weights_array).sum(axis=1)
    score = np.divide(
        np.nansum(matrix * weights_array, axis=1),
        available_weight,
        out=np.full(len(matrix), np.nan, dtype=float),
        where=available_weight > 0,
    )
    return score, available_weight


def interaction(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    result = np.sqrt(left * right)
    result[~np.isfinite(left) | ~np.isfinite(right)] = np.nan
    return result


def fit_isotonic(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Fit a non-decreasing weighted-PAV curve and return interpolation knots."""
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 2:
        raise ValueError("At least two OOF observations are required to fit Relative Grow isotonic calibration.")

    order = np.argsort(x, kind="mergesort")
    x_sorted = x[order]
    y_sorted = y[order]
    unique_x, inverse = np.unique(x_sorted, return_inverse=True)
    group_count = np.bincount(inverse).astype(float)
    group_sum = np.bincount(inverse, weights=y_sorted)
    group_mean = group_sum / group_count

    blocks: list[list[float | int]] = []
    for index, (mean, weight) in enumerate(zip(group_mean, group_count)):
        blocks.append([index, index, float(mean), float(weight)])
        while len(blocks) >= 2 and blocks[-2][2] > blocks[-1][2]:
            left = blocks[-2]
            right = blocks[-1]
            total_weight = float(left[3] + right[3])
            merged_mean = (float(left[2]) * float(left[3]) + float(right[2]) * float(right[3])) / total_weight
            blocks[-2:] = [[left[0], right[1], merged_mean, total_weight]]

    fitted = np.empty(len(unique_x), dtype=float)
    for start, end, mean, _ in blocks:
        fitted[int(start) : int(end) + 1] = float(mean)
    return unique_x.astype(float), fitted


def predict_isotonic(x: np.ndarray, x_knots: np.ndarray, y_knots: np.ndarray) -> np.ndarray:
    result = np.full(x.shape, np.nan, dtype=float)
    valid = np.isfinite(x)
    result[valid] = np.interp(x[valid], x_knots, y_knots, left=y_knots[0], right=y_knots[-1])
    return result


def append_reason(reasons: np.ndarray, mask: np.ndarray, code: str) -> None:
    for index in np.flatnonzero(mask):
        reasons[index] = code if not reasons[index] else f"{reasons[index]};{code}"


def calculate_components(data: pd.DataFrame, prediction_refs: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Calculate frozen V2 component blocks from prediction values."""
    signals: dict[str, np.ndarray] = {}
    percentiles: dict[str, np.ndarray] = {}
    for metric in METRICS:
        percentile = empirical_cdf(data[f"{metric}__pred_L_quantile"], prediction_refs[metric])
        percentiles[metric] = percentile
        signals[f"{metric}_up"] = upper_tail(percentile)
        signals[f"{metric}_down"] = upper_tail(1.0 - percentile)

    d1, d1_weight, d1_count = weighted_block(
        signals,
        ["current_assets_up", "total_assets_less_current_liabilities_up", "debtors_up"],
        [0.40, 0.40, 0.20],
        0.60,
        ["current_assets_up", "total_assets_less_current_liabilities_up"],
    )
    d2, d2_weight, d2_count = weighted_block(
        signals,
        ["creditors_total_up", "debtors_up"],
        [0.60, 0.40],
        0.60,
    )
    deepen, _ = combine_available([d1, d2], [0.70, 0.30])
    deepen[~np.isfinite(d1)] = np.nan

    cash_down = signals["cash_down"]
    nca_down = signals["net_current_assets_liabilities_down"]
    cash_or_nca_down = np.maximum(
        np.where(np.isfinite(cash_down), cash_down, -np.inf),
        np.where(np.isfinite(nca_down), nca_down, -np.inf),
    )
    cash_or_nca_down[~np.isfinite(cash_down) & ~np.isfinite(nca_down)] = np.nan
    gf1 = interaction(d1, signals["cash_down"])
    gf2 = interaction(signals["debtors_up"], cash_or_nca_down)
    gf3 = interaction(signals["creditors_total_up"], d1)
    g2, g2_count = mean_if_available([gf1, gf2, gf3], 1)
    g3, g3_count = mean_if_available(
        [signals["equity_up"], signals["net_assets_liabilities_up"], signals["net_current_assets_liabilities_up"]],
        2,
    )
    grow_raw, _ = combine_available([d1, g2, g3], [0.55, 0.20, 0.25])
    grow_raw[~np.isfinite(d1) | ~(np.isfinite(g2) | np.isfinite(g3))] = np.nan

    cl = interaction(signals["creditors_total_up"], cash_or_nca_down)
    f1, f1_weight, f1_count = weighted_block(
        {
            "cash": signals["cash_down"],
            "nca": signals["net_current_assets_liabilities_down"],
            "current_assets": signals["current_assets_down"],
            "cl": cl,
        },
        ["cash", "nca", "current_assets", "cl"],
        [0.30, 0.35, 0.20, 0.15],
        0.55,
    )
    f2, f2_weight, f2_count = weighted_block(
        signals,
        ["equity_down", "net_assets_liabilities_down", "total_assets_less_current_liabilities_down", "fixed_assets_down"],
        [0.30, 0.30, 0.25, 0.15],
        0.60,
    )
    defend, _ = combine_available([f1, f2], [0.55, 0.45])

    result = {
        "deepen": deepen * 100.0,
        "grow_raw": grow_raw * 100.0,
        "defend": defend * 100.0,
        "d1": d1,
        "d2": d2,
        "g2": g2,
        "g3": g3,
        "g2_count": g2_count,
        "f1": f1,
        "f2": f2,
        "d1_weight": d1_weight,
        "d2_weight": d2_weight,
        "f1_weight": f1_weight,
        "f2_weight": f2_weight,
        "d1_count": d1_count,
        "d2_count": d2_count,
        "f1_count": f1_count,
        "f2_count": f2_count,
    }
    result.update(percentiles)
    result.update(signals)
    return result


def make_statuses(components: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    n = len(components["deepen"])
    deepen_complete = np.isfinite(components["d1"]) & np.isfinite(components["d2"])
    deepen_partial = np.isfinite(components["d1"]) & ~np.isfinite(components["d2"])
    grow_complete = np.isfinite(components["d1"]) & np.isfinite(components["g2"]) & np.isfinite(components["g3"])
    grow_partial = np.isfinite(components["grow_raw"]) & ~grow_complete
    defend_complete = np.isfinite(components["f1"]) & np.isfinite(components["f2"])
    defend_partial = (np.isfinite(components["f1"]) | np.isfinite(components["f2"])) & ~defend_complete

    deepen_status = np.full(n, "Insufficient", dtype=object)
    deepen_status[deepen_partial] = "Partial"
    deepen_status[deepen_complete] = "Complete"
    grow_status = np.full(n, "Insufficient", dtype=object)
    grow_status[grow_partial] = "Partial"
    grow_status[grow_complete] = "Complete"
    defend_status = np.full(n, "Insufficient", dtype=object)
    defend_status[defend_partial] = "Partial"
    defend_status[defend_complete] = "Complete"

    deepen_confidence = np.full(n, "Insufficient", dtype=object)
    deepen_confidence[deepen_partial] = "Medium"
    deepen_confidence[deepen_complete] = "High"
    grow_confidence = np.full(n, "Insufficient", dtype=object)
    grow_confidence[grow_partial] = "Low"
    grow_medium = grow_complete & (components["g2_count"] < 2)
    grow_high = grow_complete & (components["g2_count"] >= 2)
    grow_confidence[grow_medium] = "Medium"
    grow_confidence[grow_high] = "High"
    defend_confidence = np.full(n, "Insufficient", dtype=object)
    defend_confidence[defend_partial] = "Low"
    defend_confidence[defend_complete] = "High"

    return {
        "deepen_status": deepen_status,
        "grow_status": grow_status,
        "defend_status": defend_status,
        "deepen_confidence": deepen_confidence,
        "grow_confidence": grow_confidence,
        "defend_confidence": defend_confidence,
    }


def score_reasons(components: Mapping[str, np.ndarray], relative_grow_tail_signal: np.ndarray) -> dict[str, np.ndarray]:
    n = len(relative_grow_tail_signal)
    deepen = np.full(n, "", dtype=object)
    append_reason(deepen, components["current_assets_up"] > 0, "CURRENT_ASSETS_UP")
    append_reason(deepen, components["total_assets_less_current_liabilities_up"] > 0, "TALCL_UP")
    append_reason(deepen, components["debtors_up"] > 0, "DEBTORS_UP")
    append_reason(deepen, components["creditors_total_up"] > 0, "CREDITORS_UP")

    grow = np.full(n, "", dtype=object)
    append_reason(grow, relative_grow_tail_signal > 0, "ABOVE_EXPECTED_VS_DEEPEN")
    append_reason(grow, components["cash_down"] > 0, "CASH_DOWN")
    append_reason(grow, components["net_current_assets_liabilities_down"] > 0, "NCA_DOWN")
    append_reason(grow, components["creditors_total_up"] > 0, "CREDITORS_UP")
    append_reason(grow, components["equity_up"] > 0, "EQUITY_UP")
    append_reason(grow, components["net_assets_liabilities_up"] > 0, "NET_ASSETS_UP")

    defend = np.full(n, "", dtype=object)
    append_reason(defend, components["cash_down"] > 0, "CASH_DOWN")
    append_reason(defend, components["net_current_assets_liabilities_down"] > 0, "NCA_DOWN")
    append_reason(defend, components["current_assets_down"] > 0, "CURRENT_ASSETS_DOWN")
    append_reason(defend, components["creditors_total_up"] > 0, "CREDITORS_UP")
    append_reason(defend, components["equity_down"] > 0, "EQUITY_DOWN")
    append_reason(defend, components["net_assets_liabilities_down"] > 0, "NET_ASSETS_DOWN")
    append_reason(defend, components["total_assets_less_current_liabilities_down"] > 0, "TALCL_DOWN")
    append_reason(defend, components["fixed_assets_down"] > 0, "FIXED_ASSETS_DOWN")

    for reasons in (deepen, grow, defend):
        reasons[reasons == ""] = "NO_TAIL_SIGNAL"
    return {"deepen": deepen, "grow": grow, "defend": defend}


def add_scale_tier(data: pd.DataFrame, oof: pd.DataFrame, output: pd.DataFrame) -> None:
    scale_metrics = [
        "total_assets_less_current_liabilities",
        "current_assets",
        "employees",
    ]
    percentiles = []
    for metric in scale_metrics:
        column = f"{metric}__x_t"
        reference = sorted_reference(np.log1p(np.maximum(oof[column].astype(float), 0.0)))
        transformed = np.log1p(np.maximum(data[column].astype(float), 0.0))
        percentiles.append(empirical_cdf(transformed, reference))
    matrix = np.column_stack(percentiles)
    count = np.isfinite(matrix).sum(axis=1)
    scale_percentile = np.full(len(data), np.nan, dtype=float)
    valid_scale = count >= 2
    scale_percentile[valid_scale] = np.nanmedian(matrix[valid_scale], axis=1)
    output["scale_percentile"] = scale_percentile
    output["scale_evidence_count"] = count
    output["scale_status"] = np.where(np.isfinite(scale_percentile), "Available", "Insufficient")
    output["scale_tier"] = pd.cut(
        scale_percentile,
        bins=[-np.inf, 0.20, 0.40, 0.60, 0.80, np.inf],
        labels=["Very Small", "Small", "Medium", "Large", "Very Large"],
        right=False,
    ).astype(object)
    output.loc[~np.isfinite(scale_percentile), "scale_tier"] = "Insufficient"


def add_score_rank_fields(
    output: pd.DataFrame,
    source: pd.DataFrame,
    specs: Iterable[tuple[str, str, str]],
) -> None:
    """Add status-specific fixed OOF percentiles and same-status batch rank percentiles."""
    for score_column, status_column, prefix in specs:
        output[f"{prefix}_reference_percentile"] = np.nan
        output[f"{prefix}_batch_rank_percentile"] = np.nan
        for status in ("Complete", "Partial"):
            source_values = source.loc[source[status_column].eq(status), score_column].dropna()
            if source_values.empty:
                continue
            reference = sorted_reference(source_values)
            target_mask = output[status_column].eq(status) & output[score_column].notna()
            output.loc[target_mask, f"{prefix}_reference_percentile"] = empirical_cdf(
                output.loc[target_mask, score_column], reference
            )
            output.loc[target_mask, f"{prefix}_batch_rank_percentile"] = output.loc[target_mask, score_column].rank(
                method="average", pct=True
            )


def make_output(input_data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    required_columns = {
        "CompanyNumber_norm",
        "period_t",
        "period_t_plus_1",
        "pred_source",
        "is_latest_pair",
        "primary_sector",
        "acct_cat_raw",
        "acct_cat_model",
    }
    for metric in METRICS:
        required_columns.add(f"{metric}__pred_L_quantile")
    for metric in ("total_assets_less_current_liabilities", "current_assets", "employees"):
        required_columns.add(f"{metric}__x_t")
    missing = sorted(required_columns - set(input_data.columns))
    if missing:
        raise ValueError(f"Input file is missing required columns: {missing}")

    all_rows = input_data.copy()
    oof = all_rows.loc[all_rows["pred_source"].eq("oof")].copy()
    if oof.empty:
        raise ValueError("No OOF rows found; V3 cannot create fixed reference distributions.")
    latest = all_rows.loc[all_rows["is_latest_pair"].astype(bool)].copy()
    if latest["CompanyNumber_norm"].duplicated().any():
        raise ValueError("Latest-pair filter did not produce one row per company.")

    prediction_refs = {metric: sorted_reference(oof[f"{metric}__pred_L_quantile"]) for metric in METRICS}
    oof_components = calculate_components(oof, prediction_refs)
    latest_components = calculate_components(latest, prediction_refs)
    oof_status = make_statuses(oof_components)
    latest_status = make_statuses(latest_components)

    x_knots, y_knots = fit_isotonic(oof_components["deepen"], oof_components["grow_raw"])
    oof_expected_grow = predict_isotonic(oof_components["deepen"], x_knots, y_knots)
    latest_expected_grow = predict_isotonic(latest_components["deepen"], x_knots, y_knots)
    oof_residual = oof_components["grow_raw"] - oof_expected_grow
    latest_residual = latest_components["grow_raw"] - latest_expected_grow
    residual_reference = sorted_reference(pd.Series(oof_residual))
    oof_relative_percentile = empirical_cdf(oof_residual, residual_reference)
    latest_relative_percentile = empirical_cdf(latest_residual, residual_reference)
    oof_relative_grow = oof_relative_percentile * 100.0
    latest_relative_grow = latest_relative_percentile * 100.0
    latest_relative_tail_signal = upper_tail(latest_relative_percentile) * 100.0
    oof_relative_grow[~np.isfinite(oof_components["grow_raw"])] = np.nan
    latest_relative_grow[~np.isfinite(latest_components["grow_raw"])] = np.nan

    base_columns = [
        "CompanyNumber_norm",
        "period_t",
        "period_t_plus_1",
        "primary_sector",
        "acct_cat_raw",
        "acct_cat_model",
        "pred_source",
    ]
    output = latest[base_columns].copy()
    output["forward_deepen_score"] = latest_components["deepen"]
    output["forward_relative_grow_score"] = latest_relative_grow
    output["forward_relative_grow_tail_signal"] = latest_relative_tail_signal
    output["forward_defend_score"] = latest_components["defend"]
    output["forward_grow_raw_score"] = latest_components["grow_raw"]
    output["forward_grow_residual"] = latest_residual
    output["forward_relative_grow_residual_percentile"] = latest_relative_percentile

    output["forward_deepen_status"] = latest_status["deepen_status"]
    output["forward_relative_grow_status"] = latest_status["grow_status"]
    output["forward_defend_status"] = latest_status["defend_status"]
    output["forward_deepen_confidence"] = latest_status["deepen_confidence"]
    output["forward_relative_grow_confidence"] = latest_status["grow_confidence"]
    output["forward_defend_confidence"] = latest_status["defend_confidence"]

    output["forward_deepen_available_blocks"] = np.isfinite(latest_components["d1"]).astype(int) + np.isfinite(
        latest_components["d2"]
    ).astype(int)
    output["forward_relative_grow_available_blocks"] = (
        np.isfinite(latest_components["d1"]).astype(int)
        + np.isfinite(latest_components["g2"]).astype(int)
        + np.isfinite(latest_components["g3"]).astype(int)
    )
    output["forward_defend_available_blocks"] = np.isfinite(latest_components["f1"]).astype(int) + np.isfinite(
        latest_components["f2"]
    ).astype(int)
    output["forward_deepen_evidence_count"] = latest_components["d1_count"] + latest_components["d2_count"]
    output["forward_relative_grow_evidence_count"] = latest_components["d1_count"] + latest_components["g2_count"] + np.isfinite(
        latest_components["g3"]
    ).astype(int)
    output["forward_defend_evidence_count"] = latest_components["f1_count"] + latest_components["f2_count"]

    reasons = score_reasons(latest_components, latest_relative_tail_signal)
    output["forward_deepen_reason_codes"] = reasons["deepen"]
    output["forward_relative_grow_reason_codes"] = reasons["grow"]
    output["forward_defend_reason_codes"] = reasons["defend"]
    for score_column, reason_column in [
        ("forward_deepen_score", "forward_deepen_reason_codes"),
        ("forward_relative_grow_score", "forward_relative_grow_reason_codes"),
        ("forward_defend_score", "forward_defend_reason_codes"),
    ]:
        output.loc[output[score_column].isna(), reason_column] = "INSUFFICIENT_EVIDENCE"

    oof_output = pd.DataFrame(
        {
            "forward_deepen_score": oof_components["deepen"],
            "forward_relative_grow_score": oof_relative_grow,
            "forward_defend_score": oof_components["defend"],
            "forward_deepen_status": oof_status["deepen_status"],
            "forward_relative_grow_status": oof_status["grow_status"],
            "forward_defend_status": oof_status["defend_status"],
        }
    )
    add_score_rank_fields(
        output,
        oof_output,
        [
            ("forward_deepen_score", "forward_deepen_status", "forward_deepen"),
            ("forward_relative_grow_score", "forward_relative_grow_status", "forward_relative_grow"),
            ("forward_defend_score", "forward_defend_status", "forward_defend"),
        ],
    )
    add_scale_tier(latest, oof, output)

    output["model_version"] = "source_predictions_wide_unspecified"
    output["score_version"] = VERSION
    output["calibration_version"] = CALIBRATION_VERSION
    output["prediction_batch"] = PREDICTION_BATCH
    output = output.sort_values("CompanyNumber_norm", kind="stable").reset_index(drop=True)

    relative_scores = output["forward_relative_grow_score"].dropna()
    relative_score_counts = relative_scores.value_counts()
    summary: dict[str, object] = {
        "input_rows": int(len(all_rows)),
        "latest_company_rows": int(len(output)),
        "unique_companies": int(output["CompanyNumber_norm"].nunique()),
        "score_version": VERSION,
        "calibration_version": CALIBRATION_VERSION,
        "score_coverage": {
            score: {
                "numeric_count": int(output[column].notna().sum()),
                "numeric_rate": round(float(output[column].notna().mean()), 6),
                "status_counts": output[status].value_counts(dropna=False).to_dict(),
            }
            for score, column, status in [
                ("deepen", "forward_deepen_score", "forward_deepen_status"),
                ("relative_grow", "forward_relative_grow_score", "forward_relative_grow_status"),
                ("defend", "forward_defend_score", "forward_defend_status"),
            ]
        },
        "all_three_complete": int(
            (
                output["forward_deepen_status"].eq("Complete")
                & output["forward_relative_grow_status"].eq("Complete")
                & output["forward_defend_status"].eq("Complete")
            ).sum()
        ),
        "spearman_complete_scores": output.loc[
            output[["forward_deepen_score", "forward_relative_grow_score", "forward_defend_score"]].notna().all(axis=1),
            ["forward_deepen_score", "forward_relative_grow_score", "forward_defend_score"],
        ]
        .rank()
        .corr()
        .round(6)
        .to_dict(),
        "relative_grow_score_diagnostics": {
            "numeric_count": int(len(relative_scores)),
            "zero_main_score_count": int((relative_scores == 0).sum()),
            "distinct_score_count": int(relative_scores.nunique()),
            "largest_tie_count": int(relative_score_counts.iloc[0]) if len(relative_score_counts) else 0,
            "largest_tie_share": round(float(relative_score_counts.iloc[0] / len(relative_scores)), 6)
            if len(relative_score_counts)
            else 0.0,
            "tail_signal_positive_count": int((output["forward_relative_grow_tail_signal"] > 0).sum()),
        },
        "isotonic_knots": int(len(x_knots)),
    }
    return output, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate V3 company-level Forward scores.")
    parser.add_argument("--input", type=Path, required=True, help="Path to predictions_wide.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for V3 CSV and summary JSON")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(
        args.input,
        dtype={"CompanyNumber_norm": "string"},
        parse_dates=["period_t", "period_t_plus_1"],
        low_memory=False,
    )
    output, summary = make_output(data)
    output_path = args.output_dir / "forward_scores_v3.csv"
    summary_path = args.output_dir / "forward_scores_v3_summary.json"
    output.to_csv(output_path, index=False, encoding="utf-8-sig", float_format="%.8f")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(output):,} company rows to {output_path}")
    print(f"Wrote audit summary to {summary_path}")


if __name__ == "__main__":
    main()
