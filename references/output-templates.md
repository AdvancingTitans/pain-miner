# Pain Miner — 输出模板（v2 · 全流程一次交付）

## 全流程总览（`render-report` 的直接输出结构）

```markdown
# 痛点挖掘报告：{目标用户}

## 元信息

- **目标用户**：{一句}
- **解析**：谁 / 场景 / 语言
- **窗口**：过去 {N} 小时（{ISO_START} – {ISO_END}）
- **阈值**：赞 ≥ {min_score} · 评 ≥ {min_comments}
- **数据源**：Reddit (Arctic Shift) · HN · V2EX · 浏览器兜底（如有）
- **登录**：全程免登录

---

## Step A — 合格社区（{K} 个）

| 平台 | 社区 | 规模/活跃 | 热度 | 热门痛点主题 | 示例帖 |
|---|---|---|---:|---|---|
| reddit | r/SaaS | 89K · 72帖/1132评 | 591 | 获客/定价 | *Why is churn…* |
| hackernews | HN | — | — | 独立开发 | *Ask HN: …* |
| v2ex | create | — | — | 副业变现 | *独立开发…* |

对每个 Reddit 社区追加独立判断：`relevance` · `activity` · `research_fit` · `signal_quality`，并写出 `member_tier`、主要人群、讨论风格、公开规则带来的研究边界与偏差风险。不得合成为机会总分。

---

## Step B — 热帖取证（{M} 条）

赞 ≥ {min_score} · 评 ≥ {min_comments} · 窗口 {hours}h

| 平台 | 社区 | 意图 | 证据类型/风险 | 标题 | 链接 | 赞 | 评 | 痛点原文 | 当前/临时方案 | 想要什么 | 热门评论×3 |
|---|---|---|---|---|---|---:|---:|---|---|---|---|
| reddit | r/SideProject | alternative_search | primary_evidence | … | [链接](url) | 65 | 123 | 「…」 | … | … | ①… ②… ③… |
| hackernews | HN | meta_discussion | context_evidence | … | [讨论](url) | 120 | 89 | 「…」 | — | … | — |
| v2ex | create | workaround_share | primary_evidence | … | [链接](url) | — | 45 | 「…」 | 手工表格 | … | — |

可选分表：
- **痛点强相关**
- **新闻/噪声**（宏观/教程帖，降权）

---

## Step C — 创意交付（需要营销文案时由 Agent 在证据范围内补充）

在写作前读取 `analysis.deduplication`、`analysis.pain_clusters`、`analysis.community_comparisons` 与 `analysis.opportunities`。重复内容保留在证据附录但不重复计数；作者字段仅是本次公开样本的弱上下文。

### 痛点结构

| # | 痛点领域 → 任务场景 → 具体障碍 | 平台 · 社区 · 代表帖 |
|---|---|---|
| 1 | 反馈管理 → 整理多渠道反馈 → 无法发现重复需求 | reddit · r/SaaS · [链接](url) |

### 跨社区共识与反证

- **共同确认的问题**：来自 `compare-communities.shared_pains`，标注各社区与来源帖。
- **社区差异**：角色、主导意图、当前方案与反对意见。
- **反证/边界**：单独列出 `counter_evidence` 与 `commercially_contaminated`，不混入支持证据。
- **可能根因**：没有明确证据时写「未知，待验证」。

### 理想状态（5 条）

1. …

### 五个候选机会与最小验证

| # | 名字 | 形式 | 承诺 | 对应痛点（含平台） |
|---|---|---|---|---|
| 1 | … | 清单 | … | P1 · reddit |

每个机会下补充：支持证据、反证/适用边界、已有替代方案、仍未解决的问题、最小验证动作（对象、成功信号、放弃条件）。

### 最优方案

**名称**：…  
**形态**：…

#### 五个要点
1. …

#### 定价
| 层级 | 内容 | 价格 |
|---|---|---|

### 十个文案钩子

#### 痛点钩（5）
1. …

#### 卖点钩（5）
6. …

---

## 取证说明

- 评论缺失帖已标注「评论未返回」
- 浏览器兜底帖标注 `data_source: browser/jina`
- 未满足阈值的帖子未列入上表
```

---

## Step A — 仅社区发现（分步交付时用）

```markdown
## 目标用户与窗口

- **目标用户**：（一句）
- **平台计划**：Reddit {subs} · HN {queries} · V2EX {nodes}
- **窗口**：过去 {N} 小时
- **数据源**：（平台列表，注明是否免登录）

## 合格社区（{K} 个）

| 平台 | 社区 | 成员 | 72h发帖 | 72h评论 | 均评/帖 | 热度 | 热门痛点主题 | 示例帖 |
|---|---|---:|---:|---:|---:|---:|---|---|
```

---

## Step B — 仅热帖取证（分步交付时用）

表头必须含 **平台** 列（见全流程模板 Step B）。

---

## Step C — 仅创意（分步交付时用）

见全流程模板 Step C；每条创意 **对应痛点** 列必须含平台来源。

---

## JSON → Markdown 映射（Agent 读 `run` 输出时）

| JSON 路径 | Markdown 区块 |
|---|---|
| `plan` | 元信息 · 平台计划 |
| `step_a.qualified_communities` | Step A 表 |
| `step_b.posts` | Step B 表（按 `platform` 分组或混排但保留平台列） |
| `step_b.browser_fallback` | 取证说明 |
| `step_b.posts[].post_intent` / `commercial_signals` / `evidence_type` / `risk_flags` | Step B 的意图、商业与风险列 |
| `analysis.pain_clusters` / `community_comparisons` / `opportunities` | Step C 的痛点结构、共识分歧与验证卡 |
| `render-report` | 研究范围、社区地图、证据、痛点结构、跨社区对照、商业信号、机会、验证与附录 |
| Agent 生成 | 在上述证据边界内扩展为文案、命名与定价 |
