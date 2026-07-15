# Account Category 赋分思路：基于 Usable Financial Evidence 的 WoE

## 1. 结论定位

`Accounts_AccountCategory` 不应该被解释为“好公司 / 差公司”标签。

它更适合被解释为：

```text
公开财务数据可用性标签
financial disclosure regime variable
usable financial evidence indicator
```

因此，account category 的赋分目标不是判断公司质量，而是衡量：

```text
某类 accounts 有多大概率提供可用于后续财务分析和建模的证据。
```

本项目中建议只计算一套分数：

```text
Usable Financial Evidence WoE Score
```

不单独计算 turnover-only WoE。

## 2. 为什么只算 usable WoE

如果只把 `T1_observed_turnover` 定义为 good，会导致 `TOTAL EXEMPTION FULL`、`SMALL`、`UNAUDITED ABRIDGED` 等类别被严重低估。

但在现有解析结果中，这些类别虽然很少披露 turnover，却通常具有较丰富的 balance sheet 信息，可以进入 `T2_balance_sheet_rich`。

例如 company-level latest candidate 结果显示：

| Account Category | T1 | T2 | T3 | T4 | 主要含义 |
|---|---:|---:|---:|---:|---|
| MEDIUM | 1,912 | 111 | 15 | 0 | 几乎都能获得 turnover，证据强 |
| FULL | 2,746 | 3,796 | 164 | 253 | turnover 和 balance sheet 都较有价值 |
| GROUP | 323 | 2,804 | 50 | 2 | 多数是 balance-sheet-rich，结构较复杂 |
| TOTAL EXEMPTION FULL | 114 | 13,713 | 112 | 90 | turnover 很少，但 T2 极强 |
| UNAUDITED ABRIDGED | 0 | 1,445 | 2 | 15 | turnover 缺失，但多数可作为 T2 proxy |
| SMALL | 23 | 659 | 14 | 2 | turnover 少，但 balance sheet proxy 可用 |

所以，如果目标是后续财务分析、proxy 建模和 evidence confidence，应该把 T1 和 T2 都视为 usable evidence。

## 3. Good / Bad 定义

本项目建议定义：

```text
good = usable financial evidence
     = T1_observed_turnover OR T2_balance_sheet_rich

bad = weak financial evidence
    = T3_balance_sheet_partial OR T4_account_category_only
```

对应到字段：

```text
good:
  financial_evidence_tier in [
    "T1_observed_turnover",
    "T2_balance_sheet_rich"
  ]

bad:
  financial_evidence_tier in [
    "T3_balance_sheet_partial",
    "T4_account_category_only"
  ]
```

这个定义的含义是：

```text
只要该公司能够提供 observed turnover 或丰富的 balance sheet proxy，
就认为它对后续财务建模是可用的。
```

## 4. WoE 计算公式

对每个 account category `c`，计算：

```text
good_c = category c 中 T1 + T2 的公司数
bad_c  = category c 中 T3 + T4 的公司数

Good_total = 全部 category 中 good 公司数
Bad_total  = 全部 category 中 bad 公司数
K = account category 数量
```

为了避免某些 category 的 bad 数量为 0 或样本过小导致 WoE 无穷大，建议使用平滑。

推荐使用 Jeffreys smoothing：

```text
alpha = 0.5
```

平滑后的 WoE：

```text
WoE_c =
ln(
  ((good_c + alpha) / (Good_total + alpha * K))
  /
  ((bad_c + alpha) / (Bad_total + alpha * K))
)
```

解释：

```text
WoE_c > 0:
  该 category 比平均水平更容易产生 usable financial evidence

WoE_c < 0:
  该 category 比平均水平更容易落入 weak evidence

WoE_c 越高:
  该 category 对后续财务解析和建模越有利
```

## 5. 转换为 0-100 分

为了方便业务解释，可以把 WoE 转成 0-100 分：

```text
category_score_0_100 =
100 * (WoE_c - min(WoE)) / (max(WoE) - min(WoE))
```

这个分数的含义是：

```text
account category 对 usable financial evidence 的经验支持度。
```

注意：

```text
高分不等于公司更好；
高分只表示该类 accounts 更可能提供可用财务证据。
```

## 6. 小样本 category 的处理

当前数据中有些 account category 样本很少，例如：

```text
AUDITED ABRIDGED: 16
AUDIT EXEMPTION SUBSIDIARY: 15
```

这类 category 的 WoE 不稳定，建议采用以下规则：

```text
如果 category 样本数 < 100:
  合并为 "OTHER_SMALL_CATEGORY"
  或者保留原值但标记 low_support
```

推荐在正式输出中增加：

```text
category_sample_size
category_support_flag
```

例如：

```text
high_support: n >= 500
medium_support: 100 <= n < 500
low_support: n < 100
```

## 7. 当前结果的初步判断

基于 company-level latest candidate 表，`Accounts_AccountCategory` 和 `financial_evidence_tier` 有明显关系。

当前交叉表显示：

```text
MEDIUM:
  T1 + T2 = 99.27%

FULL:
  T1 + T2 = 94.01%

GROUP:
  T1 + T2 = 98.36%

TOTAL EXEMPTION FULL:
  T1 + T2 = 98.56%

UNAUDITED ABRIDGED:
  T1 + T2 = 98.84%

SMALL:
  T1 + T2 = 97.71%
```

这说明，如果只看 usable evidence，很多 category 都是可用的。

更细的区别不在于“是否可用”，而在于：

```text
MEDIUM / FULL:
  更可能提供 observed turnover，证据强度更高

TOTAL EXEMPTION FULL / SMALL / UNAUDITED ABRIDGED:
  turnover 少，但 balance sheet proxy 丰富，适合 T2 proxy 建模

GROUP:
  usable evidence 高，但集团 accounts 结构复杂，解释时要谨慎
```

因此，usable WoE 适合回答：

```text
这个 category 是否值得进入财务分析流程？
```

但不适合单独回答：

```text
这个 category 是否能提供 turnover？
这个公司是否更优质？
这个公司是否更需要融资？
```

## 8. 在项目中的使用方式

### 8.1 数据分析阶段

可用于解释不同 account category 下的数据可用性差异：

```text
availability_by_account_category
missingness_by_account_category
evidence_tier_distribution_by_account_category
```

核心结论可以写成：

```text
Account category is strongly associated with financial evidence availability.
This confirms that missing turnover is structurally related to filing regime,
rather than being random missingness.
```

### 8.2 模型阶段

可以作为模型特征之一：

```text
account_category_usable_woe
account_category_support_flag
financial_evidence_tier
financial_core_score
financial_conservative_score
```

它帮助模型理解：

```text
同样缺失 turnover，在不同 account category 下含义不同。
```

例如：

```text
MICRO ENTITY 或 TOTAL EXEMPTION FULL 缺失 turnover 是正常披露规则；
FULL 或 MEDIUM 缺失 turnover 可能更值得检查。
```

### 8.3 结果解释阶段

可以用于最终 company-level 输出中的 evidence confidence：

```text
Company A:
  segment = SME
  evidence_confidence = high
  reason = T1 observed turnover from FULL accounts

Company B:
  segment = likely_BB
  evidence_confidence = medium
  reason = T2 balance-sheet-rich TOTAL EXEMPTION FULL accounts

Company C:
  segment = unknown
  evidence_confidence = low
  reason = weak financial evidence
```

## 9. 推荐报告表述

英文表述：

```text
We derive an account-category score using Weight of Evidence based on usable financial evidence.
The target is defined as whether a company has either observed turnover or balance-sheet-rich evidence.
This score is not intended to measure company quality or financing need directly.
Instead, it captures the empirical likelihood that a filing category provides sufficient public financial evidence for downstream analysis.
Rare categories are grouped or smoothed to avoid unstable estimates.
```

中文表述：

```text
我们使用 WoE 方法为 account category 构造经验分数。
其中 good 被定义为公司具有可用财务证据，即进入 T1 observed turnover 或 T2 balance-sheet-rich。
该分数不是公司好坏评分，也不是融资需求评分，而是衡量不同 accounts 类型产生可用公开财务证据的概率。
对于样本量较小的 category，我们进行合并或平滑处理，以避免分数不稳定。
```

## 10. 最终结论

`Accounts_AccountCategory` 赋分是可行的，但必须明确：

```text
分数含义 = usable financial evidence likelihood
不是 company quality
不是 creditworthiness
不是 financing need
```

本项目建议采用：

```text
good = T1_observed_turnover OR T2_balance_sheet_rich
bad = T3_balance_sheet_partial OR T4_account_category_only
method = WoE with smoothing
output = account_category_usable_woe + 0-100 normalised score
```

该分数可以用于：

```text
1. 数据可用性分析
2. missingness 机制解释
3. downstream model feature
4. evidence confidence 解释
5. candidate pool 数据质量控制
```
