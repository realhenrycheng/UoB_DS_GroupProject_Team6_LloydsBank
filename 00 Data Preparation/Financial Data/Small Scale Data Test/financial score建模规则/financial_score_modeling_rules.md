# Financial Score 建模规则说明

## 1. 目标

本文档整理 Companies House accounts 数据中 financial proxy score 的构建规则。

当前目标不是直接完成最终预测模型，而是建立一套可解释、可复用的财务规模 proxy，用于：

- 在缺少 turnover 的公司中估计财务规模；
- 辅助 BB / SME / Mid Corporate 分层；
- 评估 Companies House accounts 数据是否足以支持后续建模；
- 识别 accounts 披露不足带来的 bias。

## 2. 字段来源

所有原始财务字段均来自 Companies House accounts bulk 文件中的 iXBRL / HTML 标签。

例如：

- `turnover` 来自 `TurnoverRevenue`、`Revenue`、`SalesRevenue` 等标签；
- `current_assets` 来自 current assets 相关标签；
- `net_assets_liabilities` 来自 net assets / liabilities 相关标签；
- `equity` 来自 capital and reserves / equity 相关标签；
- `cash` 来自 cash at bank / cash in hand 相关标签；
- `debtors` 来自 debtors 相关标签；
- `creditors_total` 来自 creditors 相关标签；
- `employees` 来自 average number of employees 相关标签。

以下字段不是 Companies House 原始字段，而是项目中派生得到：

- `financial_core_score_raw`
- `financial_core_score`
- `financial_conservative_score_raw`
- `financial_conservative_score`
- `available_proxy_field_count`
- `available_core_balance_field_count`
- `financial_evidence_tier`
- `observed_segment_from_turnover`

为兼容前一版输出，当前也保留：

- `financial_scale_score_raw`
- `financial_scale_score`

其中：

```text
financial_scale_score_raw = financial_core_score_raw
financial_scale_score = financial_core_score
```

## 3. Turnover 与 Label

如果 accounts 文件中能直接提取 turnover，则该公司属于 T1 样本。

基于 observed turnover，可派生 Lloyds BCB 风格的分层标签：

| Segment | Rule |
|---|---|
| BB | turnover < £3m |
| SME | £3m <= turnover < £25m |
| MidCorporate | £25m <= turnover < £500m |

字段名：

```text
observed_segment_from_turnover
```

该标签只能用于有 observed turnover 的公司。

## 4. Turnover 不进入 Financial Score

正式 financial proxy score 不包含 `turnover`。

原因是 label leakage：

```text
用 turnover 构造 score，再用这个 score 预测 turnover-derived segment
```

会导致结果过于乐观。

因此，后续正式 score 使用 turnover-excluded 版本。

## 5. Log Transform 规则

财务字段通常有极端值，因此规模类字段先做 log 变换。

当前采用 signed log 规则：

```text
signed_log1p(x) = sign(x) * log(1 + abs(x))
```

解释：

- 正值保留为正的 log scale；
- 负值保留负号，例如 negative equity / net liabilities；
- `0` 转换为 `0`；
- `NaN` 保持缺失。

需要注意：

```text
0 != missing
```

如果某个字段真实披露为 0，则应进入计算。

如果某个字段没有披露，为 `NaN`，则代表缺失，而不是公司真实值为 0。

## 6. Core Score

### 6.1 定义

`financial_core_score` 衡量基于已披露核心财务字段的公司财务规模。

当前采用 7 个 core fields：

```text
current_assets
net_assets_liabilities
equity
cash
debtors
creditors_total
employees
```

### 6.2 Raw Score

```text
financial_core_score_raw =
mean(
  log_current_assets,
  log_net_assets_liabilities,
  log_equity,
  log_cash,
  log_debtors,
  log_creditors_total,
  log_employees
)
```

计算规则：

```text
skip missing values
```

也就是说，只对非 `NaN` 字段求平均。

示例：

```text
Company A:
current_assets, equity, employees available
cash, debtors, creditors_total, net_assets_liabilities missing

financial_core_score_raw =
mean(log_current_assets, log_equity, log_employees)
```

### 6.3 解释

Core score 的含义是：

```text
基于已披露核心字段的财务规模 proxy
```

优点：

- 不会把未披露字段误认为 0；
- 对 micro entity / total exemption full 更公平；
- 适合作为主 financial proxy score。

使用时必须同时保留 field count，说明该 score 基于多少个核心字段。

## 7. Conservative Score

### 7.1 定义

`financial_conservative_score` 是固定分母版本，用于对披露不足进行惩罚。

它和 core score 使用相同的 7 个核心字段：

```text
current_assets
net_assets_liabilities
equity
cash
debtors
creditors_total
employees
```

### 7.2 Raw Score

```text
financial_conservative_score_raw =
sum(available log core fields) / 7
```

其中 `7` 是核心字段总数。

缺失字段不参与分子，但仍计入分母。

这等价于：

```text
missing field contributes 0 to the numerator
```

但解释上不应说：

```text
missing = true zero
```

而应说：

```text
missing receives a disclosure penalty
```

### 7.3 解释

Conservative score 的含义是：

```text
披露惩罚后的财务规模 proxy
```

用途：

- 作为 sensitivity check；
- 反映 disclosure completeness；
- 防止少披露公司因为分母小而 score 虚高。

## 8. 标准化规则

两个 raw score 均在样本内做 0-100 min-max 标准化。

```text
financial_core_score =
(financial_core_score_raw - min(core_raw))
/
(max(core_raw) - min(core_raw))
* 100
```

```text
financial_conservative_score =
(financial_conservative_score_raw - min(conservative_raw))
/
(max(conservative_raw) - min(conservative_raw))
* 100
```

注意：

```text
0-100 score 是 sample-relative score
```

它适合当前样本内比较。后续扩大到 candidate / full dataset 时，应重新计算标准化参数，或固定训练集参数后再应用。

## 9. Field Count

Field count 是数据完整度指标，不是公司规模指标。

当前保留：

```text
available_proxy_field_count
available_core_balance_field_count
```

其中：

```text
available_core_balance_field_count =
count_non_missing(
  current_assets,
  net_assets_liabilities,
  equity,
  cash,
  debtors,
  creditors_total,
  employees
)
```

解释：

```text
field count = financial score confidence / data completeness indicator
```

示例：

```text
Company A:
financial_core_score = 80
available_core_balance_field_count = 7
```

说明该 score 基于 7 个核心字段，可信度较高。

```text
Company B:
financial_core_score = 80
available_core_balance_field_count = 2
```

说明该 score 只基于 2 个核心字段，可信度较弱。

## 10. Evidence Tier

继续使用 evidence tier 标记每家公司财务证据强度。

| Tier | Rule | Meaning |
|---|---|---|
| T1 | observed turnover available | 可直接观察 turnover |
| T2 | at least 4 core fields available | balance sheet rich |
| T3 | at least 2 proxy fields available | partial proxy evidence |
| T4 | only account category or very sparse fields | low financial evidence |

字段名：

```text
financial_evidence_tier
```

当前小样本结果：

| Tier | Count |
|---|---:|
| T1_observed_turnover | 149 |
| T2_balance_sheet_rich | 1,829 |
| T3_balance_sheet_partial | 61 |
| T4_account_category_only | 19 |

## 11. Sanity Check 结果

当前基于 sample 输出：

- `financial_features_sample_year.csv`
- `turnover_company_year_selected.csv`

T1 observed turnover 样本：

```text
T1 rows = 149
BB = 68
SME = 62
MidCorporate = 19
```

### 11.1 Score 与 observed turnover

| Score | Spearman vs log(observed turnover) | Spearman vs observed BB/SME/Mid label |
|---|---:|---:|
| financial_core_score | 0.694 | 0.652 |
| financial_conservative_score | 0.705 | 0.667 |

结论：

```text
financial_core_score 与 observed turnover 同方向。
financial_conservative_score 作为 sensitivity check 也与 observed turnover 同方向。
```

### 11.2 Segment Summary

| Observed Segment | Companies | Turnover Median | Core Score Median | Conservative Score Median | Core Field Count Median |
|---|---:|---:|---:|---:|---:|
| BB | 68 | £15,131 | 56.9 | 42.6 | 6 |
| SME | 62 | £13,101,185 | 89.0 | 87.0 | 7 |
| MidCorporate | 19 | £49,230,457 | 94.0 | 93.0 | 7 |

结论：

```text
score median 随 BB -> SME -> MidCorporate 单调上升。
```

## 12. 后续建模使用建议

后续模型中建议同时保留：

```text
financial_core_score
financial_conservative_score
financial_core_score_raw
financial_conservative_score_raw
available_core_balance_field_count
available_proxy_field_count
financial_evidence_tier
has_current_assets
has_net_assets_liabilities
has_equity
has_cash
has_debtors
has_creditors_total
has_employees
Accounts_AccountCategory
primary_sector
```

解释方式：

```text
financial_core_score = disclosed financial scale
financial_conservative_score = disclosure-adjusted conservative financial scale
field count = confidence / completeness
evidence tier = financial evidence strength
```

这样模型可以同时学习：

- 公司财务规模；
- 数据披露完整度；
- score 的可信度；
- account category 带来的系统性差异；
- sector 带来的资产结构差异。

## 13. 当前结论

当前阶段采用：

```text
financial_core_score
```

作为主 financial proxy score。

同时生成：

```text
financial_conservative_score
```

作为 sensitivity check。

保留：

```text
financial_scale_score = financial_core_score
```

作为旧输出兼容字段。

推荐报告表述：

```text
Missing financial fields were not treated as true zero values because absence of disclosure does not imply zero financial activity. We therefore constructed two financial proxy scores: an available-field core score and a conservative fixed-denominator score. The former captures disclosed financial scale, while the latter provides a sensitivity check for disclosure sparsity. Field counts and evidence tiers were retained as data completeness and confidence indicators.
```
