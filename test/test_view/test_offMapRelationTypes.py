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
Relation SN types that aren't on the map: the view's "show" > "relation
type" menu shows one (eg: a super-model's, which "show" > "node" doesn't
list), and a relation's "set src" and "set dst" menus make one its end,
showing it -- each a menu of every relation SN type the model can use, a
submenu for each super-model, then the model's own (as "make relation
to..." is).

Created on Nov 17, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk

import sn
from util import terminal
from sn.model.model import Model, Node, Relation, IsaIndividual, SN_URL

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
    '''
    An ontology (thing, part-of: thing -> thing, related-to: top -> top) and
    a model built on it (person, likes: person -> person; alice likes bob),
    all of the model shown: none of the ontology.
    '''
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snOffMap-")
    self.folder = Path(self.tmp.name).resolve()
    self.onto = onto = Model((self.folder / "onto.snm").as_uri())
    self.thing = Node(onto, [onto.NODE], name="thing")
    self.partOf = Relation(onto, [onto.RELATION], self.thing, self.thing, name="part-of")
    self.relatedTo = Relation(onto, [onto.RELATION], name="related-to")
    onto.save()
    self.m = m = Model((self.folder / "m.snm").as_uri())
    m.setSuperModels([str(self.folder / "onto.snm")])
    self.person = person = Node(m, [m.NODE], name="person")
    self.likes = Relation(m, [m.RELATION], person, person, name="likes")
    self.alice = Node(m, [person], individual=True, name="alice")
    self.bob = Node(m, [person], individual=True, name="bob")
    self.r = Relation(m, [self.likes], self.alice, self.bob, individual=True)
    self.sn = Model.AllDBs[SN_URL]
    self.contains = next(t for t in self.sn.values() if isinstance(t, Relation) and t.name == "contains")
    from sn.view.graphics.sngView import SNGView
    self.v = v = SNGView((self.folder / "v.snv").as_uri(), model=m)
    v.window.withdraw()
    v._askName = lambda mo, objectID=None: None
    v.showAllModel()
    self.pump()

  def tearDown(self):
    v = self.v
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

  def V(self, mo):
    'The view object of model object *mo*, or None.'
    return self.v.findViewObjectForGraphObject(mo)

  @staticmethod
  def items(menu:tk.Menu) -> list[tuple[str, str, str]]:
    ':returns: (type, label, state) of each of *menu*\'s items, but separators.'
    return [(menu.type(i), menu.entrycget(i, "label"), str(menu.entrycget(i, "state")))
            for i in range(menu.index("end") + 1) if menu.type(i) != "separator"] # type: ignore[operator]

  def sub(self, menu:tk.Menu, label:str) -> tk.Menu:
    'The submenu of *menu*\'s cascade *label*.'
    return menu.nametowidget(menu.entrycget(label, "menu"))

  def invoke(self, menu:tk.Menu, label:str) -> None:
    menu.invoke(menu.index(label))
    self.pump()

  def event(self, x:float, y:float):
    'A stand-in for a Tk event at window coordinates (*x*, *y*).'
    return SimpleNamespace(x=x, y=y, x_root=x, y_root=y, state=0, delta=0, num=1, widget=self.v.canvas)

  def showMenu(self, x:float=300, y:float=400) -> tk.Menu:
    'The background menu\'s "view" > "show" > "relation type" submenu, as if asked for at (*x*, *y*).'
    menu = self.v.makeMenu(self.event(x, y))
    return self.sub(self.sub(self.sub(menu, "view"), "show"), "relation type")

  # ---- the menus ------------------------------------------------------------------

  def test0100byModel(self):
    'Every relation SN type the model can use, by model: its super-models\' (nearest first), then its own; no variables.'
    from sn.view.graphics.viewInput import relationTypesByModel
    groups = [(m.name, [r.name for r in types]) for m, types in relationTypesByModel(self.m)]
    self.assertEqual([g[0] for g in groups], ["sn", "onto.snm", "m.snm"]) # (not the base rules: just variables)
    self.assertEqual(groups[1][1], ["part-of", "related-to"])
    self.assertEqual(groups[2][1], ["likes"])
    self.assertIn("contains", groups[0][1])
    self.assertFalse(any(n.startswith("?") or n.startswith("^") for _, names in groups for n in names))

  def test0200showMenu(self):
    'view > show > relation type: a submenu for each super-model, then the model\'s own; as "make relation to..." is.'
    menu = self.showMenu()
    self.assertEqual(self.items(menu), [("cascade", "sn", "normal"), ("cascade", "onto.snm", "normal"), ("command", "likes", "normal")])
    self.assertEqual([l for _, l, _ in self.items(self.sub(menu, "onto.snm"))], ["part-of", "related-to"])
    make = tk.Menu(self.v.canvas)
    self.V(self.alice).addModelEditingMenuItems(make)
    self.assertEqual(self.items(self.sub(make, "make relation to...")), self.items(menu))

  # ---- show -----------------------------------------------------------------------

  def test0300showOffMap(self):
    'A super-model\'s relation SN type with no ends of its own is shown where the menu was asked for, selected; one undo.'
    v = self.v
    self.assertIsNone(self.V(self.relatedTo))
    self.invoke(self.sub(self.showMenu(300, 400), "onto.snm"), "related-to")
    vo = self.V(self.relatedTo)
    self.assertIsNotNone(vo)
    cx, cy = vo.centerPt()
    self.assertLess(abs(cx - 300) + abs(cy - 400), 120, vo.boundingBox()) # (a free place near there)
    self.assertTrue(vo.selected())
    v.context.undo()
    self.pump()
    self.assertIsNone(self.V(self.relatedTo))
    v.context.redo()
    self.pump()
    self.assertIsNotNone(self.V(self.relatedTo))

  def test0400showWithItsEnds(self):
    'One with a domain and range is drawn to them (they\'re shown too); undone, they all go.'
    v = self.v
    self.invoke(self.sub(self.showMenu(), "onto.snm"), "part-of")
    vo, thing = self.V(self.partOf), self.V(self.thing)
    self.assertIsNotNone(vo)
    self.assertIsNotNone(thing)
    self.assertIs(vo.src, thing)
    self.assertIs(vo.dst, thing)
    v.context.undo()
    self.pump()
    self.assertIsNone(self.V(self.partOf))
    self.assertIsNone(self.V(self.thing))

  def test0500showShownSelectsIt(self):
    'One that\'s shown already is just selected: nothing to undo.'
    v = self.v
    likes = self.V(self.likes)
    before = (list(v.context.doList.queue), v.context.doList.index)
    self.invoke(self.showMenu(), "likes")
    self.assertIs(self.V(self.likes), likes)
    self.assertTrue(likes.selected())
    self.assertEqual((list(v.context.doList.queue), v.context.doList.index), before)

  def test0600showInLockedView(self):
    'Showing is the view\'s, not the model\'s: a locked view shows them too.'
    v = self.v
    v.setEditLocked(True)
    self.assertFalse(v.isModelEditor())
    self.invoke(self.sub(self.showMenu(), "sn"), "contains")
    self.assertIsNotNone(self.V(self.contains))

  # ---- set src, set dst -----------------------------------------------------------

  def relationMenu(self, mo) -> tk.Menu:
    menu = tk.Menu(self.v.canvas)
    self.V(mo).addModelEditingMenuItems(menu)
    return menu

  def test0700setItems(self):
    '"set src" beside "reset src", "set dst" beside "reset dst"; the type it already is greyed out.'
    menu = self.relationMenu(self.r)
    labels = [l for _, l, _ in self.items(menu)]
    i = labels.index("reset src")
    self.assertEqual(labels[i:i + 4], ["reset src", "set src", "reset dst", "set dst"])
    self.assertEqual(self.items(menu)[i + 1][0], "cascade")
    src = self.sub(menu, "set src")
    self.assertEqual([l for _, l, _ in self.items(src)], ["sn", "onto.snm", "likes"])
    self.assertEqual(self.items(self.sub(src, "onto.snm")), [("command", "part-of", "normal"), ("command", "related-to", "normal")])
    # (likes isa relation: its isa link's dst is relation, so that's greyed out there)
    isa = next(r for r in self.likes._getOutgoing(lambda r: isinstance(r, IsaIndividual)))[0]
    dst = self.sub(self.relationMenu(isa), "set dst")
    self.assertIn(("command", "relation", "disabled"), self.items(self.sub(dst, "sn")))
    self.assertIn(("command", "likes", "disabled"), self.items(dst)) # (likes isa likes: a cycle)

  def test0800setSrcOffMap(self):
    '"set src" > a super-model\'s type: it\'s the relation\'s src, and shown, beside the line\'s src end; one undo for both.'
    v = self.v
    rel = self.V(self.r)
    self.assertIsNone(self.V(self.relatedTo))
    self.invoke(self.sub(self.sub(self.relationMenu(self.r), "set src"), "onto.snm"), "related-to")
    self.assertIs(self.r.localSrc, self.relatedTo)
    vo = self.V(self.relatedTo)
    self.assertIsNotNone(vo)
    self.assertIs(rel.src, vo)
    self.assertLess(vo.centerPt()[0], rel.boundingBox()[0] + 1) # (out to the left: its src end)
    v.context.undo()
    self.pump()
    self.assertIs(self.r.localSrc, self.alice)
    self.assertIs(rel.src, self.V(self.alice))
    self.assertIsNone(self.V(self.relatedTo))
    v.context.redo()
    self.pump()
    self.assertIs(self.r.localSrc, self.relatedTo)
    self.assertIs(rel.src, self.V(self.relatedTo))

  def test0900setDstShown(self):
    '"set dst" > one that\'s shown: just the end changes.'
    v = self.v
    likes = self.V(self.likes)
    self.invoke(self.sub(self.relationMenu(self.r), "set dst"), "likes")
    self.assertIs(self.r.localDst, self.likes)
    self.assertIs(self.V(self.r).dst, likes)
    v.context.undo()
    self.pump()
    self.assertIs(self.r.localDst, self.bob)
    self.assertIs(self.V(self.likes), likes)

  def test1000isaOfNodesHasNone(self):
    'An isa link between nodes can\'t end at a relation: its "set src" and "set dst" are greyed out.'
    isa = next(r for r in self.alice._getOutgoing(lambda r: isinstance(r, IsaIndividual)))[0]
    items = dict((l, s) for _, l, s in self.items(self.relationMenu(isa)))
    self.assertEqual(items["set src"], "disabled")
    self.assertEqual(items["set dst"], "disabled")
    self.assertFalse(self.V(isa).canEndAt("src", self.likes))

  def test1100lockedView(self):
    'In a locked view, like the other model edits: not on the menu, with "reset src"/"reset dst".'
    v = self.v
    v.setEditLocked(True)
    labels = [l for _, l, _ in self.items(self.V(self.r).makeMenu())]
    for label in ("reset src", "set src", "reset dst", "set dst"):
      self.assertNotIn(label, labels)

if __name__ == "__main__":
  unittest.main()
