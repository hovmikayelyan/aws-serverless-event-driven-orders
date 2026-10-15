#!/usr/bin/env bash
# Exercise every path. Usage: scripts/demo.sh <api-url>
set -euo pipefail
url=${1:?api url}
post() { curl -s -X POST "$url" -H 'content-type: application/json' -d "$1"; echo; }
echo "1. small order (billing+inventory only, no saga)";   post '{"amount": 20}'
echo "2. big high-priority order (fan-out to 3 + saga)";   post '{"amount": 500, "priority": "high"}'
echo "3. transient failure => Step Functions retries w/ backoff"; post '{"amount": 300, "simulateFailure": "transient"}'
echo "4. payment declined => saga compensation";           post '{"amount": 300, "simulateFailure": "payment"}'
echo "5. billing poison message => 3 retries then billing DLQ"; post '{"amount": 30, "simulateFailure": "billing"}'
