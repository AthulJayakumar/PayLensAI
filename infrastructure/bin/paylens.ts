#!/usr/bin/env node
/** CDK entry point that composes regional application, image, and cost-control stacks. */
import * as cdk from "aws-cdk-lib";
import { PayLensPilotStack } from "../lib/paylens-pilot-stack";
import { CostControlsStack } from "../lib/cost-controls-stack";
import { ImageRepositoriesStack } from "../lib/image-repositories-stack";

const app = new cdk.App();
// Context selects repeatable dev/pilot names and retention defaults.
const environment = app.node.tryGetContext("environment") ?? "dev";
if (!["dev", "pilot"].includes(environment)) throw new Error("environment must be dev or pilot");
new ImageRepositoriesStack(app, `PayLens-${environment}-Images`, {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? "eu-north-1" }, environment,
});
new PayLensPilotStack(app, `PayLens-${environment}`, {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION ?? "eu-north-1" },
  environment,
  backupRetentionDays: Number(app.node.tryGetContext("backupRetentionDays") ?? (environment === "pilot" ? 7 : 1)),
  budgetLimitUsd: Number(app.node.tryGetContext("budgetLimitUsd") ?? 150),
});
// Budgets are global resources managed through us-east-1, separate from eu-north-1 workloads.
new CostControlsStack(app, `PayLens-${environment}-Costs`, {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: "us-east-1" }, environment,
  budgetLimitUsd: Number(app.node.tryGetContext("budgetLimitUsd") ?? 150),
});
app.synth();
