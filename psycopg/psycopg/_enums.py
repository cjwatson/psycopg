"""
Enum values for psycopg

These values are defined by us and are not necessarily dependent on
libpq-defined enums.
"""

# Copyright (C) 2020-2021 The Psycopg Team

from enum import Enum

from . import pq


class PyFormat(str, Enum):
    """
    Enum representing the format wanted for a query argument.

    The value `AUTO` allows psycopg to choose the best value for a certain
    value.
    """

    __module__ = "psycopg.adapt"

    AUTO = "s"
    """Automatically chosen (``%s`` placeholder)."""
    TEXT = "t"
    """Text parameter (``%t`` placeholder)."""
    BINARY = "b"
    """Binary parameter (``%b`` placeholder)."""

    @classmethod
    def from_pq(cls, fmt: pq.Format) -> "PyFormat":
        return _pg2py[fmt]

    @classmethod
    def as_pq(cls, fmt: "PyFormat") -> pq.Format:
        return _py2pg[fmt]


class IsolationLevel(Enum):
    """
    Enum representing the isolation level for a transaction.
    """

    __module__ = "psycopg"

    READ_UNCOMMITTED = 1
    """:sql:`READ UNCOMMITTED` isolation level."""
    READ_COMMITTED = 2
    """:sql:`READ COMMITTED` isolation level."""
    REPEATABLE_READ = 3
    """:sql:`REPEATABLE READ` isolation level."""
    SERIALIZABLE = 4
    """:sql:`SERIALIZABLE` isolation level."""


_py2pg = {
    PyFormat.TEXT: pq.Format.TEXT,
    PyFormat.BINARY: pq.Format.BINARY,
}

_pg2py = {
    pq.Format.TEXT: PyFormat.TEXT,
    pq.Format.BINARY: PyFormat.BINARY,
}
