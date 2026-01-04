"""
OpenTelemetry integration for fastapi-crons.

This module provides optional OpenTelemetry tracing and metrics integration
for cron job monitoring and observability.

Note: This module requires the opentelemetry-api and opentelemetry-sdk packages.
Install with: pip install fastapi-crons[otel]
"""
import logging
from typing import Any

logger = logging.getLogger("fastapi_cron.telemetry")

# Check for OpenTelemetry availability
try:
    from opentelemetry import metrics, trace
    from opentelemetry.trace import SpanKind, Status, StatusCode
    OTEL_AVAILABLE = True
except ImportError:
    OTEL_AVAILABLE = False
    trace = None
    metrics = None


class OpenTelemetryHooks:
    """
    OpenTelemetry integration hooks for cron jobs.

    This class provides before_run, after_run, and on_error hooks that
    automatically create spans and record metrics for job executions.

    Example:
        >>> from fastapi_crons import Crons
        >>> from fastapi_crons.telemetry import OpenTelemetryHooks
        >>>
        >>> # Initialize OpenTelemetry (your setup code)
        >>> # ...
        >>>
        >>> crons = Crons(app)
        >>> otel_hooks = OpenTelemetryHooks(service_name="my-service")
        >>>
        >>> # Add hooks globally to all jobs
        >>> crons.add_before_run_hook(otel_hooks.before_run)
        >>> crons.add_after_run_hook(otel_hooks.after_run)
        >>> crons.add_on_error_hook(otel_hooks.on_error)
    """

    def __init__(
        self,
        service_name: str = "fastapi-crons",
        tracer_name: str | None = None,
        meter_name: str | None = None,
        record_metrics: bool = True,
    ):
        """
        Initialize OpenTelemetry hooks.

        Args:
            service_name: Name of the service for telemetry
            tracer_name: Custom tracer name (defaults to service_name)
            meter_name: Custom meter name (defaults to service_name)
            record_metrics: Whether to record metrics in addition to traces
        """
        if not OTEL_AVAILABLE:
            logger.warning(
                "OpenTelemetry packages not installed. "
                "Install with: pip install fastapi-crons[otel]"
            )
            self._tracer = None
            self._meter = None
            self._job_runs_counter = None
            self._job_duration_histogram = None
            self._job_failures_counter = None
            return

        self.service_name = service_name
        tracer_name = tracer_name or service_name
        meter_name = meter_name or service_name

        # Initialize tracer
        self._tracer = trace.get_tracer(tracer_name)

        # Initialize metrics if enabled
        if record_metrics:
            self._meter = metrics.get_meter(meter_name)

            # Create metrics instruments
            self._job_runs_counter = self._meter.create_counter(
                name="cron_job_runs_total",
                description="Total number of cron job runs",
                unit="1",
            )

            self._job_duration_histogram = self._meter.create_histogram(
                name="cron_job_duration_seconds",
                description="Duration of cron job executions",
                unit="s",
            )

            self._job_failures_counter = self._meter.create_counter(
                name="cron_job_failures_total",
                description="Total number of cron job failures",
                unit="1",
            )

            self._job_retries_counter = self._meter.create_counter(
                name="cron_job_retries_total",
                description="Total number of cron job retry attempts",
                unit="1",
            )

            self._job_timeouts_counter = self._meter.create_counter(
                name="cron_job_timeouts_total",
                description="Total number of cron job timeouts",
                unit="1",
            )
        else:
            self._meter = None
            self._job_runs_counter = None
            self._job_duration_histogram = None
            self._job_failures_counter = None
            self._job_retries_counter = None
            self._job_timeouts_counter = None

        # Store active spans for correlation
        self._active_spans: dict[str, Any] = {}

    def before_run(self, job_name: str, context: dict[str, Any]) -> None:
        """Hook executed before job runs - starts a span."""
        if not OTEL_AVAILABLE or self._tracer is None:
            return

        # Create span for job execution
        span = self._tracer.start_span(
            name=f"cron.job.{job_name}",
            kind=SpanKind.INTERNAL,
        )

        # Set span attributes
        span.set_attribute("cron.job.name", job_name)
        span.set_attribute("cron.job.expression", context.get("expr", ""))
        span.set_attribute("cron.job.tags", str(context.get("tags", [])))
        span.set_attribute("cron.job.scheduled_time", context.get("scheduled_time", ""))
        span.set_attribute("cron.job.actual_time", context.get("actual_time", ""))
        span.set_attribute("cron.instance_id", context.get("instance_id", ""))

        if context.get("manual_trigger"):
            span.set_attribute("cron.job.manual_trigger", True)

        # Store span for later
        self._active_spans[job_name] = span

        # Record job run metric
        if self._job_runs_counter is not None:
            tags = context.get("tags", [])
            self._job_runs_counter.add(
                1,
                attributes={
                    "job_name": job_name,
                    "tags": ",".join(tags) if tags else "",
                },
            )

    def after_run(self, job_name: str, context: dict[str, Any]) -> None:
        """Hook executed after job completes successfully - ends span with success."""
        if not OTEL_AVAILABLE:
            return

        span = self._active_spans.pop(job_name, None)
        if span is None:
            return

        try:
            # Add execution details
            span.set_attribute("cron.job.duration", context.get("duration", 0))
            span.set_attribute("cron.job.success", True)

            attempts = context.get("attempts", 1)
            span.set_attribute("cron.job.attempts", attempts)

            # Set success status
            span.set_status(Status(StatusCode.OK))

            # Record duration metric
            if self._job_duration_histogram is not None:
                duration = context.get("duration", 0)
                tags = context.get("tags", [])
                self._job_duration_histogram.record(
                    duration,
                    attributes={
                        "job_name": job_name,
                        "success": "true",
                        "tags": ",".join(tags) if tags else "",
                    },
                )

            # Record retries if there were any
            if attempts > 1 and self._job_retries_counter is not None:
                self._job_retries_counter.add(
                    attempts - 1,
                    attributes={"job_name": job_name},
                )

        finally:
            span.end()

    def on_error(self, job_name: str, context: dict[str, Any]) -> None:
        """Hook executed when job fails - ends span with error."""
        if not OTEL_AVAILABLE:
            return

        span = self._active_spans.pop(job_name, None)
        if span is None:
            return

        try:
            error = context.get("error", "Unknown error")

            # Add execution details
            span.set_attribute("cron.job.duration", context.get("duration", 0))
            span.set_attribute("cron.job.success", False)
            span.set_attribute("cron.job.error", error)

            attempts = context.get("attempts", 1)
            span.set_attribute("cron.job.attempts", attempts)

            is_timeout = context.get("is_timeout", False)
            span.set_attribute("cron.job.is_timeout", is_timeout)

            # Record exception and set error status
            span.record_exception(Exception(error))
            span.set_status(Status(StatusCode.ERROR, error))

            # Record metrics
            if self._job_duration_histogram is not None:
                duration = context.get("duration", 0)
                tags = context.get("tags", [])
                self._job_duration_histogram.record(
                    duration,
                    attributes={
                        "job_name": job_name,
                        "success": "false",
                        "tags": ",".join(tags) if tags else "",
                    },
                )

            if self._job_failures_counter is not None:
                tags = context.get("tags", [])
                self._job_failures_counter.add(
                    1,
                    attributes={
                        "job_name": job_name,
                        "error_type": type(error).__name__ if isinstance(error, Exception) else "str",
                        "tags": ",".join(tags) if tags else "",
                    },
                )

            # Record retries
            if attempts > 1 and self._job_retries_counter is not None:
                self._job_retries_counter.add(
                    attempts - 1,
                    attributes={"job_name": job_name},
                )

            # Record timeout
            if is_timeout and self._job_timeouts_counter is not None:
                self._job_timeouts_counter.add(
                    1,
                    attributes={"job_name": job_name},
                )

        finally:
            span.end()


def is_otel_available() -> bool:
    """Check if OpenTelemetry packages are available."""
    return OTEL_AVAILABLE


def get_recommended_otel_setup() -> str:
    """Return recommended OpenTelemetry setup code."""
    return '''
# Recommended OpenTelemetry setup for fastapi-crons

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

# Setup tracing
trace.set_tracer_provider(TracerProvider())
otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317")
trace.get_tracer_provider().add_span_processor(BatchSpanProcessor(otlp_exporter))

# Setup metrics
reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint="http://localhost:4317"))
metrics.set_meter_provider(MeterProvider(metric_readers=[reader]))

# Now use OpenTelemetryHooks
from fastapi_crons.telemetry import OpenTelemetryHooks

otel_hooks = OpenTelemetryHooks(service_name="my-cron-service")
crons.add_before_run_hook(otel_hooks.before_run)
crons.add_after_run_hook(otel_hooks.after_run)
crons.add_on_error_hook(otel_hooks.on_error)
'''
