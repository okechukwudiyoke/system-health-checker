import platform
import shutil
import socket


def get_uptime():
    with open("/proc/uptime", "r") as file:
        uptime_seconds = float(file.read().split()[0])

    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return days, hours, minutes


def main():
    hostname = socket.gethostname()
    os_name = platform.system()
    os_version = platform.release()

    total, used, free = shutil.disk_usage("/")

    days, hours, minutes = get_uptime()

    print("=" * 50)
    print("        LINUX SYSTEM HEALTH CHECK")
    print("=" * 50)

    print(f"Hostname: {hostname}")
    print(f"Operating System: {os_name}")
    print(f"Kernel: {os_version}")

    print("\nDisk:")
    print(f"Total: {total / (1024**3):.2f} GB")
    print(f"Used:  {used / (1024**3):.2f} GB")
    print(f"Free:  {free / (1024**3):.2f} GB")

    print("\nUptime:")
    print(f"{days} days, {hours} hours, {minutes} minutes")

    print("=" * 50)


if __name__ == "__main__":
    main()
