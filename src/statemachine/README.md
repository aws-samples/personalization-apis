# Configuration synchronization state machine

The [sync_resources.asl.json](./sync_resources.asl.json) file is an AWS Step Function state machine definition that synchronizes cache settings found in your [configuration](../../docs/configuration.md) to CloudFront and/or API Gateway as well as provision tables in DynamoDB to hold item metadata (if configured to do so).