"""
BSL File Reader.

Reads .bsl files with proper encoding detection.
"""

from pathlib import Path

import aiofiles

from mcp_1c.utils.logger import get_logger

logger = get_logger(__name__)

try:
    from charset_normalizer import from_bytes as _detect_from_bytes

    _HAS_CHARSET_NORMALIZER = True
except ImportError:
    _HAS_CHARSET_NORMALIZER = False

# Common encodings for 1C files
ENCODINGS = ["utf-8-sig", "utf-8", "cp1251", "cp866"]


class BslReader:
    """
    Reader for BSL (1C:Enterprise Script) files.

    Handles various encodings commonly used in 1C configurations.
    """

    def __init__(self) -> None:
        """Initialize reader."""
        self.logger = get_logger(__name__)

    async def read_file(self, path: Path) -> str:
        """
        Read BSL file content.

        Tries multiple encodings to handle different file formats.

        Args:
            path: Path to .bsl file

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file doesn't exist
            UnicodeDecodeError: If no encoding works
        """
        if not path.exists():
            raise FileNotFoundError(f"BSL file not found: {path}")

        # Try each encoding
        for encoding in ENCODINGS:
            try:
                async with aiofiles.open(path, encoding=encoding) as f:
                    content = await f.read()
                    self.logger.debug(f"Read {path} with encoding {encoding}")
                    return content
            except UnicodeDecodeError:
                continue

        raise UnicodeDecodeError(
            "unknown",
            b"",
            0,
            1,
            f"Could not decode {path} with any known encoding",
        )

    async def read_lines(self, path: Path) -> list[str]:
        """
        Read BSL file as list of lines.

        Args:
            path: Path to .bsl file

        Returns:
            List of lines
        """
        content = await self.read_file(path)
        return content.splitlines()

    async def read_range(
        self,
        path: Path,
        start_line: int,
        end_line: int,
    ) -> str:
        """
        Read specific line range from file.

        Args:
            path: Path to .bsl file
            start_line: Start line (1-based)
            end_line: End line (1-based, inclusive)

        Returns:
            Content of specified lines
        """
        lines = await self.read_lines(path)

        # Convert to 0-based indexing
        start_idx = max(0, start_line - 1)
        end_idx = min(len(lines), end_line)

        return "\n".join(lines[start_idx:end_idx])

    def read_file_sync(self, path: Path) -> str:
        """
        Synchronous version of read_file.

        Args:
            path: Path to .bsl file

        Returns:
            File content
        """
        if not path.exists():
            raise FileNotFoundError(f"BSL file not found: {path}")

        for encoding in ENCODINGS:
            try:
                with open(path, encoding=encoding) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue

        raise UnicodeDecodeError(
            "unknown",
            b"",
            0,
            1,
            f"Could not decode {path} with any known encoding",
        )

    def detect_encoding(self, path: Path) -> str:
        """
        Detect file encoding.

        Uses charset-normalizer when available for more accurate detection,
        falling back to sequential encoding trial.

        Args:
            path: Path to file

        Returns:
            Detected encoding name
        """
        with open(path, "rb") as f:
            raw = f.read(4096)

        # Check for BOM first
        if raw.startswith(b"\xef\xbb\xbf"):
            return "utf-8-sig"

        # Try charset-normalizer if available (faster and more accurate)
        if _HAS_CHARSET_NORMALIZER:
            result = _detect_from_bytes(raw)
            best = result.best()
            if best and best.encoding:
                return best.encoding

        # Fallback to sequential encoding trial
        for encoding in ENCODINGS:
            try:
                raw.decode(encoding)
                return encoding
            except (UnicodeDecodeError, LookupError):
                continue

        return "utf-8"
