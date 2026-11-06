"""Portable project-root path handling; never stores a workstation's folder tree."""
import os
from pathlib import Path, PureWindowsPath

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value):
    """Resolve relative configuration from the Laga root, independent of cwd."""
    path = Path(value).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def reference(path, base):
    """Return a portable POSIX relative reference, including ../ for external data."""
    try:
        return Path(os.path.relpath(Path(path).resolve(), Path(base).resolve())).as_posix()
    except ValueError as error:
        raise ValueError("Portable data and credential references must use the same filesystem volume") from error


def is_absolute_reference(value):
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


def legacy_basename(value):
    """Understand either platform's old persisted paths without using that old root."""
    return PureWindowsPath(value).name if PureWindowsPath(value).is_absolute() else Path(value).name


def display_reference(path, database_directory):
    """Return (relative path, base label) for startup summaries without host paths."""
    path = Path(path).resolve()
    if path.is_relative_to(PROJECT_ROOT):
        return path.relative_to(PROJECT_ROOT).as_posix(), "Laga"
    return reference(path, database_directory), "databaseDirectory"
