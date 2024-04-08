# WARNING: this file is auto-generated by 'async_to_sync.py'
# from the original file 'connection_async.py'
# DO NOT CHANGE! Change the original file instead.
"""
Psycopg connection object (sync version)
"""

# Copyright (C) 2020 The Psycopg Team

from __future__ import annotations

import logging
from time import monotonic
from types import TracebackType
from typing import Any, Generator, Iterator, List, Optional
from typing import Type, Union, cast, overload, TYPE_CHECKING
from contextlib import contextmanager

from . import pq
from . import errors as e
from . import waiting
from .abc import AdaptContext, ConnDict, ConnParam, Params, PQGen, Query, RV
from ._tpc import Xid
from .rows import Row, RowFactory, tuple_row, args_row
from .adapt import AdaptersMap
from ._enums import IsolationLevel
from ._compat import Self
from .conninfo import make_conninfo, conninfo_to_dict
from .conninfo import conninfo_attempts, timeout_from_conninfo
from ._pipeline import Pipeline
from ._encodings import pgconn_encoding
from .generators import notifies
from .transaction import Transaction
from .cursor import Cursor
from .server_cursor import ServerCursor
from ._connection_base import BaseConnection, CursorRow, Notify

from threading import Lock

if TYPE_CHECKING:
    from .pq.abc import PGconn

_WAIT_INTERVAL = 0.1

TEXT = pq.Format.TEXT
BINARY = pq.Format.BINARY

IDLE = pq.TransactionStatus.IDLE
ACTIVE = pq.TransactionStatus.ACTIVE
INTRANS = pq.TransactionStatus.INTRANS

_INTERRUPTED = KeyboardInterrupt

logger = logging.getLogger("psycopg")


class Connection(BaseConnection[Row]):
    """
    Wrapper for a connection to the database.
    """

    __module__ = "psycopg"

    cursor_factory: Type[Cursor[Row]]
    server_cursor_factory: Type[ServerCursor[Row]]
    row_factory: RowFactory[Row]
    _pipeline: Optional[Pipeline]

    def __init__(
        self,
        pgconn: "PGconn",
        row_factory: RowFactory[Row] = cast(RowFactory[Row], tuple_row),
    ):
        super().__init__(pgconn)
        self.row_factory = row_factory
        self.lock = Lock()
        self.cursor_factory = Cursor
        self.server_cursor_factory = ServerCursor

    @classmethod
    def connect(
        cls,
        conninfo: str = "",
        *,
        autocommit: bool = False,
        prepare_threshold: Optional[int] = 5,
        context: Optional[AdaptContext] = None,
        row_factory: Optional[RowFactory[Row]] = None,
        cursor_factory: Optional[Type[Cursor[Row]]] = None,
        **kwargs: ConnParam,
    ) -> Self:
        """
        Connect to a database server and return a new `Connection` instance.
        """

        params = cls._get_connection_params(conninfo, **kwargs)
        timeout = timeout_from_conninfo(params)
        rv = None
        attempts = conninfo_attempts(params)
        for attempt in attempts:
            try:
                conninfo = make_conninfo("", **attempt)
                gen = cls._connect_gen(conninfo, timeout=timeout)
                rv = waiting.wait_conn(gen, interval=_WAIT_INTERVAL)
            except e._NO_TRACEBACK as ex:
                if len(attempts) > 1:
                    logger.debug(
                        "connection attempt failed: host: %r port: %r, hostaddr %r: %s",
                        attempt.get("host"),
                        attempt.get("port"),
                        attempt.get("hostaddr"),
                        str(ex),
                    )
                last_ex = ex
            else:
                break

        if not rv:
            assert last_ex
            raise last_ex.with_traceback(None)

        rv._autocommit = bool(autocommit)
        if row_factory:
            rv.row_factory = row_factory
        if cursor_factory:
            rv.cursor_factory = cursor_factory
        if context:
            rv._adapters = AdaptersMap(context.adapters)
        rv.prepare_threshold = prepare_threshold
        return rv

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if self.closed:
            return

        if exc_type:
            # try to rollback, but if there are problems (connection in a bad
            # state) just warn without clobbering the exception bubbling up.
            try:
                self.rollback()
            except Exception as exc2:
                logger.warning("error ignored in rollback on %s: %s", self, exc2)
        else:
            self.commit()

        # Close the connection only if it doesn't belong to a pool.
        if not getattr(self, "_pool", None):
            self.close()

    @classmethod
    def _get_connection_params(cls, conninfo: str, **kwargs: Any) -> ConnDict:
        """Manipulate connection parameters before connecting."""
        return conninfo_to_dict(conninfo, **kwargs)

    def close(self) -> None:
        """Close the database connection."""
        if self.closed:
            return
        self._closed = True

        # TODO: maybe send a cancel on close, if the connection is ACTIVE?

        self.pgconn.finish()

    @overload
    def cursor(self, *, binary: bool = False) -> Cursor[Row]: ...

    @overload
    def cursor(
        self, *, binary: bool = False, row_factory: RowFactory[CursorRow]
    ) -> Cursor[CursorRow]: ...

    @overload
    def cursor(
        self,
        name: str,
        *,
        binary: bool = False,
        scrollable: Optional[bool] = None,
        withhold: bool = False,
    ) -> ServerCursor[Row]: ...

    @overload
    def cursor(
        self,
        name: str,
        *,
        binary: bool = False,
        row_factory: RowFactory[CursorRow],
        scrollable: Optional[bool] = None,
        withhold: bool = False,
    ) -> ServerCursor[CursorRow]: ...

    def cursor(
        self,
        name: str = "",
        *,
        binary: bool = False,
        row_factory: Optional[RowFactory[Any]] = None,
        scrollable: Optional[bool] = None,
        withhold: bool = False,
    ) -> Union[Cursor[Any], ServerCursor[Any]]:
        """
        Return a new `Cursor` to send commands and queries to the connection.
        """
        self._check_connection_ok()

        if not row_factory:
            row_factory = self.row_factory

        cur: Union[Cursor[Any], ServerCursor[Any]]
        if name:
            cur = self.server_cursor_factory(
                self,
                name=name,
                row_factory=row_factory,
                scrollable=scrollable,
                withhold=withhold,
            )
        else:
            cur = self.cursor_factory(self, row_factory=row_factory)

        if binary:
            cur.format = BINARY

        return cur

    def execute(
        self,
        query: Query,
        params: Optional[Params] = None,
        *,
        prepare: Optional[bool] = None,
        binary: bool = False,
    ) -> Cursor[Row]:
        """Execute a query and return a cursor to read its results."""
        try:
            cur = self.cursor()
            if binary:
                cur.format = BINARY

            return cur.execute(query, params, prepare=prepare)
        except e._NO_TRACEBACK as ex:
            raise ex.with_traceback(None)

    def commit(self) -> None:
        """Commit any pending transaction to the database."""
        with self.lock:
            self.wait(self._commit_gen())

    def rollback(self) -> None:
        """Roll back to the start of any pending transaction."""
        with self.lock:
            self.wait(self._rollback_gen())

    def cancel_safe(self) -> None:
        """Cancel the current operation on the connection.

        This is a non-blocking version of `cancel()` which leverages a more
        secure and improved cancellation feature of the libpq (available from
        version 17).

        In contrast with `cancel()`, it is not appropriate for use in a signal
        handler.

        If the underlying libpq is older than version 17, fall back to
        `cancel()`.
        """
        if self._should_cancel():
            try:
                waiting.wait_conn(self._cancel_gen(), interval=_WAIT_INTERVAL)
            except e.NotSupportedError:
                self.cancel()

    @contextmanager
    def transaction(
        self, savepoint_name: Optional[str] = None, force_rollback: bool = False
    ) -> Iterator[Transaction]:
        """
        Start a context block with a new transaction or nested transaction.

        :param savepoint_name: Name of the savepoint used to manage a nested
            transaction. If `!None`, one will be chosen automatically.
        :param force_rollback: Roll back the transaction at the end of the
            block even if there were no error (e.g. to try a no-op process).
        :rtype: Transaction
        """
        tx = Transaction(self, savepoint_name, force_rollback)
        if self._pipeline:
            with self.pipeline(), tx, self.pipeline():
                yield tx
        else:
            with tx:
                yield tx

    def notifies(
        self, *, timeout: Optional[float] = None, stop_after: Optional[int] = None
    ) -> Generator[Notify, None, None]:
        """
        Yield `Notify` objects as soon as they are received from the database.

        :param timeout: maximum amount of time to wait for notifications.
            `!None` means no timeout.
        :param stop_after: stop after receiving this number of notifications.
            You might actually receive more than this number if more than one
            notifications arrives in the same packet.
        """
        # Allow interrupting the wait with a signal by reducing a long timeout
        # into shorter interval.
        if timeout is not None:
            deadline = monotonic() + timeout
            interval = min(timeout, _WAIT_INTERVAL)
        else:
            deadline = None
            interval = _WAIT_INTERVAL

        nreceived = 0

        while True:
            # Collect notifications. Also get the connection encoding if any
            # notification is received to makes sure that they are consistent.
            try:
                with self.lock:
                    ns = self.wait(notifies(self.pgconn), interval=interval)
                    if ns:
                        enc = pgconn_encoding(self.pgconn)
            except e._NO_TRACEBACK as ex:
                raise ex.with_traceback(None)

            # Emit the notifications received.
            for pgn in ns:
                n = Notify(pgn.relname.decode(enc), pgn.extra.decode(enc), pgn.be_pid)
                yield n
                nreceived += 1

            # Stop if we have received enough notifications.
            if stop_after is not None and nreceived >= stop_after:
                break

            # Check the deadline after the loop to ensure that timeout=0
            # polls at least once.
            if deadline:
                interval = min(_WAIT_INTERVAL, deadline - monotonic())
                if interval < 0.0:
                    break

    @contextmanager
    def pipeline(self) -> Iterator[Pipeline]:
        """Context manager to switch the connection into pipeline mode."""
        with self.lock:
            self._check_connection_ok()

            pipeline = self._pipeline
            if pipeline is None:
                # WARNING: reference loop, broken ahead.
                pipeline = self._pipeline = Pipeline(self)

        try:
            with pipeline:
                yield pipeline
        finally:
            if pipeline.level == 0:
                with self.lock:
                    assert pipeline is self._pipeline
                    self._pipeline = None

    def wait(self, gen: PQGen[RV], interval: Optional[float] = _WAIT_INTERVAL) -> RV:
        """
        Consume a generator operating on the connection.

        The function must be used on generators that don't change connection
        fd (i.e. not on connect and reset).
        """
        try:
            return waiting.wait(gen, self.pgconn.socket, interval=interval)
        except _INTERRUPTED:
            if self.pgconn.transaction_status == ACTIVE:
                # On Ctrl-C, try to cancel the query in the server, otherwise
                # the connection will remain stuck in ACTIVE state.
                self.cancel_safe()
                try:
                    waiting.wait(gen, self.pgconn.socket, interval=interval)
                except e.QueryCanceled:
                    pass  # as expected
            raise

    def _set_autocommit(self, value: bool) -> None:
        self.set_autocommit(value)

    def set_autocommit(self, value: bool) -> None:
        """Method version of the `~Connection.autocommit` setter."""
        with self.lock:
            self.wait(self._set_autocommit_gen(value))

    def _set_isolation_level(self, value: Optional[IsolationLevel]) -> None:
        self.set_isolation_level(value)

    def set_isolation_level(self, value: Optional[IsolationLevel]) -> None:
        """Method version of the `~Connection.isolation_level` setter."""
        with self.lock:
            self.wait(self._set_isolation_level_gen(value))

    def _set_read_only(self, value: Optional[bool]) -> None:
        self.set_read_only(value)

    def set_read_only(self, value: Optional[bool]) -> None:
        """Method version of the `~Connection.read_only` setter."""
        with self.lock:
            self.wait(self._set_read_only_gen(value))

    def _set_deferrable(self, value: Optional[bool]) -> None:
        self.set_deferrable(value)

    def set_deferrable(self, value: Optional[bool]) -> None:
        """Method version of the `~Connection.deferrable` setter."""
        with self.lock:
            self.wait(self._set_deferrable_gen(value))

    def tpc_begin(self, xid: Union[Xid, str]) -> None:
        """
        Begin a TPC transaction with the given transaction ID `!xid`.
        """
        with self.lock:
            self.wait(self._tpc_begin_gen(xid))

    def tpc_prepare(self) -> None:
        """
        Perform the first phase of a transaction started with `tpc_begin()`.
        """
        try:
            with self.lock:
                self.wait(self._tpc_prepare_gen())
        except e.ObjectNotInPrerequisiteState as ex:
            raise e.NotSupportedError(str(ex)) from None

    def tpc_commit(self, xid: Union[Xid, str, None] = None) -> None:
        """
        Commit a prepared two-phase transaction.
        """
        with self.lock:
            self.wait(self._tpc_finish_gen("COMMIT", xid))

    def tpc_rollback(self, xid: Union[Xid, str, None] = None) -> None:
        """
        Roll back a prepared two-phase transaction.
        """
        with self.lock:
            self.wait(self._tpc_finish_gen("ROLLBACK", xid))

    def tpc_recover(self) -> List[Xid]:
        self._check_tpc()
        status = self.info.transaction_status
        with self.cursor(row_factory=args_row(Xid._from_record)) as cur:
            cur.execute(Xid._get_recover_query())
            res = cur.fetchall()

        if status == IDLE and self.info.transaction_status == INTRANS:
            self.rollback()

        return res
