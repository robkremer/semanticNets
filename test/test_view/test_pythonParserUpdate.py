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
The pythonParser plugin's "Update" (see its *dialog.update()*): asked whether
to update or replace the model and view already made from some code, updating
keeps the nodes -- and ids -- of what's still there, and opens the view made
before, showing the new modules (and what's gone as missing: it can still be
saved, and read again, so). ("Replace" and "Cancel" are as before.)

The windows are never shown, and nothing is saved outside a temporary folder
(but the preferences' recent files: they're not saved).

Created on Oct 24, 2026

@author: robkremer
'''
import builtins
import logging
import os
import sys
import tempfile
import unittest
from unittest import mock
import tkinter as tk
import sn
from util import terminal
from util.persistence.pRef import PRDb
from sn.model.model import Model, Node
from sn.plugins import importBundled

MAIN = 'from . import a\nclass A:\n  def m(self): pass\ndef f(): pass\nif __name__ == "__main__": f()\n'
MAIN_AFTER = 'from . import b\nclass A:\n  """A doc."""\n  def m(self): pass\n  def n(self): pass\nif __name__ == "__main__": A()\n'

class TestUpdate(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import decorators, progress
    from sn.view.graphics.guiApp import Application
    cls.dialog = importBundled("pythonParser", "dialog")
    decorators._fonts.clear() # (made for an application an earlier test made, and destroyed: eg: test_viewSmoke's)
    # (the application routes stdout, stderr, input(), logging and excepthook
    # to its windows' terminals: put them all back afterwards)
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    try:
      cls.app = Application()
    except tk.TclError as ex:
      cls.restore()
      raise unittest.SkipTest(f"no display: {ex}")

  @classmethod
  def restore(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    (sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry,
     Application.current, progress.listener) = cls.saved
    logging.getLogger().handlers[:] = handlers

  @classmethod
  def tearDownClass(cls):
    from sn.view.graphics import decorators
    cls.app.destroy()
    decorators._fonts.clear() # (made for this application: no good to a later test's -- eg: test_viewSmoke's)
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty: # (nothing here is to be saved in the preferences)
      sn.snPrefs.setDirty(False)

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snPythonParserUpdate-")
    self.package = os.path.join(os.path.realpath(self.tmp.name), "pk")
    os.mkdir(self.package)
    self.write("__init__.py", "")
    self.write("main.py", MAIN)
    self.write("a.py", "def g(): pass\n")
    self.modelPath = os.path.join(self.package, "main_py.snm")
    self.viewPath = os.path.join(self.package, "main_py.snv")
    with mock.patch("tkinter.Toplevel.deiconify"): # (the view's window: not shown)
      self.assertTrue(self.dialog.convert(self.app, [self.package], self.dialog.Options()))
    self.assertTrue(os.path.exists(self.viewPath))
    self.before = self.ids(Model(self.modelPath))

  def tearDown(self):
    for name in list(self.app.windows):
      self.app._closeWindow(name, quitIfLast=False, askToSave=False)
    self.app.update()
    Model._initCache()
    self.tmp.cleanup()

  def write(self, name:str, text:str) -> None:
    with open(os.path.join(self.package, name), "w") as f:
      f.write(text)

  def ids(self, model:Model) -> dict[str, int]:
    return {str(o.getLocal("qualified-name")): int(o.id) for o in model.values()
            if o.model is model and isinstance(o, Node) and isinstance(o.getLocal("qualified-name"), str)}

  def change(self, choice:str) -> bool:
    'Change the code, and make the model again: *choice* is the answer to "Update, or replace?".'
    os.remove(os.path.join(self.package, "a.py"))
    self.write("b.py", "def h(): pass\n")
    self.write("main.py", MAIN_AFTER)
    with mock.patch.object(self.dialog, "askChoice", return_value=choice) as ask, \
         mock.patch("tkinter.Toplevel.deiconify"):
      done = self.dialog.convert(self.app, [self.package], self.dialog.Options())
    self.assertEqual(ask.call_count, 1)
    self.assertEqual(ask.call_args.args[3], ["Update", "Replace", "Cancel"])
    return done

  def view(self):
    windows = [w for name, w in self.app.windows.items() if name.endswith("main_py.snv")]
    self.assertEqual(len(windows), 1)
    return windows[0].view

  def shown(self, view) -> list[str]:
    return sorted(str(o.modelObject.name) if o.modelObject is not None else "(missing)" for o in view.values() if o is not None)

  def test_update(self):
    'Updated: what\'s still there keeps its id, what\'s new is added (new modules shown in the view), and what\'s gone is missing from the view.'
    self.assertTrue(self.change("Update"))
    model = Model(self.modelPath)
    after = self.ids(model)
    for name in ("pk", "pk.main", "pk.main.A", "pk.main.A.m", "pk.main.__main__"):
      self.assertEqual(after[name], self.before[name], name)
    for name in ("pk.b", "pk.b.h", "pk.main.A.n"):
      self.assertGreater(after[name], max(self.before.values()), name)
    for name in ("pk.a", "pk.a.g", "pk.main.f"):
      self.assertNotIn(name, after)
    self.assertFalse(model.isDirty())
    view = self.view()
    self.assertEqual(self.shown(view), ["(missing)"] * 3 + ["b", "contains-module", "contains-module", "imports", "main", "pk"])
    self.assertFalse(view.isDirty())

    # (a view with missing objects is saved, and read again, with them missing)
    view.setDirty()
    view.save()
    for name in list(self.app.windows):
      self.app._closeWindow(name, quitIfLast=False, askToSave=False)
    Model._initCache()
    view = PRDb.readFile(view.url)
    self.assertEqual(self.shown(view), ["(missing)"] * 3 + ["b", "contains-module", "contains-module", "imports", "main", "pk"])
    view.detachFromModel()

  def test_replace(self):
    'Replaced: made afresh, as before.'
    self.assertTrue(self.change("Replace"))
    after = self.ids(Model(self.modelPath))
    self.assertNotIn("pk.a", after)
    self.assertNotIn("(missing)", self.shown(self.view()))

  def test_cancel(self):
    'Cancelled: nothing\'s changed.'
    with open(self.modelPath) as f:
      model = f.read()
    self.assertFalse(self.change("Cancel"))
    with open(self.modelPath) as f:
      self.assertEqual(f.read(), model)

if __name__ == "__main__":
  unittest.main()
