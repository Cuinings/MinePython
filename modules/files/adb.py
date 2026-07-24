# -*- coding: utf-8 -*-
"""ADB 一键安装接口（P-ADB）。

提供两个接口，让用户在 Web UI 上对 APK 文件「一键安装」到已连接的
Android 设备：

* ``GET  /api/adb/devices`` —— 列出当前通过 adb 连接的设备
  （含序列号、型号、授权状态），用于前端选择目标设备。
* ``POST /api/adb/install`` —— 把指定 APK 安装到设备
  （``adb install -r``，自动替换旧版本）。

adb 在服务器的运行主机上执行（与 Web 服务同机），因此需要：
1. 主机已安装 Android SDK Platform-Tools（含 ``adb``）；
2. 目标手机已开启「USB 调试」并与主机相连；
3. 如需自定义 adb 路径，可在 ``.env`` 设置 ``ADB_PATH``。

接口对非法路径（越权访问 UPLOAD_DIR 之外的文件）做了防护，并对
「未安装 adb」「无已授权设备」「多台设备」等情形返回清晰的中文提示，
而不是直接抛 500。
"""

import logging
import os
import re
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from modules.user.auth import require_permission
from modules.user.config import ADB_PATH, ADB_TIMEOUT, UPLOAD_DIR
from modules.user.utils import _audit_log

log = logging.getLogger("uvicorn")

router = APIRouter(prefix="/api/adb", tags=["ADB"])


class AdbInstallRequest(BaseModel):
    """安装请求体：目标文件的相对存储路径 + 可选的设备序列号。"""

    path: str
    serial: str | None = None


def _run_adb(args: list[str], timeout: int = 30):
    """运行 ``adb <args>``，统一处理常见异常。

    返回：
    * ``subprocess.CompletedProcess`` —— 正常（无论 adb 自身退出码）；
    * ``None`` —— 找不到 adb 可执行文件（未安装 / 不在 PATH）；
    * ``"TIMEOUT"`` —— 执行超时；
    其他启动异常也会被包成 returncode=1 的 CompletedProcess，交给调用方统一处理。
    """

    try:
        return subprocess.run(
            [ADB_PATH, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as exc:  # adb 存在但启动失败（权限、损坏等）
        log.warning("adb launch failed for %s: %s", args, exc)
        return subprocess.CompletedProcess(
            [ADB_PATH, *args], returncode=1, stdout="", stderr=f"adb 启动失败: {exc}"
        )


def _parse_devices(raw: str) -> list[dict]:
    """解析 ``adb devices -l`` 的输出，返回设备字典列表。

    每行形如：``serial  device  model:XXX product:YYY device:ZZZ``
    只跳过首行 ``List of devices attached`` 与空行。
    """

    devices: list[dict] = []
    if not raw:
        return devices
    for line in raw.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = ""
        for tok in parts[2:]:
            if tok.startswith("model:"):
                model = tok.split(":", 1)[1]
        devices.append(
            {
                "serial": serial,
                "state": state,  # device | offline | unauthorized | ...
                "model": model,
                "ready": state == "device",  # 只有已授权(usb调试)才可安装
            }
        )
    return devices


def _list_devices() -> list[dict]:
    """返回全部已连接设备（含未授权/离线）。adb 缺失时返回空列表。"""

    proc = _run_adb(["devices", "-l"], timeout=20)
    if proc is None or proc == "TIMEOUT" or not isinstance(proc, subprocess.CompletedProcess):
        return []
    return _parse_devices(proc.stdout or "")


def _list_ready_devices() -> list[dict]:
    """返回已授权（state==device）的可用设备。"""

    return [d for d in _list_devices() if d["ready"]]


@router.get("/devices")
async def list_devices(
    user: dict = Depends(require_permission("file:adb_install")),
):
    """列出通过 adb 连接的设备（含型号与授权状态）。"""

    proc = _run_adb(["devices", "-l"], timeout=20)
    if proc is None:
        return {
            "ok": False,
            "adb_missing": True,
            "devices": [],
            "message": (
                "未检测到 adb：请先安装 Android SDK Platform-Tools 并加入 PATH，"
                "或在 .env 中设置 ADB_PATH。"
            ),
        }
    if proc == "TIMEOUT":
        raise HTTPException(504, "adb devices 执行超时")
    devices = _parse_devices(proc.stdout or "")
    return {
        "ok": True,
        "adb_missing": False,
        "devices": devices,
        "message": "" if devices else "未检测到已连接的设备",
    }


@router.post("/install")
async def install_apk(
    body: AdbInstallRequest,
    user: dict = Depends(require_permission("file:adb_install")),
):
    """把指定 APK 文件一键安装到设备。

    安全：
    * 仅接受 ``.apk`` 文件；
    * 路径必须落在 UPLOAD_DIR 之内（禁止 ``..`` 越权访问）；
    * 未指定 serial 时，若只有一台已授权设备则自动选用，多台则返回
      ``needs_serial`` 让前端弹出选择。
    """

    # 1. 解析并校验路径，防止越权访问 UPLOAD_DIR 之外的文件。
    try:
        full = (UPLOAD_DIR / body.path).resolve()
        base = UPLOAD_DIR.resolve()
    except Exception:
        raise HTTPException(400, "非法文件路径")
    if full != base and not str(full).startswith(str(base) + os.sep):
        raise HTTPException(400, "非法文件路径")
    if full.suffix.lower() != ".apk":
        raise HTTPException(400, "仅支持安装 .apk 文件")
    if not full.exists() or not full.is_file():
        raise HTTPException(404, "文件不存在")

    # 2. 确认 adb 可用。
    ver = _run_adb(["version"], timeout=15)
    if ver is None:
        raise HTTPException(
            400,
            "未检测到 adb：请先安装 Android SDK Platform-Tools 并加入 PATH，"
            "或在 .env 中设置 ADB_PATH。",
        )
    if ver == "TIMEOUT":
        raise HTTPException(504, "adb version 执行超时")

    # 3. 确定目标设备序列号。
    serial = (body.serial or "").strip()
    if not serial:
        ready = _list_ready_devices()
        if len(ready) == 0:
            return {
                "ok": False,
                "needs_device": True,
                "devices": _list_devices(),
                "message": "未检测到已授权设备，请连接手机并开启 USB 调试。",
            }
        if len(ready) > 1:
            return {
                "ok": False,
                "needs_serial": True,
                "devices": ready,
                "message": "检测到多台设备，请选择目标设备。",
            }
        serial = ready[0]["serial"]

    # 4. 执行安装（替换已装旧版本）。
    args = ["-s", serial, "install", "-r", str(full)]
    t0 = time.time()
    result = _run_adb(args, timeout=ADB_TIMEOUT)
    if result is None:
        raise HTTPException(400, "adb 执行失败（未找到 adb）。")
    if result == "TIMEOUT":
        raise HTTPException(504, f"adb install 超时（>{ADB_TIMEOUT}s）")

    out = (result.stdout or "") + (result.stderr or "")
    success = result.returncode == 0 and "Success" in out
    _audit_log(
        "adb_install",
        f"{body.path} -> {serial}",
        user["username"],
    )

    return {
        "ok": success,
        "serial": serial,
        "returncode": result.returncode,
        "output": out.strip(),
        "elapsed_sec": round(time.time() - t0, 1),
        "message": "安装成功" if success else "安装失败",
    }


class AdbConnectRequest(BaseModel):
    """WiFi 配对请求体：手机在「无线调试」下显示的 IP:端口。"""

    host: str
    port: int = 5555


def _validate_host(host: str) -> str | None:
    """仅允许主机名 / IPv4 / IPv6 字面量与端口，避免注入。

    ``adb connect`` 通过参数列表传参（不走 shell），此处再做一层白名单。
    """
    h = (host or "").strip()
    if not h:
        return None
    # 允许 字母/数字/点/冒号/百分号(IPv6)/下划线/连字符
    if not re.fullmatch(r"[\w.\-:\[\]%]+", h):
        return None
    return h


@router.post("/connect")
async def connect_wifi(
    body: AdbConnectRequest,
    user: dict = Depends(require_permission("file:adb_install")),
):
    """让服务器上的 adb 通过 WiFi (TCP/IP) 连上手机。

    手机需先开启「无线调试 / 网络 ADB」并给出 IP:端口；服务器与该
    IP 必须网络可达（同局域网或可路由）。连上后 ``adb devices`` 即可看到
    设备，随后 ``/api/adb/install`` 即可安装。
    """
    host = _validate_host(body.host)
    if not host or not (1 <= int(body.port or 5555) <= 65535):
        raise HTTPException(400, "无效的 host / port")
    target = f"{host}:{int(body.port or 5555)}"
    ver = _run_adb(["version"], timeout=15)
    if ver is None:
        raise HTTPException(
            400,
            "服务器未检测到 adb：请先在服务器安装 Android SDK Platform-Tools 并加入 PATH，"
            "或在 .env 设置 ADB_PATH。",
        )
    proc = _run_adb(["connect", target], timeout=20)
    if proc is None:
        raise HTTPException(400, "adb 执行失败（未找到 adb）。")
    if proc == "TIMEOUT":
        raise HTTPException(504, f"adb connect {target} 超时（>{20}s）")
    out = (proc.stdout or "") + (proc.stderr or "")
    return {
        "ok": True,
        "target": target,
        "output": out.strip(),
        "devices": _list_devices(),
        "message": out.strip() or "已发起连接",
    }


@router.post("/disconnect")
async def disconnect_wifi(
    body: AdbConnectRequest,
    user: dict = Depends(require_permission("file:adb_install")),
):
    """断开服务器与某 WiFi 设备的 adb 连接。"""
    host = _validate_host(body.host)
    if not host:
        raise HTTPException(400, "无效的 host")
    target = f"{host}:{int(body.port or 5555)}"
    proc = _run_adb(["disconnect", target], timeout=20)
    if proc is None:
        raise HTTPException(400, "adb 执行失败（未找到 adb）。")
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"ok": True, "target": target, "output": out.strip(), "devices": _list_devices()}
