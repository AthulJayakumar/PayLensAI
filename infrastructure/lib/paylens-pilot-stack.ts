/** Complete low-cost pilot runtime: network, data, identity, compute, edge, and monitoring. */

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as cloudfront from "aws-cdk-lib/aws-cloudfront";
import * as appscaling from "aws-cdk-lib/aws-applicationautoscaling";
import * as origins from "aws-cdk-lib/aws-cloudfront-origins";
import * as cloudwatch from "aws-cdk-lib/aws-cloudwatch";
import * as cloudwatchActions from "aws-cdk-lib/aws-cloudwatch-actions";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as ecr from "aws-cdk-lib/aws-ecr";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as kms from "aws-cdk-lib/aws-kms";
import * as logs from "aws-cdk-lib/aws-logs";
import * as rds from "aws-cdk-lib/aws-rds";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as sns from "aws-cdk-lib/aws-sns";
import * as subscriptions from "aws-cdk-lib/aws-sns-subscriptions";
import * as sqs from "aws-cdk-lib/aws-sqs";

interface Props extends cdk.StackProps { environment: "dev" | "pilot"; backupRetentionDays: number; budgetLimitUsd: number; }

export class PayLensPilotStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: Props) {
    super(scope, id, props);
    const prefix = `paylens-${props.environment}`;
    const stripeConnectionMode = this.node.tryGetContext("stripeConnectionMode") ?? "SANDBOX_KEY";
    if (!["SANDBOX_KEY", "OAUTH"].includes(stripeConnectionMode)) {
      throw new Error("stripeConnectionMode must be SANDBOX_KEY or OAUTH");
    }
    const budgetEmail = new cdk.CfnParameter(this, "BudgetAlertEmail", { type: "String", description: "Verified operator email for cost and operational alerts" });
    const originVerify = new cdk.CfnParameter(this, "OriginVerifyHeader", { type: "String", noEcho: true, minLength: 32, description: "Random value CloudFront sends to the ALB" });

    // Public application subnets avoid NAT cost; the database remains isolated and private.
    const vpc = new ec2.Vpc(this, "Vpc", { availabilityZones: ["eu-north-1a", "eu-north-1b"], natGateways: 0,
      subnetConfiguration: [
        { name: "application", subnetType: ec2.SubnetType.PUBLIC, cidrMask: 24 },
        { name: "database", subnetType: ec2.SubnetType.PRIVATE_ISOLATED, cidrMask: 24 },
      ],
    });
    // A retained rotating key protects raw imports and application/provider secrets.
    const dataKey = new kms.Key(this, "DataKey", { enableKeyRotation: true, alias: `alias/${prefix}-data`, removalPolicy: cdk.RemovalPolicy.RETAIN });
    const rawBucket = new s3.Bucket(this, "RawBucket", { bucketName: undefined, encryption: s3.BucketEncryption.KMS,
      encryptionKey: dataKey, blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL, enforceSSL: true,
      versioned: true, removalPolicy: cdk.RemovalPolicy.RETAIN, autoDeleteObjects: false,
      lifecycleRules: [{ id: "expire-analysis-input", prefix: "analysis-input/", expiration: cdk.Duration.days(7),
        noncurrentVersionExpiration: cdk.Duration.days(30) }, { id: "raw-to-infrequent-access", prefix: "merchant/",
        transitions: [{ storageClass: s3.StorageClass.INFREQUENT_ACCESS, transitionAfter: cdk.Duration.days(30) }] }],
    });

    // Each workload has independent retries and a DLQ so one failure class cannot block another.
    const makeQueue = (name: string, timeoutSeconds: number) => {
      const dlq = new sqs.Queue(this, `${name}Dlq`, { queueName: `${prefix}-${name}-dlq`, encryption: sqs.QueueEncryption.KMS_MANAGED,
        retentionPeriod: cdk.Duration.days(14) });
      const queue = new sqs.Queue(this, `${name}Queue`, { queueName: `${prefix}-${name}`, encryption: sqs.QueueEncryption.KMS_MANAGED,
        visibilityTimeout: cdk.Duration.seconds(timeoutSeconds), receiveMessageWaitTime: cdk.Duration.seconds(20),
        deadLetterQueue: { queue: dlq, maxReceiveCount: 4 } });
      return { queue, dlq };
    };
    const providerSync = makeQueue("provider-sync", 900);
    const analysis = makeQueue("analysis", 900);
    const webhook = makeQueue("webhook", 300);

    // Security groups restrict PostgreSQL ingress to ECS application tasks.
    const dbSg = new ec2.SecurityGroup(this, "DatabaseSg", { vpc, allowAllOutbound: false, description: "RDS accepts PostgreSQL only from PayLens tasks" });
    const taskSg = new ec2.SecurityGroup(this, "TaskSg", { vpc, allowAllOutbound: true, description: "No public ingress; outbound via public IP avoids NAT" });
    dbSg.addIngressRule(taskSg, ec2.Port.tcp(5432), "PayLens tasks only");
    const database = new rds.DatabaseInstance(this, "Database", {
      engine: rds.DatabaseInstanceEngine.postgres({ version: rds.PostgresEngineVersion.VER_17 }),
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.BURSTABLE4_GRAVITON, ec2.InstanceSize.MICRO),
      vpc, vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_ISOLATED }, securityGroups: [dbSg],
      credentials: rds.Credentials.fromGeneratedSecret("paylens_app", { secretName: `${prefix}/database` }), databaseName: "paylens", port: 5432,
      allocatedStorage: 20, maxAllocatedStorage: 50, storageType: rds.StorageType.GP3, storageEncrypted: true,
      multiAz: false, publiclyAccessible: false, backupRetention: cdk.Duration.days(props.backupRetentionDays),
      deletionProtection: props.environment === "pilot", deleteAutomatedBackups: false,
      removalPolicy: props.environment === "pilot" ? cdk.RemovalPolicy.SNAPSHOT : cdk.RemovalPolicy.SNAPSHOT,
      cloudwatchLogsExports: ["postgresql"], autoMinorVersionUpgrade: true,
    });
    const appSecret = new secretsmanager.Secret(this, "ApplicationSecret", { secretName: `${prefix}/application`,
      encryptionKey: dataKey, generateSecretString: { secretStringTemplate: JSON.stringify({}), generateStringKey: "master",
        passwordLength: 64, excludePunctuation: true } });
    const stripeSecret = new secretsmanager.Secret(this, "StripeSecret", { secretName: `${prefix}/stripe`, encryptionKey: dataKey,
      secretObjectValue: { appClientId: cdk.SecretValue.unsafePlainText("NOT_CONFIGURED"), developerApiKey: cdk.SecretValue.unsafePlainText("NOT_CONFIGURED"), webhookSecret: cdk.SecretValue.unsafePlainText("NOT_CONFIGURED") } });

    // Pilot accounts are administrator-provisioned; optional TOTP strengthens authenticated access.
    const userPool = new cognito.UserPool(this, "UserPool", { userPoolName: `${prefix}-users`, selfSignUpEnabled: false,
      signInAliases: { email: true }, standardAttributes: { email: { required: true, mutable: true } },
      passwordPolicy: { minLength: 12, requireDigits: true, requireLowercase: true, requireUppercase: true, requireSymbols: true },
      mfa: cognito.Mfa.OPTIONAL, mfaSecondFactor: { sms: false, otp: true }, accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });
    const userPoolClient = userPool.addClient("WebClient", { userPoolClientName: `${prefix}-web`, generateSecret: false,
      authFlows: { userSrp: true, userPassword: true }, preventUserExistenceErrors: true, accessTokenValidity: cdk.Duration.hours(1),
    });

    // API, worker, and web processes scale/deploy independently on one Fargate cluster.
    const cluster = new ecs.Cluster(this, "Cluster", { vpc, clusterName: prefix, containerInsightsV2: ecs.ContainerInsights.ENABLED });
    const apiLog = new logs.LogGroup(this, "ApiLog", { logGroupName: `/paylens/${props.environment}/api`, retention: logs.RetentionDays.ONE_MONTH });
    const workerLog = new logs.LogGroup(this, "WorkerLog", { logGroupName: `/paylens/${props.environment}/worker`, retention: logs.RetentionDays.ONE_MONTH });
    const frontendLog = new logs.LogGroup(this, "FrontendLog", { logGroupName: `/paylens/${props.environment}/frontend`, retention: logs.RetentionDays.ONE_WEEK });
    const apiTask = new ecs.FargateTaskDefinition(this, "ApiTask", { cpu: 512, memoryLimitMiB: 1024 });
    const workerTask = new ecs.FargateTaskDefinition(this, "WorkerTask", { cpu: 1024, memoryLimitMiB: 2048 });
    const frontendTask = new ecs.FargateTaskDefinition(this, "FrontendTask", { cpu: 256, memoryLimitMiB: 512 });
    const backendRepository = ecr.Repository.fromRepositoryName(this, "BackendRepository", `${prefix}-backend`);
    const frontendRepository = ecr.Repository.fromRepositoryName(this, "FrontendRepository", `${prefix}-frontend`);
    const imageTag = this.node.tryGetContext("imageTag") ?? "bootstrap";
    const backendImage = ecs.ContainerImage.fromEcrRepository(backendRepository, imageTag);
    const frontendImage = ecs.ContainerImage.fromEcrRepository(frontendRepository, imageTag);
    const commonEnvironment = {
      PAYLENS_ENV: props.environment, PAYLENS_API_PREFIX: "/api", AWS_REGION: this.region,
      DB_NAME: "paylens", DB_PORT: database.dbInstanceEndpointPort,
      PAYLENS_RAW_BUCKET: rawBucket.bucketName, PAYLENS_RAW_KMS_KEY_ID: dataKey.keyArn,
      PAYLENS_PROVIDER_SYNC_QUEUE_URL: providerSync.queue.queueUrl, PAYLENS_ANALYSIS_QUEUE_URL: analysis.queue.queueUrl,
      PAYLENS_WEBHOOK_QUEUE_URL: webhook.queue.queueUrl, COGNITO_USER_POOL_ID: userPool.userPoolId,
      COGNITO_CLIENT_ID: userPoolClient.userPoolClientId, STRIPE_CONNECTION_MODE: stripeConnectionMode,
    };
    const commonSecrets = {
      DB_HOST: ecs.Secret.fromSecretsManager(database.secret!, "host"), DB_USERNAME: ecs.Secret.fromSecretsManager(database.secret!, "username"),
      DB_PASSWORD: ecs.Secret.fromSecretsManager(database.secret!, "password"),
      PAYLENS_CREDENTIAL_ENCRYPTION_KEY: ecs.Secret.fromSecretsManager(appSecret, "master"),
      PAYLENS_OAUTH_STATE_SECRET: ecs.Secret.fromSecretsManager(appSecret, "master"),
      STRIPE_APP_CLIENT_ID: ecs.Secret.fromSecretsManager(stripeSecret, "appClientId"),
      STRIPE_APP_DEVELOPER_API_KEY: ecs.Secret.fromSecretsManager(stripeSecret, "developerApiKey"),
      STRIPE_SANDBOX_API_KEY: ecs.Secret.fromSecretsManager(stripeSecret, "sandboxApiKey"),
      STRIPE_SANDBOX_ACCOUNT_ID: ecs.Secret.fromSecretsManager(stripeSecret, "sandboxAccountId"),
      STRIPE_WEBHOOK_SECRET: ecs.Secret.fromSecretsManager(stripeSecret, "webhookSecret"),
    };
    const apiContainer = apiTask.addContainer("api", { image: backendImage, environment: commonEnvironment, secrets: commonSecrets,
      logging: ecs.LogDrivers.awsLogs({ logGroup: apiLog, streamPrefix: "api" }), healthCheck: { command: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/health')\" || exit 1"], interval: cdk.Duration.seconds(30), timeout: cdk.Duration.seconds(5), retries: 3, startPeriod: cdk.Duration.seconds(30) } });
    apiContainer.addPortMappings({ containerPort: 8000 });
    const workerContainer = workerTask.addContainer("worker", { image: backendImage, command: ["python", "-m", "app.worker"],
      environment: commonEnvironment, secrets: commonSecrets, logging: ecs.LogDrivers.awsLogs({ logGroup: workerLog, streamPrefix: "worker" }) });
    const frontendContainer = frontendTask.addContainer("frontend", { image: frontendImage, logging: ecs.LogDrivers.awsLogs({ logGroup: frontendLog, streamPrefix: "frontend" }) });
    frontendContainer.addPortMappings({ containerPort: 3000 });
    // Least-privilege grants attach data access only to backend roles that need it.
    for (const task of [apiTask, workerTask]) {
      rawBucket.grantReadWrite(task.taskRole); dataKey.grantEncryptDecrypt(task.taskRole); database.secret!.grantRead(task.executionRole!);
      appSecret.grantRead(task.executionRole!); stripeSecret.grantRead(task.executionRole!);
    }
    for (const q of [providerSync.queue, analysis.queue, webhook.queue]) {
      q.grantConsumeMessages(workerTask.taskRole);
      q.grantSendMessages(apiTask.taskRole);
    }

    const apiService = new ecs.FargateService(this, "ApiService", { cluster, taskDefinition: apiTask, desiredCount: 1,
      assignPublicIp: true, vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }, securityGroups: [taskSg],
      circuitBreaker: { rollback: true }, minHealthyPercent: 0, maxHealthyPercent: 200 });
    const workerService = new ecs.FargateService(this, "WorkerService", { cluster, taskDefinition: workerTask, desiredCount: 1,
      assignPublicIp: true, vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }, securityGroups: [taskSg], circuitBreaker: { rollback: true }, minHealthyPercent: 100, maxHealthyPercent: 200 });
    const frontendService = new ecs.FargateService(this, "FrontendService", { cluster, taskDefinition: frontendTask, desiredCount: 1,
      assignPublicIp: true, vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }, securityGroups: [taskSg], circuitBreaker: { rollback: true }, minHealthyPercent: 100, maxHealthyPercent: 200 });

    // CloudFront supplies a secret origin header; direct ALB requests receive the default 403.
    const albSg = new ec2.SecurityGroup(this, "AlbSg", { vpc, allowAllOutbound: false });
    albSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), "CloudFront origin HTTP");
    taskSg.addIngressRule(albSg, ec2.Port.tcp(8000), "ALB to API"); taskSg.addIngressRule(albSg, ec2.Port.tcp(3000), "ALB to frontend");
    const alb = new elbv2.ApplicationLoadBalancer(this, "Alb", { vpc, internetFacing: true, securityGroup: albSg,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC }, dropInvalidHeaderFields: true });
    const listener = alb.addListener("Http", { port: 80, defaultAction: elbv2.ListenerAction.fixedResponse(403) });
    listener.addTargets("Api", { priority: 10, port: 8000, protocol: elbv2.ApplicationProtocol.HTTP, targets: [apiService],
      healthCheck: { path: "/health" }, conditions: [elbv2.ListenerCondition.httpHeader("X-PayLens-Origin", [originVerify.valueAsString]), elbv2.ListenerCondition.pathPatterns(["/api/*", "/health"])] });
    listener.addTargets("Frontend", { priority: 20, port: 3000, protocol: elbv2.ApplicationProtocol.HTTP, targets: [frontendService],
      healthCheck: { path: "/" }, conditions: [elbv2.ListenerCondition.httpHeader("X-PayLens-Origin", [originVerify.valueAsString]), elbv2.ListenerCondition.pathPatterns(["/*"])] });
    const origin = new origins.HttpOrigin(alb.loadBalancerDnsName, { protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
      customHeaders: { "X-PayLens-Origin": originVerify.valueAsString } });
    // API requests are never cached. CloudFront forbids Authorization in a custom
    // origin allow-list, so use its managed all-viewer policy while replacing Host.
    const distribution = new cloudfront.Distribution(this, "Distribution", { defaultBehavior: { origin, viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED, allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL }, additionalBehaviors: {
      "/api/*": { origin, viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED, originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER, allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL },
      "/health": { origin, viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED },
      "/assets/*": { origin, viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS, cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED },
    }, httpVersion: cloudfront.HttpVersion.HTTP2_AND_3 });
    const publicUrl = `https://${distribution.distributionDomainName}`;
    apiContainer.addEnvironment("PAYLENS_FRONTEND_URL", publicUrl);
    apiContainer.addEnvironment("PAYLENS_CORS_ORIGINS", publicUrl);
    apiContainer.addEnvironment("STRIPE_OAUTH_REDIRECT_URI", `${publicUrl}/api/providers/stripe/oauth/callback`);
    workerContainer.addEnvironment("PAYLENS_FRONTEND_URL", publicUrl);
    workerContainer.addEnvironment("PAYLENS_CORS_ORIGINS", publicUrl);
    workerContainer.addEnvironment("STRIPE_OAUTH_REDIRECT_URI", `${publicUrl}/api/providers/stripe/oauth/callback`);

    // Queue depth adds worker capacity without prematurely scaling the request-facing API.
    const workerScaling = workerService.autoScaleTaskCount({ minCapacity: 1, maxCapacity: 3 });
    workerScaling.scaleOnMetric("QueueBacklogScaling", { metric: new cloudwatch.MathExpression({ expression: "MAX([p,a,w])", usingMetrics: {
      p: providerSync.queue.metricApproximateNumberOfMessagesVisible(), a: analysis.queue.metricApproximateNumberOfMessagesVisible(), w: webhook.queue.metricApproximateNumberOfMessagesVisible(),
    }, period: cdk.Duration.minutes(1) }), scalingSteps: [{ upper: 0, change: -1 }, { lower: 1, change: +1 }, { lower: 10, change: +2 }], adjustmentType: appscaling.AdjustmentType.CHANGE_IN_CAPACITY });

    // Operational alarms cover user-facing failures, poison messages, worker failures, and DB pressure.
    const alarms = new sns.Topic(this, "AlarmTopic", { displayName: `${prefix} operational alarms` });
    alarms.addSubscription(new subscriptions.EmailSubscription(budgetEmail.valueAsString));
    const alarmActions = [new cloudwatchActions.SnsAction(alarms)];
    for (const [name, metric] of [["Api5xx", alb.metrics.httpCodeTarget(elbv2.HttpCodeTarget.TARGET_5XX_COUNT)], ["ProviderDlq", providerSync.dlq.metricApproximateNumberOfMessagesVisible()], ["AnalysisDlq", analysis.dlq.metricApproximateNumberOfMessagesVisible()], ["WebhookDlq", webhook.dlq.metricApproximateNumberOfMessagesVisible()] ] as const) {
      const alarm = new cloudwatch.Alarm(this, `${name}Alarm`, { metric, threshold: 1, evaluationPeriods: 1, treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING });
      alarm.addAlarmAction(...alarmActions);
    }
    const staleWebhookAlarm = new cloudwatch.Alarm(this, "StaleWebhookAlarm", {
      metric: webhook.queue.metricApproximateAgeOfOldestMessage({ period: cdk.Duration.minutes(1) }),
      threshold: 300,
      evaluationPeriods: 2,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    staleWebhookAlarm.addAlarmAction(...alarmActions);
    const jobFailureMetric = new logs.MetricFilter(this, "WorkerFailureMetric", { logGroup: workerLog,
      metricNamespace: "PayLens", metricName: "WorkerJobFailures", filterPattern: logs.FilterPattern.stringValue("$.event", "=", "job_failed"), metricValue: "1" });
    const workerFailureAlarm = new cloudwatch.Alarm(this, "WorkerFailureAlarm", { metric: jobFailureMetric.metric({ period: cdk.Duration.minutes(5), statistic: "sum" }), threshold: 1, evaluationPeriods: 1, treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING });
    workerFailureAlarm.addAlarmAction(...alarmActions);
    const dbConnectionsAlarm = new cloudwatch.Alarm(this, "DatabaseConnectionsAlarm", { metric: database.metricDatabaseConnections(), threshold: 70, evaluationPeriods: 2, treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING });
    dbConnectionsAlarm.addAlarmAction(...alarmActions);
    new cloudwatch.Dashboard(this, "Dashboard", { dashboardName: prefix, widgets: [[new cloudwatch.GraphWidget({ title: "API target latency / 5xx", left: [alb.metrics.targetResponseTime()], right: [alb.metrics.httpCodeTarget(elbv2.HttpCodeTarget.TARGET_5XX_COUNT)] })], [new cloudwatch.GraphWidget({ title: "Queue backlog / webhook age", left: [providerSync.queue.metricApproximateNumberOfMessagesVisible(), analysis.queue.metricApproximateNumberOfMessagesVisible(), webhook.queue.metricApproximateNumberOfMessagesVisible()], right: [webhook.queue.metricApproximateAgeOfOldestMessage()] })]] });
    // Deployment scripts consume these outputs instead of duplicating generated identifiers.
    new cdk.CfnOutput(this, "ApplicationUrl", { value: `https://${distribution.distributionDomainName}` });
    new cdk.CfnOutput(this, "UserPoolId", { value: userPool.userPoolId });
    new cdk.CfnOutput(this, "UserPoolClientId", { value: userPoolClient.userPoolClientId });
    new cdk.CfnOutput(this, "RawBucketName", { value: rawBucket.bucketName });
    new cdk.CfnOutput(this, "StripeSecretArn", { value: stripeSecret.secretArn });
    new cdk.CfnOutput(this, "BackendRepositoryUri", { value: backendRepository.repositoryUri });
    new cdk.CfnOutput(this, "FrontendRepositoryUri", { value: frontendRepository.repositoryUri });
    new cdk.CfnOutput(this, "ClusterName", { value: cluster.clusterName });
    new cdk.CfnOutput(this, "ApiServiceName", { value: apiService.serviceName });
    new cdk.CfnOutput(this, "WorkerServiceName", { value: workerService.serviceName });
    new cdk.CfnOutput(this, "FrontendServiceName", { value: frontendService.serviceName });
    new cdk.CfnOutput(this, "ApiTaskDefinitionArn", { value: apiTask.taskDefinitionArn });
    new cdk.CfnOutput(this, "ApplicationSubnetIds", { value: vpc.publicSubnets.map(subnet => subnet.subnetId).join(",") });
    new cdk.CfnOutput(this, "TaskSecurityGroupId", { value: taskSg.securityGroupId });
    new cdk.CfnOutput(this, "DatabaseInstanceIdentifier", { value: database.instanceIdentifier });
    new cdk.CfnOutput(this, "WebhookDeadLetterQueueUrl", { value: webhook.dlq.queueUrl });
  }
}
