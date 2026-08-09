# 表 3：`03_financial_change_labels.csv` 字段解释

## 1. 这张表回答什么问题

表 3 描述同一家公司从会计期 `t` 到下一相邻会计期 `t+1` 的财务指标变化，共 122 个字段。每行是一组有效的“公司—相邻年度期间”配对，而不是一家公司。当前文件有 81,603 行，涉及 76,611 家公司；同一家公司可能有多行。

- 行粒度：一家公司的一组相邻期间。
- 唯一键：`CompanyNumber_norm + period_t + period_t_plus_1`。
- 配对规则：先按公司和 `period_end` 排序，取下一条已观测期间；仅保留期间间隔在 250—550 天（含边界）之间的配对。
- 变化对象：11 个指标，每个指标均保留两期原值、变化值、可用性、相对变化等级及分组阈值；其中 `net_current_assets_liabilities` 与 `profit_loss` 均包含 `t`、`t+1`、变化值、资格标记和变化分位字段。
- 典型用途：历史增长/收缩画像、趋势特征、预测下一会计期变化的目标变量。

> 时间泄漏警告：本表的变化字段使用了 `t+1` 期数据。在 `available_date_t` 时点做预测时，`*_t_plus_1`、`*_signed_log_change`、`*_percent_change` 和 `*_change_band` 都尚不可见，不能直接作为时点 `t` 的特征。若将某一行的变化当特征，应确保预测基准日在 `available_date_t_plus_1` 之后，或把该变化向后滞后一组期间。

## 2. 相邻期间是怎样构造的

1. 同一 `CompanyNumber_norm` 内按 `period_end` 升序排列。
2. 当前行作为 `t`，下一条已观测记录作为 `t+1`。
3. 计算 `gap_days = period_t_plus_1 - period_t`。
4. 只保留 `250 <= gap_days <= 550` 的配对。

因此，“相邻”是数据中下一条已观测会计期，不保证恰好相隔 365 天，也不保证公司没有漏报中间期间。

## 3. 公司、期间与证据字段

| 字段 | 类型/取值 | 解释 | 特征工程注意事项 |
|---|---|---|---|
| `CompanyNumber_norm` | 字符串 | 标准化 Companies House 公司编号。纯数字补齐为 8 位；英文字母前缀编号标准化为两位字母加六位数字。 | 必须按字符串读取，否则前导零会丢失。 |
| `CompanyName` | 字符串 | 公司名称，来自 10 万家公司母表。 | 展示字段；通常不直接进入模型。 |
| `primary_sector` | 类别 | 公司主行业。 | 是变化分位阈值的首要分组字段之一；可编码为类别特征。 |
| `Accounts_AccountCategory` | 类别 | Companies House 账户类别，如 `MICRO ENTITY`、`SMALL`、`FULL`。 | 与行业共同决定首选比较组；不能等同于银行客户分层。 |
| `period_t` | 日期 | 起始会计期的期末日。 | 表示财务值所属期间，不代表信息对外可见日期。 |
| `period_t_plus_1` | 日期 | 下一相邻会计期的期末日。 | 用于定义目标窗口；不能仅凭该日期判断数据何时可用。 |
| `available_date_t` | 日期 | 包含 `t` 期报表的 Companies House 月度 ZIP 对应月份的月末日。 | 这是保守的近似可用日，不是精确 filing timestamp；时间切分优先使用它而不是 `period_t`。 |
| `available_date_t_plus_1` | 日期 | 包含 `t+1` 期报表的月度 ZIP 对应月份月末日。 | `t -> t+1` 变化最早应视为在该日可用。 |
| `gap_days` | 整数/浮点 | 两个会计期末日之差，单位为天。 | 文件中只保留 250—550 天；可作为时间跨度控制变量。 |
| `evidence_tier_t` | 类别 | `t` 期的财务证据等级。 | 见下方等级定义；可用于样本筛选或加权。 |
| `evidence_tier_t_plus_1` | 类别 | `t+1` 期的财务证据等级。 | 若用于目标质量控制可以使用；在时点 `t` 预测中属于未来信息。 |

证据等级按以下顺序从强到弱：

| 等级 | 构造规则 |
|---|---|
| `T1_observed_turnover` | 本期成功提取到 turnover；无论核心代理字段数多少，优先定为 T1。 |
| `T2_balance_sheet_rich` | 没有 turnover，但 7 个核心代理字段中至少 4 个可用。 |
| `T3_balance_sheet_partial` | 没有 turnover，但 7 个核心代理字段中有 2—3 个可用。 |
| `T4_account_category_only` | 已匹配到账目，但没有 turnover，且核心代理字段少于 2 个。 |

7 个核心代理字段为：`current_assets`、`net_assets_liabilities`、`equity`、`creditors_total`、`employees`、`cash`、`debtors`。

## 4. 11 个变化指标的业务含义

下列每个指标都展开为同一组 10 个字段；字段前缀见第一列。

| 指标前缀 | 中文含义 | 是否要求两期非负 | 解读重点 |
|---|---|---:|---|
| `current_assets` | 流动资产 | 是 | 资产负债表中的短期资产规模；增加不必然等于流动性改善。 |
| `fixed_assets` | 固定资产 | 是 | 长期实物/资本性资产规模；变化可能来自投资、折旧、处置或口径变化。 |
| `creditors_total` | 债权人/应付款总额代理 | 是 | 优先使用报表总额；缺失时可由一年内与一年后到期 creditors 相加构造。并不严格等同于 current liabilities。 |
| `equity` | 权益/股东资金 | 否 | 可为负；正向变化通常表示权益改善，但应结合利润、注资等信息解释。 |
| `net_assets_liabilities` | 净资产/净负债 | 否 | 可为负；与 `equity` 可能高度相似或相同，建模前检查共线性。 |
| `net_current_assets_liabilities` | 净流动资产/负债（营运资金） | 否 | 可为负；是表 4 营运资金缺口状态的底层数值，应与 `working_capital_deficit_*` 转变标签结合解释。 |
| `cash` | 现金及现金等价物 | 是 | 波动往往较大，不能单独视为经营好坏。 |
| `debtors` | 应收款项 | 是 | 增加可能代表业务扩张，也可能代表回款变慢。 |
| `employees` | 期内平均员工数或报表员工总数 | 是 | 源标签可能存在单位/解析异常；应结合表 5 质量标记并做合理范围检查。 |
| `profit_loss` | 利润/亏损 | 否 | 可为负；跨期覆盖较低，适合辅助分析盈利改善/恶化，不应在全样本中单独主导模型或评分。 |
| `total_assets_less_current_liabilities` | 总资产减流动负债 | 否 | Companies House 报表字段；可为负，是资本结构/净资产规模代理。 |

“是否要求两期非负”决定 `*_change_eligible`：标为“是”的指标，只要任一期小于 0 就不参与变化计算和分位统计；标为“否”的指标允许负数。

## 5. 每个指标重复出现的 10 类字段

下表中的 `<metric>` 依次替换为：`current_assets`、`fixed_assets`、`creditors_total`、`equity`、`net_assets_liabilities`、`net_current_assets_liabilities`、`cash`、`debtors`、`employees`、`profit_loss`、`total_assets_less_current_liabilities`。这套规则完整覆盖 110 个指标字段。

| 字段模式 | 解释 | 计算/取值规则 |
|---|---|---|
| `<metric>_t` | 指标在起始期间 `t` 的原始值。 | 从去重后的 company-period panel 取得；金额通常按报表原币单位记录，员工数为人数。 |
| `<metric>_t_plus_1` | 指标在下一期间 `t+1` 的原始值。 | 同上。 |
| `<metric>_change_eligible` | 该指标的两期变化是否可计算。 | 两期都非空；对要求非负的指标，还要求两期都 `>= 0`。这是数据适用性标记，不是变化方向。 |
| `<metric>_signed_log_change` | 保留正负号的对数尺度变化，是变化分位标签的依据。 | `slog(t+1) - slog(t)`，其中 `slog(x) = sign(x) × ln(1 + abs(x))`。支持零和负值，降低极端金额的影响。 |
| `<metric>_percent_change` | 相对于 `t` 期绝对值的比例变化。 | 当 eligible 且 `abs(t) > 1e-12` 时，`(t+1 - t) / abs(t)`；否则为空。0.20 表示相对基期绝对值增加 20%。 |
| `<metric>_change_band` | 当前变化在可比样本中的相对等级。 | 按 `signed_log_change` 与 30%/70% 阈值比较：`<= low` 为 `Low`，`> low 且 < high` 为 `Medium`，`>= high` 为 `High`。 |
| `<metric>_change_threshold_scope` | 本行实际采用的阈值层级。 | `sector_account_category`、`sector` 或 `global`。 |
| `<metric>_change_threshold_n` | 计算本行所用阈值的有效样本量。 | 对应实际阈值层级中的 eligible 变化观测数。 |
| `<metric>_change_low_threshold` | Low/Medium 分界值。 | 所用比较组 `signed_log_change` 的第 30 百分位数。 |
| `<metric>_change_high_threshold` | Medium/High 分界值。 | 所用比较组 `signed_log_change` 的第 70 百分位数。 |

### 5.1 完整字段前缀展开

每一行均实际包含以下后缀：`_t`、`_t_plus_1`、`_change_eligible`、`_signed_log_change`、`_percent_change`、`_change_band`、`_change_threshold_scope`、`_change_threshold_n`、`_change_low_threshold`、`_change_high_threshold`。

| 前缀 | 该组的 10 个实际字段 |
|---|---|
| `current_assets` | `current_assets_t` 至 `current_assets_change_high_threshold` |
| `fixed_assets` | `fixed_assets_t` 至 `fixed_assets_change_high_threshold` |
| `creditors_total` | `creditors_total_t` 至 `creditors_total_change_high_threshold` |
| `equity` | `equity_t` 至 `equity_change_high_threshold` |
| `net_assets_liabilities` | `net_assets_liabilities_t` 至 `net_assets_liabilities_change_high_threshold` |
| `net_current_assets_liabilities` | `net_current_assets_liabilities_t` 至 `net_current_assets_liabilities_change_high_threshold` |
| `cash` | `cash_t` 至 `cash_change_high_threshold` |
| `debtors` | `debtors_t` 至 `debtors_change_high_threshold` |
| `employees` | `employees_t` 至 `employees_change_high_threshold` |
| `profit_loss` | `profit_loss_t` 至 `profit_loss_change_high_threshold` |
| `total_assets_less_current_liabilities` | `total_assets_less_current_liabilities_t` 至 `total_assets_less_current_liabilities_change_high_threshold` |

### 5.2 110 个实际指标字段逐项索引

下表逐项列出 CSV 中的实际字段名。计算公式和空值条件与 5 节的统一规则完全一致。

| 实际字段 | 指标 | 字段解释 |
|---|---|---|
| `current_assets_t` | 流动资产 | `t` 期原始值。 |
| `current_assets_t_plus_1` | 流动资产 | `t+1` 期原始值。 |
| `current_assets_change_eligible` | 流动资产 | 两期是否满足该指标的变化计算条件。 |
| `current_assets_signed_log_change` | 流动资产 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `current_assets_percent_change` | 流动资产 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `current_assets_change_band` | 流动资产 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `current_assets_change_threshold_scope` | 流动资产 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `current_assets_change_threshold_n` | 流动资产 | 实际阈值层级的有效样本数。 |
| `current_assets_change_low_threshold` | 流动资产 | 所用 signed-log change 的第 30 百分位阈值。 |
| `current_assets_change_high_threshold` | 流动资产 | 所用 signed-log change 的第 70 百分位阈值。 |
| `fixed_assets_t` | 固定资产 | `t` 期原始值。 |
| `fixed_assets_t_plus_1` | 固定资产 | `t+1` 期原始值。 |
| `fixed_assets_change_eligible` | 固定资产 | 两期是否满足该指标的变化计算条件。 |
| `fixed_assets_signed_log_change` | 固定资产 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `fixed_assets_percent_change` | 固定资产 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `fixed_assets_change_band` | 固定资产 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `fixed_assets_change_threshold_scope` | 固定资产 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `fixed_assets_change_threshold_n` | 固定资产 | 实际阈值层级的有效样本数。 |
| `fixed_assets_change_low_threshold` | 固定资产 | 所用 signed-log change 的第 30 百分位阈值。 |
| `fixed_assets_change_high_threshold` | 固定资产 | 所用 signed-log change 的第 70 百分位阈值。 |
| `creditors_total_t` | 债权人/应付款总额代理 | `t` 期原始值。 |
| `creditors_total_t_plus_1` | 债权人/应付款总额代理 | `t+1` 期原始值。 |
| `creditors_total_change_eligible` | 债权人/应付款总额代理 | 两期是否满足该指标的变化计算条件。 |
| `creditors_total_signed_log_change` | 债权人/应付款总额代理 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `creditors_total_percent_change` | 债权人/应付款总额代理 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `creditors_total_change_band` | 债权人/应付款总额代理 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `creditors_total_change_threshold_scope` | 债权人/应付款总额代理 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `creditors_total_change_threshold_n` | 债权人/应付款总额代理 | 实际阈值层级的有效样本数。 |
| `creditors_total_change_low_threshold` | 债权人/应付款总额代理 | 所用 signed-log change 的第 30 百分位阈值。 |
| `creditors_total_change_high_threshold` | 债权人/应付款总额代理 | 所用 signed-log change 的第 70 百分位阈值。 |
| `equity_t` | 权益 | `t` 期原始值。 |
| `equity_t_plus_1` | 权益 | `t+1` 期原始值。 |
| `equity_change_eligible` | 权益 | 两期是否满足该指标的变化计算条件。 |
| `equity_signed_log_change` | 权益 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `equity_percent_change` | 权益 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `equity_change_band` | 权益 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `equity_change_threshold_scope` | 权益 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `equity_change_threshold_n` | 权益 | 实际阈值层级的有效样本数。 |
| `equity_change_low_threshold` | 权益 | 所用 signed-log change 的第 30 百分位阈值。 |
| `equity_change_high_threshold` | 权益 | 所用 signed-log change 的第 70 百分位阈值。 |
| `net_assets_liabilities_t` | 净资产/净负债 | `t` 期原始值。 |
| `net_assets_liabilities_t_plus_1` | 净资产/净负债 | `t+1` 期原始值。 |
| `net_assets_liabilities_change_eligible` | 净资产/净负债 | 两期是否满足该指标的变化计算条件。 |
| `net_assets_liabilities_signed_log_change` | 净资产/净负债 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `net_assets_liabilities_percent_change` | 净资产/净负债 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `net_assets_liabilities_change_band` | 净资产/净负债 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `net_assets_liabilities_change_threshold_scope` | 净资产/净负债 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `net_assets_liabilities_change_threshold_n` | 净资产/净负债 | 实际阈值层级的有效样本数。 |
| `net_assets_liabilities_change_low_threshold` | 净资产/净负债 | 所用 signed-log change 的第 30 百分位阈值。 |
| `net_assets_liabilities_change_high_threshold` | 净资产/净负债 | 所用 signed-log change 的第 70 百分位阈值。 |
| `net_current_assets_liabilities_t` | 净流动资产/负债（营运资金） | `t` 期原始值。 |
| `net_current_assets_liabilities_t_plus_1` | 净流动资产/负债（营运资金） | `t+1` 期原始值。 |
| `net_current_assets_liabilities_change_eligible` | 净流动资产/负债（营运资金） | 两期是否满足该指标的变化计算条件。 |
| `net_current_assets_liabilities_signed_log_change` | 净流动资产/负债（营运资金） | 两期 signed-log 值之差；分位标签的实际输入。 |
| `net_current_assets_liabilities_percent_change` | 净流动资产/负债（营运资金） | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `net_current_assets_liabilities_change_band` | 净流动资产/负债（营运资金） | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `net_current_assets_liabilities_change_threshold_scope` | 净流动资产/负债（营运资金） | 实际阈值层级：行业×账户类别、行业或总体。 |
| `net_current_assets_liabilities_change_threshold_n` | 净流动资产/负债（营运资金） | 实际阈值层级的有效样本数。 |
| `net_current_assets_liabilities_change_low_threshold` | 净流动资产/负债（营运资金） | 所用 signed-log change 的第 30 百分位阈值。 |
| `net_current_assets_liabilities_change_high_threshold` | 净流动资产/负债（营运资金） | 所用 signed-log change 的第 70 百分位阈值。 |
| `cash_t` | 现金及现金等价物 | `t` 期原始值。 |
| `cash_t_plus_1` | 现金及现金等价物 | `t+1` 期原始值。 |
| `cash_change_eligible` | 现金及现金等价物 | 两期是否满足该指标的变化计算条件。 |
| `cash_signed_log_change` | 现金及现金等价物 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `cash_percent_change` | 现金及现金等价物 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `cash_change_band` | 现金及现金等价物 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `cash_change_threshold_scope` | 现金及现金等价物 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `cash_change_threshold_n` | 现金及现金等价物 | 实际阈值层级的有效样本数。 |
| `cash_change_low_threshold` | 现金及现金等价物 | 所用 signed-log change 的第 30 百分位阈值。 |
| `cash_change_high_threshold` | 现金及现金等价物 | 所用 signed-log change 的第 70 百分位阈值。 |
| `debtors_t` | 应收款项 | `t` 期原始值。 |
| `debtors_t_plus_1` | 应收款项 | `t+1` 期原始值。 |
| `debtors_change_eligible` | 应收款项 | 两期是否满足该指标的变化计算条件。 |
| `debtors_signed_log_change` | 应收款项 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `debtors_percent_change` | 应收款项 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `debtors_change_band` | 应收款项 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `debtors_change_threshold_scope` | 应收款项 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `debtors_change_threshold_n` | 应收款项 | 实际阈值层级的有效样本数。 |
| `debtors_change_low_threshold` | 应收款项 | 所用 signed-log change 的第 30 百分位阈值。 |
| `debtors_change_high_threshold` | 应收款项 | 所用 signed-log change 的第 70 百分位阈值。 |
| `employees_t` | 员工数 | `t` 期原始值。 |
| `employees_t_plus_1` | 员工数 | `t+1` 期原始值。 |
| `employees_change_eligible` | 员工数 | 两期是否满足该指标的变化计算条件。 |
| `employees_signed_log_change` | 员工数 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `employees_percent_change` | 员工数 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `employees_change_band` | 员工数 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `employees_change_threshold_scope` | 员工数 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `employees_change_threshold_n` | 员工数 | 实际阈值层级的有效样本数。 |
| `employees_change_low_threshold` | 员工数 | 所用 signed-log change 的第 30 百分位阈值。 |
| `employees_change_high_threshold` | 员工数 | 所用 signed-log change 的第 70 百分位阈值。 |
| `profit_loss_t` | 利润/亏损 | `t` 期原始值。 |
| `profit_loss_t_plus_1` | 利润/亏损 | `t+1` 期原始值。 |
| `profit_loss_change_eligible` | 利润/亏损 | 两期是否满足该指标的变化计算条件。 |
| `profit_loss_signed_log_change` | 利润/亏损 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `profit_loss_percent_change` | 利润/亏损 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `profit_loss_change_band` | 利润/亏损 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `profit_loss_change_threshold_scope` | 利润/亏损 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `profit_loss_change_threshold_n` | 利润/亏损 | 实际阈值层级的有效样本数。 |
| `profit_loss_change_low_threshold` | 利润/亏损 | 所用 signed-log change 的第 30 百分位阈值。 |
| `profit_loss_change_high_threshold` | 利润/亏损 | 所用 signed-log change 的第 70 百分位阈值。 |
| `total_assets_less_current_liabilities_t` | 总资产减流动负债 | `t` 期原始值。 |
| `total_assets_less_current_liabilities_t_plus_1` | 总资产减流动负债 | `t+1` 期原始值。 |
| `total_assets_less_current_liabilities_change_eligible` | 总资产减流动负债 | 两期是否满足该指标的变化计算条件。 |
| `total_assets_less_current_liabilities_signed_log_change` | 总资产减流动负债 | 两期 signed-log 值之差；分位标签的实际输入。 |
| `total_assets_less_current_liabilities_percent_change` | 总资产减流动负债 | `(t+1-t)/abs(t)`；基期接近零时为空。 |
| `total_assets_less_current_liabilities_change_band` | 总资产减流动负债 | 基于所用比较组 P30/P70 的 `Low/Medium/High` 标签。 |
| `total_assets_less_current_liabilities_change_threshold_scope` | 总资产减流动负债 | 实际阈值层级：行业×账户类别、行业或总体。 |
| `total_assets_less_current_liabilities_change_threshold_n` | 总资产减流动负债 | 实际阈值层级的有效样本数。 |
| `total_assets_less_current_liabilities_change_low_threshold` | 总资产减流动负债 | 所用 signed-log change 的第 30 百分位阈值。 |
| `total_assets_less_current_liabilities_change_high_threshold` | 总资产减流动负债 | 所用 signed-log change 的第 70 百分位阈值。 |


## 6. 分位标签与回退机制

对每个指标分别计算阈值，步骤如下：

1. 首选 `primary_sector + Accounts_AccountCategory` 组内第 30/70 百分位数。
2. 若该组 eligible 样本少于 30，或两个阈值相等，则回退到 `primary_sector` 行业层级。
3. 若行业层级同样少于 30 或阈值相等，则回退到全样本 `global` 阈值。
4. 只有最终阈值非空且 `low < high` 时才生成 `Low/Medium/High`。

一个容易忽略的情况是：`*_change_eligible=True` 且阈值字段已有值时，`*_change_band` 仍可能为空。这表示最终选中的阈值相等或无效，常见于大量变化为 0 的离散指标（尤其员工数）。不要把空白 band 自动归为 `Medium`。

`Low/Medium/High` 是样本内的相对变化位置：

- `Low` 通常表示较强收缩或较弱增长；
- `Medium` 表示比较组中间区间；
- `High` 通常表示较强增长或较弱收缩。

它们不是通用的财务健康等级。比如 creditors 的 `High` 只是债权人金额增长较快，未必是正面信号。

## 7. 汇总字段

| 字段 | 类型 | 解释 |
|---|---|---|
| `change_available_field_count` | 0—11 的整数 | 11 个指标中 `*_change_eligible=True` 的数量。衡量这一行变化信息的覆盖度，不代表财务表现好坏。 |

## 8. 建模建议

- 做描述性分析：优先同时报告 `signed_log_change`、原值和 `change_band`，不要只看百分比变化。
- 做回归：`signed_log_change` 通常比原始差值稳健；对可为负的指标尤其有用。
- 做分类目标：可用 `change_band`，但应保留 `threshold_scope` 和 `threshold_n` 做敏感性检查。
- 做时点 `t` 预测：把本行的变化当 target；只使用在 `available_date_t` 前已知的其他特征。
- 把历史变化当 feature：必须使用上一组已完整披露的变化，并按 `available_date_t_plus_1` 对齐，不能把当前行的未来变化泄漏进模型。
- 对 `percent_change` 做截尾/稳健处理：基期很小时比例会极端；基期为零时该字段为空，但 `signed_log_change` 仍可用。
- 合并表 5：可利用证据等级、异常负值、极端金额和期间间隔异常做过滤、加权或稳健性分析。

## 9. 例子

若 `cash_t=100`、`cash_t_plus_1=150`：

- `cash_change_eligible=True`；
- `cash_percent_change=(150-100)/100=0.5`；
- `cash_signed_log_change=ln(151)-ln(101)`；
- `cash_change_band` 还要与该公司适用比较组的 30%/70% 阈值比较，不能只凭 50% 增长直接判断为 `High`。

若 `equity_t=-100`、`equity_t_plus_1=-50`，则 percent change 为 `(+50)/100=+0.5`，signed-log change 也为正，表示负权益有所改善；但公司在两期仍可能处于负权益状态，需结合表 4 的 persistent/recovery 标签。
