# Edge authentication function (OAuth2)

This [Lambda@Edge](https://aws.amazon.com/lambda/edge/) function performs OAuth2 token verification within CloudFront. Therefore it is only needed when the authentication mode specified at deployment is `OAuth2-Cognito`.

The reason for performing authentication in CloudFront using this function rather just letting API Gateway handle OAuth2 authentication is to allow CloudFront caches to be used to cache responses closer to users (and therefore further reduce latency). If API Gateway was used for authentication, every request would have to travel to API Gateway.

You can install the OAuth2 edge resources into the us-east-1 region using the "Launch Stack" button below.

[![Launch Stack](https://cdn.rawgit.com/buildkite/cloudformation-launch-stack-button-svg/master/launch-stack.svg)](https://console.aws.amazon.com/cloudformation/home?region=us-east-1#/stacks/create/review?templateURL=https://s3.amazonaws.com/personalize-solution-staging-us-east-1/personalization-apis-edge/template.yaml&stackName=personalization-apis-edge)

If you'd rather install the OAuth2 edge resources manually using AWS SAM, execute the following commands at the command line (the `deploy_edge_auth.sh` shell script can also be used as a shortcut).

```bash
sam build --use-container --cached --template-file template-edge.yaml && sam deploy --region us-east-1 --config-file samconfig-edge.toml --guided
```

Once deployment finishes successfully, sign in to the AWS console, switch to the `N. Virginia - us-east-1` region, browse to the Lambda service page, find the `EdgeAuthFunction`, and deploy it to the CloudFront distribution created when you installed the solution (check the CloudFormation output parameters to determine the distribution URL and ID) as a **Viewer Request**. See the [API authentication documentation](../../docs/api_authentication.md) for details. This does not mean that the Personalization APIs must be deployed in "us-east-1" as well--those resources should be deployed in the AWS region where your recommenders are deployed.

**API requests will not be authenticated by this function until the edge function is successfully deployed to CloudFront.**