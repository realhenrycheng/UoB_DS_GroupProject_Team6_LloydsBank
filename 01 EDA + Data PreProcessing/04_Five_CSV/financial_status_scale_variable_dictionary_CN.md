# 财务状态表与财务规模表变量字典

## 1. 文档目的

本文档解释以下两张公司级财务表中的全部变量：

- `01_financial_status_labels_100k.csv`
- `02_financial_scale_labels_100k.csv`

两张表均为“一家公司一行”，各有 100,000 行，使用 `CompanyNumber_norm` 作为连接键。它们描述的是每家公司最新 account period 的财务快照，不是历史 best-evidence period。

需要特别区分：

- **原始公司字段**：来自 Companies House 公司母表，或由母表字段在上游阶段完成标准化。
- **财务事实字段**：从 Accounts Monthly Bulk 中的 iXBRL/XBRL 财务标签抽取。CSV 中保存的是经过数值解析、单位缩放、正负号处理和同名事实筛选后的标准化数值，不是未经处理的原始文本。
- **构建字段**：通过日期选择、缺失判断、公式、绝对值、分位数或规则生成。
- **经验分位标签**：表示公司在同类样本中的相对位置，不是通用会计标准，也不等于 Lloyds 的 BB/SME/Mid Corporate 正式分层。

## 2. 数据构建流程

### 2.1 财务事实抽取

财务来源为 2024 年 7 月至 2026 年 6 月的 24 个 Companies House Accounts Monthly Bulk ZIP。

处理步骤如下：

1. 从 Accounts 文件名解析公司编号和 account period end。
2. 从 iXBRL/XBRL 标签中识别目标财务事实。
3. 去除金额中的逗号和货币符号，处理括号负数、`sign` 和 `scale` 属性。
4. 同一指标存在多个事实时，优先选择 period 与文件 period 一致、维度较少的事实。
5. 同一公司同一 period 有多个文件时，优先保留证据等级更高、可获得日期更新的文件。
6. 每家公司选择 period end 最新的一期，形成两张 100,000 行的公司级快照。
7. 没有匹配 Accounts 的公司仍保留在表中，但财务字段和相关标签为空。

### 2.2 `creditors_total` 的特殊处理

`creditors_total` 是一个“标准化抽取/补算字段”：

- 优先从 `Creditors` 或 `TotalCreditors` 标签直接抽取；
- 如果没有总额标签，但存在一年内和一年以上 creditors，则构建为：

```text
creditors_total
= creditors_within_one_year
+ creditors_after_one_year
```

因此，该字段不一定严格等同于 current liabilities。所有以它为分母或分子的指标都应理解为 creditors proxy。

### 2.3 Evidence tier

`financial_evidence_tier` 是构建字段，不是 Companies House 原始标签。使用以下 7 个 core proxy fields 计算可用字段数：

```text
current_assets
net_assets_liabilities
equity
creditors_total
employees
cash
debtors
```

规则为：

```text
T1_observed_turnover:
    turnover 可获得

T2_balance_sheet_rich:
    turnover 缺失，core fields 可用数 >= 4

T3_balance_sheet_partial:
    turnover 缺失，core fields 可用数为 2–3

T4_account_category_only:
    turnover 缺失，core fields 可用数 < 2
```

虽然 turnover 没有出现在这两张输出表中，但它参与了 evidence tier 的构建。

## 3. 两张表共有的基础字段

| 变量 | 类型 | 来源/构建方法 | 含义与使用说明 |
|---|---|---|---|
| `CompanyNumber_norm` | 构建的标识字段 | 对母表 `CompanyNumber` 去除非字母数字字符、转大写，并对纯数字公司编号补足 8 位 | 两表的唯一公司连接键。应按字符串读取，不能当作数值。 |
| `CompanyName` | 原始公司字段 | 来自公司母表 | Companies House 公司名称。 |
| `primary_sector` | 上游构建字段 | 根据公司 SIC code 映射到项目定义的八个行业，并选择 primary sector | 用于行业比较和分位阈值分组；不是 Companies House 原生行业字段。 |
| `Accounts_AccountCategory` | 原始公司字段 | 来自公司母表的 Accounts category | 如 `MICRO ENTITY`、`TOTAL EXEMPTION FULL`、`FULL`、`MEDIUM` 等。用于分组和解释数据披露差异。 |
| `latest_period_end` | 构建的时间字段 | 从 Accounts 文件名解析 `period_end`，再选择每家公司最新 period | 表中财务快照对应的会计期末。空值表示没有匹配 Accounts。 |
| `latest_available_date` | 构建的可获得日期 | 根据来源 Monthly Bulk ZIP 的月份，取该月月末 | 近似表示该 Accounts 文件进入项目数据集的时间，不是精确法定 filing timestamp。时间模型应优先使用它控制信息可见性。 |
| `financial_evidence_tier` | 构建的质量字段 | 按 turnover 和 7 个 core proxy fields 的可用数量生成 T1–T4 | 用于样本过滤、置信度和分层分析，不是公司规模或融资需求标签。 |

## 4. 表一：`01_financial_status_labels_100k.csv`

### 4.1 表的作用

该表共有 63 个字段，描述公司最新期间的：

- 原始/标准化财务事实；
- 当前财务状态；
- 财务比率 proxy；
- 行业和 account category 组内的 Low/Medium/High 相对位置。

状态字段通常用于公司画像、模型 feature 或预测结果 reason code。它们不是“未来融资需求”的直接 target。

### 4.2 直接抽取的财务事实字段

下列字段均从 Accounts iXBRL/XBRL 中抽取并标准化为数值。金额单位沿用报告中的数值，经 XBRL `scale` 处理后通常可理解为英镑；`employees` 为人数。

| 变量 | 类型 | 识别的主要 Accounts 标签 | 含义 |
|---|---|---|---|
| `cash` | 财务事实 | `CashBankOnHand`、`CashAndCashEquivalents`、`CashAtBankAndInHand` | 现金及现金等价物 proxy。 |
| `creditors_total` | 财务事实/可能补算 | `Creditors`、`TotalCreditors`；缺失时可能由一年内与一年以上 creditors 相加 | 披露的债权人金额 proxy，不保证等同于 current liabilities。 |
| `current_assets` | 财务事实 | `CurrentAssets` | 流动资产。 |
| `debtors` | 财务事实 | `Debtors`、`DebtorsAmountsFallingDueWithinOneYear` | 应收款项 proxy。不同公司可能采用不同披露口径。 |
| `employees` | 财务事实 | `AverageNumberEmployeesDuringPeriod`、`AverageNumberOfEmployeesDuringPeriod`、`EmployeesTotal` | 平均员工数或披露员工数。应检查异常小数和负数。 |
| `equity` | 财务事实 | `Equity`、`ShareholderFunds`、`CapitalAndReserves` | 权益/股东资金 proxy。允许为负。 |
| `fixed_assets` | 财务事实 | `FixedAssets` | 固定资产。 |
| `net_assets_liabilities` | 财务事实 | `NetAssetsLiabilities`、`NetAssets` | 净资产或净负债。允许为负。 |
| `net_current_assets_liabilities` | 财务事实 | `NetCurrentAssetsLiabilities` | 净流动资产/负债。允许为负。 |
| `profit_loss` | 财务事实 | `ProfitLoss`、`ProfitLossBeforeTax`、`OperatingProfitLoss` | 报告利润或亏损 proxy。不同标签的会计口径可能不同，因此只适合作为辅助信号。 |
| `total_assets_less_current_liabilities` | 财务事实 | `TotalAssetsLessCurrentLiabilities` | 总资产减流动负债。允许为负。 |

### 4.3 当前状态标签

`eligible` 表示构建该状态所需的原始字段是否可用。只有 `eligible = TRUE` 时，相应 flag 的 TRUE/FALSE 才有意义；缺失不能改填为 FALSE。

| 变量 | 类型 | 构建规则 | 含义 |
|---|---|---|---|
| `negative_equity_eligible` | 构建字段 | `equity` 非空 | 是否可以判断负权益状态。当前有效公司为 91,479 家。 |
| `negative_equity_flag` | 构建标签 | 在 eligible 样本中，`equity < 0` | TRUE 表示负权益。当前为 17,170 家，占 eligible 样本 18.77%。 |
| `positive_equity_flag` | 构建标签 | 在 eligible 样本中，`equity > 0` | TRUE 表示正权益。注意 `equity = 0` 时，负权益和正权益两个 flag 都为 FALSE。 |
| `working_capital_deficit_eligible` | 构建字段 | `net_current_assets_liabilities` 非空 | 是否可以判断营运资金缺口。当前有效公司为 89,721 家。 |
| `working_capital_deficit_flag` | 构建标签 | 在 eligible 样本中，`net_current_assets_liabilities < 0` | TRUE 表示净流动资产为负，是短期流动性压力 proxy。当前为 27,349 家，占 eligible 样本 30.48%。 |
| `reported_loss_eligible` | 构建字段 | `profit_loss` 非空 | 是否可以判断报告亏损。当前仅 4,655 家有效。 |
| `reported_loss_flag` | 构建标签 | 在 eligible 样本中，`profit_loss < 0` | TRUE 表示报告亏损。当前为 1,343 家，占 eligible 样本 28.85%；因覆盖率低，只建议作为辅助信号。 |
| `creditors_cover_eligible` | 构建字段 | `current_assets` 和 `creditors_total` 均非空，且两者均大于等于 0 | 是否可以比较流动资产和 creditors。当前有效公司为 79,599 家。 |
| `creditors_exceed_current_assets_flag` | 构建标签 | 在 eligible 样本中，`creditors_total > current_assets` | TRUE 表示 creditors 超过流动资产，是债权人压力 proxy。当前为 30,191 家。 |
| `current_assets_cover_creditors_flag` | 构建标签 | 在 eligible 样本中，`current_assets >= creditors_total` | 与上一字段互补；在 eligible 样本中包含两者相等的情况。 |

### 4.4 构建的财务比率

代码先构建：

```text
disclosed_assets = current_assets + fixed_assets
```

只有相关分子、分母满足要求时才计算比率，否则为空。

| 变量 | 类型 | 公式和有效条件 | 含义 |
|---|---|---|---|
| `cash_to_creditors_ratio` | 构建比率 | `cash / creditors_total`；要求 cash 非空且 `creditors_total > 0` | 现金相对 creditors 的覆盖程度。因 creditors 口径限制，应称为 cash coverage proxy。 |
| `fixed_assets_to_disclosed_assets_ratio` | 构建比率 | `fixed_assets / (current_assets + fixed_assets)`；要求 current/fixed assets 均非空且合计大于 0 | 已披露资产中的固定资产占比，即资产密集度 proxy。 |
| `debtors_to_current_assets_ratio` | 构建比率 | `debtors / current_assets`；要求 debtors 非空且 `current_assets > 0` | 流动资产中的应收款项占比，即 receivables intensity proxy。 |
| `creditors_to_disclosed_assets_ratio` | 构建比率 | `creditors_total / (current_assets + fixed_assets)`；要求 creditors 非空且 disclosed assets 大于 0 | creditors 相对已披露资产的强度 proxy。 |
| `employees_per_million_disclosed_assets` | 构建比率 | `employees / ((current_assets + fixed_assets) / 1,000,000)`；要求 `employees >= 0` 且 disclosed assets 大于 0 | 每百万已披露资产对应的员工数，即 employee intensity proxy。极小资产可能造成极端值。 |

### 4.5 Low/Medium/High 分位标签的统一规则

表一的五组 ratio band 均使用比率原值计算阈值，不做 signed-log 变换。

阈值优先级：

1. `primary_sector + Accounts_AccountCategory` 组内阈值；
2. 如果该组 eligible 数量少于 30，或 30%/70% 阈值相同，则回退到 `primary_sector`；
3. 如果行业层面仍不满足要求，则回退到全体 eligible 样本。

分带规则：

```text
value <= 30%分位阈值        -> Low
30%分位阈值 < value < 70%分位阈值 -> Medium
value >= 70%分位阈值        -> High
```

每组标签均包含以下六类字段：

| 后缀 | 类型 | 统一含义 |
|---|---|---|
| `*_eligible` | 构建字段 | 生成该 ratio/band 所需的值是否有效。 |
| `*_band` | 构建标签 | `Low`、`Medium`、`High`；为空表示不 eligible 或无法形成有效阈值。 |
| `*_threshold_scope` | 构建审计字段 | 实际使用的阈值范围：`sector_account_category`、`sector` 或 `global`。 |
| `*_threshold_n` | 构建审计字段 | 计算该公司所用阈值的 eligible 参考样本数。 |
| `*_low_threshold` | 构建审计字段 | 所用参考组的 30% 分位阈值，单位与对应 ratio 相同。 |
| `*_high_threshold` | 构建审计字段 | 所用参考组的 70% 分位阈值，单位与对应 ratio 相同。 |

### 4.6 五组状态分位字段

下表明确列出表一剩余全部字段。

| 前缀 | 输入变量 | 该前缀包含的全部字段 | 解释 |
|---|---|---|---|
| `cash_coverage` | `cash_to_creditors_ratio` | `cash_coverage_eligible`、`cash_coverage_band`、`cash_coverage_threshold_scope`、`cash_coverage_threshold_n`、`cash_coverage_low_threshold`、`cash_coverage_high_threshold` | 公司 cash coverage proxy 在相似行业/account category 公司中的相对位置。Low 表示相对较低，High 表示相对较高；不直接等同于“风险高/低”。 |
| `asset_intensity` | `fixed_assets_to_disclosed_assets_ratio` | `asset_intensity_eligible`、`asset_intensity_band`、`asset_intensity_threshold_scope`、`asset_intensity_threshold_n`、`asset_intensity_low_threshold`、`asset_intensity_high_threshold` | 固定资产占已披露资产比例的相对位置。High 通常表示更资产密集。 |
| `receivables_intensity` | `debtors_to_current_assets_ratio` | `receivables_intensity_eligible`、`receivables_intensity_band`、`receivables_intensity_threshold_scope`、`receivables_intensity_threshold_n`、`receivables_intensity_low_threshold`、`receivables_intensity_high_threshold` | 应收款项占流动资产比例的相对位置。High 表示流动资产中 debtors 占比较高。 |
| `creditor_intensity` | `creditors_to_disclosed_assets_ratio` | `creditor_intensity_eligible`、`creditor_intensity_band`、`creditor_intensity_threshold_scope`、`creditor_intensity_threshold_n`、`creditor_intensity_low_threshold`、`creditor_intensity_high_threshold` | creditors 相对 disclosed assets 的相对强度。High 仅表示相对较高，不自动等于财务困境。 |
| `employee_intensity` | `employees_per_million_disclosed_assets` | `employee_intensity_eligible`、`employee_intensity_band`、`employee_intensity_threshold_scope`、`employee_intensity_threshold_n`、`employee_intensity_low_threshold`、`employee_intensity_high_threshold` | 每百万 disclosed assets 员工数的相对位置。High 通常表示劳动密集度相对较高。 |

## 5. 表二：`02_financial_scale_labels_100k.csv`

### 5.1 表的作用

该表共有 58 个字段。它分别为七个财务规模指标建立 Low/Medium/High 分带，用于：

- turnover 缺失公司规模的 proxy；
- 三分类模型的候选特征；
- 行业和 account category 内部的相对规模比较；
- 模型解释和敏感性分析。

该表没有把七个指标手工加权为一个总分，也不能替代 observed turnover 生成的 BB/SME/Mid Corporate 正式标签。

### 5.2 直接抽取/标准化的规模输入字段

以下字段的抽取含义与表一相同：

| 变量 | 类型 | 含义 |
|---|---|---|
| `current_assets` | 财务事实 | 流动资产。 |
| `fixed_assets` | 财务事实 | 固定资产。 |
| `creditors_total` | 财务事实/可能补算 | 披露 creditors 总额 proxy。 |
| `equity` | 财务事实 | 权益/股东资金 proxy，允许为负。 |
| `employees` | 财务事实 | 平均或披露员工数。 |
| `net_assets_liabilities` | 财务事实 | 净资产/净负债，允许为负。 |
| `total_assets_less_current_liabilities` | 财务事实 | 总资产减流动负债，允许为负。 |
| `abs_equity_for_scale` | 构建字段 | `abs(equity)` | 权益绝对值，只用于衡量 balance-sheet magnitude。负权益公司不会因为符号为负而自动被放入 Low，但方向信息必须从 `equity` 或 `negative_equity_flag` 获取。 |

### 5.3 Signed-log 规模变换

七个规模输入在计算分位阈值前先做：

```text
signed_log1p(x) = sign(x) * ln(1 + abs(x))
```

目的：

- 缩小财务金额的长尾和极端值影响；
- 保留 `net_assets_liabilities`、`total_assets_less_current_liabilities` 等字段的正负方向；
- 让分位比较更加稳定。

需要特别注意：

- `*_scale_low_threshold` 和 `*_scale_high_threshold` 保存的是 **signed-log 变换后的阈值**，不是英镑原值。
- 若需要把正阈值还原为原尺度，可使用 `exp(threshold) - 1`。
- 对负阈值应使用 `- (exp(abs(threshold)) - 1)`。
- Low/Medium/High 仍然只是参考组中的相对位置，不是绝对规模标准。

### 5.4 Scale 分位字段的统一后缀

七组 scale label 均包含：

| 后缀 | 类型 | 统一含义 |
|---|---|---|
| `*_eligible` | 构建字段 | 原始值是否存在并满足该指标的有效性要求。 |
| `*_band` | 构建标签 | signed-log 值相对 30%/70% 阈值的 `Low`、`Medium` 或 `High`。 |
| `*_threshold_scope` | 构建审计字段 | `sector_account_category`、`sector` 或 `global`。 |
| `*_threshold_n` | 构建审计字段 | 实际参考组的 eligible 样本数。 |
| `*_low_threshold` | 构建审计字段 | signed-log 尺度上的 30% 分位阈值。 |
| `*_high_threshold` | 构建审计字段 | signed-log 尺度上的 70% 分位阈值。 |

分组回退和 Low/Medium/High 边界规则与表一完全相同。

### 5.5 七组规模变量

| 前缀 | 输入值及 eligible 条件 | 该前缀包含的全部字段 | 解释 |
|---|---|---|---|
| `current_assets_scale` | `current_assets` 非空且大于等于 0 | `current_assets_scale_eligible`、`current_assets_scale_band`、`current_assets_scale_threshold_scope`、`current_assets_scale_threshold_n`、`current_assets_scale_low_threshold`、`current_assets_scale_high_threshold` | 流动资产规模的相对分带。 |
| `fixed_assets_scale` | `fixed_assets` 非空且大于等于 0 | `fixed_assets_scale_eligible`、`fixed_assets_scale_band`、`fixed_assets_scale_threshold_scope`、`fixed_assets_scale_threshold_n`、`fixed_assets_scale_low_threshold`、`fixed_assets_scale_high_threshold` | 固定资产规模的相对分带。 |
| `creditors_scale` | `creditors_total` 非空且大于等于 0 | `creditors_scale_eligible`、`creditors_scale_band`、`creditors_scale_threshold_scope`、`creditors_scale_threshold_n`、`creditors_scale_low_threshold`、`creditors_scale_high_threshold` | creditors 金额规模 proxy 的相对分带；不是严格的负债规模评级。 |
| `absolute_equity_scale` | `abs_equity_for_scale` 非空且大于等于 0 | `absolute_equity_scale_eligible`、`absolute_equity_scale_band`、`absolute_equity_scale_threshold_scope`、`absolute_equity_scale_threshold_n`、`absolute_equity_scale_low_threshold`、`absolute_equity_scale_high_threshold` | 权益绝对规模的相对分带。必须与 equity 正负方向字段一起解释。 |
| `employee_scale` | `employees` 非空且大于等于 0 | `employee_scale_eligible`、`employee_scale_band`、`employee_scale_threshold_scope`、`employee_scale_threshold_n`、`employee_scale_low_threshold`、`employee_scale_high_threshold` | 员工人数规模的相对分带。大量相同员工数可能导致 sector/account category 阈值重合，因此较多公司会回退到 sector 阈值。 |
| `net_assets_scale` | `net_assets_liabilities` 非空；允许负数 | `net_assets_scale_eligible`、`net_assets_scale_band`、`net_assets_scale_threshold_scope`、`net_assets_scale_threshold_n`、`net_assets_scale_low_threshold`、`net_assets_scale_high_threshold` | 净资产/净负债 signed magnitude 的相对分带。负值通常位于较低分带，但该字段同时混合方向和规模，应结合负权益状态解释。 |
| `total_assets_scale` | `total_assets_less_current_liabilities` 非空；允许负数 | `total_assets_scale_eligible`、`total_assets_scale_band`、`total_assets_scale_threshold_scope`、`total_assets_scale_threshold_n`、`total_assets_scale_low_threshold`、`total_assets_scale_high_threshold` | 总资产减流动负债的相对规模分带。 |

| 变量 | 类型 | 构建规则 | 含义 |
|---|---|---|---|
| `financial_scale_available_field_count` | 构建的完整度字段 | 七个 `*_scale_eligible` 的 TRUE 数量之和，范围 0–7 | 表示该公司可用于规模判断的指标数量。它不是规模分数；数值高只表示信息更完整。 |

## 6. 如何正确读取空值和布尔值

### 6.1 `eligible = FALSE`

表示构建该标签所需的财务事实缺失或不满足有效条件。对应的 flag、band 和 threshold 为空是预期行为。

错误做法：

```text
将空 flag 填为 FALSE
```

这样会把“未知”误写成“状态没有发生”。

正确做法：

```text
先用 *_eligible 过滤
或在模型中同时保留 eligible/missing indicator
```

### 6.2 Band 的解释

`Low`、`Medium`、`High` 表示相对于参考组的经验分位：

- 不代表好、一般、坏；
- 不代表低风险、中风险、高风险；
- 不直接等于 BB、SME、Mid Corporate；
- 不同 sector/account category 使用的阈值可能不同。

### 6.3 Threshold scope

| 值 | 含义 |
|---|---|
| `sector_account_category` | 使用相同行业和相同 account category 的参考组。 |
| `sector` | 细分组样本不足或阈值重合，回退到相同行业。 |
| `global` | 行业层面也不能形成有效阈值，回退到全部 eligible 公司。 |
| 空值 | 该公司不 eligible，未分配阈值。 |

## 7. 建模角色建议

| 字段类型 | 建议角色 |
|---|---|
| 直接抽取的财务事实 | 模型原始数值 feature；建议使用 signed-log、缺失标记和异常值控制。 |
| 当前状态 flag | 当前画像 feature、reason code 或风险控制变量。 |
| Ratio | 连续 feature；保留原值通常比只使用 band 信息更多。 |
| Low/Medium/High band | 非线性/分组 feature、解释字段和稳健性分析字段。 |
| `*_threshold_*` | 审计和复现字段，通常不应直接作为模型 feature，否则可能把 group size 或阈值选择机制泄漏给模型。 |
| `financial_evidence_tier` | 数据质量/control/confidence 字段；可用于分层训练或结果置信度。 |
| `financial_scale_available_field_count` | 数据完整度 feature/control，不是公司规模本身。 |

正式三分类 target 仍应由 observed turnover 构建：

```text
BB: turnover < £3m
SME: £3m <= turnover < £25m
Mid Corporate: £25m <= turnover < £500m
```

本文件中的状态和规模标签不能替代 observed turnover target。

## 8. 关键限制

1. Accounts 主要是年度披露，最新财务状态不等于未来 4–6 个月的融资需求。
2. `latest_available_date` 是 Monthly Bulk 月末近似值，不是精确 filing date。
3. 不同 XBRL 标签可能具有不同会计口径，尤其是 `profit_loss`、`debtors`、`equity` 和 `creditors_total`。
4. `creditors_total` 相关 ratio 是 proxy，不应称为严格的 current ratio 或 current-liability ratio。
5. 分位阈值由当前 100,000 家公司样本估计。应用到新批次公司时，应固定训练期阈值，不能用测试集或未来数据重新计算。
6. 时间预测必须按 `latest_available_date` 或更精确的 filing date 切分，不能把未来 filing 用于过去 snapshot。

## 9. 生成依据

两张表及其规则来自：

```text
generate_financial_five_tables.ipynb
```

现有总览文件：

```text
financial_five_tables_guide_CN.md
```

本文档在总览基础上补充了两张表全部字段的来源、公式、分位规则和建模角色。
