"""Thin wrapper so domain code can open spans whether or not OpenTelemetry export is enabled."""

import contextlib
import uuid

from opentelemetry import trace

tracer = trace.get_tracer("deploymind")


@contextlib.contextmanager
def span(name: str, **attributes):
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            if v is not None:
                s.set_attribute(k, v if isinstance(v, str | int | float | bool) else str(v))
        yield s


def current_trace_id() -> str:
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.trace_id else uuid.uuid4().hex
