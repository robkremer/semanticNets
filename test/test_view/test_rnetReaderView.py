'''
The rnetReader plugin's view and front end: *view.showNet()* puts each node
where CNet drew it, the size it was (scaled by *view.SCALE*), with its
relations between them, each label on its line -- a box (a node of an
enclosure type) as a window, the size it was, that carries what's in it
when it's moved; *view.convert()* makes the
model and view files, opens the view, and asks before replacing them; the
saved view opens again as it was. The dialog's model and view follow the
net file (in the folder they were last made in, if it's given), until
they're changed by hand.

The windows are never shown for long, and nothing is saved outside a
temporary folder (as in test_viewSmoke).

Created on Nov 11, 2026

@author: robkremer
'''
import builtins
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import tkinter as tk
import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model
from sn.plugins import importBundled

NET = "﻿" + "\r".join(l.replace("|", "\t") for l in (
  "|C|9|FFFFE1||40",
  "T|3",
  "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
  "0|0|Arial|11|0|20|000000|FFFFFF|000080|000080|0|0|0||Title",
  "3|0|Arial|9|1|8200|000000|FFFFFF|000000|B10000|0|0|0||frame",
  "A|2",
  "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
  "0|0|0|0|1|1|00A000|00A000|00A000|00A000|Excludes symmetric",
  "M|1", "693804|FFCD7D|Asserted",
  "N|5|0|-1",
  "0|81|10|20|19|19|A|",
  "0|0|200|20|19|19|B|",
  "0|0|100|150|19|19||",
  "1|0|10|200|120|14|A title|",
  "2|0|0|0|240|60|a box|", # (holding A and B)
  "L|3|0",
  "0|1|0",
  "2|0|1",
  "2|1|0",
  "G|1",
  "0 1 2|",
)) + "\r"

class TestNetView(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    from sn.view.graphics import progress
    from sn.view.graphics.guiApp import Application
    cls.rnet = importBundled("rnetReader", "rnet")
    cls.reader = importBundled("rnetReader", "reader")
    cls.netView = importBundled("rnetReader", "view")
    cls.saved = (sys.stdout, sys.stderr, builtins.input, sys.excepthook,
                 list(logging.getLogger().handlers), terminal._installedIORoutingRegistry,
                 Application.current, progress.listener)
    cls.prefsWereDirty = sn.snPrefs.isDirty()
    from sn.view.graphics import decorators
    decorators._fonts.clear() # (made for an application an earlier test made, and destroyed)
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
    decorators._fonts.clear()
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snRnet-")
    self.folder = Path(self.tmp.name).resolve()
    self.rnetPath = self.folder / "net.rnet"
    self.rnetPath.write_text(NET, encoding="utf-8")
    self.views = []

  def tearDown(self):
    for name in list(self.app.windows):
      self.app._closeWindow(name, quitIfLast=False, askToSave=False)
    for v in self.views:
      if not v._closed:
        v.detachFromModel()
        self.app.terminalRegistry.unregisterWindow(v.window)
      if v.window.winfo_exists():
        v.window.destroy()
    self.app.update()
    Model._initCache()
    self.tmp.cleanup()

  def shown(self, view) -> dict:
    from sn.view.graphics.vnodes import VNode
    return {str(vo.modelObject.name): vo for vo in view.values()
            if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()}

  def relations(self, view) -> list:
    from sn.view.graphics.vrelations import VRelation
    return [vo for vo in view.values() if isinstance(vo, VRelation) and vo._isConnected() and not vo.isHidden()]

  def test_showNet(self):
    'Each node where CNet drew it, its size, kept; the relations between them, each label on its line; no types.'
    from sn.view.graphics.sngView import SNGView
    built = self.reader.buildModel(self.rnet.parse(str(self.rnetPath)), str(self.folder / "net.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.netView.showNet(v, built)
    shown = self.shown(v)
    self.assertEqual(set(shown), {"A", "B", "", "A title", "a box"})
    s, m = self.netView.SCALE, self.netView.MARGIN
    for name, (x, y, w, h) in {"A": (10, 20, 19, 19), "": (100, 150, 19, 19), "A title": (10, 200, 120, 14),
                               "a box": (0, 0, 240, 60)}.items():
      box, cnet = shown[name].boundingBox(), [int(m + x * s), int(m + y * s), int(m + (x + w) * s), int(m + (y + h) * s)]
      self.assertEqual(box[:2], cnet[:2], name)
      self.assertTrue(all(c <= b <= c + 2 for b, c in zip(box[2:], cnet[2:])), f"{name}: {box} {cnet}") # (or a little bigger, if its text needs it)
      self.assertTrue(shown[name].userSized)
    rels = self.relations(v)
    self.assertEqual(sorted((r.src.modelObject.name, r.dst.modelObject.name) for r in rels), [("", "A"), ("", "B"), ("A", "B")])
    for r in rels:
      (ax, ay), (bx, by), (cx, cy) = r.src.centerPt(), r.dst.centerPt(), r.centerPt()
      self.assertLess(abs((bx - ax) * (cy - ay) - (by - ay) * (cx - ax)) / max(1.0, ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5), 3.0) # (on the line)
    # the box: a window holding A and B (its "contains" arcs aren't drawn), that carries them when it's moved
    box = shown["a box"]
    self.assertTrue(box.isContextWindow())
    self.assertEqual(sorted(str(vo.modelObject.name) for vo in box.carriedContents()), ["A", "B", "Includes"]) # (A -> B too: its ends are in it)
    self.assertTrue(all(box.paneAt(shown[n].centerPt()) is not None for n in ("A", "B")))
    (ax, ay), bb = shown["A"].centerPt(), box.boundingBox()
    v.context.move(box, bb[0] + 50, bb[1] + 400, _oldPos=list(bb))
    self.app.update()
    nx, ny = shown["A"].centerPt()
    self.assertAlmostEqual(nx, ax + 50, delta=1); self.assertAlmostEqual(ny, ay + 400, delta=1)
    self.assertTrue(all(box.paneAt(shown[n].centerPt()) is not None for n in ("A", "B")))

  def test_reasoned(self):
    '''
    After reasoning, the kernel's inferences are drawn -- but not what's
    implied by what's drawn ("vis/hideImplied"): no loops (from cycles, or an
    inconsistent node), each symmetric one once (not again the other way
    round, nor beside an asserted one), and no includes beside an equivalent.
    '''
    from sn.view.graphics.sngView import SNGView
    from test_sn.test_knetRules import KERNEL
    path = self.folder / "kernel.rnet"
    path.write_text(KERNEL, encoding="utf-8")
    built = self.reader.buildModel(self.rnet.parse(str(path)), str(self.folder / "kernel.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.netView.showNet(v, built)
    v.reason("clingo")
    self.app.update()
    inferred = [r for r in self.relations(v) if r.isInferred()]
    self.assertTrue(inferred)
    self.assertFalse([r for r in inferred if r.src is r.dst])
    between = lambda a, b: sorted(str(r.modelObject.getParents()[0].name) for r in self.relations(v)
                                  if {str(r.src.modelObject.name), str(r.dst.modelObject.name)} == {a, b})
    self.assertEqual(between("dog", "plant"), ["excludes"])           # (once, not both ways)
    self.assertEqual(between("animal", "plant"), ["Excludes"])        # (the asserted one: not again, inferred, the other way)
    self.assertEqual(between("on", "lit"), ["equivalent"])            # (not includes, both ways, beside it)
    self.assertEqual(between("on", "off"), ["Negates symmetric"])     # (nor its excludes and coexcludes)
    self.assertEqual(between("three", "odd"), ["includes"])

  def test_marks(self):
    '''
    A node's truth marks are bars (see the plugin's *hooks.markBars()* and
    *decorators.SideBars*): asserted true, a brown one beside it; after
    reasoning, the marks the reasoner concluded too (eg: black beside, for
    true by inclusion; both bars, for both) -- and they go when the
    assertion's taken back and it's reasoned again.
    '''
    from sn.view.graphics.sngView import SNGView
    from sn.hooks import HookContext
    from test_sn.test_knetRules import MARKS
    hooks = importBundled("rnetReader", "hooks")
    path = self.folder / "marks.rnet"
    path.write_text(MARKS, encoding="utf-8")
    built = self.reader.buildModel(self.rnet.parse(str(path)), str(self.folder / "marks.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.netView.showNet(v, built)
    self.app.update()
    shown = self.shown(v)
    def bars(name:str) -> list[tuple[str, str]]: # (each bar's colour, and where: right of the node, or above it)
      vo = shown[name]
      deco = vo.decorators.get("sideBars")
      x1, y1, x2, y2 = v.viewToWindow(vo.boundingBox())
      ret = []
      for i in deco.ids if deco is not None else []:
        bx1, by1, bx2, by2 = v.canvas.coords(i)
        ret.append(("right" if bx1 >= x2 else "top" if by2 <= y1 else "?", v.canvas.itemcget(i, "fill")))
      return sorted(ret)
    self.assertEqual(bars("a0"), [("right", "#693804")])
    self.assertEqual(bars("a2"), [("right", "#693804"), ("top", "#693804")])
    self.assertEqual(bars("c0"), [])
    v.reason("clingo")
    self.app.update()
    self.assertEqual(bars("c0"), [("right", "#000000")])                   # (true by inclusion)
    self.assertEqual(bars("f0"), [("top", "#00a000")] if shown["f0"].modelObject["markFalse"] == "excluded"
                     else [("top", "#a9a9a9")])                            # (false by exclusion, or by inclusion)
    self.assertEqual([c for _, c in bars("d2")], ["#0000ff", "#00a000"])  # (both)
    hooks.clearMarks(shown["a0"].modelObject, HookContext(view=v, selection=[shown["a0"]]))
    self.app.update()
    self.assertIsNone(shown["a0"].modelObject.getLocalAttr("markTrue"))
    self.assertEqual(bars("a0"), [])
    v.reason("clingo")
    self.app.update()
    self.assertEqual(bars("c0"), [])
    v.context.undo()
    self.app.update()
    self.assertEqual(bars("a0"), [("right", "#693804")])

  def test_convert(self):
    'The files are made, the view opened; made again, it asks first -- and does nothing if told not to.'
    model, view = str(self.folder / "out" / "net.snm"), str(self.folder / "out" / "net.snv")
    with mock.patch.object(self.netView.messagebox, "askokcancel", return_value=True) as ask, \
         mock.patch("tkinter.Toplevel.deiconify"): # (not shown)
      made = self.netView.convert(self.app, str(self.rnetPath), model, view)
      self.assertIsNotNone(made)
      built, v = made
      self.assertFalse(ask.called)
    self.assertTrue(os.path.isfile(model) and os.path.isfile(view))
    self.assertEqual(len(self.shown(v)), 5)
    self.assertEqual(len(built.boxes), 1)
    self.assertIn("1 groups", built.report()) # (not made)
    with mock.patch.object(self.netView.messagebox, "askokcancel", return_value=False) as ask:
      self.assertIsNone(self.netView.convert(self.app, str(self.rnetPath), model, view))
      self.assertTrue(ask.called)

  def test_reopened(self):
    'The saved view opens again with the nodes where they were, and the box\'s members.'
    model, view = str(self.folder / "net.snm"), str(self.folder / "net.snv")
    with mock.patch("tkinter.Toplevel.deiconify"): # (not shown)
      built, v = self.netView.convert(self.app, str(self.rnetPath), model, view)
    boxes = {name: vo.boundingBox() for name, vo in self.shown(v).items()}
    for name in list(self.app.windows):
      self.app._closeWindow(name, quitIfLast=False, askToSave=False)
    self.app.update()
    Model._initCache()
    with mock.patch("tkinter.Toplevel.deiconify"): # (not shown)
      window = self.app.openWindow(Path(view).as_uri())
    self.assertIsNotNone(window)
    v2 = window.view
    self.app.update()
    self.assertEqual({name: vo.boundingBox() for name, vo in self.shown(v2).items()}, boxes)
    self.assertEqual(len(self.relations(v2)), 3)
    m = v2.model
    box, = (o for o in m.values() if o is not None and o.model is m and o.isCollection())
    self.assertEqual(sorted(str(x.name) for x in box.getMembers()), ["A", "B"])
    self.assertTrue(self.shown(v2)["a box"].isContextWindow())

class TestDialog(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    cls.netView = importBundled("rnetReader", "view")
    try:
      cls.root = tk.Tk()
    except tk.TclError as ex:
      raise unittest.SkipTest(f"no display: {ex}")
    cls.root.withdraw()

  @classmethod
  def tearDownClass(cls):
    cls.root.destroy()

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    self.tmp.cleanup()

  def dialog(self, **kw):
    d = self.netView.ReaderDialog(self.root, **kw) # (any window will do: it's only its parent)
    d.withdraw()
    self.addCleanup(lambda: d.winfo_exists() and d.destroy())
    return d

  def test_follow(self):
    'The model and view follow the net file -- beside it, or in the output folder -- until changed by hand; emptied, they follow again.'
    d = self.dialog()
    self.assertTrue(d.goButton.instate(["disabled"]))
    net = str(self.folder / "patterns.rnet")
    d.vars["rnet"].set(net)
    self.assertEqual((d.vars["model"].get(), d.vars["view"].get()), self.netView.defaultPaths(net))
    self.assertEqual(d.vars["model"].get(), str(self.folder / "patterns.snm"))
    self.assertFalse(d.goButton.instate(["disabled"]))
    mine = str(self.folder / "mine" / "m.snm")
    d.vars["model"].set(mine)
    self.assertEqual(d.vars["view"].get(), str(self.folder / "mine" / "m.snv"))
    d.vars["rnet"].set(str(self.folder / "other.rnet"))
    self.assertEqual(d.vars["model"].get(), mine)
    d.vars["model"].set("")
    self.assertEqual(d.vars["model"].get(), str(self.folder / "other.snm"))
    out = str(self.folder / "made")
    d2 = self.dialog(rnetPath=net, outputFolder=out)
    self.assertEqual(d2.vars["model"].get(), os.path.join(out, "patterns.snm"))
    self.assertEqual(d2.vars["view"].get(), os.path.join(out, "patterns.snv"))

  def test_go(self):
    'Go makes them (convert(), stubbed here), says which, and closes.'
    went, closed = [], []
    net = str(self.folder / "patterns.rnet")
    d = self.dialog(rnetPath=net, onGo=lambda *files: went.append(files), onClose=lambda: closed.append(True))
    with mock.patch.object(self.netView, "convert", return_value=(object(), object())) as convert:
      d.go()
    self.assertEqual(convert.call_args.args[1:4], (net, str(self.folder / "patterns.snm"), str(self.folder / "patterns.snv")))
    self.assertEqual(went, [(net, str(self.folder / "patterns.snm"), str(self.folder / "patterns.snv"))])
    self.assertEqual(closed, [True])
    self.assertFalse(d.winfo_exists())

if __name__ == "__main__":
  unittest.main()
