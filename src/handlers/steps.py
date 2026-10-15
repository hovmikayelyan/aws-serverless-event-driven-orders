"""Step Functions task handlers for the fulfilment saga (dispatch on `action`)."""
from common.obs import emit_metric, log


class TransientError(Exception):
    """Retried by Step Functions with exponential backoff."""


class PaymentDeclined(Exception):
    """Business failure: not retried, triggers compensation."""


def validate(order):
    if order["amount"] <= 0:
        raise ValueError("amount must be positive")
    return order


def reserve_inventory(order):
    if order.get("simulateFailure") == "transient":
        raise TransientError("inventory service timeout")
    return {"reserved": True, "orderId": order["orderId"]}


def charge_payment(order):
    if order.get("simulateFailure") == "payment":
        raise PaymentDeclined("card declined")
    return {"charged": order["amount"], "orderId": order["orderId"]}


def release_inventory(order):
    log("INFO", "compensate: inventory released", orderId=order["orderId"])
    return {"released": True}


def refund_payment(order):
    log("INFO", "compensate: payment refunded", orderId=order["orderId"])
    return {"refunded": True}


def ship(order):
    emit_metric("OrdersShipped", 1)
    return {"shipped": True, "orderId": order["orderId"]}


ACTIONS = {f.__name__: f for f in (validate, reserve_inventory, charge_payment, release_inventory, refund_payment, ship)}


def handler(event, context):
    return ACTIONS[event["action"]](event["order"])
