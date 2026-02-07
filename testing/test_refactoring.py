import unittest
import inspect
import dis
import inspect
import pytest

from pluggy._callers import _multicall
from pluggy import HookspecMarker, HookimplMarker, PluginManager
from pluggy._hooks import HookCaller, HookImpl

from pluggy._manager import DistFacade
from pluggy._result import HookCallError


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

def create_impl(function, **kwargs):
    """
    Erstellt eine HookImpl-Instanz für Testzwecke.
    """
    # Standard-Optionen
    opts: HookimplOpts = {
        "wrapper": False,
        "hookwrapper": False,
        "optionalhook": False,
        "tryfirst": False,
        "trylast": False,
        "specname": None,
    }
    opts.update(kwargs)
    
    # Dummy Plugin-Objekt und Name
    return HookImpl(None, "test_plugin", function, opts)

def create_impl(function, **kwargs):
    """
    Erstellt eine HookImpl-Instanz, die genau so aussieht, 
    wie _multicall sie erwartet.
    """
    opts: HookimplOpts = {
        "wrapper": False,
        "hookwrapper": False,
        "optionalhook": False,
        "tryfirst": False,
        "trylast": False,
        "specname": None,
    }
    opts.update(kwargs)
    # Name und Plugin sind für die Logik von _multicall meist irrelevant, 
    # müssen aber vorhanden sein.
    return HookImpl(None, "test_plugin", function, opts)

# --- REGRESSION TESTS (VERHALTENS-GARANTIE) ---

def test_multicall_behavior_collect_all():
    """
    Verifiziert: firstresult=False
    - Muss alle Ergebnisse sammeln.
    - Muss in umgekehrter Reihenfolge (LIFO) ausführen.
    """
    def hook_a(arg): return "A"
    def hook_b(arg): return "B"

    # Registrierungsreihenfolge: A, dann B.
    # Ausführung (_multicall reversed): B, dann A.
    impls = [create_impl(hook_a), create_impl(hook_b)]
    
    # Aufruf
    res = _multicall("test_hook", impls, {"arg": 1}, firstresult=False)
    
    # Erwartung: Liste [B, A]
    assert res == ["B", "A"]

def test_multicall_behavior_firstresult():
    """
    Verifiziert: firstresult=True
    - Muss stoppen, sobald ein Ergebnis nicht None ist.
    - Muss None-Ergebnisse überspringen.
    - Muss nachfolgende Hooks ignorieren.
    """
    def hook_none(arg): return None
    def hook_winner(arg): return "Winner"
    def hook_loser(arg): raise RuntimeError("Sollte nicht aufgerufen werden!")

    # Registrierung: Loser, Winner, None
    # Ausführung reversed: None -> Winner (STOP) -> Loser (skipped)
    impls = [
        create_impl(hook_loser), 
        create_impl(hook_winner), 
        create_impl(hook_none)
    ]
    
    res = _multicall("test_hook", impls, {"arg": 1}, firstresult=True)
    
    assert res == "Winner"

def test_multicall_behavior_firstresult_no_match():
    """
    Verifiziert: firstresult=True
    - Muss None zurückgeben, wenn kein Hook ein Ergebnis liefert.
    """
    def hook_none(arg): return None
    
    impls = [create_impl(hook_none)]
    res = _multicall("test_hook", impls, {"arg": 1}, firstresult=True)
    
    assert res is None

def test_multicall_argument_mapping():
    """
    Verifiziert: Argument-Parsing
    - Muss Argumente anhand der Parameternamen der Funktion zuordnen.
    - Überflüssige kwargs müssen ignoriert werden.
    """
    def hook(x, y): 
        return x + y

    impls = [create_impl(hook)]
    kwargs = {"x": 10, "y": 20, "unused": 999}
    
    res = _multicall("test_hook", impls, kwargs, firstresult=False)
    
    assert res == [30]

def test_multicall_missing_argument_error():
    """
    Verifiziert: Error Handling
    - Muss HookCallError werfen, wenn ein benötigtes Argument fehlt.
    """
    def hook(required_arg): return True

    impls = [create_impl(hook)]
    kwargs = {"wrong_arg": 1}

    with pytest.raises(HookCallError) as excinfo:
        _multicall("test_hook", impls, kwargs, firstresult=False)
    
    assert "must provide argument 'required_arg'" in str(excinfo.value)

def test_multicall_wrappers_execution_order():
    """
    Verifiziert: Hookwrappers
    - Muss Code VOR dem Yield ausführen.
    - Muss Code NACH dem Yield ausführen.
    - Muss das Ergebnis korrekt durchreichen.
    """
    call_order = []

    def wrapper(arg):
        call_order.append("wrapper_start")
        outcome = yield
        call_order.append("wrapper_end")
        # Wrapper sieht das Ergebnis
        assert outcome.get_result() == ["impl"]

    def impl(arg):
        call_order.append("impl")
        return "impl"

    impls = [create_impl(impl), create_impl(wrapper, hookwrapper=True)]
    
    # Ausführung reversed: Wrapper (Start) -> Impl -> Wrapper (End)
    res = _multicall("test_hook", impls, {"arg": 1}, firstresult=False)
    
    assert res == ["impl"]
    assert call_order == ["wrapper_start", "impl", "wrapper_end"]

def test_multicall_wrappers_modify_result():
    """
    Verifiziert: Hookwrappers Ergebnis-Manipulation
    - Wrapper muss in der Lage sein, das Ergebnis zu überschreiben.
    """
    def wrapper_force(arg):
        outcome = yield
        # Wir überschreiben das Ergebnis der inneren Funktion
        outcome.force_result(["overwritten"])

    def impl(arg):
        return "original"

    impls = [create_impl(impl), create_impl(wrapper_force, hookwrapper=True)]
    
    res = _multicall("test_hook", impls, {"arg": 1}, firstresult=False)
    
    assert res == ["overwritten"]

def test_multicall_exception_handling():
    """
    Verifiziert: Exception Propagation
    - Wenn ein Hook crasht, muss die Exception nach außen dringen.
    """
    def impl_crash(arg):
        raise ValueError("Crash!")

    impls = [create_impl(impl_crash)]
    
    with pytest.raises(ValueError, match="Crash!"):
        _multicall("test_hook", impls, {"arg": 1}, firstresult=False)

def test_multicall_wrapper_exception_handling():
    """
    FIXED: Pluggy Wrappers fangen Exceptions nicht mit try/except um das yield,
    sondern erhalten ein Result-Objekt, das die Exception enthält.
    """
    log = []
    def wrapper_check_exception(arg):
        outcome = yield
        # Hier prüfen wir, ob die Exception im Result-Objekt angekommen ist
        if outcome.exception:
            log.append("caught")
            # Wir machen nichts weiter, d.h. die Exception bleibt im Result 
            # und wird am Ende von _multicall geworfen.

    def impl_crash(arg):
        raise ValueError("Boom")

    impls = [create_impl(impl_crash), create_impl(wrapper_check_exception, hookwrapper=True)]
    
    # Die Exception muss trotzdem aus _multicall herauskommen
    with pytest.raises(ValueError, match="Boom"):
        _multicall("test_hook", impls, {"arg": 1}, firstresult=False)
    
    assert log == ["caught"]
if __name__ == "__main__":
    unittest.main()