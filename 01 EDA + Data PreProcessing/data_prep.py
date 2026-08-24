"""
preprocessing.py - Preprocessing for financial change prediction

    clean_global(df): no fitting, run once on the full table
    build_matrix(frame, variant): fitting; refitted inside each training fold

"""

import numpy as np
import pandas as pd
import re

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

METRICS = [
    "current_assets", "fixed_assets", "creditors_total", "equity",
    "net_assets_liabilities", "net_current_assets_liabilities",
    "cash", "debtors", "employees", "profit_loss",
    "total_assets_less_current_liabilities",
]

# Fields that cannot be negative. The other five can
NONNEG = ["current_assets", "fixed_assets", "creditors_total", "cash", "debtors", "employees"]


# Bimodal on the signed-log scale. A single linear coefficient cannot describe both clusters,
# so the Ridge branch splits them into sign and magnitude. Trees can split near zero and are left unchanged
BIMODAL = ["equity", "net_assets_liabilities", "net_current_assets_liabilities",
           "total_assets_less_current_liabilities", "profit_loss"]


# AccountCategory Merged to five. 
# The smallest raw category has one row and would be absent from some folds.
# GROUP's missingness pattern is different from the others, so it is kept apart.
CATEGORY_MAP = {
    "MICRO ENTITY":               "MICRO",
    "TOTAL EXEMPTION FULL":       "TEF",
    "UNAUDITED ABRIDGED":         "ABRIDGED",
    "GROUP":                      "GROUP",
    "SMALL":                      "FULL_DISCLOSURE",
    "MEDIUM":                     "FULL_DISCLOSURE",
    "FULL":                       "FULL_DISCLOSURE",
    "AUDIT EXEMPTION SUBSIDIARY": "FULL_DISCLOSURE",
}

CAT_COLS = ["primary_sector", "acct_cat_model", "evidence_tier_t"]

NUMERIC_META = ["company_age_at_t", "gap_days", "period_month"]
BINARY_META = ["is_private_limited", "multi_sic_company"]
NO_TRANSFORM = ["period_month", "gap_days"]

# Cleaning thresholds for employees
EMP_CEILING = 1500  # beyond the plausible range
EMP_MICRO_CEILING = 50  # the statutory threshold for micro-entity is 10. 50 tolerates a lagging label

WINSOR_LO, WINSOR_HI = 0.005, 0.995
MIN_GROUP_OBS = 200 # fall back to the global median


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def signed_log1p(x):
    """Sign-preserving log transform"""
    x = pd.to_numeric(x, errors="coerce")
    return np.sign(x) * np.log1p(np.abs(x))

import re

def normalise_company_number(s):
    """
    strip non-alphanumerics, uppercase, and zero-pad pure digits to eight characters.
    """
    s = re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()
    return s.zfill(8) if s.isdigit() else s

# ---------------------------------------------------------------------------
# Layer 1: global cleaning
# ---------------------------------------------------------------------------

def clean_global(df):
    """
    Cleaning and derivation applied once to the full table. Safe to run before splitting.

    Returns:
        out(DataFrame): a cleaned copy
        log(DataFrame): rows affected by each rule
    """
    out = df.copy()
    log = []

    # 1.Impossible negatives to NaN. The values are untrustworthy and unrecoverable.
    for m in NONNEG:
        for suf in ("_t", "_t_plus_1"):
            col = f"{m}{suf}"
            if col not in out.columns:
                continue
            mask = out[col] < 0
            out.loc[mask, col] = np.nan
            log.append({"rule": "negative_to_nan", "column": col, "n": int(mask.sum())})

    # 2.Parsing errors in employees: monetary values mis-tagged, years mis-tagged, figures off by a factor of 1000.
    for suf in ("_t", "_t_plus_1"):
        col = f"employees{suf}"
        if col not in out.columns:
            continue
        mask = (out[col] > EMP_CEILING) | (
            (out["Accounts_AccountCategory"] == "MICRO ENTITY")
            & (out[col] > EMP_MICRO_CEILING)
        )
        out.loc[mask, col] = np.nan
        log.append({"rule": "employees_implausible", "column": col, "n": int(mask.sum())})

    # 3. Account category: merged for modelling, raw retained for stratified reporting
    out["acct_cat_raw"] = out["Accounts_AccountCategory"]
    out["acct_cat_model"] = (out["Accounts_AccountCategory"]
                             .map(CATEGORY_MAP).fillna("FULL_DISCLOSURE"))
    unmapped = set(out["acct_cat_raw"].dropna()) - set(CATEGORY_MAP)
    if unmapped:
        log.append({"rule": "unmapped_category", "column": str(sorted(unmapped)), "n": -1})

    # 4. 96.9% CompanyCategory is Private Limited, so a binary flag suffices
    out["is_private_limited"] = (out["CompanyCategory"] == "Private Limited Company")

    # 5. Age at t. 365.25 approximates leap years.
    out["company_age_at_t"] = (
        (out["period_t"] - out["IncorporationDate"]).dt.days / 365.25
    )

    # 6. Month: seasons recur, so it extrapolates. 
    # Year is deliberately excluded, since every deployment row sits in an unseen year.
    out["period_month"] = out["period_t"].dt.month

    log = pd.DataFrame(log)
    return out, log[log["n"] != 0].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Layer 2: feature matrix
# ---------------------------------------------------------------------------

def _peer_percentile(values, groups, ref=None):
    """
    Within-group percentile. 
    With ref=None the training fold's empirical distributionis recorded; 
    otherwise an existing one is applied.
    """
    if ref is None:
        ref = {k: np.sort(v.dropna().to_numpy())
               for k, v in values.groupby(groups, observed=True)}
    out = [
        np.searchsorted(ref[g], v) / len(ref[g])
        if (g in ref and len(ref[g]) > 0 and pd.notna(v)) else np.nan
        for g, v in zip(groups, values)
    ]
    return np.asarray(out, dtype=float), ref


def build_matrix(frame, variant, fit_stats=None, peer_pct=False):
    """
    Build the feature matrix. Both branches carry identical content:
    the same eleven fields, metadata and rows, differing only in representation

    Parameters:
        variant: "gbm"/"ridge"
        fit_stats: With None, statistics are fitted on `frame` (training fold).
                When passed, they are applied as-is (validation fold).
        peer_pct: Whether to add within-group percentile columns, for the ablation

    Returns:
        X: DataFrame
        cat_cols(list): Categorical column names. The gbm branch leaves them for the model to
                handle. The ridge branch has already one-hot encoded them and returns [].
        fit_stats(dict): Fitted statistics. Empty for gbm.
    """
    if variant not in ("gbm", "ridge"):
        raise ValueError(f"unknown variant: {variant}")

    fitting = fit_stats is None
    stats = {} if fitting else dict(fit_stats)
    X = pd.DataFrame(index=frame.index)

    # the eleven period-t fields
    for m in METRICS:
        v = frame[f"{m}_t"]
        if variant == "ridge" and m in BIMODAL:
            X[f"{m}_is_negative"] = (v < 0).astype(float)
            X[f"{m}_log_abs"] = np.log1p(v.abs())
        else:
            X[f"{m}_sl"] = signed_log1p(v)
        # Missing indicators: disclosure is habitual, so missingness is informative
        X[f"{m}_missing"] = v.isna().astype(float)

    # metadata
    for c in NUMERIC_META:
        X[c] = frame[c]
    for c in BINARY_META:
        X[c] = frame[c].astype(float)

    # within-group percentile (optional)
    if peer_pct:
        refs = stats.get("peer_ref", {})
        for m in METRICS:
            v = signed_log1p(frame[f"{m}_t"])
            r, ref = _peer_percentile(v, frame["acct_cat_model"],
                                      None if fitting else refs.get(m))
            X[f"{m}_peer_pct"] = r
            if fitting:
                refs[m] = ref
        if fitting:
            stats["peer_ref"] = refs

    # categorical variables
    if variant == "gbm":
        for c in CAT_COLS:
            X[c] = frame[c].astype(str)
        return X, CAT_COLS, stats

    # ====== ridge branch only ===========
    num_cols = [c for c in X.columns
                if not c.endswith("_missing")
                and c not in BINARY_META
                and c not in NO_TRANSFORM]
    # Clipping extreme values for linear coefficients
    if fitting:
        stats["winsor"] = {c: (X[c].quantile(WINSOR_LO), X[c].quantile(WINSOR_HI))
                           for c in num_cols}
    for c, (lo, hi) in stats["winsor"].items():
        if c in X.columns:
            X[c] = X[c].clip(lo, hi)


    # Imputation: group medians differ far more than the within-field spread, 
    # so group medians are preferred, with a global fallback where observations are thin.
    groups = frame["acct_cat_model"]
    if fitting:
        imp = {}
        for c in num_cols:
            by_group = X[c].groupby(groups, observed=True)
            counts = by_group.count()
            med = by_group.median()
            # Per group: use the group median where observations suffice, else fall back
            table = {g: med[g] for g in counts.index if counts[g] >= MIN_GROUP_OBS}
            imp[c] = ("group", table, X[c].median())
        stats["impute"] = imp
    for c, (kind, table, fallback) in stats["impute"].items():
        if c not in X.columns:
            continue
        filler = groups.map(table).fillna(fallback) if kind == "group" else fallback
        X[c] = X[c].fillna(filler)
    if fitting:
        stats["impute_simple"] = {c: X[c].median() for c in NO_TRANSFORM if c in X.columns}
    for c, v in stats["impute_simple"].items():
        if c in X.columns:
            X[c] = X[c].fillna(v)

    # One-hot: the category set is fixed on the training fold. 
    # Categories absent from the validation fold are added as zero columns.
    if fitting:
        stats["cat_levels"] = {c: sorted(frame[c].dropna().astype(str).unique())
                               for c in CAT_COLS}
    dummy_cols = []
    for c, levels in stats["cat_levels"].items():
        s = frame[c].astype(str)
        for lv in levels:
            name = f"{c}={lv}"
            X[name] = (s == lv).astype(float)
            dummy_cols.append(name)

    # Interactions: the curves are not parallel, and with main effects only the slope is
    # algebraically identical across groups. 
    # Interaction is present in most fields but varies in strength, 
    # so all numeric columns are treated.
    acct_dummies = [c for c in dummy_cols if c.startswith("acct_cat_model=")]
    inter = {f"{n}__x__{d}": X[n].to_numpy() * X[d].to_numpy()
             for n in num_cols for d in acct_dummies}
    X = pd.concat([X, pd.DataFrame(inter, index=X.index)], axis=1)

    return X, [], stats