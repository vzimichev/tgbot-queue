resource "aws_cloudwatch_log_group" "admin_lambda" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = 14
}
resource "aws_iam_role" "admin_lambda" {
  name_prefix = "${var.function_name}-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}
resource "aws_iam_role_policy" "admin_lambda" {
  name = "telegram-webhook-publish"
  role = aws_iam_role.admin_lambda.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = "sqs:SendMessage", Resource = aws_sqs_queue.admin_updates.arn },
      { Effect = "Allow", Action = "secretsmanager:GetSecretValue", Resource = var.webhook_secret_arn },
      { Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "${aws_cloudwatch_log_group.admin_lambda.arn}:*" }
    ]
  })
}
data "archive_file" "admin_lambda" {
  type = "zip"
  source {
    content  = file("${path.module}/lambda/admin.py")
    filename = "index.py"
  }
  output_path = "${path.module}/.terraform/admin-lambda.zip"
}
resource "aws_lambda_function" "admin_webhook" {
  function_name    = var.function_name
  description      = "Telegram admin webhook publisher to SQS."
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "index.handler"
  role             = aws_iam_role.admin_lambda.arn
  timeout          = 25
  memory_size      = 128
  filename         = data.archive_file.admin_lambda.output_path
  source_code_hash = data.archive_file.admin_lambda.output_base64sha256
  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.admin_lambda.name
  }
  environment {
    variables = {
      SQS_QUEUE_URL      = aws_sqs_queue.admin_updates.url
      WEBHOOK_SECRET_ARN = var.webhook_secret_arn
    }
  }
  depends_on = [aws_iam_role_policy.admin_lambda]
  lifecycle { prevent_destroy = true }
}
