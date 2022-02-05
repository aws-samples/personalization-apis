# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import decimal

class CompatEncoder(json.JSONEncoder):
    """ Compatibility encoder that supports Decimal type
    Usage:
    json.dumps(data, cls=CompatEncoder)
    """
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            if obj % 1 > 0:
                return float(obj)
            else:
                return int(obj)
        else:
            return super(CompatEncoder, self).default(obj)
