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

1. **发现**他们在哪些社区活跃（Reddit / Hacker News / V2EX）
2. **取证**高赞高评的真实帖子与评论
3. **产出**（配合 AI）痛点聚类、5 个产品创意、最优方案、10 条文案钩子

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

### 方式二：命令行一键跑（只要结构化证据）

```bash
python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 168 \
  --min-score 30 \
  --min-comments 15 \
  --fetch-comments \
  --out result.json
```

终端会输出 JSON，包含社区发现（Step A）和热帖取证（Step B）。  
Step C（创意、定价、钩子）需要你自己分析 JSON，或交给 AI 读 `result.json` 继续写。

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

**AI 读 JSON 后产出的报告结构（节选）：**

```markdown
# 痛点挖掘报告：独立 SaaS 创业者

## Step A — 合格社区
| 平台 | 社区 | 热门痛点主题 |
| reddit | r/startups | 获客难、冷启动 |
| reddit | r/Entrepreneur | 找合伙人、定价迷茫 |

## Step B — 热帖取证
| 平台 | 标题 | 赞 | 评 | 痛点原文 |
| reddit | I built a SaaS but nobody uses it | 89 | 67 | 「花了 6 个月做产品，上线后零付费用户…」 |

## Step C — 创意交付
### 五个小型数字产品
1. **客户对话剧本本** — Notion 模板 + 15 张提问卡，¥49 起
2. **冷启动检查清单** — 上线前 30 项自检
…

### 十个文案钩子
- 痛点钩：「产品做完了，第一个付费用户在哪？」
- 卖点钩：「15 个问题，摸清用户愿不愿意掏钱」
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
| `--no-hn` / `--no-v2ex` | — | 跳过补充平台 |

中文目标用户会自动启用 V2EX；英文目标以 Reddit + HN 为主。

---

## 输出 JSON 结构

`run` 命令的 JSON 分三块，方便 AI 或你自己解析：

```json
{
  "target": "独立 SaaS 创业者",
  "plan": { "reddit_subs": ["SaaS", "Entrepreneur"], "v2ex_nodes": ["create"] },
  "step_a": { "qualified_communities": [ /* 合格社区列表 */ ] },
  "step_b": { "posts": [ /* 热帖，每条含 platform / url / score / pain_themes */ ] },
  "total_posts": 7
}
```

每条热帖必有 `platform` 字段（`reddit` / `hackernews` / `v2ex`），创意必须能回溯到具体帖子。

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
A: 阈值太严或该窗口内社区不活跃。试试 `--min-score 30 --min-comments 15 --hours 168`，或手动 `--subs` 换社区。

**Q: 评论是空的？**  
A: Arctic Shift 部分帖子评论 API 会 422。加 `--fetch-comments` 后脚本会尝试 Jina 读公开页；仍缺失会标空，不会编造。

**Q: 只有 JSON，没有创意报告？**  
A: 脚本负责 A+B 取证；C（聚类、5 创意、钩子）设计给 AI 读 JSON 后生成。把 `result.json` 丢给你的 Agent，或参考 [`references/output-templates.md`](references/output-templates.md)。

**Q: 和 hotspot-research 有什么区别？**  
A: Pain Miner 从**社区讨论**挖用户痛点 → 微型产品；hotspot-research 做**行业深度报告**。前者偏「卖什么小产品」，后者偏「这个赛道怎么回事」。

---

## 仓库结构

```text
pain-miner/
├── README.md              ← 你正在看的用户指南
├── SKILL.md               ← AI Agent 工作流说明
├── scripts/pain_miner.py  ← 主脚本
├── references/            ← 平台路由、输出模板
└── examples/              ← 真实跑出来的样例 JSON
```

---

## License

MIT — 见 [LICENSE](LICENSE)
