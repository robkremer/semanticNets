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
import math
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

  def test_smoothLines(self):
    'The links are smooth curves: with its label off the line between its ends (eg: kept in a box), an exclusion\'s bar still crosses its line squarely.'
    from sn.view.graphics.sngView import SNGView
    built = self.reader.buildModel(self.rnet.parse(str(self.rnetPath)), str(self.folder / "net.snm"))
    self.assertEqual({t["vis/lineType"] for t in built.linkTypes.values()}, {self.reader.LINE_TYPE})
    self.assertEqual(self.reader.LINE_TYPE, "smooth")
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.netView.showNet(v, built)
    c = v.canvas
    exc = next(r for r in self.relations(v) if (r.src.modelObject.name, r.dst.modelObject.name) == ("", "A"))
    (ax, ay), (bx, by) = exc.src.centerPt(), exc.dst.centerPt()
    for off in (0, 60, -60): # (on the line between its ends, then off it to either side)
      n = ((ay - by), (bx - ax)); size = math.hypot(*n)
      exc.moveToCenterOn((ax + bx) / 2 + n[0] / size * off, (ay + by) / 2 + n[1] / size * off, adjustPos=False)
      exc.draw()
      self.app.update()
      info = exc.connectInfo
      line = c.coords(info.sourceLineID)
      self.assertEqual((len(line), c.itemcget(info.sourceLineID, "smooth")), (6, "true")) # (a curve: 3 points, smoothed)
      bar = [i for i in info.middleIDs if c.type(i) == "line"]
      self.assertEqual(len(bar), 1, "one bar, in the middle")
      x0, y0, x1, y1 = c.coords(bar[0])
      tx, ty = line[4] - line[2], line[5] - line[3] # (the curve's direction where it meets the bar: its last control segment)
      cos = abs((x1 - x0) * tx + (y1 - y0) * ty) / (math.hypot(x1 - x0, y1 - y0) * math.hypot(tx, ty))
      self.assertLess(cos, 0.02, f"the bar crosses the line squarely (offset {off})")
      centre = v.viewToWindow(*exc.centerPt())
      self.assertLess(math.dist(((x0 + x1) / 2, (y0 + y1) / 2), centre), 1.0) # (on the label, where the curve runs through)

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
    A node's truth marks are bars through it (see the plugin's
    *hooks.markBars()* and *decorators.SideBars*), as Gaines draws them:
    asserted true, a brown vertical one; asserted false, horizontal; after
    reasoning, the marks the reasoner concluded too (eg: black, for true by
    inclusion; both bars, for both) -- and they go when the assertion's taken
    back and it's reasoned again.
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
    def bars(name:str) -> list[tuple[str, str]]: # (each bar's colour, and where: through the node, vertical or horizontal)
      return sorted((where, color) for where, color, _ in self.bars(v, shown[name]))
    self.assertEqual(bars("a0"), [("vertical", "#693804")])
    self.assertEqual(bars("a2"), [("horizontal", "#693804"), ("vertical", "#693804")])
    self.assertEqual(bars("c0"), [])
    v.reason("clingo")
    self.app.update()
    self.assertEqual(bars("c0"), [("vertical", "#000000")])                # (true by inclusion)
    self.assertEqual(bars("f0"), [("horizontal", "#00a000")] if shown["f0"].modelObject["markFalse"] == "excluded"
                     else [("horizontal", "#a9a9a9")])                     # (false by exclusion, or by inclusion)
    self.assertEqual(bars("d2"), [("horizontal", "#00a000"), ("vertical", "#0000ff")])  # (both)
    hooks.clearMarks(shown["a0"].modelObject, HookContext(view=v, selection=[shown["a0"]]))
    self.app.update()
    self.assertIsNone(shown["a0"].modelObject.getLocalAttr("markTrue"))
    self.assertEqual(bars("a0"), [])
    v.reason("clingo")
    self.app.update()
    self.assertEqual(bars("c0"), [])
    v.context.undo()
    self.app.update()
    self.assertEqual(bars("a0"), [("vertical", "#693804")])

  def bars(self, view, vo) -> list[tuple[str, str, list[float]]]:
    '''
    :returns: *vo*'s bars (see *decorators.SideBars*), as drawn: where each
      is -- "vertical" or "horizontal" through its centre (or its title
      bar's, for a window), "outside" it, or "?" -- its colour, and its
      rectangle; each through it checked to be under its text, over its
      shape.
    '''
    c = view.canvas
    deco = vo.decorators.get("sideBars")
    x1, y1, x2, y2 = view.viewToWindow(vo.boundingBox())
    if vo.isContextWindow():
      y2 = view.viewToWindow([0, vo.boundingBox()[1] + vo.bannerHeight()])[1]
      label, under = vo.decorators["frame"].ids["title"], vo.decorators["frame"].ids["banner"]
    else:
      label, under = vo.decorators["text"].id, vo._shape.id
    order = c.find_all() # (bottom to top)
    ret = []
    for i in deco.ids if deco is not None else []:
      bx1, by1, bx2, by2 = c.coords(i)
      inside = x1 <= bx1 < bx2 <= x2 and y1 <= by1 < by2 <= y2
      if inside and bx2 - bx1 < (x2 - x1) / 4 and by2 - by1 > (y2 - y1) * 0.8:
        where = "vertical"
      elif inside and by2 - by1 < (y2 - y1) / 4 and bx2 - bx1 > (x2 - x1) * 0.8:
        where = "horizontal"
      else:
        where = "outside" if bx1 >= x2 or bx2 <= x1 or by1 >= y2 or by2 <= y1 else "?"
      if where in ("vertical", "horizontal"):
        self.assertLess(order.index(under), order.index(i), f"{vo.name}: a bar under its shape")
        self.assertLess(order.index(i), order.index(label), f"{vo.name}: a bar over its text")
      ret.append((where, c.itemcget(i, "fill"), [bx1, by1, bx2, by2]))
    return ret

  def test_barsThrough(self):
    '''
    A node's bars through its centre (see *decorators.SideBars*): from edge to
    edge, inside its outline, under its text, thinner than those at its
    sides; two on one, side by side, centred; a window's through its title
    bar; and a side's still outside it.
    '''
    from sn.view.graphics.sngView import SNGView
    from sn.view.graphics.decorators import SideBars
    built = self.reader.buildModel(self.rnet.parse(str(self.rnetPath)), str(self.folder / "net.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    v.context.visibility("system objects", "hide")
    self.netView.showNet(v, built)
    self.app.update()
    shown = self.shown(v)
    a, box = shown["A"], shown["a box"]
    a.modelObject["vis/sideBars"] = "vertical:red vertical:blue horizontal right:green"
    box.modelObject["vis/sideBars"] = "vertical:#00a000"
    self.app.update()
    a.draw(); box.draw()
    found = self.bars(v, a)
    self.assertEqual([(where, color) for where, color, _ in found],
                     [("outside", "green"), ("vertical", "red"), ("vertical", "blue"), ("horizontal", "black")])
    s, r1, r2, h = [x[2] for x in found]
    x1, y1, x2, y2 = v.viewToWindow(a.boundingBox())
    self.assertAlmostEqual((r1[0] + r2[2]) / 2, (x1 + x2) / 2, delta=0.5)   # (the two side by side, centred)
    self.assertLess(r1[2], r2[0])
    self.assertAlmostEqual((h[1] + h[3]) / 2, (y1 + y2) / 2, delta=0.5)
    self.assertLess(r1[2] - r1[0], s[2] - s[0])                              # (thinner than a side's)
    self.assertAlmostEqual(r1[2] - r1[0], SideBars.THROUGH_WIDTH * v._scale, delta=0.01)
    self.assertGreater(r1[1], y1); self.assertLess(r1[3], y2)                # (inside its outline)
    self.assertEqual([(where, color) for where, color, _ in self.bars(v, box)], [("vertical", "#00a000")])
    a.modelObject["vis/sideBars"] = "middle" # (not a side, nor through it: none, and a warning)
    self.app.update()
    a.draw()
    self.assertEqual(self.bars(v, a), [])

  def test_probes(self):
    '''
    A node's "Probes..." menu item shows its net's probes, probe sets and
    reconstruction in a window: consistent ones first, then the kind chosen
    -- and copies them.
    '''
    from sn.view.graphics.sngView import SNGView
    from sn.hooks import HookContext
    from test_sn.test_knetRules import PROBES
    hooks = importBundled("rnetReader", "hooks")
    path = self.folder / "probes.rnet"
    path.write_text(PROBES, encoding="utf-8")
    built = self.reader.buildModel(self.rnet.parse(str(path)), str(self.folder / "probes.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    self.netView.showNet(v, built)
    self.app.update()
    node = built.nodes[0]
    self.assertTrue(node[".menu/Probes..."].endswith(":showProbes"))
    d = hooks.showProbes(node, HookContext(view=v, selection=[]))
    self.addCleanup(lambda: d.top.winfo_exists() and d.top.destroy())
    self.assertEqual(d.top.title(), "Probes: probes")
    text = lambda: d.text.get("1.0", "end-1c")
    self.assertTrue(text().startswith("Consistent probes of probes: 96\n"), text())
    d.kind.set("admissible")
    d.refresh()
    self.assertTrue(text().startswith("Admissible probes of probes: 192\n"), text())
    d.copy()
    self.assertEqual(d.top.clipboard_get(), text())
    with mock.patch.object(importBundled("rnetReader", "probes"), "findProbes",
                           side_effect=__import__("sn.model.reasoner", fromlist=["TooManyProbes"]).TooManyProbes(4096)):
      d.refresh()
    self.assertTrue(text().startswith("There are more than 4096 probes."), text())

  FORMS = "﻿" + "\r".join(l.replace("|", "\t") for l in (
    "|C|9|FFFFFF||32", "T|1", "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
    "A|2", "1|0|0|0|1|0|000000|000000|000000|000000|Includes", "1|1|0|0|1|0|00A000|00A000|00A000|00A000|Excludes",
    "N|4|0|-1", "0|0|10|10|19|19|a|", "0|0|80|10|19|19|b|", "0|0|150|10|19|19|c|", "0|0|220|10|19|19|d|",
    "L|4|0", "0|1|0", "1|2|0", "0|2|0", "2|3|1", # (a includes b, b includes c, a includes c: redundant; c excludes d)
    "G|0")) + "\r"
  "A net for the Net menu's items: one of its links the others imply."

  def formsView(self):
    ''':returns: A view of *FORMS*'s net (withdrawn), and what the reader built.'''
    return self.netOf(self.FORMS, "forms")

  def netOf(self, text:str, name:str):
    ''':returns: A view of the net *text* (withdrawn), as the file *name*, and what the reader built.'''
    from sn.view.graphics.sngView import SNGView
    path = self.folder / f"{name}.rnet"
    path.write_text(text, encoding="utf-8")
    built = self.reader.buildModel(self.rnet.parse(str(path)), str(self.folder / f"{name}.snm"))
    v = SNGView(fixURL(built.model.url, ".snv", replaceExt=True, mode="w")[0], model=built.model)
    self.views.append(v)
    v.window.withdraw()
    self.netView.showNet(v, built)
    self.app.update()
    return v, built

  def test_forms(self):
    '''
    A node's Net menu: the minimal form takes out the link the others imply
    (a includes c), and the maximal form asserts it again, with the
    exclusions the others imply -- each one command, undone in one go -- and
    each says what it did.
    '''
    from sn.hooks import HookContext
    hooks = importBundled("rnetReader", "hooks")
    forms = importBundled("rnetReader", "forms")
    v, built = self.formsView()
    m, a = built.model, built.nodes[0]
    for item, fn in (("Minimal form", "minimalForm"), ("Maximal form", "maximalForm"), ("Saturate", "saturate"),
                     ("Check merge with...", "checkMerge")):
      self.assertTrue(a[f".menu/Net/{item}"].endswith(f":{fn}"), item)
    links = lambda: sorted(hooks._describe(r) for r in forms.netLinks(m))
    before = links()
    self.assertIn("a Includes c", before)
    context = HookContext(view=v, selection=[])
    with mock.patch("builtins.print") as said:
      gone = hooks.minimalForm(a, context)
    self.assertEqual([hooks._describe(r) for r in gone], ["a Includes c"])
    self.assertEqual(said.call_args_list[0].args[0], "Minimal form of forms: took out 1 link:")
    self.app.update()
    self.assertEqual(links(), sorted(set(before) - {"a Includes c"}))
    self.assertEqual(len(self.relations(v)), 3)
    v.context.undo()
    self.app.update()
    self.assertEqual(links(), before)
    v.context.redo()
    self.app.update()
    with mock.patch("builtins.print") as said:
      added = hooks.maximalForm(a, context)
    self.assertEqual(sorted(hooks._describe(r) for r in added), ["a excludes d", "a includes c", "b excludes d"])
    self.assertFalse(any(r.inferred for r in added))
    self.assertEqual(said.call_args_list[0].args[0], "Maximal form of forms: asserted 3 links:")
    v.context.undo()
    self.assertTrue(all(r.inferred for r in added))
    with mock.patch("builtins.print") as said:
      self.assertEqual(hooks.minimalForm(a, HookContext(view=v, selection=[])), [])
    self.assertEqual(said.call_args_list[0].args[0], "Minimal form of forms: took out 0 links.")

  def test_saturate(self):
    '''
    Saturate adds the net's admissible probes as nodes, each linked to the
    nodes true and false in it -- shown in the view, without asking their
    names -- as one command, undone in one go. Too many: said, and nothing added.
    '''
    from sn.hooks import HookContext
    from sn.model.model import Node
    hooks = importBundled("rnetReader", "hooks")
    v, built = self.formsView()
    m, a = built.model, built.nodes[0]
    count = len(m)
    with mock.patch("builtins.print") as said, \
         mock.patch("sn.view.graphics.viewEditing.applyEditAttrsBox", side_effect=AssertionError("asked a name")):
      added = hooks.saturate(a, HookContext(view=v, selection=[]))
      self.app.update()
    probes = [o for o in added if isinstance(o, Node)]
    self.assertEqual([p.name for p in probes], [f"probe {k}" for k in range(1, 6)]) # (none true; d; c; b and c; a, b and c)
    self.assertEqual(said.call_args_list[0].args[0], "Saturated forms: added 5 admissible probes: " +
                     ", ".join(f"probe {k}" for k in range(1, 6)))
    self.assertTrue(all(p.isa(importBundled("rnetReader", "forms").probeType(m)) for p in probes))
    self.assertEqual(len(added) - len(probes), 5 * 4) # (each linked to every node)
    self.assertEqual(sorted(self.shown(v)), ["a", "b", "c", "d"] + [f"probe {k}" for k in range(1, 6)]) # (not their SN type)
    self.assertEqual(len(self.relations(v)), 4 + 5 * 4) # (nor what each is an instance of)
    v.context.undo()
    self.app.update()
    self.assertEqual(len(m), count)
    self.assertEqual((sorted(self.shown(v)), len(self.relations(v))), (["a", "b", "c", "d"], 4))
    v.context.redo()
    self.app.update()
    self.assertEqual((len(self.shown(v)), len(self.relations(v))), (9, 24))
    v.context.undo()
    self.app.update()
    v.context.remove(built.nodes[1]) # (b, with its two links: put back, the view shows them as it did -- no SN types)
    self.app.update()
    self.assertEqual((sorted(self.shown(v)), len(self.relations(v))), (["a", "c", "d"], 2))
    v.context.undo()
    self.app.update()
    self.assertEqual((sorted(self.shown(v)), len(self.relations(v))), (["a", "b", "c", "d"], 4))
    with mock.patch.object(importBundled("rnetReader", "forms"), "SATURATION_LIMIT", 4), \
         self.assertLogs("snplugins.rnetReader.hooks", "ERROR") as logs:
      saturate = importBundled("rnetReader", "forms").saturate
      with mock.patch.object(importBundled("rnetReader", "forms"), "saturate",
                             side_effect=lambda model, context=None: saturate(model, context=context, limit=4)):
        self.assertEqual(hooks.saturate(a, HookContext(view=v, selection=[])), [])
    self.assertIn("There are more than 4 probes.", logs.output[0])
    self.assertEqual(len(m), count)

  def test_checkMerge(self):
    '''
    "Check merge with..." asks for another net -- a Rep Plus net file, here
    -- and shows what merging it would do, in a window: a net where c
    includes a, merged with this one (where a includes c, by way of b),
    makes the three equivalent: consistent, but not conservative. Asked for
    none: nothing.
    '''
    from sn.hooks import HookContext
    hooks = importBundled("rnetReader", "hooks")
    v, built = self.formsView()
    other = self.folder / "other.rnet"
    other.write_text("﻿" + "\r".join(l.replace("|", "\t") for l in (
      "|C|9|FFFFFF||32", "T|1", "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
      "A|1", "1|0|0|0|1|0|000000|000000|000000|000000|Includes",
      "N|3|0|-1", "0|0|10|10|19|19|c|", "0|0|80|10|19|19|a|", "0|0|150|10|19|19|e|",
      "L|2|0", "0|1|0", "2|0|0", # (c includes a, e includes c)
      "G|0")) + "\r", encoding="utf-8")
    context = HookContext(view=v, selection=[])
    with mock.patch.object(hooks, "askNet", return_value=""):
      self.assertIsNone(hooks.checkMerge(built.nodes[0], context))
    with mock.patch.object(hooks, "askNet", return_value=str(other)):
      w = hooks.checkMerge(built.nodes[0], context)
    self.addCleanup(lambda: w.top.winfo_exists() and w.top.destroy())
    self.assertEqual(w.top.title(), "Merge: other into forms")
    text = w.report()
    self.assertTrue(text.startswith("Merging other into forms\nNodes they share (by label): a, c\n"), text)
    self.assertIn("Consistent: yes\n", text)
    self.assertIn("Conservative: no\n", text)
    self.assertIn("New links in other:\n  a equivalent c\n", text)
    self.assertTrue(text.endswith("New links in forms:\n  a equivalent b\n  a equivalent c\n  b equivalent c"), text)
    self.assertNotIn("other.snm", " ".join(Model.AllDBs)) # (made just now, and let go of)
    self.assertFalse(any(r.model is not built.model and r.model.name != "knet.snm" for n in built.nodes.values()
                         for r in (*n._outgoing, *n._incoming))) # (the merge's links gone)

  @staticmethod
  def knet(nodes:list[str], links:list[str], marks:dict[str, str]|None=None) -> str:
    '''
    :param nodes: The nodes' labels (drawn in rows of five).
    :param links: The links: "tail|head|link type" (0 includes, 1 excludes).
    :param marks: The nodes' marks (by label: hex -- 81 asserted true, 82 false).
    :returns: A net of them.
    '''
    return "\ufeff" + "\r".join(l.replace("|", "\t") for l in (
      "|C|9|FFFFFF||32", "T|1", "2|0|Arial|9|1|0|000000|FFFFFF|000000|008A00|0|0|0||Concept",
      "A|2", "1|0|0|0|1|0|000000|000000|000000|000000|Includes", "1|1|0|0|1|0|00A000|00A000|00A000|00A000|Excludes",
      f"N|{len(nodes)}|0|-1",
      *[f"0|{(marks or {}).get(n, 0)}|{10 + 90 * (k % 5)}|{10 + 60 * (k // 5)}|30|19|{n}|" for k, n in enumerate(nodes)],
      f"L|{len(links)}|0", *links, "G|0")) + "\r"

  def test_expansion(self):
    '''
    A node's Expand and Net menus: an anonymous node below it (shown, without
    asking its name), the net's protoconnectives expanded (x includes a ∧ b:
    x includes a and b), and the net factored (I and J each include A, B and
    C) -- each one command, undone in one go, and each says what it did.
    '''
    from sn.hooks import HookContext
    hooks = importBundled("rnetReader", "hooks")
    v, built = self.netOf(self.knet(["x", "a ∧ b", "I", "J", "A", "B", "C"],
                                    ["0|1|0", "2|4|0", "2|5|0", "2|6|0", "3|4|0", "3|5|0", "3|6|0"]), "expand")
    m, x = built.model, built.nodes[0]
    for item, fn in (("Expand/Anonymous node below", "addAnonymousBelow"), ("Expand/Anonymous node above", "addAnonymousAbove"),
                     ("Net/Expand protoconnectives", "expandProtoconnectives"), ("Net/Factor", "factor"),
                     ("Net/Existence...", "showExistence"), ("Existence/Essentially top", "essentiallyTop"),
                     ("Existence/Essentially bottom", "essentiallyBottom"), ("Existence/Unspecified", "unspecified"),
                     ("Mark/Abduce", "abduce")):
      self.assertTrue(x[f".menu/{item}"].endswith(f":{fn}"), item)
    count = len(m)
    context = HookContext(view=v, selection=[])
    with mock.patch("builtins.print") as said, \
         mock.patch("sn.view.graphics.viewEditing.applyEditAttrsBox", side_effect=AssertionError("asked a name")):
      made = hooks.addAnonymousBelow(x, context)
      self.app.update()
    self.assertEqual(said.call_args_list[0].args[0], "Anonymous node in expand: made 1 node (anonymous 1) and 1 link:")
    self.assertEqual(said.call_args_list[1].args[0], "  anonymous 1 Includes x")
    self.assertIn("anonymous 1", self.shown(v))
    v.context.undo()
    self.app.update()
    self.assertNotIn("anonymous 1", self.shown(v))
    self.assertEqual(len(m), count)
    with mock.patch("builtins.print") as said:
      made = hooks.expandProtoconnectives(x, context)
      self.app.update()
    self.assertEqual(said.call_args_list[0].args[0], "Expand protoconnectives in expand: expanded 1 (a ∧ b).")
    self.assertEqual(sorted(hooks._describe(r) for r in made if hasattr(r, "src") and r.src is not None),
                     ["x Includes a", "x Includes b"])
    shown = self.shown(v)
    self.assertTrue({"a", "b"} <= set(shown) and "a ∧ b" not in shown)
    v.context.undo()
    self.app.update()
    shown = self.shown(v)
    self.assertTrue("a ∧ b" in shown and not {"a", "b"} & set(shown))
    links = len(self.relations(v))
    with mock.patch("builtins.print") as said:
      made = hooks.factor(x, context)
      self.app.update()
    self.assertEqual(said.call_args_list[0].args[0], "Factor expand: I, J -- includes -- A, B, C: 6 links become 5")
    self.assertEqual(len(self.relations(v)), links - 1)
    self.assertIn("anonymous 1", self.shown(v))
    v.context.undo()
    self.app.update()
    self.assertEqual(len(self.relations(v)), links)
    with mock.patch("builtins.print") as said:
      hooks.factor(x, context)
    self.app.update()

  def test_existence(self):
    '''
    A node's Existence menu specifies what the selected nodes essentially
    are (undone in one go); Net/Existence... shows the net's nodes'
    existential status in a window: Socrates, specified essentially bottom,
    is singular; and man, too, though Socrates includes it.
    '''
    from sn.hooks import HookContext
    hooks = importBundled("rnetReader", "hooks")
    existence = importBundled("rnetReader", "existence")
    v, built = self.netOf(self.knet(["Socrates", "man", "mortal"], ["0|1|0", "1|2|0"]), "existence")
    socrates, man = built.nodes[0], built.nodes[1]
    shown = self.shown(v)
    hooks.essentiallyBottom(socrates, HookContext(view=v, selection=[shown["Socrates"], shown["man"]]))
    self.assertEqual([existence.specified(n) for n in (socrates, man)], ["bottom", "bottom"])
    w = hooks.showExistence(socrates, HookContext(view=v, selection=[]))
    self.addCleanup(lambda: w.top.winfo_exists() and w.top.destroy())
    self.assertEqual(w.top.title(), "Existence: existence")
    text = w.report()
    self.assertTrue(text.startswith("Existence in existence\n"), text)
    self.assertIn("\nSocrates  yes         yes      -            yes       yes\n", text)
    self.assertIn("man is specified to be essentially bottom, but Socrates includes it.", text)
    v.context.undo()
    self.assertEqual([existence.specified(n) for n in (socrates, man)], [None, None])
    hooks.essentiallyTop(built.nodes[2], HookContext(view=v, selection=[]))
    self.assertEqual(existence.specified(built.nodes[2]), "top")
    hooks.unspecified(built.nodes[2], HookContext(view=v, selection=[]))
    self.assertIsNone(existence.specified(built.nodes[2]))

  def test_abduce(self):
    '''
    Mark/Abduce: whatever explains wet (rain, or a sprinkler), it's damp,
    and not dry -- purple bars, as KNet draws them (its defaults' colour) --
    said in the terminal; the next "reason" takes them out.
    '''
    from sn.hooks import HookContext
    hooks = importBundled("rnetReader", "hooks")
    v, built = self.netOf(self.knet(["wet", "rain", "sprinkler", "damp", "dry"],
                                    ["1|0|0", "2|0|0", "1|3|0", "2|3|0", "0|4|1"]), "abduce")
    shown = self.shown(v)
    def bars(name:str) -> list[str]:
      deco = shown[name].decorators.get("sideBars")
      return sorted(v.canvas.itemcget(i, "fill") for i in (deco.ids if deco is not None else []))
    with mock.patch("builtins.print") as said:
      found = hooks.abduce(built.nodes[0], HookContext(view=v, selection=[]))
      self.app.update()
    self.assertEqual(said.call_args_list[0].args[0], found.report())
    self.assertTrue(found.report().startswith("Abduction from wet in abduce: 2 explanations (rain, sprinkler)"))
    self.assertEqual(bars("damp"), ["#800080"])
    self.assertEqual(bars("dry"), ["#800080"])
    self.assertEqual(bars("rain"), [])
    v.reason("clingo")
    self.app.update()
    self.assertEqual(bars("damp"), [])

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

  def test_rules(self):
    'Which KNet rules the model builds on: the paper\'s at first (or what it\'s told), passed to convert().'
    reader = importBundled("rnetReader", "reader")
    net = str(self.folder / "patterns.rnet")
    self.assertEqual(self.dialog().rules.get(), reader.DIRECTIONAL)
    self.assertEqual(self.dialog(rules="sideways").rules.get(), reader.DIRECTIONAL)
    d = self.dialog(rnetPath=net, rules=reader.SYMMETRIC)
    self.assertEqual(d.rules.get(), reader.SYMMETRIC)
    with mock.patch.object(self.netView, "convert", return_value=(object(), object())) as convert:
      d.go()
    self.assertEqual(convert.call_args.kwargs["rules"], reader.SYMMETRIC)

if __name__ == "__main__":
  unittest.main()
