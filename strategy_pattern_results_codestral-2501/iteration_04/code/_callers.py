from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import Sequence
from typing import cast
from typing import NoReturn
from typing import TypeAlias
import warnings

from ._hooks import HookImpl
from ._result import HookCallError
from ._result import Result
from ._warnings import PluggyTeardownRaisedWarning

Teardown: TypeAlias = Generator[None, object, object]

def run_old_style_hookwrapper(
    hook_impl: HookImpl, hook_name: str, args: Sequence[object]
) -> Teardown:
    teardown: Teardown = cast(Teardown, hook_impl.function(*args))
    try:
        next(teardown)
    except StopIteration:
        _raise_wrapfail(teardown, "did not yield")
    try:
        res = yield
        result = Result(res, None)
    except BaseException as exc:
        result = Result(None, exc)
    try:
        teardown.send(result)
    except StopIteration:
        pass
    except BaseException as e:
        _warn_teardown_exception(hook_name, hook_impl, e)
        raise
    else:
        _raise_wrapfail(teardown, "has second yield")
    finally:
        teardown.close()
    return result.get_result()

def _raise_wrapfail(
    wrap_controller: Generator[None, object, object],
    msg: str,
) -> NoReturn:
    co = wrap_controller.gi_code
    raise RuntimeError(
        f"wrap_controller at {co.co_name!r} {co.co_filename}:{co.co_firstlineno} {msg}"
    )

def _warn_teardown_exception(
    hook_name: str, hook_impl: HookImpl, e: BaseException
) -> None:
    msg = (
        f"A plugin raised an exception during an old-style hookwrapper teardown.\n"
        f"Plugin: {hook_impl.plugin_name}, Hook: {hook_name}\n"
        f"{type(e).__name__}: {e}\n"
        f"For more information see https://pluggy.readthedocs.io/en/stable/api_reference.html#pluggy.PluggyTeardownRaisedWarning"
    )
    warnings.warn(PluggyTeardownRaisedWarning(msg), stacklevel=6)

def _strategy_hookwrapper(hook_impl: HookImpl, hook_name: str, args: Sequence[object], teardowns: list[Teardown]) -> None:
    function_gen = run_old_style_hookwrapper(hook_impl, hook_name, args)
    next(function_gen)
    teardowns.append(function_gen)

def _strategy_wrapper(hook_impl: HookImpl, hook_name: str, args: Sequence[object], teardowns: list[Teardown]) -> None:
    try:
        res = hook_impl.function(*args)
        function_gen = cast(Generator[None, object, object], res)
        next(function_gen)
        teardowns.append(function_gen)
    except StopIteration:
        _raise_wrapfail(function_gen, "did not yield")

def _strategy_regular(hook_impl: HookImpl, hook_name: str, args: Sequence[object], results: list[object], firstresult: bool) -> None:
    res = hook_impl.function(*args)
    if res is not None:
        results.append(res)
        if firstresult:
            raise StopIteration

STRATEGY_MAP = {
    'hookwrapper': _strategy_hookwrapper,
    'wrapper': _strategy_wrapper,
    'regular': _strategy_regular
}

def _multicall(
    hook_name: str,
    hook_impls: Sequence[HookImpl],
    caller_kwargs: Mapping[str, object],
    firstresult: bool,
) -> object | list[object]:
    __tracebackhide__ = True
    results: list[object] = []
    exception = None
    try:
        teardowns: list[Teardown] = []
        try:
            for hook_impl in reversed(hook_impls):
                try:
                    args = [caller_kwargs[argname] for argname in hook_impl.argnames]
                except KeyError as e:
                    for argname in hook_impl.argnames:
                        if argname not in caller_kwargs:
                            raise HookCallError(
                                f"hook call must provide argument {argname!r}"
                            ) from e

                strategy_key = 'hookwrapper' if hook_impl.hookwrapper else 'wrapper' if hook_impl.wrapper else 'regular'
                try:
                    STRATEGY_MAP[strategy_key](hook_impl, hook_name, args, teardowns, results, firstresult)
                except StopIteration:
                    break
        except BaseException as exc:
            exception = exc
    finally:
        if firstresult:
            result = results[0] if results else None
        else:
            result = results

        for teardown in reversed(teardowns):
            try:
                if exception is not None:
                    try:
                        teardown.throw(exception)
                    except RuntimeError as re:
                        if (
                            isinstance(exception, StopIteration)
                            and re.__cause__ is exception
                        ):
                            teardown.close()
                            continue
                        else:
                            raise
                else:
                    teardown.send(result)
                teardown.close()
            except StopIteration as si:
                result = si.value
                exception = None
                continue
            except BaseException as e:
                exception = e
                continue
            _raise_wrapfail(teardown, "has second yield")

    if exception is not None:
        raise exception
    else:
        return result