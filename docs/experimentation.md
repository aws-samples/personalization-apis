# Personalization APIs experimentation: A/B testing

Support for A/B testing recommender strategies is built-in to the Personalization APIs solution. All that is needed to run an A/B test is to setup an experiment in [Amazon CloudWatch Evidently](https://aws.amazon.com/blogs/aws/cloudwatch-evidently/), configure your recommender variations in your Personalize APIs configuration, and take your experiment live. These steps are outlined in more detail below.

## Step 1: Setup features and experiment in [Amazon CloudWatch Evidently](https://aws.amazon.com/blogs/aws/cloudwatch-evidently/)

- [Create a project](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Evidently-newproject.html) in Evidently for your application.
- [Add a feature](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Evidently-newfeature.html) to your project representing the personalization use-case in your application. This can be a UI control or widget where you're displaying personalized recommendations.
    - Your feature can have one or more variations. To test different personalization recommenders for this feature, create a string type variation for each recommender that you want to test. For the variation value, enter a unique name for each variation for the feature. The name should be alphanumeric.
- [Create an experiment](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Evidently-newexperiment.html) for the feature.

## Step 2: Setup the recommender variations in your Personalization APIs configuration

Next, take the details of the project, feature, variations, and experiment to your Personalization APIs configuration. Below is an example configuration that defines an experiment with two variations that tests a related items recommender trained with the Personalize SIMS recipe against the a recommender trained with the Similar-Items recipe. Under `experiments` you can define one or more features where they key is the feature name from your Evidently experiment (`product-detail-view` in this case). Under `metrics`, the metric name (`productDetailRecClicked`) must match the metric name you setup in Evidently for your experiment and the `entityIdKey` and `valueKey` matches the corresponding metric settings for your experiment. The variation names are `sims` and `similar-items` and these must match the variation string values for the feature of the experiment.

```javascript
{
    "namespaces": {
        "my-store": {
            "recommenders": {
                "related-items": {
                    "similar": {
                        "experiments": {
                            "product-detail-view": {
                                "method": "evidently",
                                "project": "my-store",
                                "metrics": {
                                    "productDetailRecClicked": {
                                        "trackExposures": true,
                                        "entityIdKey": "userDetails.userId",
                                        "valueKey": "details.productClicked"
                                    }
                                }
                            }
                        },
                        "variations": {
                            "sims": {
                                "type": "personalize-campaign",
                                "arn": "arn:aws:personalize:[REGION:[ACCOUNT]:campaign/[CAMPAIGN_NAME]"
                            },
                            "similar-items": {
                                "type": "personalize-campaign",
                                "arn": "arn:aws:personalize:[REGION:[ACCOUNT]:campaign/[CAMPAIGN_NAME]"
                            }
                        }
                    }
                }
            }
        }
    }
}
```

Once your configuration is updated in AppConfig and deployed, the Personalization APIs will automatically pick it up.

## Step 3: Take your experiment live

Within Evidently, take your experiement live. The Personalization APIs solution will automatically call Evidently to evaluate the feature for the recommender to determine which variation to use for the current user and record an exposure event back to Evidently to indicate that the user receiving a variation. When an experiment is active, the API response will include details on the experiment. This will allow you to include this information back in the `/events` API to indicate the user converted (i.e. clicked on a recommendation, eventually purchased a recommended product or watched a recommended video).

### Exposure events

When an exeriment is active for a recommender and a user is provided recommendations from a recommender's variation, a exposure event is automatically posted to Evidently's PutProjectEvents API. This event indicates that the user has been presented with a variation and is part of the experiment.

### Conversion events

When a user converts for an experiment variation, you can include details on the experiment when you send events back to the Personalization APIs. The `experimentConversions` array can include one or more conversion events for the user. You must include the recommender name, feature name, metric name, and (optionally) a conversion value. If a value is not specified, the Personalization APIs solution will use `1.0` as the metric value.

`POST /events/{namespace}`

```javascript
{
   "userId": "12",
   "experimentConversions": [
        {
            "recommender": "similar",
            "feature": "product-detail-view",
            "metric": "productDetailRecClicked"
        }
    ]
}
```

