import socket
import subprocess

PORT = 8000
RESULT_FILE = "port_check_result.txt"


def is_port_free(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
        s.close()
        return True
    except OSError:
        s.close()
        return False


def find_pid(port):
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="replace")
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line.upper():
                parts = line.split()
                return parts[-1]
    except Exception as e:
        return f"ERR_{e}"
    return None


def kill_pid(pid):
    try:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                       check=True, capture_output=True, text=True)
        return True
    except Exception as e:
        return f"ERR_{e}"


if is_port_free(PORT):
    msg = "FREE"
else:
    pid = find_pid(PORT)
    if pid and not str(pid).startswith("ERR_"):
        ok = kill_pid(pid)
        if ok is True:
            msg = f"KILLED_PID_{pid}"
        else:
            msg = f"IN_USE_PID_{pid}_KILL_FAILED_{ok}"
    else:
        msg = f"IN_USE_NO_PID_{pid}"

with open(RESULT_FILE, "w") as f:
    f.write(msg + "\n")
