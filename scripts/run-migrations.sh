#!/usr/bin/env bash
# Run Alembic as a one-off ECS task using the deployed API task definition and network.
set -euo pipefail
ENVIRONMENT="${1:?environment required}"
STACK="PayLens-${ENVIRONMENT}"
output() { aws cloudformation describe-stacks --stack-name "$STACK" --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
# Resolve generated resource identifiers from stack outputs to keep this script environment-neutral.
CLUSTER=$(output ClusterName)
TASK=$(output ApiTaskDefinitionArn)
SUBNETS=$(output ApplicationSubnetIds)
SG=$(output TaskSecurityGroupId)
RESULT=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$TASK" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"api","command":["alembic","-c","/app/alembic.ini","upgrade","head"]}]}' --query 'tasks[0].taskArn' --output text)
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$RESULT"
# A stopped task is not necessarily successful, so assert its container exit code.
EXIT=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$RESULT" --query 'tasks[0].containers[0].exitCode' --output text)
test "$EXIT" = "0"
