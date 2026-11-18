resource "aws_sqs_queue" "managed_dlq" {
  name                      = "${var.managed_project_name}-telegram-updates-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
  lifecycle { prevent_destroy = true }
}
resource "aws_sqs_queue" "managed_updates" {
  name                       = "${var.managed_project_name}-telegram-updates"
  receive_wait_time_seconds  = 20
  visibility_timeout_seconds = var.managed_sqs_visibility_timeout
  message_retention_seconds  = 1209600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.managed_dlq.arn
    maxReceiveCount     = 5
  })
  lifecycle { prevent_destroy = true }
}
resource "aws_cloudwatch_metric_alarm" "managed_dlq" {
  alarm_name          = "${var.managed_project_name}-dead-letter"
  alarm_description   = "Unprocessed Telegram updates require inspection; no notification destination configured."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { QueueName = aws_sqs_queue.managed_dlq.name }
}
