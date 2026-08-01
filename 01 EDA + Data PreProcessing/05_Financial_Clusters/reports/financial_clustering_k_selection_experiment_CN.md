# SignalBridge 财务聚类 K 选择实验：过程与结果记录

## 1. 实验概览

| 项目 | 内容 |
|---|---|
| 实验目标 | 从公司最新财务快照中识别可解释的财务原型（financial archetypes），为后续公司排名系统提供结构化财务信号 |
| 样本母体 | 100,000 家英国活跃公司 |
| 最终选择 | **K = 5** |
| 最终状态 | K=5 已通过统计稳定性、Cluster规模和业务解释性检查，可作为正式财务Cluster框架 |
| V1 Run ID | `20260725T151423Z` |
| V2 Run ID | `20260725T153022Z` |
| 实验日期 | 2026-07-25 |

本实验的目标不是重新完成 BB / SME / Mid Corporate 三分类，而是构建能够服务后续公司排名的财务画像。Cluster用于描述公司的财务结构、融资需求和风险类型；三分类标签后续只用于交叉分析，不参与本次聚类。

---

## 2. 数据来源与表的分工

S3输入路径：

```text
s3://team6-project-288469846191-eu-north-1-an/processed/financial_features/
```

使用的五张表如下。

| 文件 | 粒度 | 在实验中的用途 |
|---|---|---|
| `01_financial_status_labels_100k.csv` | 一家公司一行，最新快照 | 当前财务数值、状态标签和画像解释 |
| `02_financial_scale_labels_100k.csv` | 一家公司一行，最新快照 | Low / Medium / High规模带，用于Cluster解释和Tableau交叉分析 |
| `03_financial_change_labels.csv` | 一条相邻年度pair一行 | 使用period-t字段重建历史Cluster，以period-t+1变化作为外部结果 |
| `04_financial_transition_labels.csv` | 一条相邻年度pair一行 | 验证下一期负权益、营运资金缺口和债权人压力的发生、持续与恢复 |
| `05_financial_data_quality_labels_100k.csv` | 一家公司一行 | 样本过滤、完整度控制、置信度和敏感性分析 |

连接规则：

```text
公司级表：CompanyNumber_norm
跨期表：CompanyNumber_norm + period_t + period_t_plus_1
```

为防止信息泄漏：

- 聚类只使用最新快照或历史period-t时点已知的字段；
- `t+1`变化和状态转移只作为外部验证结果；
- 新闻、招聘和BB / SME / Mid Corporate标签不进入聚类特征；
- 历史验证使用period-t特征预测Cluster，再观察period-t+1结果。

---

## 3. 分析样本

V2建立了两个样本口径。

### 3.1 Broad eligible cohort

主要业务样本，共 **84,711 家公司**。筛选条件：

- `useful_financial_evidence_flag = True`；
- 至少4个核心代理字段；
- 账目不超过24个月；
- 不存在不可能负值；
- 至少5个模型特征非缺失。

### 3.2 Complete core cohort

敏感性分析样本，共 **22,878 家公司**。在Broad eligible条件上进一步要求：

```text
core_fields_complete_flag = True
```

Broad eligible是主要公司覆盖范围；Complete core用于检验缺失值和披露完整度是否改变K选择。

---

## 4. V1实验及失败诊断

V1使用了14个模型特征，包含规模、偿付能力和经营结构比率。自动选择结果为K=2：

| Cluster | 公司数 | 占比 |
|---|---:|---:|
| FC01 | 2,272 | 2.64% |
| FC02 | 83,872 | 97.36% |

虽然K=2的Silhouette达到0.938、Bootstrap ARI达到0.824，但它并不是两个有意义的公司原型，而是“少量极端公司”与“其余主体公司”的分离。

两个变量贡献了两个聚类中心之间约99.95%的距离：

| 特征 | 距离贡献 |
|---|---:|
| `employees_per_million_assets_proxy` | 60.33% |
| `creditors_to_disclosed_assets_proxy` | 39.62% |
| 其余12个特征合计 | 约0.05% |

主要原因：

1. 分母非常小时，比率发生爆炸；
2. 99%截尾后上限仍然过高；
3. 稀疏变量在中位数插补后IQR接近0，RobustScaler无法有效缩放；
4. V1只限制最小Cluster占比，没有限制最大Cluster占比；
5. MiniBatchKMeans在不同K下的Inertia没有稳定单调下降，说明结果受局部收敛影响。

V1结论：

> K=2是失败结果，不用于正式公司标签。V1保留为方法迭代和问题诊断记录。

---

## 5. V2方法修正

### 5.1 K搜索范围

```text
K = 3, 4, 5, 6, 7, 8
```

K=2被排除，因为两个类别无法满足多原型财务框架的业务目标。

### 5.2 模型特征

V2只保留覆盖率较高、可在历史period-t重建的8个核心特征。

#### Scale block：总权重40%

```text
log_current_assets
log_creditors_total
log_employees
```

#### Solvency block：总权重40%

```text
signed_log_equity
signed_log_net_assets_liabilities
signed_log_total_assets_less_current_liabilities
```

#### Creditor-pressure block：总权重20%

```text
log_creditors_to_current_assets_proxy
signed_log_current_assets_minus_creditors_proxy
```

现金、应收账款和固定资产等覆盖率较低的字段不再参与公司间距离计算，而是用于聚类完成后的画像解释。

债权人压力比率仅在以下条件成立时计算：

```text
current_assets >= GBP 1,000
creditors_total >= 0
```

该规则用于避免极小分母制造异常距离。

### 5.3 预处理

1. 非负金额采用`log1p`；
2. 可能为负的金额采用signed-log；
3. 每个特征按1%和99%分位截尾；
4. 缺失值采用训练样本中位数插补；
5. 使用StandardScaler标准化；
6. 按40% / 40% / 20%配置三个特征块的总距离权重。

### 5.4 算法与抽样

- 算法：标准KMeans；
- 固定拟合样本：60,000家公司；
- `n_init = 30`；
- `max_iter = 500`；
- Silhouette评估样本：8,000家公司；
- Bootstrap稳定性参考样本：8,000家公司；
- Bootstrap重复次数：3；
- 随机种子：42。

使用固定样本和标准KMeans，使不同K的Inertia和质量指标可以横向比较。选定K后，再把全部合格公司分配到最近的聚类中心。

### 5.5 评价指标

| 指标 | 判断方向 |
|---|---|
| Silhouette | 越高越好 |
| Calinski–Harabasz | 越高越好 |
| Davies–Bouldin | 越低越好 |
| Bootstrap ARI | 越高越稳定 |
| Minimum cluster share | 不得低于2% |
| Maximum cluster share | 不得高于65% |
| Normalized cluster entropy | 不得低于0.70 |

综合评分权重：

```text
Silhouette          25%
Calinski–Harabasz   10%
Davies–Bouldin      10%
Bootstrap ARI       30%
Cluster balance     25%
```

---

## 6. V2的K比较结果

### 6.1 Broad eligible cohort

| K | Silhouette | Davies–Bouldin | Bootstrap ARI | 最小簇占比 | 最大簇占比 | Entropy | Composite |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 0.220 | 1.407 | 0.973 | 19.42% | 48.43% | 0.941 | 0.517 |
| 4 | 0.259 | 1.205 | 0.965 | 14.90% | 38.11% | 0.953 | 0.533 |
| **5** | **0.289** | **1.152** | **0.982** | **11.27%** | **41.00%** | **0.924** | **0.792** |
| 6 | 0.302 | 1.226 | 0.978 | 6.74% | 40.54% | 0.900 | 0.592 |
| 7 | 0.264 | 1.248 | 0.982 | 5.44% | 31.99% | 0.916 | 0.658 |
| 8 | 0.260 | 1.200 | 0.971 | 5.01% | 28.55% | 0.906 | 0.408 |

K=5在主要业务样本中获得最高综合评分，并通过所有统计和业务规则。

### 6.2 Complete core cohort

| K | Silhouette | Davies–Bouldin | Bootstrap ARI | 最小簇占比 | 最大簇占比 | Entropy | Composite |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 0.303 | 1.156 | 0.982 | 17.95% | 57.30% | 0.886 | 0.683 |
| **4** | **0.321** | **1.135** | **0.992** | **14.76%** | **44.97%** | **0.926** | **0.858** |
| 5 | 0.336 | 1.257 | 0.749 | 8.72% | 44.62% | 0.879 | 0.475 |
| 6 | 0.285 | 1.221 | 0.943 | 8.21% | 31.55% | 0.939 | 0.608 |
| 7 | 0.275 | 1.210 | 0.704 | 2.34% | 24.75% | 0.911 | 0.342 |
| 8 | 0.261 | 1.158 | 0.958 | 2.27% | 22.88% | 0.938 | 0.533 |

Complete core样本更偏向K=4。进一步复现发现：

- K=4基本完整保留了V2的财务困境型FC02；
- K=4基本完整保留了资产负债驱动型FC04；
- K=4把FC01与部分FC03合并；
- K=4把FC05与另一部分FC03合并。

因此，K=4保留了主要风险结构，但压缩了健康公司的规模层次。K=5增加了：

```text
Small healthy → Healthy core → Large financially strong
```

由于最终排名系统需要覆盖Broad eligible样本，并需要区分健康公司的规模和能力层次，最终保留K=5。

---

## 7. K=5的Cluster规模分布

| Cluster | 公司数 | 占比 |
|---|---:|---:|
| FC01 | 12,828 | 15.14% |
| FC02 | 15,056 | 17.77% |
| FC03 | 34,734 | 41.00% |
| FC04 | 12,549 | 14.81% |
| FC05 | 9,544 | 11.27% |
| **合计** | **84,711** | **100.00%** |

公司数量呈现“中间多、两端少”的单峰钟形外观，但不能严格称为正态分布，因为Cluster是离散类别，FC01–FC05也不是等距数值。

对连续规模指标进行检查：

- 偏度：0.169，整体接近对称；
- 超额峰度：1.696，尾部明显重于正态分布；
- 正态性检验：`p < 0.001`，拒绝正态分布。

推荐表述：

> The cluster-size distribution is unimodal and broadly bell-shaped, while the underlying financial scale distribution remains heavy-tailed rather than normally distributed.

---

## 8. 五个财务Cluster的正式定义

### 8.1 正式名称

| Cluster | 正式英文名称 | 中文含义 |
|---|---|---|
| FC01 | **Small Low-Activity** | 小规模、低经营活跃度 |
| FC02 | **Distressed Balance Sheet** | 资产负债表困境型 |
| FC03 | **Healthy Core** | 健康主体型 |
| FC04 | **Asset-Backed Creditor-Heavy** | 资产支撑、债权人压力型 |
| FC05 | **Large Financially Strong** | 大型财务稳健型 |

### 8.2 关键财务中位数

| 指标 | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Cash | £715 | £3,482 | £27,099 | £9,244 | £158,543 |
| Creditors | £380 | £39,934 | £16,523 | £77,054 | £165,614 |
| Current assets | £979 | £9,000 | £49,729 | £17,212 | £445,637 |
| Debtors | £562 | £7,700 | £18,695 | £7,599 | £215,523 |
| Employees | 0 | 1 | 1 | 1 | 8 |
| Equity | £400 | **−£12,092** | £22,470 | £10,365 | £189,597 |
| Fixed assets | £1,099 | £8,134 | £4,335 | £105,624 | £49,863 |
| Net assets | £460 | **−£15,571** | £26,112 | £14,506 | £266,902 |
| Net current assets | £425 | **−£16,480** | £23,220 | **−£5,321** | £177,906 |
| Total assets less current liabilities | £987 | **−£4,878** | £38,275 | £43,212 | £337,501 |

### 8.3 当前财务压力

| 当前状态 | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative equity | 9.79% | **88.53%** | 0.28% | 2.83% | 0.48% |
| Working-capital deficit | 11.77% | **87.47%** | 3.67% | **64.92%** | 7.90% |
| Creditors exceed current assets | 30.23% | **88.60%** | 2.12% | **100.00%** | 7.64% |
| Core fields complete | 9.35% | 23.44% | 25.12% | 26.32% | **64.13%** |

### 8.4 Cluster解释

#### FC01 — Small Low-Activity

- 资产、员工和债权人规模均较低；
- 80.5%为Micro Entity；
- 当前财务压力不高，但规模小、披露完整度最低；
- 更适合作为低规模、早期或低活跃公司群体，而不是直接判定为低风险。

#### FC02 — Distressed Balance Sheet

- 权益、净资产和净流动资产中位数均为负；
- 负权益率88.53%；
- 营运资金缺口率87.47%；
- 是五类中最明确的财务困境群体；
- 后续排名中应作为高风险类别，而不能因融资需求高直接获得高机会分。

#### FC03 — Healthy Core

- 中等规模、权益和净资产为正；
- 当前负权益、营运资金缺口和债权人压力最低或接近最低；
- 覆盖41.00%的公司，是样本中的主体健康公司；
- 适合作为标准对照组和主流客户基础。

#### FC04 — Asset-Backed Creditor-Heavy

- 固定资产中位数£105,624，为五类中较高；
- 债权人中位数£77,054；
- 权益和净资产仍为正；
- 营运资金缺口率64.92%，债权人超过流动资产率100%；
- Real Estate占44.8%，但仍包含其他行业；
- 代表“有资产支撑但短期资金结构承压”，可能同时具有融资机会和风险。

#### FC05 — Large Financially Strong

- 流动资产、现金、应收账款、权益和净资产规模最高；
- 员工中位数8人；
- 核心字段完整率64.13%，显著高于其他Cluster；
- 当前压力和下一期风险发生率最低；
- 代表高财务能力、低风险的大型稳健公司。

---

## 9. Cluster分配质量

| Cluster | Assignment margin中位数 | High confidence占比 |
|---|---:|---:|
| FC01 | 0.320 | 61.98% |
| FC02 | 0.338 | 68.20% |
| FC03 | 0.518 | 82.75% |
| FC04 | 0.398 | 76.18% |
| FC05 | 0.521 | 77.66% |

FC03和FC05边界最清晰。FC01和FC02仍有一部分边界公司，因此下游使用时应保留：

```text
assignment_margin
cluster_assignment_confidence
imputed_feature_count
```

Cluster不应在低置信度公司上被当成绝对事实。

---

## 10. 下一期财务结果验证

历史数据：

- 原始相邻年度pairs：81,603；
- 合理年度间隔pairs：81,598；
- 可重建并分配历史Cluster的pairs由Notebook按至少5个模型特征筛选；
- 所有结果均使用period-t特征分Cluster，再观察period-t+1。

### 10.1 下一期压力发生率

| 下一期事件 | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative-equity onset | 8.25% | 7.24% | 3.85% | 7.25% | **2.20%** |
| Working-capital-deficit onset | 10.10% | **23.61%** | 7.78% | 13.22% | **5.65%** |
| Creditor-pressure onset | 16.12% | **27.68%** | 10.27% | N/A | **6.26%** |

FC04当前样本中债权人压力高度普遍，因此缺少可用于“新发生”的合格观察值，不能计算有意义的creditor-pressure onset。

### 10.2 压力持续与恢复

| 下一期结果 | FC01 | FC02 | FC03 | FC04 | FC05 |
|---|---:|---:|---:|---:|---:|
| Negative-equity persistence | 69.38% | **78.58%** | 76.47% | 76.64% | 65.62% |
| Negative-equity recovery | 30.62% | 21.42% | 23.53% | 23.36% | **34.38%** |
| Working-capital-deficit persistence | 68.74% | **84.26%** | 77.69% | 81.63% | 76.93% |
| Working-capital-deficit recovery | 31.26% | **15.74%** | 22.31% | 18.37% | 23.07% |
| Creditor-pressure persistence | 79.72% | 86.60% | **91.94%** | 82.13% | 74.38% |
| Creditor-pressure recovery | 20.28% | 13.40% | 8.06% | 17.87% | **25.62%** |

持续率和恢复率只在当前状态满足相应eligibility的公司中计算，因此不能只比较百分比，还必须结合有效pair数量。例如FC03和FC05的负权益公司本来就很少，相应持续率样本量远低于FC02。

Reported loss覆盖率较低，Cluster级有效样本有限，只作为辅助证据，不作为核心画像依据。

总体判断：

- FC02具有最高的综合财务风险；
- FC04表现为资产支撑下的持续营运资金和债权人压力；
- FC03为健康主体，但少量已经承压的公司仍可能持续承压；
- FC05的压力发生率最低、恢复表现总体较好；
- FC01当前压力有限，但小规模公司下一期发生负权益和债权人压力的概率高于FC03和FC05。

---

## 11. K=5的最终选择结论

K=5被确定为当前财务Cluster框架，原因如下：

1. 在主要Broad eligible样本中综合评分最高；
2. Bootstrap ARI达到0.982，分组稳定；
3. 最小Cluster占11.27%，最大Cluster占41.00%，不存在异常小类或支配性大类；
4. Cluster entropy达到0.924，分布合理；
5. 五类在规模、权益、净资产、固定资产和债权人压力上具有明确区别；
6. 中间的FC02、FC03和FC04规模相近但财务状态不同，说明结果不是单纯规模分档；
7. 五类在下一期风险发生、持续和恢复方面具有可解释差异；
8. K=5比K=4保留了健康公司从小规模到大型稳健的业务层次。

最终参数：

```text
SELECTED_K = 5
```

---

## 12. Cluster与后续排名的关系

Cluster ID不是从差到好的顺序，也不能直接转成1–5分。例如：

- FC02融资需求可能很高，但财务风险也最高；
- FC04可能存在真实融资机会，但需要风险约束；
- FC05财务能力强、风险低，但不代表当前融资需求最高；
- FC01规模较小，商业价值和成长潜力需要结合招聘、新闻和行业信号判断。

建议在后续排名中分别构建：

| 财务维度 | 含义 |
|---|---|
| Financial capacity | 公司承载融资和业务合作的能力 |
| Financing need | 可能存在的融资或营运资金需求 |
| Financial risk | 负权益、资金缺口和债权人压力 |
| Data confidence | 财务证据层级、完整度和Cluster分配置信度 |

后续融合框架：

```text
Business segment × Financial cluster × News signals × Hiring signals
```

BB / SME / Mid Corporate用于业务分层；Financial Cluster用于财务结构；新闻和招聘用于补充增长动能与事件信号。

---

## 13. 局限性

1. Cluster使用每家公司的最新财务快照，不代表公司永久类别；
2. Companies House Accounts主要是年度披露，不等同于未来4–6个月融资需求；
3. `creditors_total`不一定等于严格会计定义的流动负债，相关结果是proxy；
4. 现金、固定资产和应收账款披露覆盖不足，只用于画像而未进入核心聚类；
5. Reported loss覆盖率低；
6. 历史验证属于回溯式外部关联分析，不是正式预测准确率；
7. 未来加入新财务快照后，需要监控Cluster规模、中心漂移和分配置信度；
8. K=5在Complete core样本中的稳定性低于K=4，因此应持续进行样本口径敏感性检查；
9. 自动生成名称只用于初步解释，正式名称应固定在业务映射表中。

---

## 14. 实验产物与路径

### Notebook

EC2：

```text
/data/signalbridge/notebooks/financial_clustering/01_financial_cluster_k_selection_v2.ipynb
```

S3：

```text
s3://team6-project-288469846191-eu-north-1-an/notebooks/financial_clustering/01_financial_cluster_k_selection_v2.ipynb
```

### V2结果

```text
s3://team6-project-288469846191-eu-north-1-an/processed/financial_clustering/k_selection_v2/run_id=20260725T153022Z/
```

主要文件：

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

### V2模型

```text
s3://team6-project-288469846191-eu-north-1-an/models/financial_clustering/k_selection/v2/run_id=20260725T153022Z/
```

主要文件：

```text
financial_cluster_model.joblib
experiment_config.json
cluster_name_mapping.json
```

---

## 15. 下一步

1. 固定五个正式英文Cluster名称；
2. 生成最终公司级Financial Cluster主表；
3. 为每家公司保留Cluster、assignment margin、confidence和reason codes；
4. 深入分析`Cluster × Sector × Account Category`；
5. 与BB / SME / Mid Corporate分类结果交叉；
6. 构建Financial capacity、Financing need、Financial risk和Data confidence；
7. 接入News和Hiring维度；
8. 设计Tableau Cluster分布、画像、行业、风险和转移Dashboard；
9. 在新财务快照到达后执行Cluster drift和稳定性监控。

