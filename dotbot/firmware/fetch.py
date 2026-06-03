"""Firmware release fetching + cache layout (no CLI, no flashing).

The engine behind `dotbot fw fetch` and the auto-fetch hook in
`flash.flash_role`: decide which GitHub release to pull (pinned / latest /
an explicit tag), download every asset it publishes into the
source-qualified cache (`~/.dotbot/artifacts/<source>-<version>/`), and
record provenance in a `manifest.json`. Pure library code; the Click
surface lives in `dotbot/cli/fw.py`.

Kept separate from `flash.py` (the hardware-facing flashing engine): this
module never touches a device, only the network + the cache.
"""

from __future__ import annotations

import json
import os
import shutil
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

GITHUB_API = "https://api.github.com/repos"
# Firmware release sources. swarmit ships the swarm system images (bootloader
# + mari netcore + mari gateway); DotBot-firmware ships the bare apps (.hex)
# and the sandbox apps (.bin). Each is cached in its own <source>-<version>/
# subdir of the artifacts cache so versions and provenance never collide.
RELEASE_SOURCES = {
    "swarmit": "DotBots/swarmit",
    "dotbot-firmware": "DotBots/DotBot-firmware",
}
DEFAULT_FETCH_SOURCES = ("swarmit", "dotbot-firmware")
# The DotBot-firmware release this pydotbot is built and tested against. Unlike
# swarmit (a Python dependency, whose firmware release is tagged identically to
# the package, so we read it from importlib.metadata), DotBot-firmware is not a
# Python package - so the expected version is declared here and bumped
# deliberately when pydotbot adopts a new release. `dotbot fw fetch` (no -f)
# pulls exactly this; -f overrides it.
DOTBOT_FIRMWARE_VERSION = "1.22.0rc1"

# Transient HTTP statuses worth retrying (GitHub's asset CDN 502s now and
# then under concurrent load; 429 is rate-limiting).
_RETRY_STATUS = {429, 500, 502, 503, 504}


def resolve_fw_root(bin_dir: Path, source: str, fw_version: str) -> Path:
    return bin_dir / f"{source}-{fw_version}"


def _human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def _short_path(path: Path) -> str:
    """Path relative to the cwd when that's shorter, else absolute."""
    try:
        rel = os.path.relpath(path)
    except ValueError:
        # Windows: path and cwd on different drives have no relative form.
        return str(path)
    return rel if not rel.startswith("..") else str(path)


def download_file(url: str, dest: Path, *, retries: int = 3) -> int:
    """Download ``url`` to ``dest``; return the number of bytes written.

    Retries transient failures (connection errors and HTTP 429/5xx) with
    exponential backoff - GitHub's CDN occasionally 502s under concurrent
    downloads, and a sporadic failure shouldn't abort the whole fetch.
    """
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise click.ClickException(f"HTTP {status} while downloading {url}")
                data = resp.read()
            dest.write_bytes(data)
            return len(data)
        except urllib.error.HTTPError as exc:
            if exc.code not in _RETRY_STATUS or attempt == retries:
                raise click.ClickException(
                    f"HTTP error while downloading {url}: {exc}"
                ) from exc
            reason = f"HTTP {exc.code}"
        except urllib.error.URLError as exc:
            if attempt == retries:
                raise click.ClickException(
                    f"Network error while downloading {url}: {exc}"
                ) from exc
            reason = str(exc.reason)
        delay = 0.5 * (2**attempt)
        click.echo(
            f"  [retry] {url.rsplit('/', 1)[-1]} ({reason}); retrying in {delay:.1f}s",
            err=True,
        )
        time.sleep(delay)
    raise click.ClickException(  # pragma: no cover - loop always returns/raises
        f"Failed to download {url} after {retries} retries."
    )


def _github_get(url: str):
    """Unauthenticated GitHub API GET (60 req/hour is plenty for a CLI)."""
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "dotbot"},
    )
    try:
        with urllib.request.urlopen(request) as resp:
            return json.load(resp)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise click.ClickException(f"GitHub API request failed ({url}): {exc}") from exc


def resolve_release(source: str, fw_version: str) -> dict:
    """Return the GitHub release JSON for ``source`` at ``fw_version``.

    ``fw_version="latest"`` resolves the newest release via ``/releases``
    (prereleases included, unlike ``/releases/latest`` which skips them - the
    current newest, e.g. swarmit 0.8.0rc2, is a prerelease).
    """
    if source not in RELEASE_SOURCES:
        raise click.ClickException(
            f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
        )
    repo = RELEASE_SOURCES[source]
    if fw_version == "latest":
        releases = _github_get(f"{GITHUB_API}/{repo}/releases?per_page=1")
        if not releases:
            raise click.ClickException(
                f"No releases found for {repo}; pass an explicit -f <version>."
            )
        return releases[0]
    return _github_get(f"{GITHUB_API}/{repo}/releases/tags/{fw_version}")


def resolve_latest_version(source: str = "swarmit") -> str:
    """The newest release tag for ``source`` (prereleases included)."""
    return resolve_release(source, "latest")["tag_name"]


def pinned_version(source: str) -> str:
    """The exact firmware release this pydotbot pins for ``source``.

    swarmit is a Python dependency whose firmware release is tagged identically
    to the package, so its pin is read from the installed package. DotBot-firmware
    is not a Python package, so its pin is the declared ``DOTBOT_FIRMWARE_VERSION``.
    `dotbot fw fetch` (no -f) resolves to these; pass -f to override.
    """
    if source == "swarmit":
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _pkg_version

        try:
            return _pkg_version("swarmit")
        except PackageNotFoundError as exc:
            raise click.ClickException(
                "Cannot infer the swarmit firmware version: the swarmit package "
                "is not installed. Pass -f <version> explicitly."
            ) from exc
    if source == "dotbot-firmware":
        return DOTBOT_FIRMWARE_VERSION
    raise click.ClickException(
        f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
    )


def fetch_assets(
    source: str, fw_version: str, bin_dir: Path, local_root: Path | None = None
) -> Path:
    """Fetch one source's firmware into ``bin_dir/<source>-<version>/``.

    For a released version, downloads every ``.hex``/``.bin`` asset the GitHub
    release publishes (so it adapts to whatever the release ships, no hardcoded
    asset list) and writes a ``manifest.json`` with provenance. For
    ``fw_version="local"``, symlinks/copies from a local build tree into
    ``<source>-local/``. Used by `dotbot fw fetch` and the auto-fetch hook in
    `flash_role`.
    """
    if source not in RELEASE_SOURCES:
        raise click.ClickException(
            f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
        )
    if fw_version == "local" and not local_root:
        raise click.ClickException("--local-root is required when --fw-version=local.")
    if fw_version != "local" and local_root:
        click.echo(
            "[WARN] --local-root ignored when --fw-version is not 'local'.",
            err=True,
        )

    if fw_version == "local":
        return _link_local_assets(source, local_root, bin_dir)

    release = resolve_release(source, fw_version)
    tag = release["tag_name"]
    out_dir = resolve_fw_root(bin_dir, source, tag)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets = [
        a for a in release.get("assets", []) if a["name"].endswith((".hex", ".bin"))
    ]
    if not assets:
        raise click.ClickException(
            f"{source} release {tag} publishes no .hex/.bin assets."
        )
    click.echo(
        f"Fetching {source} {tag} ({len(assets)} files) into {_short_path(out_dir)}"
    )
    names: list[str] = []
    errors: list[str] = []
    # Downloads are I/O-bound, so a small thread pool overlaps them (urllib
    # releases the GIL during the network read). Sources stay sequential.
    # Kept modest: GitHub's asset CDN starts 502ing under heavier fan-out
    # (download_file retries transient failures regardless).
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_to_name = {
            pool.submit(
                download_file, asset["browser_download_url"], out_dir / asset["name"]
            ): asset["name"]
            for asset in assets
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                size = future.result()
            except click.ClickException as exc:
                errors.append(f"{name}: {exc.format_message()}")
                continue
            names.append(name)
            click.echo(f"  {name} ({_human_size(size)})")
    if errors:
        raise click.ClickException(
            f"{len(errors)} asset(s) failed to download:\n  " + "\n  ".join(errors)
        )
    _write_manifest(out_dir, source, tag, RELEASE_SOURCES[source], names)
    return out_dir


def _write_manifest(
    out_dir: Path, source: str, version: str, repo: str, files: list[str]
) -> None:
    """Record provenance next to the binaries (a cheap audit trail)."""
    from dotbot import pydotbot_version

    manifest = {
        "source": source,
        "version": version,
        "repo": repo,
        "url": f"https://github.com/{repo}/releases/tag/{version}",
        "pydotbot": pydotbot_version(),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": sorted(files),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _link_local_assets(source: str, local_root: Path, bin_dir: Path) -> Path:
    """Symlink/copy a local build tree into ``bin_dir/<source>-local/``."""
    if source != "swarmit":
        raise click.ClickException(
            f"--fw-version local is only wired for source 'swarmit' so far, "
            f"not '{source}'."
        )
    local_root = local_root.expanduser().resolve()
    out_dir = resolve_fw_root(bin_dir, source, "local")
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "bootloader-dotbot-v3.hex": local_root
        / "device/bootloader/Output/dotbot-v3/Debug/Exe/bootloader-dotbot-v3.hex",
        "netcore-nrf5340-net.hex": local_root
        / "device/network_core/Output/nrf5340-net/Debug/Exe/netcore-nrf5340-net.hex",
        "03app_gateway_app-nrf5340-app.hex": local_root
        / "mari/firmware/app/03app_gateway_app/Output/nrf5340-app/Debug/Exe/03app_gateway_app-nrf5340-app.hex",
        "03app_gateway_net-nrf5340-net.hex": local_root
        / "mari/firmware/app/03app_gateway_net/Output/nrf5340-net/Debug/Exe/03app_gateway_net-nrf5340-net.hex",
    }
    missing = [name for name, src in mapping.items() if not src.exists()]
    if missing:
        raise click.ClickException(
            f"Missing local build artifacts: {', '.join(missing)}"
        )
    for name, src in mapping.items():
        dest = out_dir / name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        try:
            os.symlink(src, dest)
            click.echo(f"[LINK] {dest} -> {src}")
        except OSError:
            shutil.copy2(src, dest)
            click.echo(f"[COPY] {dest} <- {src}")
    return out_dir
