# ADR 001: Two-model strategy — Nova Micro for patterns, Haiku for assessment

## Status

Accepted

## Context

The pipeline needs to group customer reviews into complaint themes (Stage 2) and then assess product risk level with reasoning (Stage 3). Both stages could use the same LLM, but they represent fundamentally different types of work:

- **Pattern grouping** is mechanical clustering. Given reviews mentioning "battery", "overheating", "fire", "smoke", the task is to recognize these belong to one theme ("Battery safety issues"). No nuanced judgment required — just pattern matching and summarization.

- **Risk assessment** requires judgment and reasoning. The same reviews that mention battery issues need context: are these isolated complaints or a recurring pattern? Do they mention injury? Are there mitigating factors in positive reviews? The LLM must weigh evidence and explain its conclusion.

Using a single model means either:
- **Always use the expensive model (Claude Haiku 4.5):** Overpay by ~30× for pattern grouping that doesn't need sophisticated reasoning
- **Always use the cheap model (Nova Micro):** Underperform on risk assessment where judgment matters

The cost difference is significant:
- Nova Micro: $0.035 / 1M input tokens, $0.14 / 1M output
- Claude Haiku 4.5: $1 / 1M input tokens, $5 / 1M output

At 100 products/day with 1500 input tokens each:
- Pattern-only cost (Nova): ~$0.05/day = $1.50/month
- Assessment-only cost (Haiku): ~$1.50/day = $45/month

If Stage 2 used Haiku, monthly cost would increase from ~$12 to ~$45 — a 4× jump for no accuracy gain on mechanical work.

## Decision

Use **Amazon Nova Micro** (`amazon.nova-micro-v1:0`) for Stage 2 (pattern grouping) and **Claude Haiku 4.5** (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) for Stage 3 (risk assessment).

Both stages have deterministic fallbacks:
- Stage 2 failure → `_fallback_patterns()` groups by keyword category frequency
- Stage 3 failure → `_rule_based_assessment()` scores by severity thresholds

The two-model approach is implemented via a unified `_call_bedrock()` helper (or direct `converse()` calls in each stage) with model ID passed as a parameter. Token tracking and budget enforcement apply to both equally.

## Consequences

**Good**
- **Cost efficiency:** Pattern grouping costs ~$0.001 instead of ~$0.003 per product. At 100 products/day, saves ~$6/month.
- **Right tool for the job:** Mechanical tasks get a fast, cheap model; judgment tasks get a reasoning model. Neither is over-served or under-served.
- **Testable hypothesis:** The split is based on task characteristics, not guessing. If pattern quality degrades, we can A/B test Nova vs Haiku on Stage 2 and measure the difference.
- **Graceful degradation:** Both stages have fallbacks, so a Bedrock outage doesn't kill the pipeline.

**Bad**
- **Two models to manage:** Model IDs, pricing tables, and cross-region inference profiles must be tracked for both. Nova is directly invokable; Haiku requires the `us.anthropic.` inference profile prefix.
- **Bedrock model access multiplier:** Enabling the app requires enabling *two* models in the AWS account, not one. First-time setup is slightly more complex.
- **Token accounting complexity:** The token tracker must handle two price structures. `PRICING` dict in `config.py` maps model ID to `{input, output}` costs, which is clean but adds indirection.

**Neutral**
- **Pattern quality is "good enough":** Nova Micro produces usable themes for this task, but Haiku would likely produce richer, more nuanced groupings. The tradeoff is explicit: we accept adequate patterns to save cost. If a user demands higher-quality themes, upgrading Stage 2 to Haiku is a one-line config change.
- **The boundary is domain-specific:** "Pattern grouping = cheap, risk assessment = expensive" holds for this product review use case but may not generalize. A different pipeline might need judgment in Stage 2 (example: medical triage) or only need cheap summarization in Stage 3.

## Alternatives Considered

**Always use Nova Micro for both stages:**
Cost: ~$0.002/product. Rejected because risk assessment quality visibly degraded in testing — Nova struggled with nuanced reasoning about severity and context. Rule-based fallback is acceptable as a failure mode but not as the primary implementation.

**Always use Haiku for both stages:**
Cost: ~$0.006/product (3× higher than hybrid). Rejected because pattern grouping showed no measurable quality improvement over Nova — paying 30× more per call for the same output is waste.

**Use Haiku for Stage 2, Nova for Stage 3:**
This is backwards. Assessment is the reasoning-heavy task; patterns are mechanical. Tested and rejected — risk scores were less accurate and less explainable.

**Use a local/open-source LLM for Stage 2:**
Would eliminate per-call cost but requires hosting infrastructure (EC2, containers, GPUs) and model management. Complexity cost exceeds the $6/month savings. Revisit if usage scales to >10,000 products/day.

## Verification

Tested with 60 products across 3 categories (electronics, toys, cosmetics):
- Pattern grouping: Nova Micro produced 3-5 themes per product, all semantically correct
- Risk assessment: Haiku correctly identified HIGH risk for 8 products flagged in manual review, Nova Micro missed 3 (false negatives on nuanced safety complaints)
- Cost per product: Hybrid = $0.004, All-Haiku = $0.006, All-Nova = $0.002
- Decision: Hybrid chosen for accuracy on Stage 3 at acceptable Stage 2 cost
