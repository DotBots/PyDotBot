"""Firmware release fetching + cache layout (no CLI, no flashing).

The engine behind `dotbot fw fetch` and the `-f` rule every flash command
shares (`resolve_fw_dir`): decide which GitHub release to pull (pinned /
latest / an explicit tag), download every asset it publishes into the
source-qualified cache (`~/.dotbot/artifacts/<source>-<version>/`), record
provenance in a `manifest.json`, and find the set a flash reads from.
Pure library code; the Click surface lives in `dotbot/cli/fw.py`.

Kept separate from `flash.py` (the hardware-facing flashing engine): this
module never touches a device, only the network + the cache.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import click

GITHUB_API = "https://api.github.com/repos"
# Firmware release sources. swarmit ships the swarm system images (bootloader
# + netcore + the Mari gateway); DotBot-firmware ships the bare apps (.hex)
# and the sandbox apps (.bin). Mari's releases publish no firmware. Each is cached in its own <source>-<version>/
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
DOTBOT_FIRMWARE_VERSION = "1.24.0"

# Transient HTTP statuses worth retrying (GitHub's asset CDN 502s now and
# then under concurrent load; 429 is rate-limiting).
_RETRY_STATUS = {429, 500, 502, 503, 504}


# A release tag starts with a digit, optionally after a `v` (1.23.0, 0.8.0rc2,
# v2.0). A set name built by `dotbot fw build --as` must not, so the two never
# share a cache directory and `-f` can tell them apart without the network.
_RELEASE_TAG_RE = re.compile(r"^v?[0-9]")
SET_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


def resolve_fw_root(bin_dir: Path, source: str, fw_version: str) -> Path:
    return bin_dir / f"{source}-{fw_version}"


def is_release_tag(value: str) -> bool:
    return bool(_RELEASE_TAG_RE.match(value))


def is_dir_value(value: str) -> bool:
    """Whether a `-f` value names a directory (it contains a path separator)."""
    return "/" in value or os.sep in value


def validate_set_name(name: str) -> str:
    """Return `name` if it can name a built set, else raise."""
    if name == "latest" or is_release_tag(name) or not SET_NAME_RE.match(name):
        raise click.ClickException(
            f"'{name}' cannot name a firmware set: use letters, digits, '.', '_' "
            "or '-', starting with a letter, and not 'latest' (a name starting "
            "with a digit or 'v<digit>' reads as a release tag)."
        )
    return name


def _missing(root: Path, required) -> list[str]:
    return [name for name in required if not (root / name).is_file()]


def _release_dir(
    release_source: str,
    tag: str,
    bin_dir: Path,
    required,
    build: str,
    *,
    suggest_latest: bool = True,
) -> Path:
    root = resolve_fw_root(bin_dir, release_source, tag)
    # A fetched release has a manifest; without one the directory is absent
    # or a partial download.
    if _missing(root, required) and not (root / "manifest.json").is_file():
        click.echo(
            f"[INFO] {release_source} {tag} is not cached in {root}; fetching..."
        )
        root = fetch_assets(release_source, tag, bin_dir)
    missing = _missing(root, required)
    if missing:
        latest = (
            "  - try the newest release: pass -f latest\n" if suggest_latest else ""
        )
        raise click.ClickException(
            f"{release_source} release {tag} does not publish "
            f"{', '.join(missing)}.\n{latest}"
            f"  - {'or ' if latest else ''}build it: "
            f"{_build_line(build, 'local')}, then pass -f local"
        )
    return root


def resolve_fw_dir(
    source: str,
    fw_version: str | None,
    bin_dir: Path,
    *,
    build: str,
    required=(),
    release_source: str | None = None,
) -> tuple[Path, str]:
    """The directory a flash command reads ``source`` firmware from, and its label.

    - omitted: the release pydotbot pins;
    - a value containing ``/``: a directory of release-named files, used as-is;
    - ``latest``: the newest release, resolved to its tag;
    - anything else: ``<bin_dir>/<source>-<value>/``, a release tag or a set
      built by `dotbot fw build` (``local`` or an ``--as`` name).

    A release tag missing from the cache is fetched; nothing is ever built.
    ``required`` names the files that must be present; ``build`` (e.g.
    ``spin`` or ``mari-gateway --schedule tiny``) completes the
    `dotbot fw build` line an error suggests.
    ``release_source`` is the source whose releases carry ``source``'s images
    when that is another one (``mari``: ``swarmit``); tags then name its
    releases, while set names still name ``<source>-<set>/``.
    """
    rel = release_source or source

    def release(tag: str, suggest_latest: bool = True) -> Path:
        return _release_dir(
            rel, tag, bin_dir, required, build, suggest_latest=suggest_latest
        )

    if fw_version is None:
        tag = pinned_version(rel)
        click.echo(f"[INFO] no -f given: using the {rel} release pydotbot pins, {tag}")
        return release(tag), tag
    if is_dir_value(fw_version):
        path = Path(fw_version).expanduser()
        if not path.is_dir():
            raise click.ClickException(f"-f {fw_version}: no such directory.")
        missing = _missing(path, required)
        if missing:
            raise click.ClickException(
                f"{path} is used as-is and has no {', '.join(missing)}."
            )
        return path.resolve(), path.resolve().name
    if fw_version == "latest":
        tag = resolve_latest_version(rel)
        click.echo(f"[INFO] latest {rel} release: {tag}")
        return release(tag, suggest_latest=False), tag
    if is_release_tag(fw_version):
        return release(fw_version), fw_version
    root = resolve_fw_root(bin_dir, source, fw_version)
    if not root.is_dir():
        raise click.ClickException(
            f"No '{fw_version}' {source} set: {root} does not exist.\n"
            "-f takes a release tag, 'latest', a set built by `dotbot fw build`, "
            "or a directory path containing '/'.\n"
            f"  - build it: {_build_line(build, fw_version)}\n"
            f"  - or fetch a release: dotbot fw fetch {build.split()[0]} -f <tag>"
        )
    missing = _missing(root, required)
    if missing:
        raise click.ClickException(
            f"The '{fw_version}' {source} set ({root}) has no "
            f"{', '.join(missing)}.\n"
            f"  - build it: {_build_line(build, fw_version)}"
        )
    return root, fw_version


def _build_line(build: str, name: str) -> str:
    line = f"dotbot fw build {build}"
    if name != "local":
        line += f" --as {name}"
    return line


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


def _ssl_context() -> ssl.SSLContext:
    """TLS context with certifi's CA bundle.

    A python.org Python on macOS has no system CA store wired in, so the
    default context fails with CERTIFICATE_VERIFY_FAILED.
    """
    import certifi

    return ssl.create_default_context(cafile=certifi.where())


def download_file(url: str, dest: Path, *, retries: int = 3) -> int:
    """Download ``url`` to ``dest``; return the number of bytes written.

    Retries transient failures (connection errors and HTTP 429/5xx) with
    exponential backoff - GitHub's CDN occasionally 502s under concurrent
    downloads, and a sporadic failure shouldn't abort the whole fetch.
    """
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(url, context=_ssl_context()) as resp:
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
        with urllib.request.urlopen(request, context=_ssl_context()) as resp:
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


def fetch_assets(source: str, fw_version: str, bin_dir: Path) -> Path:
    """Fetch one release into ``bin_dir/<source>-<tag>/``.

    Downloads every ``.hex``/``.bin`` asset the GitHub release publishes and
    writes a ``manifest.json`` with provenance. ``fw_version`` is a tag or
    ``latest``.
    """
    if source not in RELEASE_SOURCES:
        raise click.ClickException(
            f"Unknown firmware source '{source}'. Known: {', '.join(RELEASE_SOURCES)}."
        )
    if fw_version != "latest" and not is_release_tag(fw_version):
        raise click.ClickException(
            f"'{fw_version}' is not a release tag. `dotbot fw fetch` takes a tag "
            "(e.g. 1.23.0) or 'latest'; a locally built set comes from "
            "`dotbot fw build`."
        )

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
