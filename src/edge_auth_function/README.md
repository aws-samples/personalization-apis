# Edge authentication function (OAuth2)

This [Lambda@Edge](https://aws.amazon.com/lambda/edge/) function performs OAuth2 token verification within CloudFront. Therefore it is only needed when the authentication mode specified at deployment is `OAuth2-Cognito`.

The reason for performing authentication in CloudFront using this function rather just letting API Gateway handle OAuth2 authentication is to allow CloudFront caches to be used to cache responses closer to users (and therefore further reduce latency). If API Gateway was used for authentication, every request would have to travel to API Gateway.

This function is deployed using a dedicated AWS SAM template, [template-edge.yaml](../../template-edge.yaml).

```bash
sam build --use-container --cached --template-file template-edge.yaml && sam deploy --region us-east-1 --config-file samconfig-edge.toml --guided
```

**IMPORTANT**: the [template-edge.yaml](../../template-edge.yaml) resources **must** be deployed in the "us-east-1" region as shown above since that is the only region where Lambda@Edge functions can be deployed to a CloudFront distribution. This does not mean that the Personalization APIs must be deployed in "us-east-1" as well--those resources should be deployed in the AWS region where your recommenders are deployed.

Once you deploy this function in your AWS account, you must deploy it to the CloudFront distribution created when the Personalization APIs were deployed (check the CloudFormation output parameters to determine the distribution URL and ID). **API requests will not be authenticated by this function until this additional step is completed.**