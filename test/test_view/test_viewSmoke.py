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
from util.utils import urlPath
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
    return SimpleNamespace(**{"x": x, "y": y, "x_root": x, "y_root": y, "state": 0, "delta": 0, "num": 1, "widget": self.view.canvas, **kw})

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
    self.assertFalse(v._layoutPanelShown().get())
    v.showLayoutPanel(True) # (in a window that's never shown, it's made once the window is: see showLayoutPanel())
    self.pump()
    self.assertTrue(v._layoutPanelShown().get())
    self.assertTrue(v._layoutPanelState().startswith("shown=1"))
    v.toggleLayoutPanel()
    self.pump()
    self.assertFalse(v._layoutPanelShown().get())
    self.assertTrue(v._layoutPanelState().startswith("shown=0"))
    v.gatherNodes()
    self.pump()
    self.assertEqual(v.validate(), 0) # (how many problems it found)

  def test0410treeLayoutKeepsDrops(self):
    # (a class with two bases: under the dynamic tree layout, the second base is in no tree -- its only child
    # is under the first -- so it's put near what it's related to. Dropped, it must be pinned, not put back.)
    from sn.model.model import Node
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.relationTable import RelationTable
    v, m = self.view, self.model
    klass = Node(m, [m.NODE], name="klass")
    inherits = Relation(m, [m.RELATION], klass, klass, name="inherits-from")
    a, b, c = (Node(m, [klass], individual=True, name=n) for n in ("base1", "base2", "derived"))
    Relation(m, [inherits], c, a, individual=True)
    Relation(m, [inherits], c, b, individual=True)
    self.pump()
    v.showAllModel()
    self.pump()
    v.setDynamicLayout(TreeLayout(v, relations=RelationTable.decode("inherits-from:shapes:destination"), direction="down",
                                  others="near"))
    self.pump()
    roots, _, _, others, _ = v.localLayout.structure(dynamic=True)
    self.assertIn(self.vo("base1"), roots)
    self.assertIn(self.vo("base2"), others)
    for name in ("base2", "base1"): # (in no tree; a root: both stay where they're dropped)
      vo = self.vo(name)
      bb = vo.boundingBox()
      far = max(o.boundingBox()[2] for o in v.values() if o is not None and o._isConnected()) + 500 # (clear of everything)
      v.context.move(vo, far, bb[1], _oldPos=list(bb), _drag=True)
      self.pump()
      self.assertEqual(vo.boundingBox()[0], far, name)
    self.assertIn(self.vo("base2")._id, v.localLayout.pins)
    self.assertNotIn(self.vo("base1")._id, v.localLayout.pins) # (a root's kept where it is anyway)

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
    text = Path(urlPath(v.url) or "").read_text(encoding="utf-8")
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

  def test0610individuals(self):
    'The "individuals" category: in both menus; hides, or erases, all but the types (relations, isa links too); undone.'
    v = self.view
    for mode in ("hide", "erase"):
      menu = v._visibilityMenu(mode)
      self.assertIn("individuals", [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)
                                    if menu.type(i) == "checkbutton"])
    def objects(individual:bool) -> list:
      return [o for o in v.values() if o is not None and o.modelObject is not None
              and o.modelObject.isIndividual() == individual]
    individuals, types = objects(True), objects(False)
    self.assertTrue(any(isinstance(o.modelObject, Relation) for o in individuals))
    self.assertTrue(any(isinstance(o.modelObject, IsaIndividual) for o in individuals))
    self.assertTrue(types)
    hidden = [o for o in individuals if o._hidden] # (eg: by the view's default hides)
    v.context.visibility("individuals", "hide")
    self.pump()
    self.assertTrue(all(o._hidden for o in individuals))
    self.assertFalse(any(o._hidden for o in types))
    self.assertIn("person", self.shown())
    self.assertNotIn("alice", self.shown())
    v.context.undo()
    self.pump()
    self.assertEqual([o for o in individuals if o._hidden], hidden)
    count = len(list(v.values()))
    v.context.visibility("individuals", "erase")
    self.pump()
    self.assertEqual(objects(True), [])
    self.assertEqual(len(objects(False)), len(types))
    v.context.undo()
    self.pump()
    self.assertEqual(len(list(v.values())), count)
    self.assertIn("alice", self.shown())

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

  def test0850danglingEnds(self):
    # a relation whose own end is top, while top isn't shown, is left dangling there (see
    # VRelation._resolveEnd()): showing top attaches it (see _attachDanglingEnds())
    v, m = self.view, self.model
    top = m.TOP
    self.assertIsNone(v.findViewObjectForGraphObject(top)) # (a super-model's: showAllModel() doesn't show it)
    alice = self.vo("alice")
    toTop = v.context.new_relation("relation", name="toTop", source=alice.modelObject, destination=top)
    fromTop = v.context.new_relation("relation", name="fromTop", source=top, destination=alice.modelObject)
    self.pump()
    vTo, vFrom = (v.findViewObjectForGraphObject(r) for r in (toTop, fromTop))
    assert vTo is not None and vFrom is not None
    self.assertIs(vTo.src, alice)
    self.assertIsNone(vTo.dst)
    self.assertIsNone(vFrom.src)
    self.assertIs(vFrom.dst, alice)
    vTop = v.makeViewObjectForGraphObject(top, atPoint=(400, 400))
    self.pump()
    self.assertIs(vTo.dst, vTop)
    self.assertIs(vFrom.src, vTop)
    self.assertIs(vTo.src, alice) # (the other ends are as they were)
    self.assertIs(vFrom.dst, alice)

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

  def test0910optionClick(self):
    'Option-click: the object and its relations; with Cmd or Shift too, toggled in or out of the selection.'
    from util.utils import _ALT_MASK, _CMD_MASK
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    def click(vo, state):
      x, y = v.viewToWindow(*vo.centerPt())
      ev = self.event(x - v.canvas.canvasx(0), y - v.canvas.canvasy(0), state=state)
      vo.onButton_1(ev)
      v.onButton_1(ev)
      vo.onB1_ButtonRelease(ev)
      v.onB1_ButtonRelease(ev)
    withRels = lambda vo: {vo, *(r for r in vo.relations if not r.isHidden())}
    nodes = [o for o in v._shownObjects() if not isinstance(o, VRelation) and len(withRels(o)) > 1]
    a, b = nodes[0], next(n for n in nodes[1:] if not withRels(n) & withRels(nodes[0]) - {n})
    other = next(o for o in v._shownObjects() if o not in withRels(a) | withRels(b))
    other.selected(True)
    click(a, _ALT_MASK)
    self.assertEqual(set(v.selected), withRels(a))
    click(b, _ALT_MASK | _CMD_MASK) # added
    self.assertEqual(set(v.selected), withRels(a) | withRels(b))
    click(a, _ALT_MASK | 0x1) # (Shift) taken out
    self.assertEqual(set(v.selected), withRels(b))
    click(b, _ALT_MASK) # just b's again
    self.assertEqual(set(v.selected), withRels(b))
    # an Option-drag zooms, and selects nothing
    for o in v.selected.copy(): o.selected(False)
    x, y = v.viewToWindow(*b.centerPt())
    x, y = x - v.canvas.canvasx(0), y - v.canvas.canvasy(0)
    b.onButton_1(self.event(x, y, state=_ALT_MASK))
    v.onButton_1(self.event(x, y, state=_ALT_MASK))
    v.onB1_Motion(self.event(x, y - 50, state=_ALT_MASK))
    v.onB1_ButtonRelease(self.event(x, y - 50, state=_ALT_MASK))
    self.assertFalse(v.selected)

  def test0950validateKey(self):
    'Option-V validates: by the V key, as the keysym is whatever the layout makes of it (the keycodes are from real presses). (Elsewhere, Alt-V: by its keysym.)'
    from sn.view.graphics.viewBase import KEY_VALIDATE, KEY_PASTE
    from util.platformSupport import MAC
    v = self.view
    self.assertNotEqual(KEY_VALIDATE[0], KEY_PASTE[0])
    self.assertTrue(v.canvas.bind(KEY_VALIDATE[0]))
    if not MAC:
      self.assertEqual(KEY_VALIDATE[0], "<Alt-KeyPress-v>")
      return
    self.assertTrue(v.canvas.bind("<Option-KeyPress>"))
    calls = []
    v.validate = lambda refresh=False: calls.append(refresh) or 0 # type: ignore[method-assign]
    key = lambda keycode, state: SimpleNamespace(keycode=keycode, state=state, widget=v.canvas)
    self.assertEqual(v.onOptionKey(key(0x98002c7, 0x10)), "break") # Option-V (ABC Extended: a caron)
    self.assertEqual(calls, [True])
    self.assertIsNone(v.onOptionKey(key(0x9c0030c, 0x11)))       # Shift-Option-V
    self.assertIsNone(v.onOptionKey(key(0x88000b8, 0x10)))       # Option-C
    self.assertEqual(calls, [True])

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

  def test1200newViewOfOpenModel(self):
    'New... a view of a model whose view is open: the model in memory is used, not read again -- which would show all of it in that view.'
    from tkinter import filedialog
    from util.persistence.pRef import PRDb
    v, m = self.view, self.model
    self.app.windows[v.url] = v.window # (as if opened by openWindow())
    before = len(v)
    v.context.visibility("individuals", "erase") # (what's erased mustn't come back, either)
    self.pump()
    shown = len(v)
    self.assertLess(shown, before)
    readFile = PRDb.readFile
    read:list[str] = []
    with mock.patch.object(filedialog, "askopenfilename", return_value=str(self.folder / "family.snm")), \
         mock.patch.object(self.app, "noteRecent"), mock.patch.object(self.app, "noteFile"), \
         mock.patch.object(PRDb, "readFile", side_effect=lambda url, mode="w": read.append(url) or readFile(url, mode=mode)):
      window = self.app.openWindow(str(self.folder / "other.snv"))
    try:
      self.pump()
      self.assertIsNotNone(window)
      self.assertIs(window.view.model, m)
      self.assertEqual(len(window.view), 0)
      self.assertEqual(read, [])
      self.assertEqual(len(v), shown)
    finally:
      window.view.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(window)
      self.app.windows.pop(window.view.url, None)
      window.destroy()

  def test1210showAllOfBigModel(self):
    'Show all, on a model with too many objects to show: just its types are shown.'
    from sn.view.graphics.sngView import SNGView
    from sn.view.graphics.layout import nodeTypes
    m = self.model
    v = SNGView(fixURL(str(self.folder / "big.snv"), None, replaceExt=None, mode="w")[0], model=m)
    try:
      v.window.withdraw()
      get = sn.snPrefs.get
      with mock.patch.object(sn.snPrefs, "get", side_effect=lambda key, *a, **kw: 3 if key == "gui/ShowAllMax" else get(key, *a, **kw)):
        v.showAllModel()
      self.pump()
      nodes = {o.modelObject for o in v.values() if o is not None and o.modelObject is not None and not isinstance(o.modelObject, Relation)}
      self.assertEqual(nodes, set(nodeTypes(m)))
      self.assertTrue(all(isinstance(o.modelObject, IsaIndividual) for o in v.values()
                          if o is not None and isinstance(o.modelObject, Relation)))
      class E: x = y = x_root = y_root = 10
      with mock.patch("sn.view.graphics.viewInput.SHOW_MENU_MAX", 3):
        menu = v.makeMenu(E()) # type: ignore[arg-type]
      self.assertIsNotNone(menu)
    finally:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
      v.window.destroy()

  def test1300helpPages(self):
    'Each Help menu item that shows a page of the documentation shows one there is (eg: "Keys and Mouse").'
    shown:list[str] = []
    menu = self.app.helpmenu
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
    self.assertIn("Keys and Mouse", labels)
    with mock.patch.object(self.app, "showHelp", side_effect=shown.append):
      for label in labels:
        if "Guide" in label or label == "Keys and Mouse":
          menu.invoke(label)
      self.pump() # (on the Mac, afterMenu() runs them from the event loop)
    self.assertIn("user/shortcuts.html", shown)
    source = Path(sn.resourcePath("sphinx", "source"))
    for page in shown:
      self.assertTrue((source / page).with_suffix(".rst").exists(), page)

  def test1310helpServedNotFile(self):
    'showHelp() opens the page from the documentation\'s local web server, not as a file: URL (Safari leaves those unstyled).'
    import tempfile
    from util import folderServer
    with tempfile.TemporaryDirectory() as top:
      os.makedirs(os.path.join(top, "user"))
      Path(top, "user", "shortcuts.html").write_text("<p>keys</p>")
      with mock.patch.object(sn, "resourcePath", side_effect=lambda *parts: top if parts == ("help",) else "/nonexistent"), \
           mock.patch.object(folderServer.webbrowser, "open") as op:
        self.app.showHelp("user/shortcuts.html")
      try:
        op.assert_called_once()
        url = op.call_args[0][0]
        self.assertTrue(url.startswith("http://127.0.0.1:") and url.endswith("/user/shortcuts.html"), url)
        import urllib.request
        with urllib.request.urlopen(url, timeout=5) as r:
          self.assertEqual(r.read(), b"<p>keys</p>")
      finally:
        folderServer.stopServing(top)

  def test1400recentShowsWholePaths(self):
    'File | Open Recent shows each view\'s whole path ("~" for the home folder), or a web one\'s whole URL.'
    home = Path.home()
    entries = [{"view": (home / "a" / "family.snv").as_uri(), "model": ""},
               {"view": (home / "b" / "family.snv").as_uri(), "model": ""},
               {"view": "https://example.org/models/web.snv", "model": ""},
               {"view": (home / ("x" * 150) / "long.snv").as_uri(), "model": ""}]
    with mock.patch.object(self.app, "recentFiles", return_value=entries):
      self.app._fillRecentMenu()
    try:
      menu = self.app.recentMenu
      labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
      shown = (lambda p: "~" + str(p)[len(str(home)):]) if sys.platform != "win32" else str # (no "~" on Windows)
      self.assertEqual(labels[:3], [shown(home / "a" / "family.snv"), shown(home / "b" / "family.snv"),
                                    "https://example.org/models/web.snv"])
      self.assertEqual(len(labels[3]), self.app.RECENT_LABEL_LENGTH)
      self.assertTrue(labels[3].endswith("long.snv"))
      self.assertEqual(labels[4], "Clear Menu")
    finally:
      self.app._fillRecentMenu()

if __name__ == "__main__":
  unittest.main()
