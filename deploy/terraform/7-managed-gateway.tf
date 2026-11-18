resource "aws_apigatewayv2_api" "managed" {
  name          = "${var.managed_project_name}-gateway-http-api"
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_integration" "managed" {
  api_id                 = aws_apigatewayv2_api.managed.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.managed_webhook.arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "managed" {
  api_id    = aws_apigatewayv2_api.managed.id
  route_key = "POST /webhook/managed/{bot_id}"
  target    = "integrations/${aws_apigatewayv2_integration.managed.id}"
}
resource "aws_cloudwatch_log_group" "managed_api" {
  name_prefix       = "/aws/apigateway/${var.managed_project_name}-"
  retention_in_days = 14
}
resource "aws_apigatewayv2_stage" "managed" {
  api_id      = aws_apigatewayv2_api.managed.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.managed_api.arn
    format          = jsonencode({ requestId = "$context.requestId", status = "$context.status", routeKey = "$context.routeKey" })
  }
}
resource "aws_lambda_permission" "managed_gateway" {
  statement_id   = "AllowApiGateway"
  function_name  = aws_lambda_function.managed_webhook.function_name
  action         = "lambda:InvokeFunction"
  principal      = "apigateway.amazonaws.com"
  source_arn     = "${aws_apigatewayv2_api.managed.execution_arn}/*/POST/webhook/managed/*"
  source_account = data.aws_caller_identity.current.account_id
}
resource "aws_cloudwatch_metric_alarm" "managed_api_errors" {
  alarm_name          = "${var.managed_project_name}-api-errors"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { ApiId = aws_apigatewayv2_api.managed.id }
}
