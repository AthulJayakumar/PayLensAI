# PayLens AWS infrastructure

This directory describes the pilot's AWS resources as TypeScript code using
the AWS Cloud Development Kit (CDK). Reviewing the code shows what AWS will
create before a deployment is approved.

- `image-repositories-stack.ts` creates retained container repositories first.
- `paylens-pilot-stack.ts` creates networking, identity, storage, queues,
  services, the public edge, monitoring, alarms, and safe stack outputs.
- `cost-controls-stack.ts` creates spending forecasts and notifications.
- `bin/paylens.ts` selects `dev` or `pilot` names and composes the stacks.

The pilot uses public ECS task networking to reduce NAT Gateway cost. Security
groups still restrict database and service traffic, and CloudFront supplies an
origin-verification header so the public load balancer does not become an
uncontrolled alternate entrance.

Deployment is manual and protected. See [../docs/sprint-5-aws-pilot.md](../docs/sprint-5-aws-pilot.md)
and [../docs/sprint-6-operational-readiness.md](../docs/sprint-6-operational-readiness.md).
