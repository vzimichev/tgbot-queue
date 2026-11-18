# Terraform equivalent of deploy/aws

The same infrastructure, numbered 1–9 to match the CloudFormation files:

1. Admin SQS queue, DLQ and alarm.
2. Admin webhook Lambda, IAM and logs.
3. Admin HTTP API Gateway, route, invoke permission, logs and alarm.
4. Register the admin webhook with Telegram (manual script).
5. Managed SQS queue, DLQ and alarm.
6. Managed webhook Lambda, IAM and logs.
7. Managed HTTP API Gateway, route, invoke permission, logs and alarm.
8. Shared EC2 host, VPC, public subnet, IAM/SSM, security group and retained data disk.
9. Deploy both workers via SSM (manual script).

## Usage

Requires Terraform >=1.5, AWS credentials, AWS CLI, Python 3, curl, Bash and Git.
Run from this directory:

```sh
cp terraform.tfvars.example terraform.tfvars
# Fill in the existing key pair and secret ARNs; do not put secret values here.
terraform init
terraform fmt -check
terraform validate
terraform plan -out=deployment.tfplan
terraform apply deployment.tfplan
bash 4-register-webhook.sh
bash 9-deploy-ec2-worker.sh
```

All numbered `.tf` files form ONE root configuration and ONE state. Numbers are
for navigation, not sequential apply steps. Terraform orders dependencies itself.
Apply creates the infrastructure for both workers together. Scripts 4 and 9 read
outputs from this directory's selected workspace/state and run only when invoked.
The deployment script still deploys a published GitHub branch, as in deploy/aws.
Use the same AWS account/profile for Terraform and both scripts.

## Existing CloudFormation deployment

Do not apply with the default names against resources already owned by
CloudFormation. This is an alternative implementation, not an automatic migration.
For a separate deployment, choose distinct project and function names; register
its webhook only when ready to switch Telegram traffic. For migration, first
prepare a resource-by-resource import and CloudFormation ownership handoff.
Never have both systems manage the same resource.

## State and retention

State is local by default. Keep state and saved plans private and backed up;
configure an S3 backend with locking before shared/team operation. Secret values
are fetched at runtime by Lambda/EC2, not read into Terraform state.

Queues, Lambda functions and the data volume use `prevent_destroy` to guard
against accidental destroy/replacement. This is NOT identical to CloudFormation
`Retain`: removing a resource block also removes its protection. To stop managing
and retain a resource, deliberately remove it from state rather than destroy it.
Protect and review the state before any ownership changes.

Lambda source is copied unchanged from the inline CloudFormation handlers into
`lambda/admin.py` and `lambda/managed.py`; the archive provider creates index.py
ZIPs locally under `.terraform/`. AWS and archive are the only providers.
The EC2 size remains t3.micro, Lambda memory 128 MB, timeout 25 seconds, API
integration timeout 29 seconds and logging retention 14 days. SQS visibility
is configurable separately for the two queues. API/IAM/alarm names are generated
by Terraform rather than CloudFormation stack names.

Worker application deployment and disk-format confirmation remain in step 9;
Terraform only provisions and attaches the disk. EC2 has no inbound rules and
uses SSM. The EC2 instance role can access both queues, as in the original stack;
containers share that host role.
