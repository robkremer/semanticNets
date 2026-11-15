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
Canonical views, and views that aren't (see *SNGView.canonical()*): a model
whose "canonicalViews" preference is false may be shown with copies -- more
than one view object for one model object -- each line drawn to one copy of
each end, remembered with the view; each copy in its own box. Set back to
canonical, the copies are folded into one.

Created on Nov 15, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
import builtins
import logging
import sys
import tempfile
import time
import unittest
from pathlib import Path
import tkinter as tk

import sn
from util import terminal
from util.commandParser import CompositeCommandMgr
from sn.model.model import Model, Node, Relation
from sn.model.modelPrefs import CANONICAL_VIEWS

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
    alice (100,100) -likes-> bob (500,100); bob in box B [400,0 700,300].
    '''
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snViewCopies-")
    self.folder = Path(self.tmp.name).resolve()
    self.m = m = Model((self.folder / "m.snm").as_uri())
    self.person = person = Node(m, [m.NODE], name="person")
    self.likes = Relation(m, parents=[m.RELATION], src=person, dst=person, name="likes")
    self.B = Node(m, [m.COLLECTION], individual=True, name="B")
    self.alice = Node(m, [person], individual=True, name="alice")
    self.bob = Node(m, [person], individual=True, name="bob")
    self.B.addMember(self.bob)
    self.r = Relation(m, [self.likes], self.alice, self.bob, individual=True)
    self.v = self.open()
    self.v.showAllModel()
    self.pump()
    V = self.V
    keep = {self.B, self.alice, self.bob, self.r}
    others = [o for o in self.v.values() if o is not None and o.modelObject is not None and o.modelObject not in keep
              and not hasattr(o, "src")]
    for i, o in enumerate(others): # (out of the way)
      o.moveTo(80 * i, 1500, adjustPos=False)
    V(self.B).reshape([400, 0, 700, 300])
    self.centre(V(self.alice), 100, 100)
    self.centre(V(self.bob), 500, 100)
    self.pump()

  def open(self, name:str="v.snv"):
    from sn.view.graphics.sngView import SNGView
    v = SNGView((self.folder / name).as_uri(), model=self.m)
    v.window.withdraw()
    v._askName = lambda mo, objectID=None: None
    return v

  def close(self, v) -> None:
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
    if v.window.winfo_exists():
      v.window.destroy()
    self.pump()

  def tearDown(self):
    self.close(self.v)
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

  def V(self, mo, v=None):
    'The (first) view object of model object *mo*.'
    vo = (v or self.v).findViewObjectForGraphObject(mo)
    self.assertIsNotNone(vo, mo)
    return vo

  @staticmethod
  def centre(vo, cx:float, cy:float) -> None:
    'Put *vo*\'s centre at (*cx*, *cy*) (not a command).'
    x1, y1, x2, y2 = vo.boundingBox()
    vo.moveTo(cx - (x2 - x1) / 2, cy - (y2 - y1) / 2, adjustPos=False)

  def copy(self, vo, cx:float, cy:float):
    'Show a copy of *vo* (by the command), its centre at (*cx*, *cy*).'
    v = self.v
    before = list(v.copiesOf(vo))
    v.context.another_copy(vo)
    self.pump()
    made = [c for c in v.copiesOf(vo) if c not in before]
    self.assertEqual(len(made), 1)
    self.centre(made[0], cx, cy)
    self.pump()
    return made[0]

  def drag(self, vo, cx:float, cy:float) -> None:
    'Drag *vo* so its centre\'s at (*cx*, *cy*), and drop it, as VObject.onButton_1() and onB1_ButtonRelease() do.'
    v = self.v
    old, along = {vo: vo.centerPt()}, set()
    for r in vo.relations:
      if r is not vo:
        old.setdefault(r, r.centerPt())
        along.add(r)
    start = list(vo.boundingBox())
    self.centre(vo, cx, cy)
    x, y = vo.boundingBox()[:2]
    with CompositeCommandMgr(v.context):
      v.context.move(vo, x, y, _oldPos=start, _drag=True)
      v._updateContainment(old, draggedAlong=along)
    self.pump()

  def holders(self, mo) -> list[str]:
    'The names of the windows that hold *mo*, sorted.'
    return sorted(w.modelObject.name for w in self.v.contextWindows() if w.containmentOf(mo))

  # ---- canonical (the default) ---------------------------------------------------

  def test0100canonicalByDefault(self):
    'A model\'s views are canonical unless it says otherwise: no copies, and two view objects for one is a fault.'
    v = self.v
    self.assertTrue(self.m.canonicalViews())
    self.assertTrue(v.canonical())
    self.assertIs(self.m.prefs.get(CANONICAL_VIEWS), True)
    with self.assertRaises(ValueError):
      v.makeCopy(self.V(self.bob))
    menu = tk.Menu(v.canvas)
    self.V(self.bob).addViewMenuItems(menu)
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
    self.assertFalse(any(l.startswith("show a copy") for l in labels), labels)
    self.assertEqual(v.validate(), 0)

  # ---- copies ---------------------------------------------------------------------

  def test0200showACopy(self):
    'Not canonical: "show a copy" makes another view object for the same model object -- undoably -- and nothing is a fault.'
    self.m.setCanonicalViews(False)
    v = self.v
    self.assertFalse(v.canonical())
    bob = self.V(self.bob)
    menu = tk.Menu(v.canvas)
    bob.addViewMenuItems(menu)
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
    self.assertIn("show a copy", labels)
    c = self.copy(bob, 150, 400)
    self.assertIs(c.modelObject, self.bob)
    self.assertEqual(v.copiesOf(bob), [bob, c])
    self.assertEqual(v.validate(), 0)
    self.assertEqual(self.V(self.r).dst, bob, "the line stays where it was")
    v.context.undo()
    self.pump()
    self.assertEqual(v.copiesOf(bob), [bob])
    v.context.redo()
    self.pump()
    self.assertEqual(v.copiesOf(bob), [bob, c])

  def test0300newLineToTheCopiesDrawnBetween(self):
    'A relation drawn between copies is drawn to those copies (not the nearest).'
    self.m.setCanonicalViews(False)
    v = self.v
    alice, bob = self.V(self.alice), self.V(self.bob)
    far = self.copy(alice, 900, 600)
    v.makeRelation(far, bob, self.likes)
    self.pump()
    made = [o for o in v.values() if o is not None and hasattr(o, "src") and o.modelObject is not self.r
            and o.modelObject is not None and o.modelObject.isIndividual() and o.modelObject.isa(self.likes)]
    self.assertEqual(len(made), 1)
    self.assertIs(made[0].src, far)
    self.assertIs(made[0].dst, bob)

  def test0400moveALineToAnotherCopy(self):
    'An end dragged onto another copy of the same: just the line moves (undoably); the model\'s the same.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    vr = self.V(self.r)
    v.context.attach_end(vr, "dst", c)
    self.pump()
    self.assertIs(vr.dst, c)
    self.assertIs(self.r.dst, self.bob)
    self.assertIn(vr, c._incoming)
    self.assertNotIn(vr, bob._incoming)
    v.context.undo()
    self.pump()
    self.assertIs(vr.dst, bob)

  def test0500savedAndRead(self):
    'Copies, which copy each line\'s drawn to, and a copy\'s own label are saved with the view, and read back.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    v.context.attach_end(self.V(self.r), "dst", c)
    v.context.own_label(c, "b.")
    self.pump()
    self.assertEqual(c.labelText(), "b.")
    self.assertEqual(bob.labelText(), "bob")
    self.m.save()
    v.save()
    url = v.url
    self.close(v)
    from sn.view.graphics.sngView import SNGView
    from util.persistence.pRef import PRDb
    PRDb.AllDBs.pop(url, None)
    self.v = w = SNGView.getDB(url)
    if not hasattr(w, "window") or w.window is None:
      self.app.openWindow(w)
    self.pump(0.5)
    copies = w.viewObjectsFor(self.bob)
    self.assertEqual(len(copies), 2)
    own = [x for x in copies if x.ownLabel is not None]
    self.assertEqual([x.ownLabel for x in own], ["b."])
    vr = self.V(self.r, w)
    self.assertIs(vr.dst, own[0], "drawn to the copy it was drawn to")
    self.assertEqual(w.validate(), 0)

  def test0600eachCopyInItsBox(self):
    'Each copy is in the box it\'s drawn in: dragging one copy out leaves the box holding the model object while another\'s there.'
    self.m.setCanonicalViews(False)
    bob = self.V(self.bob)
    c = self.copy(bob, 550, 200) # (in B too)
    self.assertEqual(self.holders(self.bob), ["B"])
    self.drag(c, 150, 500) # (one copy out: the other's still in B)
    self.assertEqual(self.holders(self.bob), ["B"])
    self.drag(bob, 900, 500) # (and now the last)
    self.assertEqual(self.holders(self.bob), [])

  def test0700foldedWhenCanonicalAgain(self):
    'Set back to canonical, a view\'s copies are folded into one: the lines drawn to the others are drawn to it.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    vr = self.V(self.r)
    v.context.attach_end(vr, "dst", c)
    self.pump()
    self.m.setCanonicalViews(True)
    self.assertEqual(v.foldCopies(), 1)
    self.pump()
    self.assertEqual(v.copiesOf(bob), [bob])
    self.assertIs(vr.dst, bob)
    self.assertEqual(v.validate(), 0)

  def test0800foldedOnReading(self):
    'A view saved with copies, read once its model\'s canonical again, shows each object once.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    v.context.attach_end(self.V(self.r), "dst", c)
    self.pump()
    v.save()
    url = v.url
    self.close(v)
    self.m.setCanonicalViews(True)
    from sn.view.graphics.sngView import SNGView
    from util.persistence.pRef import PRDb
    PRDb.AllDBs.pop(url, None)
    self.v = w = SNGView.getDB(url)
    if not hasattr(w, "window") or w.window is None:
      self.app.openWindow(w)
    self.pump(0.5)
    self.assertEqual(len([x for x in w.viewObjectsFor(self.bob) if x._isConnected()]), 1)
    self.assertIsNotNone(self.V(self.r, w).dst)
    self.assertEqual(w.validate(), 0)

  def test0900deletedAndPutBack(self):
    'Removing a model object takes all its copies out of the view; undoing that puts them all back.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    v.doRemove([bob])
    self.pump()
    self.assertFalse(bob._isConnected())
    self.assertFalse(c._isConnected())
    v.context.undo()
    self.pump()
    self.assertTrue(bob._isConnected())
    self.assertTrue(c._isConnected())

  # ---- the copies' glow -------------------------------------------------------------

  def glowing(self) -> set:
    'The view objects with a copy\'s glow, by the canvas: those with an item tagged "copyHighlight".'
    v = self.v
    return {vo for vo in list(v._db.values()) if vo is not None and getattr(vo, "decorators", None) is not None
            and "copyHighlight" in vo.decorators and set(v.canvas.find_withtag(vo.tag)) & set(v.canvas.find_withtag("copyHighlight"))}

  def test1000copiesGlowUnderTheMouse(self):
    '''
    With the mouse over a copy, the others glow (in their own colour, not a
    query's), till it leaves -- not when it just moves to another of the
    copy's items (Tk's leave, then enter).
    '''
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c1, c2 = self.copy(bob, 150, 400), self.copy(bob, 600, 500)
    alice = self.V(self.alice)
    v.selected.clear()
    for vo in (bob, c1, c2):
      vo.selected(False)
    self.pump()
    self.assertEqual(self.glowing(), set())
    bob.onEnter(None)
    self.pump()
    self.assertEqual(self.glowing(), {c1, c2})
    fill = v.canvas.itemcget(c1.decorators["copyHighlight"].id, "fill")
    self.assertEqual(fill, sn.snPrefs.get("gui/copyHighlightColor"))
    self.assertNotEqual(fill, sn.snPrefs.get("gui/highlightColor"))
    bob.onLeave(None)
    bob.onEnter(None) # (before Tk's idle: the mouse moved to its text)
    self.pump()
    self.assertEqual(self.glowing(), {c1, c2})
    bob.onLeave(None)
    self.pump()
    self.assertEqual(self.glowing(), set())
    alice.onEnter(None) # (no copies: nothing glows)
    self.pump()
    self.assertEqual(self.glowing(), set())
    alice.onLeave(None)
    c1.onEnter(None)
    self.pump()
    self.assertEqual(self.glowing(), {bob, c2})

  def test1100copiesGlowWhileSelected(self):
    'While a copy is selected, the others glow; deselected, or the model canonical again, they don\'t.'
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    bob.selected(True)
    self.pump()
    self.assertEqual(self.glowing(), {c})
    c.moveTo(200, 450, adjustPos=False) # (the glow goes with it)
    self.pump()
    self.assertEqual(self.glowing(), {c})
    bob.selected(False)
    self.pump()
    self.assertEqual(self.glowing(), set())
    c.selected(True)
    self.pump()
    self.assertEqual(self.glowing(), {bob})
    self.m.setCanonicalViews(True)
    v.foldCopies()
    self.pump()
    self.assertEqual(self.glowing(), set())
    self.assertTrue(v.canonical())

if __name__ == "__main__":
  unittest.main()
