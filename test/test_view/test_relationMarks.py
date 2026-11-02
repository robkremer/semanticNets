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
A relation's marks in a real view (in a hidden window): stacked terminators
("vis/terminator4" = "o>", ">>"), middle marks ("vis/midMarks" = "|||"), the
line running through a label with no text, a dangling end's stub -- and that
changing a relation's own line attributes redraws it, as does changing a type
it (or a node) inherits them from, or making it an instance of another type.

Created on Nov 2, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import math
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock
import tkinter as tk

import sn
from util import terminal
from util.utils import fixURL
from sn.model.model import Model, Node, Relation
from util.attribute import Attribute

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
    decorators._fonts.clear() # (this application's: see setUpClass())
    cls.restore()
    Model._initCache()
    if not cls.prefsWereDirty:
      sn.snPrefs.setDirty(False)

  def setUp(self):
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snMarks-")
    m = self.model = Model((Path(self.tmp.name).resolve() / "marks.snm").as_uri())
    self.a = Node(m, [m.NODE], individual=True, name="a")
    self.b = Node(m, [m.NODE], individual=True, name="b")
    self.rel = Relation(m, [m.RELATION], self.a, self.b, individual=True, name="r")
    self.view = v = SNGView(fixURL(m.url, ".snv", replaceExt=True, mode="w")[0], model=m)
    v.window.withdraw()
    v._askName = lambda mo: None
    v.showAllModel()
    self.pump()
    va, vb, self.vr = (v.findViewObjectForGraphObject(o) for o in (self.a, self.b, self.rel))
    va.moveTo(20, 100, adjustPos=False)
    vb.moveTo(320, 100, adjustPos=False)
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

  def pump(self, seconds:float=0.3) -> None:
    'Let the event loop run: the model\'s notifications, and what the view puts off till idle.'
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def set(self, key:str, value) -> None:
    'Set one of the relation\'s attributes, as the attribute editor does, and let it redraw.'
    self.view.context.set_attribute(self.rel, key, value)
    self.pump()

  def types(self, ids) -> list[str]:
    return [self.view.canvas.type(i) for i in ids]

  # ---- the tests -------------------------------------------------------------

  def test0100ownAttributesRedraw(self):
    'Changing a relation\'s own terminator or line colour redraws it with the new one (the view\'s cache was stale).'
    info = self.vr.connectInfo
    self.assertEqual(self.types(info.destTerminatorIDs), ["polygon"])     # (the default: "arrow")
    self.set("vis/terminator4", "circle(8)")
    self.assertEqual(self.types(self.vr.connectInfo.destTerminatorIDs), ["oval"])
    self.set("vis/lineColor", "red")
    self.assertEqual(self.view.canvas.itemcget(self.vr.connectInfo.destLineID, "fill"), "red")

  def test0200stackedTerminators(self):
    '"o>": a circle behind the arrowhead; ">>": two arrowheads; the line stops short of them.'
    c = self.view.canvas
    self.set("vis/terminator4", "o>")
    info = self.vr.connectInfo
    self.assertEqual([t for t in self.types(info.destTerminatorIDs) if t != "line"], ["oval", "polygon"])
    self.set("vis/terminator4", ">>")
    info = self.vr.connectInfo
    self.assertEqual([t for t in self.types(info.destTerminatorIDs) if t != "line"], ["polygon", "polygon"])
    end = self.view.viewToWindow(*info.destEnd)
    last = c.coords(info.destLineID)[-2:]
    self.assertGreater(math.dist(end, last), 10)                          # (more than one arrowhead back)
    self.assertEqual(self.vr._terminalAt(*end), "dst")                    # (still grabbed at its end)

  def test0300middleMarks(self):
    '"|||" in the middle with no label text: three bars, and the line runs through the label to them.'
    c = self.view.canvas
    self.set("vis/midMarks", "|||")
    self.set("vis/label", "")
    self.assertEqual(self.vr.labelText(), "")
    info = self.vr.connectInfo
    self.assertEqual(self.types(info.middleIDs), ["line"] * 3)
    centre = self.view.viewToWindow(*self.vr.centerPt())
    self.assertLess(math.dist(c.coords(info.sourceLineID)[-2:], centre), 1.0) # (the two lines meet at its centre)
    self.assertLess(math.dist(c.coords(info.destLineID)[:2], centre), 1.0)
    bb = self.vr.boundingBox()
    self.assertGreaterEqual(min(bb[2] - bb[0], bb[3] - bb[1]), 12)        # (its box is big enough for them)
    self.set("vis/label", "$name")                                       # with text: the lines stop at its edge again
    info = self.vr.connectInfo
    self.assertGreater(math.dist(c.coords(info.sourceLineID)[-2:], centre), 3.0)
    self.assertEqual(len(info.middleIDs), 3)                             # (the marks still drawn, over the text)
    self.set("vis/midMarks", "")
    self.assertEqual(self.vr.connectInfo.middleIDs, [])

  def test0400straight(self):
    '"<|>" in the middle of a straight connector: two arrowheads and a bar.'
    self.set("vis/lineType", "straight")
    self.set("vis/midMarks", "<|>")
    self.set("vis/label", "")
    info = self.vr.connectInfo
    self.assertEqual(self.types(info.middleIDs), ["line", "polygon", "line", "polygon"]) # (the line between the heads, then the marks)

  def test0500badSpec(self):
    'A spec that can\'t be read (eg: in a saved model) draws nothing (and says so in the log).'
    from sn.view.graphics import connectors
    connectors._badSpecs.discard("arow") # (each is warned about once)
    with self.assertLogs("sn.view.graphics.connectors", level="WARNING"), \
         mock.patch("sn.model.snAttribute.checkMarks", return_value=None): # (past the check on setting it: see test0510)
      self.set("vis/terminator4", "arow")
    self.assertEqual(self.vr.connectInfo.destTerminatorIDs, [])
    self.assertIsNotNone(self.vr.connectInfo.destLineID)

  def test0510badSpecRefused(self):
    'A marks attribute set to a spec that can\'t be read is refused, saying why; one that can is taken.'
    from sn.model.snAttribute import MARKS_ATTRS
    for key in MARKS_ATTRS:
      with self.subTest(key=key):
        was = self.rel[key]
        with self.assertRaises(ValueError) as caught:
          self.rel[key] = "arow"
        self.assertIn(f'key "{key}"', str(caught.exception))
        self.assertIn('unknown mark "arow"', str(caught.exception))
        self.assertEqual(self.rel[key], was)
    with self.assertRaises(ValueError) as caught:
      self.rel.setAttr("vis/midMarks", Attribute("o)", None, None))               # (a value-only record, as the editor makes)
    self.assertIn('unexpected ")"', str(caught.exception))
    self.rel["vis/terminator4"] = "o>"
    self.rel["vis/midMarks"] = ""
    self.rel.setAttr("vis/terminator1", Attribute("circle(6) arrow(8,10,3)", None, None))
    self.assertEqual((self.rel["vis/terminator4"], self.rel["vis/midMarks"], self.rel["vis/terminator1"]),
                     ("o>", "", "circle(6) arrow(8,10,3)"))
    self.rel["vis/label"] = "arow"                                     # (other attributes aren't checked as marks)
    self.pump()
    self.assertEqual(self.vr.cache["vis/terminator4"], "o>")

  def test0520editorShowsWhy(self):
    'The attribute editor checks a marks spec before it saves, as it checks the inheritance rules: the message names the key and the mark.'
    from util.attributeEditor import HierarchicalAttrEditor
    editor = HierarchicalAttrEditor(self.view.canvas, self.rel, title="marks")
    try:
      editor.withdraw()
      editor.updatedKeys = {"vis/terminator4": Attribute("arow", None, None), "vis/midMarks": Attribute("|||", None, None), "vis/lineColor": Attribute("red", None, None)}
      errors = editor._validateUpdates()
      self.assertEqual(len(errors), 1, errors)
      self.assertIn('key "vis/terminator4"', errors[0])
      self.assertIn('unknown mark "arow"', errors[0])
      editor.updatedKeys = {"vis/terminator4": Attribute("o>", None, None)}
      self.assertEqual(editor._validateUpdates(), [])
    finally:
      editor.destroy()

  def test0530savedBadSpecStillLoads(self):
    'A saved model with a spec that can\'t be read (from before the check) still loads, with the spec as saved.'
    url = (Path(self.tmp.name).resolve() / "saved.snm").as_uri()
    m = Model(url)
    a, b = Node(m, [m.NODE], individual=True, name="a"), Node(m, [m.NODE], individual=True, name="b")
    r = Relation(m, [m.RELATION], a, b, individual=True, name="r")
    with mock.patch("sn.model.snAttribute.checkMarks", return_value=None):
      r["vis/terminator4"] = "arow"
    m.save()
    Model._initCache()
    again = Model.getDB(url, mode="r")
    loaded = next(o for o in again.values() if isinstance(o, Relation) and o.name == "r")
    self.assertEqual(loaded["vis/terminator4"], "arow")

  def test0600danglingStub(self):
    'A relation with no destination of its own: a stub, with its terminators at its end, grabbed there.'
    m = self.model
    loose = Relation(m, [m.RELATION], self.a, None, individual=True, name="loose")
    self.pump()
    vl = self.view.findViewObjectForGraphObject(loose)
    self.view.context.set_attribute(loose, "vis/terminator4", "o>")
    self.pump()
    stub = vl.__dict__["_stubIds"]["dst"]
    self.assertEqual([t for t in self.types(stub.end) if t != "line"], ["oval", "polygon"])
    end = self.view.viewToWindow(*vl.__dict__["_stubEnds"]["dst"])
    self.assertEqual(vl._terminalAt(*end), "dst")

  def test0700typeChangeRedrawsInheritors(self):
    'Changing a type\'s look redraws its instances and subtypes in the view -- and those below them that inherit it.'
    m, v, c = self.model, self.view, self.view.canvas
    ctx = v.context
    T = Node(m, [m.NODE], individual=False, name="T")
    S = Node(m, [T], individual=False, name="S")                         # (a subtype)
    t = Node(m, [S], individual=True, name="t")                          # (an instance of the subtype)
    R = Relation(m, [m.RELATION], m.NODE, m.NODE, individual=False, name="R")
    r = Relation(m, [R], self.a, self.b, individual=True, name="r2")
    self.pump()
    vS, vt, vr = (v.findViewObjectForGraphObject(o) for o in (S, t, r))
    fill = lambda vo: c.itemcget(vo._shape.id, "fill")
    ctx.set_attribute(T, "vis/fillColor", "#ff0000")                     # (the view doesn't show T)
    self.pump()
    self.assertEqual(vS.cache["vis/fillColor"], "#ff0000")
    self.assertEqual(fill(vS), "#ff0000")
    self.assertEqual(fill(vt), "#ff0000")
    ctx.set_attribute(S, "vis/fillColor", "#00ff00")                     # (S's own: hides T's from S and t)
    ctx.set_attribute(T, "vis/fillColor", "#0000ff")
    self.pump()
    self.assertEqual(fill(vt), "#00ff00")
    ctx.delete_attribute(S, "vis/fillColor")
    self.pump()
    self.assertEqual(fill(vt), "#0000ff")                                # (T's again)
    ctx.set_attribute(R, "vis/lineColor", "red")                         # a relation type
    ctx.set_attribute(R, "vis/terminator4", "o>")
    self.pump()
    self.assertEqual(c.itemcget(vr.connectInfo.destLineID, "fill"), "red")
    self.assertEqual([x for x in self.types(vr.connectInfo.destTerminatorIDs) if x != "line"], ["oval", "polygon"])

  def test0800newTypeRedraws(self):
    'Making an object an instance of another type (an isa link made, moved, taken out or put back) redraws it with what it now inherits.'
    from sn.model.model import IsaIndividual
    m, v, c = self.model, self.view, self.view.canvas
    T = Node(m, [m.NODE], individual=False, name="T")
    T["vis/fillColor"] = "#ff0000"
    U = Node(m, [m.NODE], individual=False, name="U")
    U["vis/fillColor"] = "#00ff00"
    self.pump()
    va = v.findViewObjectForGraphObject(self.a)
    fill = lambda: c.itemcget(va._shape.id, "fill")
    plain = fill()
    self.assertNotIn(plain, ("#ff0000", "#00ff00"))
    v.context.new_relation([m.ISA], individual=True, source=self.a, destination=T, model=m)
    self.pump()
    toNode, toT = (next(r for r, o in self.a._getOutgoing(lambda r: isinstance(r, IsaIndividual)) if o is t) for t in (m.NODE, T))
    self.assertEqual(fill(), plain)                                      # (the first parent's comes first: NODE's)
    toNode._disconnect()                                                 # taken out: T's now
    self.pump()
    self.assertEqual(fill(), "#ff0000")
    toT.dst = U                                                          # moved: U's
    self.pump()
    self.assertEqual(fill(), "#00ff00")
    toT.dst = T
    toNode._reconnect()                                                  # put back (after T's now)
    self.pump()
    self.assertEqual(fill(), "#ff0000")
    v.context.undo()                                                     # (the isa link to T taken out again)
    self.pump()
    self.assertEqual(fill(), plain)

if __name__ == "__main__":
  unittest.main()
