# Linux System Health Checker

A Python system monitoring tool built as part of my beginner DevOps learning roadmap.
It takes one CPU, memory, disk and uptime snapshot, classifies resource usage, and
optionally sends incident events to an n8n webhook.

**Baseline:** Python 3.12, Ubuntu 24.04 LTS, psutil 7.2.2 and requests 2.34.2.

## What this demonstrates

- Linux resource monitoring with hostname, operating system and kernel details.
- A complete JSON report for automation, alongside readable terminal output.
- Configurable warning/critical thresholds with input validation.
- Exit codes that shell scripts and schedulers can act on.
- WAT (UTC+1) timestamps and optional rotating operational logs.
- n8n incident delivery with a timeout and explicit failure reporting.
- Automated tests and GitHub Actions CI on Ubuntu 24.04 / Python 3.12.

## Install on Ubuntu

From your existing repository directory:

```bash
python3 --version
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python health_check.py --no-webhook
```

If Ubuntu reports that venv is unavailable, install `python3-venv` using apt first.
Dependencies are installed in `.venv`, not into the system Python.

## Your first practical task: trigger a safe warning

A threshold is the point at which a reading needs attention. Lowering a threshold
lets you test the warning path without filling your disk or stressing your CPU.

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
python health_check.py --format json --disk-warning 0 --disk-critical 100 --no-webhook
check_code=$?
echo "Exit code: $check_code"
```

Find `metrics.disk.status`, `incidents`, and `timestamp` in the output. Disk should
be WARNING when usage is below 100%; exit code is 1 unless another metric is
CRITICAL (then 2). The `--no-webhook` flag prevents this exercise sending alerts.
These overrides apply only to this run; they do not change the defaults.

**Explain back:** Why did the disk warn when it was not full? Which incident field
would your n8n Switch node use to choose warning versus critical?

## Options and defaults

```bash
python health_check.py --help
python health_check.py --format json --no-webhook > report.json
python -m json.tool report.json
python health_check.py --cpu-warning 60 --cpu-critical 85 --no-webhook
python health_check.py --log-file health.log --no-webhook
python health_check.py --disk-path /home --no-webhook
```

| Metric | Warning at or above | Critical at or above |
| --- | ---: | ---: |
| CPU | 70% | 90% |
| Memory | 75% | 90% |
| Disk | 80% | 90% |

Each metric accepts `--<metric>-warning` and `--<metric>-critical`.
Thresholds must satisfy `0 <= warning < critical <= 100`. Classification uses the
unrounded reading; displayed values are rounded to one decimal place.
Disk path selects a filesystem to measure, not the size of that directory.

| Exit code | Meaning |
| --- | --- |
| 0 | All monitored metrics healthy |
| 1 | At least one warning, no critical metric |
| 2 | At least one critical metric; also used by argparse for invalid arguments |
| 3 | Collection/log setup failed, or a configured webhook delivery failed |

**Behavior change:** warning/critical runs now return nonzero exit codes.
Existing shell automation using `set -e` must deliberately handle these codes.
For invalid arguments, stderr explains the error and no report is emitted.
For webhook failures, the report still describes resource health; exit 3 indicates
that delivery failed. An unset webhook URL is optional, not an execution failure.

## JSON and logging explained

JSON is a labelled data format that another program can read without guessing
where the CPU number appears in a sentence. The report includes `schema_version`,
`timestamp`, hostname/OS/kernel, uptime in seconds, overall status, metrics and
incidents. Memory/disk capacities use bytes; text output displays GiB.

Standard output carries the report. Standard error carries operational logs, so
`> report.json` produces valid JSON. Timestamps include `+01:00` (WAT).
`--log-file` also writes logs to a file, rotating at approximately 1 MB and keeping
three backups. Its parent directory must already exist. Logs record check status
and delivery results, not a history of every metric reading.

## Existing n8n integration

Set `N8N_WEBHOOK_URL` in your shell to your workflow's webhook URL, then run:

```bash
python health_check.py
```

Never commit the URL. `.env` is ignored by Git but is **not automatically loaded**.
Each warning/critical metric sends the existing five-field incident contract:

```json
{
  "hostname": "ubuntu-vm",
  "metric": "disk",
  "value": 92.4,
  "threshold": 90,
  "severity": "critical"
}
```

Requests have a five-second timeout. Failures are logged without printing the
webhook URL, and no automatic retry occurs. `--no-webhook` always disables delivery.
Tests mock HTTP calls: they never contact n8n.

## Tests and continuous integration

```bash
python -m unittest discover -s tests -v
```

Tests check exact threshold boundaries, incident compatibility, JSON/exit codes,
invalid configuration, resource errors, log output and webhook failure handling.
They substitute predictable readings for real CPU/disk values so results do not
change with machine load. No additional test dependency is needed.

GitHub Actions is the robot that runs these tests whenever code is pushed or a
pull request changes. `.github/workflows/ci.yml` installs dependencies, runs tests,
and checks that a real no-webhook run produces valid JSON. It does not require
secrets or contact your n8n instance. Check the Actions tab for the actual result.

## Project structure

```text
system-health-checker/
├── .github/workflows/ci.yml
├── tests/test_health_check.py
├── health_check.py
├── requirements.txt
├── README.md
└── .gitignore
```

## Prioritized next milestones

1. **Understand this change:** complete the warning exercise and explain the JSON,
   thresholds, exit code and passing tests. This is the highest-value first step.
2. **Schedule on Ubuntu:** use a systemd timer, handle exit codes, and document a
   real warning-to-n8n demonstration. Add deduplication before frequent alerts.
3. **Docker packaging:** package a non-root Python 3.12 image and test it in CI.
   Define the monitoring scope first: containers can expose a mix of host and
   container resource views; do not present those readings as complete host or
   container-limit monitoring. Native Ubuntu execution is the current target.
4. **Operational improvements:** configurable sampling, alert cooldown/recovery
   events, then metric history and a dashboard once the alert lifecycle works.

This is a one-shot learning tool, not a monitoring daemon. CPU is sampled for one
second; brief spikes may trigger incidents. Repeated runs may send duplicate
alerts. It does not monitor services, network health, multiple mounts, or Docker
cgroup limits. A single run is not evidence of long-term system reliability.
