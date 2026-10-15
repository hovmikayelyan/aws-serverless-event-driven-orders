"""SQS-triggered consumer, shared by billing / inventory / notifications (CONSUMER_NAME env var).

- partial batch response: only failed messages are retried (ReportBatchItemFailures)
- idempotent: duplicate deliveries are acknowledged without side effects
- after maxReceiveCount failures SQS moves the message to the consumer's DLQ
- `simulateFailure == "<consumer>"` poisons the message to exercise retry -> DLQ
"""
import json
import os

from common import idempotency
from common.events import upcast
from common.obs import cold_start, emit_metric, log

CONSUMER = os.environ["CONSUMER_NAME"]


def process(order: dict) -> None:
    """Stand-in for the real downstream call (DB write, email, ...)."""
    if order.get("simulateFailure") == CONSUMER:
        raise RuntimeError(f"{CONSUMER}: simulated downstream failure")
    log("INFO", "processed", consumer=CONSUMER, orderId=order["orderId"], amount=order["amount"])


def handler(event, context):
    if cold_start():
        emit_metric("ColdStart", 1, Consumer=CONSUMER)
    failures = []
    for record in event["Records"]:
        try:
            envelope = json.loads(record["body"])  # EventBridge -> SQS target: full event envelope
            event_id = envelope["id"]
            order = upcast(envelope["detail"])
            idempotency.claim(CONSUMER, event_id)
            try:
                process(order)
            except Exception:
                idempotency.release(CONSUMER, event_id)
                raise
            emit_metric("Processed", 1, Consumer=CONSUMER)
        except idempotency.AlreadyProcessed:
            emit_metric("DuplicateSkipped", 1, Consumer=CONSUMER)
        except Exception as e:  # noqa: BLE001 - report just this item for retry
            log("ERROR", "failed", consumer=CONSUMER, messageId=record["messageId"], error=str(e))
            emit_metric("Failed", 1, Consumer=CONSUMER)
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
