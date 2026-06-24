# Financial Segment Modeling Feature Group Conclusion

## Core Conclusion

Using proxy features alone is not sufficient for reliable BB / SME / MidCorporate segment prediction.

The latest feature-group experiment shows that raw financial fields provide the main predictive signal, ratio / flag features add modest incremental value, and proxy features can still provide additional value when combined with the full financial feature set.

For subsequent modeling, the recommended default input is:

```text
Model_D_all_proxy_raw_ratio_flag_features
```

This means:

```text
proxy features
+ raw financial fields
+ ratio features
+ flag features
+ account category
+ sector
```

## Compared Feature Groups

The experiment compared four feature groups:

| Feature Group | Description | Number of Features |
|---|---|---:|
| Model A | proxy-only features | 11 |
| Model B | raw financial fields | 12 |
| Model C | raw financial fields + ratio / flag features | 31 |
| Model D | proxy + raw financial fields + ratio / flag features | 39 |

The two modeling tasks were:

- BB vs non_BB binary classification
- BB / SME / MidCorporate multiclass classification

## Main Findings

### 1. Proxy-only is not enough

Model A is consistently weaker than the feature groups using raw financial data.

This means proxy scores can capture part of the financial scale signal, but they lose too much information when used as the only model input.

Proxy-only models should therefore be used only as a weak baseline or ablation comparison, not as the final modeling input.

### 2. Raw financial fields are essential

Model B substantially improves performance compared with Model A.

This shows that the model needs direct access to financial scale and structure fields such as:

- `current_assets`
- `net_assets_liabilities`
- `equity`
- `cash`
- `debtors`
- `creditors_total`
- `employees`
- `profit_loss`
- `borrowings`

These fields represent the main predictive signal for segment classification.

### 3. Ratio and flag features add modest value

Model C is generally slightly better than Model B, especially for non-linear models.

Useful ratio / structure features include:

- `cash_to_current_assets`
- `debtors_to_current_assets`
- `creditors_to_current_assets`
- `net_assets_to_current_assets`
- `equity_to_current_assets`
- `borrowings_to_current_assets`
- `profit_loss_to_current_assets`
- per-employee financial scale features
- high/low structure flags
- negative equity / negative net asset flags

The improvement from Model B to Model C is positive but not transformational. These features should be kept as supporting financial structure indicators.

### 4. Adding proxy features to the full feature set gives extra value

Model D adds proxy features back on top of Model C.

The result shows that proxy features still contain useful summary information, especially for Logistic Regression.

In the BB vs non_BB task, HistGradientBoosting improves from Model C to Model D:

| Model | Balanced Accuracy | BB Recall | BB F1 |
|---|---:|---:|---:|
| Model C + HistGradientBoosting | 0.882 | 0.786 | 0.817 |
| Model D + HistGradientBoosting | 0.891 | 0.803 | 0.827 |

In the multiclass task, the improvement is smaller but still positive:

| Model | Balanced Accuracy | Macro F1 | Weighted F1 |
|---|---:|---:|---:|
| Model C + HistGradientBoosting | 0.782 | 0.799 | 0.821 |
| Model D + HistGradientBoosting | 0.784 | 0.801 | 0.822 |

The proxy features are therefore not sufficient alone, but they are useful as additional summary signals in the full model.

## Model Choice

The recommended main model is:

```text
Model_D_all_proxy_raw_ratio_flag_features + HistGradientBoosting
```

This is the strongest predictive setup in the current experiment.

The recommended interpretable baseline is:

```text
Model_D_all_proxy_raw_ratio_flag_features + Logistic Regression
```

This model is less flexible than HistGradientBoosting, but it is more transparent and easier to explain in the dissertation and stakeholder discussions.

## Final Modeling Decision

For subsequent financial segment modeling:

```text
Do not use proxy-only features as the final modeling input.

Use Model_D_all_proxy_raw_ratio_flag_features as the default input feature set.
```

The practical interpretation is:

```text
raw financial fields are the core signal;
ratio and flag features add financial structure;
proxy scores add useful summary information;
the full feature set is preferred for later training.
```
