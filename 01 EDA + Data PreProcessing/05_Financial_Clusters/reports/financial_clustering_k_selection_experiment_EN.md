# SignalBridge Financial Clustering: K-Selection Experiment and Results

## 1. Experiment overview

| Item | Description |
|---|---|
| Objective | Identify interpretable financial archetypes from each company's latest financial snapshot and produce structured financial signals for the downstream company-ranking system |
| Population | 100,000 active UK companies |
| Final selection | **K = 5** |
| Final status | K=5 passed the statistical-stability, cluster-size and business-interpretability checks and is accepted as the working financial-cluster framework |
| V1 Run ID | `20260725T151423Z` |
| V2 Run ID | `20260725T153022Z` |
| Experiment date | 25 July 2026 |

The purpose of this experiment was not to repeat the BB / SME / Mid Corporate classification task. The clusters describe financial structure, potential financing need and risk type. Business-segment labels will be used later for cross-analysis and will not be treated as clustering features.

---

## 2. Data sources and table roles

S3 input prefix:

```text
s3://team6-project-288469846191-eu-north-1-an/processed/financial_features/
```

| File | Grain | Role in the experiment |
|---|---|---|
| `01_financial_status_labels_100k.csv` | One row per company, latest snapshot | Current financial values, status reason codes and profile interpretation |
| `02_financial_scale_labels_100k.csv` | One row per company, latest snapshot | Low / Medium / High scale bands for interpretation and Tableau cross-analysis |
| `03_financial_change_labels.csv` | One adjacent annual pair per row | Reconstruct historical period-t clusters and observe period-t+1 changes |
| `04_financial_transition_labels.csv` | One adjacent annual pair per row | Validate subsequent onset, persistence and recovery of financial-pressure states |
| `05_financial_data_quality_labels_100k.csv` | One row per company | Sample filtering, completeness controls, confidence and sensitivity analysis |

Join keys:

```text
Company-level tables:
CompanyNumber_norm

Period-pair tables:
CompanyNumber_norm + period_t + period_t_plus_1
```

Leakage controls:

- Clustering uses only fields available in the latest snapshot or at historical period t.
- Period-t+1 changes and transitions are used only as external outcomes.
- News, hiring and BB / SME / Mid Corporate labels are excluded from clustering.
- Historical validation assigns a cluster using period-t features before examining period-t+1 outcomes.

---

## 3. Analysis cohorts

### 3.1 Broad eligible cohort

The main business cohort contains **84,711 companies**. Eligibility requires:

- `useful_financial_evidence_flag = True`;
- at least four available core proxy fields;
- accounts no older than 24 months;
- no impossible negative values;
- at least five non-missing model features.

### 3.2 Complete core cohort

The sensitivity cohort contains **22,878 companies**. It applies the broad rules and additionally requires:

```text
core_fields_complete_flag = True
```

The broad cohort represents the intended business coverage. The complete-core cohort tests whether missingness and disclosure completeness materially change the K selection.

---

## 4. V1 experiment and failure diagnosis

V1 used 14 features covering scale, solvency and operating-structure ratios. It automatically selected K=2:

| Cluster | Companies | Share |
|---|---:|---:|
| FC01 | 2,272 | 2.64% |
| FC02 | 83,872 | 97.36% |

Although K=2 achieved a Silhouette score of 0.938 and a Bootstrap ARI of 0.824, it did not identify two meaningful company archetypes. It separated a small extreme group from the remaining population.

Approximately 99.95% of the distance between the two centroids came from two variables:

| Feature | Contribution to centroid distance |
|---|---:|
| `employees_per_million_assets_proxy` | 60.33% |
| `creditors_to_disclosed_assets_proxy` | 39.62% |
| Remaining 12 features combined | approximately 0.05% |

Primary causes:

1. Ratios exploded when their denominators were very small.
2. The 99th-percentile caps remained extremely high.
3. Sparse variables formed a large mass at the imputed median, leaving near-zero IQR and ineffective robust scaling.
4. V1 restricted only the minimum cluster share and did not constrain the maximum share.
5. MiniBatchKMeans inertia was not consistently decreasing across K, indicating inconsistent local convergence.

V1 conclusion:

> K=2 was rejected and must not be used for formal company labels. V1 is retained as a reproducible methodological failure and diagnostic record.

---

## 5. V2 methodological changes

### 5.1 K search range

```text
K = 3, 4, 5, 6, 7, 8
```

K=2 was excluded because two categories cannot support the intended multi-archetype financial framework.

### 5.2 Model features

V2 retained eight higher-coverage core features that can also be reconstructed at historical period t.

#### Scale block: 40% total weight

```text
log_current_assets
log_creditors_total
log_employees
```

#### Solvency block: 40% total weight

```text
signed_log_equity
signed_log_net_assets_liabilities
signed_log_total_assets_less_current_liabilities
```

#### Creditor-pressure block: 20% total weight

```text
log_creditors_to_current_assets_proxy
signed_log_current_assets_minus_creditors_proxy
```

Cash, debtors and fixed-assets variables have lower coverage. They no longer affect company-to-company clustering distance and are instead used for post-clustering profile interpretation.

The creditor-pressure ratio is calculated only when:

```text
current_assets >= GBP 1,000
creditors_total >= 0
```

This rule prevents extremely small denominators from generating artificial distances.

### 5.3 Preprocessing

1. Apply `log1p` to non-negative amounts.
2. Apply signed-log transformation to variables that may be negative.
3. Winsorise every feature at its 1st and 99th percentiles.
4. Impute missing values with the training-sample median.
5. Standardise with StandardScaler.
6. Apply total distance weights of 40%, 40% and 20% to the three feature blocks.

### 5.4 Algorithm and sampling

- Algorithm: standard KMeans;
- fixed fitting sample: 60,000 companies;
- `n_init = 30`;
- `max_iter = 500`;
- Silhouette evaluation sample: 8,000 companies;
- Bootstrap stability reference sample: 8,000 companies;
- Bootstrap repeats: 3;
- random seed: 42.

Using the same fixed sample and standard KMeans makes inertia and quality metrics more comparable across candidate K values. After selecting K, all eligible companies are assigned to their nearest centroid.

### 5.5 Evaluation criteria

| Metric | Direction or rule |
|---|---|
| Silhouette | Higher is better |
| Calinski–Harabasz | Higher is better |
| Davies–Bouldin | Lower is better |
| Bootstrap ARI | Higher indicates more stable assignments |
| Minimum cluster share | At least 2% |
| Maximum cluster share | No more than 65% |
| Normalized cluster entropy | At least 0.70 |

Composite-score weights:

```text
Silhouette          25%
Calinski–Harabasz   10%
Davies–Bouldin      10%
Bootstrap ARI       30%
Cluster balance     25%
```

---

## 6. V2 K-comparison results

### 6.1 Broad eligible cohort

| K | Silhouette | Davies–Bouldin | Bootstrap ARI | Minimum share | Maximum share | Entropy | Composite |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 0.220 | 1.407 | 0.973 | 19.42% | 48.43% | 0.941 | 0.517 |
| 4 | 0.259 | 1.205 | 0.965 | 14.90% | 38.11% | 0.953 | 0.533 |
| **5** | **0.289** | **1.152** | **0.982** | **11.27%** | **41.00%** | **0.924** | **0.792** |
| 6 | 0.302 | 1.226 | 0.978 | 6.74% | 40.54% | 0.900 | 0.592 |
| 7 | 0.264 | 1.248 | 0.982 | 5.44% | 31.99% | 0.916 | 0.658 |
| 8 | 0.260 | 1.200 | 0.971 | 5.01% | 28.55% | 0.906 | 0.408 |

K=5 achieved the highest composite score in the primary business cohort and passed every configured statistical and business rule.

### 6.2 Complete core cohort

| K | Silhouette | Davies–Bouldin | Bootstrap ARI | Minimum share | Maximum share | Entropy | Composite |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 0.303 | 1.156 | 0.982 | 17.95% | 57.30% | 0.886 | 0.683 |
| **4** | **0.321** | **1.135** | **0.992** | **14.76%** | **44.97%** | **0.926** | **0.858** |
| 5 | 0.336 | 1.257 | 0.749 | 8.72% | 44.62% | 0.879 | 0.475 |
| 6 | 0.285 | 1.221 | 0.943 | 8.21% | 31.55% | 0.939 | 0.608 |
| 7 | 0.275 | 1.210 | 0.704 | 2.34% | 24.75% | 0.911 | 0.342 |
| 8 | 0.261 | 1.158 | 0.958 | 2.27% | 22.88% | 0.938 | 0.533 |

The complete-core cohort preferred K=4. A direct K=4 versus K=5 crosswalk showed that:

- K=4 retained the V2 distressed cluster FC02 almost intact.
- K=4 retained the asset-backed, creditor-heavy cluster FC04 almost intact.
- K=4 merged FC01 with part of FC03.
- K=4 merged FC05 with another part of FC03.

K=4 therefore preserved the primary risk structure but compressed the scale gradient among financially healthy companies. K=5 added the commercially useful progression:

```text
Small healthy → Healthy core → Large financially strong
```

Because the ranking system must cover the broad cohort and distinguish the capacity levels of healthy companies, K=5 was retained.

---

## 7. Cluster-size distribution under K=5

| Cluster | Companies | Share |
|---|---:|---:|
| FC01 | 12,828 | 15.14% |
| FC02 | 15,056 | 17.77% |
| FC03 | 34,734 | 41.00% |
| FC04 | 12,549 | 14.81% |
| FC05 | 9,544 | 11.27% |
| **Total** | **84,711** | **100.00%** |

The counts have a unimodal, broadly bell-shaped appearance, with a large central group and smaller groups at both ends. They must not be described as a formal normal distribution because clusters are discrete categories and FC01–FC05 are not equally spaced numerical values.

For a continuous scale index:

- skewness: 0.169, indicating broad symmetry;
- excess kurtosis: 1.696, indicating heavier tails than a normal distribution;
- normality test: `p < 0.001`, rejecting normality.

Recommended wording:

> The cluster-size distribution is unimodal and broadly bell-shaped, while the underlying financial scale distribution remains heavy-tailed rather than normally distributed.

---

## 8. Formal definitions of the five financial clusters

### 8.1 Formal names

| Cluster | Formal name | Interpretation |
|---|---|---|
| FC01 | **Small Low-Activity** | Small companies with limited operating scale |
| FC02 | **Distressed Balance Sheet** | Companies with severe balance-sheet distress |
| FC03 | **Healthy Core** | Financially healthy core population |
| FC04 | **Asset-Backed Creditor-Heavy** | Asset-backed companies under creditor and working-capital pressure |
| FC05 | **Large Financially Strong** | Larger companies with strong financial capacity |

### 8.2 Key financial medians

| Variable | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Cash | GBP 715 | GBP 3,482 | GBP 27,099 | GBP 9,244 | GBP 158,543 |
| Creditors | GBP 380 | GBP 39,934 | GBP 16,523 | GBP 77,054 | GBP 165,614 |
| Current assets | GBP 979 | GBP 9,000 | GBP 49,729 | GBP 17,212 | GBP 445,637 |
| Debtors | GBP 562 | GBP 7,700 | GBP 18,695 | GBP 7,599 | GBP 215,523 |
| Employees | 0 | 1 | 1 | 1 | 8 |
| Equity | GBP 400 | **GBP -12,092** | GBP 22,470 | GBP 10,365 | GBP 189,597 |
| Fixed assets | GBP 1,099 | GBP 8,134 | GBP 4,335 | GBP 105,624 | GBP 49,863 |
| Net assets | GBP 460 | **GBP -15,571** | GBP 26,112 | GBP 14,506 | GBP 266,902 |
| Net current assets | GBP 425 | **GBP -16,480** | GBP 23,220 | **GBP -5,321** | GBP 177,906 |
| Total assets less current liabilities | GBP 987 | **GBP -4,878** | GBP 38,275 | GBP 43,212 | GBP 337,501 |

### 8.3 Current financial-pressure rates

| Current state | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative equity | 9.79% | **88.53%** | 0.28% | 2.83% | 0.48% |
| Working-capital deficit | 11.77% | **87.47%** | 3.67% | **64.92%** | 7.90% |
| Creditors exceed current assets | 30.23% | **88.60%** | 2.12% | **100.00%** | 7.64% |
| Core fields complete | 9.35% | 23.44% | 25.12% | 26.32% | **64.13%** |

### 8.4 Cluster interpretations

#### FC01 — Small Low-Activity

- Low asset, employee and creditor scale.
- 80.5% of companies are Micro Entities.
- Current financial pressure is limited, but financial disclosure completeness is the lowest.
- The cluster should be interpreted as small and low-activity rather than automatically low-risk.

#### FC02 — Distressed Balance Sheet

- Median equity, net assets and net current assets are negative.
- Negative-equity rate is 88.53%.
- Working-capital-deficit rate is 87.47%.
- This is the clearest financially distressed group.
- It should receive a high financial-risk signal and must not receive a high opportunity score merely because financing need appears high.

#### FC03 — Healthy Core

- Medium scale with positive equity and net assets.
- Negative equity, working-capital deficit and creditor pressure are very uncommon.
- It contains 41.00% of eligible companies and forms the core healthy population.
- It is a useful benchmark group for downstream analysis.

#### FC04 — Asset-Backed Creditor-Heavy

- Median fixed assets are GBP 105,624.
- Median creditors are GBP 77,054.
- Equity and net assets remain positive.
- Working-capital-deficit rate is 64.92%, while creditors exceed current assets for 100% of eligible observations.
- Real Estate represents 44.8%, although the cluster spans other sectors.
- It represents asset backing combined with short-term financial-structure pressure and may contain both financing opportunity and risk.

#### FC05 — Large Financially Strong

- The highest current-assets, cash, debtors, equity and net-assets levels.
- Median employee count is eight.
- Core-field completeness is 64.13%, materially higher than in the other clusters.
- Current pressure and subsequent onset rates are the lowest.
- It represents high financial capacity and comparatively low financial risk.

---

## 9. Assignment quality

| Cluster | Median assignment margin | High-confidence share |
|---|---:|---:|
| FC01 | 0.320 | 61.98% |
| FC02 | 0.338 | 68.20% |
| FC03 | 0.518 | 82.75% |
| FC04 | 0.398 | 76.18% |
| FC05 | 0.521 | 77.66% |

FC03 and FC05 have the clearest boundaries. FC01 and FC02 contain more boundary cases. Downstream datasets should therefore retain:

```text
assignment_margin
cluster_assignment_confidence
imputed_feature_count
```

A low-confidence assignment should not be treated as an absolute company characteristic.

---

## 10. Validation against subsequent financial outcomes

Historical data:

- original adjacent annual pairs: 81,603;
- pairs with a reasonable annual gap: 81,598;
- historical clusters are reconstructed only when at least five model features are available;
- all outcomes are observed at period t+1 after assigning the period-t cluster.

### 10.1 Subsequent onset rates

| Subsequent event | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative-equity onset | 8.25% | 7.24% | 3.85% | 7.25% | **2.20%** |
| Working-capital-deficit onset | 10.10% | **23.61%** | 7.78% | 13.22% | **5.65%** |
| Creditor-pressure onset | 16.12% | **27.68%** | 10.27% | N/A | **6.26%** |

FC04 already has creditor pressure in almost all eligible period-t observations, leaving no meaningful population at risk of a new creditor-pressure onset.

### 10.2 Persistence and recovery

| Subsequent outcome | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative-equity persistence | 69.38% | **78.58%** | 76.47% | 76.64% | 65.62% |
| Negative-equity recovery | 30.62% | 21.42% | 23.53% | 23.36% | **34.38%** |
| Working-capital-deficit persistence | 68.74% | **84.26%** | 77.69% | 81.63% | 76.93% |
| Working-capital-deficit recovery | 31.26% | **15.74%** | 22.31% | 18.37% | 23.07% |
| Creditor-pressure persistence | 79.72% | 86.60% | **91.94%** | 82.13% | 74.38% |
| Creditor-pressure recovery | 20.28% | 13.40% | 8.06% | 17.87% | **25.62%** |

Persistence and recovery rates are conditional on the corresponding eligibility population. Percentages must therefore be interpreted together with eligible-pair counts. FC03 and FC05 begin with very few negative-equity companies, so their persistence samples are much smaller than FC02's.

Reported-loss coverage is low and cluster-level eligible samples are limited. It is retained as supporting evidence rather than a primary cluster-defining outcome.

Overall interpretation:

- FC02 has the highest combined financial risk.
- FC04 represents persistent working-capital and creditor pressure despite asset backing.
- FC03 is the healthy core, although the small subgroup already under pressure may remain under pressure.
- FC05 has the lowest onset rates and generally stronger recovery.
- FC01 has limited current pressure, but subsequent negative-equity and creditor-pressure onset rates exceed those of FC03 and FC05.

---

## 11. Final rationale for selecting K=5

K=5 is accepted as the current financial-cluster framework because:

1. It achieved the highest composite score in the broad eligible cohort.
2. Bootstrap ARI reached 0.982, indicating strong assignment stability.
3. The smallest cluster contains 11.27% and the largest 41.00%; no cluster is trivial or dominant.
4. Normalized cluster entropy reached 0.924.
5. The five clusters differ clearly in scale, equity, net assets, fixed assets and creditor pressure.
6. FC02, FC03 and FC04 have similar overall scale but materially different financial states, proving that the solution is not a simple size segmentation.
7. The clusters show interpretable differences in subsequent onset, persistence and recovery.
8. K=5 preserves the scale gradient among healthy companies that K=4 compresses.

Final parameter:

```text
SELECTED_K = 5
```

---

## 12. Relationship between clusters and the ranking system

Cluster IDs are not an ordered score and must not be converted directly into values from one to five.

- FC02 may have high financing need but also the highest risk.
- FC04 may represent a genuine financing opportunity subject to risk constraints.
- FC05 has strong financial capacity and low risk but does not necessarily have the highest immediate financing need.
- FC01 is small, so its commercial value and growth potential require hiring, news and sector evidence.

Recommended financial outputs:

| Dimension | Meaning |
|---|---|
| Financial capacity | Ability to support financing and broader commercial relationships |
| Financing need | Evidence of potential funding or working-capital requirements |
| Financial risk | Negative equity, working-capital deficit and creditor pressure |
| Data confidence | Evidence tier, completeness and cluster-assignment confidence |

Downstream integration:

```text
Business segment × Financial cluster × News signals × Hiring signals
```

BB / SME / Mid Corporate provides the business segment, the financial cluster provides financial structure, and news and hiring provide growth momentum and event evidence.

---

## 13. Limitations

1. Each cluster uses the latest financial snapshot and is not a permanent company identity.
2. Companies House Accounts are mainly annual disclosures and do not directly measure financing need over the next four to six months.
3. `creditors_total` is not necessarily identical to current liabilities under a strict accounting definition; related measures are proxies.
4. Cash, fixed-assets and debtors coverage is insufficient for inclusion in the core clustering distance.
5. Reported-loss coverage is low.
6. Historical validation is retrospective external association analysis, not formal forecast accuracy.
7. New financial snapshots require monitoring of cluster sizes, centroid drift and assignment confidence.
8. K=5 is less stable than K=4 within the complete-core cohort, so cohort-sensitivity monitoring should continue.
9. Automatically generated names are preliminary; formal names should be fixed in a controlled business mapping.

---

## 14. Experiment artefacts and paths

### Notebook

EC2:

```text
/data/signalbridge/notebooks/financial_clustering/01_financial_cluster_k_selection_v2.ipynb
```

S3:

```text
s3://team6-project-288469846191-eu-north-1-an/notebooks/financial_clustering/01_financial_cluster_k_selection_v2.ipynb
```

### V2 results

```text
s3://team6-project-288469846191-eu-north-1-an/processed/financial_clustering/k_selection_v2/run_id=20260725T153022Z/
```

Primary files:

```text
k_selection_metrics.csv
k_selection_shortlist.csv
company_cluster_assignments.csv
cluster_profiles.csv
cluster_sector_mix.csv
cluster_account_category_mix.csv
cluster_scale_band_mix.csv
cluster_future_transition_rates.csv
cluster_future_change_summary.csv
figures/
```

### V2 model

```text
s3://team6-project-288469846191-eu-north-1-an/models/financial_clustering/k_selection/v2/run_id=20260725T153022Z/
```

Primary files:

```text
financial_cluster_model.joblib
experiment_config.json
cluster_name_mapping.json
```

---

## 15. Next steps

1. Freeze the five formal English cluster names.
2. Produce the final company-level Financial Cluster master table.
3. Retain cluster ID, assignment margin, confidence and reason codes for every company.
4. Extend the `Cluster × Sector × Account Category` analysis.
5. Cross the clusters with BB / SME / Mid Corporate results.
6. Construct Financial Capacity, Financing Need, Financial Risk and Data Confidence outputs.
7. Integrate News and Hiring dimensions.
8. Build Tableau views for cluster distribution, profiles, sectors, risks and transitions.
9. Monitor cluster drift and stability when a new financial snapshot becomes available.

