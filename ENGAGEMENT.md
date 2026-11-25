# Engagement readout: Smokesignal

How this project would be scoped, delivered and handed over if it were a customer engagement.
The customer is a composite: a product safety team at a large online retailer, not a named
company. Test results are reproducible from this repository; costs are estimates from list prices.

## The customer and what they asked for

Customer reviews arrive continuously across thousands of products. A few mention fires, choking
hazards or injuries, often in passing and often in reviews with four or five stars. The team finds
them late, by chance or after a complaint escalates.

**The ask:** "Use an LLM to read all the reviews and tell us which products are dangerous."

## What discovery found

| Observed | What it meant |
|:--|:--|
| Most reviews contain no complaint at all | Sending every review to a model pays for reading noise. A free keyword pass can decide which products need a model at all |
| Grouping complaints into themes is mechanical; judging severity is not | Two models: a very cheap one for grouping, a stronger one for the risk call |
| "Flag for removal" is a policy decision with legal weight | The final action must come from versioned rules on the model's risk level, not from the model |
| The team's spend is approved monthly | A hard daily budget, checked before every model call, with a deterministic fallback when it is reached |
| Alert fatigue already exists | Email only for HIGH and CRITICAL; everything else goes to metrics |

## What was delivered

- A four-stage pipeline: keyword triage (no model), theme grouping (Amazon Nova Micro), risk
  assessment (Claude Haiku), and a rule-based action decision.
- A deterministic fallback for each model stage, used on any failure or when the budget is spent.
  The fallback is conservative: it flags more rather than less.
- Per-model token and cost tracking with a daily cap, a same-day cache keyed by product and
  marketplace, and alerts through SNS with CloudWatch metrics and alarms.
- Infrastructure as code (CloudFormation) with a least-privilege IAM user.
- A web UI that streams each product's result as its stages complete.

## Proof that it works

| Claim | Evidence | Reproduce |
|:--|:--|:--|
| Triage catches complaints across five categories at the documented thresholds | Keyword triage tests | `pytest tests/unit/test_keyword_triage.py` |
| Actions follow the policy exactly at every boundary | Action decision tests | `pytest tests/unit/test_action_decision.py` |
| A model outage or a spent budget degrades safely, never errors | Fallback tests | `pytest tests/unit/test_fallbacks.py` |
| Spend cannot exceed the cap | Token tracker tests, including daily rollover | `pytest tests/unit/test_token_tracker.py` |
| The stages work together | Pipeline test with Bedrock, SNS and CloudWatch mocked | `pytest tests/integration/test_pipeline.py` |

## What is not yet proven, and how the engagement would prove it

**The quality of the model's risk call has not been measured.** The tests prove the pipeline,
the policy and the fallbacks, not whether Haiku rates a real product's risk correctly. Phase 1 is
built around closing that gap: products the safety team has already investigated become a
labelled set, and the readout reports how many confirmed hazards Smokesignal flagged (recall, the
number that matters) and how many flags were noise (the number that matters to the team's time),
for the model path and for the fallback path separately.

**Review collection is a demonstration.** The browser-based fetcher is fragile by nature. In a
real deployment the customer's own review data feed replaces it, and that integration is the
first piece of work in phase 1.

## Rollout plan

| Phase | What changes | Gate to move on |
|:--|:--|:--|
| 1. Shadow | Connect the customer's review feed; run daily; no alerts sent; compare flags with the team's own investigations | Recall on known hazards measured and agreed; noise rate acceptable to the team |
| 2. Alert | HIGH and CRITICAL alerts go to the safety team's queue for review | Every alert is triaged within the team's SLA; false alarms reviewed weekly and fed into keywords and prompts |
| 3. Scale | Extend to all products and to non-English marketplaces | Keyword triage covers the new languages (today it is English only) |

## Risks and open items

- **English-only triage** misses non-English complaints before any model sees them.
- **Tested with tens of products, not thousands.** Throughput and cache behaviour at scale are
  unverified.
- **Costs** (~$0.004 per product) are list-price estimates, not measured spend.

## Feedback for the platform team

Every model call here needed the same scaffolding around it: a budget check, token accounting, a
deterministic fallback and a cache. Customers rebuild this in each project; a managed per-project
spend cap with a fallback hook would remove a week of work from most engagements like this one.
