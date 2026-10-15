import json

import pytest
from botocore.exceptions import ClientError

from common import idempotency
from common.events import upcast
from handlers import consumer, ingest, steps


class FakeTable:
    def __init__(self):
        self.items = set()

    def put_item(self, Item, ConditionExpression):
        if Item["pk"] in self.items:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items.add(Item["pk"])

    def delete_item(self, Key):
        self.items.discard(Key["pk"])


@pytest.fixture
def table(monkeypatch):
    t = FakeTable()
    monkeypatch.setattr(idempotency, "_table", t)
    return t


def sqs_record(msg_id, event_id, **detail):
    d = {"schemaVersion": 2, "orderId": "o1", "amount": 50, **detail}
    return {"messageId": msg_id, "body": json.dumps({"id": event_id, "detail": d})}


def test_consumer_processes_and_dedupes(table):
    ev = {"Records": [sqs_record("m1", "e1")]}
    assert consumer.handler(ev, None) == {"batchItemFailures": []}
    assert "billing#e1" in table.items
    # redelivery of the same event is a no-op, not a failure
    assert consumer.handler(ev, None) == {"batchItemFailures": []}


def test_consumer_reports_only_failed_items_and_allows_retry(table):
    ev = {"Records": [sqs_record("ok", "e1"), sqs_record("bad", "e2", simulateFailure="billing")]}
    assert consumer.handler(ev, None) == {"batchItemFailures": [{"itemIdentifier": "bad"}]}
    assert "billing#e2" not in table.items  # claim released so the retry can run
    assert "billing#e1" in table.items


def test_malformed_message_is_reported_for_dlq(table):
    out = consumer.handler({"Records": [{"messageId": "x", "body": "not json"}]}, None)
    assert out["batchItemFailures"] == [{"itemIdentifier": "x"}]


def test_upcast_v1_to_v2():
    out = upcast({"schemaVersion": 1, "orderId": "a", "amount": 1})
    assert out["schemaVersion"] == 2 and out["currency"] == "USD"
    with pytest.raises(ValueError):
        upcast({"schemaVersion": 9})


def test_ingest_validates_and_publishes(monkeypatch):
    sent = {}

    class Events:
        def put_events(self, Entries):
            sent["entry"] = Entries[0]
            return {"FailedEntryCount": 0, "Entries": [{"EventId": "ev-1"}]}

    monkeypatch.setattr(ingest, "events", Events())
    assert ingest.handler({"body": "{}"}, None)["statusCode"] == 400
    r = ingest.handler({"body": json.dumps({"amount": 120, "orderId": "o9"})}, None)
    assert r["statusCode"] == 202
    assert json.loads(sent["entry"]["Detail"])["orderId"] == "o9"
    assert sent["entry"]["DetailType"] == "OrderPlaced"


def test_saga_steps():
    order = {"orderId": "o", "amount": 10}
    assert steps.handler({"action": "reserve_inventory", "order": order}, None)["reserved"]
    with pytest.raises(steps.TransientError):
        steps.handler({"action": "reserve_inventory", "order": {**order, "simulateFailure": "transient"}}, None)
    with pytest.raises(steps.PaymentDeclined):
        steps.handler({"action": "charge_payment", "order": {**order, "simulateFailure": "payment"}}, None)
    assert steps.handler({"action": "refund_payment", "order": order}, None)["refunded"]
