# Personalization APIs Inference Item Metadata

Having access to item metadata (item name, price, description, category, brand, genre, etc) directly in recommender responses allows applications to more easily render recommendations in their UI. However, many primitive recommendation systems, such as Amazon Personalize, provide only item IDs and not item metadata in their responses. Although Amazon Personalize campaigns and recommenders can be configured to return item metadata, there are limits on the number of columns (10) and items (50) that can be returned when item metadata for responses is enabled. There is also an additional charge to have item metadata returned in Personalize responses (see the [pricing page](https://aws.amazon.com/personalize/pricing/) for details).

This project provides the ability to leverage the native capability of underlying recommenders from Amazon Personalize to provide item metadata as well as an alternative sidecar item metadata storage and retrievel mechanism that injects item metadata in responses before they are returned by the API. See the detailed instructions below on each mechanism.

** Keep in mind that item metadata in responses can be controlled by the `decorateItems` query string parameter to API requests. By default item metadata is enabled (if configured as described below) but it can be disabled at the request level by setting `decorateItems` to 0/false/no in your requests.

## Personalize item metadata

If you're using Amazon Personalize campaigns and/or recommenders with a deployment of this project and your use case is within the 10 metadata returned column and 50 item limit, then using the native Amazon Personalize item metadata return feature may be the best option. Some configuration is still required to use this approach.

First, you will have to enable metadata to be returned from your Amazon Personalize campaigns and/or recommenders. This can be done in the Amazon Personalize console or API when creating your campaigns or recommenders (for the API/SDK, see the `campaignConfig.enableMetadataWithRecommendations` parameter for the [CreateCampaign](https://docs.aws.amazon.com/personalize/latest/dg/API_CreateCampaign.html) and [UpdateCampaign](https://docs.aws.amazon.com/personalize/latest/dg/API_UpdateCampaign.html) APIs for campaigns and the `recommenderConfig.enableMetadataWithRecommendations` parameter for the [CreateRecommender](https://docs.aws.amazon.com/personalize/latest/dg/API_CreateRecommender.html) and [UpdateRecommender](https://docs.aws.amazon.com/personalize/latest/dg/API_UpdateRecommender.html) APIs for recommenders).

Once metadata has been enabled for your Amazon Personalize campaigns/recommenders, you can then configure the Personalization APIs to request item metadata when making inference calls. This is done with the `inferenceMetadata` section in the Personalization APIs configuration. Below is an example of using item metadata provided by Amazon Personalize (`type` of `personalize`) and specifying that the columns `NAME`, `DESCRIPTION`, `PRICE`, and `CATEGORY` should be requested from Personalize and returned by the API response. The column names must match columns in your Amazon Personalize items dataset schema.

```json
{
    "namespaces": {
        "my-app-1": {
            "inferenceItemMetadata": {
                "type": "personalize",
                "itemColumns": [
                    "NAME",
                    "DESCRIPTION",
                    "PRICE",
                    "CATEGORY"
                ]
            },
            "recommenders": {
            }
        }
    }
}
```

- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.type`: Must be `"personalize"` (required to use Amazon Personalize provided item metadata).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.itemColumns`: Array of column names to request Personalize to return in responses (required).

Although the example above shows the `inferenceItemMetadata` being specified at the namespace level, it can also be specified at the recommender or variation level instead. This allows you override item metadata configurations at different levels of the configuration.

An API response that includes item metadata from Amazon Personalize would look something like this where the `metadata` dictionary in the response includes the item metadata columns that were configured in `inferenceItemMetadata.itemColumns`:


```json
{
  "itemList": [
    {
      "itemId": "f6231107-7050-44ea-ac6a-dcb09f4a0b33",
      "score": 0.298052,
      "metadata": {
        "name": "Camping Lamp",
        "category": "outdoors",
        "description": "Be sure to bring this camping lamp with you to the outdoors",
        "price": 19.99
      }
    }
  ]
}
```

Note that Amazon Personalize will convert snake case column names to camel case in the response. For example, the schema column `BRAND_NAME` will be converted to `brandName` in the response. In addition, categorical field values will be returned as formatted when they were ingested (i.e., `ONE|TWO|THREE`) into Amazon Personalize rather than being returned as an array of values (i.e., `["ONE","TWO","THREE"]`)

## Sidecar item metadata storage, retrieval, and injection

As mentioned above, the Personalization APIs project also supports an item metadata sidecar feature whereby item metadata is injected into recommender responses before they are returned from the API layer. There are currently two sidecar implementations supported by the project.

To take advantage of the sidecar item metadata capability, you upload your inference item metadata to the S3 staging bucket created by the Personalization APIs deployment. The name of this bucket can be found in the CloudFormation output parameters (look for the `StagingBucket` output parameter). When you upload your inference item metadata (described in detail below) to the appropriate folder in the staging bucket (the folder name is based on the namespace key), an AWS Lambda function is invoked that automatically updates the appropriate sidecar datastore(s) based on the configuration described below. **Therefore, it's vital that you update your configuration with inference item metadata configuration before uploading your item metadata to the staging bucket.**

### Local DBM datastore

Declares that item metadata should be managed in a local DBM datastore for a namespace that is automatically downloaded from S3 and stored on the local Lambda volume of the API origin function. This option provides the lowest possible latency for item metadata decoration (~1-3ms) but is not suitable for very large item catalogs for when a large number of namespaces are served by the same Personalization APIs deployment.

```json
{
    "namespaces": {
        "my-app-1": {
            "inferenceItemMetadata": {
                "type": "localdb",
                "syncInterval": 300
            },
            "recommenders": {
            }
        }
    }
}
```

- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.type`: Must be `"localdb"` (required).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.syncInterval`: How often to sync DBM files from the S3 staging bucket in seconds (optional, default is 300 seconds).

### Amazon DynamoDB tables

Declares that a Amazon DynamoDB table should be used to query for item metadata for a particular namespace. The table can optionally be automatically provisioned by the Personalization APIs solution (when the configuration changes) or you can create the table directly (see `autoProvision` field). The table name is derived based on a concatenation of `PersonalizationApiItemMetadata_` and the namespace key. So for the example configuration fragment below, the table name would be `PersonalizationApiItemMetadata_my-app1`. Therefore, if you create the DynamoDB table yourself, you must use the apppropriate table name.

```json
{
    "namespaces": {
        "my-app-1": {
            "inferenceItemMetadata": {
                "autoProvision": true,
                "type": "dynamodb",
                "billingMode": "PROVISIONED",
                "provisionedThroughput": {
                    "readCapacityUnits": 10,
                    "writeCapacityUnits": 2
                }
            },
            "recommenders": {
            }
        }
    }
}
```

- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.autoProvision`: boolean that controls whether the DynamoDB table should be created automatically on-the-fly and its billing mode and provisioned throughput updated based on the configuration (optional). The default is `true`.
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.type`: Must be `"dynamodb"` (required).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.billingMode`: Valid values are `"PROVISIONED"` or `"PAY_PER_REQUEST"` (optional). Default is `"PAY_PER_REQUEST"`.
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.provisionedThroughput.readCapacityUnits`: Read capacity units (required if `billingMode` is `"PROVISIONED"`).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.provisionedThroughput.writeCapacityUnits`: Write capacity units (required if `billingMode` is `"PROVISIONED"`).

### Preparing and Uploading Inference Item Metadata to S3

When the Personalization APIs solution is deployed, an S3 bucket is created that is used as a staging area for uploading item metadata. The bucket name can be determined from the CloudFormation output parameter named `StagingBucket`. To provide inference item metadata for your items to the Personalization APIs solution, create a [JSON Lines](https://jsonlines.org/) file for each namespace where each file contains metadata for every item that could be recommended by recommenders for that namespace. All of the fields for an item's ID will be used to decorate the response for the item. For example, the following JSONL fragment includes metadata for 6 products for a sample e-commerce item catalog.

```json
{"id": "6579c22f-be2b-444c-a52b-0116dd82df6c", "current_stock": 15, "name": "Tan Backpack", "category": "accessories", "style": "backpack", "description": "This tan backpack is nifty for traveling", "price": 90.99, "image": "6579c22f-be2b-444c-a52b-0116dd82df6c.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/6579c22f-be2b-444c-a52b-0116dd82df6c.jpg"}
{"id": "2e852905-c6f4-47db-802c-654013571922", "current_stock": 15, "name": "Pale Pink Backpack", "category": "accessories", "style": "backpack", "description": "Pale pink backpack for women", "price": 123.99, "image": "2e852905-c6f4-47db-802c-654013571922.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/2e852905-c6f4-47db-802c-654013571922.jpg"}
{"id": "4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09", "current_stock": 17, "name": "Gainsboro Backpack", "category": "accessories", "style": "backpack", "description": "This gainsboro backpack for women is first-rate for the season", "price": 87.99, "image": "4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09.jpg"}
{"id": "7977f680-2cf7-457d-8f4d-afa0aa168cb9", "current_stock": 17, "name": "Gray Backpack", "category": "accessories", "style": "backpack", "description": "This gray backpack for women is first-rate for the season", "price": 125.99, "image": "7977f680-2cf7-457d-8f4d-afa0aa168cb9.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/7977f680-2cf7-457d-8f4d-afa0aa168cb9.jpg"}
{"id": "b5649d7c-4651-458d-a07f-912f253784ce", "current_stock": 13, "name": "Peru-Orange Backpack", "category": "accessories", "style": "backpack", "description": "Peru-orange backpack for women", "price": 141.99, "image": "b5649d7c-4651-458d-a07f-912f253784ce.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/b5649d7c-4651-458d-a07f-912f253784ce.jpg"}
{"id": "296d144e-7f86-464b-9c5a-f545257f1700", "current_stock": 11, "name": "Black Backpack", "category": "accessories", "style": "backpack", "description": "This black backpack for women is first-class for the season", "price": 144.99, "image": "296d144e-7f86-464b-9c5a-f545257f1700.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/296d144e-7f86-464b-9c5a-f545257f1700.jpg"}
```

The only requirements for this file is that every line represent a single item as a complete JSON document and that the document has an `"id"` field that represents the item's ID. The item ID should be the same ID that will be returned by recommenders for the namespace. You can optionally gzip the file before uploading it to the S3 staging bucket. The file must be uploaded into a folder in the staging bucket with the following format.

```
import/{NAMESPACE_KEY}/
```

Where `{NAMESPACE_KEY}` is the namespace key in the configuration. For the example configuration fragments above for the `my-app-1` namespace, if you put your metadata in a file named `item-metadata.jsonl` and gzipped the file, the file would be uploaded as:

```
import/my-app-1/item-metadata.jsonl.gz
```

Once the file has been uploaded for a namespace, the file is loaded into the datastore based on the configuration. For example, if DynamoDB is configured as the item metadata datastore type for a namespace, the contents of the uploaded file will be loaded into a DynamoDB table for the namespace. Any items that already existed in the table that were not included in the uploaded file be automatically deleted. If the datastore type is `localdb`, a DBM file will be built and staged in the S3 staging bucket in the `localdbs/` folder. This staged DBM file is automatically downloaded by the Personalization APIs Lambda function to the Lambda instance's local volume.

A decorated API response that includes item metadata would look something like this where the `metadata` dictionary includes the item metadata that was uploaded to the S3 staging bucket:

```json
{
  "itemList": [
    {
      "itemId": "f6231107-7050-44ea-ac6a-dcb09f4a0b33",
      "score": 0.298052,
      "metadata": {
        "current_stock": 16,
        "name": "Camping Lamp",
        "category": "outdoors",
        "style": "camping",
        "description": "Be sure to bring this camping lamp with you to the outdoors",
        "price": 19.99,
        "image": "f6231107-7050-44ea-ac6a-dcb09f4a0b33.jpg",
        "where_visible": "UI",
        "image_url": "https://d22kv7nk938ern.cloudfront.net/images/outdoors/f6231107-7050-44ea-ac6a-dcb09f4a0b33.jpg"
      }
    }
  ]
}
```
