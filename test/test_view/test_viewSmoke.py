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
import importlib.util
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
from sn.model.model import Model, Node, Relation, IsaIndividual
from util.commandParser import CompositeCommandMgr

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
    v._askName = lambda mo, objectID=None: None # (a new type's attribute editor: not here)
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
    rel = next(o for o in inferred if isinstance(o.modelObject, Relation) and o.modelObject.isIndividual()
               and not isinstance(o.modelObject, IsaIndividual))
    menu = tk.Menu(v.window)
    try:
      rel.addModelEditingMenuItems(menu)
      labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"] # type: ignore[operator]
    finally:
      menu.destroy()
    self.assertIn("mark as asserted", labels)
    self.assertIn("explain (why it holds)", labels) # (whether or not an engine that explains is installed)
    if importlib.util.find_spec("nmo_python") is not None: # (the optional Nemo engine: it explains)
      with mock.patch("builtins.print") as printed:
        rel.explainInferred(rel.modelObject)
      self.assertTrue(printed.call_args and "doesn't hold" not in str(printed.call_args[0][0]), printed.call_args)
    from sn.model.reasoner import EngineMissing
    with mock.patch.object(v.context, "explain", side_effect=EngineMissing("nemo")), \
         mock.patch("sn.view.graphics.viewReasoning.showEngineMissing") as shown:
      rel.explainInferred(rel.modelObject) # (no engine that explains: a dialog says how to install one)
    shown.assert_called_once()
    self.assertEqual(shown.call_args[0][1].engine, "nemo")
    v.clearReasoning()
    self.pump()
    self.assertFalse([o for o in v.values() if o is not None and o._isConnected() and o.isInferred()])
    v.reasonSilently()
    self.pump()
    self.assertIsNotNone(v.reasoning)

  def test0305reasonAbout(self):
    'An object\'s (or the selection\'s) "reason", "reason silently" and "retract": just what\'s about them.'
    v = self.view
    inferred = lambda: sorted(f"{o.modelObject.localSrc.name} {o.modelObject.localDst.name}" for o in v.values()
                              if o is not None and o._isConnected() and o.isInferred() and isinstance(o.modelObject, Relation)
                              and not isinstance(o.modelObject, IsaIndividual))
    marked = lambda name: [m for m in self.vo(name).statusReport() if "reasoner:" in str(m)]
    def invoke(vo, label:str) -> None:
      menu = vo.makeMenu()
      try:
        labels = [menu.entrycget(i, "label") if menu.type(i) == "command" else None for i in range(menu.index("end") + 1)] # type: ignore[operator]
        self.assertIn(label, labels)
        menu.invoke(labels.index(label))
      finally:
        menu.destroy()
      self.pump()
    carol = self.vo("carol")
    invoke(carol, "reason")                                       # carol -has-uncle-> bob (through alice's inferred sibling)
    self.assertEqual(inferred(), ["carol bob"])
    self.assertEqual(marked("bob"), [])                           # (bob's warning isn't about carol)
    self.assertTrue(v.reasoningSummary().startswith("about carol:"), v.reasoningSummary())
    invoke(self.vo("bob"), "reason silently")                     # (bob's: in the model, not drawn -- but marked)
    self.assertEqual(inferred(), ["carol bob"])
    self.assertTrue(marked("bob"))
    self.vo("alice").selected(True)
    self.vo("bob").selected(True, _multi=True)
    invoke(self.vo("alice"), "reason (2 selected)")                # (both: one run)
    self.assertEqual(inferred(), ["alice bob", "alice bob", "carol bob"])
    self.vo("alice").selected(False); self.vo("bob").selected(False)
    invoke(carol, "retract")
    self.assertNotIn("carol bob", inferred())
    v.clearReasoning()
    self.pump()
    self.assertEqual(inferred(), [])

  def test0310engineMissing(self):
    'A missing reasoner engine is said in a dialog, with a link to how to install it, and to the installed ones.'
    from sn.model.reasoner import EngineMissing, INSTALL_HELP
    from sn.view.graphics import viewReasoning
    v = self.view
    with mock.patch("sn.model.reasoner.reason", side_effect=EngineMissing("nemo")), \
         mock.patch.object(viewReasoning, "showEngineMissing") as shown:
      v.reason("nemo")
    shown.assert_called_once()
    instead = shown.call_args[1]["instead"]
    with mock.patch.object(type(v), "reason") as reasoned:
      instead("clingo") # (its "Use clingo this time")
    reasoned.assert_called_once_with("clingo", silent=False, about=None)

    with mock.patch("sn.model.reasoner.defaultEngine", return_value="nemo"), \
         mock.patch("sn.model.reasoner.installedEngines", return_value=["clingo"]), \
         mock.patch("sn.model.reasoner.setDefaultEngine") as chose:
      d = viewReasoning.showEngineMissing(v.canvas, EngineMissing("nemo"), instead=lambda e: None)
    try:
      text = d.text.get("1.0", "end")
      self.assertIn('The "nemo" reasoner engine isn\'t installed.', text)
      self.assertIn("How to install it", text)
      self.assertIn("Use clingo this time", text)
      self.assertIn("Use clingo from now on", text)
      with mock.patch("sn.view.graphics.guiApp.showHelp") as helped:
        d._actions["help"]()
      helped.assert_called_once_with(INSTALL_HELP)
      d._actions["pref:clingo"]()
      chose.assert_called_once_with("clingo")
    finally:
      d.destroy()

    d = viewReasoning.showEngineMissing(v.canvas, EngineMissing("nemo", "DLL load failed"))
    try:
      text = d.text.get("1.0", "end")
      self.assertIn("isn't working", text)
      self.assertIn("DLL load failed", text)
      self.assertNotIn("this time", text) # (nothing to do instead: eg, for explain)
    finally:
      d.destroy()

  def test0312engineBox(self):
    'The reasoning toolbar says which engine reasoning uses, and its menu chooses another -- but not one that isn\'t installed.'
    from sn.model import reasoner
    from sn.view.graphics import viewReasoning
    v = self.view
    v.showReasoningToolbar(True)
    bar = v._reasoningToolbar
    original = reasoner.defaultEngine()
    self.assertEqual(bar.engineLabel.cget("text"), f"{original} ▾")
    with mock.patch.object(bar.engineMenu, "tk_popup") as popped:
      bar.showEngineMenu()
    menu = bar.engineMenu
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"] # type: ignore[operator]
    self.assertIn("clingo", labels)
    self.assertEqual(len([l for l in labels if l.split()[0] in reasoner.ENGINES]), len(reasoner.ENGINES))
    self.assertIn("How to install an engine...", labels)
    self.assertEqual(labels[popped.call_args[0][2]].split()[0], original) # (the current one is over the box)
    try:
      with mock.patch("sn.model.reasoner.engineInstalled", return_value=False), \
           mock.patch.object(viewReasoning, "showEngineMissing") as shown:
        bar.chooseEngine("prolog")
      shown.assert_called_once()
      self.assertEqual(shown.call_args[0][1], "prolog")
      self.assertEqual(reasoner.defaultEngine(), original) # (not chosen)
      other = "nemo" if original != "nemo" else "clingo"
      with mock.patch("sn.model.reasoner.engineInstalled", return_value=True):
        bar.chooseEngine(other)
      self.assertEqual(reasoner.defaultEngine(), other)
      self.assertEqual(bar.engineLabel.cget("text"), f"{other} ▾") # (the setting's callback shows it)
      reasoner.setDefaultEngine(original) # (eg: from the dialog's "Use ... from now on")
      self.assertEqual(bar.engineLabel.cget("text"), f"{original} ▾")
    finally:
      reasoner.setDefaultEngine(original)

  def test0315engineMissingTyped(self):
    'A typed command that needs a missing engine says so in a line, and the dialog links to how to install it.'
    from sn.model.reasoner import EngineMissing
    from sn.view.graphics import viewReasoning
    term = self.view.terminal
    with mock.patch.object(term.context.parser, "parseLine", side_effect=EngineMissing("nemo")), \
         mock.patch.object(viewReasoning, "showEngineMissing") as shown, \
         self.assertLogs("sn", "ERROR") as logged:
      self.assertIsNone(term._onLine("explain ancestorOf ann fred"))
      self.pump()
    self.assertIn("pip install nemo-python", "\n".join(logged.output))
    shown.assert_called_once()
    self.assertIs(shown.call_args[0][0], term)

  def test0320showHelpSection(self):
    'A help page\'s section is shown when the page is there (eg: in the bundled help).'
    from sn.view.graphics import guiApp
    with tempfile.TemporaryDirectory() as top:
      os.makedirs(os.path.join(top, "user"))
      Path(top, "user", "reasoning.html").write_text("<html></html>")
      with mock.patch.object(sn, "resourcePath", lambda *parts: top if parts == ("help",) else "/nowhere"), \
           mock.patch("util.folderServer.openInBrowser") as opened:
        guiApp.showHelp("user/reasoning.html#installing-an-engine")
    opened.assert_called_once_with(top, "user/reasoning.html#installing-an-engine")

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

  def test0440arrangedLabelsOffNodes(self):
    # "arrange now": the labels of the relations the layout doesn't place itself (here: all but isa) aren't left
    # on the nodes it arranges; one undo puts them back. An isa link's label (it shows no text) isn't pinned.
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.balloonLayout import HubLayout
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    def onNodes() -> list:
      inWindows = v.containmentHomes()
      shown = [o for o in v._shownObjects() if o not in inWindows and not o.isContextWindow()]
      nodes = [o for o in shown if not isinstance(o, VRelation)]
      overlap = lambda a, b: a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
      return [(r.name, n.name) for r in shown if isinstance(r, VRelation) and r._labelShown()
              for n in nodes if overlap(r.boundingBox(), n.boundingBox())]
    # (what's put back exactly: not floating labels -- they go between their ends, wherever those are)
    places = lambda: {o: o.boundingBox()[:2] for o in v._shownObjects() if not (isinstance(o, VRelation) and o.floating())}
    for cls in (TreeLayout, HubLayout):
      with self.subTest(layout=cls.NAME):
        before = places()
        floating = {o for o in v._shownObjects() if isinstance(o, VRelation) and o.floating()}
        cls(v, **{p.name: p.default for p in cls.PARAMETERS}).arrange(animate=False)
        self.pump()
        self.assertEqual(onNodes(), [])
        isas = [r for r in v._shownObjects() if isinstance(r, VRelation) and isinstance(r.modelObject, IsaIndividual)]
        self.assertTrue(isas)
        self.assertTrue(all(r.floating() for r in isas)) # (no text: not pinned -- its line runs through it)
        v.context.undo()
        self.pump()
        self.assertEqual(places(), before)
        self.assertEqual({o for o in v._shownObjects() if isinstance(o, VRelation) and o.floating()}, floating)

  def test0450animationSwitchesLayoutBack(self):
    # starting the animation switches a kept tree layout to "avoid overlaps"; undoing the run puts the tree back,
    # as it was (its pins too), without arranging anything; redoing it switches again
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.layout import FindFree
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    tree = TreeLayout(v, **{p.name: p.default for p in TreeLayout.PARAMETERS})
    v.setDynamicLayout(tree)
    self.pump()
    tree.pins.add(12345)
    v.toggleAnimationLayout()
    self.assertIsInstance(v.localLayout, FindFree)
    self.pump(0.3)
    v.toggleAnimationLayout() # (stopped: the run's one command)
    self.pump()
    self.assertIsInstance(v.localLayout, FindFree)
    nodes = lambda: {o: o.boundingBox()[:2] for o in v._shownObjects() if not isinstance(o, VRelation)}
    after = nodes()
    v.context.undo()
    self.pump()
    self.assertIs(v.localLayout, tree)
    self.assertIn(12345, tree.pins)
    v.context.redo()
    self.pump()
    self.assertIsInstance(v.localLayout, FindFree)
    self.assertEqual(nodes(), after)

  def inheritance(self):
    '''
    A class with two bases, and a grandchild: under a tree of "inherits-from", base1 -> derived -> grandchild; the
    relation from derived to base2 shapes the tree but isn't a tree relation ("loose").

    :returns: The view objects of base1, base2, derived, grandchild, and the loose relation.
    '''
    from sn.model.model import Node
    v, m = self.view, self.model
    klass = Node(m, [m.NODE], name="klass")
    inherits = Relation(m, [m.RELATION], klass, klass, name="inherits-from")
    a, b, c, d = (Node(m, [klass], individual=True, name=n) for n in ("base1", "base2", "derived", "grandchild"))
    Relation(m, [inherits], c, a, individual=True)
    loose = Relation(m, [inherits], c, b, individual=True)
    Relation(m, [inherits], d, c, individual=True)
    self.pump()
    v.showAllModel()
    self.pump()
    return (*(self.vo(n) for n in ("base1", "base2", "derived", "grandchild")), v.findViewObjectForGraphObject(loose))

  def dropLabel(self, rel) -> list:
    'Drag the label of *rel* clear of everything, and drop it, as the user does: :returns: where it was dropped.'
    v = self.view
    bb = rel.boundingBox()
    far = max(o.boundingBox()[2] for o in v.values() if o is not None and o._isConnected()) + 500
    v.context.move(rel, far, bb[1], _oldPos=list(bb), _drag=True, _wasFloating=rel.floating(), _group=[rel])
    self.pump()
    return [far, bb[1]]

  def test0420keptLayoutsLeaveLooseLabels(self):
    # a kept tree (and balloon) layout leaves the label of a relation that isn't a tree relation as it is: floating,
    # or where the user dropped it; undoing the drop floats it again
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.balloonLayout import BalloonLayout
    from sn.view.graphics.relationTable import RelationTable
    v = self.view
    _a, _b, _c, _d, loose = self.inheritance()
    table = lambda: RelationTable.decode("inherits-from:shapes:destination")
    for layout in (TreeLayout(v, relations=table(), direction="down", others="near"), BalloonLayout(v, relations=table())):
      with self.subTest(layout=layout.NAME):
        loose.floating(True)
        v.setDynamicLayout(layout)
        self.pump()
        self.assertIn(loose, v.localLayout.structure(dynamic=True)[4] if isinstance(layout, TreeLayout)
                             else v.localLayout._tree().structure(dynamic=True)[4])
        self.assertTrue(loose.floating())
        at = self.dropLabel(loose)
        self.assertFalse(loose.floating())
        self.assertEqual(loose.boundingBox()[:2], at)
        v.context.new_node("node", name=f"another {layout.NAME}", individual=True) # (a command: the layout adjusts after it)
        self.pump()
        self.assertFalse(loose.floating())
        self.assertEqual(loose.boundingBox()[:2], at)
        v.context.undo() # (the new node)
        v.context.undo() # (the drop)
        self.pump()
        self.assertTrue(loose.floating())

  def test0430subtreeDraggedTogether(self):
    # a parent dragged together with its child under a kept tree layout: the parent is pinned, as the root of
    # its subtree, and the child stays under it
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.relationTable import RelationTable
    v = self.view
    _a, _b, c, d, _loose = self.inheritance()
    v.setDynamicLayout(TreeLayout(v, relations=RelationTable.decode("inherits-from:shapes:destination"), direction="down",
                                  others="near"))
    self.pump()
    far = max(o.boundingBox()[2] for o in v.values() if o is not None and o._isConnected()) + 500
    with CompositeCommandMgr(v.context):
      for n in (c, d):
        bb = n.boundingBox()
        v.context.move(n, far + bb[0] - c.boundingBox()[0], bb[1], _oldPos=list(bb), _drag=True, _group=[c, d])
    self.pump()
    self.assertIn(c._id, v.localLayout.pins)
    self.assertNotIn(d._id, v.localLayout.pins)
    roots, children, _, _, _ = v.localLayout.structure(dynamic=True)
    self.assertIn(c, roots)
    self.assertIn(d, [k for g in children.get(c, []) for k in g])
    self.assertEqual(c.boundingBox()[0], far)

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
    from util.utils import getMenuBar, getSubMenu
    edit = getSubMenu(getMenuBar(), "Edit", makeIfNone=None) # type: ignore[arg-type]
    assert edit is not None
    states = lambda: [str(edit.entrycget(path.split("|")[1], "state")) for path in v.MODEL_EDIT_ITEMS]
    self.assertEqual(states(), ["normal", "normal"])
    v.setEditLocked(True) # (greyed out while the model can't be changed here)
    self.assertEqual(states(), ["disabled", "disabled"])
    v.setEditLocked(False)
    self.assertEqual(states(), ["normal", "normal"])
    v.onWindowFocusOut()
    v.setEditLocked(True) # (not its items now: nothing's done to them)
    v.setEditLocked(False)
    v.model._writeLocked = True
    try:
      v.onWindowFocusIn()
      self.assertEqual(states(), ["disabled", "disabled"])
      self.assertEqual(str(edit.entrycget("Lock view", "state")), "disabled") # (and checked: it can't be unlocked)
      self.assertTrue(v._editLockedVar().get())
      v.model._writeLocked = False
      v.refreshLock()
      self.assertEqual(str(edit.entrycget("Lock view", "state")), "normal")
      self.assertEqual(states(), ["normal", "normal"])
      v.onWindowFocusOut()
    finally:
      v.model._writeLocked = False
      v.setEditLocked(False)
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

  def test0620relationCategoryByName(self):
    '''
    A relation type's category hides the relations of every type of that name:
    eg: of two copies of an ontology a model reaches (one beside it, and the
    one its objects were made with) -- as with views read from the web.
    '''
    v, m = self.view, self.model
    likes = next(o for o in m.values() if o is not None and o.name == "likes" and not o.isIndividual())
    person = next(o for o in m.values() if o is not None and o.name == "person" and not o.isIndividual())
    alice, bob = self.vo("alice").modelObject, self.vo("bob").modelObject
    copy = Relation(m, parents=[m.RELATION], src=person, dst=person, name="likes") # (another type of the same name)
    rel = Relation(m, parents=[copy], src=bob, dst=alice, individual=True, name="likes")
    self.pump()
    vo = v.findViewObjectForGraphObject(rel) or v.makeViewObjectForGraphObject(rel)
    self.pump()
    self.assertIsNot(copy, likes)
    v.context.visibility(v.relationCategory("likes"), "hide")
    self.pump()
    self.assertTrue(vo._hidden)

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

  def intruders(self) -> list:
    'What overlaps a context window it doesn\'t belong in: (object, window) names.'
    v = self.view
    homes = v.containmentHomes()
    return [(o.modelObject.name, w.modelObject.name) for w in v._visibleWindows() for o in v.values()
            if o is not None and o._isConnected() and not o.isHidden() and v._intrudes(o, w, homes)]

  def test0710strayVariablesGoHome(self):
    'Show all puts a rule\'s variables in its window; one moved out of it goes back after the next change, undone with it.'
    v = self.view
    rule = self.vo("uncle rule")
    self.assertEqual(v.strayVariables(), {})
    x = next(vo for vo, (w, _) in v.containmentHomes().items() if w is rule and vo.modelObject.isVariable())
    rb = rule.boundingBox()
    x.moveTo(rb[2] + 300, rb[3] + 300, adjustPos=False) # (not a command: eg: as an old view might have it)
    self.assertEqual(v.strayVariables(), {rule: [x]})
    alice = self.vo("alice")
    bb = alice.boundingBox()
    v.context.move(alice, bb[0] + 5, bb[1], _oldPos=list(bb))
    self.pump()
    self.assertIsNotNone(rule.paneAt(x.centerPt()))
    self.assertEqual(v.strayVariables(), {})
    self.assertEqual(self.intruders(), [])
    v.context.undo()
    self.pump()
    self.assertEqual(v.strayVariables(), {rule: [x]})

  def test0720windowsDontGoIntoRules(self):
    'A window dropped on a rule isn\'t put in it (it\'s pushed off); dropped in a plain context, it is.'
    from util.commandParser import CompositeCommandMgr
    v = self.view
    rule, brother, query = self.vo("uncle rule"), self.vo("brother def"), self.vo("who likes dave?")
    def drop(w, on):
      old = {w: w.centerPt()}
      bb, (px1, py1, px2, py2) = w.boundingBox(), next(iter(on.panes().values()))
      x, y = (px1 + px2 - bb[2] + bb[0]) / 2, (py1 + py2 - bb[3] + bb[1]) / 2
      w.moveTo(x, y, adjustPos=False) # (as the drag moves it, before it's dropped: see VObject.onB1_ButtonRelease())
      with CompositeCommandMgr(v.context):
        v.context.move(w, x, y, _oldPos=list(bb), _drag=True)
        v._updateContainment(old)
      self.pump()
    drop(brother, rule)
    self.assertEqual(rule.containmentOf(brother.modelObject), [])
    self.assertEqual(self.intruders(), [])
    rb, bb = rule.boundingBox(), brother.boundingBox()
    self.assertFalse(rb[0] < bb[2] and bb[0] < rb[2] and rb[1] < bb[3] and bb[1] < rb[3], "still on the rule")
    drop(brother, query)
    self.assertNotEqual(query.containmentOf(brother.modelObject), [])

  def nested(self):
    '''
    "brother def" dropped in the query "who likes dave?" (a plain context): a window in a window. With nothing
    hidden by a category (a fresh view's default).

    :returns: The query's window and brother def's.
    '''
    v = self.view
    query, brother = self.vo("who likes dave?"), self.vo("brother def")
    for c in list(v.hides):
      v.context.visibility(c, "show")
    old = {brother: brother.centerPt()}
    bb, (px1, py1, px2, py2) = brother.boundingBox(), query.panes()["contains"]
    x, y = (px1 + px2 - bb[2] + bb[0]) / 2, (py1 + py2 - bb[3] + bb[1]) / 2
    if bb[2] - bb[0] > px2 - px1 or bb[3] - bb[1] > py2 - py1: # (room for it)
      qb = query.boundingBox()
      query.boundingBox([qb[0], qb[1], qb[2] + bb[2] - bb[0] + 40, qb[3] + bb[3] - bb[1] + 40])
      v.freshPaint(); query.draw()
      px1, py1, px2, py2 = query.panes()["contains"]
      x, y = (px1 + px2 - bb[2] + bb[0]) / 2, (py1 + py2 - bb[3] + bb[1]) / 2
    brother.moveTo(x, y, adjustPos=False)
    with CompositeCommandMgr(v.context):
      v.context.move(brother, x, y, _oldPos=list(bb), _drag=True)
      v._updateContainment(old)
    self.pump()
    self.assertNotEqual(query.containmentOf(brother.modelObject), [])
    return query, brother

  def test0740nestedWindows(self):
    # collapsing (or erasing) a window with a window in it hides (erases) the inner window's contents too
    v = self.view
    query, brother = self.nested()
    inner = [vo for vo in brother.windowContents() if vo._isConnected()]
    self.assertTrue(inner)
    self.assertFalse(any(vo.isHidden() for vo in inner))
    v.context.collapse(query, True)
    self.pump()
    self.assertTrue(brother.isHidden())
    self.assertEqual([vo.modelObject.name for vo in inner if not vo.isHidden()], [])
    v.context.collapse(query, False)
    self.pump()
    self.assertEqual([vo.modelObject.name for vo in inner if vo.isHidden()], [])
    v.context.visibility("queries", "erase")
    self.pump()
    self.assertEqual([vo.modelObject.name for vo in [query, brother, *inner] if vo._isConnected()], [])
    v.context.undo()
    self.pump()
    self.assertTrue(all(vo._isConnected() for vo in [query, brother, *inner]))

  def test0750relationIntoNestedWindow(self):
    # a relation from something in a window to something in a window inside it belongs in the outer window
    from sn.model.model import Node
    v, m = self.view, self.model
    query, brother = self.nested()
    homes = v.containmentHomes()
    b = next(vo for vo, (w, _) in homes.items() if w is brother and not isinstance(vo.modelObject, Relation))
    person = next(o for o in m.values() if o is not None and o.name == "person" and o.isType())
    likes = next(o for o in m.values() if o is not None and o.name == "likes" and o.isType())
    a = Node(m, [person], individual=True, name="?asker")
    Relation(m, [m.CONTAINS], query.modelObject, a, individual=True)
    rel = Relation(m, [likes], a, b.modelObject, individual=True)
    self.pump()
    v.showAllModel()
    self.pump()
    va, vr = v.findViewObjectForGraphObject(a), v.findViewObjectForGraphObject(rel)
    pane = query.panes()["contains"]
    va.moveTo(pane[0] + 10, pane[1] + 10, adjustPos=False)
    self.pump()
    self.assertEqual(v.containmentHomes([vr]).get(vr), (query, "contains"))
    v.bumpIntruders()
    self.assertIsNotNone(query.paneAt(vr.centerPt()))

  def test0760collapseHidesUsedVariables(self):
    # collapsing a rule hides the variables its patterns use, not just those it contains (eg: the base rules');
    # dragging a variable the rule's patterns use out of it doesn't take it out of the rule
    from sn.model.model import Node
    v, m = self.view, self.model
    rule = v.context.new_node("rule", name="symmetric likes", individual=True)
    self.pump()
    person = next(o for o in m.values() if o is not None and o.name == "person" and o.isType())
    likes = next(o for o in m.values() if o is not None and o.name == "likes" and o.isType())
    p, q = (Node(m, [person], individual=True, name=n) for n in ("?p", "?q"))
    Relation(m, [m.ANTECEDENT], rule, Relation(m, [likes], p, q, individual=True), individual=True)
    Relation(m, [m.CONSEQUENT], rule, Relation(m, [likes], q, p, individual=True), individual=True)
    self.pump()
    v.showAllModel()
    self.pump()
    vr = self.vo("symmetric likes")
    v.gatherIntoWindow(vr)
    self.pump()
    vp, vq = v.findViewObjectForGraphObject(p), v.findViewObjectForGraphObject(q)
    self.assertIsNotNone(vr.paneAt(vp.centerPt()))
    v.context.collapse(vr, True)
    self.pump()
    self.assertTrue(vp.isHidden() and vq.isHidden())
    v.context.collapse(vr, False)
    self.pump()
    self.assertFalse(vp.isHidden() or vq.isHidden())
    Relation(m, [m.CONTAINS], rule, p, individual=True) # (contained too: eg: by an older version)
    self.pump()
    rb, bb = vr.boundingBox(), vp.boundingBox()
    old = {vp: vp.centerPt()}
    vp.moveTo(rb[2] + 200, rb[3] + 200, adjustPos=False) # (as the drag moves it)
    with CompositeCommandMgr(v.context):
      v.context.move(vp, rb[2] + 200, rb[3] + 200, _oldPos=list(bb), _drag=True)
      v._updateContainment(old)
    self.pump()
    self.assertNotEqual(vr.containmentOf(p), [])
    self.assertIsNotNone(vr.paneAt(vp.centerPt())) # (put back: see homeStrays())

  def test0770ruleConcludesAType(self):
    # with "types" hidden, a rule that concludes ?x isa person still shows its isa link -- and person
    from sn.model.model import Node
    v, m = self.view, self.model
    rule = v.context.new_node("rule", name="persons", individual=True)
    self.pump()
    person = next(o for o in m.values() if o is not None and o.name == "person" and o.isType())
    x = Node(m, [person], individual=True, name="?someone")
    isa = next(o for o in m.values() if isinstance(o, IsaIndividual) and o.src is x)
    Relation(m, [m.CONSEQUENT], rule, isa, individual=True)
    self.pump()
    v.showAllModel()
    self.pump()
    v.gatherIntoWindow(self.vo("persons"))
    self.pump()
    v.context.visibility("types", "hide")
    self.pump(0.4)
    self.assertFalse(v.findViewObjectForGraphObject(isa).isHidden())
    self.assertFalse(self.vo("person").isHidden())

  def test0730layoutsMoveWindowsAside(self):
    'What a layout arranges onto a context window moves the window aside, with its contents: nothing ends up in a window it doesn\'t belong in.'
    from sn.view.graphics.treeLayout import TreeLayout
    v = self.view
    rule = self.vo("uncle rule")
    layout = TreeLayout(v, relation="isa", direction="down", others="rows")
    targets = layout.targets()
    person = self.vo("person")
    x, y = targets.get(person, person.boundingBox()[:2])
    rb = rule.boundingBox()
    v.context.move(rule, x - 20, y - 20, _oldPos=list(rb)) # (where the tree will be)
    self.pump()
    inRule = {vo: pane for vo, (w, pane) in v.containmentHomes().items() if w is rule and not (hasattr(vo, "floating") and vo.floating())}
    self.assertTrue(inRule)
    layout.arrange(animate=False)
    self.pump()
    self.assertEqual(self.intruders(), [])
    self.assertNotEqual(rule.boundingBox()[:2], [x - 20, y - 20])
    for vo, pane in inRule.items():
      self.assertIsNotNone(rule.paneAt(vo.centerPt()), vo.modelObject.name)

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

  def test0855findFarApart(self):
    # Find with matches too far apart to fit in the window: it shows the one nearest the middle, and goes
    # through them one by one, round again after the last
    v = self.view
    c = v.canvas
    for name, x in (("zz-one", -4000), ("zz-two", 4000)):
      v.context.new_node("person", name=name, individual=True)
      self.pump()
      self.vo(name).moveTo(x, 2000, adjustPos=False)
    v.resetScrollRegion()
    found, _ = v.search("zz-")
    self.assertEqual(len(found), 2)
    self.pump()
    def inMiddle(vo) -> bool:
      x, y = v.viewToWindow(*vo.centerPt())
      mx, my = c.canvasx(c.winfo_width() / 2), c.canvasy(c.winfo_height() / 2)
      return abs(x - mx) <= c.winfo_width() / 2 + 2 and abs(y - my) <= c.winfo_height() / 2 + 2
    self.assertTrue(any(inMiddle(vo) for vo in found))
    seen = []
    for _ in range(3):
      k, n = v.showMatch(1)
      self.assertEqual(n, 2)
      vo = v._liveMatches()[k - 1]
      self.assertTrue(inMiddle(vo), vo.name)
      seen.append(vo.name)
    self.assertEqual(seen[0], seen[2])
    self.assertNotEqual(seen[0], seen[1])
    self.assertEqual(v.showMatch(-1)[0], [vo.name for vo in v._liveMatches()].index(seen[1]) + 1)

  def test0860isaChoices(self):
    # making an isa link (see SNView.makeRelationFrom()): only a type can be chosen as the parent -- not
    # one it has already, nor one that'd make an isa cycle; and a cycle is said, not a traceback
    v, m = self.view, self.model
    v.context.new_node("person", name="employee", type=True)
    self.pump()
    alice, bob, person, employee = (self.vo(n) for n in ("alice", "bob", "person", "employee"))
    def choices(origin):
      v.makeRelationFrom(origin, m.ISA)
      assert v._elasticLineChoiceData is not None
      choose = v._elasticLineChoiceData.filter
      v.cancelElasticLine()
      return choose
    choose = choices(alice)
    self.assertFalse(choose(bob))      # (an individual)
    self.assertFalse(choose(person))   # (already)
    self.assertTrue(choose(employee))
    self.assertFalse(choices(person)(employee)) # (a cycle)
    n = len(m)
    with self.assertLogs(level="ERROR") as logs:
      v.makeRelation(person, employee, m.ISA)
    self.assertNotIn("Traceback", "\n".join(logs.output))
    self.assertEqual(len(m), n)
    with self.assertRaises(ValueError): # (a second isa link to the same parent)
      v.context.new_relation("isa", source=alice.modelObject, destination=person.modelObject)

  def test0865reEndRubberBand(self):
    # re-ending a relation: while choosing, the half being re-ended isn't drawn (the rubber band, thin and dashed,
    # stands in for it); cancelled, it's back
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    rel = next(o for o in v._shownObjects() if isinstance(o, VRelation) and not isinstance(o.modelObject, IsaIndividual)
               and o.src is not None and o.dst is not None and o.connectInfo is not None)
    c = v.canvas
    for end, half in (("dst", rel.connectInfo.destIDs()), ("src", rel.connectInfo.sourceIDs())):
      with self.subTest(end=end):
        self.assertTrue(half)
        states = {i: c.itemcget(i, "state") for i in half}
        rel.chooseNewEndpoint(end)
        data = v._elasticLineChoiceData
        self.assertIsNotNone(data)
        self.assertEqual({c.itemcget(i, "state") for i in half}, {"hidden"})
        self.assertNotEqual(c.itemcget(data.lineID, "dash"), "")
        self.assertLessEqual(float(c.itemcget(data.lineID, "width")), 2)
        v.cancelElasticLine()
        self.assertIsNone(v._elasticLineChoiceData)
        self.assertEqual({i: c.itemcget(i, "state") for i in half}, states)

  def test0866undoRefused(self):
    # an undo that fails (eg: what it would change can't be) says why, and stays where it was: undoing again tries
    # it again, not the command before it
    from util.command import Command
    v = self.view
    class Refusing(Command):
      def __init__(self):
        super().__init__("refusing")
        self.refuse = True
      def do(self):
        super().do()
      def undo(self):
        super().undo()
        if self.refuse:
          raise PermissionError("not now")
    v.context.new_node("person", name="eve", individual=True)
    self.pump()
    c = Refusing()
    v.context.doList.do(c)
    with self.assertLogs(level="ERROR") as logs:
      v.context.undo()
    self.assertIn('Can\'t undo "refusing": not now', "\n".join(logs.output))
    self.assertIn("eve", self.shown())
    c.refuse = False
    v.context.undo() # (it, this time)
    v.context.undo() # (eve)
    self.pump()
    self.assertNotIn("eve", self.shown())

  def test0870madeWhileZoomed(self):
    # a new object's box is drawn where it is, at the view's zoom -- its shadow too (a type's)
    v = self.view
    v.zoom(2.0)
    self.pump()
    for name, kw in (("eve", {"individual": True}), ("employee", {"type": True})):
      v.context.new_node("person", name=name, **kw)
      self.pump()
      vo = self.vo(name)
      expected = [float(c) for c in v.viewToWindow(vo._shape.points())]
      self.assertEqual([round(c, 3) for c in v.canvas.coords(vo._shape.id)], [round(c, 3) for c in expected], name)
    shadow = self.vo("employee").decorators.get("shadow")
    if shadow is not None and shadow.id is not None:
      sx = v.canvas.coords(shadow.id)[0::2]
      bx = v.canvas.coords(self.vo("employee")._shape.id)[0::2]
      self.assertLess(abs(min(sx) - min(bx)), 20) # (beside the box, not at half its coordinates)

  def test0880zoomRepaints(self):
    # what's a fixed size on the screen stays so after a zoom: eg, the selection handles
    v = self.view
    alice = self.vo("alice")
    v.selected.clear()
    alice.selected(True)
    self.pump()
    handle = alice.decorators["selected"]
    size = lambda: (lambda c: round(c[2] - c[0]))(v.canvas.coords(next(iter(handle.ids.values()))))
    before = size()
    v.zoom(2.5)
    self.pump()
    self.assertEqual(size(), before)
    marker = next((m for m in alice.decorators["markers"].markers if m.id is not None), None)
    if marker is not None: # (its letter in the view's font, at its zoom: not Tk's fixed font)
      self.assertNotIn("TkSmallCaptionFont", str(v.canvas.itemcget(marker.id, "font")))

  def test0890hideZoomShow(self):
    # objects hidden while the view zooms are inside the scroll region when they're shown again
    v = self.view
    person = self.vo("person")
    person.moveTo(3000, 2500, adjustPos=False)
    v.resetScrollRegion()
    self.pump()
    v.context.visibility("types", "hide")
    self.pump()
    v.zoom(1.25)
    self.pump()
    v.context.visibility("types", "show")
    self.pump()
    x1, y1, x2, y2 = (float(c) for c in str(v.canvas.cget("scrollregion")).split())
    bx1, by1, bx2, by2 = v.canvas.bbox(person._shape.id)
    self.assertTrue(x1 <= bx1 and y1 <= by1 and bx2 <= x2 and by2 <= y2, ((x1, y1, x2, y2), (bx1, by1, bx2, by2)))

  def test0895changedWhileErased(self):
    # an object changed while it's erased from the view comes back as it is now
    v, m = self.view, self.model
    alice = self.vo("alice")
    v.doErase([alice])
    self.pump()
    v.context.set_attribute(alice.modelObject, "name", "alicia")
    v.context.set_attribute(m["person"], "vis/fillColor", "red")
    self.pump()
    v.context.undo() # (the colour)
    v.context.undo() # (the name)
    v.context.undo() # (the erase)
    self.pump()
    self.assertIn("alice", v.canvas.itemcget(alice.decorators["text"].id, "text"))
    v.doErase([alice])
    self.pump()
    m["person"]["vis/fillColor"] = "green" # (inherited: changed while it's erased -- not a command, so undo puts back the erase)
    self.pump()
    v.context.undo() # (the erase)
    self.pump()
    self.assertEqual(alice.cache["vis/fillColor"], "green")
    self.assertEqual(v.canvas.itemcget(alice._shape.id, "fill"), "green")

  def test0898undoEraseChecks(self):
    # undoing an erase doesn't put back an object the view shows already (the model's undo brought it
    # back), nor one that's gone from the model since
    v, m = self.view, self.model
    alice = self.vo("alice")
    mo = alice.modelObject
    v.doErase([alice])
    self.pump()
    v.context.remove(mo)
    self.pump()
    v.context.undo() # (the remove: the view shows it again, with a new view object)
    self.pump()
    v.context.undo() # (the erase)
    self.pump()
    self.assertEqual(len([o for o in v.viewObjectsFor(mo) if o._isConnected()]), 1)
    bob = self.vo("bob")
    v.doErase([bob])
    self.pump()
    bob.modelObject._disconnect() # (gone from the model -- not by a command of this view's)
    self.pump()
    v.context.undo() # (the erase)
    self.pump()
    self.assertFalse(bob._isConnected())
    self.assertEqual(v.validate(), 0)

  def test0899drops(self):
    # a dropped object stays where it's dropped if it's on nothing (not 15 units clear of everything); one
    # dropped on something is nudged off the shortest way (left too); what's dropped together keeps its shape
    v = self.view
    a, b = self.vo("alice"), self.vo("bob")
    b.moveTo(5000, 5000, adjustPos=False)
    w = a.boundingBox()[2] - a.boundingBox()[0]
    v.context.move(a, 5000 - w - 6, 5000, _drag=True)
    self.assertEqual(a.boundingBox()[:2], [5000 - w - 6, 5000])
    v.context.move(a, 5000 - w + 10, 5000, _drag=True) # (10 into b's left edge)
    x, y = a.boundingBox()[:2]
    self.assertLess(x, 5000 - w)
    self.assertEqual(y, 5000)
    a.moveTo(5000 - w - 6, 5000, adjustPos=False)
    with CompositeCommandMgr(v.context):
      for n, dx in ((a, -w - 6), (b, 0)):
        v.context.move(n, 7000 + dx, 7000, _drag=True, _group=[a, b])
    self.assertEqual(a.boundingBox()[:2], [7000 - w - 6, 7000])
    self.assertEqual(b.boundingBox()[:2], [7000, 7000])

  def test0900undoHideKeepsShownAnyway(self):
    # an object shown anyway in a hidden category: hidden again when that's undone; shown again when hiding
    # the category again is undone
    v = self.view
    person = self.vo("person")
    v.context.visibility("types", "hide")
    self.pump()
    self.assertTrue(person._hidden)
    v.context.represent([person.modelObject]) # (asked for: shown anyway)
    self.pump()
    self.assertFalse(person._hidden)
    v.context.undo()
    self.pump()
    self.assertTrue(person._hidden)
    v.context.redo()
    self.pump()
    self.assertFalse(person._hidden)
    v.context.visibility("types", "show")
    v.context.visibility("types", "hide") # (hides it too)
    self.pump()
    self.assertTrue(person._hidden)
    v.context.undo() # (the second hide)
    v.context.undo() # (the show)
    self.pump()
    self.assertEqual(v.hides.get("types"), "hide")
    self.assertFalse(person._hidden)
    v.context.redo()
    v.context.redo()
    self.pump()
    self.assertTrue(person._hidden)

  def test0910showHiddenOfTypes(self):
    # "show" > "relations..." and "nodes...": those of the types chosen that are hidden by their category are
    # shown (not "they're all shown already"); undone
    v = self.view
    rel = next(o for o in v.values() if o is not None and o._isConnected() and isinstance(o.modelObject, Relation)
               and not isinstance(o.modelObject, IsaIndividual) and o.modelObject.isIndividual())
    typeName = next(p for p in rel.modelObject.getParents() if p is not None).name
    alice = self.vo("alice")
    class Dialog: # (chooses the type, instead of asking)
      def __init__(self, _parent, _title, types, _checked, note="", options=()):
        self.types, self.options = types, {label: on for label, on in options}
      def show(self):
        return {id(t) for t in self.types if t.name in (typeName, "person")}
    for category, vo, show in ((v.relationCategory(typeName), rel, v.showRelationsOfTypes),
                               ("individuals", alice, v.showNodesOfTypes)):
      v.context.visibility(category, "hide")
      self.pump()
      self.assertTrue(vo._hidden)
      with mock.patch("sn.view.graphics.visibilityDialog.TypesDialog", Dialog), \
           mock.patch("tkinter.messagebox.showinfo") as info:
        show()
      self.pump()
      info.assert_not_called()
      self.assertFalse(vo._hidden, category)
      v.context.undo()
      self.pump()
      self.assertTrue(vo._hidden, category)
      v.context.undo() # (the hide)
      self.pump()

  def test0920arrangeDuringTween(self):
    # arranging again while an arrangement is still moving things smoothly: undoing it puts them back where the
    # first one put them (not part way there)
    from sn.view.graphics.treeLayout import TreeLayout
    from sn.view.graphics.balloonLayout import BalloonLayout
    v = self.view
    defaults = lambda cls: {p.name: p.default for p in cls.PARAMETERS}
    first = TreeLayout(v, **defaults(TreeLayout)).arrange()
    self.assertIsNotNone(first)
    self.pump(0.06) # (part way)
    BalloonLayout(v, **defaults(BalloonLayout)).arrange()
    self.pump(0.5)
    v.context.undo()
    self.pump()
    for vo, _, (x, y), _ in first.moves:
      if vo._isConnected():
        self.assertEqual([round(c) for c in vo.boundingBox()[:2]], [round(x), round(y)], vo.name)

  def test0930undoLabelDrag(self):
    # dropping a dragged relation label pins it there; undoing that floats it again (it follows its ends)
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    rel = next(o for o in v._shownObjects() if isinstance(o, VRelation) and o.floating()
               and not isinstance(o.modelObject, IsaIndividual) and o.src is not None and o.dst is not None)
    def drag(vo, dx, dy):
      x, y = v.viewToWindow(*vo.centerPt())
      x, y = x - v.canvas.canvasx(0), y - v.canvas.canvasy(0)
      vo.onButton_1(self.event(x, y))
      for i in range(1, 11):
        vo.onB1_Motion(self.event(x + dx * i / 10, y + dy * i / 10))
      vo.onB1_ButtonRelease(self.event(x + dx, y + dy))
      self.pump()
    drag(rel, 120, 90)
    self.assertFalse(rel.floating())
    v.context.undo()
    self.pump()
    self.assertTrue(rel.floating())
    before = rel.centerPt()
    rel.src.moveTo(rel.src.boundingBox()[0] + 200, rel.src.boundingBox()[1], adjustPos=False)
    self.pump()
    self.assertNotEqual(rel.centerPt(), before) # (it followed its end)
    v.context.redo()
    self.pump()
    self.assertFalse(rel.floating())

  def test0894longWindowTitle(self):
    # a window's title stays in its banner, clear of its kind ("rule"): cut short, with an ellipsis
    v, m = self.view, self.model
    r = v.context.new_node("rule", name="a rule with a name far too long for its window", individual=True)
    self.pump()
    vr = self.vo(r.name)
    x1, y1, _, y2 = vr.boundingBox()
    vr.boundingBox([x1, y1, x1 + 180, y2])
    v.freshPaint(); vr.draw(); self.pump()
    frame = vr.decorators["frame"]
    c = v.canvas
    title, kind, banner = (c.bbox(frame.ids[k]) for k in ("title", "kind", "banner"))
    self.assertTrue(c.itemcget(frame.ids["title"], "text").endswith("\u2026"))
    self.assertLessEqual(title[2], kind[0])
    self.assertLessEqual(kind[2], banner[2])

  def test0896becomesAWindow(self):
    # a node made a rule is drawn as a window; made a plain node again, it has its text back
    v, m = self.view, self.model
    x = v.context.new_node("node", name="x", individual=True)
    self.pump()
    vx = self.vo("x")
    self.assertIn("text", vx.decorators)
    v.context.new_relation("isa", source=x, destination=m.RULE)
    self.pump()
    self.assertIn("frame", vx.decorators)
    self.assertNotIn("text", vx.decorators)
    v.context.undo()
    self.pump()
    self.assertIn("text", vx.decorators)
    self.assertNotIn("frame", vx.decorators)
    x1, y1, x2, y2 = vx.boundingBox()
    self.assertLess(x2 - x1, vx.WINDOW_MIN[0]) # (as big as its text again)

  def test0897collectionIsABox(self):
    '''
    A plain collection (an individual of the SN type collection) is drawn as a
    box with one pane, like a query: it carries what it contains when it's
    moved, and a rule can go in it. What it contains is a fact, not a pattern.
    '''
    from util.commandParser import CompositeCommandMgr
    v, m = self.view, self.model
    box = v.context.new_node("collection", name="box", individual=True)
    self.pump()
    vb = self.vo("box")
    self.assertTrue(vb.isContextWindow())
    self.assertIn("frame", vb.decorators)
    self.assertEqual(list(vb.panes()), ["contains"])
    alice = self.vo("alice")
    v.context.new_relation("contains", individual=True, source=box, destination=alice.modelObject)
    self.pump()
    v.gatherIntoWindow(vb)
    self.pump()
    self.assertIsNotNone(vb.paneAt(alice.centerPt()))
    self.assertIn(alice, vb.carriedContents())
    (ax, ay), bb = alice.centerPt(), vb.boundingBox()
    v.context.move(vb, bb[0] + 300, bb[1] + 40, _oldPos=list(bb))
    self.pump()
    nx, ny = alice.centerPt()
    self.assertAlmostEqual(nx - ax, 300, delta=1); self.assertAlmostEqual(ny - ay, 40, delta=1)
    self.assertIsNotNone(vb.paneAt(alice.centerPt()))
    # a rule dropped in it goes in it (it's a one-pane box)
    rule = self.vo("uncle rule")
    rb = vb.boundingBox()
    big = rule.boundingBox()
    vb.boundingBox([rb[0], rb[1], rb[0] + (big[2] - big[0]) + 200, rb[1] + (big[3] - big[1]) + 200])
    v.freshPaint(); vb.draw()
    old = {rule: rule.centerPt()}
    px1, py1, px2, py2 = vb.panes()["contains"]
    x, y = px2 - (big[2] - big[0]) - 10, py2 - (big[3] - big[1]) - 10
    rule.moveTo(x, y, adjustPos=False)
    with CompositeCommandMgr(v.context):
      v.context.move(rule, x, y, _oldPos=list(big), _drag=True)
      v._updateContainment(old)
    self.pump()
    self.assertNotEqual(vb.containmentOf(rule.modelObject), [])
    self.assertTrue(box.isMember(rule.modelObject) and box.isMember(alice.modelObject))

  def dropInto(self, vo, w, pane):
    'Drag *vo* into context window *w*\'s *pane* (one undo), as a drop there does.'
    from util.commandParser import CompositeCommandMgr
    v = self.view
    x1, y1, x2, y2 = w.panes()[pane]
    bb = list(vo.boundingBox())
    old = {vo: vo.centerPt()}
    x, y = (x1 + x2) / 2 - (bb[2] - bb[0]) / 2, y2 - (bb[3] - bb[1]) - 8
    vo.moveTo(x, y, adjustPos=False)
    with CompositeCommandMgr(v.context):
      v.context.move(vo, x, y, _oldPos=bb, _drag=True)
      v._updateContainment(old)
    self.pump()

  def test0898partsArePanes(self):
    '''
    A rule's parts (plain contexts it holds by antecedent and consequent) are
    its panes: not drawn themselves. Something dropped in a pane goes in
    that part -- made then, for a rule that has none yet (and taken away
    again by an undo). A second antecedent is a pane of its own.
    '''
    v, m = self.view, self.model
    uncle = self.vo("uncle rule")
    rule = uncle.modelObject
    self.assertEqual([p.name for p in rule.parts()], ["antecedent", "consequent"]) # (the example, converted as it was read)
    self.assertEqual(list(uncle.panes()), ["antecedent", "consequent"])
    for part in rule.parts():
      pvo = v.findViewObjectForGraphObject(part)
      self.assertTrue(pvo is None or (pvo.isTiledPart() and pvo.isHidden()), part.name)
    self.assertNotIn("antecedent", {w.modelObject.name for w in v.contextWindows()})
    x = next(o for o in rule.parts(m.ANTECEDENT)[0].getMembers() if o.name == "?x")
    self.assertEqual(uncle.containmentOf(x), [next(r for r in x._incoming if r.localSrc is rule.parts(m.ANTECEDENT)[0])])
    # a new rule: its panes, before it has parts; a drop makes the part
    new = v.context.new_node("rule", name="new rule", individual=True)
    self.pump()
    nw = self.vo("new rule")
    big = list(nw.boundingBox())
    nw.boundingBox([big[0], big[1], big[0] + 400, big[1] + 260]); v.freshPaint(); nw.draw()
    self.assertEqual([(n, p) for n, _, p in nw.paneSpecs()], [("antecedent", None), ("consequent", None)])
    alice = self.vo("alice")
    self.dropInto(alice, nw, "consequent")
    [cons] = new.parts(m.CONSEQUENT)
    self.assertTrue(cons.isMember(alice.modelObject))
    self.assertEqual(nw.paneOfRelation(nw.containmentOf(alice.modelObject)[0]), "consequent")
    self.dropInto(alice, nw, "antecedent")                       # (switching panes: out of one part, into the other)
    [ante] = new.parts(m.ANTECEDENT)
    self.assertTrue(ante.isMember(alice.modelObject))
    self.assertFalse(cons.isMember(alice.modelObject))
    v.context.undo()
    self.pump()
    self.assertEqual(new.parts(), [cons])                        # (the antecedent made by the drop: gone again)
    self.assertTrue(cons.isMember(alice.modelObject))
    # a second antecedent: a pane of its own, beside the first
    second = Node(m, [m.CONTEXT], individual=True, name="antecedent")
    Relation(m, [m.ANTECEDENT], rule, second, individual=True)
    self.pump()
    self.assertEqual(list(uncle.panes()), ["antecedent", "antecedent 2", "consequent"])
    bob = self.vo("bob")
    self.dropInto(bob, uncle, "antecedent 2")
    self.assertTrue(second.isMember(bob.modelObject))

  def test0899partsAsBoxes(self):
    '''
    "show parts as boxes": a rule's parts drawn each as a box of its own, in
    the rule's box where its pane was, carrying what's in it; and back.
    '''
    v, m = self.view, self.model
    uncle = self.vo("uncle rule")
    rule = uncle.modelObject
    v.gatherIntoWindow(uncle)
    self.pump()
    ante, cons = rule.parts()
    x = v.findViewObjectForGraphObject(next(o for o in ante.getMembers() if o.name == "?x"))
    uncle.setTiled(False)
    self.pump()
    self.assertFalse(rule.tilesParts())
    self.assertEqual(list(uncle.panes()), ["contains"])
    va = v.findViewObjectForGraphObject(ante)
    self.assertFalse(va.isHidden())
    self.assertIn(va, v.contextWindows())
    self.assertIs(v.containmentHomes()[va][0], uncle)            # (the part's box is in the rule's)
    self.assertIs(v.containmentHomes()[x][0], va)                # (and ?x in it)
    self.assertIsNotNone(va.paneAt(x.centerPt()))
    v.context.undo()
    self.pump()
    self.assertTrue(rule.tilesParts())
    self.assertTrue(va.isHidden())
    self.assertEqual(list(uncle.panes()), ["antecedent", "consequent"])

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
    v._askName = lambda mo, objectID=None: asked.append(mo.name)
    v.context.new_node("person", name="eve", individual=True)
    self.pump()
    self.assertEqual(asked, ["eve"])
    for i in range(20):
      Node(m, [m["person"]], individual=True, name=f"made{i}")
    self.pump()
    self.assertEqual(asked, ["eve"])
    self.assertIn("made0", self.shown()) # (shown, without asking)

  def test1110cancelledNewObject(self):
    'A new object left nameless (its editor cancelled) isn\'t made after all: undone, and not to be redone -- in a window\'s pane too. Named, it stays.'
    from sn.view.graphics import viewEditing
    v, m = self.view, self.model
    del v._askName # (the real one, with the editor stood in for)
    def make(into=None) -> None:
      menu = tk.Menu(v.canvas)
      v.addNewObjectMenus(menu, (100, 100), into=into)
      types = menu.nametowidget(menu.entrycget("new instance of Node", "menu"))
      types.nametowidget(types.entrycget(m.name, "menu")).invoke("person")
      self.pump()
    def gone() -> list:
      return [o for o in v.values() if o is not None and o.modelObject is not None and not o.modelObject._isConnected()]
    query = self.vo("who likes dave?")
    for into in (None, (query, "contains")):
      n, undo = len(list(m.values())), v.context.doList.getUndoDesc()
      with mock.patch.object(viewEditing, "applyEditAttrsBox"): # (cancelled: nothing changed)
        make(into)
      self.assertEqual(len(list(m.values())), n, into)
      self.assertEqual(v.context.doList.getUndoDesc(), undo)
      self.assertEqual(v.context.doList.getRedoDesc(), "<nothing to redo>")
      self.assertEqual(gone(), [])
    with mock.patch.object(viewEditing, "applyEditAttrsBox", side_effect=lambda parent, mo, **kw: mo.__setitem__("name", "zed")):
      make()
    self.assertIn("zed", self.shown())
    v.context.undo()
    self.pump()
    self.assertNotIn("zed", self.shown())
    v.context.redo() # (a named one comes back)
    self.pump()
    self.assertIn("zed", self.shown())

  def test1120selectionRedraw(self):
    'Selecting a relation thickens its line, deselecting thins it again; a node loses its handles. What\'s selected, erased and put back by undo: shown unselected -- and the context windows remembered are the ones there are.'
    from sn.view.graphics.vrelations import VRelation
    v = self.view
    r = next(o for o in v.values() if isinstance(o, VRelation) and not o._hidden and o.connectInfo is not None and o.connectInfo.sourceLineID is not None)
    def width() -> float:
      assert r.connectInfo is not None and r.connectInfo.sourceLineID is not None
      return float(v.canvas.itemcget(r.connectInfo.sourceLineID, "width"))
    before = width()
    r.selected(True)
    self.assertGreater(width(), before)
    r.selected(False)
    self.assertEqual(width(), before)
    n = self.vo("alice")
    n.selected(True)
    self.assertTrue(v.canvas.find_withtag("handle"))
    n.selected(False)
    self.assertFalse(v.canvas.find_withtag("handle"))
    query = self.vo("who likes dave?")
    v.contextWindows() # (remembered: kept up to date as they're erased and put back)
    for vo in (query, r, n):
      vo.selected(True, _multi=True)
    v.doErase([query, r, n])
    self.pump()
    self.assertNotIn(query, v.contextWindows())
    self.assertEqual(v.selected, set())
    v.context.undo()
    self.pump()
    self.assertIn(query, v.contextWindows())
    self.assertEqual(v.contextWindows(), [w for w in v.values() if w is not None and not isinstance(w, VRelation) and w._isConnected() and w.isContextWindow()
                                          and not w.isTiledPart()])
    self.assertFalse(r.selected())
    self.assertEqual(width(), before)

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
