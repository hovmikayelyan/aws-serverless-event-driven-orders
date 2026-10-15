# Serverless & event-driven order platform (AWS, SAM + Python 3.12)

```
POST /orders ─► IngestFunction ─► EventBridge bus ─┬─ rule(all)        ─► SQS ─► BillingFunction       ─► DLQ
 (provisioned,   (validate,        (OrderPlaced,   ├─ rule(all)        ─► SQS ─► InventoryFunction     ─► DLQ
  arm64, alias)   schema v2)        schemaVersion) ├─ rule(priority=high)► SQS ─► NotificationsFunction ─► DLQ
                                                   └─ rule(amount>=100) ─► Step Functions saga
                                                      Validate → Parallel(Reserve ‖ Charge) → Wait → Ship
                                                                  └─ Catch → Compensate(release ‖ refund) → Fail
```

## Requirement → implementation

| Requirement | Where |
|---|---|
| **Cold-start optimized function** | `IngestFunction`: arm64, 512 MB, only `boto3` imported at module level, client created in init phase and reused, no heavy deps, `AutoPublishAlias: live` + **Provisioned Concurrency** (`IngestProvisionedConcurrency` param). Cold starts are counted with an EMF `ColdStart` metric; `scripts/coldstart-report.sh` reports `@initDuration`. |
| **Workflow orchestration** | `statemachine/fulfilment.asl.json`: sequential steps, **parallel fan-out/fan-in**, **retry with exponential backoff + jitter** (transient errors only), **saga compensation** on failure, **Wait** state. |
| **Event-driven fan-out** | One event → 3 consumers + saga, via EventBridge rules; **filtering** (`priority=high`, `amount>=100`); each consumer has its own SQS buffer. |
| **DLQ + retry logic** | Per-consumer SQS DLQ (`maxReceiveCount: 3`), partial-batch responses (`ReportBatchItemFailures`), EventBridge target `RetryPolicy` + delivery DLQ, DLQ alarm. |
| **Observability** | X-Ray active tracing on all Lambdas and the state machine; EMF custom metrics (`ColdStart`, `Processed`, `Failed`, `DuplicateSkipped`, `OrdersAccepted`, `OrdersShipped`); structured JSON logs; CloudWatch dashboard + DLQ and saga-failure alarms. |

Additional patterns: **idempotency** (DynamoDB conditional write, TTL, claim released on failure), **event versioning**
(`schemaVersion` + `upcast`), **protecting downstream** (SQS buffer + `ScalingConfig.MaximumConcurrency` so Lambda can't
stampede a database), **exactly-once simulation** = at-least-once delivery + idempotent consumers.

Production trade-offs: DLQ for poison messages vs. retry for transient ones (retry in SQS up to 3 times, then park);
retry storms are limited by capped attempts + backoff/jitter + max concurrency; a circuit breaker would sit in front of the real
downstream (not simulated here).

## Run

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # unit tests (no AWS needed)

sam validate --lint
sam build && sam deploy --guided       # needs AWS creds
scripts/demo.sh <ApiUrl output>        # exercises success, retry, compensation, DLQ paths
scripts/coldstart-report.sh <stack>    # cold-start stats; compare with IngestProvisionedConcurrency=0
aws sqs receive-message --queue-url <BillingDLQUrl output>   # inspect parked poison message
```
Tracing: CloudWatch → X-Ray traces map shows API → Lambda → EventBridge → SQS → consumers; Step Functions console shows
the retry/compensation path per execution.

## Credentials and secrets
No credentials are stored in this repo. `sam deploy` uses the AWS credentials already configured in your shell (profile, SSO or
environment variables). The Lambdas use their IAM execution roles, so no keys appear in code or the template.
