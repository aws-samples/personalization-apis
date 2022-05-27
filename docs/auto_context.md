# Automatic Context and Filter Values

Contextual recommendations can provide recommendations that are not only personalized to a user but also take into account the user's current context. The idea is to build a recommender that learns users' interests that include context. Examples of context include the user's current device type (i.e., mobile phone, tablet, desktop, smart TV), location, time of day, day of week, season, or even weather conditions. Combining a user's behavior with current context is a powerful way to provide recommendations that target the moment the user is in. For example, for a VOD platform, a user may consume different video content on their mobile phone during the week when commuting to/from work (TV sitcoms, news) than on weekends on their smart TV (feature films). Or a national clothing retailer may want to personalize recommendations to match the climate and currrent season of their users.

Taking advantage of context requires specifying context values with interactions/events so recommenders can use context as features when training models as well as providing the user's current context at inference time. This typically requires adding logic to client and possibly server applications to derive context.

Another place where context can be used is in filters where you want to use more rigid guardrails based on context to include or exclude items in recommendations. For example, a quick service restaurant (QSR) that serves breakfast, lunch, and dinner where items are only available during their respective meal type, may use a filter that limits recommendations to items that match the meal type based on the user's current time.

The Personalization APIs solution has the ability to automatically generate context values for many common use cases for new interactions/events, for inference calls, and dynamic filter values. This eliminates the need for you to update your client and server applications to derive context for these use cases.

Automatically derving context and filter values is achieved through [Amazon CloudFront headers](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/using-cloudfront-headers.html) that are included in requests to custom origins (i.e., the Personalization API endpoints). Through the Personalization APIs [configuration](./configuration.md), you can setup rules to map these header values to fields and values in your schema and interactions dataset for Amazon Personalize.

Examples of automatic context:

- Device type: map user's current device type to a categorical field value in a Personalize interactions dataset
    - Map `cloudfront-is-*-viewer` header with a value of `true` to a named field value
- Location: map current location of user into categorical field value in the interactions dataset
	- Map `cloudfront-viewer-country` header value to a named field value
    - Map `cloudfront-viewer-city` header value to a named field value
	- Map `cloudfront-viewer-country-region` header value to a named field value
	- Map `cloudfront-viewer-postal-code` header value to a named field value
	- Map `cloudfront-viewer-metro-code` header value to a named field value
	- Map `cloudfront-viewer-time-zone` header value to a named field value
- Time: map time of request in user's timezone into categorical field value
    - Day of week (e.g., mon, tue, wed, thu, fri, sat, sun)
	- Weekday/weekend (e.g., mon-fri = weekday, sat/sun = weekend)
	- Time of day (e.g., morning, afternoon, evening, night)
	- Season mapped to user's current hemisphere (spring, summer, fall, winter)
- Third party data (FUTURE: art of the possible)
    - Weather: map current weather condition in user's location (latitude/longitude, metro code, city, etc) into categorical field value in the interactions dataset
	- Demographics: map demographics in user's location into categorical field value

## Adding context mapping to your configuration

Automatic context mappings for interactions/events and inference calls are specified in an `autoContext` list for namespace, recommender, or variation.

### Device type

Here is an example that populates a `deviceType` field with the value of `Desktop`, `Phone`, `TV`, or `Tablet` depending value of the corresponding CloudFront header. An optional `default` value can be specified that is used when none of automatic context rules evaluate to true. Note that `evaluateAll` property controls whether all rules are evaluated (`true`) or whether evaluation stops at the first rule that is matched (`false`).

```json
{
    "namespaces": {
        "my-store": {
            "autoContext": {
                "deviceType": {
                    "type": "string",
                    "default": "Desktop",
                    "evaluateAll": true,
                    "rules": [
                        {
                            "type": "header-value",
                            "header": "cloudfront-is-desktop-viewer",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": "true",
                                    "mapTo": "Desktop"
                                }
                            ]
                        },
                        {
                            "type": "header-value",
                            "header": "cloudfront-is-mobile-viewer",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": "true",
                                    "mapTo": "Phone"
                                }
                            ]
                        },
                        {
                            "type": "header-value",
                            "header": "cloudfront-is-smarttv-viewer",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": "true",
                                    "mapTo": "TV"
                                }
                            ]
                        },
                        {
                            "type": "header-value",
                            "header": "cloudfront-is-tablet-viewer",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": "true",
                                    "mapTo": "Tablet"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }
}
```

### Time based context

Time-based context uses the current time in the user's current time zone to field values.

The following example populates a `timeOfDay` field based on the current hour of the day in the user's time zone. The hour value 0-23 can be used with value mapping expressions to map ranges of values to the desired categorical value. In the following example, 10pm-3am is `Night`, 4am-10am is `Morning`, 11am-5pm is `Afternoon`, and 6pm-9pm is `Evening`. Note that since the `evaluateAll` field is set to `false`, rule evaluation stops after the first matched rule.

```json
{
    "namespaces": {
        "my-store": {
            "autoContext": {
                "timeOfDay": {
                    "type": "string",
                    "evaluateAll": false,
                    "rules": [
                        {
                            "type": "hour-of-day",
                            "valueMappings": [
                                {
                                    "operator": "less-than",
                                    "value": 4,
                                    "mapTo": "Night"
                                },
                                {
                                    "operator": "less-than",
                                    "value": 11,
                                    "mapTo": "Morning"
                                },
                                {
                                    "operator": "less-than",
                                    "value": 18,
                                    "mapTo": "Afternoon"
                                },
                                {
                                    "operator": "less-than",
                                    "value": 22,
                                    "mapTo": "Evening"
                                },
                                {
                                    "operator": "greater-than",
                                    "value": 21,
                                    "mapTo": "Night"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }
}
```

A similar approach could be used to map the current time of day to different meal types (breakfast, lunch, dinner).

Another time-based rule type is `day-of-week` that can be used to map the current day of week to the day of week name or a day of week type (i.e. `WeekDay`/`Weekend`).

```json
{
    "namespaces": {
        "my-store": {
            "autoContext": {
                "dayOfWeek": {
                    "type": "string",
                    "evaluateAll": false,
                    "rules": [
                        {
                            "type": "day-of-week",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": 0,
                                    "mapTo": "Monday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 1,
                                    "mapTo": "Tuesday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 2,
                                    "mapTo": "Wednesday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 3,
                                    "mapTo": "Thursday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 4,
                                    "mapTo": "Friday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 5,
                                    "mapTo": "Saturday"
                                },
                                {
                                    "operator": "equals",
                                    "value": 6,
                                    "mapTo": "Sunday"
                                }
                            ]
                        }
                    ]
                },
                "weekDayType": {
                    "type": "string",
                    "evaluateAll": false,
                    "rules": [
                        {
                            "type": "day-of-week",
                            "valueMappings": [
                                {
                                    "operator": "less-than",
                                    "value": 5,
                                    "mapTo": "Weekday"
                                },
                                {
                                    "operator": "greater-than",
                                    "value": 4,
                                    "mapTo": "Weekend"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }
}
```

Finally, here is an example that maps the current time in the user's current time zone and hemisphere (based on location) to a season. The values for the four seasons are `0` for Spring, `1` for Summer, `2` for Fall, and `3` for Winter.

```json
{
    "namespaces": {
        "my-store": {
            "autoContext": {
                "season": {
                    "type": "string",
                    "evaluateAll": false,
                    "rules": [
                        {
                            "type": "season",
                            "valueMappings": [
                                {
                                    "operator": "equals",
                                    "value": 0,
                                    "mapTo": "Spring"
                                },
                                {
                                    "operator": "equals",
                                    "value": 1,
                                    "mapTo": "Summer"
                                },
                                {
                                    "operator": "equals",
                                    "value": 2,
                                    "mapTo": "Fall"
                                },
                                {
                                    "operator": "equals",
                                    "value": 3,
                                    "mapTo": "Winter"
                                }
                            ]
                        }
                    ]
                }
            }
        }
    }
}
```

### Location based context

The `header-value` rule type can be used with CloudFront location headers to use the value of the header as the field value (i.e. when value mapping is not required). Some examples:

```json
{
    "namespaces": {
        "my-store": {
            "autoContext": {
                "city": {
                    "type": "string",
                    "rules": [
                        {
                            "type": "header-value",
                            "header": "cloudfront-viewer-city"
                        }
                    ]
                },
                "region": {
                    "type": "string",
                    "rules": [
                        {
                            "type": "header-value",
                            "header": "cloudfront-viewer-country-region"
                        }
                    ]
                },
                "metroCode": {
                    "type": "integer",
                    "rules": [
                        {
                            "type": "header-value",
                            "header": "cloudfront-viewer-metro-code"
                        }
                    ]
                },
                "timeZone": {
                    "type": "string",
                    "rules": [
                        {
                            "type": "header-value",
                            "header": "cloudfront-viewer-time-zone"
                        }
                    ]
                }
            }
        }
    }
}
```

## Context and recommendation response caching

Using context to further personalize recommendations can reduce the cacheability of recommendations responses. Care must be taken to consider the contextual attributes of requests in cache keys so that any responses served from a cache are true to the user's current context. The Personalize APIs solution will automatically tune the cache key approach used by CloudFront, and API Gateway, and device (private) caches.

## Header reference

Depending on the deployment option for the API entry point type that you select when deploying the Personalization APIs solution, you will have access to different headers when deriving context.

### Using API Gateway REST Edge Endpoint

The following CloudFront headers are provided by the API Gateway managed CloudFront distribution.

- `CloudFront-Is-Desktop-Viewer`: Set to true when CloudFront determines that the viewer is a desktop device.
- `CloudFront-Is-Mobile-Viewer`: Set to true when CloudFront determines that the viewer is a mobile device.
- `CloudFront-Is-SmartTV-Viewer`: Set to true when CloudFront determines that the viewer is a smart TV.
- `CloudFront-Is-Tablet-Viewer`: Set to true when CloudFront determines that the viewer is a tablet
- `CloudFront-Viewer-Country`: Contains the two-letter country code for the viewer’s country. For a list of country codes, see ISO 3166-1 alpha-2.

This list cannot be changed.

### Using API Gateway HTTP Endpoint

When using CloudFront with an API Gateway HTTP endpoint (or an API Gateway REST regional endpoint), the complete list of supported CloudFront headers is available.

- `CloudFront-Is-Android-Viewer`: Set to true when CloudFront determines that the viewer is a device with the Android operating system.
- `CloudFront-Is-Desktop-Viewer`: Set to true when CloudFront determines that the viewer is a desktop device.
- `CloudFront-Is-IOS-Viewer`: Set to true when CloudFront determines that the viewer is a device with an Apple mobile operating system, such as iPhone, iPod touch, and some iPad devices.
- `CloudFront-Is-Mobile-Viewer`: Set to true when CloudFront determines that the viewer is a mobile device.
- `CloudFront-Is-SmartTV-Viewer`: Set to true when CloudFront determines that the viewer is a smart TV.
- `CloudFront-Is-Tablet-Viewer`: Set to true when CloudFront determines that the viewer is a tablet
- `CloudFront-Viewer-Address`: Contains the IP address of the viewer that sent the request to CloudFront, and the port used for the request. For example, a header value of 198.51.100.10:443 means the viewer’s IP address is 198.51.100.10 and the request port is 443.
- `CloudFront-Viewer-Country`: Contains the two-letter country code for the viewer’s country. For a list of country codes, see ISO 3166-1 alpha-2.
- `CloudFront-Viewer-City`: Contains the name of the viewer’s city.
- `CloudFront-Viewer-Country-Name`: Contains the name of the viewer’s country.
- `CloudFront-Viewer-Country-Region`: Contains a code (up to three characters) that represent the viewer’s region. The region is the most specific subdivision of the ISO 3166-2 code.
- `CloudFront-Viewer-Country-Region-Name`: Contains the name of the viewer’s region. The region is the most specific subdivision of the ISO 3166-2 code.
- `CloudFront-Viewer-Latitude`: Contains the viewer’s approximate latitude.
- `CloudFront-Viewer-Longitude`: Contains the viewer’s approximate longitude.
- `CloudFront-Viewer-Metro-Code`: Contains the viewer’s metro code. This is present only when the viewer is in the United States.
- `CloudFront-Viewer-Postal-Code`: Contains the viewer’s postal code.
- `CloudFront-Viewer-Time-Zone`: Contains the viewer’s time zone, in IANA time zone database format (for example, America/Los_Angeles).