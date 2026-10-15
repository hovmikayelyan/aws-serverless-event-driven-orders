#!/usr/bin/env bash
# Print cold-start (Init Duration) vs warm stats for the ingest function from CloudWatch Logs Insights.
# Usage: scripts/coldstart-report.sh <stack-name>
set -euo pipefail
stack=${1:?stack name}
lg="/aws/lambda/$(aws cloudformation describe-stack-resource --stack-name "$stack" --logical-resource-id IngestFunction \
  --query StackResourceDetail.PhysicalResourceId --output text)"
qid=$(aws logs start-query --log-group-name "$lg" --start-time $(( $(date +%s) - 86400 )) --end-time $(date +%s) \
  --query-string 'filter @type="REPORT" | stats count() as invocations, count(@initDuration) as coldStarts, avg(@initDuration) as avgInitMs, max(@initDuration) as maxInitMs, avg(@duration) as avgMs, pct(@duration,99) as p99Ms' \
  --query queryId --output text)
sleep 5; aws logs get-query-results --query-id "$qid" --output table
