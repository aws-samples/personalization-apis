# Personalization APIs Item Metadata

Item metadata is used to decorate recommender responses with the information needed to fully render recommendations in client applications. Item metadata is uploaded to an S3 bucket created by the Personalization APIs deployment. When files are uploaded into the appropriate folder in this bucket (based on the namespace key), an AWS Lambda function is invoked that updates the appropriate datastore(s) based on the configuration described below.

## Local DBM datastore

Declares that item metadata should be managed in a local DBM datastore for a namespace that is automatically downloaded from S3 and stored on the local Lambda volume.

```javascript
{
    "namespaces": {
        "my-app-1": {
            "inferenceItemMetadata": {
                "type": "localdb"
            },
            "recommenders": {
            }
        }
    }
}
```

- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.type`: Must be `"localdb"` (required).

## Amazon DynamoDB tables

Declares that a Amazon DynamoDB table should be used to query for item metadata for a particular namespace. The table can optionally be automatically provisioned by the Personalization APIs solution (when the configuration changes) or you can create the table directly. The table name is derived based on a concatenation of `PersonalizationApiItemMetadata_` and the namespace key. So for the example configuration fragment below, the table name would be `PersonalizationApiItemMetadata_my-app1`.

```javascript
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

- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.autoProvision`: boolean that controls whether the DynamoDB table should be created on the fly and its billing mode and provisioned throughput updated based on the configuration (optional). The default is `true`.
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.type`: Must be `"dynamodb"` (required).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.billingMode`: Valid values are `"PROVISIONED"` or `"PAY_PER_REQUEST"` (optional). Default is `"PAY_PER_REQUEST"`.
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.provisionedThroughput.readCapacityUnits`: Read capacity units (required if `billingMode` is `"PROVISIONED"`).
- `namespaces.{NAMESPACE_KEY}.inferenceItemMetadata.provisionedThroughput.writeCapacityUnits`: Write capacity units (required if `billingMode` is `"PROVISIONED"`).

## Preparing and Uploading Item Metadata to S3

When the Personalization APIs solution is deployed, an S3 bucket is created that is used as a landing zone for uploading item metadata. The bucket name can be determined from the CloudFormation output parameter named `ItemMetadataBucket`. To feed metadata for your items to the Personalization APIs solution, create a [JSON Lines](https://jsonlines.org/) file for each namespace where each file contains metadata for every item that could be recommended by recommenders in that namespace. All of the fields for an item's ID will be used to decorate the response for the item. For example, the following JSONL fragment includes metadata for 6 products for a sample e-commerce item catalog.

```javascript
{"id": "6579c22f-be2b-444c-a52b-0116dd82df6c", "current_stock": 15, "name": "Tan Backpack", "category": "accessories", "style": "backpack", "description": "This tan backpack is nifty for traveling", "price": 90.99, "image": "6579c22f-be2b-444c-a52b-0116dd82df6c.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/6579c22f-be2b-444c-a52b-0116dd82df6c.jpg"}
{"id": "2e852905-c6f4-47db-802c-654013571922", "current_stock": 15, "name": "Pale Pink Backpack", "category": "accessories", "style": "backpack", "description": "Pale pink backpack for women", "price": 123.99, "image": "2e852905-c6f4-47db-802c-654013571922.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/2e852905-c6f4-47db-802c-654013571922.jpg"}
{"id": "4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09", "current_stock": 17, "name": "Gainsboro Backpack", "category": "accessories", "style": "backpack", "description": "This gainsboro backpack for women is first-rate for the season", "price": 87.99, "image": "4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/4ec7ff5c-f70f-4984-b6c4-c7ef37cc0c09.jpg"}
{"id": "7977f680-2cf7-457d-8f4d-afa0aa168cb9", "current_stock": 17, "name": "Gray Backpack", "category": "accessories", "style": "backpack", "description": "This gray backpack for women is first-rate for the season", "price": 125.99, "image": "7977f680-2cf7-457d-8f4d-afa0aa168cb9.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/7977f680-2cf7-457d-8f4d-afa0aa168cb9.jpg"}
{"id": "b5649d7c-4651-458d-a07f-912f253784ce", "current_stock": 13, "name": "Peru-Orange Backpack", "category": "accessories", "style": "backpack", "description": "Peru-orange backpack for women", "price": 141.99, "image": "b5649d7c-4651-458d-a07f-912f253784ce.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/b5649d7c-4651-458d-a07f-912f253784ce.jpg"}
{"id": "296d144e-7f86-464b-9c5a-f545257f1700", "current_stock": 11, "name": "Black Backpack", "category": "accessories", "style": "backpack", "description": "This black backpack for women is first-class for the season", "price": 144.99, "image": "296d144e-7f86-464b-9c5a-f545257f1700.jpg", "gender_affinity": "F", "where_visible": "UI", "image_url": "https://d22kv7nk938ern.cloudfront.net/images/accessories/296d144e-7f86-464b-9c5a-f545257f1700.jpg"}
```

The only requirements for this file is that every line represent a single item as a complete JSON document and that the document has an `"id"` field that represents the item's ID. The item ID should be the same ID that will be returned by recommenders for the namespace. You can gzip the file (optional) before uploading it to S3. The file must be uploading into a folder with the following format.

```
import/{NAMESPACE_KEY}/
```

Where `{NAMESPACE_KEY}` is the namespace key in the configuration. For the example configuration fragments above for the `my-app-1` namespace, if you put your metadata in a file named `item-metadata.jsonl` and gzipped the file, the file would be uploaded as:

```
import/my-app-1/item-metadata.jsonl.gz
```

Once the file has been uploaded for a namespace, the file is loaded into the datastore based on the configuration. For example, if DynamoDB is configured as the item metadata datastore type for a namespace, the contents of the uploaded file will be loaded into a DynamoDB table for the namespace. Any items that already existed in the table that were not included in the uploaded file be automatically deleted. If the datastore type is localdb, a DBM file will be built and staged in the S3 bucket. This staged DBM file is downloaded by the Personalization APIs Lambda function to the Lambda instance's local volume.

A decorated API response that includes item metadata would look something like this where the `metadata` object includes the item metadata that was uploaded to the S3 bucket:

```javascript
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
