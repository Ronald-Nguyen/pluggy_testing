from types import SimpleNamespace
import re

import pytest

from pluggy import HookspecMarker
from pluggy import PluginManager
from pluggy._hooks import normalize_hookimpl_opts
from pluggy._hooks import varnames
from pluggy._result import Result
from pluggy._tracing import TagTracer


def fn_no_args() -> None:
    pass


def fn_one(a) -> None:
    pass


def fn_default(a, b=2) -> None:
    pass


def fn_pos_only(a, /, b) -> None:
    pass


def fn_pos_only_default(a, /, b=2) -> None:
    pass


def fn_varargs(a, *args) -> None:
    pass


def fn_kwargs(a, **kwargs) -> None:
    pass


def fn_only_varargs(*args) -> None:
    pass


def fn_only_kwargs(**kwargs) -> None:
    pass


def fn_kw_only(a, *, b) -> None:
    pass


def fn_kw_only_default(a, *, b=2) -> None:
    pass


def fn_mixed(a, /, b, *, c) -> None:
    pass


def fn_mixed_default(a, /, b, c=3, *, d=4) -> None:
    pass


def fn_pos_only_kw_only(a, /, *, b) -> None:
    pass


def fn_pos_only_kw_default(a, /, *, b=1) -> None:
    pass


def fn_two_defaults(a=1, b=2) -> None:
    pass


def fn_pos_only_defaults(a=1, /, b=2) -> None:
    pass


class SimpleInit:
    def __init__(self, x, y=1) -> None:
        pass


class NoInit:
    pass


class InitVarArgs:
    def __init__(self, *args) -> None:
        pass


class InitPosOnly:
    def __init__(self, a, /, b, c=1) -> None:
        pass


class CallOnly:
    def __call__(self, x, y=1) -> None:
        pass


class CallKwOnly:
    def __call__(self, x, *, y) -> None:
        pass


class CallPosOnly:
    def __call__(self, a, /, b) -> None:
        pass


class CallNoArgs:
    def __call__(self) -> None:
        pass


class MethodClass:
    def method(self, x, y=1) -> None:
        pass

    @classmethod
    def cm(cls, x, y=2) -> None:
        pass

    @staticmethod
    def sm(x, y=2) -> None:
        pass


def plugin_function() -> None:
    pass


class PluginClass:
    pass


named_instance = PluginClass()
named_instance.__name__ = "instance_name"
namespace_plugin = SimpleNamespace(__name__="namespace_plugin")


hookspec = HookspecMarker("example")


@pytest.mark.parametrize(
    ("indent", "tags", "args", "expected"),
    [
        (0, ("alpha",), (1,), "1 [alpha]\n"),
        (1, ("alpha",), ("message",), "  message [alpha]\n"),
        (2, ("alpha", "beta"), ("x", "y"), "    x y [alpha:beta]\n"),
        (1, ("alpha", "beta", "gamma"), (True,), "  True [alpha:beta:gamma]\n"),
        (0, ("a",), ("hello", "world"), "hello world [a]\n"),
        (2, ("one", "two"), (0,), "    0 [one:two]\n"),
        (3, ("t",), ("x",), "      x [t]\n"),
        (1, ("t", "u"), (None,), "  None [t:u]\n"),
        (0, ("up",), ("value", 5), "value 5 [up]\n"),
        (2, ("x", "y", "z"), ("mix", 1, 2), "    mix 1 2 [x:y:z]\n"),
        (0, ("num",), (3.14,), "3.14 [num]\n"),
        (1, ("bool",), (False,), "  False [bool]\n"),
        (2, ("spaces", "here"), ("a", "b", "c"), "    a b c [spaces:here]\n"),
        (3, ("triple", "tag", "set"), ("multi",), "      multi [triple:tag:set]\n"),
        (1, ("pair",), ("two", "words", "here"), "  two words here [pair]\n"),
        (0, ("n",), (-1,), "-1 [n]\n"),
        (2, ("unicode",), ("café",), "    café [unicode]\n"),
        (0, ("tab",), ("a\tb",), "a\tb [tab]\n"),
    ],
)
def test_format_message_without_extra(
    indent: int,
    tags: tuple[str, ...],
    args: tuple[object, ...],
    expected: str,
) -> None:
    tracer = TagTracer()
    tracer.indent = indent
    assert tracer._format_message(tags, args) == expected


@pytest.mark.parametrize(
    ("indent", "tags", "args", "expected"),
    [
        (0, ("alpha",), ("message", {"a": 1}), "message [alpha]\n    a: 1\n"),
        (
            1,
            ("alpha", "beta"),
            ("value", {"x": "y"}),
            "  value [alpha:beta]\n      x: y\n",
        ),
        (
            2,
            ("t",),
            ("line", {"a": 1, "b": 2}),
            "    line [t]\n        a: 1\n        b: 2\n",
        ),
        (
            0,
            ("x", "y"),
            ("mix", 1, {"k": 0}),
            "mix 1 [x:y]\n    k: 0\n",
        ),
        (
            1,
            ("extra",),
            ("bool", {"flag": True}),
            "  bool [extra]\n      flag: True\n",
        ),
        (
            0,
            ("none",),
            ("none", {"value": None}),
            "none [none]\n    value: None\n",
        ),
        (
            2,
            ("multi", "dict"),
            ("items", {"a": "A", "b": "B", "c": "C"}),
            "    items [multi:dict]\n        a: A\n        b: B\n        c: C\n",
        ),
        (
            3,
            ("deep",),
            ("level", {"depth": 3}),
            "      level [deep]\n          depth: 3\n",
        ),
        (
            1,
            ("numbers",),
            (1, 2, {"sum": 3}),
            "  1 2 [numbers]\n      sum: 3\n",
        ),
        (
            0,
            ("point",),
            (3.5, {"rounded": 4}),
            "3.5 [point]\n    rounded: 4\n",
        ),
        (
            2,
            ("string",),
            ("text", {"len": 4}),
            "    text [string]\n        len: 4\n",
        ),
        (
            1,
            ("list",),
            ("values", {"items": [1, 2]}),
            "  values [list]\n      items: [1, 2]\n",
        ),
        (
            0,
            ("bool",),
            ("flag", {"state": False}),
            "flag [bool]\n    state: False\n",
        ),
        (
            2,
            ("tuple",),
            ("pair", {"data": (1, 2)}),
            "    pair [tuple]\n        data: (1, 2)\n",
        ),
        (
            1,
            ("dict",),
            ("inner", {"payload": {"a": 1}}),
            "  inner [dict]\n      payload: {'a': 1}\n",
        ),
        (
            0,
            ("multiarg",),
            ("a", "b", {"joined": "a b"}),
            "a b [multiarg]\n    joined: a b\n",
        ),
        (
            2,
            ("spaces",),
            ("sp", {"note": "has space"}),
            "    sp [spaces]\n        note: has space\n",
        ),
        (
            3,
            ("deep", "nest"),
            ("here", {"lvl": "x"}),
            "      here [deep:nest]\n          lvl: x\n",
        ),
    ],
)
def test_format_message_with_extra(
    indent: int,
    tags: tuple[str, ...],
    args: tuple[object, ...],
    expected: str,
) -> None:
    tracer = TagTracer()
    tracer.indent = indent
    assert tracer._format_message(tags, args) == expected


@pytest.mark.parametrize(
    ("callable_obj", "expected"),
    [
        pytest.param(fn_no_args, ((), ()), id="no-args"),
        pytest.param(fn_one, (("a",), ()), id="one-arg"),
        pytest.param(fn_default, (("a",), ("b",)), id="default"),
        pytest.param(fn_pos_only, (("a", "b"), ()), id="pos-only"),
        pytest.param(fn_pos_only_default, (("a",), ("b",)), id="pos-only-default"),
        pytest.param(fn_varargs, (("a",), ()), id="varargs"),
        pytest.param(fn_kwargs, (("a",), ()), id="kwargs"),
        pytest.param(fn_only_varargs, ((), ()), id="only-varargs"),
        pytest.param(fn_only_kwargs, ((), ()), id="only-kwargs"),
        pytest.param(fn_kw_only, (("a",), ()), id="kw-only"),
        pytest.param(fn_kw_only_default, (("a",), ()), id="kw-only-default"),
        pytest.param(fn_mixed, (("a", "b"), ()), id="mixed"),
        pytest.param(fn_mixed_default, (("a", "b"), ("c",)), id="mixed-default"),
        pytest.param(fn_pos_only_kw_only, (("a",), ()), id="pos-only-kw-only"),
        pytest.param(fn_pos_only_kw_default, (("a",), ()), id="pos-only-kw-default"),
        pytest.param(fn_two_defaults, ((), ("a", "b")), id="two-defaults"),
        pytest.param(fn_pos_only_defaults, ((), ("a", "b")), id="pos-only-defaults"),
        pytest.param(SimpleInit, (("x",), ("y",)), id="class-init"),
        pytest.param(NoInit, ((), ()), id="class-no-init"),
        pytest.param(InitVarArgs, ((), ()), id="class-varargs"),
        pytest.param(InitPosOnly, (("a", "b"), ("c",)), id="class-pos-only"),
        pytest.param(CallOnly(), (("x",), ("y",)), id="call-only"),
        pytest.param(CallKwOnly(), (("x",), ()), id="call-kw-only"),
        pytest.param(CallPosOnly(), (("a", "b"), ()), id="call-pos-only"),
        pytest.param(CallNoArgs(), ((), ()), id="call-no-args"),
        pytest.param(MethodClass.method, (("x",), ("y",)), id="method-unbound"),
        pytest.param(MethodClass().method, (("x",), ("y",)), id="method-bound"),
        pytest.param(MethodClass.cm, (("x",), ("y",)), id="classmethod-unbound"),
        pytest.param(MethodClass().cm, (("x",), ("y",)), id="classmethod-bound"),
        pytest.param(MethodClass.sm, (("x",), ("y",)), id="staticmethod"),
    ],
)
def test_varnames_signatures(
    callable_obj: object, expected: tuple[tuple[str, ...], tuple[str, ...]]
) -> None:
    assert varnames(callable_obj) == expected


@pytest.mark.parametrize(
    "value",
    [
        0,
        1,
        -1,
        2.5,
        "text",
        "",
        ("tuple",),
        ["list"],
        {"a": 1},
        object(),
        True,
        None,
    ],
)
def test_result_force_result_clears_exception(value: object) -> None:
    result = Result.from_call(lambda: 1 / 0)
    result.force_result(value)
    assert result.get_result() == value
    assert result.exception is None
    assert result.excinfo is None


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("value"),
        KeyError("key"),
        RuntimeError("runtime"),
        OSError("os"),
        ZeroDivisionError("zero"),
        TypeError("type"),
        IndexError("index"),
        LookupError("lookup"),
        AttributeError("attr"),
        EOFError("eof"),
        StopIteration("stop"),
        AssertionError("assert"),
    ],
)
def test_result_force_exception_overrides_result(exc: BaseException) -> None:
    result = Result.from_call(lambda: "ok")
    result.force_exception(exc)
    assert result.exception is exc
    with pytest.raises(type(exc)) as raised:
        result.get_result()
    assert raised.value is exc


@pytest.mark.parametrize(
    ("plugin", "expected_name"),
    [
        (object(), None),
        ("string", None),
        (42, None),
        (plugin_function, "plugin_function"),
        (lambda: None, "<lambda>"),
        (PluginClass, "PluginClass"),
        (PluginClass(), None),
        (named_instance, "instance_name"),
        (namespace_plugin, "namespace_plugin"),
        (len, "len"),
        (MethodClass.method, "method"),
        (PluginManager, "PluginManager"),
    ],
)
def test_get_canonical_name(
    pm: PluginManager, plugin: object, expected_name: str | None
) -> None:
    name = pm.get_canonical_name(plugin)
    if expected_name is None:
        assert name == str(id(plugin))
    else:
        assert name == expected_name


@pytest.mark.parametrize(
    ("call_type", "kwargs", "missing"),
    [
        ("direct", {}, ("arg1", "arg2", "arg3")),
        ("direct", {"arg1": 1}, ("arg2", "arg3")),
        ("direct", {"arg2": 2}, ("arg1", "arg3")),
        ("direct", {"arg3": 3}, ("arg1", "arg2")),
        ("direct", {"arg1": 1, "arg2": 2}, ("arg3",)),
        ("call_extra", {}, ("arg1", "arg2", "arg3")),
        ("call_extra", {"arg1": 1}, ("arg2", "arg3")),
        ("call_extra", {"arg2": 2}, ("arg1", "arg3")),
        ("call_extra", {"arg3": 3}, ("arg1", "arg2")),
        ("call_extra", {"arg1": 1, "arg2": 2}, ("arg3",)),
    ],
)
def test_verify_all_args_warns(
    pm: PluginManager,
    call_type: str,
    kwargs: dict[str, int],
    missing: tuple[str, ...],
) -> None:
    class Spec:
        @hookspec
        def hello(self, arg1, arg2, arg3):
            pass

    pm.add_hookspecs(Spec)
    missing_names = ", ".join(repr(name) for name in missing)
    pattern = re.escape(
        f"Argument(s) {missing_names} which are declared in the hookspec "
        "cannot be found in this hook call"
    )
    if call_type == "direct":
        with pytest.warns(UserWarning, match=pattern):
            pm.hook.hello(**kwargs)
    else:
        with pytest.warns(UserWarning, match=pattern):
            pm.hook.hello.call_extra([], kwargs=kwargs)


@pytest.mark.parametrize(
    ("call_type", "kwargs", "missing"),
    [
        ("historic", {}, ("arg1", "arg2", "arg3")),
        ("historic", {"arg1": 1}, ("arg2", "arg3")),
        ("historic", {"arg2": 2}, ("arg1", "arg3")),
        ("historic", {"arg3": 3}, ("arg1", "arg2")),
        ("historic", {"arg1": 1, "arg2": 2}, ("arg3",)),
        ("historic_callback", {}, ("arg1", "arg2", "arg3")),
        ("historic_callback", {"arg1": 1}, ("arg2", "arg3")),
        ("historic_callback", {"arg2": 2}, ("arg1", "arg3")),
        ("historic_callback", {"arg3": 3}, ("arg1", "arg2")),
        ("historic_callback", {"arg1": 1, "arg2": 2}, ("arg3",)),
    ],
)
def test_verify_all_args_warns_historic(
    pm: PluginManager,
    call_type: str,
    kwargs: dict[str, int],
    missing: tuple[str, ...],
) -> None:
    class Spec:
        @hookspec(historic=True)
        def hello(self, arg1, arg2, arg3):
            pass

    pm.add_hookspecs(Spec)
    missing_names = ", ".join(repr(name) for name in missing)
    pattern = re.escape(
        f"Argument(s) {missing_names} which are declared in the hookspec "
        "cannot be found in this hook call"
    )
    if call_type == "historic":
        with pytest.warns(UserWarning, match=pattern):
            pm.hook.hello.call_historic(kwargs=kwargs)
    else:
        with pytest.warns(UserWarning, match=pattern):
            pm.hook.hello.call_historic(lambda res: None, kwargs=kwargs)


@pytest.mark.parametrize(
    ("tags_input", "tag_path", "expected_tags"),
    [
        ("a", ("a",), ("a",)),
        ("a:b", ("a", "b"), ("a", "b")),
        (("a", "b"), ("a", "b"), ("a", "b")),
        ("a:b:c", ("a", "b", "c"), ("a", "b", "c")),
        (("root", "child"), ("root", "child"), ("root", "child")),
        ("root:child:grand", ("root", "child", "grand"), ("root", "child", "grand")),
        (("x", "y", "z"), ("x", "y", "z"), ("x", "y", "z")),
        ("x:y:z", ("x", "y", "z"), ("x", "y", "z")),
    ],
)
def test_setprocessor_matches_tags(
    tags_input: str | tuple[str, ...],
    tag_path: tuple[str, ...],
    expected_tags: tuple[str, ...],
) -> None:
    tracer = TagTracer()
    seen: list[tuple[tuple[str, ...], tuple[object, ...]]] = []
    tracer.setprocessor(tags_input, lambda tags, args: seen.append((tags, args)))
    log = tracer.get(tag_path[0])
    for name in tag_path[1:]:
        log = log.get(name)
    log("msg")
    assert seen == [(expected_tags, ("msg",))]


@pytest.mark.parametrize(
    "opts",
    [
        {},
        {"trylast": True},
        {"tryfirst": True},
        {"tryfirst": True, "trylast": True},
        {"optionalhook": True, "specname": "opt"},
        {"optionalhook": True, "trylast": True},
        {"optionalhook": True, "tryfirst": True},
        {"optionalhook": True, "tryfirst": True, "trylast": True},
        {"hookwrapper": True},
        {"hookwrapper": True, "trylast": True},
        {"hookwrapper": True, "tryfirst": True},
        {"hookwrapper": True, "tryfirst": True, "trylast": True, "specname": "wrap"},
        {"hookwrapper": True, "optionalhook": True},
        {"hookwrapper": True, "optionalhook": True, "trylast": True},
        {"hookwrapper": True, "optionalhook": True, "tryfirst": True},
        {"hookwrapper": True, "optionalhook": True, "tryfirst": True, "trylast": True},
        {"wrapper": True},
        {"wrapper": True, "trylast": True},
        {"wrapper": True, "tryfirst": True},
        {"wrapper": True, "tryfirst": True, "trylast": True, "specname": "firstlast"},
        {"wrapper": True, "optionalhook": True},
        {"wrapper": True, "optionalhook": True, "trylast": True},
        {"wrapper": True, "optionalhook": True, "tryfirst": True},
        {"wrapper": True, "optionalhook": True, "tryfirst": True, "trylast": True},
        {"wrapper": True, "hookwrapper": True},
        {"wrapper": True, "hookwrapper": True, "trylast": True},
        {"wrapper": True, "hookwrapper": True, "tryfirst": True},
        {"wrapper": True, "hookwrapper": True, "tryfirst": True, "trylast": True},
        {"wrapper": True, "hookwrapper": True, "optionalhook": True},
        {"wrapper": True, "hookwrapper": True, "optionalhook": True, "trylast": True},
        {"wrapper": True, "hookwrapper": True, "optionalhook": True, "tryfirst": True},
        {
            "wrapper": True,
            "hookwrapper": True,
            "optionalhook": True,
            "tryfirst": True,
            "trylast": True,
            "specname": "all",
        },
    ],
)
def test_normalize_hookimpl_opts_sets_defaults(opts: dict[str, object]) -> None:
    working = dict(opts)
    normalize_hookimpl_opts(working)
    expected = {
        "wrapper": False,
        "hookwrapper": False,
        "optionalhook": False,
        "tryfirst": False,
        "trylast": False,
        "specname": None,
    }
    expected.update(opts)
    assert working == expected
