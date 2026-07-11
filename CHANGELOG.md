# Changelog

## 2.3.1 — 2026-07-11

- Add a conservative shared HTTP layer for every public source: descriptive User-Agent, per-host pacing, bounded retry for transient failures, and a per-run circuit breaker after 403/429.
- Reuse Arctic Shift listing and comment results within a run so discovery/extraction do not fetch the same Reddit data twice.
- Mark Jina 403/429 as structured source failures and stop subsequent Jina fallback calls in the same run; do not treat block pages as evidence.
- Clarify that anonymous Reddit JSON is an environment/access limitation, while OpenCLI/official credentials are optional user-authorized routes—not a bypass mechanism.

## 2.3.0 — 2026-07-11

- Replace legacy Step A/B/C output guidance with the nine-section `render-report` contract.
- Add target-relevance filtering, bilingual Chinese SaaS planning, and an evidence gate that suppresses opportunities below the required primary evidence count.
- Add source-health observations, `diagnose`, Reddit block-page detection, and automatic HN-first query expansion when Reddit has too few qualifying posts.

## 2.2.0 — 2026-07-11

- Add complete source-linked Markdown reports with `render-report`.
- Add structured target profiles and research scope to `run` output.
- Add community profiles, intent and commercial-signal extraction, signal panels,
  cross-community comparisons, evidence-risk labels, and validation-oriented
  OpportunityCards.
- Preserve backward-compatible source fields and avoid opaque opportunity scores.

## 2.0.0

- Initial public release.
