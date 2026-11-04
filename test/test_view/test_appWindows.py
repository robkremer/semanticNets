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
The app's windows and files (see *sn.view.graphics.guiApp.Application*): what
the deep dive found -- quitting offers to save the models first; a start-up
whose files all fail shows the model directory; Change model on a view that's
never been saved; super-models' views where the program's folder can't be
written; Open Read-only of a model that's only in memory; where new windows
go, and their titles.

Created on Nov 4, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import os
import sys
import tempfile
import time
import types
import unittest
from unittest import mock
from pathlib import Path
import tkinter as tk

import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model

class TestQuit(unittest.TestCase):

  def test0100quitOffersToSaveFirst(self):
    'Application.quit() (eg: the last window closed) offers to save the models, then the settings, while the windows can still ask -- before the app goes.'
    from sn.view.graphics.guiApp import Application
    calls:list[str] = []
    fake = types.SimpleNamespace(destroy=lambda: calls.append("destroy"))
    with mock.patch.object(sn, "saveAtExit", lambda: calls.append("models")), \
         mock.patch.object(sn, "savePrefsIfChanged", lambda: calls.append("settings")):
      Application.quit(fake) # type: ignore[arg-type]
    self.assertEqual(calls, ["models", "settings", "destroy"])

  def test0200windowTitle(self):
    'A window is titled with its file\'s name, then its folder.'
    from sn.view.graphics.guiApp import windowTitle
    folder = Path(tempfile.gettempdir()).resolve() / "My Models"
    self.assertEqual(windowTitle((folder / "family.snv").as_uri()), f"family.snv — {folder}")
    self.assertEqual(windowTitle("https://example.org/models/family.snv"), "family.snv — https://example.org/models")


class TestAppWindows(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener, SNGView.askForMissingModel)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    try:
      cls.app = Application()
    except tk.TclError as ex:
      cls.restore()
      raise unittest.SkipTest(f"no display: {ex}")
    cls.app.noteRecent = cls.app.noteFile = lambda *a: None # (not in the preferences' recent files)

  @classmethod
  def restore(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    (sys.stdout, sys.stderr, builtins.input, sys.excepthook, handlers, terminal._installedIORoutingRegistry,
     Application.current, progress.listener, SNGView.askForMissingModel) = cls.saved
    logging.getLogger().handlers[:] = handlers

  @classmethod
  def tearDownClass(cls):
    cls.app.destroy()
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snAppWindows-")
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    for window in list(self.app.windows.values()):
      self.close(window.view)
    self.app.windows.clear()
    self.app.showDirectory(False)
    self.pump()
    Model._initCache()
    self.tmp.cleanup()

  def close(self, view) -> None:
    if not view._closed:
      view.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(view.window)
    if view.window.winfo_exists():
      view.window.destroy()
    self.pump()

  def pump(self, seconds:float=0.2) -> None:
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def test0300startUpWithNothingOpened(self):
    'If none of the files named at start-up can be opened, the model directory is shown: the app doesn\'t run with nothing on the screen.'
    bad = self.folder / "notes.txt"
    bad.write_text("not a model")
    self.app.showDirectory(False)
    with mock.patch("sn.view.graphics.guiApp.showExceptionDialog"), mock.patch.object(self.app, "loadPlugins"):
      self.app.startUp([str(bad)])
    self.assertEqual(self.app.windows, {})
    self.assertTrue(self.app.directoryShown())

  def test0400changeModelOfUnsavedView(self):
    'Change model on a view that\'s never been saved (it can\'t be read again) leaves its window open.'
    from sn.view.graphics.sngView import SNGView
    model = Model((self.folder / "fresh.snm").as_uri())
    other = Model((self.folder / "other.snm").as_uri())
    view = SNGView((self.folder / "fresh.snv").as_uri(), model=model)
    self.app.windows[view.url] = view.window
    with self.assertLogs(level="ERROR"):
      self.assertIsNone(self.app.changeModel(view, other.url))
    self.assertIn(view.url, self.app.windows)
    self.assertTrue(view.window.winfo_exists())
    self.assertFalse(view._closed)

  def test0500superModelViewsWhereTheyCanBeWritten(self):
    'The system model\'s view is in the program\'s folder if it can be written there, else in the program\'s own folder (~/.sn/views).'
    from sn.view.graphics.sngView import SNGView
    model = Model((self.folder / "m.snm").as_uri())
    view = SNGView((self.folder / "m.snv").as_uri(), model=model)
    self.app.windows[view.url] = view.window
    src, url = view.superModelView(model.TOP.model)
    self.assertEqual(src, "")
    self.assertTrue(url.endswith("/sn/model/sn.snv"), url)
    with mock.patch("sn.view.graphics.viewFiles.canWriteUrl", return_value=False), \
         mock.patch.object(sn, "SN_FOLDER", str(self.folder / ".sn")):
      src, url = view.superModelView(model.TOP.model)
    self.assertEqual(url, (self.folder / ".sn" / "views" / "sn.snv").as_uri())

  def test0600openReadOnlyModelOnlyInMemory(self):
    'Open Read-only of a model that\'s only in memory (its windows all closed) opens it read-only, read afresh.'
    path = self.folder / "m.snm"
    model = Model(path.as_uri())
    model.save()
    self.assertIn(model.url, Model.AllDBs)
    entry = types.SimpleNamespace(remote=False, kind="model", url=model.url, modelURL=model.url, path=str(path), name="m")
    with mock.patch("sn.view.graphics.guiApp.messagebox") as box:
      window = self.app.openEntry(entry, readOnly=True) # type: ignore[arg-type]
    self.pump()
    box.showinfo.assert_not_called()
    self.assertIsNotNone(window)
    self.assertTrue(window.view.model.writeLocked())
    self.assertIsNot(window.view.model, model) # (read afresh)

  def test0700newWindowsCascade(self):
    'New views\' windows go each down and to the right of the last, not all at the same place.'
    first, second = self.app.nextWindowGeometry(), self.app.nextWindowGeometry()
    size = lambda g: g.split("+")[0]
    place = lambda g: tuple(int(v) for v in g.split("+")[1:])
    self.assertEqual(size(first), size(second))
    self.assertEqual(place(second), (place(first)[0] + 40, place(first)[1] + 40))
    w, h = (int(v) for v in size(first).split("x"))
    self.assertGreater(w, 300)


if __name__ == "__main__":
  unittest.main()
