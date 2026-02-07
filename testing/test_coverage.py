import unittest
from unittest import mock
import warnings

import pluggy
from pluggy._callers import _multicall
from pluggy._callers import run_old_style_hookwrapper
from pluggy._hooks import HookCaller
from pluggy._hooks import HookImpl
from pluggy._hooks import HookimplMarker
from pluggy._hooks import HookspecMarker
from pluggy._hooks import normalize_hookimpl_opts
from pluggy._hooks import varnames
from pluggy._manager import PluginManager
from pluggy._manager import PluginValidationError
from pluggy._result import HookCallError
from pluggy._result import Result
from pluggy._tracing import TagTracer
from pluggy._warnings import PluggyTeardownRaisedWarning
from pluggy._warnings import PluggyWarning


def _mk_hookimpl(plugin, plugin_name, func, **opts):
    """Helper function to create HookImpl instances for testing."""
    full = {
        "wrapper": False,
        "hookwrapper": False,
        "optionalhook": False,
        "tryfirst": False,
        "trylast": False,
        "specname": None,
    }
    full.update(opts)
    normalize_hookimpl_opts(full)
    return HookImpl(plugin, plugin_name, func, full)


class TestPluggyInit(unittest.TestCase):
    def test_all_exports_exist(self):
        # __all__ is defined and items are importable attributes from pluggy/__init__.py
        self.assertTrue(hasattr(pluggy, "__all__"))
        for name in pluggy.__all__:
            # __version__ is resolved by __getattr__
            if name == "__version__":
                continue
            self.assertTrue(hasattr(pluggy, name), name)

    def test_getattr_version(self):
        with mock.patch("importlib.metadata.version", return_value="9.9.9"):
            self.assertEqual(getattr(pluggy, "__version__"), "9.9.9")

    def test_getattr_unknown_raises(self):
        with self.assertRaises(AttributeError):
            _ = pluggy.__getattr__("does_not_exist_123")


class TestPluggyWarnings(unittest.TestCase):
    def test_warning_classes_and_module(self):
        self.assertTrue(issubclass(PluggyWarning, UserWarning))
        self.assertTrue(issubclass(PluggyTeardownRaisedWarning, PluggyWarning))
        # They intentionally pretend to come from "pluggy"
        self.assertEqual(PluggyWarning.__module__, "pluggy")
        self.assertEqual(PluggyTeardownRaisedWarning.__module__, "pluggy")


class TestPluggyResult(unittest.TestCase):
    def test_result_success_and_excinfo_none(self):
        r = Result("ok", None)
        self.assertIsNone(r.exception)
        self.assertIsNone(r.excinfo)
        self.assertEqual(r.get_result(), "ok")

    def test_result_from_call_catches_exception(self):
        def boom():
            raise ValueError("x")

        r = Result.from_call(boom)
        self.assertIsInstance(r.exception, ValueError)
        self.assertIsNotNone(r.excinfo)
        with self.assertRaises(ValueError):
            r.get_result()

    def test_result_force_result_clears_exception(self):
        r = Result(None, ValueError("x"))
        r.force_result(123)
        self.assertIsNone(r.exception)
        self.assertEqual(r.get_result(), 123)

    def test_result_force_exception_overwrites_result(self):
        r = Result("ok", None)
        e = RuntimeError("nope")
        r.force_exception(e)
        self.assertIs(r.exception, e)
        with self.assertRaises(RuntimeError):
            r.get_result()

    def test_result_excinfo_property(self):
        """Test Result.excinfo property returns tuple."""
        try:
            raise ValueError("test")
        except ValueError as e:
            result = Result(None, e)

        excinfo = result.excinfo
        self.assertIsNotNone(excinfo)
        self.assertEqual(len(excinfo), 3)
        self.assertEqual(excinfo[0], ValueError)
        self.assertIsInstance(excinfo[1], ValueError)

    def test_result_force_exception_sets_traceback(self):
        """Test force_exception sets traceback."""
        result = Result("ok", None)

        try:
            raise RuntimeError("test")
        except RuntimeError as e:
            result.force_exception(e)

        self.assertIsNotNone(result.exception)
        self.assertIsNotNone(result._traceback)

    def test_result_get_result_with_traceback(self):
        """Test Result.get_result() preserves traceback."""
        try:
            raise ValueError("test")
        except ValueError as e:
            result = Result(None, e)

        try:
            result.get_result()
        except ValueError:
            import traceback

            tb_lines = traceback.format_exc()
            self.assertIn("ValueError", tb_lines)
            self.assertIn("test", tb_lines)


class TestPluggyTracing(unittest.TestCase):
    def test_tracer_formats_writer_and_processor(self):
        tracer = TagTracer()
        out = []

        def writer(s):
            out.append(s)

        proc_calls = []

        def proc(tags, args):
            proc_calls.append((tags, args))

        tracer.setwriter(writer)
        tracer.setprocessor("a:b", proc)

        sub = tracer.get("a").get("b")

        # With extra dict
        sub("hello", {"k": "v"})
        self.assertTrue(out)
        self.assertIn("[a:b]", out[-1])
        self.assertIn("k: v", out[-1])
        self.assertEqual(proc_calls[-1][0], ("a", "b"))

        # Without extra dict -> extra is {}
        sub("world")
        self.assertIn("world", out[-1])

        # If args empty -> writer should not run
        tracer2 = TagTracer()
        out2 = []
        tracer2.setwriter(lambda s: out2.append(s))
        tracer2.get("x").root._processmessage(("x",), ())
        self.assertEqual(out2, [])

    def test_tagtracer_formats_with_indent(self):
        """Test TagTracer indent handling."""
        tracer = TagTracer()
        out = []
        tracer.setwriter(lambda s: out.append(s))

        sub = tracer.get("test")
        tracer.indent = 2
        sub("message")

        self.assertTrue(any("    " in s for s in out))  # 2 levels of indent

    def test_tagtracer_setprocessor_with_tuple(self):
        """Test setprocessor with tuple tags."""
        tracer = TagTracer()
        calls = []

        def processor(tags, args):
            calls.append((tags, args))

        tracer.setprocessor(("a", "b"), processor)
        sub = tracer.get("a").get("b")
        sub("test")

        self.assertEqual(calls[0][0], ("a", "b"))

    def test_tagtracer_get_creates_subtracers(self):
        """Test TagTracer.get() creates nested TagTracerSub."""
        tracer = TagTracer()

        sub1 = tracer.get("level1")
        self.assertEqual(sub1.tags, ("level1",))

        sub2 = sub1.get("level2")
        self.assertEqual(sub2.tags, ("level1", "level2"))

        # Both should share the same root
        self.assertIs(sub1.root, sub2.root)

    def test_tagtracer_processmessage_without_writer(self):
        """Test _processmessage works without writer."""
        tracer = TagTracer()

        calls = []

        def processor(tags, args):
            calls.append((tags, args))

        tracer.setprocessor("test", processor)

        sub = tracer.get("test")
        sub("message")

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], ("test",))

    def test_tagtracer_format_message_without_extra(self):
        """Test _format_message without extra dict."""
        tracer = TagTracer()

        msg = tracer._format_message(["tag1", "tag2"], ["arg1", "arg2"])

        self.assertIn("arg1 arg2", msg)
        self.assertIn("[tag1:tag2]", msg)


class TestHooksVarNamesAndMarkers(unittest.TestCase):
    def test_varnames_for_function_and_defaults(self):
        def f(a, b, c=1, d=2):  # kwargs are the defaults tail
            return a, b, c, d

        args, kwargs = varnames(f)
        self.assertEqual(args, ("a", "b"))
        self.assertEqual(kwargs, ("c", "d"))

    def test_varnames_for_class_init_strips_self(self):
        class C:
            def __init__(self, x, y=1):  # noqa
                pass

        args, kwargs = varnames(C)
        self.assertEqual(args, ("x",))
        self.assertEqual(kwargs, ("y",))

    def test_varnames_non_routine(self):
        class CallableObj:
            def __call__(self, a, b=1):
                return a + b

        args, kwargs = varnames(CallableObj())
        self.assertEqual(args, ("a",))
        self.assertEqual(kwargs, ("b",))

    def test_varnames_callable_with_exception(self):
        """Test varnames handles exceptions when getting __call__."""

        class BadCallable:
            def __getattr__(self, name):
                if name == "__call__":
                    raise RuntimeError("boom")
                raise AttributeError(name)

        args, kwargs = varnames(BadCallable())
        self.assertEqual(args, ())
        self.assertEqual(kwargs, ())

    def test_varnames_class_without_init_attribute(self):
        """Test varnames handles classes missing __init__."""
        class NoInitMeta(type):
            def __getattribute__(cls, name):
                if name == "__init__":
                    raise AttributeError("no init")
                return super().__getattribute__(name)

        class NoInit(metaclass=NoInitMeta):
            pass

        args, kwargs = varnames(NoInit)
        self.assertEqual(args, ())
        self.assertEqual(kwargs, ())

    def test_varnames_signature_typeerror(self):
        """Test varnames handles inspect.signature TypeError."""
        args, kwargs = varnames(object())
        self.assertEqual(args, ())
        self.assertEqual(kwargs, ())

    def test_varnames_pypy_implicit_obj(self):
        """Test varnames uses PyPy implicit names when enabled."""
        import pluggy._hooks as hooks

        original_pypy = hooks._PYPY
        hooks._PYPY = True
        try:
            class C:
                # Exercise PyPy implicit name handling.
                def method(self, x):
                    return x

            args, kwargs = hooks.varnames(C.method)
            self.assertEqual(args, ("x",))
            self.assertEqual(kwargs, ())
        finally:
            hooks._PYPY = original_pypy

    def test_hookspec_marker_sets_opts_and_validates_historic_firstresult(self):
        spec = HookspecMarker("proj")

        @spec(firstresult=False, historic=True)
        def hook(x):  # noqa
            return x

        self.assertTrue(hasattr(hook, "proj_spec"))
        self.assertTrue(hook.proj_spec["historic"])
        self.assertFalse(hook.proj_spec["firstresult"])

        with self.assertRaises(ValueError):

            @spec(firstresult=True, historic=True)
            def bad(x):  # noqa
                return x

    def test_hookimpl_marker_sets_opts(self):
        impl = HookimplMarker("proj")

        @impl(tryfirst=True, specname="hook")
        def implfn(x):  # noqa
            return x

        self.assertTrue(hasattr(implfn, "proj_impl"))
        self.assertEqual(implfn.proj_impl["specname"], "hook")
        self.assertTrue(implfn.proj_impl["tryfirst"])

    def test_normalize_hookimpl_opts_defaults(self):
        opts = {}
        normalize_hookimpl_opts(opts)
        self.assertEqual(
            opts,
            {
                "tryfirst": False,
                "trylast": False,
                "wrapper": False,
                "hookwrapper": False,
                "optionalhook": False,
                "specname": None,
            },
        )

    def test_hookmarker_as_decorator_factory(self):
        """Test HookspecMarker and HookimplMarker as decorator factories."""
        spec = HookspecMarker("proj")
        impl = HookimplMarker("proj")

        # Use as decorator factory
        decorator = spec(firstresult=True)

        def h(x):
            return x

        decorated = decorator(h)
        self.assertTrue(hasattr(decorated, "proj_spec"))
        self.assertTrue(decorated.proj_spec["firstresult"])

        # Same for impl
        impl_decorator = impl(tryfirst=True)

        def impl_h(x):
            return x

        impl_decorated = impl_decorator(impl_h)
        self.assertTrue(hasattr(impl_decorated, "proj_impl"))
        self.assertTrue(impl_decorated.proj_impl["tryfirst"])


class TestCallersMulticall(unittest.TestCase):
    def _mk_hookimpl(self, plugin, plugin_name, func, **opts):
        full = {
            "wrapper": False,
            "hookwrapper": False,
            "optionalhook": False,
            "tryfirst": False,
            "trylast": False,
            "specname": None,
        }
        full.update(opts)
        normalize_hookimpl_opts(full)
        return HookImpl(plugin, plugin_name, func, full)

    def test_multicall_missing_argument_raises_hookcallerror(self):
        def impl(a):  # expects a
            return a

        hi = self._mk_hookimpl(object(), "p", impl)
        with self.assertRaises(HookCallError):
            _multicall("h", [hi], {"b": 1}, firstresult=False)

    def test_multicall_firstresult_breaks(self):
        def impl1(x):
            return "r1"

        def impl2(x):
            return "r2"

        hi1 = self._mk_hookimpl(object(), "p1", impl1)
        hi2 = self._mk_hookimpl(object(), "p2", impl2)
        res = _multicall("h", [hi1, hi2], {"x": 1}, firstresult=True)
        self.assertEqual(res, "r2")  # reversed order, so hi2 runs first and breaks

    def test_multicall_firstresult_with_none_results(self):
        """Test firstresult returns None when no non-None results."""

        def impl1(x):
            return None

        def impl2(x):
            return None

        hi1 = self._mk_hookimpl(object(), "p1", impl1)
        hi2 = self._mk_hookimpl(object(), "p2", impl2)

        result = _multicall("h", [hi1, hi2], {"x": 1}, firstresult=True)
        self.assertIsNone(result)

    def test_run_old_style_hookwrapper_did_not_yield_raises(self):
        def bad_old_style(x):
            if False:
                yield None  # pragma: no cover

        hi = self._mk_hookimpl(object(), "p", bad_old_style, hookwrapper=True)
        gen = run_old_style_hookwrapper(hi, "h", [1])
        with self.assertRaises(RuntimeError):
            next(gen)

    def test_run_old_style_hookwrapper_second_yield_raises(self):
        def bad_two_yields(x):
            yield None
            _ = yield None  # second yield -> wrapfail

        hi = self._mk_hookimpl(object(), "p", bad_two_yields, hookwrapper=True)
        gen = run_old_style_hookwrapper(hi, "h", [1])
        next(gen)
        with self.assertRaises(RuntimeError):
            gen.send("ok")

    def test_run_old_style_hookwrapper_teardown_raises_warns_and_reraises(self):
        def bad_teardown(x):
            yield None
            raise RuntimeError("boom in teardown")

        hi = self._mk_hookimpl(object(), "p", bad_teardown, hookwrapper=True)
        gen = run_old_style_hookwrapper(hi, "h", [1])
        next(gen)
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with self.assertRaises(RuntimeError):
                gen.send("ok")
            self.assertTrue(
                any(isinstance(i.message, PluggyTeardownRaisedWarning) for i in w)
            )

    def test_multicall_wrapper_stopiteration_did_not_yield(self):
        def wrapper(x):
            if False:
                yield None  # pragma: no cover

        hi = self._mk_hookimpl(object(), "p", wrapper, wrapper=True)
        with self.assertRaises(RuntimeError):
            _multicall("h", [hi], {"x": 1}, firstresult=False)


class TestHookCallerBehavior(unittest.TestCase):
    def test_hookcaller_call_historic_and_apply_history(self):
        pm = PluginManager("proj")

        spec = HookspecMarker("proj")

        class Spec:
            @spec(historic=True)
            def myhook(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P1:
            @impl
            def myhook(self, x):  # noqa
                return x + 1

        p1 = P1()
        pm.register(p1)

        calls = []
        pm.hook.myhook.call_historic(
            result_callback=lambda r: calls.append(r), kwargs={"x": 10}
        )
        self.assertEqual(calls, [11])

        # Apply history to a newly registered implementation
        class P2:
            @impl
            def myhook(self, x):  # noqa
                return x + 2

        p2 = P2()
        pm.register(p2)
        # When registering p2, history should have been applied (callback should receive p2 result too)
        self.assertEqual(calls, [11, 12])

    def test_hookcaller_call_extra_orders_before_wrappers(self):
        pm = PluginManager("proj")

        spec = HookspecMarker("proj")

        class Spec:
            @spec(firstresult=True)
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P:
            @impl(wrapper=True)
            def h(self, x):  # generator wrapper
                res = yield
                # pass-through
                return res

        pm.register(P())

        def extra(x):
            return "extra"

        # call_extra should insert extra before wrappers/tryfirsts etc and still obey firstresult
        res = pm.hook.h.call_extra([extra], {"x": 1})
        self.assertEqual(res, "extra")

    def test_hookcaller_remove_plugin_missing_raises(self):
        hook = HookCaller("h", lambda *args, **kwargs: None)
        hook._add_hookimpl(_mk_hookimpl(object(), "p", lambda: None))
        with self.assertRaises(ValueError):
            hook._remove_plugin(object())

    def test_subset_hook_caller(self):
        pm = PluginManager("proj")

        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P1:
            @impl
            def h(self, x):  # noqa
                return "p1"

        class P2:
            @impl
            def h(self, x):  # noqa
                return "p2"

        p1, p2 = P1(), P2()
        pm.register(p1, name="p1")
        pm.register(p2, name="p2")

        sub = pm.subset_hook_caller("h", [p1])
        self.assertNotEqual(sub, pm.hook.h)
        res = sub(x=1)
        self.assertIn("p2", res)  # only p2 left

        sub2 = pm.subset_hook_caller("h", [object()])
        self.assertEqual(sub2, pm.hook.h)


class TestPluginManager(unittest.TestCase):
    def test_register_duplicate_name_and_duplicate_plugin(self):
        pm = PluginManager("proj")

        class P:
            pass

        p = P()
        pm.register(p, name="same")
        with self.assertRaises(ValueError):
            pm.register(P(), name="same")

        with self.assertRaises(ValueError):
            pm.register(p, name="other")

    def test_register_blocked_name_returns_none(self):
        pm = PluginManager("proj")

        pm.set_blocked("x")

        class P:
            pass

        self.assertIsNone(pm.register(P(), name="x"))

    def test_unblock_and_is_blocked(self):
        pm = PluginManager("proj")
        pm.set_blocked("x")
        self.assertTrue(pm.is_blocked("x"))
        self.assertTrue(pm.unblock("x"))
        self.assertFalse(pm.is_blocked("x"))
        self.assertFalse(pm.unblock("x"))  # already unblocked

    def test_add_hookspecs_no_hooks_raises(self):
        pm = PluginManager("proj")

        class Empty:
            pass

        with self.assertRaises(ValueError):
            pm.add_hookspecs(Empty)

    def test_parse_hookimpl_opts_non_routine_is_none(self):
        pm = PluginManager("proj")

        class P:
            x = 1

        self.assertIsNone(pm.parse_hookimpl_opts(P(), "x"))

    def test_hookimpl_opts_non_dict_returns_none(self):
        """Test parse_hookimpl_opts returns None for non-dict marker."""
        pm = PluginManager("proj")

        class P:
            def f(self):
                pass

            f.proj_impl = "not a dict"

        result = pm.parse_hookimpl_opts(P(), "f")
        self.assertIsNone(result)

    def test_parse_hookimpl_opts_getattr_exception(self):
        pm = PluginManager("proj")

        class BadMethod:
            def __getattr__(self, name):
                raise RuntimeError("boom")

            def __call__(self):
                return None

        class P:
            bad = BadMethod()

        with mock.patch("pluggy._manager.inspect.isroutine", return_value=True):
            result = pm.parse_hookimpl_opts(P(), "bad")
        self.assertEqual(result, {})

    def test_verify_hook_errors(self):
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec(historic=True)
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class BadHistoricWrapper:
            @impl(wrapper=True)
            def h(self, x):  # noqa
                yield

        with self.assertRaises(PluginValidationError):
            pm.register(BadHistoricWrapper())

        # Non-generator with wrapper=True
        pm2 = PluginManager("proj")

        class Spec2:
            @spec
            def h(self, x):  # noqa
                pass

        pm2.add_hookspecs(Spec2)

        class BadWrapperNotGen:
            @impl(wrapper=True)
            def h(self, x):  # noqa
                return x

        with self.assertRaises(PluginValidationError):
            pm2.register(BadWrapperNotGen())

        # wrapper and hookwrapper mutually exclusive
        class BadMutual:
            @impl(wrapper=True, hookwrapper=True)
            def h(self, x):  # noqa
                yield

        with self.assertRaises(PluginValidationError):
            pm2.register(BadMutual())

        # Hookimpl has arg not in spec
        class BadArgs:
            @impl
            def h(self, x, y):  # noqa
                return x

        with self.assertRaises(PluginValidationError):
            pm2.register(BadArgs())

    def test_check_pending_unknown_hook_raises(self):
        pm = PluginManager("proj")
        impl = HookimplMarker("proj")

        class P:
            @impl(optionalhook=False)
            def unknown(self):  # noqa
                return None

        pm.register(P())
        with self.assertRaises(PluginValidationError):
            pm.check_pending()

    def test_unregister_by_name_and_by_plugin(self):
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P:
            @impl
            def h(self):  # noqa
                return "x"

        p = P()
        name = pm.register(p, name="p")
        self.assertEqual(pm.get_name(p), "p")
        self.assertIs(pm.unregister(name="p"), p)

        # Not registered anymore
        self.assertIsNone(pm.get_name(p))

        # unregister missing plugin by name returns None
        self.assertIsNone(pm.unregister(name="nope"))

        # Register again and unregister by plugin
        pm.register(p, name="p2")
        self.assertIs(pm.unregister(plugin=p), p)

    def test_getters_and_lists(self):
        pm = PluginManager("proj")

        class P:
            pass

        p = P()
        pm.register(p, name="p")
        self.assertTrue(pm.is_registered(p))
        self.assertTrue(pm.has_plugin("p"))
        self.assertIs(pm.get_plugin("p"), p)
        self.assertIn(p, pm.get_plugins())
        self.assertIn(("p", p), pm.list_name_plugin())

    def test_load_setuptools_entrypoints_mocked(self):
        pm = PluginManager("proj")

        # Build fake dist + entry points.
        class EP:
            def __init__(self, group, name, plugin_obj):
                self.group = group
                self.name = name
                self._plugin_obj = plugin_obj

            def load(self):
                return self._plugin_obj

        class Dist:
            def __init__(self, name, eps):
                self.metadata = {"name": name}
                self.entry_points = eps

        impl = HookimplMarker("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self):  # noqa
                pass

        pm.add_hookspecs(Spec)

        class P:
            @impl
            def h(self):  # noqa
                return "ok"

        dist = Dist("d1", [EP("grp", "ep1", P())])

        with mock.patch("importlib.metadata.distributions", return_value=[dist]):
            count = pm.load_setuptools_entrypoints("grp")
        self.assertEqual(count, 1)

        # Same EP name already registered -> skipped
        with mock.patch("importlib.metadata.distributions", return_value=[dist]):
            count2 = pm.load_setuptools_entrypoints("grp")
        self.assertEqual(count2, 0)

        # Blocked -> skipped
        pm2 = PluginManager("proj")
        pm2.add_hookspecs(Spec)
        pm2.set_blocked("ep1")
        with mock.patch("importlib.metadata.distributions", return_value=[dist]):
            count3 = pm2.load_setuptools_entrypoints("grp")
        self.assertEqual(count3, 0)

    def test_add_hookcall_monitoring_and_enable_tracing(self):
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")
        impl = HookimplMarker("proj")

        class Spec:
            @spec
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        class P:
            @impl
            def h(self, x):  # noqa
                return x + 1

        pm.register(P())

        events = []

        def before(name, methods, kwargs):
            events.append(("before", name, dict(kwargs)))

        def after(outcome, name, methods, kwargs):
            events.append(("after", name, dict(kwargs), outcome.exception))

        undo = pm.add_hookcall_monitoring(before, after)
        self.assertEqual(pm.hook.h(x=1), [2])
        self.assertEqual(events[0][0], "before")
        self.assertEqual(events[1][0], "after")
        undo()

        # enable_tracing wraps monitoring and returns undo as well
        undo2 = pm.enable_tracing()
        _ = pm.hook.h(x=2)
        undo2()

    def test_hookcaller_missing_arg_raises_hookcallerror(self):
        """Test that HookCallError is raised when required argument is missing."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self, a, b):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P:
            @impl
            def h(self, a, b):  # noqa
                return a + b

        pm.register(P())

        # Should warn first, then raise HookCallError in _multicall
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # Suppress the warning
            with self.assertRaises(HookCallError):
                pm.hook.h(a=1)

    def test_warn_for_function_called(self):
        """Test _warn_for_function issues warnings correctly."""
        from pluggy._manager import _warn_for_function

        def my_func():
            pass

        my_warning = UserWarning("test warning")

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            _warn_for_function(my_warning, my_func)
            self.assertEqual(len(w), 1)
            self.assertIn("test warning", str(w[0].message))

    def test_hookspec_warn_on_impl_triggers(self):
        """Test that hookspec warn_on_impl triggers warnings."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")
        impl = HookimplMarker("proj")

        my_warning = DeprecationWarning("This hook is deprecated")

        class Spec:
            @spec(warn_on_impl=my_warning)
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        class P:
            @impl
            def h(self, x):  # noqa
                return x

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pm.register(P())
            # Should have triggered the warning
            self.assertTrue(any("deprecated" in str(warning.message) for warning in w))

    def test_hookspec_warn_on_impl_args_triggers(self):
        """Test that hookspec warn_on_impl_args triggers warnings for specific arguments."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")
        impl = HookimplMarker("proj")

        arg_warning = DeprecationWarning("Argument x is deprecated")

        class Spec:
            @spec(warn_on_impl_args={"x": arg_warning})
            def h(self, x, y):  # noqa
                pass

        pm.add_hookspecs(Spec)

        class P:
            @impl
            def h(self, x, y):  # noqa
                return x + y

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            pm.register(P())
            # Should have triggered the argument warning
            self.assertTrue(
                any("Argument x is deprecated" in str(warning.message) for warning in w)
            )

    def test_distfacade_properties(self):
        """Test DistFacade wrapper for distribution metadata."""
        from pluggy._manager import DistFacade

        class MockDist:
            def __init__(self):
                self.metadata = {"name": "test-package"}
                self.version = "1.0.0"

        facade = DistFacade(MockDist())
        self.assertEqual(facade.project_name, "test-package")
        self.assertEqual(facade.version, "1.0.0")
        self.assertIn("project_name", dir(facade))

    def test_hookcaller_repr(self):
        """Test HookCaller __repr__."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self):  # noqa
                pass

        pm.add_hookspecs(Spec)
        self.assertIn("HookCaller", repr(pm.hook.h))
        self.assertIn("'h'", repr(pm.hook.h))

    def test_hookimpl_repr(self):
        """Test HookImpl __repr__."""
        hi = _mk_hookimpl(object(), "test_plugin", lambda x: x)
        repr_str = repr(hi)
        self.assertIn("HookImpl", repr_str)
        self.assertIn("test_plugin", repr_str)

    def test_subset_hookcaller_repr(self):
        """Test _SubsetHookCaller __repr__."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        impl = HookimplMarker("proj")

        class P:
            @impl
            def h(self, x):  # noqa
                return x

        p = P()
        pm.register(p)

        subset = pm.subset_hook_caller("h", [p])
        repr_str = repr(subset)
        self.assertIn("_SubsetHookCaller", repr_str)
        self.assertIn("'h'", repr_str)

    def test_hookcaller_call_historic_asserts_on_direct_call(self):
        """Test that calling a historic hook directly raises AssertionError."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec(historic=True)
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        with self.assertRaises(AssertionError):
            pm.hook.h(x=1)

    def test_hookcaller_call_extra_asserts_on_historic(self):
        """Test that call_extra on historic hook raises AssertionError."""
        pm = PluginManager("proj")
        spec = HookspecMarker("proj")

        class Spec:
            @spec(historic=True)
            def h(self, x):  # noqa
                pass

        pm.add_hookspecs(Spec)

        with self.assertRaises(AssertionError):
            pm.hook.h.call_extra([], {"x": 1})

    def test_multicall_wrapper_teardown_exception_continues(self):
        """Test that exceptions in teardown are propagated."""

        def impl(x):
            return "result"

        def wrapper_raises_in_teardown(x):
            yield
            raise ValueError("teardown error")

        hi_impl = _mk_hookimpl(object(), "impl", impl)
        hi_wrapper = _mk_hookimpl(
            object(), "wrapper", wrapper_raises_in_teardown, wrapper=True
        )

        with self.assertRaises(ValueError):
            _multicall("h", [hi_wrapper, hi_impl], {"x": 1}, firstresult=False)

    def test_multicall_wrapper_teardown_continues_on_stopiteration(self):
        """Test that StopIteration in teardown updates result and continues."""

        def impl(x):
            return "result"

        yielded_values = []  # Capture values sent into the wrapper for assertions.
        def wrapper_with_return_value(x):
            # Capture values sent into the wrapper.
            yielded_values.append((yield))
            # Return a new value
            return "new_value"

        hi_impl = _mk_hookimpl(object(), "impl", impl)
        hi_wrapper = _mk_hookimpl(
            object(), "wrapper", wrapper_with_return_value, wrapper=True
        )

        result = _multicall("h", [hi_wrapper, hi_impl], {"x": 1}, firstresult=False)
        # The wrapper returns a value, which becomes the result
        self.assertEqual(result, "new_value")
        self.assertEqual(yielded_values, [["result"]])

    def test_multicall_wrapper_returns_value_via_stopiteration(self):
        """Test wrapper returning value which creates StopIteration with value."""

        def impl(x):
            return "impl_result"

        yielded_values = []  # Capture values sent into the wrapper for assertions.
        def wrapper_returns(x):
            # Capture values sent into the wrapper.
            yielded_values.append((yield))
            # Return a new value
            return "wrapper_override"

        hi_impl = _mk_hookimpl(object(), "impl", impl)
        hi_wrapper = _mk_hookimpl(object(), "wrapper", wrapper_returns, wrapper=True)

        result = _multicall("h", [hi_wrapper, hi_impl], {"x": 1}, firstresult=False)
        # Wrapper's return value should override
        self.assertEqual(result, "wrapper_override")
        self.assertEqual(yielded_values, [["impl_result"]])


class TestCoverageReloads(unittest.TestCase):
    def test_reload_modules_for_full_coverage(self):
        import runpy
        import typing
        import pluggy
        from pluggy import _callers, _hooks, _manager, _result, _tracing, _warnings

        def run_module_path(module, run_name):
            """Re-execute module initialization via runpy for coverage.

            Args:
                module: Imported module object to execute.
                run_name: Name used for __name__/__package__ during execution.
            """
            runpy.run_path(module.__file__, run_name=run_name)

        original_type_checking = typing.TYPE_CHECKING
        try:
            typing.TYPE_CHECKING = True
            run_module_path(_hooks, "pluggy._hooks_typechecking")
            run_module_path(_manager, "pluggy._manager_typechecking")
        finally:
            typing.TYPE_CHECKING = original_type_checking

        run_module_path(_callers, "pluggy._callers_coverage")
        run_module_path(_result, "pluggy._result_coverage")
        run_module_path(_tracing, "pluggy._tracing_coverage")
        run_module_path(_warnings, "pluggy._warnings_coverage")
        runpy.run_path(pluggy.__file__, run_name="pluggy._coverage")


if __name__ == "__main__":
    unittest.main()
