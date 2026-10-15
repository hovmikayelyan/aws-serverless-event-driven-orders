"""API Gateway -> validate -> publish OrderPlaced to EventBridge.

Cold-start notes: only boto3 (already in the runtime) is imported at module level, the client is built
once during init, and nothing heavy is imported. arm64 + small package + provisioned concurrency on the alias.
"""
import json
import os
import uuid

import boto3

from common.obs import cold_start, emit_metric, log

events = boto3.client("events")  # init phase, reused on warm invokes
BUS = os.environ["EVENT_BUS"]


def handler(event, context):
    if cold_start():
        emit_metric("ColdStart", 1)
    try:
        body = json.loads(event.get("body") or "{}")
        detail = {
            "schemaVersion": 2,
            "orderId": body.get("orderId") or str(uuid.uuid4()),
            "amount": float(body["amount"]),
            "currency": body.get("currency", "USD"),
            "priority": body.get("priority", "normal"),
            "simulateFailure": body.get("simulateFailure"),
        }
    except (KeyError, ValueError, TypeError):
        return {"statusCode": 400, "body": json.dumps({"error": "amount (number) is required"})}

    resp = events.put_events(Entries=[{
        "EventBusName": BUS,
        "Source": "orders.api",
        "DetailType": "OrderPlaced",
        "Detail": json.dumps(detail),
    }])
    if resp["FailedEntryCount"]:
        log("ERROR", "put_events failed", resp=resp["Entries"])
        return {"statusCode": 502, "body": json.dumps({"error": "could not publish"})}
    emit_metric("OrdersAccepted", 1)
    return {"statusCode": 202, "body": json.dumps({"orderId": detail["orderId"], "eventId": resp["Entries"][0]["EventId"]})}
