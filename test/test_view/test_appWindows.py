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

  def test0150quitAgainWhileAsking(self):
    '''Application.onQuit() again while it's asking whether to save the
    changes (eg: Quit chosen again from the menu bar, as the question can't be
    seen) does nothing more: the questions aren't asked again, each inside the
    other, leaving them all waiting.'''
    from sn.view.graphics.guiApp import Application
    calls:list[str] = []
    fake = types.SimpleNamespace(_quitting=False, rememberOpenWindows=lambda: calls.append("remember"),
                                 quit=lambda: calls.append("quit"))
    fake.closeAllWindows = lambda: (calls.append("views"), Application.onQuit(fake)) # (quit again, while asking about a view)
    with mock.patch.object(sn, "saveAtExit", lambda: calls.append("models")), \
         mock.patch.object(sn, "savePrefsIfChanged", lambda: calls.append("settings")), \
         mock.patch("sys.exit", lambda *a: calls.append("exit")), self.assertLogs(level="INFO"):
      Application.onQuit(fake) # type: ignore[arg-type]
    self.assertEqual(calls, ["remember", "views", "models", "settings", "quit", "exit"])

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

  def stacked(self, windows:list, expected:list, seconds:float=3) -> list:
    'Let the window manager catch up (eg: on Linux, it stacks them when it gets to it): *windows* in their stacking order, once it\'s *expected* (or the time\'s up).'
    from util.windowStacking import stackingOrder
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      order = stackingOrder(windows)
      if order == expected or time.monotonic() > end:
        return order
      time.sleep(0.02)

  def test0750reopenedInStackingOrder(self):
    '''The windows open when the app quit are reopened one in front of
    another as they were -- the model directory among them -- not in the
    order they were opened in.'''
    from sn.view.graphics.guiApp import Application
    def restore(pref:str, existed:bool, value) -> None:
      if existed:
        sn.snPrefs[pref] = value
      elif pref in sn.snPrefs:
        del sn.snPrefs[pref]
    for pref in (Application.OPEN_WINDOWS_PREF, Application.DIRECTORY_PREF, Application.DIRECTORY_STACK_PREF):
      self.addCleanup(restore, pref, pref in sn.snPrefs, sn.snPrefs.get(pref))
    paths = [self.folder / "a" / "family.snv", self.folder / "a" / "animals.snv", self.folder / "b" / "family.snv"]
    for folder in ("a", "b"):
      sn.copyExamples(str(self.folder / folder))
    windows = [self.app.openWindow(p.as_uri()) for p in paths]
    self.assertNotIn(None, windows)
    self.app.showDirectory()
    self.pump()
    for w in (windows[2], self.app, windows[0], windows[1]): # (not as they were opened)
      w.lift()
    expected = [windows[2], self.app, windows[0], windows[1]]
    self.assertEqual(self.stacked([self.app] + windows, expected), expected)
    self.app.rememberOpenWindows()
    urls = [view.url for view in (windows[2].view, windows[0].view, windows[1].view)]
    self.assertEqual([e["view"] for e in sn.snPrefs[Application.OPEN_WINDOWS_PREF]], urls) # (from the back to the front)
    self.assertEqual(sn.snPrefs[Application.DIRECTORY_STACK_PREF], 1) # (one behind the model directory)
    for window in windows:
      self.close(window.view)
    self.app.windows.clear()
    Model._initCache()
    self.app.showDirectory() # (as on start-up: before the windows are reopened)
    self.assertEqual(self.app.reopenWindows(), 3)
    reopened = [self.app.windows[url] for url in urls]
    expected = [reopened[0], self.app, reopened[1], reopened[2]]
    self.assertEqual(self.stacked([self.app] + reopened, expected), expected)

  def test0800examplesOverLockedCopies(self):
    'Copies of the examples that have been made read-only (or locked, on the Mac) are unlocked and replaced.'
    target = self.folder / "ex"
    sn.copyExamples(str(target), ["family.snm"])
    copy = target / "family.snm"
    copy.write_text("changed")
    os.chmod(copy, 0o444)
    if hasattr(os, "chflags"):
      import stat
      os.chflags(copy, stat.UF_IMMUTABLE) # type: ignore[attr-defined] # @UndefinedVariable
    sn.copyExamples(str(target), ["family.snm"])
    self.assertIn(target.as_uri(), copy.read_text(encoding="utf-8"))

  def examples(self, fail:OSError|None, replace:bool=False, answer:bool=True):
    'Install the examples into a folder of the test\'s, with copying them failing with *fail*: (what was returned, the askChoice mock, the settings opener mock).'
    from sn.view.graphics.guiApp import Application
    saved = sn.snPrefs.get(Application.EXAMPLES_PREF, False)
    self.addCleanup(lambda: sn.snPrefs.__setitem__(Application.EXAMPLES_PREF, saved))
    sn.snPrefs[Application.EXAMPLES_PREF] = False
    with mock.patch.object(self.app, "EXAMPLES_FOLDER", str(self.folder / "ex")), \
         mock.patch.object(sn, "copyExamples", side_effect=fail), \
         mock.patch("util.platformSupport.MAC", True), \
         mock.patch("util.platformSupport.responsibleApp", return_value="Eclipse"), \
         mock.patch("sn.view.graphics.guiApp.openPrivacySettings") as opener, \
         mock.patch("sn.view.graphics.guiApp.askChoice", return_value="Open Privacy Settings" if answer else "Not Now") as box:
      with self.assertLogs(level="ERROR"):
        ret = self.app.installExamples(replace=replace)
    return ret, box, opener

  def test0810examplesPrivacyBlocked(self):
    'If the Mac\'s privacy protection stops the examples being copied, the user\'s told which app to allow, and offered the settings; on the first launch, it\'s not tried again.'
    import errno
    from sn.view.graphics.guiApp import Application
    blocked = PermissionError(errno.EPERM, "Operation not permitted", str(self.folder / "ex" / "animals.snm"))
    ret, box, opener = self.examples(blocked)
    self.assertFalse(ret)
    message = box.call_args[0][2]
    self.assertIn("isn't letting Eclipse use", message)
    self.assertIn("Help | Install Example Models", message)
    opener.assert_called_once()
    self.assertTrue(sn.snPrefs.get(Application.EXAMPLES_PREF, False)) # (not again at the next launch)
    ret, box, opener = self.examples(blocked, replace=True, answer=False)
    opener.assert_not_called()
    self.assertFalse(sn.snPrefs.get(Application.EXAMPLES_PREF, False)) # (asked for: not marked done)

  def test0820examplesOtherError(self):
    'Another reason they can\'t be copied is just said.'
    import errno
    ret, box, opener = self.examples(OSError(errno.ENOSPC, "No space left on device"))
    self.assertFalse(ret)
    self.assertEqual(box.call_args[0][3], ["OK"]) # (no settings to open)
    self.assertIn("No space left on device", box.call_args[0][2])
    opener.assert_not_called()

  def test0830installExamplesChecksFirst(self):
    'Help | Install Example Models says the folder can\'t be used before asking to replace the copies, or closing their windows.'
    import errno
    target = self.folder / "ex"
    with mock.patch.object(self.app, "EXAMPLES_FOLDER", str(target)), \
         mock.patch("tempfile.TemporaryFile", side_effect=PermissionError(errno.EPERM, "Operation not permitted", str(target / "tmpx"))), \
         mock.patch("util.platformSupport.MAC", True), \
         mock.patch("util.platformSupport.responsibleApp", return_value="Eclipse"), \
         mock.patch("sn.view.graphics.guiApp.openPrivacySettings"), \
         mock.patch.object(self.app, "installExamples") as install, \
         mock.patch("sn.view.graphics.guiApp.askChoice", return_value="Not Now") as asked, \
         mock.patch("sn.view.graphics.guiApp.messagebox") as box:
      self.app.onInstallExamples()
    box.askokcancel.assert_not_called()
    install.assert_not_called()
    self.assertIn("isn't letting Eclipse use", asked.call_args[0][2])
    with mock.patch.object(self.app, "EXAMPLES_FOLDER", str(target)), \
         mock.patch.object(self.app, "installExamples") as install, \
         mock.patch("sn.view.graphics.guiApp.messagebox") as box:
      self.app.onInstallExamples() # (it can be: on to installing them)
    install.assert_called_once_with(replace=True)

  def privacy(self):
    'The Mac (as far as the privacy protection goes), started from Eclipse; messages mocked: (the askChoice mock, the settings opener mock).'
    self.app._privacyExplained.clear()
    for patch in (mock.patch("util.platformSupport.MAC", True),
                  mock.patch("util.platformSupport.responsibleApp", return_value="Eclipse")):
      patch.start()
      self.addCleanup(patch.stop)
    opener, box = mock.patch("sn.view.graphics.guiApp.openPrivacySettings"), mock.patch("sn.view.graphics.guiApp.askChoice")
    self.addCleanup(opener.stop)
    self.addCleanup(box.stop)
    return box.start(), opener.start()

  def test0900openBlockedByPrivacy(self):
    'A view the Mac\'s privacy protection won\'t let be read: which app to allow, not a traceback -- once for its folder, not for each window.'
    import errno
    from util.persistence.serialize import SerializationStrategy
    sn.copyExamples(str(self.folder), ["family.snm", "family.snv"])
    view = self.folder / "family.snv"
    box, opener = self.privacy()
    box.return_value = "Open Privacy Settings"
    blocked = PermissionError(errno.EPERM, "Operation not permitted", str(view))
    with mock.patch.object(SerializationStrategy, "peekTypex", side_effect=blocked), \
         mock.patch("sn.view.graphics.guiApp.showExceptionDialog") as traceback, \
         self.assertLogs(level="ERROR"):
      self.assertIsNone(self.app.openWindow(view.as_uri()))
      self.assertIsNone(self.app.openWindow(view.as_uri())) # (just said: only logged)
    traceback.assert_not_called()
    box.assert_called_once()
    message = box.call_args[0][2]
    self.assertIn('family.snv" couldn\'t be opened', message)
    self.assertIn("isn't letting Eclipse use", message)
    opener.assert_called_once()
    with mock.patch.object(SerializationStrategy, "peekTypex", side_effect=ValueError("not a view")), \
         mock.patch("sn.view.graphics.guiApp.showExceptionDialog") as traceback, \
         self.assertLogs(level="ERROR"):
      self.assertIsNone(self.app.openWindow(view.as_uri()))
    traceback.assert_called_once() # (anything else: the traceback, as before)

  def test0910commandBlockedByPrivacy(self):
    'A menu command (eg: File | Save view) the privacy protection stopped: which app to allow, as well as the usual report.'
    import errno
    box, opener = self.privacy()
    box.return_value = "Not Now"
    path = str(self.folder / "family.snv")
    try:
      try:
        raise PermissionError(errno.EPERM, "Operation not permitted", path)
      except OSError as e:
        raise ValueError(f'Can\'t write "{path}"') from e
    except ValueError as ex:
      with mock.patch("sys.stderr"):
        self.app.report_callback_exception(type(ex), ex, ex.__traceback__)
    self.assertIn('family.snv" couldn\'t be read or written', box.call_args[0][2])
    opener.assert_not_called()
    box.reset_mock()
    with mock.patch("sys.stderr"):
      self.app.report_callback_exception(KeyError, KeyError("x"), None)
    box.assert_not_called()

  def test0920commandFailsReplaced(self):
    '''A command that fails once the program's been replaced since it was
    opened (eg: by a rebuild: "unknown encoding: utf-8-sig", as its codec's
    module can't be loaded any more -- see util.programFiles): say so, offering
    to quit (not again straight away: only logged); not the privacy protection.'''
    from util import programFiles
    box, opener = self.privacy()
    box.return_value = f"Quit {sn.NAME}"
    self.app._replacedExplained = float("-inf")
    ex = LookupError("unknown encoding: utf-8-sig")
    with mock.patch.object(programFiles, "changed", return_value=["/Applications/Semantic Nets.app/Contents/Frameworks/base_library.zip"]), \
         mock.patch.object(self.app, "onQuit") as quit, mock.patch("sys.stderr"), self.assertLogs(level="ERROR"):
      self.app.report_callback_exception(LookupError, ex, None)
      self.assertIn(f"{sn.NAME} has been replaced or moved since it was opened", box.call_args[0][2])
      self.assertIn(f"Quit {sn.NAME} and open it again.", box.call_args[0][2])
      quit.assert_called_once()
      box.reset_mock()
      self.app.report_callback_exception(LookupError, ex, None) # (just said: only logged)
      box.assert_not_called()
    with mock.patch.object(programFiles, "changed", return_value=[]), mock.patch("sys.stderr"):
      self.app.report_callback_exception(LookupError, ex, None) # (not replaced: just the usual report)
    box.assert_not_called()
    opener.assert_not_called()


if __name__ == "__main__":
  unittest.main()
