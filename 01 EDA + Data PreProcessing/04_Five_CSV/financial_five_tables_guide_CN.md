# 财务数据分析五大表使用说明

## 数据范围

- 公司母表：`UKcompanies_active_account_category_sample_100k.csv`，共 100,000 家公司。
- 财务来源：2024年7月至2026年6月的24个Companies House Accounts Monthly Bulk ZIP。
- 当前快照：每家公司最新的account period，而不是历史best-evidence period。
- 分位标签：优先采用`primary_sector + Accounts_AccountCategory`组内30%/70%分位数；有效样本少于30或阈值相同时，回退到行业，再回退到总体。
- 原始公司表和Accounts ZIP不会被修改。

## 文件与作用

### 1. `01_financial_status_labels_100k.csv`

一家公司一行，共 100,000 行。描述最新期间的财务状态和reason codes，包括负权益、营运资金缺口、reported loss、债权人压力，以及现金覆盖、资产密集度、应收账款密集度等分位标签。

- `negative_equity_flag`：17,170/91,479，占有效样本 18.77%。
- `working_capital_deficit_flag`：27,349/89,721，占有效样本 30.48%。
- `reported_loss_flag`：1,343/4,655，占有效样本 28.85%；因覆盖率低，只建议作为辅助信号。

用途：当前公司画像、模型输入、结果解释。它们不是融资需求的直接标签。

### 2. `02_financial_scale_labels_100k.csv`

一家公司一行，共 100,000 行。分别为current assets、fixed assets、creditors、absolute equity、employees、net assets和total assets生成Low/Medium/High规模带。

用途：三分类模型特征、行业内规模比较、缺少turnover公司的规模proxy。该表不构造人工加权的商业机会总分，也不能替代Lloyds正式BB/SME/Mid Corporate层级。

### 3. `03_financial_change_labels.csv`

一条相邻年度company-period pair一行，共 81,603 行，涉及 76,611 家公司。包含原值、下一期值、signed-log change、percent change和30/70变化等级。

用途：描述增长、稳定或收缩；可以把历史变化作为下一次预测的输入，也可以把下一期变化作为target。`t -> t+1`变化在时间`t`尚不可见，不能当作时间`t`特征。

### 4. `04_financial_transition_labels.csv`

一条相邻年度company-period pair一行，共 81,603 行。记录负权益、营运资金缺口、债权人压力和reported loss的发生、持续与恢复。

- `negative_equity_onset_flag`：3,325/64,717，占有效pair 5.14%。
- `working_capital_deficit_onset_flag`：4,623/53,281，占有效pair 8.68%。

用途：训练下一期财务状态模型。每个target必须与相应`*_eligible`字段一起使用，缺失不能当作False。

### 5. `05_financial_data_quality_labels_100k.csv`

一家公司一行，共 100,000 行。包括T1-T4 evidence tier、期间数量、turnover覆盖、字段完整度、账目时效、异常负值、极端金额和证据等级变化。

用途：过滤、样本加权、置信度、敏感性分析和数据质量监控。它不是业务机会标签。

## 连接键

- 公司级表：使用`CompanyNumber_norm`连接。
- 跨期表：使用`CompanyNumber_norm + period_t + period_t_plus_1`唯一定位pair。
- 连接多维度数据时必须保证news和hiring变量在相应`available_date_t`之前已经可获得。

## Feature、Target与Control

- 当前状态及规模标签通常是feature或reason code。
- `*_onset_flag`、`*_recovery_flag`及下一期变化等级可以作为未来target。
- T级、完整度和异常标记是control/confidence字段。
- 三分类的正式target仍应由observed turnover生成：BB < £3m，SME £3m–£25m，Mid Corporate £25m–£500m。

## 重要限制

- Accounts数据主要是年度披露，下一期财务状态不等于未来4–6个月融资需求。
- `creditors_total`不一定等于严格会计定义的current liabilities，相关ratio应称为proxy。
- 分位标签是样本相对位置，不是通用财务健康标准。
- 未来模型应按照`available_date`做时间切分，不能随机把未来filing放入训练集。
