#!/usr/bin/env python3
"""
Download @yume-chan/adb 0.0.19 + webusb backend from npm registry
and unpack them into static/js/vendor/ for local serving.

Generates:
  - static/js/webadb-importmap.json
  - static/js/webadb.bundle.js (re-exports Adb + AdbWebUsbBackend)

No Node.js / npm is required. Run this on server A (the machine that can access npm registry).
"""
import json
import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "static" / "js" / "vendor"
IMPORTMAP = ROOT / "static" / "js" / "webadb-importmap.json"
WRAPPER = ROOT / "static" / "js" / "webadb.bundle.js"

# Exact versions known to be compatible with @yume-chan/adb-backend-webusb@0.0.19
PACKAGES = {
    "@yume-chan/adb": "0.0.19",
    "@yume-chan/adb-backend-webusb": "0.0.19",
    "@yume-chan/async": "2.2.0",
    "@yume-chan/event": "0.0.19",
    "@yume-chan/struct": "0.0.19",
    "@yume-chan/stream-extra": "0.0.19",
    "@yume-chan/dataview-bigint-polyfill": "0.0.19",
    "tslib": "2.4.1",
    "@types/w3c-web-usb": "1.0.6",  # types-only dependency; mapped to an empty shim
}


def npm_tarball_url(name: str, version: str) -> str:
    if name.startswith("@"):
        scope, pkg = name.split("/")
        return f"https://registry.npmjs.org/{scope}/{pkg}/-/{pkg}-{version}.tgz"
    return f"https://registry.npmjs.org/{name}/-/{name}-{version}.tgz"


def find_esm_entry(pkg_dir: Path) -> Optional[str]:
    """Pick the browser ESM entry for a downloaded package.

    Returns None for types-only packages (e.g. @types/*); the caller will
    map them to an empty shim so the import map stays complete.
    """
    pkg_json = pkg_dir / "package.json"
    data: dict = {}
    if pkg_json.exists():
        data = json.loads(pkg_json.read_text(encoding="utf-8"))

    # 1. Explicit esm/ directory is the most reliable for yume-chan packages.
    for cand in ("esm/index.js", "esm/index.mjs"):
        if (pkg_dir / cand).exists():
            return cand

    # 2. package.json "module" field (preferred by bundlers) if it exists on disk.
    mod = data.get("module", "")
    if mod.endswith((".js", ".mjs")) and (pkg_dir / mod).exists():
        return mod.replace("\\", "/")

    # 3. Common ESM build directories.
    for cand in ("out/index.js", "dist/index.js", "lib/index.js", "index.js"):
        if (pkg_dir / cand).exists():
            return cand

    # 4. Last resort: first index.js anywhere (types-only packages have none).
    for p in sorted(pkg_dir.rglob("index.js")):
        return p.relative_to(pkg_dir).as_posix()

    return None


def main() -> int:
    print("[webadb] Downloading ya-webadb packages from npm registry ...")
    print("[webadb] This only needs to run once on server A.")
    VENDOR.mkdir(parents=True, exist_ok=True)

    # Empty shim for types-only dependencies that may be listed but never imported at runtime.
    # Use .js (not .mjs) so Starlette StaticFiles serves it with a JavaScript MIME type.
    EMPTY_SHIM = VENDOR / "_empty.js"
    EMPTY_SHIM.write_text("export default {};\nexport {};\n", encoding="utf-8")

    imports = {}

    for name, version in PACKAGES.items():
        print(f"[webadb] {name}@{version}")
        url = npm_tarball_url(name, version)
        dest = VENDOR / name
        if dest.exists():
            shutil.rmtree(dest)

        # Types-only packages are not needed at runtime; map them to an empty shim.
        if name.startswith("@types/"):
            imports[name] = "/static/js/vendor/_empty.js"
            imports[name + "/"] = "/static/js/vendor/"
            print(f"[webadb]   -> types-only, mapped to empty shim")
            continue

        tgz = ROOT / f"_webadb_{name.replace('/', '_')}_{version}.tgz"
        urllib.request.urlretrieve(url, tgz)

        # npm tarballs normally extract to a top-level "package/" directory.
        # Remove any stale "package" dir first, then auto-detect the real top dir.
        stale_package = VENDOR / "package"
        if stale_package.exists():
            shutil.rmtree(stale_package)
        with tarfile.open(tgz, "r:gz") as tf:
            tf.extractall(path=VENDOR)

        top_dirs = [p for p in VENDOR.iterdir() if p.is_dir() and p.name != "_empty.js"]
        if not top_dirs:
            print(f"[webadb] ERROR: extraction failed for {name}", file=sys.stderr)
            return 1
        extracted = top_dirs[0]
        if len(top_dirs) > 1:
            package_dirs = [p for p in top_dirs if p.name == "package"]
            if package_dirs:
                extracted = package_dirs[0]

        dest.parent.mkdir(parents=True, exist_ok=True)
        extracted.rename(dest)
        tgz.unlink()

        entry = find_esm_entry(dest)
        if entry is None:
            imports[name] = "/static/js/vendor/_empty.js"
            imports[name + "/"] = "/static/js/vendor/"
        else:
            imports[name] = f"/static/js/vendor/{name}/{entry}"
            imports[name + "/"] = f"/static/js/vendor/{name}/{Path(entry).parent.as_posix()}/"

    IMPORTMAP.write_text(json.dumps({"imports": imports}, indent=2), encoding="utf-8")
    WRAPPER.write_text(
        'export { Adb } from "@yume-chan/adb";\n'
        'export { AdbWebUsbBackend } from "@yume-chan/adb-backend-webusb";\n',
        encoding="utf-8",
    )

    print("[webadb] DONE.")
    print(f"[webadb] Import map: {IMPORTMAP}")
    print(f"[webadb] Wrapper:    {WRAPPER}")
    print("[webadb] Next: restart the server (run_https.bat) and open the page over HTTPS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
