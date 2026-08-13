# Financial Scoring Rule Pack — FIN_BASE_V1.0

## 目的

本配置包定义基于公开财务数据的 Deepen、Grow、Defend 三维基础代理分数，并预注册多组权重实验。它不使用 Cluster 或 T 级调整，不使用新闻和招聘数据，也不声称预测真实 Lloyds 产品需求。

## 权重实验

当前固定六组候选方案：

1. `EW`：三个 Block 等权，作为最少主观假设的基线；
2. `BASE`：理论基准方案；
3. `STATIC_FOCUS`：提高当前静态状态或承载能力权重；
4. `DYNAMIC_FOCUS`：提高最近变化和风险轨迹权重；
5. `CONSERVATIVE`：降低 C 级条件交互和重复计分风险；
6. `OPPORTUNITY_FOCUS`：提高 Deepen/Grow 的活动和扩张动量权重。

方案按 Deepen、Grow、Defend 分别选择，不强制三个维度使用同一个最终 Scenario。

## 文件

- `model.yaml`：模型边界、时间规则、标准化、缺失处理和选择原则；
- `signals.csv`：一行一条有效评分规则；
- `weight_scenarios.csv`：六组预定义 Block 权重；
- `excluded_signals.csv`：不进入基础分的字段及允许用途；
- `evidence.csv`：规则依据和限制；
- `validation_plan.yaml`：在实验前固定的比较与选择协议；
- `financial_scoring_rulebook_v1.xlsx`：便于人工审阅的格式化工作簿；
- `CHANGELOG.md`：版本变更记录。

## 选择原则

不构造另一个带主观权重的“综合最优分”。选择采用顺序门槛：

1. 淘汰逻辑、覆盖率、时间泄漏或指标支配检查不合格的方案；
2. 比较排名稳定性；
3. 对 Grow 和 Defend 比较历史代理结果；
4. 若候选方案的历史表现差异处于重叠置信区间内，优先选择 `EW` 或 `BASE`；
5. Deepen 因缺少真实标签，主要依据稳健性、可解释性和专家案例审查。

## 当前状态

`draft`。完成结构审查、敏感性实验和历史代理回测后才能升级为 `approved_v1`。

