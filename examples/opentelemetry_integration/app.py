"""
OpenTelemetry Integration Example for FastAPI-Crons

This example demonstrates:
- Tracing cron job executions with OpenTelemetry
- Recording job metrics (runs, successes, failures, duration)
- Integrating with observability backends (Jaeger, Prometheus, etc.)

Requirements:
    pip install fastapi-crons[otel]
    pip install opentelemetry-exporter-otlp-proto-grpc  # For OTLP export

    # Optional: Run Jaeger for trace visualization
    docker run -d --name jaeger \
      -p 16686:16686 \
      -p 4317:4317 \
      jaegertracing/all-in-one:latest

Run with:
    uvicorn app:app --reload

Then visit:
    - http://localhost:8000/crons - View jobs
    - http://localhost:16686 - Jaeger UI to view traces
"""

import asyncio
import logging
import random
from datetime import datetime

from fastapi import FastAPI

from fastapi_crons import (
    Crons,
    get_cron_router,
    is_otel_available,
)

# =============================================================================
# OPENTELEMETRY SETUP
# =============================================================================

# Check if OpenTelemetry is available
if is_otel_available():
    from opentelemetry import metrics, trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        ConsoleMetricExporter,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    from fastapi_crons.telemetry import OpenTelemetryHooks

    # Try to import OTLP exporter (optional)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,  # noqa: F401
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False

    # Create resource with service name
    resource = Resource.create({
        "service.name": "fastapi-crons-example",
        "service.version": "1.0.0",
        "deployment.environment": "development",
    })

    # Setup tracing
    tracer_provider = TracerProvider(resource=resource)

    # Add span processors
    # Console exporter for development (prints to stdout)
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # OTLP exporter for production (sends to Jaeger/OTLP collector)
    if OTLP_AVAILABLE:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
            tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        except Exception as e:
            logging.warning(f"Could not connect to OTLP collector: {e}")

    trace.set_tracer_provider(tracer_provider)

    # Setup metrics
    # Console exporter for development
    metric_reader = PeriodicExportingMetricReader(
        ConsoleMetricExporter(),
        export_interval_millis=30000,  # Export every 30 seconds
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    OTEL_CONFIGURED = True
    logging.info("✅ OpenTelemetry configured successfully")
else:
    OTEL_CONFIGURED = False
    logging.warning(
        "⚠️ OpenTelemetry not available. Install with: pip install fastapi-crons[otel]"
    )


# =============================================================================
# LOGGING SETUP
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    title="FastAPI-Crons OpenTelemetry Example",
    description="Demonstrates OpenTelemetry integration for observability",
)

crons = Crons(app)
app.include_router(get_cron_router(), prefix="/crons", tags=["Cron Jobs"])


# =============================================================================
# OPENTELEMETRY HOOKS
# =============================================================================

if OTEL_CONFIGURED:
    # Create OpenTelemetry hooks
    otel_hooks = OpenTelemetryHooks(
        service_name="fastapi-crons-example",
        tracer_name="cron.jobs",        # Custom tracer name
        meter_name="cron.metrics",       # Custom meter name
        record_metrics=True,             # Enable metrics recording
    )

    # Add hooks to all jobs globally
    # These hooks will:
    # - Create spans for each job execution
    # - Record job run, success, failure counters
    # - Record job duration histogram
    crons.add_before_run_hook(otel_hooks.before_run)
    crons.add_after_run_hook(otel_hooks.after_run)
    crons.add_on_error_hook(otel_hooks.on_error)

    logger.info("📊 OpenTelemetry hooks registered for all jobs")


# =============================================================================
# CRON JOBS
# =============================================================================

@crons.cron("*/1 * * * *", name="traced_job", tags=["traced", "demo"])
async def traced_job():
    """
    Job that is automatically traced by OpenTelemetry.

    The OTel hooks will:
    - Create a span for this job execution
    - Record job attributes (name, tags, expression)
    - Measure execution duration
    - Record success/failure status
    """
    logger.info("Executing traced job...")

    # Simulate some work
    await asyncio.sleep(random.uniform(0.1, 1.0))

    logger.info("Traced job completed!")
    return {"status": "success", "timestamp": datetime.now().isoformat()}


@crons.cron("*/2 * * * *", name="flaky_job", tags=["traced", "flaky"])
async def flaky_job():
    """
    Job that occasionally fails to demonstrate error tracing.

    When this job fails, the OTel hooks will:
    - Record the error in the span
    - Set span status to ERROR
    - Increment the failure counter
    """
    logger.info("Executing flaky job...")

    await asyncio.sleep(random.uniform(0.2, 0.5))

    # Simulate occasional failures
    if random.random() < 0.3:  # 30% failure rate
        raise ValueError("Simulated failure for tracing demo")

    logger.info("Flaky job completed!")
    return "success"


@crons.cron(
    "*/3 * * * *",
    name="slow_traced_job",
    max_retries=2,
    timeout=10.0,
    tags=["traced", "slow"]
)
async def slow_traced_job():
    """
    Slow job with retries to demonstrate retry tracing.

    The traces will show:
    - Number of retry attempts
    - Duration per attempt
    - Final success/failure
    """
    logger.info("Executing slow traced job...")

    delay = random.uniform(2.0, 5.0)
    await asyncio.sleep(delay)

    # Simulate failure on some attempts
    if random.random() < 0.4:
        raise ConnectionError("Simulated connection error")

    logger.info(f"Slow traced job completed in {delay:.2f}s")
    return {"duration": delay}


# =============================================================================
# CUSTOM TRACING (Advanced)
# =============================================================================

if OTEL_CONFIGURED:
    tracer = trace.get_tracer("custom.cron.tracer")

    @crons.cron("*/5 * * * *", name="custom_traced_job", tags=["custom"])
    async def custom_traced_job():
        """
        Job with custom span creation for fine-grained tracing.

        This demonstrates how to add custom spans within your job
        for more detailed observability.
        """
        # The OTel hooks already create a span for the job
        # But you can create child spans for sub-operations

        with tracer.start_as_current_span("fetch_data") as span:
            span.set_attribute("data.source", "external_api")
            await asyncio.sleep(0.5)  # Simulate API call
            span.set_attribute("data.records", 42)

        with tracer.start_as_current_span("process_data") as span:
            span.set_attribute("processing.mode", "batch")
            await asyncio.sleep(0.3)  # Simulate processing
            span.set_attribute("processing.records_processed", 42)

        with tracer.start_as_current_span("save_results") as span:
            span.set_attribute("storage.type", "database")
            await asyncio.sleep(0.2)  # Simulate DB write
            span.set_attribute("storage.records_saved", 42)

        return {"processed": 42}


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
def root():
    """Root endpoint with usage information."""
    return {
        "message": "FastAPI-Crons OpenTelemetry Example",
        "otel_configured": OTEL_CONFIGURED,
        "endpoints": {
            "/crons": "View jobs",
            "/crons/health": "Health check",
            "/otel-status": "OpenTelemetry configuration status",
        },
        "traces": "View traces at http://localhost:16686 (Jaeger UI)",
    }


@app.get("/otel-status")
def otel_status():
    """Get OpenTelemetry configuration status."""
    return {
        "otel_available": is_otel_available(),
        "otel_configured": OTEL_CONFIGURED,
        "note": "Run Jaeger with: docker run -d --name jaeger -p 16686:16686 -p 4317:4317 jaegertracing/all-in-one:latest",
        "installation": "pip install fastapi-crons[otel] opentelemetry-exporter-otlp-proto-grpc",
    }


# =============================================================================
# CONFIGURATION NOTES
# =============================================================================
"""
OPENTELEMETRY METRICS RECORDED:

Counters:
- cron_job_runs_total: Total number of job runs
  Labels: job_name, tags

- cron_job_failures_total: Total number of job failures
  Labels: job_name, error_type, tags

- cron_job_retries_total: Total number of retry attempts
  Labels: job_name

- cron_job_timeouts_total: Total number of timeouts
  Labels: job_name

Histograms:
- cron_job_duration_seconds: Job execution duration
  Labels: job_name, success, tags

SPAN ATTRIBUTES:

- cron.job.name: Job name
- cron.job.expression: Cron expression
- cron.job.tags: Job tags
- cron.job.scheduled_time: When the job was scheduled
- cron.job.actual_time: When it actually started
- cron.instance_id: Instance ID
- cron.job.duration: Execution duration
- cron.job.success: Success/failure
- cron.job.error: Error message (if failed)
- cron.job.attempts: Number of attempts (with retry)
- cron.job.is_timeout: Whether it timed out

RECOMMENDED EXPORTERS:

For Development:
- ConsoleSpanExporter
- ConsoleMetricExporter

For Production:
- OTLPSpanExporter (to Jaeger, Tempo, etc.)
- OTLPMetricExporter (to Prometheus, etc.)
- Or any OpenTelemetry-compatible backend
"""
