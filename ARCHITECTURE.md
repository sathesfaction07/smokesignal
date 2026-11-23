# Review Risk Analyzer — Technical Architecture

## Overview

A 4-stage review analysis pipeline combining deterministic keyword matching with Amazon Bedrock LLMs to detect product safety and quality risks. Stage 1 (triage) scans for 130+ complaint keywords at zero cost. Stage 2 (patterns) groups themes with Nova Micro (~$0.001). Stage 3 (assessment) reasons about risk with Claude Haiku 4.5 (~$0.003). Stage 4 (action) routes decisions and triggers SNS alerts for HIGH/CRITICAL products. Daily cache by ASIN+marketplace prevents reprocessing. Budget enforcement halts on spending cap. Web UI streams results via SSE as pipeline stages complete.

**Design principle:** Separate mechanical work (keyword matching, grouping) from judgment (risk assessment, reasoning). Use cheap models for simple tasks, expensive models only where nuance matters. Fail gracefully — every AI stage has a deterministic fallback.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        WEB CLIENT (Browser)                          │
│                      http://localhost:5000                           │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  FLASK SERVER (app.py)                                               │
│                                                                      │
│  GET /          -> static/index.html                                 │
│  POST /analyze  -> parse ASINs, check cache, stream SSE              │
│                                                                      │
│  _parse_asin_input() -> extracts ASINs from URLs, comma/space-sep   │
│  _format_result()    -> sanitizes for JSON serialization            │
│  generate()          -> yields SSE events per stage                  │
└───────────────────────┬─────────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        ▼                               ▼
┌──────────────────────┐    ┌──────────────────────────────────────┐
│  DAILY CACHE         │    │  REVIEW FETCHER                       │
│  (monitoring/        │    │  (agents/review_fetcher.py)           │
│   daily_cache.py)    │    │                                       │
│                      │    │  - Launch Chrome (headless, eager)    │
│  .cache/results_     │    │  - Open N tabs (parallel)             │
│  YYYY-MM-DD.json     │    │  - Extract product + reviews          │
│                      │    │  - Yield per ASIN (streaming)         │
│  Cache key:          │    │  - atexit/signal/weakref cleanup      │
│  f"{asin}_{market}"  │    │                                       │
│                      │    │  Supports 25 marketplaces             │
│  Auto-expires daily  │    └──────────────┬────────────────────────┘
└──────────────────────┘                   │
                                           ▼
                        ┌──────────────────────────────────────────┐
                        │  REVIEW ANALYZER                          │
                        │  (agents/review_analyzer.py)              │
                        │                                           │
                        │  analyze_reviews_data(data) orchestrator  │
                        │      ↓                                    │
                        │  ┌────────────────────────────────────┐  │
                        │  │ STAGE 1: TRIAGE                    │  │
                        │  │ run_triage_agent()                 │  │
                        │  │ - Keyword scan (130+ triggers)     │  │
                        │  │ - 5 categories: safety, quality,   │  │
                        │  │   packaging, description, general  │  │
                        │  │ - Cost: $0 (pure Python)           │  │
                        │  │ Output: neg%, severity, categories │  │
                        │  └────────────┬───────────────────────┘  │
                        │               ↓                           │
                        │  ┌────────────────────────────────────┐  │
                        │  │ STAGE 2: PATTERNS                  │  │
                        │  │ run_pattern_agent()                │  │
                        │  │ - Budget check                     │  │
                        │  │ - Token tracking (in + out)        │  │
                        │  │ - Bedrock Converse API             │  │
                        │  │   Model: amazon.nova-micro-v1:0    │  │
                        │  │ - Group 3-5 complaint themes       │  │
                        │  │ - Fallback: keyword clustering     │  │
                        │  │ - Cost: ~$0.001                    │  │
                        │  └────────────┬───────────────────────┘  │
                        │               ↓                           │
                        │  ┌────────────────────────────────────┐  │
                        │  │ STAGE 3: ASSESSMENT                │  │
                        │  │ run_safety_agent()                 │  │
                        │  │ - Budget check                     │  │
                        │  │ - Token tracking                   │  │
                        │  │ - Bedrock Converse API             │  │
                        │  │   Model: us.anthropic.claude-      │  │
                        │  │          haiku-4-5-20251001-v1:0   │  │
                        │  │ - Structured reasoning prompt      │  │
                        │  │ - Output: risk level + concern +   │  │
                        │  │          reasoning                 │  │
                        │  │ - Fallback: rule-based scoring     │  │
                        │  │ - Cost: ~$0.003                    │  │
                        │  └────────────┬───────────────────────┘  │
                        │               ↓                           │
                        │  ┌────────────────────────────────────┐  │
                        │  │ STAGE 4: ACTION                    │  │
                        │  │ run_action_agent()                 │  │
                        │  │ - CRITICAL → FLAG_FOR_REMOVAL      │  │
                        │  │ - HIGH     → FLAG_FOR_REVIEW       │  │
                        │  │ - MEDIUM   → MONITOR               │  │
                        │  │ - LOW      → APPROVE               │  │
                        │  │ - SNS alert for HIGH/CRITICAL      │  │
                        │  │ - CloudWatch metrics always        │  │
                        │  │ - Cost: $0 (pure rules)            │  │
                        │  └────────────────────────────────────┘  │
                        └──────────────┬────────────────────────────┘
                                       │
                        ┌──────────────┼──────────────┐
                        ▼              ▼              ▼
            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
            │ CLOUDWATCH   │  │ SNS          │  │ CACHE        │
            │ Metrics      │  │ Email alerts │  │ Write        │
            │ /Alarms      │  │ HIGH/CRIT    │  │ result       │
            └──────────────┘  └──────────────┘  └──────────────┘
```

---

## Components

### 1. Flask Server (`app.py`)

Minimal web server with two routes and SSE streaming.

**Routes:**
- `GET /` — serves `static/index.html`
- `POST /analyze` — accepts JSON `{asins: "B08..., B09...", marketplace: "US"}`, streams SSE events

**`_parse_asin_input(raw)`** — regex extracts ASINs from URLs, comma-separated, space-separated, or newline-separated input. Returns list of uppercase ASINs.

**`_format_result(raw)`** — sanitizes dict for JSON: removes non-serializable objects (browser driver references), converts NumPy types to native Python.

**`generate()`** — generator yielding SSE events:
1. Check cache for each ASIN
2. Fetch uncached ASINs via `stream_reviews_multi()`
3. For each result: `analyze_reviews_data()` → yield stages 1-4 as SSE
4. Save to cache on completion

SSE format: `data: {"stage": "triage", "asin": "B08...", "result": {...}}\n\n`

Server logs errors to `vista.server` logger. Flask's debug mode is off in production.

### 2. Review Fetcher (`agents/review_fetcher.py`)

Selenium Chrome automation with three modes: single ASIN, batch (all at once), and streaming (yield per ASIN).

**`stream_reviews_multi(asins, marketplace)`** — the main entry point for the web UI. Opens one Chrome instance with N tabs (parallel loading). Yields `(asin, result_dict)` tuples as each completes.

**Chrome configuration:**
- Headless
- `page_load_strategy='eager'` — returns control before images/scripts fully load
- Images disabled (`--blink-settings=imagesEnabled=false`)
- Incognito, no sandbox (for container compatibility)

**Cleanup mechanisms:**
1. `atexit.register()` — close all drivers on normal exit
2. Signal handlers (SIGTERM, SIGINT) — close on kill
3. `weakref.WeakSet` registry — tracks all driver instances globally

**Why all three:** Selenium Chrome leaks memory if not closed. A try/finally catches normal paths, but crashes and signals bypass it. The registry ensures every created driver is tracked and closeable.

**XPath selectors:**
- Product title: `//span[@id='productTitle']`
- Star rating: `//span[@data-hook='rating-out-of-text']`
- Reviews: `//div[@data-hook='review']` with nested `.//span[@data-hook='review-body']`

Returns: `{"product_name": "...", "rating": "4.5 out of 5", "reviews": ["...", "..."], "asin": "...", "marketplace": "..."}`

On failure: `{"status": "error", "error": "...", "asin": "...", "marketplace": "..."}`

### 3. Review Analyzer (`agents/review_analyzer.py`)

The 4-stage pipeline. Each stage is a function returning a dict.

#### Stage 1: Triage (`run_triage_agent`)

Keyword scan across 5 categories. Each category has 20-30 triggers:
- **Safety:** fire, burn, explode, choke, sharp, toxic, chemical smell, smoke
- **Quality:** broke, defective, stopped working, cheap, flimsy, fall apart
- **Packaging:** damaged, dented, missing parts, wrong item, used, resealed
- **Description mismatch:** not as described, misleading, fake, counterfeit
- **General disappointment:** waste of money, returned, regret, disappointed

Returns:
```python
{
    "negative_percentage": 45.2,
    "severity_score": 3.8,
    "categories": {
        "safety": 12,
        "quality": 28,
        "packaging": 5,
        "description_mismatch": 8,
        "general": 15
    }
}
```

No LLM — pure `any(keyword in review.lower() for keyword in triggers)`.

#### Stage 2: Patterns (`run_pattern_agent`)

Prompt: "Group these reviews into 3-5 recurring complaint themes. Return JSON array."

**Budget check first:** `token_tracker.check_budget_before_call()` raises `BudgetExceededError` if daily cap exceeded.

**Token tracking:**
```python
input_tokens = count_tokens(user_message, MODEL_ID_TOOLS)
output_tokens = count_tokens(response, MODEL_ID_TOOLS)
token_tracker.record_call(MODEL_ID_TOOLS, input_tokens, output_tokens)
```

**Bedrock call:** `bedrock.converse()` with `amazon.nova-micro-v1:0`, max_tokens=512.

**Fallback:** On any exception, `_fallback_patterns()` groups by keyword category frequency.

Returns:
```python
[
    {"theme": "Battery overheating", "count": 8},
    {"theme": "Poor build quality", "count": 15},
    {"theme": "Misleading size claims", "count": 6}
]
```

#### Stage 3: Assessment (`run_safety_agent`)

System prompt: "You are a product safety analyst. Assess risk level based on triage and patterns."

User prompt: Structured JSON of triage + patterns, asking for `risk_level` (LOW/MEDIUM/HIGH/CRITICAL), `primary_concern`, `reasoning`.

**Model:** `us.anthropic.claude-haiku-4-5-20251001-v1:0` (cross-region inference profile required for Claude access).

**Budget check + token tracking:** same as Stage 2.

**Fallback:** `_rule_based_assessment(triage)`:
- If `triage["severity_score"] > 4.0` → HIGH
- If `triage["categories"]["safety"] > 10` → CRITICAL
- Else scale by negative percentage

Returns:
```python
{
    "risk_level": "HIGH",
    "primary_concern": "Battery safety — 8 reports of overheating",
    "reasoning": "Recurring pattern of thermal issues across multiple reviews..."
}
```

#### Stage 4: Action (`run_action_agent`)

Deterministic routing:

```python
if risk_level == "CRITICAL":
    action = "FLAG_FOR_REMOVAL"
    _send_sns_alert(subject, message)
    _publish_cw_metric("ProductFlags", 1.0)
elif risk_level == "HIGH":
    action = "FLAG_FOR_REVIEW"
    _send_sns_alert(subject, message)
    _publish_cw_metric("ProductFlags", 1.0)
elif risk_level == "MEDIUM":
    action = "MONITOR"
    _publish_cw_metric("ProductFlags", 0.0)
else:
    action = "APPROVE"
```

**SNS alert format:**
```
Subject: [CRITICAL] Product B08RWPHMZF flagged for removal
Body: Product: Wireless Headphones XYZ
      Risk: CRITICAL
      Primary concern: Battery overheating
      Action: FLAG_FOR_REMOVAL
      [link to Amazon product page]
```

Returns: `{"action": "FLAG_FOR_REMOVAL", "alert_sent": True, "metric_published": True}`

### 4. Token Tracker (`monitoring/token_tracker.py`)

Global singleton tracking daily spend.

**State:**
```python
_daily_usage = {
    "date": "2026-08-10",
    "calls": 0,
    "input_tokens": 0,
    "output_tokens": 0,
    "cost_usd": 0.0
}
```

Resets on date change (checked on every call).

**`check_budget_before_call(estimated_tokens)`** — raises `BudgetExceededError` if `_daily_usage["cost_usd"] + estimated_cost > DAILY_BUDGET_USD`.

**`record_call(model_id, in_tokens, out_tokens)`** — increments counters, calculates cost from `PRICING` dict in `config.py`, publishes to CloudWatch.

**CloudWatch metrics published:**
- `TokensUsedTotal` (sum of input + output)
- `CostUSD` (cumulative daily)
- `BudgetUtilizationPct` (cost / budget * 100)

Namespace: `BedrockReviewIntel` (from `config.CLOUDWATCH_NAMESPACE`).

### 5. Daily Cache (`monitoring/daily_cache.py`)

Same-day ASIN+marketplace result storage.

**File:** `.cache/results_YYYY-MM-DD.json` (gitignored)

**Structure:**
```json
{
    "B08RWPHMZF_US": {
        "product_name": "...",
        "risk_level": "HIGH",
        ...
    },
    "B09V3KXJPB_UK": { ... }
}
```

**`get_cached(asin, marketplace)`** — returns dict if found, else `None`. Auto-deletes yesterday's file on first call of a new day.

**`save_to_cache(asin, marketplace, result)`** — writes atomically (temp file + rename).

Cache hit avoids all 4 stages = $0 cost + instant response.

### 6. Logger (`monitoring/logger.py`)

Structured JSON logs via Python `logging` module.

**Namespace:** `vista` (child loggers: `vista.fetcher`, `vista.analyzer`, `vista.server`, `vista.agentcore`).

**Format:**
```json
{"timestamp": "2026-08-10T14:23:45Z", "level": "ERROR", "module": "vista.analyzer", "event": "Bedrock call failed", "details": "..."}
```

Designed for CloudWatch Logs ingestion. The CloudFormation template creates a Metric Filter that counts `$.level = "ERROR"` events and triggers an alarm at >3 errors/5min.

### 7. Strands Agent (`agents/strands_agent.py`)

**Not integrated into the main pipeline** — a separate demo of Bedrock AgentCore.

Uses the Strands SDK (`strands-agents` package) to create a proper agent with:
1. System prompt
2. Two registered tools: `classify_risk_level()`, `check_safety_keywords()`
3. Autonomous tool selection — the agent decides when to call which tool

The agent manages its own tool-calling loop. You give it a task ("Analyze this product's reviews"), and it decides: "I should first check for safety keywords, then classify the risk level."

**Why separate:** Integrating this into the pipeline would complicate the working system. The pipeline is a deterministic sequence; the Strands agent is autonomous exploration. Both patterns are valuable; neither needs to subsume the other.

**Running:** `python agents/strands_agent.py` (no Flask server needed).

---

## Data Flow: Single ASIN Analysis

```
1. User enters B08RWPHMZF in web UI, selects US, clicks Analyze
2. POST /analyze {"asins": "B08RWPHMZF", "marketplace": "US"}
3. app.py parses → ["B08RWPHMZF"]
4. Check daily_cache.get_cached("B08RWPHMZF", "US") → None (cache miss)
5. Launch Selenium Chrome, open amazon.com/dp/B08RWPHMZF
6. Extract product title, rating, reviews → yield result
7. Pass to analyze_reviews_data()

   STAGE 1 (0ms, $0):
   - Scan 85 reviews for 130 keywords
   - Find 23 safety mentions, 41 quality complaints
   - Output: negative_percentage=48.2, severity=4.1
   - SSE: {"stage": "triage", "result": {...}}

   STAGE 2 (~1000ms, $0.001):
   - check_budget_before_call() → OK (used $0.23 of $1.00)
   - count_tokens(reviews) → 1420 input tokens
   - Bedrock converse(nova-micro) → 3 themes
   - count_tokens(response) → 85 output tokens
   - record_call() → cost += $0.000062
   - SSE: {"stage": "patterns", "result": [...]}

   STAGE 3 (~2000ms, $0.003):
   - check_budget_before_call() → OK
   - count_tokens(triage+patterns) → 450 input tokens
   - Bedrock converse(haiku) → risk=HIGH, reasoning
   - count_tokens(response) → 120 output tokens
   - record_call() → cost += $0.00105
   - SSE: {"stage": "assessment", "result": {...}}

   STAGE 4 (10ms, $0):
   - risk_level == "HIGH" → action = FLAG_FOR_REVIEW
   - _send_sns_alert() → email sent
   - _publish_cw_metric("ProductFlags", 1.0)
   - SSE: {"stage": "action", "result": {...}}

8. daily_cache.save_to_cache("B08RWPHMZF", "US", full_result)
9. Frontend displays: risk badge, patterns, reasoning, decision
10. Repeat request → instant cache hit, $0 cost
```

---

## AWS Integration

### Bedrock Models

| Model | ID | Use Case | Cost |
|:--|:--|:--|:--|
| Nova Micro | `amazon.nova-micro-v1:0` | Pattern grouping (Stage 2) | $0.035 / 1M in, $0.14 / 1M out |
| Claude Haiku 4.5 | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Risk assessment (Stage 3) | $1 / 1M in, $5 / 1M out |

**Cross-region inference profile required for Claude.** The model ID prefix `us.anthropic.` indicates use of the inference profile, not direct model invocation. Without this, Haiku 4.5 is unavailable in `us-east-1`.

**API:** Bedrock Converse API (`bedrock_runtime.converse()`) — unified interface for all models, returns structured response with `usage` tokens.

### SNS Alerts

Topic: `bedrock-processor-alerts` (created by CloudFormation)

Email subscriptions require confirmation. Alerts sent only for HIGH/CRITICAL.

Alert throttling: none — every flagged product sends an email. In production, add SNS message deduplication or a rate-limiting layer.

### CloudWatch

**Custom metrics:**
- `TokensUsedTotal` (Count)
- `CostUSD` (Count, cumulative daily)
- `BudgetUtilizationPct` (Percent)
- `ProductFlags` (Count, 1.0 per HIGH/CRITICAL, 0.0 otherwise)

**Log Group:** `/review-intel/app` (14-day retention)

**Metric Filter:** Counts `$.level = "ERROR"` events, publishes to `AppErrors` metric.

**Alarms:**
1. `HighFlagRate` — >5 flags/day → SNS notification
2. `ErrorRate` — >3 errors/5min → SNS notification
3. `BudgetHigh` — >80% of `DAILY_BUDGET_USD` → SNS notification

All alarms notify via the same SNS topic as product alerts.

### IAM Permissions

The CloudFormation stack creates a user `review-intel-deployer` with least-privilege policy:

```yaml
- Effect: Allow
  Action:
    - bedrock:InvokeModel
    - bedrock:InvokeModelWithResponseStream
  Resource:
    - arn:aws:bedrock:*::foundation-model/amazon.nova-micro-v1:0
    - arn:aws:bedrock:*::foundation-model/*claude-haiku*

- Effect: Allow
  Action:
    - sns:Publish
  Resource: !Ref AlertsTopic

- Effect: Allow
  Action:
    - cloudwatch:PutMetricData
  Resource: "*"
  Condition:
    StringEquals:
      cloudwatch:namespace: BedrockReviewIntel

- Effect: Allow
  Action:
    - logs:CreateLogStream
    - logs:PutLogEvents
  Resource: !GetAtt AppLogGroup.Arn
```

No S3, no Lambda, no EC2 — only Bedrock, SNS, CloudWatch.

---

## Configuration

All settings in `config.py`, overrideable via environment variables.

```python
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MODEL_ID_TOOLS = "amazon.nova-micro-v1:0"
MODEL_ID_AGENT = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
CLOUDWATCH_NAMESPACE = "BedrockReviewIntel"

PRICING = {
    MODEL_ID_TOOLS: {"input": 0.000035, "output": 0.00014},
    MODEL_ID_AGENT: {"input": 0.001, "output": 0.005},
}

MARKETPLACES = {
    "US": "www.amazon.com",
    "UK": "www.amazon.co.uk",
    # ... 25 total
}
```

`DAILY_BUDGET_USD` is not in `config.py` — it lives in `token_tracker.py` as `1.0` with an override via `os.getenv("DAILY_BUDGET_USD", "1.0")`.

---

## Failure Modes and Fallbacks

| Failure | Detection | Response |
|:--|:--|:--|
| **Selenium can't open Amazon** | Exception in `review_fetcher.py` | Yield error dict, skip AI stages, return to user |
| **No reviews found** | Empty review list | Yield error, skip AI stages |
| **Bedrock unavailable (Stage 2)** | `ClientError` on converse | Log error, call `_fallback_patterns()`, continue |
| **Bedrock unavailable (Stage 3)** | `ClientError` on converse | Log error, call `_rule_based_assessment()`, continue |
| **Budget exceeded** | `check_budget_before_call()` raises `BudgetExceededError` | Caught by broad `except Exception` handlers, triggers fallback (same path as Bedrock failure), continues |
| **SNS publish fails** | Exception in `_send_sns_alert()` | Log error, set `alert_sent=False`, continue (metric still published) |
| **CloudWatch publish fails** | Exception in `_publish_cw_metric()` | Log error, set `metric_published=False`, continue |
| **Cache write fails** | Exception in `daily_cache.save_to_cache()` | Log error, continue (next request will refetch) |
| **Chrome crashes mid-fetch** | Signal handler catches | Close all drivers via `weakref.WeakSet`, return partial results |

**Design philosophy:** Every external dependency has a fallback or graceful degradation. No single failure aborts the entire pipeline.

---

## Testing

**No automated test suite.** This is a portfolio demonstration, not production software.

**Manual testing via web UI:**
1. Start `python app.py`
2. Enter test ASINs (B08RWPHMZF, B09V3KXJPB, etc.)
3. Verify stages 1-4 animate correctly
4. Check results display
5. Confirm cache file created
6. Re-analyze → cache hit (instant)

**Offline testing:** Load `sample_data/product_reviews_us.json` directly into `analyze_reviews_data()` without running Selenium.

**Strands demo:** `python agents/strands_agent.py` — verifies Bedrock AgentCore integration, tool registration, autonomous tool selection.

---

## Deployment

### Local Development

```bash
bash setup.sh
source .venv/bin/activate
export AWS_PROFILE=vista
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:ACCOUNT:bedrock-processor-alerts
python app.py
```

### AWS Infrastructure

```bash
aws cloudformation create-stack \
  --stack-name review-intel-infra \
  --template-body file://infra/cloudformation.yaml \
  --parameters ParameterKey=AlertEmailList,ParameterValue="you@example.com" \
  --capabilities CAPABILITY_IAM \
  --profile vista
```

Stack outputs: `SNSTopicArn`, `AccessKeyId`, `SecretAccessKey`, `AppLogGroupName`.

### Docker (Not Included)

A Dockerfile would require:
- Python 3.10+ base image
- Chrome + ChromeDriver installation
- `pip install -r requirements.txt`
- `CMD ["python", "app.py"]`
- Env vars: `AWS_PROFILE`, `SNS_TOPIC_ARN`, `DAILY_BUDGET_USD`

Not provided because Chrome in Docker requires `--no-sandbox --disable-dev-shm-usage` flags and headless mode configuration, which complicates the demo without adding educational value.

---

## Performance Characteristics

**Selenium fetch:** ~3-8 seconds per ASIN (depends on page size, network latency, marketplace)

**Stage 1 (triage):** <100ms (pure Python keyword scan)

**Stage 2 (patterns):** ~1-2 seconds (Bedrock Nova Micro call)

**Stage 3 (assessment):** ~2-4 seconds (Bedrock Haiku call)

**Stage 4 (action):** ~50ms (SNS publish + CloudWatch put)

**Total per ASIN (uncached):** ~6-15 seconds, ~$0.004

**Total per ASIN (cached):** <100ms, $0

**Multi-ASIN batches:** Selenium opens all tabs in parallel (limited by browser instance), but AI stages run sequentially per ASIN. 10 ASINs take ~60-150 seconds total.

**Scale limits (untested):**
- Selenium multi-tab: unknown upper bound (tested up to 10 tabs)
- Daily budget: configurable, default $1 = ~250 ASINs
- Cache file size: unknown (not tested beyond 100 entries)

---

## Security Considerations

**AWS credentials:** Must be configured via AWS CLI or environment variables. No hardcoded keys in code (fallback SNS ARN contains account ID, which is not sensitive).

**Secrets in `.env`:** Gitignored. Never commit `.env` files.

**Cross-Site Scripting (XSS):** Frontend uses `textContent` and `innerText` for user-generated content (product names, reviews), not `innerHTML`. No XSS risk.

**Selenium automation detection:** Amazon may block requests from headless Chrome. The fetcher uses `--disable-blink-features=AutomationControlled` to reduce detectability, but this is not foolproof.

**Rate limiting:** None. The tool can hammer Amazon's servers if given a large ASIN list. Daily cache mitigates this for same-day repeats, but no inter-request delay is enforced.

**IAM least-privilege:** CloudFormation policy grants only Bedrock invoke, SNS publish, CloudWatch metrics, and Logs write. No S3, EC2, or admin permissions.

---

## Cost Estimation

| Scenario | Cost |
|:--|:--|
| 1 ASIN, first analysis | ~$0.004 |
| 1 ASIN, same-day repeat | $0 (cache hit) |
| 10 ASINs/day | ~$0.04/day = ~$1.20/month |
| 100 ASINs/day | ~$0.40/day = ~$12/month |
| 250 ASINs/day (budget cap) | $1.00/day = $30/month |

**SNS:** Free tier covers 1,000 emails/month. HIGH/CRITICAL alerts count against this.

**CloudWatch:** Free tier covers 10 custom metrics. This project uses 4.

**Bedrock:** No free tier. All costs are per-token.

**Hidden costs:** None. Selenium runs locally (no EC2). Flask runs locally (no ECS/Lambda). Only Bedrock + SNS + CloudWatch.

---

## Future Improvements (Not Implemented)

**Batch CLI mode:** `python -m review_risk_analyzer analyze products.csv --output results.json`

**Multi-language support:** Expand Stage 1 keyword lists to French, German, Spanish, Japanese.

**Streaming results to disk:** Write per-ASIN results as they complete instead of holding all in memory.

**Request throttling:** Add inter-request delay to Selenium to avoid Amazon rate limits.

**Automated tests:** pytest fixtures for all 4 stages, mocking Bedrock/SNS/Selenium.

**Docker deployment:** Containerize with Chrome installed, publish to ECR.

**Web UI improvements:** Dark mode, export to CSV/Excel, historical trend charts.
