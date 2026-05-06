"""Backward-compatible import shim for the renamed :mod:`pebench` package.

PE-Bench used the internal package name ``flybackbench`` during early
development. The public artifact now uses ``pebench``. This shim keeps old
notebooks and scripts importable while making the new package the source of
truth.
"""

from __future__ import annotations

from importlib import import_module
import sys

_pebench = import_module("pebench")
__path__ = _pebench.__path__
__all__ = getattr(_pebench, "__all__", [])

sys.modules[__name__] = _pebench
