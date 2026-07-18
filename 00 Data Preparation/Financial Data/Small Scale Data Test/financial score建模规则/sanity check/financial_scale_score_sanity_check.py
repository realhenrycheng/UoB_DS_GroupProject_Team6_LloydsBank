from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(r"E:\000硕士毕设\财务数据\小样本测试")
FEATURES_CSV = BASE_DIR / "financial_features_sample_year.csv"
TURNOVER_CSV = BASE_DIR / "turnover_company_year_selected.csv"
OUT_DIR = Path("outputs") / "financial_scale_sanity_check"

BB_MAX = 3_000_000
SME_MAX = 25_000_000

PROXY_FIELDS = [
    "financial_scale_score",
    "financial_scale_score_raw",
    "current_assets",
    "equity",
    "employees",
    "creditors_total",
    "fixed_assets",
    "cash",
    "debtors",
    "borrowings",
    "net_assets_liabilities",
    "profit_loss",
]

LOG_FIELDS = [
    "log_current_assets",
    "log_equity",
    "log_employees",
    "log_creditors_total",
    "log_fixed_assets",
    "log_cash",
    "log_debtors",
    "log_borrowings",
    "log_net_assets_liabilities",
]

SEGMENT_ORDER = {"BB": 0, "SME": 1, "MidCorporate": 2}


def assign_segment(turnover: float) -> str | float:
    if pd.isna(turnover):
        return np.nan
    if turnover < BB_MAX:
        return "BB"
    if turnover < SME_MAX:
        return "SME"
    return "MidCorporate"


def winsorise(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    clean = pd.to_numeric(s, errors="coerce")
    lo, hi = clean.quantile([lower, upper])
    return clean.clip(lo, hi)


def safe_log1p_signed(s: pd.Series) -> pd.Series:
    values = pd.to_numeric(s, errors="coerce")
    return np.sign(values) * np.log1p(np.abs(values))


def corr_rows(df: pd.DataFrame, target: str, fields: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for field in fields:
        if field not in df.columns:
            continue
        pair = df[[target, field]].apply(pd.to_numeric, errors="coerce").dropna()
        if len(pair) < 10:
            rows.append(
                {
                    "target": target,
                    "field": field,
                    "n": len(pair),
                    "pearson": np.nan,
                    "spearman": np.nan,
                    "note": "too_few_observations",
                }
            )
            continue
        rows.append(
            {
                "target": target,
                "field": field,
                "n": len(pair),
                "pearson": pair[target].corr(pair[field], method="pearson"),
                "spearman": pair[target].corr(pair[field], method="spearman"),
                "note": "",
            }
        )
    return rows


def quantile_summary(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    rows = []
    for field in fields:
        if field not in df.columns:
            continue
        s = pd.to_numeric(df[field], errors="coerce").dropna()
        if s.empty:
            continue
        q = s.quantile([0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0])
        rows.append(
            {
                "field": field,
                "n": int(s.size),
                "missing": int(df[field].isna().sum()),
                "min": q.loc[0],
                "p01": q.loc[0.01],
                "p05": q.loc[0.05],
                "p25": q.loc[0.25],
                "median": q.loc[0.5],
                "p75": q.loc[0.75],
                "p95": q.loc[0.95],
                "p99": q.loc[0.99],
                "max": q.loc[1.0],
                "max_to_p99_ratio": q.loc[1.0] / q.loc[0.99] if q.loc[0.99] not in (0, np.nan) else np.nan,
            }
        )
    return pd.DataFrame(rows)


def transform_diagnostics(df: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    rows = []
    for field in fields:
        if field not in df.columns:
            continue
        raw = pd.to_numeric(df[field], errors="coerce")
        log_signed = safe_log1p_signed(raw)
        win_log = winsorise(log_signed)
        pair_raw = pd.DataFrame({"turnover": df["observed_turnover"], "x": raw}).dropna()
        pair_log = pd.DataFrame({"turnover": df["log_observed_turnover"], "x": log_signed}).dropna()
        pair_win = pd.DataFrame({"turnover": df["log_observed_turnover"], "x": win_log}).dropna()
        rows.append(
            {
                "field": field,
                "n_raw": len(pair_raw),
                "raw_spearman_vs_turnover": pair_raw["turnover"].corr(pair_raw["x"], method="spearman")
                if len(pair_raw) >= 10
                else np.nan,
                "signed_log_spearman_vs_log_turnover": pair_log["turnover"].corr(pair_log["x"], method="spearman")
                if len(pair_log) >= 10
                else np.nan,
                "winsorised_signed_log_spearman_vs_log_turnover": pair_win["turnover"].corr(pair_win["x"], method="spearman")
                if len(pair_win) >= 10
                else np.nan,
                "raw_skew": raw.dropna().skew(),
                "signed_log_skew": log_signed.dropna().skew(),
                "recommendation": "log_or_signed_log_plus_winsorise"
                if raw.dropna().skew() > 2 or raw.dropna().quantile(0.99) * 5 < raw.dropna().max()
                else "log_transform_still_preferred_for_scale_model",
            }
        )
    return pd.DataFrame(rows)


def residual_outliers(df: pd.DataFrame) -> pd.DataFrame:
    model_df = df[["log_observed_turnover", "financial_scale_score"]].dropna()
    if len(model_df) < 10:
        return pd.DataFrame()
    slope, intercept = np.polyfit(model_df["financial_scale_score"], model_df["log_observed_turnover"], deg=1)
    out = df.copy()
    out["pred_log_turnover_from_score"] = intercept + slope * out["financial_scale_score"]
    out["score_turnover_residual"] = out["log_observed_turnover"] - out["pred_log_turnover_from_score"]
    out["abs_residual"] = out["score_turnover_residual"].abs()
    cols = [
        "CompanyNumber",
        "CompanyName",
        "primary_sector",
        "Accounts_AccountCategory",
        "observed_turnover",
        "observed_segment",
        "financial_scale_score",
        "current_assets",
        "equity",
        "employees",
        "creditors_total",
        "pred_log_turnover_from_score",
        "score_turnover_residual",
        "abs_residual",
    ]
    return out.sort_values("abs_residual", ascending=False)[cols].head(30)


def save_plots(t1: pd.DataFrame) -> list[str]:
    written: list[str] = []
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return written

    plt.figure(figsize=(8, 5))
    colors = t1["observed_segment"].map({"BB": "#3b82f6", "SME": "#16a34a", "MidCorporate": "#dc2626"}).fillna("#6b7280")
    plt.scatter(t1["financial_scale_score"], t1["log_observed_turnover"], c=colors, alpha=0.75, s=28)
    plt.xlabel("financial_scale_score")
    plt.ylabel("log(observed turnover)")
    plt.title("Financial scale score vs observed turnover")
    plt.grid(alpha=0.2)
    p = OUT_DIR / "score_vs_log_turnover.png"
    plt.tight_layout()
    plt.savefig(p, dpi=160)
    plt.close()
    written.append(str(p))

    plt.figure(figsize=(7, 5))
    order = ["BB", "SME", "MidCorporate"]
    data = [t1.loc[t1["observed_segment"] == seg, "financial_scale_score"].dropna() for seg in order]
    plt.boxplot(data, labels=order, showfliers=False)
    plt.ylabel("financial_scale_score")
    plt.title("Financial scale score by observed segment")
    plt.grid(axis="y", alpha=0.2)
    p = OUT_DIR / "score_by_observed_segment.png"
    plt.tight_layout()
    plt.savefig(p, dpi=160)
    plt.close()
    written.append(str(p))

    return written


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    features = pd.read_csv(FEATURES_CSV)
    turnover = pd.read_csv(TURNOVER_CSV)

    key_cols = ["CompanyNumber", "internal_filename"]
    turn = turnover[key_cols + ["selected_turnover_value", "selected_fact_name", "has_turnover_candidate"]].copy()
    df = features.merge(turn, on=key_cols, how="left", suffixes=("", "_selected"))
    df["observed_turnover"] = pd.to_numeric(df["selected_turnover_value"], errors="coerce")
    df["observed_turnover"] = df["observed_turnover"].fillna(pd.to_numeric(df["turnover"], errors="coerce"))
    df["log_observed_turnover"] = np.log(df["observed_turnover"].where(df["observed_turnover"] > 0))
    df["observed_segment"] = df["observed_turnover"].apply(assign_segment)
    df["observed_segment_code"] = df["observed_segment"].map(SEGMENT_ORDER)

    t1 = df[df["observed_turnover"].notna()].copy()

    corr = pd.DataFrame(
        corr_rows(t1, "log_observed_turnover", ["financial_scale_score", "financial_scale_score_raw"] + LOG_FIELDS)
        + corr_rows(t1, "observed_turnover", PROXY_FIELDS)
        + corr_rows(t1, "observed_segment_code", PROXY_FIELDS)
    )
    corr.to_csv(OUT_DIR / "financial_scale_score_correlations.csv", index=False, encoding="utf-8-sig")

    segment_summary = (
        t1.groupby("observed_segment", dropna=False)
        .agg(
            companies=("CompanyNumber", "count"),
            turnover_median=("observed_turnover", "median"),
            turnover_p25=("observed_turnover", lambda x: x.quantile(0.25)),
            turnover_p75=("observed_turnover", lambda x: x.quantile(0.75)),
            score_median=("financial_scale_score", "median"),
            score_mean=("financial_scale_score", "mean"),
            current_assets_median=("current_assets", "median"),
            equity_median=("equity", "median"),
            employees_median=("employees", "median"),
            creditors_total_median=("creditors_total", "median"),
        )
        .reset_index()
    )
    segment_summary["segment_order"] = segment_summary["observed_segment"].map(SEGMENT_ORDER)
    segment_summary = segment_summary.sort_values("segment_order").drop(columns=["segment_order"])
    segment_summary.to_csv(OUT_DIR / "financial_scale_score_segment_summary.csv", index=False, encoding="utf-8-sig")

    quantiles = quantile_summary(t1, ["observed_turnover"] + PROXY_FIELDS)
    quantiles.to_csv(OUT_DIR / "financial_scale_score_quantiles.csv", index=False, encoding="utf-8-sig")

    transforms = transform_diagnostics(t1, PROXY_FIELDS)
    transforms.to_csv(OUT_DIR / "financial_scale_score_transform_diagnostics.csv", index=False, encoding="utf-8-sig")

    outliers = residual_outliers(t1)
    outliers.to_csv(OUT_DIR / "financial_scale_score_outliers.csv", index=False, encoding="utf-8-sig")

    plot_paths = save_plots(t1)

    summary = {
        "input_features": str(FEATURES_CSV),
        "input_turnover": str(TURNOVER_CSV),
        "all_feature_rows": int(len(df)),
        "t1_observed_turnover_rows": int(len(t1)),
        "t1_rate": float(len(t1) / len(df)) if len(df) else 0.0,
        "observed_segment_counts": t1["observed_segment"].value_counts(dropna=False).to_dict(),
        "financial_scale_score_vs_log_turnover_spearman": float(
            t1[["financial_scale_score", "log_observed_turnover"]].dropna().corr(method="spearman").iloc[0, 1]
        ),
        "financial_scale_score_vs_observed_segment_spearman": float(
            t1[["financial_scale_score", "observed_segment_code"]].dropna().corr(method="spearman").iloc[0, 1]
        ),
        "core_field_complete_rows": int(
            t1[["current_assets", "equity", "employees", "creditors_total"]].notna().all(axis=1).sum()
        ),
        "plot_paths": plot_paths,
    }
    (OUT_DIR / "financial_scale_score_sanity_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nTop correlations vs log observed turnover:")
    print(
        corr[corr["target"] == "log_observed_turnover"]
        .sort_values("spearman", ascending=False)
        .head(12)
        .to_string(index=False)
    )
    print("\nSegment summary:")
    print(segment_summary.to_string(index=False))
    print(f"\nOutputs written to: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
