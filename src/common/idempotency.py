"""Idempotency via DynamoDB conditional write. Gives effectively-once processing on top of
at-least-once delivery (SQS/EventBridge). Key = <consumer>#<event id>."""
import os
import time

import boto3
from botocore.exceptions import ClientError

# Created at init time -> reused across warm invocations, paid once during cold start.
_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb").Table(os.environ["IDEMPOTENCY_TABLE"])
    return _table


class AlreadyProcessed(Exception):
    pass


def claim(consumer: str, event_id: str, ttl_seconds: int = 24 * 3600) -> None:
    """Raise AlreadyProcessed if this consumer already handled this event."""
    try:
        table().put_item(
            Item={"pk": f"{consumer}#{event_id}", "expires_at": int(time.time()) + ttl_seconds},
            ConditionExpression="attribute_not_exists(pk)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise AlreadyProcessed(event_id) from e
        raise


def release(consumer: str, event_id: str) -> None:
    """Un-claim after a failed attempt so the retry can run."""
    table().delete_item(Key={"pk": f"{consumer}#{event_id}"})
