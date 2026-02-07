

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType
from typing import cast
from typing import final
from typing import Generic
from typing import TypeAlias
from typing import TypeVar


_ExcInfo: TypeAlias = tuple[type[BaseException], BaseException, TracebackType | None]
ResultType = TypeVar("ResultType")


class HookCallError(Exception):
    """Hook was called incorrectly."""


@final
class Result(Generic[ResultType]):


    __slots__ = ("_result", "_exception", "_traceback")

    def __init__(
        self,
        result: ResultType | None,
        exception: BaseException | None,
    ) -> None:

        self._result = result
        self._exception = exception
        self._traceback = exception.__traceback__ if exception is not None else None

    @property
    def excinfo(self) -> _ExcInfo | None:

        exc = self._exception
        if exc is None:
            return None
        else:
            return (type(exc), exc, self._traceback)

    @property
    def exception(self) -> BaseException | None:

        return self._exception

    @classmethod
    def from_call(cls, func: Callable[[], ResultType]) -> Result[ResultType]:

        __tracebackhide__ = True
        result = exception = None
        try:
            result = func()
        except BaseException as exc:
            exception = exc
        return cls(result, exception)

    def force_result(self, result: ResultType) -> None:

        self._result = result
        self._exception = None
        self._traceback = None

    def force_exception(self, exception: BaseException) -> None:

        self._result = None
        self._exception = exception
        self._traceback = exception.__traceback__ if exception is not None else None

    def get_result(self) -> ResultType:

        __tracebackhide__ = True
        exc = self._exception
        tb = self._traceback
        if exc is None:
            return cast(ResultType, self._result)
        else:
            raise exc.with_traceback(tb)


_Result = Result
