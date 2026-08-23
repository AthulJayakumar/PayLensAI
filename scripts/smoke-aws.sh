#!/usr/bin/env bash
# Redeploy running tasks, wait for stability, then probe API and browser entry points.
set -euo pipefail
ENVIRONMENT="${1:?environment required}"
STACK="PayLens-${ENVIRONMENT}"
output() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
CLUSTER=$(output ClusterName)
# Force all services to pick up the newly registered image-tagged task definitions.
for key in ApiServiceName WorkerServiceName FrontendServiceName; do aws ecs update-service --cluster "$CLUSTER" --service "$(output "$key")" --force-new-deployment >/dev/null; done
for key in ApiServiceName WorkerServiceName FrontendServiceName; do aws ecs wait services-stable --cluster "$CLUSTER" --services "$(output "$key")"; done
URL=$(output ApplicationUrl)
# Retries allow CloudFront and ECS health transitions to converge after deployment.
curl --fail --retry 12 --retry-delay 10 "$URL/health"
curl --fail --retry 5 "$URL/login" >/dev/null
