# Pain Miner — 平台路由参考（v2 · 免登录优先）

## 登录需求对照表

| 平台 | 默认路径 | 登录 | 备注 |
|---|---|---|---|
| Reddit · Arctic Shift | ✅ 主源 | 免登录 | 帖文稳定；部分评论 422 |
| Hacker News · Firebase/Algolia | ✅ 补充 | 免登录 | 官方 API |
| V2EX · 公开 API | ✅ 补充 | 免登录 | 中文社区 |
| 浏览器 · Jina Reader | ✅ 兜底 | 免登录 | `r.jina.ai/{url}` |
| 浏览器 · old.reddit.com | ✅ 兜底 | 免登录 | 公开帖/搜素页 |
| pullpush.io | ⚠️ 末位 | 免登录 | 易 429，间隔 ≥4s |
| OpenCLI / agent-reach Reddit | ⚠️ 可选 | **需登录** | 非默认；用户桌面已登录时用 |
| Twitter/X | ❌ 不纳入 | 需 cookie | |
| LinkedIn | ❌ 不纳入 | 需登录 | |
| 小红书 | ❌ 不纳入 | 需 token | |
| Reddit 匿名 .json | ❌ | 403 | |
| Dev.to / Lobsters | ❌ | 可访问但痛点密度低 | |

---

## Reddit（主源）— Arctic Shift

```bash
# 最新帖（需已知 subreddit 名）
GET https://arctic-shift.photon-reddit.com/api/posts/search?subreddit={SUB}&limit=100&sort=desc

# 评论
GET https://arctic-shift.photon-reddit.com/api/comments/search?link_id=t3_{POST_ID}&limit=100
```

| 字段 | 说明 |
|---|---|
| `subreddit_subscribers` | 成员数 |
| `score` / `ups` | 赞数 |
| `num_comments` | 评论数 |
| `selftext` | 正文 |
| `permalink` | → `https://www.reddit.com{permalink}` |

**限制**：无全局 sub 搜索 API → 社区发现靠 `plan-communities` 关键词推断 + Agent 修正 `--subs`。  
422 → `limit=50`；请求间隔 ≥ 1.2s。

### pullpush（末位兜底）

```bash
GET https://api.pullpush.io/reddit/search/submission/?subreddit={SUB}&size=50&sort=desc&sort_type=created_utc&after={UNIX}
```

连续 3 次 429 则放弃，改浏览器兜底。

### OpenCLI（可选，需登录）

```bash
agent-reach doctor --json   # reddit active_backend
opencli reddit subreddit-info {SUB} -f yaml
```

仅当用户环境已登录且 Arctic Shift 不可用。

---

## Hacker News（补充 ✅）

```bash
GET https://hn.algolia.com/api/v1/search?query={Q}&tags=story&numericFilters=created_at_i>{AFTER_UNIX}

GET https://hacker-news.firebaseio.com/v0/item/{ID}.json
```

| HN 字段 | 映射 |
|---|---|
| `points` / `score` | 赞数 |
| `num_comments` | 评论数 |
| `story_text` | Ask HN 正文 |

适用：SaaS、开发者工具、创业工作流。个人生活类密度低于 Reddit。

---

## V2EX（中文补充 ✅）

```bash
curl -s "https://www.v2ex.com/api/topics/hot.json" -H "User-Agent: pain-miner/2.0"
curl -s "https://www.v2ex.com/api/topics/show.json?node_name={NODE}&page=1" -H "User-Agent: pain-miner/2.0"
```

| 字段 | 映射 |
|---|---|
| `replies` | 回复数（作评论阈值） |
| `title` | 标题 |

常用节点：`create`, `career`, `programmer`, `cloud`, `life`, `share`, `finance`。

---

## 浏览器兜底（免登录）

### 何时触发

1. Arctic Shift + pullpush 均失败  
2. `run --min-total-posts` 未达标  
3. 评论 API 返回空，需补读讨论  

### Jina Reader（脚本内置）

```bash
python3 scripts/pain_miner.py browser-read \
  --url "https://old.reddit.com/r/SaaS/comments/abc123/title_here/"
```

底层：`GET https://r.jina.ai/{url}` — 将公开页转为可读 Markdown，**无需 API key**。

### Agent 内置浏览器

与 Jina 二选一；优先 Jina（确定性更好）。浏览器用于：
- `old.reddit.com/r/{sub}/top/?t=week`
- `hn.algolia.com` 搜索结果页
- `v2ex.com/go/{node}` 列表页

**禁止**：登录墙后的页面、私信、需 cookie 的 X/LinkedIn/小红书。

### plan 生成的兜底 URL

`plan-communities` 输出 `browser_fallback_urls`，`run` 在热帖不足时自动尝试读取。

### 社区画像的公开规则读取

`profile-community --platform reddit --community <sub>` 与 `plan-communities --profile-communities` 会读取近期公开帖子，并可通过 Jina 读取公开规则页 `old.reddit.com/r/<sub>/about/rules/`。它只记录规则中可见的商业表达限制；读取失败时字段为 `unknown`，不降级为登录或 Cookie 抓取。

---

## 多平台数据合并规范

JSON 中每条帖子必须有：

```json
{
  "platform": "reddit | hackernews | v2ex | browser",
  "community": "r/SaaS | Hacker News | V2EX/create",
  "data_source": "arctic-shift | hn.algolia.com | v2ex.com/api | browser/jina"
}
```

交付 Markdown 表头必须有 **平台** 列；Step C 创意映射需写明平台。

---

## 数据源标注（交付页脚）

```text
数据源：arctic-shift（Reddit 主）+ hn.algolia.com（HN）+ v2ex.com/api（V2EX，如有）
兜底：r.jina.ai（如有）
窗口：{ISO_START} – {ISO_END}（{N}h）
阈值：score ≥ {min_score}，comments ≥ {min_comments}
登录：全程免登录（或注明 OpenCLI 已登录备选）
```
