import os
import sys

os.environ.update(
    AWS_DEFAULT_REGION="eu-west-1", AWS_ACCESS_KEY_ID="x", AWS_SECRET_ACCESS_KEY="x",
    EVENT_BUS="bus", IDEMPOTENCY_TABLE="idem", CONSUMER_NAME="billing",
)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
