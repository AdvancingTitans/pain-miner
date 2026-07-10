# Pain Miner — 研究报告契约（v2.3）

`render-report` 是完整交付的唯一 Markdown 模板。采集管道内部可保留社区规划、取证和分析阶段，但**不得**把它们作为用户报告中的 `Step A / B / C` 标题。

```markdown
# 痛点研究报告：{目标用户}

## 1. 研究范围
- 目标用户、角色、任务线索、语言
- 时间窗口、平台、阈值
- 研究判定：`READY` 或 `INSUFFICIENT_EVIDENCE`

## 2. 社区地图
| 社区 | 规模层级 | 活跃度 | 相关度 | 研究适配 | 信号质量 | 偏差风险 |

## 3. 高价值证据
| 意图 | 社区 | 用户原话摘要 | 当前方案 | 想要结果 | 证据类型/风险 |

只列 `target_relevance != low` 的帖子；低相关帖子保留在 JSON 审计，不得支撑结论。

## 4. 痛点结构
每项按「痛点领域 → 任务场景 → 具体障碍」展示，并附信号面板与来源。

## 5. 跨社区共识与分歧
列出共同痛点、社区差异、反证和可引用来源。单一社区或样本不足时明确 `not_applicable_or_insufficient_cross_community_evidence`。

## 6. 商业信号
说明替代品搜索、付费意愿、现有方案不满与临时方案成本；不得使用单一机会总分。

## 7. 候选产品方向
每张 OpportunityCard 必含：目标任务、支持证据、反证/边界、已有替代方案、未解决问题。
只有 `evidence_verdict.status = READY` 才能出现本节的候选方向。

## 8. 推荐验证方案
每个候选给出 concierge test、行动、成功信号和放弃信号。

## 9. 证据附录
- 每条来源的链接、平台、社区、数据源与抓取时间
- 数据限制
- `source_health` 数据源健康度
- 当证据不足时，固定输出下一步取证动作
```

## JSON → Markdown 映射

| JSON 路径 | 报告区块 |
|---|---|
| `target_profile` / `research_scope` / `filters` / `analysis.evidence_verdict` | 1. 研究范围 |
| `step_a.community_profiles` / `qualified_communities` | 2. 社区地图 |
| `analysis.posts`（排除 `target_relevance=low`） | 3. 高价值证据、9. 证据附录 |
| `analysis.pain_clusters` | 4. 痛点结构、6. 商业信号 |
| `analysis.community_comparisons` / `community_comparisons_status` | 5. 跨社区共识与分歧 |
| `analysis.opportunities` | 7. 候选产品方向、8. 推荐验证方案 |
| `source_health` / `analysis.limitations` / `analysis.evidence_verdict.next_actions` | 9. 证据附录 |

## Agent 规则

- 必须优先运行 `render-report`，再做证据范围内的文字润色。
- 不得从采集阶段名称复制出 `Step A / B / C` 标题。
- `INSUFFICIENT_EVIDENCE` 时不得补写产品名、定价、营销钩子或“最优方案”。
- `commercially_contaminated`、`context_evidence` 和低相关帖子不能单独构成支持证据。
