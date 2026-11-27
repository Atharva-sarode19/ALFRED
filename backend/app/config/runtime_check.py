"""
Environment guards with actionable messages, so a bad install fails with a clear
explanation instead of a deep traceback.

* `check_python()` runs when the app starts.
* `check_pyav()` runs before the Whisper model is used.
"""

from __future__ import annotations

import sys

MIN_PYTHON = (3, 11)
RECOMMENDED_PYTHON = "3.12"
PYAV_MIN_MAJOR = 15
PYAV_MAX_MAJOR = 18  # faster-whisper needs av.open(metadata_errors=...), removed in PyAV 19

SETUP_HINT = (
    "Create the environment with the recommended Python and reinstall: "
    f"`py -{RECOMMENDED_PYTHON} -m venv .venv` (Windows) / `python{RECOMMENDED_PYTHON} -m venv .venv`, "
    "then `pip install -r requirements.txt` (see README, Setup)."
)


class EnvironmentCheckError(RuntimeError):
    pass


def check_python(version: tuple[int, ...] | None = None) -> None:
    current = tuple(version or sys.version_info[:3])
    if current[:2] < MIN_PYTHON:
        raise EnvironmentCheckError(
            f"ALFRED needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ (recommended {RECOMMENDED_PYTHON}); "
            f"this is {'.'.join(map(str, current))}. {SETUP_HINT}"
        )


def check_pyav(version: str | None = None) -> None:
    """Raise if the installed PyAV is outside the range faster-whisper works with."""
    if version is None:
        try:
            import av
        except ImportError as exc:
            raise EnvironmentCheckError(f"PyAV (`av`) is not installed. {SETUP_HINT}") from exc
        version = av.__version__
    try:
        major = int(version.split(".")[0])
    except ValueError:
        return  # unparseable (dev build): do not block
    if not PYAV_MIN_MAJOR <= major <= PYAV_MAX_MAJOR:
        raise EnvironmentCheckError(
            f"PyAV {version} is not compatible with faster-whisper (supported: "
            f"{PYAV_MIN_MAJOR}.x-{PYAV_MAX_MAJOR}.x; newer releases removed `metadata_errors`). "
            f"Fix: `pip install -r requirements.txt` (it pins `av>=15.1,<19`)."
        )
