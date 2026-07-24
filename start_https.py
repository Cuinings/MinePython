#!/usr/bin/env python3
"""Run_https equivalent in Python — avoids cmd batch parsing pitfalls.

Usage:
    python start_https.py
"""

import os
import sys
import subprocess
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

PYTHON = os.path.join(HERE, ".venv313", "Scripts", "python.exe")
if not os.path.isfile(PYTHON):
    PYTHON = os.path.join(HERE, ".venv", "Scripts", "python.exe")
if not os.path.isfile(PYTHON):
    PYTHON = "python"

print("=" * 60)
print(" MinePython HTTPS startup")
print("=" * 60)

# 1) Verify cryptography
print("[1/5] Checking cryptography...")
p = subprocess.run([PYTHON, "-c", "import cryptography"], capture_output=True)
if p.returncode != 0:
    print("[ERROR] cryptography not installed.")
    print("[ERROR] Run: pip install cryptography")
    sys.exit(1)
print("[1/5] cryptography OK")

# 2) Generate cert if missing
CERT = os.path.join(HERE, "ssl", "cert.pem")
if not os.path.isfile(CERT):
    print("[2/5] Generating self-signed cert...")
    p = subprocess.run([PYTHON, "gen_cert.py"])
    if p.returncode != 0:
        print("[ERROR] gen_cert.py failed.")
        sys.exit(1)
else:
    print("[2/5] Cert already exists, reusing.")

# 3) Set env
os.environ["SSL_CERTFILE"] = CERT
os.environ["SSL_KEYFILE"] = os.path.join(HERE, "ssl", "key.pem")
print("[3/5] SSL_CERTFILE =", os.environ["SSL_CERTFILE"])

# 4) Check ADB bundle (ya-webadb 2.x localized build)
BUNDLE = os.path.join(HERE, "static", "js", "webadb2.bundle.js")
if not os.path.isfile(BUNDLE):
    print("[WARN] webadb2.bundle.js not found.")
    print("[WARN] Run: python download_webadb2.py")
    sys.exit(1)
print("[4/5] WebUSB ADB 2.x bundle OK (webadb2.bundle.js)")

# 5) Kill any process on port 8000
print("[5/5] Checking port 8000...")
try:
    out = subprocess.check_output(
        ["netstat", "-ano"], text=True, errors="replace", timeout=10
    )
    for line in out.splitlines():
        if ":8000" in line and "LISTENING" in line:
            parts = line.strip().split()
            pid = parts[-1]
            print(f"  Killing PID {pid} on port 8000...")
            subprocess.run(["taskkill", "/PID", pid, "/F"],
                           capture_output=True)
    time.sleep(1)
except Exception as e:
    print(f"  (port check skipped: {e})")

# 6) Start server
print("=" * 60)
print(" Starting server on HTTPS :8000...")
print("=" * 60)
os.execv(PYTHON, [PYTHON, "server.py"])
