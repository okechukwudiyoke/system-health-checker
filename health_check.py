import json
import platform
import shutil
import socket
import time

import psutil


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


def main():
    hostname = socket.gethostname()
    operating_system = platform.system()
    kernel = platform.release()

    cpu_usage = psutil.cpu_percent(interval=1)

    memory = psutil.virtual_memory()
    memory_usage = memory.percent

    disk = shutil.disk_usage("/")
    disk_usage = (disk.used / disk.total) * 100

    uptime_days, uptime_hours, uptime_minutes = get_uptime()
    cpu_status, cpu_incident = evaluate_metric(
        hostname,
        "cpu",
        cpu_usage,
        CPU_WARNING,
        CPU_CRITICAL,
    )

    memory_status, memory_incident = evaluate_metric(
        hostname,
        "memory",
        memory_usage,
        MEMORY_WARNING,
        MEMORY_CRITICAL,
    )

    disk_status, disk_incident = evaluate_metric(
        hostname,
        "disk",
        disk_usage,
        DISK_WARNING,
        DISK_CRITICAL,
    )

    incidents = [
        incident
        for incident in (
            cpu_incident,
            memory_incident,
            disk_incident,
        )
        if incident is not None
    ]

    print("=" * 55)
    print("             LINUX SYSTEM HEALTH CHECK")
    print("=" * 55)

    print(f"Hostname: {hostname}")
    print(f"Operating System: {operating_system}")
    print(f"Kernel: {kernel}")

    print("\nCPU:")
    print(f"Usage:  {cpu_usage:.1f}%")
    print(f"Status: {cpu_status}")

    print("\nMemory:")
    print(f"Total:     {memory.total / (1024 ** 3):.2f} GB")
    print(f"Used:      {memory.used / (1024 ** 3):.2f} GB")
    print(f"Available: {memory.available / (1024 ** 3):.2f} GB")
    print(f"Usage:     {memory_usage:.1f}%")
    print(f"Status:    {memory_status}")

    print("\nDisk:")
    print(f"Total:  {disk.total / (1024 ** 3):.2f} GB")
    print(f"Used:   {disk.used / (1024 ** 3):.2f} GB")
    print(f"Free:   {disk.free / (1024 ** 3):.2f} GB")
    print(f"Usage:  {disk_usage:.1f}%")
    print(f"Status: {disk_status}")

    print("\nUptime:")
    print(
        f"{uptime_days} days, "
        f"{uptime_hours} hours, "
        f"{uptime_minutes} minutes"
    )


    if incidents:
        print("\nIncident Events:")
        print(json.dumps(incidents, indent=2))

    print("=" * 55)


if __name__ == "__main__":
    main()
