#!/usr/bin/env python3
"""
Download ya-webadb 2.x (the maintained, self-contained line) from the npm
registry and unpack the ESM builds into static/js/vendor2/ for local serving.

Unlike the broken 0.0.19 split packages (whose WebUSB credential-store
companion package was never published), 2.x ships working WebUSB transport
(`@yume-chan/adb-daemon-webusb`) and credential store
(`@yume-chan/adb-credential-web`, IndexedDB-backed WebCrypto keys).

Generates:
  - static/js/webadb2-importmap.json
  - static/js/webadb2.bundle.js
    (re-exports Adb, AdbDaemonTransport, AdbDaemonWebUsbDeviceManager,
     and the default-exported AdbWebCredentialStore)

No Node.js / npm required. Run this on server A (the machine with internet).
"""
import json
import os
import re
import shutil
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENDOR = ROOT / "static" / "js" / "vendor2"
IMPORTMAP = ROOT / "static" / "js" / "webadb2-importmap.json"
WRAPPER = ROOT / "static" / "js" / "webadb2.bundle.js"

# Coherent 2.x entry set (all published together, matching semver ranges).
ENTRY_PACKAGES = {
    "@yume-chan/adb": "2.6.0",
    "@yume-chan/adb-daemon-webusb": "2.3.2",
    "@yume-chan/adb-credential-web": "2.1.0",
}

HEADERS = {"Accept": "application/json"}
_user_agent = ("Mozilla/5.0 (compatible; webadb-localizer/2.x)")


def _urlopen(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    return urllib.request.urlopen(req, timeout=60)


_doc_cache = {}


def get_full_doc(name: str):
    if name in _doc_cache:
        return _doc_cache[name]
    scope, pkg = name.split("/")
    url = f"https://registry.npmjs.org/{scope}/{pkg}"
    doc = json.loads(_urlopen(url).read())
    _doc_cache[name] = doc
    return doc


def pick_version(doc: dict, rng: str):
    versions = list(doc.get("versions", {}).keys())
    if not versions:
        return None
    if rng in versions:
        return rng
    m = re.match(r"^\s*[\^~>=<]*\s*(\d+)\.(\d+)\.(\d+)", rng)
    if m:
        maj = int(m.group(1))
        cands = [v for v in versions if _semver_key(v)[0] == maj]
        if cands:
            return max(cands, key=_semver_key)
    return doc.get("dist-tags", {}).get("latest")


def resolve_version(name: str, rng: str):
    """Resolve a semver range to a concrete published version (local pick)."""
    try:
        doc = get_full_doc(name)
    except Exception as e:
        print(f"[webadb2]   (skip) cannot resolve {name}@{rng}: {e}", file=sys.stderr)
        return None, {}
    ver = pick_version(doc, rng)
    if ver is None:
        return None, {}
    return ver, doc["versions"][ver].get("dependencies", {})


def _semver_key(v: str):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        return (0, 0, 0)
    return tuple(int(x) for x in m.groups())


def collect_closure() -> dict:
    """BFS over dependencies, keeping the highest version per package name."""
    resolved = {}  # name -> version

    def pick(name, version):
        if name not in resolved or _semver_key(version) > _semver_key(resolved[name]):
            resolved[name] = version

    queue = [(n, v) for n, v in ENTRY_PACKAGES.items()]
    for n, v in ENTRY_PACKAGES.items():
        pick(n, v)
    seen = set()
    while queue:
        name, _ = queue.pop(0)
        if name in seen:
            continue
        seen.add(name)
        # re-resolve current resolved range to capture transitive deps
        ver, deps = resolve_version(name, resolved[name])
        if ver is None:
            continue
        for dep, rng in deps.items():
            sub = resolve_version(dep, rng)
            if sub[0] is None:
                continue
            old = resolved.get(dep)
            if old is None or _semver_key(sub[0]) > _semver_key(old):
                resolved[dep] = sub[0]
            if dep not in seen:
                queue.append((dep, sub[0]))
    return resolved


def npm_tarball_url(name: str, version: str) -> str:
    scope, pkg = name.split("/")
    return f"https://registry.npmjs.org/{scope}/{pkg}/-/{pkg}-{version}.tgz"


def find_esm_entry(pkg_dir: Path):
    pj = pkg_dir / "package.json"
    data = json.loads(pj.read_text(encoding="utf-8")) if pj.exists() else {}
    # Preferred ESM fields, in order.
    for field in ("module", "exports"):
        val = data.get(field)
        if isinstance(val, str) and val.endswith((".js", ".mjs")):
            cand = pkg_dir / val
            if cand.exists():
                return val.replace("\\", "/")
        if isinstance(val, dict):
            # "exports": { ".": { "import": "esm/index.js", ... } }
            dot = val.get(".", {})
            if isinstance(dot, dict):
                for k in ("import", "module", "default"):
                    sub = dot.get(k)
                    if isinstance(sub, str) and sub.endswith((".js", ".mjs")):
                        cand = pkg_dir / sub
                        if cand.exists():
                            return sub.replace("\\", "/")
    for cand in ("esm/index.js", "esm/index.mjs", "dist/index.js",
                "out/index.js", "lib/index.js", "index.js"):
        if (pkg_dir / cand).exists():
            return cand
    for p in sorted(pkg_dir.rglob("index.js")):
        return p.relative_to(pkg_dir).as_posix()
    return None


def scan_bare_specifiers(vendor_root: Path):
    """Return set of bare module specifiers referenced by any vendored .js file."""
    bare = set()
    for f in vendor_root.rglob("*.js"):
        if f.name.endswith(".map"):
            continue
        try:
            txt = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for m in re.finditer(r'(?:from|import)\s*[\"\']([^\"\']+)[\"\']', txt):
            spec = m.group(1)
            if spec.startswith(".") or spec.startswith("/") or spec.startswith("data:") or spec.startswith("http"):
                continue
            bare.add(spec)
    return bare


def main() -> int:
    print("[webadb2] Resolving 2.x dependency closure ...")
    resolved = collect_closure()
    print(f"[webadb2] {len(resolved)} packages to download:")
    for n in sorted(resolved):
        print(f"[webadb2]   {n}@{resolved[n]}")

    if VENDOR.exists():
        shutil.rmtree(VENDOR)
    VENDOR.mkdir(parents=True, exist_ok=True)

    EMPTY_SHIM = VENDOR / "_empty.js"
    EMPTY_SHIM.write_text("export default {};\nexport {};\n", encoding="utf-8")

    imports = {}
    downloaded = set()

    for name, version in sorted(resolved.items()):
        if name in downloaded:
            continue
        downloaded.add(name)

        # types-only packages are never imported at runtime -> empty shim
        if name.startswith("@types/"):
            imports[name] = "/static/js/vendor2/_empty.js"
            imports[name + "/"] = "/static/js/vendor2/"
            print(f"[webadb2] {name}: types-only -> empty shim")
            continue

        print(f"[webadb2] downloading {name}@{version}")
        url = npm_tarball_url(name, version)
        tgz = ROOT / f"_webadb2_{name.replace('/', '_')}_{version}.tgz"
        try:
            urllib.request.urlretrieve(url, tgz)
        except Exception as e:
            print(f"[webadb2]   ERROR downloading {name}: {e}", file=sys.stderr)
            return 1

        stale = VENDOR / "package"
        if stale.exists():
            shutil.rmtree(stale)
        with tarfile.open(tgz, "r:gz") as tf:
            tf.extractall(path=VENDOR)
        tgz.unlink()

        top_dirs = [p for p in VENDOR.iterdir() if p.is_dir() and p.name != "_empty.js"]
        extracted = next((p for p in top_dirs if p.name == "package"), top_dirs[0] if top_dirs else None)
        if extracted is None:
            print(f"[webadb2] ERROR: extraction failed for {name}", file=sys.stderr)
            return 1
        dest = VENDOR / name
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        extracted.rename(dest)

        entry = find_esm_entry(dest)
        if entry is None:
            imports[name] = "/static/js/vendor2/_empty.js"
            imports[name + "/"] = "/static/js/vendor2/"
            print(f"[webadb2]   WARNING: no ESM entry, mapped to shim")
        else:
            parent = Path(entry).parent.as_posix()
            imports[name] = f"/static/js/vendor2/{name}/{entry}"
            imports[name + "/"] = f"/static/js/vendor2/{name}/{parent}/"

    # ---- node: built-ins are only used by the Node-side ADB server ----
    # (esm/server/* under @yume-chan/adb). The browser never instantiates
    # those classes, but native ESM still loads the re-exported module,
    # so we map node: specifiers to an empty shim to let import resolve.
    bare = scan_bare_specifiers(VENDOR)
    for spec in sorted(bare):
        if spec.startswith("node:"):
            imports[spec] = "/static/js/vendor2/_empty.js"

    # ---- validate: every bare specifier in vendored code must be mapped ----
    missing = []
    for spec in sorted(bare):
        if spec in imports:
            continue
        # scoped subpath: check the package root mapping
        root = spec
        if root.startswith("@"):
            root = "/".join(spec.split("/")[:2])
        else:
            root = spec.split("/")[0]
        if root in imports or (root + "/") in imports:
            continue
        if spec.startswith("node:"):
            continue
        if spec in ("@yume-chan/adb", "@yume-chan/adb-daemon-webusb",
                       "@yume-chan/adb-credential-web"):
            # explicitly re-exported by the bundle, always resolvable
            continue
        missing.append(spec)
    if missing:
        print("\n[webadb2] WARNING: bare specifiers NOT covered by import map:", file=sys.stderr)
        for m in missing:
            print(f"   - {m}", file=sys.stderr)

    IMPORTMAP.write_text(json.dumps({"imports": imports}, indent=2), encoding="utf-8")
    WRAPPER.write_text(
        '// ya-webadb 2.x re-exports (localized build)\n'
        'export { Adb, AdbDaemonTransport } from "@yume-chan/adb";\n'
        'export { AdbDaemonWebUsbDeviceManager } from "@yume-chan/adb-daemon-webusb";\n'
        'import AdbWebCredentialStore from "@yume-chan/adb-credential-web";\n'
        'export { AdbWebCredentialStore };\n',
        encoding="utf-8",
    )

    print("\n[webadb2] DONE.")
    print(f"[webadb2] Import map: {IMPORTMAP}")
    print(f"[webadb2] Bundle:     {WRAPPER}")
    print("[webadb2] Next: restart the server (run_https.bat) and open the page over HTTPS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
