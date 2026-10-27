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
Repointing a view at another model: a view whose model's been moved asks for
it when it's read (see *SNGView.askForMissingModel*), offering the models
moved or copied from there (see *Directory.copiesOf()*); and "File | Change
model..." shows another -- eg, a copy (see *Application.changeModel()*).

Created on Oct 22, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
import tkinter as tk

import sn
from util import terminal
from util.utils import fixURL
from util.persistence.pRef import PRDb
from sn.model.model import Model
from sn.model.directory import copiesOf, Folder

class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    from sn.view.graphics.sngView import SNGView
    # (the application routes stdout, stderr, input(), logging and excepthook
    # to its windows' terminals: put them all back afterwards)
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
    if not cls.prefsWereDirty: # (nothing here is to be saved in the preferences)
      sn.snPrefs.setDirty(False)

  def setUp(self):
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snChangeModel-")
    self.folder = Path(self.tmp.name).resolve()
    sn.copyExamples(str(self.folder), ["family.snm"])
    model = Model.getDB((self.folder / "family.snm").as_uri())
    self.viewURL = fixURL(model.url, ".snv", replaceExt=True, mode="w")[0]
    view = SNGView(self.viewURL, model=model)
    view.window.withdraw()
    view.showAllModel()
    self.pump()
    view.save(overwrite=True)
    self.ids = sorted(vo.modelObject._id for vo in view.values() if vo is not None and vo.modelObject is not None
                      and vo.modelObject.db is model)
    self.assertTrue(self.ids)
    self.close(view)
    Model._initCache()

  def tearDown(self):
    for window in list(self.app.windows.values()):
      self.close(window.view)
    self.app.windows.clear()
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
    'Let the event loop run: what the view puts off till idle.'
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def move(self) -> str:
    ':returns: The URL of the model, moved to a folder of its own.'
    (self.folder / "moved").mkdir()
    shutil.move(self.folder / "family.snm", self.folder / "moved" / "family.snm")
    return (self.folder / "moved" / "family.snm").as_uri()

  def shownIDs(self, view) -> list[int]:
    ':returns: The ids of the model objects of its model it shows.'
    return sorted(vo.modelObject._id for vo in view.values() if vo is not None and vo.modelObject is not None
                  and vo.modelObject.db is view.model)

  def test0100copiesOf(self):
    old = (self.folder / "family.snm").as_uri()
    moved = self.move()
    shutil.copy(self.folder / "moved" / "family.snm", self.folder / "other.snm") # (it says it's where it was)
    found = [e.url for e in copiesOf(old, [Folder(str(self.folder), subfolders=True)])]
    self.assertEqual(set(found), {moved, (self.folder / "other.snm").as_uri()})

  def test0200askedWhenMissing(self):
    from sn.view.graphics.sngView import SNGView
    moved = self.move()
    asked = []
    SNGView.askForMissingModel = lambda view, model: asked.append((view, model)) or moved
    view = PRDb.readFile(self.viewURL)
    self.pump()
    self.assertEqual(asked, [(self.viewURL, (self.folder / "family.snm").as_uri())])
    self.assertEqual(view.model.url, moved)
    self.assertEqual(self.shownIDs(view), self.ids) # (its objects show the moved model's)
    self.assertTrue(view.isDirty()) # (saving it names the moved model)
    view.save(overwrite=True)
    self.close(view)
    Model._initCache()
    SNGView.askForMissingModel = lambda view, model: self.fail("asked again")
    view = PRDb.readFile(self.viewURL)
    self.pump()
    self.assertEqual(view.model.url, moved)
    self.assertFalse(view.isDirty())
    self.close(view)

  def test0300cancelled(self):
    from sn.view.graphics.sngView import SNGView
    self.move()
    SNGView.askForMissingModel = lambda view, model: None
    with self.assertLogs(level="WARNING"): # (its objects' model objects are missing)
      view = PRDb.readFile(self.viewURL)
      self.pump()
    self.assertEqual(view.model.url, (self.folder / "family.snm").as_uri()) # (as before: an empty model there)
    self.assertEqual(self.shownIDs(view), [])
    self.close(view)

  def test0400notAskedWhenThere(self):
    from sn.view.graphics.sngView import SNGView
    SNGView.askForMissingModel = lambda view, model: self.fail("asked")
    view = PRDb.readFile(self.viewURL)
    self.pump()
    self.assertFalse(view.isDirty())
    self.close(view)

  def test0500changeModel(self):
    shutil.copy(self.folder / "family.snm", self.folder / "copy.snm")
    copy = (self.folder / "copy.snm").as_uri()
    window = self.app.openWindow(self.viewURL)
    self.pump()
    old = window.view.model
    window = self.app.changeModel(window.view, copy)
    self.pump()
    view = window.view
    self.assertEqual(view.model.url, copy)
    self.assertIsNot(view.model, old)
    self.assertEqual(self.shownIDs(view), self.ids)
    self.assertTrue(view.isDirty())
    self.assertEqual(list(self.app.windows), [self.viewURL])
    view.save(overwrite=True)
    self.close(view)
    self.app.windows.clear()
    Model._initCache()
    view = PRDb.readFile(self.viewURL)
    self.pump()
    self.assertEqual(view.model.url, copy) # (saved naming the copy)
    self.close(view)

  def test0600changeModelMenu(self):
    'The menu item: asks which model, says what will be missing, and reopens the view.'
    from tkinter import messagebox
    shutil.copy(self.folder / "family.snm", self.folder / "copy.snm")
    copy = Model.getDB((self.folder / "copy.snm").as_uri())
    copy._unregister(copy["alice"]._id) # (one of the view's objects isn't in it)
    window = self.app.openWindow(self.viewURL)
    self.pump()
    with mock.patch("sn.view.graphics.chooseModelDialog.ChooseModelDialog.show", return_value=copy.url), \
         mock.patch.object(messagebox, "askokcancel", return_value=True) as warned:
      window.view.doChangeModel()
    self.pump()
    self.assertIn("aren't in", warned.call_args[0][1])
    self.assertEqual(self.app.windows[self.viewURL].view.model.url, copy.url)

  def test0250askedByTheApp(self):
    'Opening it in a window: the app asks, offering where it was moved to.'
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    from sn.view.graphics.sngView import SNGView
    moved = self.move()
    SNGView.askForMissingModel = self.app.askForMissingModel
    offered = []
    def show(d):
      offered.extend(e.url for e in d.candidates)
      return moved
    with mock.patch("sn.view.graphics.directoryWindow.searchPath", return_value=[Folder(str(self.folder), subfolders=True)]), \
         mock.patch.object(ChooseModelDialog, "show", show):
      window = self.app.openWindow(self.viewURL)
    self.pump()
    self.assertEqual(offered, [moved])
    self.assertEqual(window.view.model.url, moved)
    self.assertEqual(self.shownIDs(window.view), self.ids)

  def test0700dialog(self):
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    old = (self.folder / "family.snm").as_uri()
    moved = self.move()
    found = copiesOf(old, [Folder(str(self.folder), subfolders=True)])
    d = ChooseModelDialog(self.app, "t", "m", found)
    d.ok() # (the first found is chosen)
    self.assertEqual(d.result, moved)
    d = ChooseModelDialog(self.app, "t", "m", found)
    d.new.set(str(self.folder / "other.snm")) # (a path typed: its URL)
    self.assertEqual(d.list.curselection(), ())
    d.ok()
    self.assertEqual(d.result, (self.folder / "other.snm").as_uri())
    d = ChooseModelDialog(self.app, "t", "m", [])
    d.ok() # (nothing chosen: it stays open)
    self.assertIsNone(d.result)
    d.destroy()

  def test0800relativeTyped(self):
    'A relative path typed is relative to the view -- a file\'s, or a web URL\'s -- not the current directory.'
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    d = ChooseModelDialog(self.app, "t", "m", [], near=(self.folder / "elsewhere" / "x.snm").as_uri(), base=self.viewURL)
    for typed, url in [("copy.snm", (self.folder / "copy.snm").as_uri()),
                       ("shared/a b.snm", (self.folder / "shared" / "a b.snm").as_uri()),
                       ("../up.snm", (self.folder.parent / "up.snm").as_uri()),
                       (str(self.folder / "abs.snm"), (self.folder / "abs.snm").as_uri()),
                       ("https://example.com/m/x.snm", "https://example.com/m/x.snm")]:
      self.assertEqual(d.resolve(typed), url, typed)
    d.base = "https://example.com/models/family.snv"
    self.assertEqual(d.resolve("copy.snm"), "https://example.com/models/copy.snm")
    self.assertEqual(d.resolve("../other/a b.snm"), "https://example.com/other/a%20b.snm")
    d.destroy()

  def test0810changeModelTypedRelative(self):
    'File | Change model..., typing just the name of a model beside the view: the view names it relatively.'
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    shutil.copy(self.folder / "family.snm", self.folder / "copy.snm")
    window = self.app.openWindow(self.viewURL)
    self.pump()
    def show(d):
      d.new.set("copy.snm")
      d.ok()
      return d.result
    with mock.patch.object(ChooseModelDialog, "show", show):
      window.view.doChangeModel()
    self.pump()
    view = self.app.windows[self.viewURL].view
    self.assertEqual(view.model.url, (self.folder / "copy.snm").as_uri())
    view.save(overwrite=True)
    text = (self.folder / "family.snv").read_text()
    self.assertIn('"copy.snm"', text)
    self.assertNotIn(str(self.folder / "copy.snm"), text)

  def test0820showsAsStored(self):
    'The dialog names the model as the view\'s file does -- relatively, beside it -- and says so if it\'s the same one.'
    from tkinter import messagebox
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    window = self.app.openWindow(self.viewURL)
    self.pump()
    asked = []
    def show(d):
      asked.append(d)
      d.new.set("family.snm") # (the model it shows)
      d.ok()
      return d.result
    real = ChooseModelDialog.__init__
    messages = []
    def init(d, parent, title, message, *a, **k):
      messages.append(message)
      real(d, parent, title, message, *a, **k)
    with mock.patch.object(ChooseModelDialog, "__init__", init), mock.patch.object(ChooseModelDialog, "show", show), \
         mock.patch.object(messagebox, "showinfo") as told:
      window.view.doChangeModel()
    self.pump()
    self.assertIn('"family.snm" (that is, ', messages[0])
    self.assertIn("already shows that model", told.call_args[0][1])
    self.assertIn('"family.snm"', told.call_args[0][1])
    self.assertIs(self.app.windows[self.viewURL], window) # (not reopened)

if __name__ == "__main__":
  unittest.main()
