data "aws_availability_zones" "available" { state = "available" }
data "aws_ssm_parameter" "worker_ami" { name = var.image_id_parameter }
locals { worker_tags = { Project = var.project_name } }
resource "aws_vpc" "worker" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags                 = merge(local.worker_tags, { Name = "${var.project_name}-vpc" })
}
resource "aws_internet_gateway" "worker" {
  vpc_id = aws_vpc.worker.id
  tags   = merge(local.worker_tags, { Name = "${var.project_name}-igw" })
}
resource "aws_route_table" "worker" {
  vpc_id = aws_vpc.worker.id
  tags   = merge(local.worker_tags, { Name = "${var.project_name}-public" })
}
resource "aws_route" "worker_internet" {
  route_table_id         = aws_route_table.worker.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.worker.id
}
resource "aws_subnet" "worker" {
  vpc_id                  = aws_vpc.worker.id
  availability_zone       = data.aws_availability_zones.available.names[0]
  cidr_block              = "10.42.0.0/24"
  map_public_ip_on_launch = true
  tags                    = merge(local.worker_tags, { Name = "${var.project_name}-public-a" })
}
resource "aws_route_table_association" "worker" {
  subnet_id      = aws_subnet.worker.id
  route_table_id = aws_route_table.worker.id
}
resource "aws_security_group" "worker" {
  name_prefix = "${var.project_name}-worker-"
  description = "Session Manager administration; no inbound access by default."
  vpc_id      = aws_vpc.worker.id
  ingress     = []
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = merge(local.worker_tags, { Name = "${var.project_name}-ec2-worker" })
}
resource "aws_iam_role" "worker" {
  name_prefix = "${var.project_name}-worker-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy_attachment" "worker_ssm" {
  role       = aws_iam_role.worker.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "worker" {
  name = "worker-access"
  role = aws_iam_role.worker.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
        Resource = [aws_sqs_queue.admin_updates.arn, aws_sqs_queue.managed_updates.arn]
      },
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = [var.admin_bot_secret_arn, var.webhook_secret_arn] }
    ]
  })
}
resource "aws_iam_instance_profile" "worker" { role = aws_iam_role.worker.name }
resource "aws_instance" "worker" {
  ami                    = data.aws_ssm_parameter.worker_ami.value
  instance_type          = "t3.micro"
  key_name               = var.key_name
  iam_instance_profile   = aws_iam_instance_profile.worker.name
  subnet_id              = aws_subnet.worker.id
  vpc_security_group_ids = [aws_security_group.worker.id]
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }
  root_block_device {
    encrypted             = true
    delete_on_termination = true
    volume_size           = 24
    volume_type           = "gp3"
  }
  user_data  = <<-SCRIPT
    #!/bin/bash
    set -euxo pipefail
    if ! snap list amazon-ssm-agent >/dev/null 2>&1; then
      snap install amazon-ssm-agent --classic
    fi
    snap start --enable amazon-ssm-agent
  SCRIPT
  tags       = { Name = "${var.project_name}-ec2-worker" }
  depends_on = [aws_route.worker_internet, aws_route_table_association.worker, aws_iam_role_policy.worker, aws_iam_role_policy_attachment.worker_ssm]
}
resource "aws_ebs_volume" "worker_data" {
  availability_zone = aws_subnet.worker.availability_zone
  encrypted         = true
  size              = 8
  type              = "gp3"
  tags              = { Name = "${var.project_name}-admin-data" }
  lifecycle { prevent_destroy = true }
}
resource "aws_volume_attachment" "worker_data" {
  device_name = "/dev/sdf"
  instance_id = aws_instance.worker.id
  volume_id   = aws_ebs_volume.worker_data.id
}
