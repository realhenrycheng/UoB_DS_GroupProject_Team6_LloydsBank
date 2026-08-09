# 表 4：`04_financial_transition_labels.csv` 字段解释

## 1. 这张表回答什么问题

表 4 把同一家公司从 `t` 到 `t+1` 的财务状态变化编码为“发生（onset）”“恢复（recovery）”和“持续（persistent）”，共 37 个字段。每行是一组相邻年度 company-period pair，共 81,603 行。

- 行粒度：一家公司的一组相邻期间。
- 唯一键：`CompanyNumber_norm + period_t + period_t_plus_1`。
- 配对条件：下一条已观测会计期与当前期相隔 250—550 天（含边界）。
- 状态对象：负权益、营运资金缺口、债权人压力和 reported loss。
- 典型用途：下一会计期风险状态分类目标、迁移矩阵、事件发生率和恢复率分析。

> 最重要的空值规则：每个 `*_flag` 必须和相应的 `*_eligible` 一起使用。空白不是 `False`，而是“不适用或无法判断”。

## 2. 通用标识字段

| 字段 | 类型/取值 | 解释 | 使用注意事项 |
|---|---|---|---|
| `CompanyNumber_norm` | 字符串 | 标准化公司编号。 | 按字符串读取，保留前导零。 |
| `CompanyName` | 字符串 | 公司名称。 | 展示字段。 |
| `primary_sector` | 类别 | 公司主行业。 | 可用于分行业迁移率；本表标签本身不是按行业分位生成的。 |
| `Accounts_AccountCategory` | 类别 | Companies House 账户类别。 | 可作为控制变量，不等同于商业客户分层。 |
| `period_t` | 日期 | 起始会计期末日。 | 财务状态所属日期，不是披露日。 |
| `period_t_plus_1` | 日期 | 下一相邻会计期末日。 | 定义未来状态。 |
| `available_date_t` | 日期 | `t` 期报表所在月度 ZIP 的月末日。 | 时点 `t` 特征必须在该日或之前可用。 |
| `available_date_t_plus_1` | 日期 | `t+1` 期报表所在月度 ZIP 的月末日。 | 状态转移标签最早视为在该日可见。 |
| `gap_days` | 数值 | 两个期末日之间的天数。 | 文件中为 250—550 天，可作时间跨度控制。 |
| `evidence_tier_t` | 类别 | `t` 期证据等级 T1—T4。 | 等级数字越小证据越强。 |
| `evidence_tier_t_plus_1` | 类别 | `t+1` 期证据等级。 | 可控制 target 质量；对时点 `t` 来说属于未来信息。 |

证据等级：T1=观测到 turnover；T2=无 turnover 但 7 个核心代理字段至少 4 个可用；T3=2—3 个可用；T4=少于 2 个可用。

## 3. 标签的统一逻辑

对任一二元不良状态，可用以下迁移表理解：

| `t` 状态 | `t+1` 状态 | onset | recovery | persistent |
|---|---|---:|---:|---:|
| 正常 | 正常 | False | 不适用/空白 | 不适用/空白 |
| 正常 | 不良 | True | 不适用/空白 | 不适用/空白 |
| 不良 | 正常 | 不适用/空白 | True | False |
| 不良 | 不良 | 不适用/空白 | False | True |

其中 onset 的风险集只包含 `t` 期正常的公司；recovery 和 persistent 的风险集只包含 `t` 期已处于不良状态的公司。因此不能用整张表的行数直接计算发生率或恢复率。

## 4. 负权益字段

状态定义：`equity < 0` 为负权益；`equity >= 0` 为非负权益。两期 equity 都非空才可判断。

| 字段 | 解释 | 精确定义 |
|---|---|---|
| `negative_equity_transition_eligible` | 两期负权益状态是否都可判断。 | `equity_t` 和 `equity_t_plus_1` 均非空。 |
| `negative_equity_onset_eligible` | 是否进入“负权益新发生”的风险集。 | transition eligible 且 `equity_t >= 0`。 |
| `negative_equity_recovery_eligible` | 是否进入“负权益恢复”的风险集。 | transition eligible 且 `equity_t < 0`。 |
| `negative_equity_persistent_eligible` | 是否进入“负权益持续”的风险集。 | 与 recovery eligible 相同：transition eligible 且 `equity_t < 0`。 |
| `negative_equity_onset_flag` | 下一期是否新进入负权益。 | 在 onset eligible 样本中，`equity_t_plus_1 < 0` 为 True，否则 False；其他样本为空。 |
| `negative_equity_recovery_flag` | 下一期是否退出负权益。 | 在 recovery eligible 样本中，`equity_t_plus_1 >= 0` 为 True，否则 False；其他样本为空。 |
| `negative_equity_persistent_flag` | 下一期是否仍为负权益。 | 在 persistent eligible 样本中，`equity_t_plus_1 < 0` 为 True，否则 False；其他样本为空。 |

在 eligible 风险集中，`negative_equity_recovery_flag` 与 `negative_equity_persistent_flag` 互为补集。

## 5. 营运资金缺口字段

状态定义：`net_current_assets_liabilities < 0` 为营运资金缺口；`>= 0` 为无缺口。该底层字段是 Companies House 披露的 net current assets/liabilities。

| 字段 | 解释 | 精确定义 |
|---|---|---|
| `working_capital_transition_eligible` | 两期营运资金状态是否可判断。 | 两期 `net_current_assets_liabilities` 均非空。 |
| `working_capital_deficit_onset_eligible` | 是否进入“缺口新发生”风险集。 | transition eligible 且 `t` 期值 `>= 0`。 |
| `working_capital_deficit_recovery_eligible` | 是否进入“缺口恢复”风险集。 | transition eligible 且 `t` 期值 `< 0`。 |
| `working_capital_deficit_persistent_eligible` | 是否进入“缺口持续”风险集。 | 与 recovery eligible 相同。 |
| `working_capital_deficit_onset_flag` | 下一期是否新出现缺口。 | onset eligible 中，`t+1` 期值 `< 0` 为 True。 |
| `working_capital_deficit_recovery_flag` | 下一期是否消除缺口。 | recovery eligible 中，`t+1` 期值 `>= 0` 为 True。 |
| `working_capital_deficit_persistent_flag` | 下一期是否仍有缺口。 | persistent eligible 中，`t+1` 期值 `< 0` 为 True。 |

## 6. 债权人压力字段

状态定义：当 `creditors_total > current_assets` 时认为存在 creditor pressure，即披露的债权人金额代理超过流动资产。这是经验性压力代理，不是严格偿债能力或违约定义；`creditors_total` 也不一定等同于严格会计定义的流动负债。

| 字段 | 解释 | 精确定义 |
|---|---|---|
| `creditor_pressure_transition_eligible` | 两期压力状态是否可判断。 | 两期 `creditors_total` 和两期 `current_assets` 共 4 个值均非空。 |
| `creditor_pressure_onset_eligible` | 是否进入“压力新发生”风险集。 | transition eligible 且 `t` 期不满足 `creditors_total > current_assets`。 |
| `creditor_pressure_recovery_eligible` | 是否进入“压力恢复”风险集。 | transition eligible 且 `t` 期满足 `creditors_total > current_assets`。 |
| `creditor_pressure_persistent_eligible` | 是否进入“压力持续”风险集。 | 与 recovery eligible 相同。 |
| `creditor_pressure_onset_flag` | 下一期是否新出现压力。 | onset eligible 中，`creditors_total_t_plus_1 > current_assets_t_plus_1` 为 True。 |
| `creditor_pressure_recovery_flag` | 下一期是否解除压力。 | recovery eligible 中，下一期不满足上述严格大于关系为 True；相等也视为恢复。 |
| `creditor_pressure_persistent_flag` | 下一期是否仍存在压力。 | persistent eligible 中，下一期仍满足严格大于关系为 True。 |

代码只检查 4 个底层值是否非空，没有在这里额外要求它们非负。分析前建议与表 5 的 `impossible_negative_value_flag` 联用，并对异常值做敏感性分析。

## 7. Reported loss 字段

状态定义：成功抽取的 `profit_loss < 0` 为 reported loss；`>= 0` 为未报告亏损。profit/loss 覆盖率明显低于资产负债表字段，因此该组标签应作为辅助信号。

| 字段 | 解释 | 精确定义 |
|---|---|---|
| `reported_loss_transition_eligible` | 两期盈亏状态是否可判断。 | 两期 `profit_loss` 均非空。 |
| `reported_loss_onset_eligible` | 是否进入“亏损新发生”风险集。 | transition eligible 且 `profit_loss_t >= 0`。 |
| `reported_loss_recovery_eligible` | 是否进入“亏损恢复”风险集。 | transition eligible 且 `profit_loss_t < 0`。 |
| `reported_loss_onset_flag` | 下一期是否新报告亏损。 | onset eligible 中，`profit_loss_t_plus_1 < 0` 为 True。 |
| `reported_loss_recovery_flag` | 下一期是否恢复至非亏损。 | recovery eligible 中，`profit_loss_t_plus_1 >= 0` 为 True。 |

本表没有 `reported_loss_persistent_eligible` 或 `reported_loss_persistent_flag`。若确有需要，可在 `reported_loss_recovery_eligible=True` 的风险集中用 `~reported_loss_recovery_flag` 推导“持续亏损”，但应在派生变量名中明确这是后续构造。

## 8. 正确计算比率的方式

示例：负权益发生率应计算为：

```python
risk_set = df[df["negative_equity_onset_eligible"]]
onset_rate = risk_set["negative_equity_onset_flag"].mean()
```

不要先对全列 `fillna(False)` 再除以总行数；那会把“不在风险集”和“底层数据缺失”错误地当成未发生事件。

同理：

- recovery rate 的分母是对应 `*_recovery_eligible=True` 的行；
- persistence rate 的分母是对应 `*_persistent_eligible=True` 的行；
- 比较行业或账户类别时，应同时报告风险集样本量，避免小样本比率失真。

## 9. 建模与时间对齐

- 预测 onset：训练样本只保留 `*_onset_eligible=True`，target 使用相应 `*_onset_flag`。
- 预测 recovery：只保留 `*_recovery_eligible=True`。
- 预测 persistent：只保留 `*_persistent_eligible=True`。
- 特征截止日应为 `available_date_t`；target 在 `available_date_t_plus_1` 后才完整可见。
- `evidence_tier_t_plus_1` 可用于检查 target 质量，但不能作为时点 `t` 的预测特征。
- 同一家公司可能贡献多行；交叉验证或训练/测试切分要考虑公司重复和时间顺序，避免同一公司的未来记录泄漏到过去。
- 这些标签描述下一份年度账目的状态，不等同于未来 4—6 个月融资需求、违约或商业机会。
