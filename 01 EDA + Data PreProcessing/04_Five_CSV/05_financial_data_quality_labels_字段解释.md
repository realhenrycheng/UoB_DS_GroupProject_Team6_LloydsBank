# 表 5：`05_financial_data_quality_labels_100k.csv` 字段解释

## 1. 这张表回答什么问题

表 5 以 29 个字段记录 10 万家公司在当前财务快照下的数据可得性、证据强度、历史覆盖、时效性和异常情况。它用于过滤、样本加权、置信度控制、敏感性分析和数据质量监控，不是财务健康评分或商业机会标签。

- 行粒度：一家公司一行，固定 100,000 行。
- 唯一键：`CompanyNumber_norm`。
- 当前快照：每家公司已匹配到的最新 `period_end`，不是历史上证据最丰富的期间。
- 快照基准日：`2026-06-30`。
- 未匹配公司：仍保留在表中；日期、等级和计数字段可能为空，但部分布尔覆盖标记会是 False。

## 2. 公司与最新期间字段

| 字段 | 类型/取值 | 解释 | 使用注意事项 |
|---|---|---|---|
| `CompanyNumber_norm` | 字符串 | 标准化 Companies House 公司编号。 | 按字符串读取，保留前导零；用于连接其他公司级表。 |
| `CompanyName` | 字符串 | 公司名称。 | 展示字段。 |
| `primary_sector` | 类别 | 公司主行业。 | 可用于分行业质量覆盖分析。 |
| `Accounts_AccountCategory` | 类别 | Companies House 账户类别。 | 微型/小型账户的披露字段通常更少，分析质量差异时应控制该字段。 |
| `latest_period_end` | 日期 | 最新匹配会计期间的期末日。 | 不是提交日；无任何匹配账目时为空。 |
| `latest_available_date` | 日期 | 最新选中报表所在 Companies House 月度 ZIP 的月末日。 | 是近似可用日，不是精确 filing timestamp；无匹配时为空。 |

同一公司同一期间可能在多个月度 ZIP 中出现。去重时优先证据等级更强的记录；等级相同时选择 `available_date` 更晚的记录。

## 3. 证据等级与最新期字段覆盖

| 字段 | 类型/取值 | 解释 | 精确定义 |
|---|---|---|---|
| `financial_evidence_tier` | `T1`—`T4` 或空白 | 最新期的财务证据等级。 | 按下表规则分级；没有匹配到账目时为空，而不是 T4。 |
| `available_core_proxy_field_count` | 0—7 或空白 | 最新期 7 个核心代理字段中非空的数量。 | 核心字段：`current_assets`、`net_assets_liabilities`、`equity`、`creditors_total`、`employees`、`cash`、`debtors`。无匹配时为空。 |
| `available_any_financial_field_count` | 0—12 或空白 | 最新期全部候选财务字段中非空的数量。 | 7 个核心字段，再加 `turnover`、`fixed_assets`、`profit_loss`、`creditors_within_one_year`、`creditors_after_one_year`。无匹配时为空。 |

证据等级的构造顺序如下：

| 等级 | 精确定义 | 建议解读 |
|---|---|---|
| `T1_observed_turnover` | 最新期 `turnover` 非空。 | 最强：有直接营业额证据。T1 不要求核心代理字段完整。 |
| `T2_balance_sheet_rich` | turnover 为空，且核心代理字段数 `>= 4`。 | 资产负债表信息较丰富，可构造多种 proxy。 |
| `T3_balance_sheet_partial` | turnover 为空，且核心代理字段数为 2—3。 | 部分资产负债表信息可用。 |
| `T4_account_category_only` | 已匹配到账目，turnover 为空，且核心代理字段数 `< 2`。 | 财务数值证据很弱，主要依赖账户类别。 |
| 空白 | 没有匹配到该公司的账目。 | 应与“已匹配但披露少”的 T4 区分。 |

等级编号越小证据越强。它衡量的是“可得信息强弱”，不是公司质量、信用或规模。

## 4. 历史期间覆盖字段

| 字段 | 类型 | 解释 | 精确定义/空值语义 |
|---|---|---|---|
| `matched_account_periods` | 非负整数或空白 | 去重后匹配到的不同会计期间数量。 | 按 `period_end` 的唯一值计数；无匹配时为空，不是数值 0。 |
| `useful_financial_periods` | 非负整数或空白 | 具有“有用财务证据”的历史期间数量。 | T1、T2 或 T3 的期间数；T4 不计入。无匹配时为空。 |
| `first_period_end` | 日期或空白 | 已匹配历史中最早的会计期末日。 | 无匹配时为空。 |
| `turnover_periods` | 非负整数或空白 | 成功抽取 turnover 的期间数。 | 无匹配时为空；已匹配但从未抽取到 turnover 时为 0。 |
| `previous_gap_days` | 数值或空白 | 最新期间与它前一条已观测期间之间的天数。 | 直接比较最近两条 `period_end`；只有一个或零个匹配期间时为空。这里未先限定 250—550 天。 |

## 5. 覆盖与完整度布尔标记

| 字段 | 解释 | True 条件 | False/空值语义 |
|---|---|---|---|
| `has_matched_accounts_flag` | 是否至少匹配到一个会计期间。 | `matched_account_periods >= 1`。 | 无匹配时为 False。 |
| `has_two_plus_financial_periods_flag` | 是否有至少两个“有用财务证据”期间。 | `useful_financial_periods >= 2`。 | T4 不计入；缺失计数按 0 处理，因此无匹配时为 False。 |
| `has_two_plus_turnover_periods_flag` | 是否至少两期有 turnover。 | `turnover_periods >= 2`。 | 缺失按 0 处理。适合判断能否构造营业额历史变化。 |
| `has_any_turnover_flag` | 历史任一期是否有 turnover。 | company panel 内至少一条 `turnover` 非空。 | 无匹配或各期均无 turnover 时为 False。 |
| `useful_financial_evidence_flag` | 最新期是否至少达到 T3。 | 最新 `financial_evidence_tier` 属于 T1/T2/T3。 | T4 或无匹配时为 False。 |
| `core_fields_complete_flag` | 最新期 7 个核心代理字段是否全部存在。 | `available_core_proxy_field_count >= 7`。 | 缺失计数按 0 处理；不检查数值是否经济合理。 |

`has_two_plus_financial_periods_flag` 与 `matched_account_periods >= 2` 含义不同：后者可能包括两个 T4 期间，而前者要求至少两个 T1—T3 期间。

## 6. 时效性字段

| 字段 | 类型 | 解释 | 精确定义 |
|---|---|---|---|
| `accounts_age_days_at_snapshot` | 天数或空白 | 截至快照日，最新会计期末距今多少天。 | `2026-06-30 - latest_period_end`。注意它衡量 period end 的年龄，不是 filing/available date 的年龄。 |
| `accounts_older_than_24m_flag` | True/False/空白 | 最新会计期末是否早于快照日超过 24 个月。 | `accounts_age_days_at_snapshot > 730` 为 True；恰好 730 天为 False；没有最新期间时为空。 |

该“24 个月”用固定 730 天实现，不是按日历月回退两年。若业务规则要求精确月份，应另行构造。

## 7. 不可能负值检查

| 字段 | 类型 | 解释 | 精确定义 |
|---|---|---|---|
| `impossible_negative_value_flag` | 布尔 | 最新期是否有本应非负的字段小于 0。 | 检查 `cash`、`current_assets`、`fixed_assets`、`debtors`、`employees`；任一 `< 0` 即 True。 |
| `impossible_negative_fields` | 字符串 | 具体哪些字段出现负值。 | 多个字段用 `|` 连接，如 `cash|employees`；没有时为空字符串。 |

注意：该检查不包括 `equity`、`net_assets_liabilities`、`total_assets_less_current_liabilities`，因为这些字段在经济意义上允许为负；也未检查 `creditors_total`。`impossible_negative_value_flag=False` 只表示没有触发这 5 项规则，不代表数据完全正确。

没有匹配账目的公司会得到 `impossible_negative_value_flag=False`，因为不存在已观测负值；应同时参考 `has_matched_accounts_flag`，不要把 False 理解成“数据已通过全面验证”。

## 8. 极端金额检查

| 字段 | 类型 | 解释 | 精确定义 |
|---|---|---|---|
| `extreme_amount_p999_flag` | 布尔 | 最新期任一指定金额字段的绝对值是否超过全样本第 99.9 百分位阈值。 | 对 8 个字段分别计算 `abs(value)` 的 P99.9；只要任一字段严格大于其阈值即 True。 |
| `extreme_amount_thresholds_json` | JSON 字符串 | 本次生成表时采用的 8 个 P99.9 阈值。 | 同一个阈值字典重复写在每一行，便于追溯；不是公司特有值。 |

参与极端值检查的 8 个字段为：

- `cash`
- `creditors_total`
- `current_assets`
- `debtors`
- `equity`
- `fixed_assets`
- `net_assets_liabilities`
- `total_assets_less_current_liabilities`

当前文件的 JSON 阈值约为：cash 11.13m、creditors 19.78m、current assets 32.60m、debtors 40.27m、equity 29.15m、fixed assets 29.02m、net assets/liabilities 28.53m、total assets less current liabilities 38.16m。实际分析应解析每行 JSON 中的精确值，不要依赖这里的四舍五入数字。

P99.9 标记表示“值得复核”，不表示该值一定错误。大型公司可能真实超过阈值；解析单位、XBRL scale 或标签选择错误也可能造成极端值。

## 9. 期间间隔异常与证据变化

| 字段 | 类型 | 解释 | 精确定义/空值语义 |
|---|---|---|---|
| `latest_period_gap_anomaly_flag` | True/False/空白 | 最近两个已观测会计期的间隔是否偏离年度配对窗口。 | `previous_gap_days` 不在 250—550 天（含边界）时为 True；在范围内为 False；没有前一期时为空。 |
| `evidence_improved_flag` | True/False/空白 | 最新期证据等级是否比前一期增强。 | 等级 rank 为 T1=1、T2=2、T3=3、T4=4；最新 rank 更小为 True，相同或更弱为 False；无前一期为空。 |
| `evidence_deteriorated_flag` | True/False/空白 | 最新期证据等级是否比前一期减弱。 | 最新 rank 更大为 True，相同或更强为 False；无前一期为空。 |

若两个等级相同，`evidence_improved_flag=False` 且 `evidence_deteriorated_flag=False`。这表示等级稳定，并不保证具体可用字段完全相同。

`latest_period_gap_anomaly_flag` 只比较最近两条已观测期末日。它可能反映延长/缩短会计期、漏掉中间报表或匹配覆盖不足，不能直接视为公司经营异常。

## 10. 建模中的推荐角色

| 字段组 | 推荐角色 | 不推荐做法 |
|---|---|---|
| T1—T4、字段计数、覆盖 flags | 样本筛选、置信度、分层评估、缺失机制特征 | 把 T1 当“好公司”、T4 当“坏公司” |
| 账目年龄、期间间隔异常 | 时间新鲜度控制、样本权重、敏感性分析 | 直接当作融资需求或违约标签 |
| 不可能负值、P99.9 极端值 | 质量复核、winsorize 前的异常提示、稳健性分析 | 不经复核就删除所有被标记公司 |
| 证据改善/恶化 | 披露质量变化、数据可用性漂移监控 | 当作财务表现改善/恶化 |

## 11. 推荐的过滤与敏感性分析方案

可以至少保留三套样本口径并比较结果：

1. 宽口径：`has_matched_accounts_flag=True`。
2. 主分析口径：`useful_financial_evidence_flag=True`，即 T1—T3。
3. 高置信度口径：T1/T2，且 `impossible_negative_value_flag=False`、`extreme_amount_p999_flag=False`。

如果任务需要纵向特征，再额外要求 `has_two_plus_financial_periods_flag=True`；如果专门研究营业额变化，则要求 `has_two_plus_turnover_periods_flag=True`。

对被标记的极端值，优先回看原始报表、单位和 XBRL scale，再决定截尾、对数变换或剔除。数据质量字段应作为控制/置信度信息，而不是替代业务 target。

## 12. 连接与空值处理

- 与表 1、表 2 按 `CompanyNumber_norm` 一对一连接。
- 与表 3、表 4 连接时，公司级质量字段代表最新快照，未必代表历史 pair 的 `t` 期质量；若做严格历史回测，应从 panel 重新构造每个历史期间的质量字段。
- 不要对整张表统一 `fillna(0)`：日期、等级、期间计数和三态布尔字段的空白都有具体含义。
- 对 unmatched 公司，`financial_evidence_tier` 为空、若干计数为空，但覆盖 flags 为 False；建模时可显式增加“无匹配”类别。
