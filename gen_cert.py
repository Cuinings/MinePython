#!/usr/bin/env python3
"""生成自签 SSL 证书，用于在本项目上启用 HTTPS（WebUSB 需要安全上下文）。

用法:
    python gen_cert.py
按提示输入服务器局域网 IP（如 192.168.0.10），会在 ./ssl/ 下生成 cert.pem / key.pem。
"""
import os
import sys
import socket
import ipaddress
import datetime
import subprocess

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def get_all_ips():
    """Collect all non-loopback IPv4 addresses on this machine (LAN / VPN / ...).

    Uses two strategies so VPN-assigned addresses (e.g. 10.x from a corporate
    tunnel) are captured even when they are not returned by gethostname().
    """
    ips = set()
    # 1) hostname-based resolution
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if ":" not in ip:  # IPv4 only
                ips.add(ip)
    except Exception:
        pass
    # 2) Windows: enumerate every adapter via PowerShell (catches VPN IPs)
    try:
        proc = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
                "Where-Object { $_.IPAddress -ne '127.0.0.1' }).IPAddress",
            ],
            capture_output=True, text=True, timeout=20,
        )
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line and "." in line:
                ips.add(line)
    except Exception:
        pass
    return sorted(ips)


HERE = os.path.dirname(os.path.abspath(__file__))
SSL_DIR = os.path.join(HERE, "ssl")
os.makedirs(SSL_DIR, exist_ok=True)

# Accept one or more IPs as CLI args (comma-separated) for non-interactive use.
# If no args are given, auto-detect all LAN IPs (batch-friendly, no prompt).
if len(sys.argv) > 1:
    raw = sys.argv[1]
    cli_ips = [p.strip() for p in raw.split(",") if p.strip()]
else:
    print(f"未指定 IP，自动检测所有本机地址（默认网关探测为 {get_local_ip()}）...")
    cli_ips = []

# Build the SAN list: localhost + 127.0.0.1 + every detected LAN IP + any CLI IP.
san_ips = set()
san_ips.add(ipaddress.ip_address("127.0.0.1"))
for lan in get_all_ips():
    try:
        san_ips.add(ipaddress.ip_address(lan))
    except ValueError:
        pass
for ip in cli_ips:
    try:
        san_ips.add(ipaddress.ip_address(ip))
    except ValueError:
        print(f"跳过无效 IP: {ip}")

if not san_ips:
    san_ips.add(ipaddress.ip_address("127.0.0.1"))

# CN = first usable identity (prefer a LAN IP over loopback for readability).
cn = next((str(i) for i in san_ips if str(i) != "127.0.0.1"), "localhost")

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, cn),
])

san_list = [x509.DNSName("localhost")] + [x509.IPAddress(i) for i in san_ips]

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(
        x509.SubjectAlternativeName(san_list),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

cert_pem = cert.public_bytes(serialization.Encoding.PEM)
key_pem = key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL,
    serialization.NoEncryption(),
)

cert_path = os.path.join(SSL_DIR, "cert.pem")
key_path = os.path.join(SSL_DIR, "key.pem")
with open(cert_path, "wb") as f:
    f.write(cert_pem)
with open(key_path, "wb") as f:
    f.write(key_pem)

print("\n✅ 证书已生成：")
print(f"  cert: {cert_path}")
print(f"  key : {key_path}")
print("\n证书包含的地址 (SAN) —— 浏览器必须用其中任意一个访问才不会被拒：")
print("  - localhost (DNS)")
for i in sorted(san_ips, key=str):
    print("  - " + str(i))
print("\n下一步（二选一）：")
print("  Docker: 在 .env 写 SSL_CERTFILE=/app/ssl/cert.pem 和 SSL_KEYFILE=/app/ssl/key.pem，再 docker compose up -d --build")
print(f"  主机直跑: set SSL_CERTFILE={cert_path}  && set SSL_KEYFILE={key_path} 后启动 server.py")
print("\n⚠️ 手机【不要】打开此网页；网页要在连接手机的电脑的 Chrome/Edge 打开，")
print("   并用上面 SAN 里的某个 IP（或 localhost）访问，例如 https://10.67.116.6:8000/files.html")
