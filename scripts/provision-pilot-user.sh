#!/usr/bin/env bash
# Provision a Cognito subject from a one-off ECS task inside the private database network.
set -euo pipefail

ENVIRONMENT="${1:?environment required}"
SUBJECT="${2:?Cognito subject required}"
EMAIL="${3:?email required}"
MERCHANT_ID="${4:?merchant id required}"
MERCHANT_NAME="${5:?merchant name required}"
ROLE="${6:-OWNER}"
STACK="PayLens-${ENVIRONMENT}"

output() {
  aws cloudformation describe-stacks --stack-name "$STACK" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

# Reuse the deployed API task so database networking and Secrets Manager values stay private.
CLUSTER=$(output ClusterName)
TASK=$(output ApiTaskDefinitionArn)
SUBNETS=$(output ApplicationSubnetIds)
SG=$(output TaskSecurityGroupId)
OVERRIDES=$(jq -cn \
  --arg subject "$SUBJECT" --arg email "$EMAIL" --arg merchant_id "$MERCHANT_ID" \
  --arg merchant_name "$MERCHANT_NAME" --arg role "$ROLE" \
  '{containerOverrides:[{name:"api",command:["python","-m","app.admin.provision_user","--subject",$subject,"--email",$email,"--merchant-id",$merchant_id,"--merchant-name",$merchant_name,"--role",$role]}]}')

RESULT=$(aws ecs run-task --cluster "$CLUSTER" --task-definition "$TASK" --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$SG],assignPublicIp=ENABLED}" \
  --overrides "$OVERRIDES" --query 'tasks[0].taskArn' --output text)
aws ecs wait tasks-stopped --cluster "$CLUSTER" --tasks "$RESULT"
EXIT=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$RESULT" \
  --query 'tasks[0].containers[0].exitCode' --output text)
test "$EXIT" = "0"
echo "Merchant membership provisioned successfully."
