"""Lightweight observability: structured logs + CloudWatch EMF metrics + X-Ray (lazy)."""
import json
import os
import time

NAMESPACE = os.environ.get("METRICS_NAMESPACE", "OrdersPlatform")
_COLD = True


def cold_start() -> bool:
    """True only on the first invocation of an execution environment."""
    global _COLD
    was, _COLD = _COLD, False
    return was


def emit_metric(name: str, value: float = 1, unit: str = "Count", **dims: str) -> None:
    """Embedded Metric Format: becomes a CloudWatch metric with no API call / no added latency."""
    print(json.dumps({
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": NAMESPACE,
                "Dimensions": [["Function", *dims.keys()]],
                "Metrics": [{"Name": name, "Unit": unit}],
            }],
        },
        "Function": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "local"),
        name: value,
        **dims,
    }))


def log(level: str, msg: str, **fields) -> None:
    print(json.dumps({"level": level, "msg": msg, **fields}))
