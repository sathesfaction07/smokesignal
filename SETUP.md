# Vista — Complete Project Documentation

---

## What This Project Does (Simple English)

This project **analyzes Amazon product reviews using AI** to detect problems with products. When you give it a product code (called ASIN), it:

1. Opens Amazon's website using an automated browser (Selenium Chrome headless)
2. Reads all the customer reviews from that product page
3. Scans those reviews for complaints about safety, quality, packaging, misleading descriptions, and general disappointment
4. Uses AI models (Amazon Bedrock) to understand patterns in the complaints
5. Assigns a risk level: LOW, MEDIUM, HIGH, or CRITICAL
6. Sends an email alert if the product is dangerous or seriously flawed

The whole process runs as a web application you open in your browser at `http://localhost:5000`.

---

## 4-Stage Analysis Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        VISTA ANALYSIS PIPELINE                               │
└──────────────────────────────────────────────────────────────────────────────┘

  ASIN + Reviews
       │
       ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  STAGE 1        │     │  STAGE 2        │     │  STAGE 3        │     │  STAGE 4        │
│  TRIAGE         │────▶│  PATTERN        │────▶│  RISK           │────▶│  ACTION         │
│                 │     │  ANALYSIS       │     │  ASSESSMENT     │     │  DECISION       │
│  Keyword scan   │     │  Nova Micro     │     │  Claude         │     │  Rule-based     │
│  130+ triggers  │     │  amazon.nova-   │     │  Haiku 4.5      │     │  routing        │
│  5 categories   │     │  micro-v1:0     │     │  us.anthropic.  │     │                 │
│                 │     │                 │     │  claude-haiku-  │     │  APPROVE        │
│  Cost: $0       │     │  Cost: ~$0.001  │     │  4-5-20251001   │     │  MONITOR        │
│  (pure Python)  │     │  per ASIN       │     │  -v1:0          │     │  FLAG_FOR_REVIEW│
│                 │     │                 │     │                 │     │  FLAG_FOR_REMOVAL│
│  Output:        │     │  Output:        │     │  Cost: ~$0.003  │     │                 │
│  neg%, severity │     │  3–5 complaint  │     │  per ASIN       │     │  HIGH/CRITICAL  │
│  category map   │     │  theme clusters │     │                 │     │  → SNS alert    │
│                 │     │                 │     │  Output:        │     │                 │
│                 │     │                 │     │  risk level +   │     │  Cost: $0       │
│                 │     │                 │     │  reasoning      │     │  (pure rules)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘     └─────────────────┘
         │                       │                       │                       │
         └───────────────────────┴───────────────────────┴───────────────────────┘
                                             │
                                             ▼
                                    Total per ASIN: ~$0.004
                                    Daily cache prevents reprocessing
                                    Budget enforced ($1.00/day default)
```

---

## Prerequisites

| Requirement | Version | How to Check | Install |
|-------------|---------|--------------|---------|
| Python | 3.10+ | `python3 --version` | [python.org](https://www.python.org/downloads/) |
| pip | Latest | `pip --version` | Bundled with Python |
| Chrome | Latest stable | `google-chrome --version` | [google.com/chrome](https://www.google.com/chrome/) |
| ChromeDriver | Auto-managed | n/a | Handled by `selenium-manager` (bundled with Selenium 4.6+) |
| AWS CLI | v2.x+ | `aws --version` | [AWS CLI Install Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) |
| Git | Any | `git --version` | [git-scm.com](https://git-scm.com/) |

> **Note:** ChromeDriver does **not** need to be installed manually. Selenium's built-in `selenium-manager` downloads the correct driver version for your installed Chrome automatically.

---

## Supported Marketplaces

Vista supports all 25 Amazon retail marketplaces. Select the target marketplace in the UI dropdown or pass it in the API call.

### Americas (5)

| Code | Country | Domain |
|------|---------|--------|
| US | United States | amazon.com |
| CA | Canada | amazon.ca |
| MX | Mexico | amazon.com.mx |
| BR | Brazil | amazon.com.br |
| CO | Colombia | amazon.com.co |

### Europe (11)

| Code | Country | Domain |
|------|---------|--------|
| UK | United Kingdom | amazon.co.uk |
| DE | Germany | amazon.de |
| FR | France | amazon.fr |
| IT | Italy | amazon.it |
| ES | Spain | amazon.es |
| NL | Netherlands | amazon.nl |
| SE | Sweden | amazon.se |
| PL | Poland | amazon.pl |
| BE | Belgium | amazon.com.be |
| IE | Ireland | amazon.ie |
| TR | Turkey | amazon.com.tr |

### Middle East & Africa (5)

| Code | Country | Domain |
|------|---------|--------|
| AE | United Arab Emirates | amazon.ae |
| SA | Saudi Arabia | amazon.sa |
| EG | Egypt | amazon.eg |
| ZA | South Africa | amazon.co.za |
| NG | Nigeria | amazon.com.ng |

### Asia Pacific (4)

| Code | Country | Domain |
|------|---------|--------|
| IN | India | amazon.in |
| JP | Japan | amazon.co.jp |
| SG | Singapore | amazon.sg |
| AU | Australia | amazon.com.au |

---

## Project File Structure — What Each File Does

```
bedrock-review-intel/
│
├── app.py                              ← The web server (starts everything)
├── config.py                           ← All settings in one place
├── requirements.txt                    ← List of Python packages needed
├── .gitignore                          ← Files Git should ignore
├── SETUP.md                            ← Quick setup reference
│
├── agents/                             ← The AI brains
│   ├── __init__.py                     ← Makes this a Python package
│   ├── review_fetcher.py              ← Opens Amazon pages and reads reviews
│   ├── review_analyzer.py            ← 4-stage AI analysis pipeline
│   └── strands_agent.py              ← Bedrock AgentCore (Strands SDK) demo
│
├── monitoring/                         ← Watching costs and performance
│   ├── __init__.py                     ← Makes this a Python package
│   ├── logger.py                      ← Structured JSON logging (vista.* namespace)
│   ├── token_tracker.py              ← Counts AI tokens used + daily budget
│   └── daily_cache.py                ← Saves results to avoid re-processing
│
├── infra/                              ← AWS infrastructure as code
│   └── cloudformation.yaml           ← One-click AWS setup
│
├── sample_data/                        ← Test data
│   └── product_reviews_us.json       ← Example reviews for testing
│
├── static/                             ← Frontend (what you see in browser)
│   └── index.html                     ← The web page UI
│
└── .cache/                             ← Auto-created, stores today's results
    └── results_2026-08-04.json        ← Cache file (auto-deleted next day)
```

---

## Key Component Details

### Root Folder

| File | What It Does |
|------|-------------|
| **app.py** | The main entry point. Starts a Flask web server on port 5000. Has two endpoints: `GET /` serves the web page, `POST /analyze` processes ASINs and streams results back to the browser in real-time using Server-Sent Events (SSE). |
| **config.py** | Central configuration. Stores AWS region, model IDs (Nova Micro for cheap work, Claude Haiku 4.5 for smart reasoning), token pricing, CloudWatch namespace, and all 25 Amazon marketplace domains. |
| **requirements.txt** | Lists all Python libraries the project needs: boto3 (AWS), flask (web server), selenium (Chrome headless browser automation), tiktoken (token counting), python-dotenv (env files), strands-agents (AgentCore SDK). |
| **.gitignore** | Tells Git to skip: Python cache files, virtual environments, .env files, build artifacts, macOS .DS_Store, and the .cache folder. |
| **SETUP.md** | Quick-start guide for setting up on a new machine or AWS account. |

### agents/ Folder (The AI Brains)

| File | What It Does |
|------|-------------|
| **review_fetcher.py** | Uses Selenium (automated Chrome headless browser) to open Amazon product pages and extract reviews. Has 3 modes: single ASIN, batch (all at once), and streaming (yields results one by one for real-time UI). Opens multiple browser tabs in parallel for speed. Uses `page_load_strategy='eager'` and disables images for fast loading. Includes graceful cleanup — if the app crashes or is killed, the browser still gets closed properly via `atexit` handlers, signal handlers, and a `weakref.WeakSet` registry. |
| **review_analyzer.py** | The 4-stage pipeline (2 AI-powered + 2 deterministic). **Stage 1 (Triage)**: Scans review text for 130+ negative keywords across 5 categories — zero AI cost. **Stage 2 (Patterns)**: Sends reviews to Amazon Nova Micro (~$0.001/call) to group complaints into themes. **Stage 3 (Assessment)**: Sends triage + patterns to Claude Haiku 4.5 (~$0.003/call) for intelligent risk evaluation. **Stage 4 (Action)**: Rule-based decision — APPROVE/MONITOR/FLAG_FOR_REVIEW/FLAG_FOR_REMOVAL — plus SNS email alerts for HIGH/CRITICAL products. Every AI call checks the daily budget first and tracks token usage. |
| **strands_agent.py** | Demonstrates Bedrock AgentCore using the Strands SDK. Creates a proper AI agent with: a system prompt, two registered tools (`classify_risk_level` and `check_safety_keywords`), and automatic tool-use orchestration. The agent autonomously decides when to call which tool. This shows AgentCore knowledge — the agent handles the tool-calling loop itself rather than us manually coding each step. |

### monitoring/ Folder (Watching Costs and Performance)

| File | What It Does |
|------|-------------|
| **logger.py** | Creates structured JSON logs using Python logger namespace `vista` (child loggers: `vista.fetcher`, `vista.analyzer`, `vista.agentcore`, etc.). Log format: `{"timestamp": "...", "level": "ERROR", "module": "vista.analyzer", "event": "..."}`. Designed to ship to CloudWatch Logs where Metric Filters detect ERROR patterns and trigger alarms. |
| **token_tracker.py** | Counts every token sent to and received from AI models. Calculates real-time cost. Enforces a daily budget ($1.00 default, configurable via `DAILY_BUDGET_USD`) — if exceeded, raises `BudgetExceededError` which stops processing gracefully. Publishes metrics (`TokensUsedTotal`, `CostUSD`, `BudgetUtilizationPct`) to CloudWatch. |
| **daily_cache.py** | Saves processed results to a JSON file keyed by ASIN + marketplace for the current date. If you analyze the same ASIN+marketplace twice in one day, the second time is instant (served from cache). When a new day starts, yesterday's cache is automatically deleted. Prevents redundant AI costs. |

### infra/ Folder (AWS Infrastructure)

| File | What It Does |
|------|-------------|
| **cloudformation.yaml** | A CloudFormation template that creates ALL AWS resources with one click: (1) SNS Topic for email alerts, (2) Email subscriptions, (3) IAM User with least-privilege permissions (Bedrock invoke, SNS publish, CloudWatch metrics), (4) Access keys, (5) CloudWatch Log Group `/review-intel/app`, (6) Metric Filter that counts ERROR logs, (7) Three CloudWatch Alarms: high flag rate, high error rate, and budget utilization > 80%. All alarms notify via SNS email. |

### static/ Folder (Frontend)

| File | What It Does |
|------|-------------|
| **index.html** | Single-page web application using Tailwind CSS. Shows: a pipeline info strip (4 cards showing what each stage does — animates during processing), an input form for ASINs + marketplace selector, a progress bar with live agent status, and result cards showing product name, rating, risk level, category breakdown, AI reasoning, and final decision. The ASIN is a clickable link to the actual Amazon product page. |

---

## How Everything Works Together — Flowchart

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         USER OPENS BROWSER                               │
│                      http://localhost:5000                                │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (static/index.html)                                            │
│                                                                          │
│  User enters: B08RWPHMZF, B09V3KXJPB                                    │
│  Selects marketplace: US                                                 │
│  Clicks "Analyze"                                                        │
│                                                                          │
│  → Sends POST /analyze {asins: "B08RWPHMZF,B09V3KXJPB", marketplace}    │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FLASK SERVER (app.py)                                                   │
│                                                                          │
│  1. Parse ASINs from request                                             │
│  2. Check daily_cache for each ASIN+marketplace                          │
│     ├── CACHED? → Immediately stream result to frontend                  │
│     └── NOT CACHED? → Add to fetch list                                  │
│  3. Launch Selenium multi-tab fetch for uncached ASINs                   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  FETCHER AGENT (agents/review_fetcher.py)                                │
│                                                                          │
│  1. Launch ONE headless Chrome browser (page_load_strategy='eager',      │
│     images disabled for speed)                                           │
│  2. Open one tab per ASIN (all load in parallel)                         │
│  3. Wait for pages to load                                               │
│  4. Switch to each tab → extract product info + reviews                  │
│  5. Yield results one by one back to app.py                              │
│  6. Close browser when done (or on crash via atexit/signal/WeakSet)      │
│                                                                          │
│  ⚠️ If fetch fails → yield error → app.py skips AI stages (saves $$$)    │
│  ⚠️ If no reviews found → yield error → skip AI stages                   │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  ANALYZER PIPELINE (agents/review_analyzer.py)                           │
│  For each ASIN with reviews:                                             │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ STAGE 1: TRIAGE (run_triage)                                    │     │
│  │ • No AI cost — pure Python keyword matching                     │     │
│  │ • Scans 130+ keywords across 5 categories                      │     │
│  │ • Output: negative %, severity, category breakdown              │     │
│  └───────────────────────────────┬─────────────────────────────────┘     │
│                                  │                                        │
│                                  ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ STAGE 2: PATTERNS (run_pattern_analysis)                        │     │
│  │ • Calls Amazon Nova Micro (~$0.001) via Bedrock Converse API    │     │
│  │ • Budget check → Token tracking → Model call                   │     │
│  │ • Groups complaints into 3-5 recurring themes                   │     │
│  │ • Fallback: keyword-based grouping if AI fails                  │     │
│  └───────────────────────────────┬─────────────────────────────────┘     │
│                                  │                                        │
│                                  ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ STAGE 3: ASSESSMENT (run_safety_assessment)                     │     │
│  │ • Calls Claude Haiku 4.5 (~$0.003) via Bedrock Converse API    │     │
│  │ • Budget check → Token tracking → Model call                   │     │
│  │ • AI reasons about overall product health                       │     │
│  │ • Output: risk level + primary concern + reasoning              │     │
│  │ • Fallback: rule-based assessment if AI fails                   │     │
│  └───────────────────────────────┬─────────────────────────────────┘     │
│                                  │                                        │
│                                  ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────┐     │
│  │ STAGE 4: ACTION (run_action_decision)                           │     │
│  │ • No AI cost — pure rules                                       │     │
│  │ • CRITICAL → FLAG_FOR_REMOVAL → SNS email alert                 │     │
│  │ • HIGH     → FLAG_FOR_REVIEW  → SNS email alert                 │     │
│  │ • MEDIUM   → MONITOR          → CloudWatch metric only          │     │
│  │ • LOW      → APPROVE          → CloudWatch metric only          │     │
│  └─────────────────────────────────────────────────────────────────┘     │
│                                                                          │
└─────────────────────────────┬───────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  RESULTS                                                                 │
│                                                                          │
│  1. Result saved to .cache/ keyed by ASIN+marketplace (same-day reuse)  │
│  2. Result streamed to frontend via SSE                                  │
│  3. CloudWatch metrics published (TokensUsedTotal, CostUSD, flags)       │
│  4. If HIGH/CRITICAL: SNS email sent to subscribed addresses             │
│  5. Frontend displays: risk badge, patterns, reasoning, decision         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## AWS Services Used and Why

```
┌──────────────────────────────────────────────────────────────────┐
│                    AWS SERVICES MAP                                │
│                                                                    │
│  ┌─────────────┐     ┌──────────────────┐     ┌──────────────┐   │
│  │   BEDROCK   │     │   CLOUDWATCH     │     │     SNS      │   │
│  │             │     │                  │     │              │   │
│  │ Nova Micro  │     │ Custom Metrics:  │     │ Email alerts │   │
│  │ (patterns)  │     │ • TokensUsedTotal│     │ to subscribed│   │
│  │             │     │ • CostUSD        │     │ addresses    │   │
│  │ Claude      │     │ • BudgetUtil%    │     │              │   │
│  │ Haiku 4.5   │     │ • ProductFlags   │     │ Triggers on: │   │
│  │ (assessment)│     │ • AppErrors      │     │ • HighFlagRt │   │
│  │             │     │                  │     │ • ErrorRate  │   │
│  │ AgentCore   │     │ 3 Alarms:        │     │ • BudgetHigh │   │
│  │ (Strands)   │     │ • HighFlagRate   │     │              │   │
│  └─────────────┘     │ • ErrorRate      │     └──────────────┘   │
│                       │ • BudgetHigh     │                        │
│                       │                  │                        │
│                       │ Log Group:       │                        │
│                       │ /review-intel/app│                        │
│                       │ + Metric Filter  │                        │
│                       └──────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
```

| Service | Purpose | When Used |
|---------|---------|-----------|
| **Amazon Bedrock** | Invoke AI models | Stage 2 (Nova Micro) + Stage 3 (Claude Haiku 4.5) |
| **Amazon SNS** | Email alerts | When a product is flagged HIGH or CRITICAL |
| **Amazon CloudWatch** | Metrics + Alarms + Logs | Every analysis — cost tracking, error detection |
| **AWS IAM** | Least-privilege credentials | IAM user created by CloudFormation |

---

## CloudFormation Parameters

The stack in `infra/cloudformation.yaml` accepts the following parameters:

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `AlertEmailList` | `CommaDelimitedList` | No | *(empty — no alerts)* | Comma-separated email addresses that receive FLAG_FOR_REMOVAL and FLAG_FOR_REVIEW alerts. Example: `alice@example.com,bob@example.com`. Each address must confirm the subscription email before alerts are delivered. |

### CloudFormation Outputs

After `CREATE_COMPLETE`, the stack produces these outputs — copy them for your environment setup:

| Output Key | Description | Used As |
|------------|-------------|---------|
| `SNSTopicArn` | Full ARN of the alerts topic | `SNS_TOPIC_ARN` env var |
| `AccessKeyId` | IAM access key for the `review-intel-deployer` user | `aws configure --profile vista` |
| `SecretAccessKey` | IAM secret key — **save immediately, cannot retrieve later** | `aws configure --profile vista` |
| `AppLogGroupName` | CloudWatch Log Group name for shipping app logs | Ship `vista.*` logger output here |

### Resources Created by CloudFormation

| Resource | Type | Name/ARN |
|----------|------|---------|
| SNS Topic | `AWS::SNS::Topic` | `bedrock-processor-alerts` |
| Email Subscription | `AWS::SNS::Subscription` | Per address in `AlertEmailList` |
| IAM User | `AWS::IAM::User` | `review-intel-deployer` |
| IAM Policy | `AWS::IAM::ManagedPolicy` | `ReviewIntel-AppPermissions` |
| IAM Access Key | `AWS::IAM::AccessKey` | (rotatable) |
| CloudWatch Log Group | `AWS::Logs::LogGroup` | `/review-intel/app` (14-day retention) |
| Metric Filter | `AWS::Logs::MetricFilter` | Counts `$.level = "ERROR"` events |
| Alarm: High Flag Rate | `AWS::CloudWatch::Alarm` | `ReviewIntel-HighFlagRate` (>5 flags/day) |
| Alarm: Error Rate | `AWS::CloudWatch::Alarm` | `ReviewIntel-ErrorRate` (>3 errors/5 min) |
| Alarm: Budget High | `AWS::CloudWatch::Alarm` | `ReviewIntel-BudgetHigh` (>80% daily budget) |

---

## Switching to a Different AWS Account

If you want to use a completely different AWS account (not account YOUR_AWS_ACCOUNT_ID), here is exactly what changes:

### What You Need to Do

1. **Deploy CloudFormation stack** on the new account (creates everything automatically)
2. **Enable Bedrock models** on the new account
3. **Change 2 environment variables** on your machine
4. **Confirm email subscriptions** (click link in email)

### What Does NOT Change

- No code changes needed
- No file edits
- The application itself is 100% account-agnostic
- Everything account-specific comes from environment variables

### One Thing to Update in Code (Optional)

The file `agents/review_analyzer.py` has a hardcoded fallback SNS ARN:
```python
SNS_TOPIC_ARN = os.environ.get(
    "SNS_TOPIC_ARN",
    "arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:bedrock-processor-alerts",  ← change this
)
```
If you set the `SNS_TOPIC_ARN` environment variable (recommended), this fallback is never used. But for safety, update the account ID to your new one.

---

## Commands to Get the Project Running

### Scenario 1: New AWS Account (First Time Setup)

#### macOS / Linux Terminal

```bash
# Step 1: Deploy AWS infrastructure
# Go to AWS Console → CloudFormation → Create Stack → Upload infra/cloudformation.yaml
# Set AlertEmailList parameter to your email(s)
# Wait for CREATE_COMPLETE, then copy Outputs (AccessKeyId, SecretAccessKey, SNSTopicArn)

# Step 2: Enable Bedrock models
# AWS Console → Bedrock → Model Access → Enable:
#   - Amazon Nova Micro  (amazon.nova-micro-v1:0)
#   - Anthropic Claude Haiku 4.5  (requires cross-region inference profile)
# Wait for "Access granted"

# Step 3: Configure AWS CLI
aws configure --profile vista
# Enter: Access Key ID from CloudFormation Outputs
# Enter: Secret Access Key from CloudFormation Outputs
# Region: us-east-1
# Output format: json

# Step 4: Confirm email subscription
# Check your inbox for "AWS Notification - Subscription Confirmation"
# Click "Confirm subscription" link

# Step 5: Install Python dependencies
cd bedrock-review-intel
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Step 6: Install Chrome (if not already)
# Chrome is usually pre-installed on macOS; if not:
# macOS: brew install --cask google-chrome
# Ubuntu/Debian: sudo apt install google-chrome-stable

# Step 7: Set environment variables and run
export AWS_PROFILE=vista
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts
python app.py

# Open browser: http://localhost:5000
```

#### Windows Terminal (Command Prompt)

```cmd
REM Step 1: Deploy AWS infrastructure
REM Go to AWS Console → CloudFormation → Create Stack → Upload infra\cloudformation.yaml
REM Set AlertEmailList parameter to your email(s)
REM Wait for CREATE_COMPLETE, copy Outputs

REM Step 2: Enable Bedrock models
REM AWS Console → Bedrock → Model Access → Enable:
REM   - Amazon Nova Micro
REM   - Anthropic Claude Haiku 4.5

REM Step 3: Configure AWS CLI
aws configure --profile vista
REM Enter: Access Key ID from CloudFormation Outputs
REM Enter: Secret Access Key from CloudFormation Outputs
REM Region: us-east-1
REM Output format: json

REM Step 4: Confirm email subscription (check inbox, click link)

REM Step 5: Install Python dependencies
cd bedrock-review-intel
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

REM Step 6: Install Chrome
REM Download from https://www.google.com/chrome/ and install
REM OR: winget install Google.Chrome

REM Step 7: Set environment variables and run
set AWS_PROFILE=vista
set SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts
python app.py

REM Open browser: http://localhost:5000
```

#### Windows Terminal (PowerShell)

```powershell
# Step 1-4: Same as above (AWS Console steps)

# Step 5: Install Python dependencies
cd bedrock-review-intel
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Step 6: Install Chrome
# Download from https://www.google.com/chrome/ and install
# OR: winget install Google.Chrome

# Step 7: Set environment variables and run
$env:AWS_PROFILE = "vista"
$env:SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts"
python app.py

# Open browser: http://localhost:5000
```

---

### Scenario 2: Existing AWS Account (Already Set Up)

#### macOS / Linux

```bash
cd bedrock-review-intel
source .venv/bin/activate        # If using virtual environment
export AWS_PROFILE=vista
export SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:bedrock-processor-alerts
python app.py
```

#### Windows Command Prompt

```cmd
cd bedrock-review-intel
.venv\Scripts\activate
set AWS_PROFILE=vista
set SNS_TOPIC_ARN=arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:bedrock-processor-alerts
python app.py
```

#### Windows PowerShell

```powershell
cd bedrock-review-intel
.\.venv\Scripts\Activate.ps1
$env:AWS_PROFILE = "vista"
$env:SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:YOUR_AWS_ACCOUNT_ID:bedrock-processor-alerts"
python app.py
```

---

## Adding Email Subscribers for Alerts

When a product is flagged (HIGH or CRITICAL risk), an email is sent. To add more recipients:

#### macOS / Linux

```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts \
  --protocol email \
  --notification-endpoint newperson@example.com \
  --profile vista
```

#### Windows Command Prompt

```cmd
aws sns subscribe ^
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts ^
  --protocol email ^
  --notification-endpoint newperson@example.com ^
  --profile vista
```

#### Windows PowerShell

```powershell
aws sns subscribe `
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts `
  --protocol email `
  --notification-endpoint newperson@example.com `
  --profile vista
```

**Important**: The new subscriber MUST click "Confirm subscription" in the email they receive. Without confirmation, they will not get alerts.

---

## Removing Email Subscribers

```bash
# First, list all subscribers
aws sns list-subscriptions-by-topic \
  --topic-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts \
  --profile vista

# Then unsubscribe using the SubscriptionArn from the list
aws sns unsubscribe \
  --subscription-arn arn:aws:sns:us-east-1:YOUR_ACCOUNT_ID:bedrock-processor-alerts:abc123 \
  --profile vista
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_PROFILE` | Yes | — | Name of your AWS CLI profile (`vista` for this project) |
| `SNS_TOPIC_ARN` | Yes | hardcoded fallback | Full ARN of the SNS topic for HIGH/CRITICAL alerts |
| `AWS_REGION` | No | `us-east-1` | AWS region for Bedrock + CloudWatch |
| `PORT", 5000` | Port the Flask web server listens on |
| `DAILY_BUDGET_USD` | No | `1.00` | Max daily spend on AI models (USD) before halting with `BudgetExceededError` |

---

## Cost Breakdown

| What | Cost | When |
|------|------|------|
| Triage (Stage 1) | $0 | Always free — pure Python keyword matching |
| Pattern Analysis (Stage 2) | ~$0.001 | Per ASIN analyzed (Nova Micro) |
| Risk Assessment (Stage 3) | ~$0.003 | Per ASIN analyzed (Claude Haiku 4.5) |
| Action (Stage 4) | $0 | Always free — pure rules |
| SNS email | $0 | Free tier (first 1,000/month) |
| CloudWatch metrics | $0 | Free tier (first 10 custom metrics) |
| **Total per ASIN** | **~$0.004** | First analysis; $0 if cached same day |
| **100 ASINs/day** | **~$0.40/day** | ~$12/month |
| **Daily budget cap** | **$1.00** | Configurable via `DAILY_BUDGET_USD` |

---

## Testing

Vista does **not** have a formal automated test suite. The application is tested manually via the web UI.

### Manual Testing Steps

1. Start the app: `python app.py`
2. Open `http://localhost:5000`
3. Enter ASINs in any format:
   - Single ASIN: `B0GXYH3B95`
   - Full URL: `https://www.amazon.com/dp/B0GXYH3B95#customer-reviews_feature_div`
   - Comma-separated: `B0GXYH3B95, B07XJ8C8F7`
   - Space/newline-separated also works
   - Mixed (URLs + bare ASINs) also works
4. Select a marketplace (start with `US`)
5. Click **Analyze** and observe:
   - The 4 pipeline stage cards animate as processing progresses
   - Results appear per ASIN with risk badge, pattern breakdown, and AI assessment
   - AI Assessment shows: ✅ Positive observations, ⚠️ Negative observations, 📝 Reasoning
   - If SNS credentials are not configured, actions will show "⚠️ Email alert failed"
   - Check that a `.cache/results_YYYY-MM-DD.json` file was created

### Testing with Sample Data

The file `sample_data/product_reviews_us.json` contains pre-scraped reviews for offline testing. You can load it directly into `review_analyzer.py` without running the Selenium browser fetcher.

### Strands AgentCore Demo

```bash
# Run the standalone AgentCore demo (no browser needed)
source .venv/bin/activate
export AWS_PROFILE=vista
python agents/strands_agent.py
```

### Future Testing

If a test suite is added later, the recommended approach is:
- **Unit tests** — `pytest agents/` for keyword matching and pipeline logic
- **Integration tests** — mock Bedrock `converse` responses to avoid AWS costs in CI

---

## Cleanup

### Local Cleanup

```bash
# Stop the server
# Press Ctrl+C in the terminal running python app.py

# Delete today's cache (forces fresh analysis next run)
rm -rf bedrock-review-intel/.cache/

# Deactivate virtual environment
deactivate

# Full local teardown (removes venv and cache)
cd bedrock-review-intel
rm -rf .venv/ .cache/ __pycache__/ agents/__pycache__/ monitoring/__pycache__/
```

### AWS Cleanup (Tear Down Infrastructure)

> ⚠️ This permanently deletes the SNS topic (losing all subscriptions), CloudWatch alarms, log group, and IAM user.

```bash
# Delete the CloudFormation stack (removes all AWS resources in one step)
aws cloudformation delete-stack \
  --stack-name vista-infra \
  --profile vista \
  --region us-east-1

# Wait for deletion to complete
aws cloudformation wait stack-delete-complete \
  --stack-name vista-infra \
  --profile vista \
  --region us-east-1

# Optionally remove the local AWS CLI profile
aws configure --profile vista set aws_access_key_id ""
# Or manually delete from ~/.aws/credentials and ~/.aws/config
```

### Partial Cleanup (Keep Infrastructure, Reset App State)

```bash
# Clear cache only (next run re-processes all ASINs)
rm -rf bedrock-review-intel/.cache/

# Reset daily budget counter (restart the app — budget resets each calendar day automatically)
# No manual reset needed; daily_cache.py handles this on startup.
```

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| `ModuleNotFoundError: No module named 'flask'` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `Address already in use. Port 5000` | Previous server still running | Kill it: `lsof -ti:5000 \| xargs kill` (Mac/Linux) or `netstat -ano \| findstr :5000` then `taskkill /PID xxx /F` (Windows) |
| `AccessDeniedException` from Bedrock | Models not enabled | Go to Bedrock Console → Model Access → Enable Nova Micro + Claude Haiku 4.5 |
| `No reviews found` | Amazon blocked the request | Try a different ASIN, or wait 5 minutes and retry |
| `Chrome not found` | Chrome not installed | Install from [google.com/chrome](https://www.google.com/chrome/) |
| `BudgetExceededError` | Daily budget hit ($1.00 default) | Increase: `export DAILY_BUDGET_USD=5.00` or wait until tomorrow (auto-resets) |
| Old/wrong results showing | Stale cache | Delete `.cache/` folder and restart |
| SNS email not received | Subscription not confirmed | Check spam folder, click confirmation link in the "AWS Notification" email |
| `InvalidIdentityToken` on Windows | AWS credentials misconfigured | Re-run `aws configure --profile vista` |
| ChromeDriver version mismatch | Selenium-manager not running | Upgrade Selenium: `pip install --upgrade selenium` |
| `WebDriverException: Chrome not reachable` | Chrome crashed mid-analysis | Restart the app — `atexit` handlers ensure cleanup; browser will reinitialize |
| CloudWatch metrics not appearing | Wrong namespace or IAM perms | Verify `CLOUDWATCH_NAMESPACE = "BedrockReviewIntel"` in config.py and IAM policy has `cloudwatch:PutMetricData` |

---

## Tradeoffs and Decisions Made Along the Way

| Decision | Alternatives Considered | Why This Choice |
|----------|------------------------|----------------|
| All 4 stages in one file (`review_analyzer.py`) | Separate files per stage | Keeps related logic together; all stages share triage context; easier top-to-bottom reading |
| Nova Micro for patterns, Haiku for assessment | Single model for both | Pattern grouping is mechanical (no reasoning needed); assessment requires nuanced judgment |
| Rule-based triage (130+ keywords) | LLM-based triage | $0 cost, instant, deterministic; LLM would add ~$0.001/call for the same keyword matching |
| Rule-based action decisions | LLM-based decisions | Thresholds are business rules, not judgment calls; predictable, auditable, zero cost |
| Strands SDK demo as separate file | Integrated into main pipeline | Shows the 'proper' AgentCore pattern without disrupting the working pipeline |
| Daily budget $1 (not $5) | Higher budget | Vista processes individual ASINs (lower per-call cost); $1 covers ~250 ASINs/day |
| Chrome headless over Firefox | Firefox/GeckoDriver | Faster rendering, better eager load strategy, more commonly available |
| Signal handlers + weakref for cleanup | Try/finally only | Chrome processes leak memory; must kill on any exit path including crashes |
| SSE streaming with per-stage progress | Batch response after completion | User sees which stage is active in real time; builds trust in the pipeline |
| Cache by ASIN+marketplace | ASIN-only cache key | Same product may have different reviews/risk levels on different marketplaces |
| SNS alerts only for HIGH/CRITICAL | Alert on all risk levels | LOW/MEDIUM are informational; alerting on everything causes notification fatigue |
| Fallback to rule-based on LLM failure | Return error to user | Service never goes down; deterministic fallback is conservative (flags more, misses less) |

---

*These decisions reflect the constraints of educational demonstration: simplicity, testability with available data, beginner-friendly Python, and clear demonstration of Bedrock AgentCore + tokenization + CloudWatch alarm competencies.*
