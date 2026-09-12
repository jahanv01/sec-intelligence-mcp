"""Locate the prompts/ directory in both a dev checkout and an installed package.

In a dev checkout (`uv run`), source files live under src/tools/, src/edgar/, etc., two
levels below the repo root where prompts/ sits. Once installed (pip/uvx), those same files
land directly in site-packages with no repo root above them -- but the wheel ships prompts/
as a sibling top-level directory in site-packages instead (see pyproject.toml's
force-include), one level up from any given module, not two.
"""

from pathlib import Path


def prompt_path(caller_file: str, filename: str) -> Path:
    """caller_file: pass `__file__` from the calling module."""
    installed = Path(caller_file).resolve().parent.parent / "prompts" / filename
    if installed.exists():
        return installed
    return Path(caller_file).resolve().parents[2] / "prompts" / filename
