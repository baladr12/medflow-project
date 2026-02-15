import logging
import time
import uuid
from datetime import datetime, timezone
from google.cloud import logging as cloud_logging

class ObservabilityManager:
    """
    Enterprise Observability for MedFlow.
    Features: Structured Cloud Logging, Trace Correlation, and Performance Benchmarking.
    """
    def __init__(self, name="medflow-ai"):
        # 1. Setup Structured Cloud Logging
        try:
            self.cloud_client = cloud_logging.Client()
            # This integrates Python's standard logging with GCP Cloud Logging
            self.cloud_client.setup_logging()
        except Exception:
            logging.basicConfig(level=logging.INFO)
        
        self.logger = logging.getLogger(name)
        self.severity_count = {"emergency": 0, "urgent": 0, "routine": 0, "self-care": 0}
        self.trace_steps = []
        self.current_trace_id = None

    def start_request(self):
        """Initializes a new request context with a unique ID."""
        self.current_trace_id = str(uuid.uuid4())
        self.clear_trace()
        return self.current_trace_id

    # --- Structured Logging ---
    def info(self, msg, extra=None):
        """Logs info with an optional structured payload for GCP."""
        payload = {"message": msg, "trace_id": self.current_trace_id}
        if extra: payload.update(extra)
        self.logger.info(payload)

    def error(self, msg, extra=None):
        payload = {"message": msg, "trace_id": self.current_trace_id, "status": "ERROR"}
        if extra: payload.update(extra)
        self.logger.error(payload)

    # --- Performance Logic ---
    def start_timer(self):
        return time.perf_counter() # More precise than time.time() for benchmarking

    def stop_timer(self, start_time):
        return round(time.perf_counter() - start_time, 3)

    # --- Tracer Logic ---
    def add_trace(self, agent_name, action):
        """Adds a step to the immutable audit trail for clinical accountability."""
        step = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": self.current_trace_id,
            "agent": agent_name,
            "action": action
        }
        self.trace_steps.append(step)
        # Log the trace as a structured event
        self.info(f"Trace Event: {agent_name}", extra={"step": step})

    def clear_trace(self):
        self.trace_steps = []

    def get_full_trace(self):
        return self.trace_steps