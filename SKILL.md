---
name: pain-miner
description: >
  Evidence-driven community pain research for product discovery. Runs public Reddit,
  Hacker News and V2EX collection; profiles communities, labels intent and relevance,
  and renders a source-linked nine-section report. Use for pain mining, user research,
  community evidence, micro-SaaS discovery, or product opportunity validation.
---

# Pain Miner

**输入**：一句目标用户描述。
**最终输出**：九节、来源可追溯的研究报告；不是旧式 `Step A/B/C` 交付。

默认路径免登录。Reddit、HN、V2EX 的可用性取决于网络环境，工具会把失败和样本边界写入结果。

## 标准工作流

```bash
python3 scripts/pain_miner.py diagnose --out /tmp/pain-diagnose.json

python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 336 --min-score 10 --min-comments 5 \
  --profile-communities --fetch-comments --analyze \
  --out /tmp/pain-run.json

python3 scripts/pain_miner.py render-report \
  --input /tmp/pain-run.json --out /tmp/pain-report.md
```

先读 `/tmp/pain-report.md`，再在其中已有证据范围内补充写作；不要手工将 JSON 重组为流程型标题。

`run --analyze` 在主证据不足时仍会写 JSON，但返回码为 `2`，并将 `analysis.evidence_verdict.status` 置为 `INSUFFICIENT_EVIDENCE`。这不是“没有痛点”的结论，而是当前采样不能支持机会判断。

## 运行前：目标与社区计划

```bash
python3 scripts/pain_miner.py plan-communities \
  --target "独立 SaaS 创业者" --profile-communities \
  --out /tmp/pain-plan.json
```

- 检查 `reddit_subs`、`hn_queries`、`v2ex_nodes` 与 `confidence`。
- 中文目标出现 `SaaS`、`indie`、`独立开发` 等线索时必须保持 `languages: [zh, en]`；不得因中文输入而把英文社区和 HN 排除。
- SaaS/独立开发默认优先 `SaaS`、`indiehackers`、`SideProject`、`EntrepreneurRideAlong` 与 V2EX `create/share`；`career` 只能是显式补充，不得作为主证据。
- 推断不对时用 `--subs`、`--hn-query`、`--v2ex-node` 覆盖，并在报告范围中说明。

## 数据源健康与降级

先运行 `diagnose`，检查 `source_health`：

| 状态 | 动作 |
|---|---|
| `ok` | 正常收集；仍需按相关性和证据类型过滤。 |
| `degraded` | 记录原因，扩大窗口或调整阈值，不把 0 hit 解读为无需求。 |
| `unavailable` / `reddit_edge_block` | 不重复请求同一 Reddit 路径；转 HN-first，并把故障写入报告。 |
| `rate_limited` | 停止重试该源，遵守退避与间隔。 |
| `empty` | 区分“源为空”与“请求失败”；检查计划与时间窗。 |

当 Reddit 合格帖少于 3 且 HN 可用时，`run` 会一次性扩展已有的目标相关 HN 查询。不要用泛化的 `Show HN`、`MRR` 单词替代目标词；优先 `indie hacker`、`micro saas`、`solo founder first customers` 等模板。

浏览器/Jina 若返回 `whoa there, pardner`、`network policy` 或 `Blocked`，会标为失败而非成功正文。不得从拦截页提取证据。

## 证据与质量门禁

每条帖子均保留：

- `platform`、`community`、`url`、`data_source`、抓取快照；
- `post_intent`、`commercial_signals`、`evidence_type`、`risk_flags`；
- `target_relevance: high | low | unknown`。

默认规则：

1. `target_relevance=low` 帖子进入 `step_b.noise_posts` 与 `analysis.posts` 审计，不进入痛点簇和 OpportunityCard。
2. `promotion` / `commercially_contaminated`、纯行业观点和单条反证不能独立支撑产品方向。
3. 少于 `--min-primary-evidence`（默认 5）条目标相关 `primary_evidence` 时，机会卡必须为空；报告在第 1 节和第 9 节说明不足与后续动作。
4. 不得把热度、回复数或规则分类压成不透明的“机会总分”。

## 最终报告契约

只允许以下九个顶级标题：

1. 研究范围
2. 社区地图
3. 高价值证据
4. 痛点结构
5. 跨社区共识与分歧
6. 商业信号
7. 候选产品方向
8. 推荐验证方案
9. 证据附录

第 9 节必须含数据限制和 `source_health`；证据不足时还要含可执行的下一步。完整字段映射见 [`references/output-templates.md`](references/output-templates.md)。

## 分命令调试

```bash
python3 scripts/pain_miner.py discover --subs SaaS,indiehackers --hours 336
python3 scripts/pain_miner.py extract --subs SaaS,SideProject --hours 336 --min-score 10 --min-comments 5
python3 scripts/pain_miner.py hn-search --query "indie hacker" --hours 336 --min-score 10 --min-comments 5
python3 scripts/pain_miner.py v2ex-hot --node create --min-comments 5
python3 scripts/pain_miner.py compare-communities --input /tmp/pain-run.json --topic "customer feedback"
```

`analyze-research` 可以离线补齐分析；`render-report` 是唯一的完整 Markdown 输出器。

## 交付前自检

- [ ] 已执行 `diagnose` 或在报告中说明未探测的源。
- [ ] 已运行 `render-report`，最终标题没有 `Step A`、`Step B`、`Step C`。
- [ ] 每个结论都能回链到目标相关的来源帖。
- [ ] 已区分支持证据、反证、推广污染和低相关噪声。
- [ ] `INSUFFICIENT_EVIDENCE` 时没有产品机会、定价或营销钩子。
- [ ] 单一社区观察没有外推为普遍结论。
