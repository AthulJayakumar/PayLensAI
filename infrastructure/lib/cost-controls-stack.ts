/** Monthly forecast and actual-spend notifications for the pilot account. */

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as budgets from "aws-cdk-lib/aws-budgets";

export class CostControlsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { environment: string; budgetLimitUsd: number }) {
    super(scope, id, props);
    // CloudFormation asks for the operator address at deployment time, avoiding source-code PII.
    const email = new cdk.CfnParameter(this, "BudgetAlertEmail", { type: "String", description: "Verified operator email for monthly cost alerts" });
    new budgets.CfnBudget(this, "Budget", { budget: { budgetName: `paylens-${props.environment}-monthly`, budgetType: "COST", timeUnit: "MONTHLY", budgetLimit: { amount: props.budgetLimitUsd, unit: "USD" } }, notificationsWithSubscribers: [
      { notification: { comparisonOperator: "GREATER_THAN", notificationType: "FORECASTED", threshold: 80, thresholdType: "PERCENTAGE" }, subscribers: [{ address: email.valueAsString, subscriptionType: "EMAIL" }] },
      { notification: { comparisonOperator: "GREATER_THAN", notificationType: "ACTUAL", threshold: 100, thresholdType: "PERCENTAGE" }, subscribers: [{ address: email.valueAsString, subscriptionType: "EMAIL" }] },
    ] });
  }
}
