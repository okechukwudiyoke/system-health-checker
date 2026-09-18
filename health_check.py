import platform
import shutil
import socket
import time

import psutil


def get_uptime():
    uptime_seconds = psutil.boot_time()
    current_time = time.time()
    uptime = current_time - uptime_seconds

    days = int(uptime // 86400)
    hours = int((uptime % 86400) // 3600)
    minutes = int((uptime % 3600) // 60)

    return days, hours, minutes


def main():
    hostname = socket.gethostname()
    os_name = platform.system()
    os_version = platform.release()

    # CPU
    cpu_usage = psutil.cpu_percent(interval=1)

    # Memory
    memory = psutil.virtual_memory()

    # Disk
    total, used, free = shutil.disk_usage("/")

    # Uptime
    days, hours, minutes = get_uptime()

    print("=" * 55)
    print("             LINUX SYSTEM HEALTH CHECK")
    print("=" * 55)

    print(f"Hostname: {hostname}")
    print(f"Operating System: {os_name}")
    print(f"Kernel: {os_version}")

    print("\nCPU:")
    print(f"Usage: {cpu_usage}%")

    print("\nMemory:")
    print(f"Total:     {memory.total / (1024**3):.2f} GB")
    print(f"Used:      {memory.used / (1024**3):.2f} GB")
    print(f"Available: {memory.available / (1024**3):.2f} GB")
    print(f"Usage:     {memory.percent}%")

    print("\nDisk:")
    print(f"Total: {total / (1024**3):.2f} GB")
    print(f"Used:  {used / (1024**3):.2f} GB")
    print(f"Free:  {free / (1024**3):.2f} GB")

    print("\nUptime:")
    print(f"{days} days, {hours} hours, {minutes} minutes")

    print("=" * 55)


if __name__ == "__main__":
    main()
