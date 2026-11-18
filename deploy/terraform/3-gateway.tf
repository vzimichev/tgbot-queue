resource "aws_apigatewayv2_api" "admin" {
  name          = "${var.project_name}-gateway-http-api"
  protocol_type = "HTTP"
}
resource "aws_apigatewayv2_integration" "admin" {
  api_id                 = aws_apigatewayv2_api.admin.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.admin_webhook.arn
  payload_format_version = "2.0"
  timeout_milliseconds   = 29000
}
resource "aws_apigatewayv2_route" "admin" {
  api_id    = aws_apigatewayv2_api.admin.id
  route_key = "POST /webhook"
  target    = "integrations/${aws_apigatewayv2_integration.admin.id}"
}
resource "aws_cloudwatch_log_group" "admin_api" {
  name_prefix       = "/aws/apigateway/${var.project_name}-"
  retention_in_days = 14
}
resource "aws_apigatewayv2_stage" "admin" {
  api_id      = aws_apigatewayv2_api.admin.id
  name        = "$default"
  auto_deploy = true
  default_route_settings {
    throttling_burst_limit = 10
    throttling_rate_limit  = 5
  }
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.admin_api.arn
    format          = jsonencode({ requestId = "$context.requestId", status = "$context.status", routeKey = "$context.routeKey" })
  }
}
resource "aws_lambda_permission" "admin_gateway" {
  statement_id   = "AllowApiGateway"
  function_name  = aws_lambda_function.admin_webhook.function_name
  action         = "lambda:InvokeFunction"
  principal      = "apigateway.amazonaws.com"
  source_arn     = "${aws_apigatewayv2_api.admin.execution_arn}/*/POST/webhook"
  source_account = data.aws_caller_identity.current.account_id
}
resource "aws_cloudwatch_metric_alarm" "admin_api_errors" {
  alarm_name          = "${var.project_name}-api-errors"
  namespace           = "AWS/ApiGateway"
  metric_name         = "5xx"
  statistic           = "Sum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { ApiId = aws_apigatewayv2_api.admin.id }
}
