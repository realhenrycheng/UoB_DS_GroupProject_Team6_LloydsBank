# Guide to the Five Financial Analysis Tables

## Data scope

- Company universe: `UKcompanies_active_account_category_sample_100k.csv`, containing 100,000 companies.
- Financial source: 24 Companies House Accounts Monthly Bulk ZIPs from July 2024 to June 2026.
- Current snapshot: each company's latest account period, not its historical best-evidence period.
- Quantile labels: 30th/70th percentiles within `primary_sector + Accounts_AccountCategory`; groups with fewer than 30 eligible observations or tied thresholds fall back to sector and then global thresholds.
- The raw company list and Accounts ZIP files are never modified.

## Files and roles

### 1. `01_financial_status_labels_100k.csv`

One row per company, 100,000 rows. It describes the latest accounting state and reason codes: negative equity, working-capital deficit, reported loss, creditor pressure, cash coverage, asset intensity, receivables intensity and related empirical bands.

- `negative_equity_flag`: 17,170/91,479, or 18.77% of eligible companies.
- `working_capital_deficit_flag`: 27,349/89,721, or 30.48% of eligible companies.
- `reported_loss_flag`: 1,343/4,655, or 28.85% of eligible companies; use only as a secondary signal because coverage is sparse.

Use: current company profiling, model features and explanations. These fields are not direct financing-demand labels.

### 2. `02_financial_scale_labels_100k.csv`

One row per company, 100,000 rows. It provides separate Low/Medium/High bands for current assets, fixed assets, creditors, absolute equity, employees, net assets and total assets.

Use: three-class model features, within-sector scale comparison and scale proxies where turnover is unavailable. It does not create a manually weighted commercial-opportunity score and does not replace Lloyds' formal BB/SME/Mid Corporate segmentation.

### 3. `03_financial_change_labels.csv`

One row per adjacent annual company-period pair, 81,603 rows across 76,611 companies. It contains values at `t` and `t+1`, signed-log changes, percentage changes and empirical 30/70 change bands.

Use: describing growth, stability or contraction. Historical changes can be model features, while next-period changes can be prediction targets. A `t -> t+1` change is not known at time `t` and must not be used as a time-`t` feature.

### 4. `04_financial_transition_labels.csv`

One row per adjacent annual company-period pair, 81,603 rows. It records onset, persistence and recovery for negative equity, working-capital deficit, creditor pressure and reported loss.

- `negative_equity_onset_flag`: 3,325/64,717, or 5.14% of eligible pairs.
- `working_capital_deficit_onset_flag`: 4,623/53,281, or 8.68% of eligible pairs.

Use: next-period financial-state prediction. Every target must be filtered by its corresponding `*_eligible` field; missing observations must never be converted to False.

### 5. `05_financial_data_quality_labels_100k.csv`

One row per company, 100,000 rows. It contains T1-T4 evidence tier, period counts, turnover coverage, field completeness, account recency, impossible negative values, extreme amounts and evidence-tier movements.

Use: filtering, sample weighting, confidence, sensitivity analysis and data-quality monitoring. It is not a commercial-opportunity outcome.

## Join keys

- Company-level tables: join on `CompanyNumber_norm`.
- Longitudinal tables: uniquely identify a pair with `CompanyNumber_norm + period_t + period_t_plus_1`.
- When joining news or hiring data, ensure that every variable was observable on or before `available_date_t`.

## Feature, target and control roles

- Current status and scale labels are usually features or reason codes.
- `*_onset_flag`, `*_recovery_flag` and next-period change bands can be future targets.
- Evidence tier, completeness and anomaly fields are controls/confidence variables.
- The formal three-class target should still be generated from observed turnover: BB below £3m, SME £3m–£25m, and Mid Corporate £25m–£500m.

## Important limitations

- Accounts are mainly annual disclosures; a next-account financial state is not the same as financing demand in the next four to six months.
- `creditors_total` is not necessarily identical to strictly defined current liabilities, so related ratios are proxies.
- Quantile labels are relative positions within this sample, not universal financial-health standards.
- Future models must use `available_date` for temporal splitting and must not place future filings in the training set.
