import argparse
from datetime import datetime, timedelta, timezone
import logging
from logging.handlers import RotatingFileHandler
import json
import os
import platform
import shutil
import socket
import sys
import time

import psutil
import requests

LOGGER = logging.getLogger(__name__)
WAT = timezone(timedelta(hours=1), name="WAT")

CPU_WARNING = 70
CPU_CRITICAL = 90

MEMORY_WARNING = 75
MEMORY_CRITICAL = 90

DISK_WARNING = 80
DISK_CRITICAL = 90


def get_status(value, warning_threshold, critical_threshold):
    """Return the health status for a metric."""
    if value >= critical_threshold:
        return "CRITICAL"
    elif value >= warning_threshold:
        return "WARNING"
    else:
        return "HEALTHY"

def create_incident(hostname, metric, value, threshold, severity):
    """Create a structured incident event."""
    return {
        "hostname": hostname,
        "metric": metric,
        "value": round(value, 1),
        "threshold": threshold,
        "severity": severity.lower(),
    }

def send_incident(incident):
    """Send an incident event to the configured n8n webhook."""
    webhook_url = os.getenv("N8N_WEBHOOK_URL")

    if not webhook_url:
        LOGGER.info("Webhook delivery skipped: N8N_WEBHOOK_URL is not set.")
        return False

    try:
        response = requests.post(
            webhook_url,
            json=incident,
            timeout=5,
        )
        response.raise_for_status()

        LOGGER.info(
            f"Webhook delivered successfully: "
            f"{incident['metric']} ({incident['severity']})"
        )
        return True

    except requests.RequestException as error:
        # Request exceptions can contain a secret webhook URL; log only the type.
        LOGGER.error("Webhook delivery failed (%s)", type(error).__name__)
        return False

def evaluate_metric(
    hostname,
    metric,
    value,
    warning_threshold,
    critical_threshold,
):
    """Evaluate a metric and return its status and incident event."""
    status = get_status(
        value,
        warning_threshold,
        critical_threshold,
    )

    incident = None

    if status == "WARNING":
        incident = create_incident(
            hostname,
            metric,
            value,
            warning_threshold,
            status,
        )

    elif status == "CRITICAL":
        incident = create_incident(
            hostname,
            metric,
            value,
            critical_threshold,
            status,
        )

    return status, incident

def get_uptime():
    """Return system uptime as days, hours, and minutes."""
    uptime_seconds = time.time() - psutil.boot_time()

    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return days, hours, minutes


DEFAULT_THRESHOLDS = {
    "cpu": (CPU_WARNING, CPU_CRITICAL),
    "memory": (MEMORY_WARNING, MEMORY_CRITICAL),
    "disk": (DISK_WARNING, DISK_CRITICAL),
}
EXIT_CODES = {"HEALTHY": 0, "WARNING": 1, "CRITICAL": 2}


class WATFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return datetime.fromtimestamp(record.created, WAT).isoformat(timespec="seconds")


def configure_logging(log_file=None):
    """Keep operational messages off stdout so JSON stays machine-readable."""
    for handler in LOGGER.handlers[:]:
        handler.close()
        LOGGER.removeHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False
    handlers = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3))
    for handler in handlers:
        handler.setFormatter(WATFormatter("%(asctime)s %(levelname)s %(message)s"))
        LOGGER.addHandler(handler)


def collect_report(thresholds, disk_path="/"):
    """Take one sample. Keep collection separate from output and delivery."""
    hostname = socket.gethostname()
    cpu = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = shutil.disk_usage(disk_path)
    values = {"cpu": cpu, "memory": memory.percent,
              "disk": disk.used / disk.total * 100}
    metrics, incidents = {}, []
    for metric, value in values.items():
        warning, critical = thresholds[metric]
        status, incident = evaluate_metric(hostname, metric, value, warning, critical)
        metrics[metric] = {"percent": round(value, 1), "status": status,
                           "warning_threshold": warning, "critical_threshold": critical}
        if incident:
            incidents.append(incident)
    metrics["memory"].update(total_bytes=memory.total, used_bytes=memory.used,
                             available_bytes=memory.available)
    metrics["disk"].update(path=disk_path, total_bytes=disk.total,
                           used_bytes=disk.used, free_bytes=disk.free)
    return {
        "schema_version": 1,
        "timestamp": datetime.now(WAT).isoformat(timespec="seconds"),
        "hostname": hostname,
        "operating_system": platform.system(),
        "kernel": platform.release(),
        "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        "status": max((m["status"] for m in metrics.values()), key=EXIT_CODES.get),
        "metrics": metrics,
        "incidents": incidents,
    }


def format_text(report):
    lines = ["LINUX SYSTEM HEALTH CHECK", f"Time (WAT): {report['timestamp']}",
             f"Hostname: {report['hostname']}",
             f"Operating System: {report['operating_system']}",
             f"Kernel: {report['kernel']}", f"Overall status: {report['status']}"]
    for name, metric in report["metrics"].items():
        lines.append(f"{name.upper()}: {metric['percent']:.1f}% ({metric['status']})")
        for field in ("total_bytes", "used_bytes", "available_bytes", "free_bytes"):
            if field in metric:
                lines.append(f"  {field.removesuffix('_bytes')}: {metric[field] / 1024**3:.2f} GiB")
    days, remainder = divmod(report["uptime_seconds"], 86400)
    hours, remainder = divmod(remainder, 3600)
    lines.append(f"Uptime: {days} days, {hours} hours, {remainder // 60} minutes")
    return "\n".join(lines)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Check Linux system health once.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--disk-path", default="/")
    parser.add_argument("--log-file", help="Optional rotating operational log; parent directory must exist")
    parser.add_argument("--no-webhook", action="store_true", help="Do not send incidents to n8n")
    for metric, (warning, critical) in DEFAULT_THRESHOLDS.items():
        parser.add_argument(f"--{metric}-warning", type=float, default=warning)
        parser.add_argument(f"--{metric}-critical", type=float, default=critical)
    args = parser.parse_args(argv)
    for metric in DEFAULT_THRESHOLDS:
        warning = getattr(args, f"{metric}_warning")
        critical = getattr(args, f"{metric}_critical")
        if not 0 <= warning < critical <= 100:
            parser.error(f"{metric} thresholds must satisfy 0 <= warning < critical <= 100")
    return args


def main(argv=None):
    args = parse_args(argv)
    thresholds = {metric: (getattr(args, f"{metric}_warning"),
                           getattr(args, f"{metric}_critical"))
                  for metric in DEFAULT_THRESHOLDS}
    try:
        configure_logging(args.log_file)
        report = collect_report(thresholds, args.disk_path)
    except (OSError, psutil.Error) as error:
        print(f"Health check failed ({type(error).__name__}). Check disk path and log permissions.",
              file=sys.stderr)
        return 3
    print(json.dumps(report, indent=2) if args.format == "json" else format_text(report))
    LOGGER.info("Health check completed: %s", report["status"])
    delivery_failed = False
    if not args.no_webhook and os.getenv("N8N_WEBHOOK_URL"):
        for incident in report["incidents"]:
            if not send_incident(incident):
                delivery_failed = True
    return 3 if delivery_failed else EXIT_CODES[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
