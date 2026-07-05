---
name: pain-miner
description: >
  Domain-agnostic community pain-point mining → micro-product ideation. Input any target
  user description; run full pipeline A (discover communities) + B (hot-post evidence) +
  C (5 product ideas + best pick + 10 hooks). Multi-platform with source labels: Reddit,
  Hacker News, V2EX; browser fallback when APIs fail (login-free only). Use when user asks
  找痛点、目标用户痛点、社区挖掘、subreddit、50+赞、数字产品创意、文案钩子、痛点→产品、
  pain mining、product ideas from communities, or runs /pain-miner. NOT for deep industry
  reports (hotspot-research) or final copy polish (renhua).
---

# Pain Miner — 任意目标用户 · 痛点挖掘 → 微型产品创意

**输入**：一句目标用户描述（领域不限）  
**输出**：Step A 社区发现 + Step B 热帖取证 + Step C 创意交付（一次交付，多平台注明来源）

默认路径 **全部免登录**；仅当用户桌面已登录 Reddit 时，可选用 OpenCLI（非默认）。

---

## 默认工作流（用户只说目标用户时，直接跑全流程）

```text
1. 解析目标用户 → plan-communities（或由 Agent 补充/修正社区列表）
2. run 脚本 → 拿 JSON（A+B 结构化证据）
3. Agent 读 JSON → 写 Step C + 按模板输出完整 Markdown
```

**一键命令**：

```bash
# 技能目录下执行；或替换为你的安装路径（如 ~/.grok/skills/pain-miner）
python3 scripts/pain_miner.py run \
  --target "独立游戏开发者" \
  --hours 72 --min-score 50 --min-comments 20 \
  --fetch-comments \
  --out /tmp/pain-miner-run.json
```

可选覆盖（Agent 推断不准时）：

```bash
# 技能目录下执行；或替换为你的安装路径（如 ~/.grok/skills/pain-miner）
python3 scripts/pain_miner.py run \
  --target "新手父母" \
  --subs Parenting,Mommit,daddit \
  --hn-query "parenting startup" \
  --v2ex-node life,share \
  --fetch-comments --out /tmp/pain-miner-run.json
```

**禁止**：跳过脚本直接编造帖子；未满足阈值混入热帖表；创意无法对应证据帖。

---

## Step 0 — 解析目标用户（Agent，脚本前）

从用户描述提取并写入交付开头：

| 维度 | 示例 |
|---|---|
| **谁** | 独立开发者 / 新手父母 / 负债年轻人 / 跨境卖家 |
| **场景** | 获客、带娃睡眠、记账、部署、选题 |
| **语言** | 中文 → 启用 V2EX；英文 → Reddit + HN |
| **平台偏好** | 用户指定则优先；否则按语言自动 |

运行 `plan-communities` 预览推断结果，**Agent 必须核对 sub 名称是否真实存在**，不合理则修正 `--subs`：

```bash
python3 scripts/pain_miner.py plan-communities \
  --target "跨境独立站卖家" --out /tmp/pain-plan.json
```

---

## Step A — 发现目标社区

### 筛选条件（默认，用户可改）

- Reddit：成员 ≥ **10,000**
- 窗口：**24–72h** 内有新帖
- 活跃：72h 总评论 ≥ 30，或高互动帖(≥3评) ≥ 5
- HN/V2EX：按各自阈值，**单独成表**，字段含 `platform`

### 热度指数（Reddit 横向比较）

```text
heat = posts_72h × 2 + comments_72h ÷ 4 + score_72h ÷ 30 + active_threads_ge3 × 3
```

### Step A 交付字段

每个社区一行：**平台 · 社区名 · 成员/活跃度 · 热门痛点主题 · 示例帖**。

---

## Step B — 热帖取证

### 阈值（默认）

- `min_score = 50`，`min_comments = 20`，窗口 72h

### 平台路由（免登录优先，见 `references/platforms.md`）

| 顺序 | 平台 | 方式 | 登录 |
|---|---|---|---|
| 1 | Reddit | Arctic Shift API | ✅ 免登录 |
| 2 | Hacker News | Algolia + Firebase | ✅ 免登录 |
| 3 | V2EX | 公开 API | ✅ 免登录 |
| 4 | **浏览器兜底** | Jina Reader `r.jina.ai` / old.reddit 公开页 | ✅ 免登录 |
| 5 | pullpush.io | 最后兜底 | ✅ 免登录（易 429） |
| — | OpenCLI / agent-reach | 仅用户已登录 Reddit 时 | ⚠️ 需登录，非默认 |

### 浏览器兜底（API 失败或热帖不足时）

触发条件（任一）：
- Arctic Shift 422/超时，且 pullpush 也失败
- `run` 总热帖 < `min_total_posts`（默认 5）
- 评论 API 空，需补读公开讨论页

**允许读**（免登录公开页）：
```bash
# Jina Reader（脚本 browser-read 子命令）
python3 scripts/pain_miner.py browser-read \
  --url "https://old.reddit.com/r/SaaS/comments/xxxxx/"

# 或 Agent 用内置浏览器打开同一 URL
```

**禁止**：要求用户登录；读 cookie 私有页；编造评论。

### 结构化字段（每条热帖，必须含 `platform`）

| 字段 | 规则 |
|---|---|
| platform | `reddit` / `hackernews` / `v2ex` / `browser` |
| 社区 | r/xxx · HN · V2EX/节点名 |
| 痛点原文 | OP 正文前 280 字；无则标题 |
| 他们试过的 | 仅从正文/评论提取；无则「正文未提及」 |
| 想要什么 | 标题问句或 OP 明确目标 |
| 热门评论短语 ×3 | 高赞评论；缺失标注「评论未返回」 |

### 分步命令（调试 / 单平台）

```bash
python3 scripts/pain_miner.py discover \
  --subs SaaS,Entrepreneur,SideProject --hours 72 --out /tmp/a.json

python3 scripts/pain_miner.py extract \
  --subs SaaS,SideProject --fetch-comments --out /tmp/b.json

python3 scripts/pain_miner.py hn-search \
  --query "indie saas" --hours 168 --min-score 30 --min-comments 15

python3 scripts/pain_miner.py v2ex-hot --node create
```

---

## Step C — 痛点聚类与创意（Agent，读 `run` JSON 后执行）

### C1 聚类（6–8 簇，领域中立示例）

- 工具摩擦 / 工作流断裂
- 信息过载 / 不知如何选择
- 成本焦虑 / 订阅疲劳
- 学习曲线陡 / 无人带入门
- 质量不信任 / 踩坑复盘
- 孤独感 / 缺同行反馈

每簇：**平台 · 代表帖链接 · 一句痛点原文**。

### C2 理想状态（5 条）

用户语言描述「他们想变成什么样」。

### C3 五个小型数字产品

| 项 | 要求 |
|---|---|
| 名字 | 简短可传播 |
| 形式 | 模板 / Skill / 计算器 / 清单 / 微型 SaaS |
| 承诺 | 可验证，不夸大 |
| 映射痛点 | 标明簇名 + **平台来源帖** |

### C4 最优方案 + 定价三档

结合用户现有能力（上下文有技能/知识库则对齐）。

### C5 十个文案钩子

- 5 痛点钩 + 5 卖点钩（可用 renhua 润色）

### 可选落盘

`02_Raw/Resources/工作流/YYYY-MM-DD-pain-miner-{主题}.md`（用户要求时）

---

## 补充平台准入（仅免登录）

| 平台 | 状态 | 适用 |
|---|---|---|
| Reddit (Arctic Shift) | ✅ 主源 | 英文垂直社区，覆盖面最广 |
| Hacker News | ✅ 补充 | 开发者 / SaaS / 创业者 |
| V2EX | ✅ 补充 | 中文技术人 / 创作者 |
| 浏览器 (Jina/old.reddit) | ✅ 兜底 | API 失败时读公开页 |
| pullpush | ⚠️ 末位兜底 | 易 429 |
| OpenCLI Reddit | ⚠️ 可选 | 需桌面已登录，非默认 |
| Twitter/X | ❌ | 需 cookie |
| LinkedIn / 小红书 | ❌ | 需登录或 token |

---

## 限流与失败处理

| 症状 | 动作 |
|---|---|
| Arctic Shift 422 | `limit=50` 重试；仍失败标 `skipped` |
| pullpush 429 | 停止；改 Arctic Shift 或浏览器兜底 |
| 评论 API 空 | 保留热帖；`browser-read` 补读；不虚构 |
| 总热帖不足 | 浏览器读 `plan.browser_fallback_urls`；仍不足则**向用户确认**是否放宽阈值 |
| 推断 sub 不存在 | Agent 修正 `--subs` 后重跑 |

---

## 质量门禁（交付前自检）

- [ ] 一次响应含 Step A + B + C（除非用户只要某步）
- [ ] 每条证据有 **platform** 列/字段
- [ ] 链接可点击；赞评为取证快照，标注窗口与数据源
- [ ] 5 创意均能指向具体帖（含平台）
- [ ] 10 钩子：痛点 5 + 卖点 5
- [ ] 未使用需登录平台作为默认路径

---

## 相关技能

| 技能 | 关系 |
|---|---|
| `agent-reach` | 多平台路由；OpenCLI 仅作已登录备选 |
| `renhua` | Step C 钩子去 AI 味 |
| `hotspot-research` | 行业深度报告，非社区痛点 |

## 参考文件

- [`references/platforms.md`](references/platforms.md) — API、登录对照、浏览器兜底
- [`references/output-templates.md`](references/output-templates.md) — 全流程交付模板
- [`scripts/pain_miner.py`](scripts/pain_miner.py) — `plan-communities` / `run` / 分步子命令