#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
#                                                                               #
# Permission is hereby granted, free of charge, to any person obtaining a copy  #
# of this software and associated documentation files (the "Software"), to deal #
# in the Software without restriction, including without limitation the rights  #
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell     #
# copies of the Software, and to permit persons to whom the Software is         #
# furnished to do so, subject to the following conditions:                      #
#                                                                               #
# The above copyright notice and this permission notice shall be included in all#
# copies or substantial portions of the Software.                               #
#                                                                               #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR    #
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,      #
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE   #
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER        #
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, #
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE #
# SOFTWARE.                                                                     #
#################################################################################
'''
Hooks (see *sn.hooks*): functions named by attributes, found -- and their
modules imported -- only if they're made hooks, and their modules trusted.

The modules imported are made in a scratch folder; the trusted modules are
patched, not set in the preferences (which are saved at exit).

Created on Oct 13, 2026

@author: robkremer
'''
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock
from sn import hooks
from sn.hooks import hook, HookContext
from sn.model.model import Model, Node

@hook
def greet(obj, context):
  return f"hello {obj} ({context.key})"

@hook
def broken(obj, context):
  raise RuntimeError("oops")

@hook(appliesTo=lambda obj, context: obj.startswith("f"))
def fOnly(obj, context):
  return "f"

@hook(appliesTo=lambda obj, context: 1/0)
def badTest(obj, context):
  return "bad"

def notAHook(obj, context):
  return "should never be called"

class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.folder = tempfile.TemporaryDirectory()
    root = Path(cls.folder.name)
    pkg = root / "hookfixtures"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    # each module counts its imports in a file, so a test can tell whether it was imported
    for name, body in {
        "good": '''
          from sn.hooks import hook
          @hook
          def shout(obj, context):
            return str(obj).upper()
          def plain(obj, context):
            return "plain"
          ''',
        "untrusted": '''
          from sn.hooks import hook
          @hook
          def evil(obj, context):
            return "evil"
          ''',
        "bad": '''
          raise ImportError("no such luck")
          ''',
        }.items():
      (pkg / f"{name}.py").write_text(
        f'with open(__file__ + ".count", "a") as f: f.write("x")\n' + textwrap.dedent(body))
    sys.path.insert(0, str(root))
    cls.pkg = pkg

  @classmethod
  def tearDownClass(cls):
    sys.path.remove(cls.folder.name)
    for m in [m for m in sys.modules if m == "hookfixtures" or m.startswith("hookfixtures.")]:
      del sys.modules[m]
    cls.folder.cleanup()

  def setUp(self):
    hooks._problems.clear()
    hooks._reported.clear()
    patcher = mock.patch.object(hooks.snPrefs, "get", side_effect=lambda key, default=None, **kw:
                                ["hookfixtures.good", "hookfixtures.bad"] if key == hooks.TRUSTED_PREF else default)
    patcher.start()
    self.addCleanup(patcher.stop)

  def imports(self, name):
    f = self.pkg / f"{name}.py.count"
    return len(f.read_text()) if f.exists() else 0

  def test0100reference(self):
    self.assertEqual(hooks.reference(greet), f"{__name__}:greet")
    self.assertTrue(hooks.isReference("a.b:c"))
    self.assertTrue(hooks.isReference(" a:B.c "))
    for text in ["a", "a:", ":b", "a:b()", "a b:c", "a:b:c", "os.system('x')", 3, None]:
      self.assertFalse(hooks.isReference(text), text)

  def test0200call(self):
    ref = hooks.reference(greet)
    self.assertEqual(hooks.call(ref, "fred", HookContext(key=".menu/x")), "hello fred (.menu/x)")
    self.assertEqual(hooks.call(f" {ref} ", "fred"), "hello fred ()")

  def test0300notAHook(self):
    # a function that wasn't made a hook can't be called, though its module's loaded
    ref = f"{__name__}:notAHook"
    with self.assertLogs("sn.hooks", "WARNING"):
      self.assertEqual(hooks.call(ref, "fred", default="no"), "no")
    self.assertIsNotNone(hooks.problem(ref))
    with self.assertNoLogs("sn.hooks", "WARNING"): # (logged once)
      hooks.call(ref, "fred")
    for ref in ["os:system", "builtins:eval", "subprocess:run"]:
      self.assertIsNone(hooks.resolve(ref), ref)

  def test0400failing(self):
    ref = hooks.reference(broken)
    with self.assertLogs("sn.hooks", "WARNING") as logs:
      self.assertEqual(hooks.call(ref, "fred", default="dflt"), "dflt")
    self.assertIn("failed", logs.output[0])

  def test0500trusted(self):
    self.assertTrue(hooks.trusted("sn"))
    self.assertTrue(hooks.trusted("sn.exampleApps.pythonParser"))
    self.assertFalse(hooks.trusted("snake"))
    self.assertTrue(hooks.trusted("hookfixtures.good"))
    self.assertTrue(hooks.trusted("hookfixtures.good.inner"))
    self.assertFalse(hooks.trusted("hookfixtures.goodish"))
    self.assertFalse(hooks.trusted("hookfixtures"))
    self.assertFalse(hooks.trusted("hookfixtures.untrusted"))

  def test0600importsTrusted(self):
    self.assertEqual(hooks.call("hookfixtures.good:shout", "fred"), "FRED")
    self.assertEqual(self.imports("good"), 1)
    self.assertIn("no such hook", hooks.problem("hookfixtures.good:plain"))

  def test0700untrustedNotImported(self):
    with self.assertLogs("sn.hooks", "WARNING") as logs:
      self.assertIsNone(hooks.call("hookfixtures.untrusted:evil", "fred"))
    self.assertIn("isn't trusted", logs.output[0])
    self.assertEqual(self.imports("untrusted"), 0)
    self.assertNotIn("hookfixtures.untrusted", sys.modules)

  def test0800importFails(self):
    with self.assertLogs("sn.hooks", "WARNING") as logs:
      self.assertIsNone(hooks.call("hookfixtures.bad:x", "fred"))
    self.assertIn("couldn't be imported", logs.output[0])
    hooks.call("hookfixtures.bad:x", "fred")
    self.assertEqual(self.imports("bad"), 1) # (not tried again)

  def test0900hookAttributes(self):
    m = Model("temp_hooks.xml")
    method = Node(m, [m.NODE], name="method")
    method[".menu/Show source"] = hooks.reference(greet)
    method[".menu/Source/Open"] = "hookfixtures.good:shout"
    method[".menuish"] = hooks.reference(greet)
    method[".menu/Bad"] = "not a reference"
    run = Node(m, [method], individual=True, name="run")
    run[".menu/Own"] = hooks.reference(greet)
    with self.assertLogs("sn.hooks", "WARNING"):
      found = hooks.hookAttributes(run, ".menu/")
    self.assertEqual(found, {"Own": hooks.reference(greet),
                             "Show source": hooks.reference(greet),
                             "Source/Open": "hookfixtures.good:shout"})
    self.assertEqual(list(found), sorted(found))

  def test1000appliesTo(self):
    self.assertEqual(fOnly("fred", None), "f") # (the decorator gives back the function itself)
    self.assertTrue(hooks.applies(hooks.reference(fOnly), "fred"))
    self.assertFalse(hooks.applies(hooks.reference(fOnly), "ann"))
    self.assertTrue(hooks.applies(hooks.reference(greet), "ann")) # (no test: applies to all)
    self.assertTrue(hooks.applies("os:system", "ann"))            # (can't be called: shown, but disabled)
    with self.assertLogs("sn.hooks", "WARNING"):
      self.assertFalse(hooks.applies(hooks.reference(badTest), "ann"))

  def test1100selectionInContext(self):
    self.assertEqual(HookContext().selection, [])
    self.assertEqual(HookContext(selection=["a", "b"]).selection, ["a", "b"])

if __name__ == "__main__":
  unittest.main()
