# Synchronize cache settings function

This AWS Lambda function is called via the [sync_resources.asl.json](../statemachine/sync_resources.asl.json) AWS Step Function state machine to synchronize cache settings in your [configuration](../../docs/configuration.md) to CloudFront and/or API Gateway as needed. The state machine is executed each time the configuration is deployed in AWS AppConfig.