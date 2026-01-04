"""
Pre-built hooks for common use cases like logging, metrics, alerts, and webhooks.
"""
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import aiohttp

# Configure logger
logger = logging.getLogger("fastapi_cron")

# Logging hooks
def log_job_start(job_name: str, context: dict[str, Any]):
    """Log when a job starts."""
    logger.info(f"Job '{job_name}' started at {datetime.now(timezone.utc).isoformat()}")

def log_job_success(job_name: str, context: dict[str, Any]):
    """Log when a job completes successfully."""
    duration = context.get("duration", 0)
    logger.info(f"Job '{job_name}' completed successfully in {duration:.2f}s")

def log_job_error(job_name: str, context: dict[str, Any]):
    """Log when a job fails."""
    error = context.get("error", "Unknown error")
    duration = context.get("duration", 0)
    logger.error(f"Job '{job_name}' failed after {duration:.2f}s: {error}")

# Webhook hooks
async def webhook_notification(url: str, include_context: bool = True):
    """
    Create a hook that sends a webhook notification.

    Args:
        url: The webhook URL to send the notification to
        include_context: Whether to include the full context in the webhook payload

    Returns:
        A hook function that can be registered with add_before_run_hook,
        add_after_run_hook, or add_on_error_hook
    """
    async def hook(job_name: str, context: dict[str, Any]):
        payload = {
            "job_name": job_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "before_run" if "success" not in context else
                          "after_run" if context.get("success") else "on_error"
        }

        if include_context:
            payload["context"] = context

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as response:
                    if response.status >= 400:
                        logger.error(f"Webhook notification failed with status {response.status}")
            except Exception as e:
                logger.error(f"Failed to send webhook notification: {e}")

    return hook

# Metrics hooks
class MetricsCollector:
    """Simple in-memory metrics collector for cron jobs."""

    def __init__(self):
        self.metrics = {
            "job_runs": {},
            "job_durations": {},
            "job_successes": {},
            "job_failures": {}
        }

    def record_job_start(self, job_name: str, context: dict[str, Any]):
        """Record that a job has started."""
        if job_name not in self.metrics["job_runs"]:
            self.metrics["job_runs"][job_name] = 0
        self.metrics["job_runs"][job_name] += 1

    def record_job_success(self, job_name: str, context: dict[str, Any]):
        """Record that a job has completed successfully."""
        duration = context.get("duration", 0)

        if job_name not in self.metrics["job_durations"]:
            self.metrics["job_durations"][job_name] = []
        self.metrics["job_durations"][job_name].append(duration)

        if job_name not in self.metrics["job_successes"]:
            self.metrics["job_successes"][job_name] = 0
        self.metrics["job_successes"][job_name] += 1

    def record_job_failure(self, job_name: str, context: dict[str, Any]):
        """Record that a job has failed."""
        if job_name not in self.metrics["job_failures"]:
            self.metrics["job_failures"][job_name] = 0
        self.metrics["job_failures"][job_name] += 1

    def get_metrics(self):
        """Get all collected metrics."""
        return self.metrics

    def get_job_metrics(self, job_name: str):
        """Get metrics for a specific job."""
        return {
            "runs": self.metrics["job_runs"].get(job_name, 0),
            "successes": self.metrics["job_successes"].get(job_name, 0),
            "failures": self.metrics["job_failures"].get(job_name, 0),
            "durations": self.metrics["job_durations"].get(job_name, []),
            "avg_duration": sum(self.metrics["job_durations"].get(job_name, [0])) /
                           max(len(self.metrics["job_durations"].get(job_name, [1])), 1)
        }

# Create a global metrics collector instance
metrics_collector = MetricsCollector()

# Alert hooks
class AlertManager:
    """Manager for job alerts."""

    def __init__(self, alert_handlers: list[Callable[[str, str, dict[str, Any]], None]] | None = None):
        self.alert_handlers = alert_handlers or []

    def add_handler(self, handler: Callable[[str, str, dict[str, Any]], None]):
        """Add an alert handler."""
        self.alert_handlers.append(handler)

    def trigger_alert(self, job_name: str, alert_type: str, context: dict[str, Any]):
        """Trigger an alert."""
        for handler in self.alert_handlers:
            try:
                handler(job_name, alert_type, context)
            except Exception as e:
                logger.error(f"Alert handler failed: {e}")

# Create a global alert manager instance
alert_manager = AlertManager()

# Example alert handler for logging
def log_alert_handler(job_name: str, alert_type: str, context: dict[str, Any]):
    """Log an alert."""
    logger.warning(f"ALERT: {alert_type} for job '{job_name}': {context.get('error', '')}")

# Add the log alert handler to the alert manager
alert_manager.add_handler(log_alert_handler)

def alert_on_failure(job_name: str, context: dict[str, Any]):
    """Trigger an alert when a job fails."""
    alert_manager.trigger_alert(job_name, "failure", context)

def alert_on_long_duration(threshold_seconds: float):
    """
    Create a hook that triggers an alert when a job takes longer than the threshold.

    Args:
        threshold_seconds: The duration threshold in seconds

    Returns:
        A hook function that can be registered with add_after_run_hook
    """
    def hook(job_name: str, context: dict[str, Any]):
        duration = context.get("duration", 0)
        if duration > threshold_seconds:
            alert_context = {
                **context,
                "alert_reason": f"Job took {duration:.2f}s, which exceeds threshold of {threshold_seconds:.2f}s"
            }
            alert_manager.trigger_alert(job_name, "long_duration", alert_context)

    return hook
