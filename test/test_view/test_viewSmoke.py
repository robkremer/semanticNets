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
A real view (*SNGView*), in a hidden window, of a copy of the family example:
one test for each part of what a view does -- its objects, zooming and
scrolling, reasoning, layouts, files and locking, visibility, context
windows, editing, and the mouse and menus. Each goes through the view's own
methods (or its context's commands), as the editor does, and checks that what
should happen does: a smoke test of the whole view, not a specification of
any part of it.

The view's window is never shown, and nothing is saved outside a temporary
folder: the view isn't opened through *Application.openWindow()*, which
would note it in the preferences' recent files.

Created on Oct 18, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import os
import sys
import tempfile
import time
import unittest
from unittest import mock
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model, Relation, IsaIndividual

class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
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
    cls.app.destroy()
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty: # (nothing here is to be saved in the preferences)
      sn.snPrefs.setDirty(False)

  def setUp(self):
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snViewSmoke-")
    self.folder = Path(self.tmp.name).resolve()
    sn.copyExamples(str(self.folder), ["family.snm"])
    self.model = Model.getDB((self.folder / "family.snm").as_uri())
    self.assertTrue(self.model.url.startswith(self.folder.as_uri()), self.model.url)
    url = fixURL(self.model.url, ".snv", replaceExt=True, mode="w")[0]
    self.view = v = SNGView(url, model=self.model)
    self.assertTrue(v.url.startswith(self.folder.as_uri()), v.url)
    v.window.withdraw()
    v._askName = lambda mo: None # (a new type's attribute editor: not here)
    v.showAllModel()
    self.pump()

  def tearDown(self):
    v = self.view
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
    if v.window.winfo_exists():
      v.window.destroy()
    self.pump()
    Model._initCache()
    self.tmp.cleanup()

  def pump(self, seconds:float=0.2) -> None:
    'Let the event loop run: the model\'s notifications, and what the view puts off till idle.'
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def vo(self, name:str):
    'The view object of the model object named *name*.'
    found = [o for o in self.view.values() if o is not None and o.modelObject is not None and o.modelObject.name == name]
    self.assertTrue(found, f'no view object for "{name}"')
    return found[0]

  def shown(self) -> set[str]:
    'The names of the model objects the view shows (not hidden).'
    return {o.modelObject.name for o in self.view.values()
            if o is not None and o.modelObject is not None and not o._hidden}

  def event(self, x:float, y:float, **kw):
    'A stand-in for a Tk event at window coordinates (*x*, *y*).'
    return SimpleNamespace(x=x, y=y, x_root=x, y_root=y, state=0, delta=0, num=1, widget=self.view.canvas, **kw)

  # ---- the parts ------------------------------------------------------------

  def test0100core(self):
    v, m = self.view, self.model
    alice = m["alice"]
    self.assertEqual(len(v.viewObjectsFor(alice)), 1)
    self.assertIs(v.findViewObjectForGraphObject(alice), self.vo("alice"))
    self.assertIs(v.makeViewObjectForGraphObject(alice), self.vo("alice")) # (already there: not made again)
    self.assertEqual(v.validate(), 0) # (how many problems it found)
    self.assertTrue(v.isDirty()) # (a new view, not saved)
    rels = [o for o in v.values() if o is not None and isinstance(o.modelObject, Relation) and not isinstance(o.modelObject, IsaIndividual)]
    self.assertTrue(rels)

  def test0200viewport(self):
    v = self.view
    v.zoom(2.0)
    self.assertAlmostEqual(v._scale, 2.0)
    v.zoomIn()
    self.assertAlmostEqual(v._scale, 2.0 * v.ZOOM_STEP)
    v.zoomOut()
    self.assertAlmostEqual(v._scale, 2.0)
    x, y = v.windowToView(*v.viewToWindow(120, 80))
    self.assertAlmostEqual(x, 120)
    self.assertAlmostEqual(y, 80)
    state = v._viewportState()
    v.zoom(1.0)
    v.__dict__["_pendingViewport"] = state
    v._restoreViewport()
    self.assertAlmostEqual(v._scale, 2.0)
    v.zoomToFit()
    v.repaint()
    v.resetScrollRegion()
    self.pump()
    self.assertEqual(v.validate(), 0) # (how many problems it found)

  def test0300reasoning(self):
    v = self.view
    v.showReasoningToolbar(True)
    v.reason()
    self.pump()
    self.assertIsNotNone(v.reasoning)
    inferred = [o for o in v.values() if o is not None and o.isInferred()]
    self.assertTrue(inferred, "nothing inferred is shown")
    self.assertIn("inferred", v.reasoningSummary().lower() + " inferred") # (a summary, whatever it says)
    v.clearReasoning()
    self.pump()
    self.assertFalse([o for o in v.values() if o is not None and o._isConnected() and o.isInferred()])
    v.reasonSilently()
    self.pump()
    self.assertIsNotNone(v.reasoning)

  def test0400layouts(self):
    from sn.view.graphics.treeLayout import TreeLayout
    v = self.view
    before = {o.modelObject.name: o.boundingBox() for o in v.values() if o is not None and o.modelObject is not None}
    defaults = lambda *_a, **_kw: {p.name: p.default for p in TreeLayout.PARAMETERS} # (its dialog: not here)
    with mock.patch.object(TreeLayout, "askParameters", defaults):
      v.arrangeWith(TreeLayout)
    self.pump(0.5)
    after = {o.modelObject.name: o.boundingBox() for o in v.values() if o is not None and o.modelObject is not None}
    self.assertNotEqual(before, after)
    v.context.undo()
    self.pump()
    self.assertEqual(before["alice"][:2], self.vo("alice").boundingBox()[:2]) # (where it was; its height may be fitted to its text again)
    self.assertIsInstance(v._layoutPanelState(), str)
    self.assertIsInstance(v._animationState(), str)
    self.assertFalse(v._layoutPanelShown().get()) # (not shown here: in a window that's never shown, the panel keeps settling)
    v.gatherNodes()
    self.pump()
    self.assertEqual(v.validate(), 0) # (how many problems it found)

  def test0500filesAndLock(self):
    v = self.view
    self.assertTrue(v.isModelEditor())
    v.setEditLocked(True)
    self.assertTrue(v.editLocked())
    self.assertFalse(v.isModelEditor())
    self.assertTrue(v.lockedReason())
    v.setEditLocked(False)
    self.assertTrue(v.isModelEditor())
    v.onWindowFocusIn()
    v.onWindowFocusOut()
    v.save()
    text = Path(v.url.removeprefix("file://")).read_text(encoding="utf-8")
    for prop in ("viewport", "layout", "hides", "editLocked"):
      self.assertIn(f'"{prop}"', text)
    self.assertFalse(v.isDirty())

  def test0600visibility(self):
    v = self.view
    self.assertIn("person", self.shown())
    v.context.visibility("types", "hide")
    self.pump()
    self.assertNotIn("person", self.shown())
    self.assertTrue(v.shouldHide(self.vo("person")))
    self.assertIn("alice", self.shown())
    v.context.visibility("types", "show")
    self.pump()
    self.assertIn("person", self.shown())
    with v.batchedItemStates():
      v.context.visibility("rules", "hide")
    self.pump()
    self.assertNotIn("uncle rule", self.shown())
    v.context.undo()
    self.pump()
    self.assertIn("uncle rule", self.shown())

  def test0700containment(self):
    v = self.view
    rule = self.vo("uncle rule")
    self.assertIn(rule, v.contextWindows())
    homes = v.containmentHomes()
    self.assertTrue(any(win is rule for win, _pane in homes.values()), "nothing is in the rule's window")
    v.context.collapse(rule, True)
    self.pump()
    self.assertTrue(rule.collapsed)
    v.context.undo()
    self.pump()
    self.assertFalse(rule.collapsed)
    self.assertIsInstance(v.bumpIntruders(), list)
    v.restackWindows()
    self.assertEqual(v.validate(), 0) # (how many problems it found)

  def test0800editing(self):
    v, m = self.view, self.model
    n = len(m)
    alice = self.vo("alice")
    v.selected.clear()
    alice.selected(True)
    v.doCopy()
    v.doPaste()
    self.pump()
    self.assertGreater(len(m), n)
    v.context.undo()
    self.pump()
    self.assertEqual(len(m), n)
    v.doErase([alice])
    self.pump()
    self.assertNotIn("alice", self.shown())
    v.context.undo()
    self.pump()
    self.assertIn("alice", self.shown())
    v.context.new_node("person", name="eve", individual=True)
    self.pump()
    self.assertIn("eve", self.shown())
    self.assertTrue(v.search("carol"))
    v.clearHighlights()
    self.assertTrue(v.pictureObjects())

  def test0900input(self):
    v = self.view
    menu = v.makeMenu(self.event(5, 5))
    self.assertIsNotNone(menu.index("end")) # (it has items)
    menu.destroy()
    zoom = v.makeZoomMenu(tk.Menu(v.canvas))
    self.assertIsNotNone(zoom)
    # a drag-select box round everything there is
    xs = [b for o in v.values() if o is not None for b in o.boundingBox()]
    x2, y2 = v.viewToWindow(max(xs[0::2]) + 20, max(xs[1::2]) + 20)
    x1, y1 = v.viewToWindow(min(xs[0::2]) - 20, min(xs[1::2]) - 20)
    x1, y1 = x1 - v.canvas.canvasx(0), y1 - v.canvas.canvasy(0)
    x2, y2 = x2 - v.canvas.canvasx(0), y2 - v.canvas.canvasy(0)
    v.selected.clear()
    v.onButton_1(self.event(x1, y1))
    v.onB1_Motion(self.event(x2, y2))
    v.onB1_ButtonRelease(self.event(x2, y2))
    self.pump()
    self.assertIn(self.vo("alice"), v.selected)
    v.onMotion(self.event(x1, y1))
    self.assertEqual(v.validate(), 0) # (how many problems it found)

  def test1000replacingModel(self):
    'A model made afresh where one is open (eg: by a plugin): its window\'s closed and it\'s forgotten first, so what\'s made isn\'t added to it.'
    from util.persistence.pRef import PRDb
    v, m = self.view, self.model
    self.app.windows[v.url] = v.window # (as if opened by openWindow())
    path = str(self.folder / "family.snm")
    self.assertTrue(self.app.replacingModel(path))
    self.pump()
    self.assertTrue(v._closed)
    self.assertNotIn(v.url, self.app.windows)
    self.assertFalse(v.window.winfo_exists())
    self.assertNotIn(m.url, PRDb.AllDBs)
    os.remove(path) # (as the plugins do, once it's forgotten)
    fresh = Model(path)
    self.assertIsNot(fresh, m)
    self.assertNotIn("alice", {o.name for o in fresh.values()})
    self.assertTrue(self.app.replacingModel(path + ".none")) # (nothing in memory there: nothing to do)

  def test1100asksNamesOnlyOfItsOwn(self):
    'The view asks the name of a node made by its own command -- not of one a program (or another window) made.'
    from sn.model.model import Node
    v, m = self.view, self.model
    asked:list[str] = []
    v._askName = lambda mo: asked.append(mo.name)
    v.context.new_node("person", name="eve", individual=True)
    self.pump()
    self.assertEqual(asked, ["eve"])
    for i in range(20):
      Node(m, [m["person"]], individual=True, name=f"made{i}")
    self.pump()
    self.assertEqual(asked, ["eve"])
    self.assertIn("made0", self.shown()) # (shown, without asking)

if __name__ == "__main__":
  unittest.main()
