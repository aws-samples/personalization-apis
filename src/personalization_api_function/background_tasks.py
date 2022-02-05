# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import time

from typing import List
from concurrent.futures import ThreadPoolExecutor, Future
from aws_lambda_powertools import Logger, Tracer

logger = Logger(child=True)
tracer = Tracer()

class BackgroundTasks():
    def __init__(self):
        self.pool: ThreadPoolExecutor = None
        self.futures: List[Future] = []
        self.pool_init = 0
        self.task_count = 0

    def submit(self, fn, /, *args, **kwargs):
        if not self.pool:
            self.pool_init = time.time()
            self.pool = ThreadPoolExecutor()

        self.futures.append(self.pool.submit(fn, *args, **kwargs))
        self.task_count += 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.pool:
            logger.info('Waiting for background tasks to complete')
            self.pool.shutdown(True)
            logger.info('%s background tasks completed in %0.2fms', self.task_count, time.time() - self.pool_init)
