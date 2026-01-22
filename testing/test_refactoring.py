import unittest
import inspect
import dis
import inspect
import pytest

from pluggy import HookspecMarker, HookimplMarker, PluginManager
from pluggy._hooks import HookCaller

from pluggy._manager import DistFacade


class FakeDist:
    def __init__(self, name: str) -> None:
        self.metadata = {"name": name}


class TestDistFacadeProjectNameInline(unittest.TestCase):
    def test_project_name_returns_metadata_name(self):
        df = DistFacade(FakeDist("pluggy-sample"))
        self.assertEqual(df.project_name, "pluggy-sample")

    @unittest.skip("Skipping test for inlining variable name")
    def test_inline_variable_name_is_applied(self):
        func = DistFacade.project_name.fget
        self.assertTrue(inspect.isfunction(func))
        self.assertNotIn("name", func.__code__.co_varnames)
        for ins in dis.get_instructions(func):
            self.assertFalse(ins.opname.startswith("STORE") and ins.argval == "name")

class TestGetterSetter:

    @unittest.skip("only when getter setter refactoring is applied")
    def test_pluginmanager_project_name_is_property_and_usage_unchanged(self):
        # The class must expose 'project_name' as a property descriptor
        prop = inspect.getattr_static(PluginManager, "project_name")
        assert isinstance(prop, property), "PluginManager.project_name should be a @property"

        pm = PluginManager("example")
        # The instance property must return the project name string
        assert pm.project_name == "example"

        # Using the markers with the same project name should still work
        hookspec = HookspecMarker("example")
        hookimpl = HookimplMarker("example")

        class Hooks:
            @hookspec
            def he_method1(self, x):
                """spec"""

        pm.add_hookspecs(Hooks)

        class Plugin:
            @hookimpl
            def he_method1(self, x):
                return x

        pm.register(Plugin())

        # Calling the hook must still behave identically
        res = pm.hook.he_method1(x=3)
        assert res == [3]

if __name__ == "__main__":
    unittest.main()