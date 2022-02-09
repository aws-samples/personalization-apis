# Edge authentication function updater (OAuth2)

This AWS Lambda function is CloudFormation custom resource function and is a companion to the [edge_auth_function](../edge_auth_function/) Lambda@Edge function. It is responsible for injecting Cognito and JWT details into the [edge_auth_function/index.js](../edge_auth_function/index.js) source file. This is required since Lambda@Edge functions do no support Lambda environment variables.

**This function is NOT a Lambda@Edge function! It's a regular Lambda function that is called by CloudFormation when the [template-edge.yaml](../../template-edge.yaml) template is deployed.** You can also call it directly to trigger the [edge_auth_function](../edge_auth_function/) to be updated when, say, you want to switch Cognito user pool settings.