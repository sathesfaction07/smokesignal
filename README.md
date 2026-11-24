# Smokesignal

A 4-stage AI pipeline that analyzes Amazon product reviews to detect safety and quality risks. Given an ASIN (Amazon product ID), it scrapes customer reviews, scans for complaint keywords, groups themes with Amazon Nova Micro, assesses risk with Claude Haiku 4.5, and routes flagged products to SNS email alerts. Cost per product: ~$0.004. Daily cache prevents reprocessing; budget enforcement stops at a configurable spending cap.

---

## The Problem

You have thousands of products for sale and customer reviews arriving continuously. Some of those reviews mention battery fires, choking hazards, broken packaging, or misleading claims — signals that a product may need urgent attention. Reading every review manually is not scalable, and filtering by star rating misses nuanced complaints: a 4-star review can still mention a safety issue in passing.

The real problem is triage. Not every complaint is equal. "Product arrived late" is frustrating but not dangerous. "Caught fire while charging" requires immediate action. A useful system needs to separate noise from risk, group similar complaints to spot patterns, assess severity with context, and route decisions: approve, monitor, or escalate.

Doing this well requires both precision (keyword matching to avoid false positives) and judgment (understanding that "smells like burning plastic" in the context of ten similar reviews is different from one isolated mention). That is the shape this tool fits.

---

## How It Works

Four sequential stages, two deterministic and two AI-powered:

**Stage 1: Triage (Python keywords, $0)**
Scans review text for 130+ negative keywords across five categories: safety, quality, packaging, description mismatch, and general disappointment. Returns complaint percentage, severity score, and category breakdown. No LLM cost — pure pattern matching.

**Stage 2: Pattern Analysis (Amazon Nova Micro, ~$0.001 per product)**
Sends reviews to Bedrock with a prompt asking for 3-5 recurring complaint themes. Uses Nova Micro because the task is mechanical grouping, not nuanced reasoning. Falls back to keyword-based clustering on failure.

**Stage 3: Risk Assessment (Claude Haiku 4.5, ~$0.003 per product)**
Sends triage results and patterns to Claude with a structured prompt asking for: risk level (LOW/MEDIUM/HIGH/CRITICAL), primary concern, and reasoning. Uses the cross-region inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0` for access. Falls back to rule-based scoring on failure.

**Stage 4: Action Decision (Python rules, $0)**
Routes by risk level:
- CRITICAL → `FLAG_FOR_REMOVAL`, SNS email alert
- HIGH → `FLAG_FOR_REVIEW`, SNS email alert
- MEDIUM → `MONITOR`, CloudWatch metric only
- LOW → `APPROVE`, CloudWatch metric only

Every AI call checks the daily budget first and tracks token usage. Results are cached by ASIN + marketplace for the current date. When a new day starts, yesterday's cache is deleted automatically.

A Bedrock AgentCore demonstration using the Strands SDK is included as a separate executable (`agents/strands_agent.py`) showing tool registration, autonomous tool selection, and the proper agent pattern — not integrated into the main pipeline to keep that simpler.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                             USER                                      │
│                      http://localhost:5000                            │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│  FLASK SERVER (app.py)                                                │
│  POST /analyze {asins, marketplace}                                   │
│  Streams results via Server-Sent Events                               │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
            ┌───────────────┴──────────────┐
            ▼                              ▼
┌───────────────────────┐      ┌───────────────────────────┐
│  DAILY CACHE          │      │  REVIEW FETCHER           │
│  (monitoring/)        │      │  (agents/)                │
│                       │      │                           │
│  .cache/results_      │      │  Selenium headless Chrome │
│  YYYY-MM-DD.json      │      │  Multi-tab parallel fetch │
│                       │      │  25 marketplaces          │
│  Cache hit → instant  │      │  Graceful cleanup on crash│
│  Cache miss → fetch   │      └───────────┬───────────────┘
└───────────────────────┘                  │
                                           ▼
                            ┌──────────────────────────────┐
                            │  REVIEW ANALYZER             │
                            │  (agents/)                   │
                            │                              │
                            │  Stage 1: Triage (Python)    │
                            │  ↓                           │
                            │  Stage 2: Patterns (Nova)    │
                            │  ↓                           │
                            │  Stage 3: Assessment (Haiku) │
                            │  ↓                           │
                            │  Stage 4: Action (Python)    │
                            └──────────┬───────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
          ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
          │ CLOUDWATCH   │   │ SNS EMAIL    │   │ CACHE        │
          │ Metrics +    │   │ HIGH/CRITICAL│   │ Save for     │
          │ Alarms       │   │ alerts       │   │ same-day     │
          └──────────────┘   └──────────────┘   └──────────────┘
```

The fetcher yields results one at a time, so the UI updates in real time as each ASIN completes. Budget enforcement happens before every AI call. Failures at any stage are logged and gracefully degraded — a fetch error skips AI stages, an AI error falls back to deterministic logic.

---

## Project Structure

```
smokesignal/
├── app.py                      Flask server, SSE streaming
├── config.py                   AWS region, model IDs, pricing, marketplaces
├── requirements.txt            boto3, flask, selenium, tiktoken, strands-agents
├── agents/
│   ├── review_fetcher.py       Selenium multi-tab scraper with cleanup
│   ├── review_analyzer.py      4-stage pipeline (2 AI + 2 deterministic)
│   └── strands_agent.py        Bedrock AgentCore demo (Strands SDK)
├── monitoring/
│   ├── logger.py               Structured JSON logs (vista.* namespace)
│   ├── token_tracker.py        Daily budget + token cost tracking
│   └── daily_cache.py          Same-day ASIN+marketplace result cache
├── infra/
│   └── cloudformation.yaml     SNS, IAM, CloudWatch alarms, log group
├── sample_data/
│   └── product_reviews_us.json Pre-scraped reviews for offline testing
├── static/
│   └── index.html              Tailwind CSS UI with pipeline stage animation
├── data/                       (not present — sample data in sample_data/)
└── tests/                      (not present — manual testing via web UI)
```

**Note on testing:** `pytest` runs 108 tests in CI on Python 3.10–3.12 and on Windows. The tests cover keyword triage, the action decision, configuration, the daily cache, token tracking and the fallbacks when Bedrock is unavailable or over budget, plus one pipeline integration test with Bedrock, SNS and CloudWatch mocked. Live Selenium review fetching and real Bedrock calls are not covered and are checked manually through the web UI and the Strands demo.

---

## Running

### Prerequisites

- **Python 3.10+** (3.11+ recommended)
- **Chrome** (latest stable) — ChromeDriver is auto-managed by Selenium 4.6+
- **AWS Bedrock access** — both models must be enabled:
  - `amazon.nova-micro-v1:0`
  - `us.anthropic.claude-haiku-4-5-20251001-v1:0` (cross-region inference profile)
- **AWS credentials** configured via `AWS_PROFILE` or standard credential chain

### Setup

```bash
bash setup.sh
source .venv/bin/activate

# Configure AWS credentials
aws configure --profile vista
# Enter: Access Key, Secret Key, Region (us-east-1), Format (json)

# Deploy infrastructure (creates SNS topic, IAM user, CloudWatch alarms)
aws cloudformation create-stack \
  --stack-name review-intel-infra \
  --template-body file://infra/cloudformation.yaml \
  --parameters ParameterKey=AlertEmailList,ParameterValue="you@example.com" \
  --capabilities CAPABILITY_IAM \
  --profile vista

# Wait for stack completion, then copy SNSTopicArn from Outputs

# Set environment variables
export AWS_PROFILE=vista
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT:bedrock-processor-alerts

# Start the server
python app.py

# Open browser: http://localhost:5000
```

The setup script verifies Python version, creates a virtual environment, installs dependencies, confirms imports resolve, and checks that AWS credentials are valid.

### Basic Usage

1. Enter ASINs in any format:
   - Single: `B08RWPHMZF`
   - Multiple: `B08RWPHMZF, B09V3KXJPB`
   - Full URL: `https://www.amazon.com/dp/B08RWPHMZF`
   - Mixed formats work
2. Select marketplace (default: US)
3. Click **Analyze**
4. Watch the pipeline stages animate as processing occurs
5. Results show: risk badge, complaint patterns, AI reasoning, final decision

Same-day repeat requests are served from cache (instant, $0 cost).

### Strands AgentCore Demo

```bash
export AWS_PROFILE=vista
python agents/strands_agent.py
```

Shows proper Bedrock AgentCore usage: system prompt, tool registration, autonomous tool selection, and the agent deciding when to invoke which tool.

---

## Configuration

All settings via environment variables or `.env` file:

| Variable | Default | Description |
|:--|:--|:--|
| `AWS_PROFILE` | — | AWS CLI profile name |
| `SNS_TOPIC_ARN` | hardcoded fallback | SNS topic for HIGH/CRITICAL alerts |
| `AWS_REGION` | `us-east-1` | Region for Bedrock + CloudWatch |
| `PORT` | `5000` | Flask server port |
| `DAILY_BUDGET_USD` | `1.00` | Daily spend cap; when exceeded, AI stages fall back to deterministic logic |

---

## Testing

**Automated test suite covering deterministic core logic and fallback behavior.**

```bash
# Run all tests
pytest tests/ -v

# Run specific test categories
pytest tests/unit/test_keyword_triage.py      # Stage 1: keyword detection
pytest tests/unit/test_action_decision.py     # Stage 4: decision rules
pytest tests/unit/test_fallbacks.py           # AI fallback behavior
pytest tests/unit/test_token_tracker.py       # Cost tracking
pytest tests/unit/test_daily_cache.py         # Cache behavior
pytest tests/integration/test_pipeline.py     # Full pipeline
```

**What is tested:**
- Stage 1 keyword triage: 130+ negative keywords across 5 categories, case-insensitivity, severity thresholds (0.15/0.25/0.40), multi-category detection
- Stage 4 action decision: all four outcomes (APPROVE/MONITOR/FLAG_FOR_REVIEW/FLAG_FOR_REMOVAL), threshold boundaries, SNS alert routing
- Deterministic fallbacks: Stage 2 pattern grouping by keyword frequency when Bedrock fails, Stage 3 rule-based risk scoring when Haiku fails, verified per ADR-002
- Token tracker: per-model cost calculation, budget enforcement, daily rollover, CloudWatch metrics
- Daily cache: ASIN+marketplace key construction, same-day hit/miss, old cache purging, tmp_path isolation
- Config: 25-marketplace domain mapping integrity

**What is NOT tested:**
- Live Bedrock API calls (Nova Micro, Claude Haiku) — mocked in all tests
- Selenium review scraping from Amazon — requires browser automation
- SNS/CloudWatch AWS integration — mocked to avoid requiring credentials
- Web UI Flask routes — out of scope for deterministic logic focus

Offline testing with pre-scraped data is possible via `sample_data/product_reviews_us.json`.

---

## AWS Services and Costs

| **Bedrock (Nova Micro)** | Pattern grouping | ~$0.001 per product |
| **Bedrock (Haiku 4.5)** | Risk assessment | ~$0.003 per product |
| **SNS** | Email alerts | Free tier (first 1,000/month) |
| **CloudWatch** | Metrics + alarms | Free tier (first 10 custom metrics) |

**Total per product:** ~$0.004 first analysis, $0 if cached same day
**100 products/day:** ~$0.40/day = ~$12/month
**Daily budget cap:** $1.00 default, configurable

The CloudFormation stack creates:
- SNS topic + email subscriptions
- IAM user with least-privilege permissions (Bedrock invoke, SNS publish, CloudWatch metrics)
- CloudWatch Log Group `/review-intel/app` (14-day retention)
- Metric Filter counting ERROR events
- Three alarms: HighFlagRate (>5/day), ErrorRate (>3/5min), BudgetHigh (>80%)

---

## Supported Marketplaces

All 25 Amazon retail marketplaces:

**Americas:** US, CA, MX, BR, CO
**Europe:** UK, DE, FR, IT, ES, NL, SE, PL, BE, IE, TR
**Middle East & Africa:** AE, SA, EG, ZA, NG
**Asia-Pacific:** IN, JP, SG, AU

Selected via dropdown in the web UI.

---

## Tradeoffs and Decisions I Made Along the Way

**Two AI models instead of one.** Stage 2 uses Nova Micro ($0.035 / 1M input tokens) because grouping complaint themes is mechanical pattern matching, not reasoning. Stage 3 uses Claude Haiku 4.5 ($1 / 1M input tokens) because risk assessment requires nuanced judgment. A single model would work but would either overpay for simple work (always Haiku) or underperform on complex judgments (always Nova). Splitting the workload by complexity is the right tradeoff for cost efficiency.

**Rule-based triage, not LLM-based.** Stage 1 is 130+ hardcoded keywords. An LLM could scan for complaints too, but keyword matching is $0, instant, deterministic, and just as accurate for this task. Adding an LLM here would cost ~$0.001 per call and deliver no improvement — the model would essentially learn the same keyword list. I kept it simple and free.

**Rule-based action decisions, not LLM-based.** Stage 4 thresholds are business rules: CRITICAL = flag for removal, HIGH = flag for review. These are policy, not judgment calls. An LLM would add cost and nondeterminism for decisions that should be predictable and auditable. The rules live in code where they can be version-controlled and tested.

**Strands demo as a separate file, not integrated.** The Strands SDK shows the "proper" Bedrock AgentCore pattern: tool registration, autonomous tool selection, and the agent managing its own tool-calling loop. I kept it separate from the main pipeline because integrating it would complicate the working system without adding functional value. The demo teaches the pattern; the pipeline solves the problem. Both goals are served by separation.

**Chrome over Firefox.** Selenium supports both. Chrome's `page_load_strategy='eager'` is faster, ChromeDriver auto-management via `selenium-manager` is more reliable, and Chrome is more commonly installed. The tradeoff is vendor lock-in, but for a scraping demo that's acceptable — the fetcher is easily swappable.

**Signal handlers + weakref for cleanup.** Selenium Chrome processes leak memory if not explicitly closed. A try/finally block catches normal exits but not SIGTERM, SIGINT, or crashes. I added `atexit` handlers, signal handlers, and a `weakref.WeakSet` registry to track all drivers and close them on any exit path. This is overkill for a demo but reflects real-world Selenium usage — leaked processes are a production problem.

**SSE streaming, not batch response.** The frontend receives results as they complete, with per-stage progress updates. This makes the pipeline feel responsive and builds trust — you can see which stage is active. The alternative (return everything at the end) is simpler to implement but worse for UX on multi-ASIN requests. The tradeoff is complexity in `app.py` to manage the generator, which I judged worth it.

**Daily cache by ASIN+marketplace, not ASIN alone.** The same product may have different reviews (and thus different risk levels) on different marketplaces. Caching by ASIN only would return US results for a UK query. The key is `f"{asin}_{marketplace}"` and the cache file is date-stamped so it auto-expires. This costs more disk space than ASIN-only but avoids stale results.

**SNS alerts only for HIGH/CRITICAL.** LOW and MEDIUM risks go to CloudWatch metrics only. Alerting on every product causes notification fatigue — operators stop reading emails. I reserved SNS for actionable items. The tradeoff is that you must check CloudWatch dashboards for MEDIUM trends, but that is a reasonable operational model.

**Fallback to rule-based on AI failure.** If Bedrock is unavailable or a prompt fails, Stages 2 and 3 fall back to deterministic logic. The service never returns an error to the user. The fallback is conservative — it flags more and misses less — so degraded mode is safer than failing. The tradeoff is that some results are less accurate, but availability beats precision for this use case.

**Tests stop at the network.** The tests cover keyword triage, the action decision, configuration, the daily cache, token tracking and the fallbacks when Bedrock is unavailable or over budget, plus one pipeline integration test with Bedrock, SNS and CloudWatch mocked. What they do not cover is the live part: Selenium fetching real review pages and real Bedrock responses. Those are checked manually through the web UI; testing them automatically would need recorded pages and recorded model responses.

---

## Limitations and Scope Boundaries

**Requires AWS Bedrock access.** Both models must be enabled in your account. Cross-region inference profiles may require additional setup. Without Bedrock access, the tool cannot run — there is no local-only mode.

**Scraping is fragile.** Amazon can change their review page structure at any time, breaking the Selenium selectors in `review_fetcher.py`. The scraper also disables images and uses eager page load for speed, which can miss dynamic content. This is a demonstration of the analysis pipeline, not a production-grade scraper. The real value is in the 4-stage processing logic, not the data collection.

**No batch CLI mode.** You must use the web UI. There is no `python -m review_risk_analyzer analyze products.csv` command. Adding one would be straightforward but was not needed for the demonstration.

**Chrome-only.** Firefox would work with minor changes to `review_fetcher.py`, but the setup script only checks for Chrome. Multi-browser support is not a goal.

**English-language reviews only.** The keyword list in Stage 1 is English. Claude and Nova can handle other languages in Stages 2-3, but triage will miss non-English complaints. Supporting 25 marketplaces does not mean supporting 25 languages.

**Not verified at scale.** The tool has been tested with tens of ASINs, not thousands. Selenium multi-tab fetching, budget tracking, and cache behavior are unverified beyond small workloads. Daily cache prevents runaway costs, but there is no tested upper bound.

---

## Stack

| Concern | Choice |
|:--|:--|
| Language | Python 3.10+ |
| Web framework | Flask 3.0+ |
| AI models | Amazon Bedrock (Nova Micro + Claude Haiku 4.5 via Converse API) |
| AgentCore | Strands SDK (`strands-agents`) |
| Browser automation | Selenium 4.15+ (headless Chrome) |
| Token counting | tiktoken |
| Cloud | AWS (Bedrock, SNS, CloudWatch, IAM) |
| IaC | CloudFormation |
| Frontend | Tailwind CSS, vanilla JS, Server-Sent Events |
