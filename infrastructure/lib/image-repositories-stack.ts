/** Retained, immutable ECR repositories created before application deployment. */

import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ecr from "aws-cdk-lib/aws-ecr";

export class ImageRepositoriesStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: cdk.StackProps & { environment: string }) {
    super(scope, id, props);
    // Backend and frontend share lifecycle/security policy but remain independently deployable.
    for (const component of ["backend", "frontend"]) {
      const repository = new ecr.Repository(this, `${component}Repository`, {
        repositoryName: `paylens-${props.environment}-${component}`, imageScanOnPush: true,
        imageTagMutability: ecr.TagMutability.IMMUTABLE, removalPolicy: cdk.RemovalPolicy.RETAIN,
        lifecycleRules: [{ maxImageCount: 20, description: "Retain recent pilot images" }],
      });
      new cdk.CfnOutput(this, `${component}RepositoryUri`, { value: repository.repositoryUri });
    }
  }
}
