"""Download the Codex runtime on first use.

The PyPI release of this package is small: instead of the Codex binaries it
ships a manifest (``_manifest.py``) listing one platform wheel per supported
platform, hosted on the project's GitHub Release. The first time the runtime is
needed, the matching wheel is downloaded, checked against its SHA-256 digest
and unpacked into a per-user cache. Later calls reuse the cached copy.
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import ssl
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

PACKAGE_PREFIX = "codex_cli_bin/"
PACKAGE_METADATA_FILENAME = "codex-package.json"
CACHE_DIR_ENV = "CIRCLE_CODEX_CACHE_DIR"
BASE_URL_ENV = "CIRCLE_CODEX_DOWNLOAD_BASE_URL"
_EXECUTABLE_DIRS = {"bin", "codex-path", "codex-resources"}
_CHUNK_SIZE = 1024 * 1024


class RuntimeDownloadError(OSError):
    """Raised when the Codex runtime cannot be downloaded or unpacked."""


def platform_key() -> str:
    """Return the manifest key for this machine, for example ``linux-x86_64``."""
    system = platform.system()
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        arch = "arm64" if system == "Darwin" else "aarch64"
    elif machine in {"x86_64", "amd64"}:
        arch = "x86_64"
    else:
        arch = machine
    if system == "Darwin":
        return f"darwin-{arch}"
    if system == "Linux":
        return f"linux-{arch}"
    return f"{system.lower()}-{arch}"


def default_cache_root() -> Path:
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "circle-codex"
    xdg_cache = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache).expanduser() if xdg_cache else Path.home() / ".cache"
    return base / "circle-codex"


def is_runtime_dir(path: Path) -> bool:
    exe = "codex.exe" if os.name == "nt" else "codex"
    return (path / PACKAGE_METADATA_FILENAME).is_file() and (path / "bin" / exe).is_file()


def ensure_runtime(manifest: Mapping[str, Any]) -> Path:
    """Return a directory holding the runtime, downloading it on first use."""
    key = platform_key()
    files = manifest["files"]
    entry = files.get(key)
    if entry is None:
        supported = ", ".join(sorted(files))
        raise RuntimeDownloadError(
            f"No Codex runtime is published for this platform ({key}). "
            f"Supported platforms: {supported}."
        )

    target = default_cache_root() / str(manifest["version"]) / key
    if is_runtime_dir(target):
        return target

    base_url = os.environ.get(BASE_URL_ENV) or manifest["base_url"]
    url = f"{base_url.rstrip('/')}/{entry['filename']}"
    target.parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix=".download-", dir=target.parent))
    try:
        wheel_path = work_dir / entry["filename"]
        _download(url, wheel_path, expected_sha256=entry["sha256"], size=entry.get("size"))
        unpack_dir = work_dir / "runtime"
        _unpack_runtime(wheel_path, unpack_dir)
        if not is_runtime_dir(unpack_dir):
            raise RuntimeDownloadError(f"{entry['filename']} does not contain a Codex runtime")
        try:
            os.rename(unpack_dir, target)
        except OSError:
            # Another process finished the same download first.
            if not is_runtime_dir(target):
                raise
        return target
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def _download(url: str, destination: Path, *, expected_sha256: str, size: int | None) -> None:
    size_text = f" ({size / 1024 / 1024:.0f} MB)" if size else ""
    print(
        f"circle-codex: downloading the Codex runtime{size_text} from {url} "
        "(first run only)...",
        file=sys.stderr,
        flush=True,
    )
    digest = hashlib.sha256()
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "circle-codex-cli-bin"})
        with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
            with destination.open("wb") as output:
                while chunk := response.read(_CHUNK_SIZE):
                    digest.update(chunk)
                    output.write(chunk)
    except OSError as exc:
        raise RuntimeDownloadError(
            f"Could not download the Codex runtime from {url}: {exc}. "
            f"Check your internet connection or proxy settings, set {BASE_URL_ENV} to a "
            "mirror, or pass CodexConfig(codex_bin=...) to use a local Codex binary."
        ) from exc
    if digest.hexdigest() != expected_sha256:
        raise RuntimeDownloadError(
            f"Checksum mismatch for {url}: expected {expected_sha256}, got {digest.hexdigest()}."
        )


def _unpack_runtime(wheel_path: Path, destination: Path) -> None:
    """Extract the runtime files (not the Python code) from a platform wheel."""
    destination.mkdir(parents=True)
    with zipfile.ZipFile(wheel_path) as archive:
        for info in archive.infolist():
            name = info.filename
            if not name.startswith(PACKAGE_PREFIX) or name.endswith("/"):
                continue
            relative = PurePosixPath(name[len(PACKAGE_PREFIX) :])
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or "__pycache__" in relative.parts
                or relative.suffix == ".py"
            ):
                continue
            output_path = destination.joinpath(*relative.parts)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, output_path.open("wb") as output:
                shutil.copyfileobj(source, output, _CHUNK_SIZE)
            mode = (info.external_attr >> 16) & 0o777 or 0o644
            if relative.parts[0] in _EXECUTABLE_DIRS:
                # Programs must stay runnable even if the archive lost their mode bits.
                mode |= 0o755
            output_path.chmod(mode)
