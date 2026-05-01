"""Install bsl-language-server JAR into the user cache.

Pulls the latest (or a pinned) release from
https://github.com/1c-syntax/bsl-language-server/releases and lands the
JAR at::

    $XDG_CACHE_HOME/mcp-1c/bsl-language-server.jar         (Linux)
    %LOCALAPPDATA%/mcp-1c/bsl-language-server.jar          (Windows)
    ~/Library/Caches/mcp-1c/bsl-language-server.jar        (macOS)

Idempotent: a marker file (``bsl-language-server.version``) records the
installed version; reruns return early when the requested version is
already on disk. SHA-256 of the downloaded archive is verified against
the GitHub release asset metadata when available.

Stdlib-only (urllib, zipfile, json, hashlib) — installer must work in a
fresh venv where only the package itself is present.

Use as a CLI::

    mcp-1c-install-bsl-ls               # latest stable
    mcp-1c-install-bsl-ls --version 0.24.0
    mcp-1c-install-bsl-ls --jar-only    # don't unzip; keep the .zip
    mcp-1c-install-bsl-ls --force       # re-download even if up to date

Or programmatically::

    from mcp_1c.scripts.install_bsl_ls import install_bsl_ls
    path = install_bsl_ls()  # returns Path to the jar
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger("install_bsl_ls")

GITHUB_REPO = "1c-syntax/bsl-language-server"
LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
TAGGED_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{{tag}}"
)

# We download the bundled "execute"-mode zip — it contains the runnable
# JAR plus dependencies. The repo publishes assets like
# ``bsl-language-server-0.24.0.zip`` — substring match is enough to
# pick the right one (avoids hard-coding a specific naming convention
# that may shift between releases).
_ASSET_NEEDLE = "bsl-language-server"
_ASSET_SUFFIX = ".zip"


def cache_root() -> Path:
    """Return the platform-correct cache root for mcp-1c."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
        return Path(base) / "mcp-1c"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "mcp-1c"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg) if xdg else Path.home() / ".cache") / "mcp-1c"


def install_bsl_ls(
    *,
    version: str | None = None,
    target_dir: Path | None = None,
    force: bool = False,
    keep_archive: bool = False,
) -> Path:
    """Download and install bsl-language-server.

    Args:
        version: Release tag (e.g. ``"0.24.0"``). ``None`` means latest.
        target_dir: Override the cache root.
        force: Re-download even if the requested version is already
            installed.
        keep_archive: Don't delete the downloaded ``.zip`` after
            extracting. Useful for debugging release contents.

    Returns:
        Absolute path to the installed ``bsl-language-server.jar``.

    Raises:
        RuntimeError: When the GitHub API or the download fails.
    """
    target_dir = (target_dir or cache_root()).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    jar_path = target_dir / "bsl-language-server.jar"
    version_marker = target_dir / "bsl-language-server.version"

    release = _fetch_release(version)
    resolved_version = release["tag_name"]
    asset = _pick_asset(release)

    if (
        not force
        and jar_path.exists()
        and version_marker.exists()
        and version_marker.read_text(encoding="utf-8").strip()
        == resolved_version
    ):
        logger.info(f"bsl-language-server {resolved_version} already installed at {jar_path}")
        return jar_path

    logger.info(f"Downloading bsl-language-server {resolved_version} ({asset['name']})")
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / asset["name"]
        _download(asset["browser_download_url"], archive_path)
        _verify_size(archive_path, asset.get("size"))

        # GitHub doesn't publish per-asset sha256 in the release JSON, but
        # 1c-syntax includes a ``.sha256`` sibling asset starting from
        # 0.22 — pull it opportunistically for trust-on-first-install.
        _verify_sha256_if_available(release, archive_path)

        extracted_jar = _extract_jar(archive_path, Path(tmp))
        # Atomic swap: write to .new, rename over the live file.
        staged = jar_path.with_suffix(".jar.new")
        shutil.copy2(extracted_jar, staged)
        staged.replace(jar_path)
        if keep_archive:
            shutil.copy2(archive_path, target_dir / archive_path.name)

    version_marker.write_text(resolved_version, encoding="utf-8")
    logger.info(f"Installed bsl-language-server {resolved_version} → {jar_path}")
    return jar_path


# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------


def _fetch_release(version: str | None) -> dict:
    url = (
        LATEST_API
        if version is None
        else TAGGED_API.format(tag=_normalise_tag(version))
    )
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "mcp-1c-install-bsl-ls/0.2",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (https url, fixed scheme)
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and version is not None:
            raise RuntimeError(
                f"bsl-language-server release {version!r} not found on GitHub"
            ) from exc
        raise RuntimeError(f"GitHub API error: {exc}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Cannot reach GitHub API: {exc}. Check internet connectivity."
        ) from exc


def _pick_asset(release: dict) -> dict:
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if (
            isinstance(name, str)
            and name.endswith(_ASSET_SUFFIX)
            and _ASSET_NEEDLE in name
            and "sources" not in name.lower()
        ):
            return asset
    raise RuntimeError(
        f"No matching {_ASSET_NEEDLE}*{_ASSET_SUFFIX} asset in release "
        f"{release.get('tag_name')!r}. Assets: "
        f"{[a.get('name') for a in release.get('assets', [])]}"
    )


def _normalise_tag(version: str) -> str:
    """Accept ``0.24.0`` or ``v0.24.0`` — most repos use the v-prefix."""
    return version if version.startswith("v") else f"v{version}"


# ---------------------------------------------------------------------------
# Download / verify / extract
# ---------------------------------------------------------------------------


def _download(url: str, dst: Path) -> None:
    req = urllib.request.Request(
        url, headers={"User-Agent": "mcp-1c-install-bsl-ls/0.2"}
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, dst.open("wb") as out:  # noqa: S310
            shutil.copyfileobj(resp, out, length=1024 * 1024)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Download failed: {exc}") from exc


def _verify_size(path: Path, expected: int | None) -> None:
    if expected is None:
        return
    actual = path.stat().st_size
    if actual != expected:
        raise RuntimeError(
            f"Size mismatch on {path.name}: got {actual}, expected {expected}"
        )


def _verify_sha256_if_available(release: dict, archive: Path) -> None:
    """Optional integrity check via a sibling ``.sha256`` asset.

    1c-syntax publishes ``<archive>.sha256`` next to recent releases.
    We do best-effort verification: missing asset is not an error
    (older releases don't have it), but a mismatch is fatal.
    """
    target_name = archive.name + ".sha256"
    sha_asset = next(
        (a for a in release.get("assets", []) if a.get("name") == target_name),
        None,
    )
    if sha_asset is None:
        logger.debug(f"No {target_name} sibling asset; skipping checksum verification")
        return

    req = urllib.request.Request(
        sha_asset["browser_download_url"],
        headers={"User-Agent": "mcp-1c-install-bsl-ls/0.2"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            content = resp.read().decode("utf-8", errors="replace").strip()
    except urllib.error.URLError as exc:
        logger.warning(f"Could not fetch {target_name}: {exc}; skipping checksum")
        return

    # Format is usually "<sha256>  <filename>" (BSD style); take the first token.
    expected = content.split()[0].lower() if content else ""
    if len(expected) != 64:
        logger.warning(f"Malformed sha256 in {target_name!r}: {content!r}")
        return

    h = hashlib.sha256()
    with archive.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"SHA-256 mismatch for {archive.name}: got {actual}, expected {expected}"
        )
    logger.debug(f"sha256 ok ({expected[:12]}…)")


def _extract_jar(archive: Path, workdir: Path) -> Path:
    """Pull ``bsl-language-server.jar`` out of the release ZIP.

    The archive layout varies a bit between releases — the JAR is
    sometimes at the root, sometimes under a versioned folder. We pick
    the largest ``.jar`` that doesn't look like a transitive
    dependency, which has been stable across releases 0.21+.
    """
    extracted_dir = workdir / "extracted"
    extracted_dir.mkdir()
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(extracted_dir)

    candidates = sorted(
        (
            p for p in extracted_dir.rglob("*.jar")
            if "bsl-language-server" in p.name
            and "sources" not in p.name
            and "javadoc" not in p.name
        ),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError(
            f"No bsl-language-server*.jar found inside {archive.name}"
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Install bsl-language-server into the mcp-1c cache."
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Specific release tag (e.g. 0.24.0). Default: latest.",
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Override install directory (default: per-user cache root).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if the requested version is already installed.",
    )
    parser.add_argument(
        "--keep-archive",
        action="store_true",
        help="Keep the downloaded .zip alongside the extracted JAR.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    try:
        path = install_bsl_ls(
            version=args.version,
            target_dir=args.target,
            force=args.force,
            keep_archive=args.keep_archive,
        )
    except RuntimeError as exc:
        logger.error(f"Install failed: {exc}")
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
