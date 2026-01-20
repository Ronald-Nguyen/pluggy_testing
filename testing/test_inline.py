import unittest
import inspect
import dis


from pluggy._manager import DistFacade


class FakeDist:
    def __init__(self, name: str) -> None:
        self.metadata = {"name": name}


class TestDistFacadeProjectNameInline(unittest.TestCase):
    def test_project_name_returns_metadata_name(self):
        df = DistFacade(FakeDist("pluggy-sample"))
        self.assertEqual(df.project_name, "pluggy-sample")

    def test_inline_variable_name_is_applied(self):
        func = DistFacade.project_name.fget
        self.assertTrue(inspect.isfunction(func))
        self.assertNotIn("name", func.__code__.co_varnames)
        for ins in dis.get_instructions(func):
            self.assertFalse(ins.opname.startswith("STORE") and ins.argval == "name")


if __name__ == "__main__":
    unittest.main()