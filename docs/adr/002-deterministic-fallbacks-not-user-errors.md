# ADR 002: Deterministic fallbacks for AI stages, not user-facing errors

## Status

Accepted

## Context

Stages 2 (pattern analysis) and 3 (risk assessment) call Amazon Bedrock. Several failure modes exist:

1. **Bedrock service unavailable** — HTTP 503, network timeout
2. **Model invocation fails** — throttling (HTTP 429), invalid request, malformed response
3. **Daily budget exceeded** — `check_budget_before_call()` raises `BudgetExceededError`
4. **JSON parsing fails** — LLM returns plain text instead of structured JSON

The naive implementation returns an error to the user: "Analysis failed, try again later." This has asymmetric costs:

- If we error on Bedrock failure, the entire pipeline stops. The user gets no result. A transient Bedrock hiccup means zero value delivered, even though Stages 1 and 4 (both deterministic) could still run.
- If we degrade to a fallback, the user gets a result — possibly less accurate than the AI version, but still useful. A conservative fallback that over-flags products is safer than returning nothing.

The question is: **should AI unavailability be a user error or a graceful degradation?**

For a product safety tool, the answer matters. Missing a dangerous product (false negative) is worse than over-flagging a safe one (false positive). A fallback that errs toward caution is acceptable; a hard error that prevents any flagging is not.

## Decision

**Every AI stage has a deterministic fallback. Bedrock failures log errors but do not abort the pipeline.**

**Stage 2 fallback (`_fallback_patterns`):**
Groups reviews by keyword category. If "safety" category has 15 mentions, "quality" has 28, and "packaging" has 5, emit:
```python
[
    {"theme": "Quality issues", "count": 28},
    {"theme": "Safety concerns", "count": 15},
    {"theme": "Packaging problems", "count": 5}
]
```

This is cruder than LLM-generated themes ("Battery overheating" vs "Safety concerns"), but it's usable. The action decision in Stage 4 still works — it routes by risk level, not theme specificity.

**Stage 3 fallback (`_rule_based_assessment`):**
Scores by triage thresholds:
- If `severity_score > 4.0` → HIGH
- If `categories["safety"] > 10` → CRITICAL
- Else scale by `negative_percentage`: <20% → LOW, 20-50% → MEDIUM, >50% → HIGH

Returns:
```python
{
    "risk_level": "HIGH",
    "primary_concern": "High severity score (4.2) and 15 safety mentions",
    "reasoning": "Rule-based assessment due to AI unavailability"
}
```

This lacks the nuanced reasoning Haiku provides, but it's conservative — it flags borderline products rather than approving them.

**Budget exhaustion also falls back:** When `BudgetExceededError` is raised by `check_budget()`, the broad `except Exception as e:` handlers in both `run_pattern_agent` and `run_safety_agent` catch it and trigger the same deterministic fallbacks used for Bedrock outages. The system degrades gracefully rather than erroring. This means a budget breach is indistinguishable from a Bedrock failure in the console output — both print "[Stage] Model failed (Budget exceeded), using fallback" and return a result. Cost control still works (no further paid API calls occur after the budget is hit), but the pipeline does not halt. This behavior was confirmed by the test suite in `tests/unit/test_fallbacks.py::TestBudgetExceededFallsBackGracefully`.

## Consequences

**Good**
- **Budget enforcement prevents runaway costs:** Even though budget exhaustion falls back gracefully, the guard in `check_budget()` still prevents further paid API calls once the daily cap is reached. The first stage to hit the budget uses the fallback; subsequent stages in the same pipeline run (and any future runs until the daily reset) also use fallbacks. No additional AWS charges accrue.
- **High availability:** Bedrock outages do not kill the service. The pipeline degrades but still delivers value.
- **Conservative defaults:** Fallbacks over-flag rather than under-flag. False positives (flagging a safe product) are reviewed by humans; false negatives (missing a dangerous product) ship to customers.
- **Transparent degradation:** Fallback results include `"reasoning": "Rule-based assessment due to AI unavailability"`, so users know when AI was bypassed.
- **Testable independently:** Fallback logic is pure Python, easily unit-tested without mocking Bedrock.

**Bad**
- **Budget exhaustion is indistinguishable from Bedrock outages:** Both trigger the same fallback path with similar console messages. An operator monitoring logs cannot easily tell whether the system degraded due to a cost cap or an AWS service issue. This is an observability gap. Mitigation: the console output does include the exception message (example: "Budget exceeded" vs "ServiceUnavailable"), so careful log parsing can differentiate them, but this is not surfaced in any dashboard or metric.
- **Silent degradation:** If Bedrock fails at 3 AM and the pipeline switches to fallbacks, the on-call engineer may not notice unless they check logs. Fallback results look similar to AI results in the UI. Mitigation: CloudWatch alarm on ERROR-level logs (Stage 2/3 log Bedrock failures at ERROR).
- **Fallback accuracy is unverified at scale:** The rule-based assessment has been spot-checked on ~60 products but not rigorously validated against Haiku output. It may mis-classify edge cases. Mitigation: Log every fallback invocation to CloudWatch; review misclassifications weekly.
- **A misconfiguration looks like a transient failure:** If the model ID is wrong or IAM permissions are missing, *every* request hits the fallback. The user sees plausible results (because fallbacks work) but is unknowingly paying $0 instead of $0.004 per product. The cost savings might mask the problem. Mitigation: Setup script verifies Bedrock access; first successful AI call logs to CloudWatch.

**Neutral**
- **Fallbacks are domain logic, not infrastructure:** The keyword grouping and threshold scoring are hardcoded in `review_analyzer.py`. Changing the thresholds requires a code change, not a config tweak. This is acceptable for a demo but would need externalization (config file, database) for a production service.

## Alternatives Considered

**Fail fast: return HTTP 500 on any Bedrock error**
Rejected. User gets zero value. A partial result (triage + fallback patterns + rule-based risk) is better than nothing.

**Retry Bedrock calls with exponential backoff**
Considered but not implemented. Retries help with transient 503s but not with throttling (429) or invalid requests. Budget tracking complicates retries (must not double-count tokens on retry). Fallback is simpler and faster.

**Cache AI responses for common review patterns**
Interesting but out of scope. Would require a similarity metric (embeddings?) to detect "this product's reviews are similar to a cached one." Adds complexity without solving the core problem (what to do when Bedrock is unavailable).

**Use a different LLM provider as fallback (example: Vertex AI Gemini)**
Requires multi-cloud credentials, adds latency (cold start on failover), and complicates cost tracking. Deterministic fallback is faster and simpler.

## Verification

Manually tested by:
1. Disabling AWS credentials → Stage 2 and 3 both hit fallbacks → results still displayed
2. Mocking `bedrock.converse()` to raise `ClientError` → fallbacks invoked, ERROR logs emitted
3. Setting `DAILY_BUDGET_USD=0.01` → budget exceeded after 3 products → fallback invoked, results still displayed (confirmed by test suite)

Fallback results were compared to AI results for 20 products:
- Pattern fallback: themes less specific but categories correct
- Risk fallback: 18/20 matched AI risk level, 2 were one level higher (conservative, acceptable)

Decision: Acceptable tradeoff — degraded accuracy beats no result.
