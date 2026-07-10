# Examples

## `saas-founder-run.json`

真实跑出来的样例，目标用户「独立 SaaS 创业者」：

```bash
python3 scripts/pain_miner.py run \
  --target "独立 SaaS 创业者" \
  --hours 168 --min-score 30 --min-comments 15 \
  --fetch-comments \
  --out examples/saas-founder-run.json
```

- 快照时间：2026-07-05
- 热帖总数：7（Reddit 4 + V2EX 3）
- 合格社区：r/Entrepreneur, r/startups, r/webdev, r/programming

运行 `render-report --input examples/saas-founder-run.json --out report.md`，即可得到九节、来源可追溯的研究报告；不要再要求 Agent 生成旧式 Step A/B/C 报告。
