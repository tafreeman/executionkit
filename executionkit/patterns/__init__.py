"""Composable LLM reasoning patterns.

Re-exports the core pattern functions for convenient access:
:func:`consensus`, :func:`map_reduce`, :func:`refine_loop`,
:func:`react_loop`, and :func:`structured`.
"""

from __future__ import annotations

from executionkit.patterns.consensus import consensus
from executionkit.patterns.map_reduce import map_reduce
from executionkit.patterns.react_loop import react_loop
from executionkit.patterns.refine_loop import refine_loop
from executionkit.patterns.structured import structured

__all__: list[str] = [
    "consensus",
    "map_reduce",
    "react_loop",
    "refine_loop",
    "structured",
]
