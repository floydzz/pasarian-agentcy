"""Provider call accounting with per-job concurrency-safe token/call guards.

Unknown provider usage remains NULL. A reserved token allowance is conservative
for text and is a guard, not a currency invoice or an image/video price estimate.
"""
from contextvars import ContextVar
from dataclasses import dataclass, field
import hashlib
import json
import logging
import threading
import time
from functools import wraps

from sqlalchemy import select
from app.db import SessionLocal
from app.models import AICall, Workspace
from app.workspace import active_job, principal, workspace_id

log = logging.getLogger(__name__)
evidence: ContextVar[list] = ContextVar("evidence", default=[])
provider_response: ContextVar[dict | None] = ContextVar("provider_response", default=None)


@dataclass
class Meter:
    max_calls: int
    max_tokens: int
    max_cost: float | None = None
    prices: dict = field(default_factory=dict)
    cost: float = 0
    reserved_cost: float = 0
    calls: int = 0
    tokens: int = 0
    reserved: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reserve(self, tokens, input_size, output_size, model, demo=False):
        rates = self.prices.get(model)
        estimate = 0.0 if demo else (input_size * rates[0] + output_size * rates[1]) / 1_000_000 if rates else None
        with self.lock:
            if self.calls >= self.max_calls or self.tokens + self.reserved + tokens > self.max_tokens:
                raise RuntimeError("Workspace AI run budget reached")
            if self.max_cost is not None and (estimate is None or self.cost + self.reserved_cost + estimate > self.max_cost):
                raise RuntimeError("Text-model spend limit reached or pricing is missing for this model")
            self.calls += 1; self.reserved += tokens
            self.reserved_cost += estimate or 0
        return estimate

    def settle(self, allowance, used, reserved_cost, actual_cost):
        with self.lock:
            self.reserved -= allowance
            self.reserved_cost -= reserved_cost or 0
            self.cost += actual_cost if actual_cost is not None else reserved_cost or 0
            self.tokens += used if used is not None else allowance


meter: ContextVar[Meter | None] = ContextVar("call_meter", default=None)


def make_meter(identity):
    with SessionLocal() as db:
        row = db.get(Workspace, identity)
        return Meter(row.call_limit_per_job, row.token_limit_per_job, max_cost=row.max_llm_cost_per_job, prices=row.llm_prices)


def record_response(response, model):
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "prompt_tokens", getattr(usage, "input_tokens", None))
    if input_tokens is not None:
        input_tokens += (getattr(usage, "cache_creation_input_tokens", 0) or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
    provider_response.set({**(provider_response.get() or {}), "model": getattr(response, "model", None) or model,
        "request_id": getattr(response, "_request_id", None) or getattr(response, "id", None),
        "input_tokens": input_tokens,
        "output_tokens": getattr(usage, "completion_tokens", getattr(usage, "output_tokens", None))})


def instrument(function):
    @wraps(function)
    def call(self, *, system, prompt, schema, images=None):
        if principal.get() is None or active_job.get() is None:
            return function(self, system=system, prompt=prompt, schema=schema, images=images)
        current = meter.get()
        if images and current and current.max_cost is not None and "Demo" not in type(self).__name__:
            raise RuntimeError("Image-based QA needs manual review because its input cost cannot be reserved under this text-model spend limit")
        input_size = len((system + prompt + json.dumps(schema.model_json_schema(), ensure_ascii=False)).encode()) + 1024
        allowance = input_size + self.max_tokens
        reserved_cost = current.reserve(allowance, input_size, self.max_tokens, self.model, "Demo" in type(self).__name__) if current else None
        started = time.monotonic()
        response_token = provider_response.set(None)
        code = None
        try:
            return function(self, system=system, prompt=prompt, schema=schema, images=images)
        except Exception as error:
            code = type(error).__name__
            raise
        finally:
            response = provider_response.get() or {}
            used = response.get("input_tokens")
            output = response.get("output_tokens")
            rates = current.prices.get(response.get("model", self.model)) if current else None
            cost = 0.0 if "Demo" in type(self).__name__ else (used * rates[0] + output * rates[1]) / 1_000_000 if rates and used is not None and output is not None else None
            if current:
                current.settle(allowance, used + output if used is not None and output is not None else None, reserved_cost, cost)
            try:
                with SessionLocal(info={"workspace_id": workspace_id()}) as db:
                    db.add(AICall(job_id=active_job.get(), provider=type(self).__name__, model=response.get("model", self.model),
                        prompt_version=hashlib.sha256((system + schema.model_json_schema().__repr__()).encode()).hexdigest(), schema_name=schema.__name__,
                        request_id=response.get("request_id"), input_tokens=used, output_tokens=output,
                        duration_ms=round((time.monotonic()-started)*1000), status="failed" if code else "succeeded", error_code=code,
                        evidence=evidence.get()[-40:], attempts=response.get("attempts", 1), estimated_cost_usd=cost))
                    db.commit()
            except Exception:
                log.exception("could not persist AI accounting job_id=%s", active_job.get())
            provider_response.reset(response_token)
    return call
