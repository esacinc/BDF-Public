# tracing.py

import time
import json
import logging
from contextlib import contextmanager, asynccontextmanager

logger = logging.getLogger("bdf.tracing")

class Tracer:
    def __init__(self, label="workflow"):
        self.label = label
        self.start_time = time.perf_counter()
        self.steps = []

    def _record_step(self, name, start, end):
        self.steps.append({
            "step": name,
            "duration_s": round(end - start, 2) 
        })

    @contextmanager
    def step(self, name):
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self._record_step(name, start, end)

    @asynccontextmanager
    async def async_step(self, name):
        start = time.perf_counter()
        yield
        end = time.perf_counter()
        self._record_step(name, start, end)

    def report(self, extra: dict = None):
        total = round(time.perf_counter() - self.start_time, 2) 
        payload = {
            "label": self.label,
            "total_s": total, 
            "steps": self.steps,
        }
        if extra:
            payload.update(extra)

        logger.info(json.dumps(payload))
        return payload
