"""OPC-UA plugin type definitions."""

from dataclasses import dataclass
from typing import Optional, Any
from asyncua.common.node import Node


@dataclass
class VariableNode:
    """Represents an OPC-UA node mapped to a PLC debug variable."""
    node: Node
    debug_var_index: int
    datatype: str
    access_mode: str
    is_array_element: bool = False
    array_index: Optional[int] = None
    array_length: Optional[int] = None  # Length of array (for array nodes only)


@dataclass
class VariableMetadata:
    """Metadata cache for direct memory access."""
    index: int
    address: int
    size: int
    inferred_type: str
