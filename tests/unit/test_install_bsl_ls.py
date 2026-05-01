"""Unit tests for the bsl-language-server installer.

We don't hit GitHub here — every external call (urlopen) is patched.
The tests cover the parts that are easy to get subtly wrong: asset
selection, idempotent reinstall, JAR extraction from a zip with the
real (variable) layout.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_1c.scripts import install_bsl_ls as installer


def _fake_release(tag: str = "v0.24.0") -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {
                "name": "bsl-language-server-0.24.0-sources.zip",
                "browser_download_url": "https://example/sources.zip",
                "size": 1,
            },
            {
                "name": "bsl-language-server-0.24.0.zip",
                "browser_download_url": "https://example/main.zip",
                "size": 200,
            },
            {
                "name": "bsl-language-server-0.24.0.zip.sha256",
                "browser_download_url": "https://example/main.zip.sha256",
                "size": 96,
            },
        ],
    }


def _make_release_zip(jar_bytes: bytes = b"FAKE-JAR") -> bytes:
    """Build a real zip whose largest non-source jar is what we want."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bsl-language-server/lib/some-dep.jar", b"X")
        zf.writestr(
            "bsl-language-server/bsl-language-server-0.24.0.jar", jar_bytes
        )
        zf.writestr("README.md", b"hi")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Asset selection
# ---------------------------------------------------------------------------


def test_pick_asset_skips_sources_archive() -> None:
    asset = installer._pick_asset(_fake_release())
    assert "sources" not in asset["name"]
    assert asset["name"].endswith(".zip")


def test_pick_asset_raises_when_nothing_matches() -> None:
    release = {"tag_name": "v0.0", "assets": [{"name": "irrelevant.tgz"}]}
    with pytest.raises(RuntimeError, match="No matching"):
        installer._pick_asset(release)


def test_normalise_tag_adds_v_prefix() -> None:
    assert installer._normalise_tag("0.24.0") == "v0.24.0"
    assert installer._normalise_tag("v0.24.0") == "v0.24.0"


# ---------------------------------------------------------------------------
# JAR extraction
# ---------------------------------------------------------------------------


def test_extract_jar_picks_the_main_jar(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(_make_release_zip(jar_bytes=b"MAIN-JAR-PAYLOAD"))
    extracted = installer._extract_jar(archive, tmp_path)
    assert extracted.read_bytes() == b"MAIN-JAR-PAYLOAD"
    assert "bsl-language-server" in extracted.name
    assert "sources" not in extracted.name


def test_extract_jar_raises_when_no_jar_present(tmp_path: Path) -> None:
    archive = tmp_path / "empty.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.md", b"only docs")
    archive.write_bytes(buf.getvalue())
    with pytest.raises(RuntimeError, match="No bsl-language-server"):
        installer._extract_jar(archive, tmp_path)


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_install_skips_when_version_marker_matches(tmp_path: Path) -> None:
    """Marker file present + jar present + matching version → no work."""
    target = tmp_path / "cache"
    target.mkdir()
    (target / "bsl-language-server.jar").write_bytes(b"PRE-INSTALLED")
    (target / "bsl-language-server.version").write_text("v0.24.0")

    with patch.object(installer, "_fetch_release", return_value=_fake_release()):
        with patch.object(installer, "_download") as fake_download:
            path = installer.install_bsl_ls(target_dir=target)

    assert fake_download.call_count == 0  # idempotent — no download
    assert path.read_bytes() == b"PRE-INSTALLED"


def test_install_force_redownloads_even_when_up_to_date(tmp_path: Path) -> None:
    target = tmp_path / "cache"
    target.mkdir()
    (target / "bsl-language-server.jar").write_bytes(b"OLD")
    (target / "bsl-language-server.version").write_text("v0.24.0")

    def fake_download(url: str, dst: Path) -> None:
        dst.write_bytes(_make_release_zip(jar_bytes=b"REFRESHED"))

    with patch.object(
        installer, "_fetch_release", return_value=_fake_release()
    ), patch.object(
        installer, "_download", side_effect=fake_download
    ), patch.object(
        installer, "_verify_size"
    ), patch.object(
        installer, "_verify_sha256_if_available"
    ):
        path = installer.install_bsl_ls(target_dir=target, force=True)

    assert path.read_bytes() == b"REFRESHED"
    assert (target / "bsl-language-server.version").read_text() == "v0.24.0"


def test_install_full_flow_writes_jar_and_marker(tmp_path: Path) -> None:
    target = tmp_path / "fresh"

    def fake_download(url: str, dst: Path) -> None:
        dst.write_bytes(_make_release_zip(jar_bytes=b"FIRST-INSTALL"))

    with patch.object(
        installer, "_fetch_release", return_value=_fake_release("v0.25.1")
    ), patch.object(
        installer, "_download", side_effect=fake_download
    ), patch.object(
        installer, "_verify_size"
    ), patch.object(
        installer, "_verify_sha256_if_available"
    ):
        path = installer.install_bsl_ls(target_dir=target)

    assert path == target / "bsl-language-server.jar"
    assert path.read_bytes() == b"FIRST-INSTALL"
    assert (target / "bsl-language-server.version").read_text() == "v0.25.1"


# ---------------------------------------------------------------------------
# Cache root resolution
# ---------------------------------------------------------------------------


def test_cache_root_honours_xdg_cache_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    if installer.sys.platform not in ("linux", "linux2"):
        pytest.skip("XDG only relevant on Linux")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert installer.cache_root() == tmp_path / "mcp-1c"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_returns_nonzero_on_failure(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(installer, "install_bsl_ls", fail)
    rc = installer.main([])
    assert rc == 1


def test_main_returns_zero_and_prints_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    fake_path = tmp_path / "jar"
    monkeypatch.setattr(installer, "install_bsl_ls", lambda **kwargs: fake_path)
    rc = installer.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert str(fake_path) in out


# ---------------------------------------------------------------------------
# Sha256 sibling asset
# ---------------------------------------------------------------------------


def test_verify_sha256_mismatch_raises(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"ABC")

    release = _fake_release()
    bad_sha = "0" * 64

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *exc) -> None:
            return None

        def read(self) -> bytes:
            return self._body

    def fake_urlopen(req, timeout=30):
        return FakeResponse(f"{bad_sha}  release.zip\n".encode())

    with patch.object(installer.urllib.request, "urlopen", fake_urlopen):
        # Inject the sibling asset name to match what _verify expects.
        release["assets"].append(
            {
                "name": "release.zip.sha256",
                "browser_download_url": "https://example/release.zip.sha256",
            }
        )
        with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
            installer._verify_sha256_if_available(release, archive)


def test_verify_sha256_missing_sibling_is_silent(tmp_path: Path) -> None:
    archive = tmp_path / "release.zip"
    archive.write_bytes(b"ABC")
    release = {"tag_name": "v0", "assets": []}
    # Should not raise — older releases have no sibling .sha256 asset.
    installer._verify_sha256_if_available(release, archive)
