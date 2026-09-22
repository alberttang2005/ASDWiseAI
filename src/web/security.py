"""Bounded, single-worker admission controls. No caregiver content is retained."""
import asyncio
import os
import time
from collections import deque
from fastapi import HTTPException


class RequestLimits:
    def __init__(self, clock=time.monotonic, global_limit=600, owner_limit=120, max_owners=2048):
        self.clock = clock
        self.global_limit, self.owner_limit, self.max_owners = global_limit, owner_limit, max_owners
        self.requests, self.creations, self.owners = deque(), deque(), {}

    def expire(self):
        cutoff = self.clock() - 60
        for queue in (self.requests, self.creations, *self.owners.values()):
            while queue and queue[0] <= cutoff:
                queue.popleft()
        self.owners = {owner: queue for owner, queue in self.owners.items() if queue}

    def allow(self, owner, creating=False):
        self.expire()
        queue = self.owners.get(owner)
        if (len(self.requests) >= self.global_limit
                or (creating and len(self.creations) >= 20)
                or (queue is not None and len(queue) >= self.owner_limit)
                or (queue is None and len(self.owners) >= self.max_owners)):
            return False
        now = self.clock()
        self.requests.append(now)
        self.owners.setdefault(owner, deque()).append(now)
        if creating:
            self.creations.append(now)
        return True


class SessionLocks:
    """Fixed lock stripes prevent arbitrary session IDs from allocating memory."""
    def __init__(self):
        self.locks = tuple(asyncio.Lock() for _ in range(256))

    def __getitem__(self, sid):
        return self.locks[hash(sid) % len(self.locks)]


class AIBudget:
    """Fail closed instead of queueing paid work. Units are not dollar estimates."""
    def __init__(self, concurrency=None, units=None):
        self.concurrency = int(os.getenv('ASDWISE_AI_CONCURRENCY', '4')) if concurrency is None else concurrency
        self.remaining = int(os.getenv('ASDWISE_AI_BUDGET_UNITS', '1000')) if units is None else units
        if self.concurrency < 1 or self.remaining < 0:
            raise ValueError('AI concurrency must be positive and budget units nonnegative')
        self.active = 0

    def reserve(self, units):
        if self.active >= self.concurrency:
            raise HTTPException(429, 'The service is busy. Please retry shortly.', headers={'Retry-After': '30'})
        if self.remaining < units:
            raise HTTPException(503, 'The service usage allowance has been reached. Please contact the operator.')
        self.remaining -= units
        self.active += 1

    def release(self):
        self.active -= 1

    async def call(self, units, operation, *args):
        self.reserve(units)
        try:
            return await operation(*args)
        finally:
            self.release()
