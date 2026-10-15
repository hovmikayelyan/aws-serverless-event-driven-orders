"""Event versioning strategy: every event carries `schemaVersion`. Consumers upcast old versions
to the latest shape, so producers and consumers can be deployed independently."""


def upcast(detail: dict) -> dict:
    v = int(detail.get("schemaVersion", 1))
    if v == 1:  # v1: {"orderId","amount"}  ->  v2 adds currency + priority
        detail = {**detail, "currency": "USD", "priority": "normal", "schemaVersion": 2}
    if int(detail["schemaVersion"]) != 2:
        raise ValueError(f"unsupported schemaVersion {detail['schemaVersion']}")
    return detail
