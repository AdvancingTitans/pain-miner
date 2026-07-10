# Pain Miner

**Community pain-point mining CLI and AI-agent skill for finding micro-SaaS and indie product ideas.**

从 Reddit、Hacker News、V2EX 等公开社区热帖里挖真实痛点，产出可卖的微型产品创意。

```bash
python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 168 \
  --fetch-comments \
  --out result.json
```

Use it when you need evidence before building: who is complaining, where they complain, which posts got attention, and what small product could plausibly solve the pain.

## Why Star This Repo

- Turns community discussion into structured product-research evidence.
- Default no-login workflow: Reddit archive/API paths, Hacker News, V2EX, and public-page fallback.
- Works as a plain Python CLI or as an AI-agent skill.
- Designed for indie hackers, micro-SaaS builders, product researchers, and content strategists.

More AdvancingTitans agent tools: [`awesome-ai-agent-research-tools`](https://github.com/AdvancingTitans/awesome-ai-agent-research-tools).

你只需描述目标用户（例如「独立 SaaS 创业者」「新手父母」「跨境卖家」），Pain Miner 会：

1. **发现并画像**他们在哪些社区活跃（Reddit / Hacker News / V2EX）
2. **取证**高赞高评的真实帖子与评论，并标注意图、商业信号与可观测风险
3. **对照**同一主题在不同社区中的共识与分歧
4. **产出**（配合 AI）可回溯的痛点结构、候选机会、反证与最小验证方案

全程**默认免登录**，不需要 Reddit 账号或 API Key。

---

## 快速开始

### 环境要求

- Python 3.10+
- 网络可访问 Reddit（Arctic Shift）、HN、V2EX

```bash
git clone https://github.com/AdvancingTitans/pain-miner.git
cd pain-miner
```

### 方式一：配 AI Agent 使用（推荐）

把本仓库装进你的 Agent 技能目录，然后直接对 AI 说：

```text
用 pain-miner 帮我挖一下「独立 SaaS 创业者」的痛点，给产品创意
```

Agent 会读取 [`SKILL.md`](SKILL.md)，自动跑脚本拿证据，再生成完整 Markdown 报告。

**Grok / Cursor 安装示例：**

```bash
# Grok
cp -r pain-miner ~/.grok/skills/pain-miner

# 或软链，方便同步更新
ln -sf "$(pwd)" ~/.grok/skills/pain-miner
```

### 方式二：命令行一键跑（结构化证据 + 完整报告）

```bash
python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 168 \
  --min-score 30 \
  --min-comments 15 \
  --profile-communities \
  --analyze \
  --fetch-comments \
  --out result.json
```

先得到可审计 JSON，再将其渲染成完整的九节 Markdown 报告：

`--analyze` 会将去重、痛点信号面板、三级痛点结构、跨社区对照和候选 OpportunityCard 一并写入 `analysis`；不产生不透明的综合机会分。已有 JSON 也可离线补分析：

```bash
python3 scripts/pain_miner.py analyze-research --input result.json --out research.json
python3 scripts/pain_miner.py render-report --input result.json --out report.md
```

`render-report` 是完整 Markdown 交付的唯一结构：研究范围、社区地图、高价值证据、三级痛点结构、跨社区共识与分歧、商业信号、候选机会、验证方案与证据附录。它不会在缺少证据时捏造结论；`INSUFFICIENT_EVIDENCE` 时机会卡为空，并列出下一步取证动作。AI 可以在此基础上再写创意文案，但必须保留来源帖和反证。

### 方式三：分步调试

```bash
# 预览会扫哪些社区
python3 scripts/pain_miner.py plan-communities --target "新手父母"

# 只扫 Reddit 社区活跃度
python3 scripts/pain_miner.py discover --subs Parenting,Mommit,daddit --hours 72

# 只抽热帖
python3 scripts/pain_miner.py extract --subs SaaS,SideProject --fetch-comments --out hot.json

# 补充 HN / V2EX
python3 scripts/pain_miner.py hn-search --query "indie saas" --hours 168
python3 scripts/pain_miner.py v2ex-hot --node create
```

需要判断候选社区是否适合当前研究任务时，追加公开画像（默认缓存到 `.pain-miner-cache/communities/`）：

```bash
python3 scripts/pain_miner.py plan-communities \
  --target "独立 SaaS 创业者" --profile-communities

python3 scripts/pain_miner.py profile-community --platform reddit --community SaaS
```

画像分别给出 `relevance`、`activity`、`research_fit`、`signal_quality`，不会压成一个主观总分。成员规模也不再是硬门槛：小而专的社区会标为 `small_expert`，仍可作为研究样本。

---

## 示例

### 示例 1：独立 SaaS 创业者

**你对 AI 说：**

> 帮我用 pain-miner 调研独立 SaaS 创业者的痛点，要完整报告。

**脚本实际执行：**

```bash
python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 168 --min-score 30 --min-comments 15 \
  --fetch-comments \
  --out examples/saas-founder-run.json
```

**推断出的扫描计划（节选）：**

| 平台 | 扫描目标 |
|---|---|
| Reddit | r/SaaS, r/Entrepreneur, r/startups, r/webdev, r/SideProject |
| Hacker News | `saas founder`, `indie hacker` |
| V2EX | programmer, create, cloud, career |

**一次跑出来的结果（2026-07-05 快照）：**

- 合格社区 4 个：r/Entrepreneur、r/startups、r/webdev、r/programming
- 热帖 7 条（Reddit 4 + V2EX 3）
- 完整 JSON 见 [`examples/saas-founder-run.json`](examples/saas-founder-run.json)

**`render-report` 生成的报告结构（节选）：**

```markdown
# 痛点研究报告：独立 SaaS 创业者

## 1. 研究范围
- 研究判定：READY（主证据 7 / 最低 5）
- 数据源：Reddit、Hacker News、V2EX；窗口、阈值和健康度均保留在报告内

## 3. 高价值证据
| 意图 | 社区 | 用户原话摘要 | 当前方案 | 想要结果 | 证据类型/风险 |
| complaint | r/SaaS | [来源帖](url)：上线后没有付费用户 | 手工获客 | 稳定首批客户 | primary_evidence / unknown |

## 7. 候选产品方向
### Help 独立 SaaS 创业者 address 获客
- 支持证据、反证/边界、现有替代方案与未解决问题

## 9. 证据附录
- 逐帖来源、数据限制和 `source_health`
```

> 小社区（如 r/SaaS）在严格阈值下可能 0 条热帖，属正常现象。可放宽 `--min-score` / `--min-comments`，或手动指定 `--subs`。

### 示例 2：手动指定社区

当自动推断不准时，覆盖社区列表：

```bash
python3 scripts/pain_miner.py run \
  --target "跨境独立站卖家" \
  --subs ecommerce,shopify,FulfillmentByAmazon,Entrepreneur \
  --hn-query "shopify store|ecommerce startup" \
  --v2ex-node create,share \
  --fetch-comments \
  --out shopify.json
```

### 示例 3：只看计划、不爬数据

```bash
python3 scripts/pain_miner.py plan-communities --target "负债年轻人想理财"
```

输出会告诉你打算扫哪些 sub、HN 关键词、V2EX 节点，方便你先人工核对再跑 `run`。

---

### 跨社区对照

对 `run` 的 JSON 结果执行主题对照，避免把单一社区的文化或争论误判为普遍痛点：

```bash
python3 scripts/pain_miner.py compare-communities \
  --input result.json --topic "customer feedback management"
```

输出列出共享痛点、各社区的主导意图、当前方案与证据类型；根因保持 `unknown`，直到人工阅读引用证据和反证。

`plan-communities` 会生成按抱怨、求推荐、替代、迁移和付费意图组织的查询计划。需要扩大 HN 证据时，再显式启用：

```bash
python3 scripts/pain_miner.py run \
  --target "indie developers" --intent-query-expansion --max-hn-queries 6 --analyze
```

---

## 常用参数

| 参数 | 默认 | 说明 |
|---|---|---|
| `--target` | （必填） | 一句目标用户描述 |
| `--hours` | 72 | 时间窗口（小时） |
| `--min-score` | 50 | 最低赞数 |
| `--min-comments` | 20 | 最低评论数 |
| `--fetch-comments` | 关 | 拉取 Top 评论短语 |
| `--subs` | 自动推断 | 覆盖 Reddit 社区，逗号分隔 |
| `--hn-query` | 自动推断 | 覆盖 HN 搜索词，`\|` 分隔多个 |
| `--v2ex-node` | 自动推断 | 覆盖 V2EX 节点 |
| `--min-total-posts` | 5 | 热帖不足时触发浏览器兜底 |
| `--intents` | — | 只保留逗号分隔的帖子意图，如 `complaint,alternative_search` |
| `--analyze` | 关 | 在 `run` 输出中加入去重、痛点结构、信号面板与 OpportunityCard |
| `--profile-communities` | 关 | 在 `run` 中携带公开社区画像、规则摘要和四项独立研究判断 |
| `--intent-query-expansion` | 关 | 使用按需求表达生成的额外 HN 查询 |
| `--no-hn` / `--no-v2ex` | — | 跳过补充平台 |

中文目标用户会自动启用 V2EX；包含 SaaS、indie 或独立开发线索的中文目标同时保留英文 Reddit + HN 路由，避免被泛职场节点主导。

---

## 输出 JSON 结构

`run` 命令的 JSON 记录采集过程和最终研究结构；最终 Markdown 必须通过 `render-report` 生成：

```json
{
  "schema_version": "2.3",
  "target": "独立 SaaS 创业者",
  "plan": { "reddit_subs": ["SaaS", "Entrepreneur"], "v2ex_nodes": ["create"] },
  "step_a": { "qualified_communities": [ /* 合格社区列表 */ ] },
  "step_b": { "posts": [ /* 热帖，每条含 platform / url / score / pain_themes / post_intent / commercial_signals / evidence_type */ ] },
  "analysis": { "pain_clusters": [], "community_comparisons": [], "opportunities": [] },
  "source_health": { "arctic_shift": { "status": "ok" } },
  "total_posts": 7
}
```

每条热帖必有 `platform` 字段（`reddit` / `hackernews` / `v2ex`），并增量保留规则分类的 `post_intent`、`commercial_signals`、`evidence_type` 与 `risk_flags`。这些是弱信号：`unknown` 与风险标记必须如实展示，创意必须回溯到具体帖子。

---

## 数据源

| 平台 | 方式 | 登录 |
|---|---|---|
| Reddit | [Arctic Shift API](https://arctic-shift.photon-reddit.com/) | 免登录 |
| Hacker News | Algolia + Firebase API | 免登录 |
| V2EX | 公开 API | 免登录 |
| 浏览器兜底 | [Jina Reader](https://r.jina.ai/) | 免登录 |

Twitter / LinkedIn / 小红书**不纳入**（需登录）。

---

## 常见问题

**Q: 跑完热帖是 0 条？**  
A: 先运行 `python3 scripts/pain_miner.py diagnose`。`degraded` / `unavailable` 是当前网络或源的状态，不代表社区没有讨论。可扩到 `--hours 336`、适度降低阈值；Reddit 不可用而 HN 正常时会自动扩展 HN-first 查询。若 `run --analyze` 返回码为 2，请阅读报告的“证据不足：下一步”，不要强行生成产品结论。

**Q: 评论是空的？**  
A: Arctic Shift 部分帖子评论 API 会 422。加 `--fetch-comments` 后脚本会尝试 Jina 读公开页；仍缺失会标空，不会编造。

**Q: 如何生成完整报告？**
A: 运行 `python3 scripts/pain_miner.py render-report --input result.json --out report.md`。它会生成有来源帖、反证和验证动作的九节 Markdown 报告；需要营销文案时，再让 Agent 基于该报告创作，且不得脱离证据。

**Q: 和 hotspot-research 有什么区别？**  
A: Pain Miner 从**社区讨论**挖用户痛点 → 微型产品；hotspot-research 做**行业深度报告**。前者偏「卖什么小产品」，后者偏「这个赛道怎么回事」。

---

## 仓库结构

```text
pain-miner/
├── README.md              ← 你正在看的用户指南
├── SKILL.md               ← AI Agent 工作流说明
├── scripts/pain_miner.py  ← 主脚本
├── painminer/             ← 结构化分析与数据模型
├── tests/                 ← 离线回归测试
├── references/            ← 平台路由、输出模板
└── examples/              ← 真实跑出来的样例 JSON
```

---

## License

MIT — 见 [LICENSE](LICENSE)
