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
from types import SimpleNamespace
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

  # ---- the copies marker ------------------------------------------------------------

  def marked(self, vo) -> bool:
    'Whether *vo* has the copies marker, "C", by the canvas (see decorators.copiesMarked()).'
    canvas = self.v.canvas
    for m in vo.decorators["markers"].markers:
      if m.label == "C":
        return m.id is not None and bool(canvas.find_withtag(m.id)) and canvas.itemcget(m.id, "text") == "C" \
               and canvas.itemcget(m.id, "state") != "hidden"
    self.fail(f"{vo} has no copies marker")

  def test1200copiesMarked(self):
    '''
    A node shown more than once is marked "C" (each copy), while
    "gui/showCopyTags" is on; one shown once isn't -- nor anything in a
    canonical view.
    '''
    v = self.v
    bob, alice = self.V(self.bob), self.V(self.alice)
    self.assertFalse(self.marked(bob))
    self.m.setCanonicalViews(False)
    v.repaint()
    self.assertFalse(self.marked(bob), "no copies yet")
    c = self.copy(bob, 150, 400)
    self.assertTrue(self.marked(bob), "the copy is made: the one it copies is marked too")
    self.assertTrue(self.marked(c))
    self.assertFalse(self.marked(alice))
    tip = next(m for m in c.decorators["markers"].markers if m.label == "C").tooltipFunc()
    self.assertIn("2 times", tip)
    v.context.undo() # (the copy's taken away)
    self.pump()
    self.assertFalse(self.marked(bob))
    v.context.redo()
    self.pump()
    self.assertTrue(self.marked(bob))
    self.assertTrue(self.marked(c))
    v.context.erase(c) # (erased from the view)
    self.pump()
    self.assertFalse(self.marked(bob))
    v.context.undo()
    self.pump()
    self.assertTrue(self.marked(bob))
    from util.attribute import Attribute
    before, wasDirty = sn.snPrefs.getAttr("gui/showCopyTags"), sn.snPrefs.isDirty()
    try:
      sn.snPrefs["gui/showCopyTags"] = Attribute(False, before.type, before.restriction, before.note)
      v.repaint()
      self.assertFalse(self.marked(bob), "turned off")
      self.assertFalse(self.marked(c))
    finally:
      sn.snPrefs["gui/showCopyTags"] = before
      if not wasDirty:
        sn.snPrefs.setDirty(False)
    v.repaint()
    self.assertTrue(self.marked(bob))
    self.m.setCanonicalViews(True)
    v.foldCopies()
    self.pump()
    self.assertFalse(self.marked(bob), "folded: one copy, unmarked")

  # ---- cut, copy and paste in the view ---------------------------------------------

  FIT = 3
  '''How far (view units) a new view object may be from where it was put, once it's first drawn: fitted to its
  text about its centre, then grown down to its least height (see *WrappingText.fitOwner()*).'''

  def connected(self, mo, v=None) -> list:
    'The view objects (copies) shown for *mo*.'
    return [o for o in (v or self.v).viewObjectsFor(mo) if o._isConnected()]

  def modelSize(self) -> int:
    'How many objects the model has.'
    return len([o for o in self.m.values() if o is not None])

  def test1300copyAndPasteInView(self):
    """
    "Copy in view" then "Paste in view": new copies of the selection -- the
    same model objects -- laid out as they were (beside them), the line between
    them drawn between the new copies; the model's unchanged. One undo.
    """
    from sn.view.graphics import viewCopying
    self.m.setCanonicalViews(False)
    v = self.v
    alice, bob, vr = self.V(self.alice), self.V(self.bob), self.V(self.r)
    size = self.modelSize()
    viewCopying.clipboard = None
    v.doViewCopy(vos=[alice, bob])
    clip = viewCopying.clipboard
    self.assertIsNotNone(clip)
    self.assertEqual([e.modelObject for e in clip.entries], [self.alice, self.bob, self.r], "the line between them comes too")
    self.assertEqual(len(clip.selected), 2)
    v.doViewPaste()
    self.pump()
    self.assertEqual(self.modelSize(), size, "no new model objects")
    a2 = [c for c in self.connected(self.alice) if c is not alice]
    b2 = [c for c in self.connected(self.bob) if c is not bob]
    r2 = [c for c in self.connected(self.r) if c is not vr]
    self.assertEqual((len(a2), len(b2), len(r2)), (1, 1, 1))
    self.assertIs(r2[0].src, a2[0])
    self.assertIs(r2[0].dst, b2[0])
    self.assertIs(vr.src, alice, "the old line stays where it was")
    self.assertIs(vr.dst, bob)
    ox, oy = a2[0].centerPt()[0] - alice.centerPt()[0], a2[0].centerPt()[1] - alice.centerPt()[1]
    bx, by = b2[0].centerPt()[0] - bob.centerPt()[0], b2[0].centerPt()[1] - bob.centerPt()[1]
    self.assertAlmostEqual(bx, ox, delta=self.FIT, msg="moved together")
    self.assertAlmostEqual(by, oy, delta=self.FIT, msg="moved together")
    self.assertGreater(abs(ox) + abs(oy), 50, "beside them: they're still there")
    self.assertEqual(set(v.selected), {a2[0], b2[0]}, "what was asked for is selected")
    self.assertEqual(v.validate(), 0)
    v.context.undo()
    self.pump()
    self.assertEqual([len(self.connected(o)) for o in (self.alice, self.bob, self.r)], [1, 1, 1])
    v.context.redo()
    self.pump()
    self.assertEqual([len(self.connected(o)) for o in (self.alice, self.bob, self.r)], [2, 2, 2])
    self.assertIs(r2[0].src, a2[0])

  def test1310pastedLineToTheNearestCopy(self):
    'A line copied without its other end is drawn from the pasted copy to the nearest copy of that end.'
    from sn.view.graphics import viewCopying
    self.m.setCanonicalViews(False)
    v = self.v
    alice, bob, vr = self.V(self.alice), self.V(self.bob), self.V(self.r)
    far = self.copy(bob, 900, 700)
    v.doViewCopy(vos=[alice, vr])
    self.assertEqual(len(viewCopying.clipboard.entries), 2)
    v.context.view_paste(x=850, y=600)
    self.pump()
    a2 = [c for c in self.connected(self.alice) if c is not alice][0]
    r2 = [c for c in self.connected(self.r) if c is not vr][0]
    self.assertIs(r2.src, a2)
    self.assertIs(r2.dst, far, "the copy of bob nearest the pasted alice")
    self.assertIs(vr.dst, bob)

  def test1320cutInViewErasesOnly(self):
    """
    "Cut in view" erases the view objects (the model keeps their objects);
    "Paste in view" puts copies back where they were (nothing's there now).
    """
    from sn.view.graphics import viewCopying
    self.m.setCanonicalViews(False)
    v = self.v
    bob = self.V(self.bob)
    c = self.copy(bob, 150, 400)
    where = list(c.boundingBox())
    size = self.modelSize()
    v.doViewCopy(cut=True, vos=[c])
    self.pump()
    self.assertFalse(c._isConnected())
    self.assertTrue(bob._isConnected())
    self.assertTrue(self.bob._isConnected())
    self.assertEqual(self.modelSize(), size)
    self.assertIs(viewCopying.clipboard.entries[0].modelObject, self.bob)
    v.doViewPaste()
    self.pump()
    back = [x for x in self.connected(self.bob) if x is not bob]
    self.assertEqual(len(back), 1)
    for got, want in zip(back[0].boundingBox(), where):
      self.assertAlmostEqual(got, want, delta=self.FIT, msg="where it was cut from")
    v.context.undo() # (the paste)
    v.context.undo() # (the cut)
    self.pump()
    self.assertTrue(c._isConnected())
    self.assertEqual(len(self.connected(self.bob)), 2)
    self.assertEqual(self.modelSize(), size)

  def test1330aBoxCarriesItsContents(self):
    'A box copied in the view brings copies of what it carries: in the new box, which holds them as the model says.'
    self.m.setCanonicalViews(False)
    v = self.v
    B, bob = self.V(self.B), self.V(self.bob)
    v.doViewCopy(vos=[B])
    v.context.view_paste(x=900, y=500)
    self.pump()
    B2 = [c for c in self.connected(self.B) if c is not B]
    b2 = [c for c in self.connected(self.bob) if c is not bob]
    self.assertEqual((len(B2), len(b2)), (1, 1))
    x1, y1, x2, y2 = B2[0].boundingBox()
    cx, cy = b2[0].centerPt()
    self.assertTrue(x1 < cx < x2 and y1 < cy < y2, "inside the new box")
    self.assertEqual(self.holders(self.bob), ["B", "B"], "both boxes hold it")
    self.drag(B2[0], 1200, 800) # (its contents go with it)
    cx, cy = b2[0].centerPt()
    x1, y1, x2, y2 = B2[0].boundingBox()
    self.assertTrue(x1 < cx < x2 and y1 < cy < y2, "carried")
    self.assertTrue(self.B.isMember(self.bob), "the model's unchanged")
    self.assertEqual(v.validate(), 0)

  def test1340savedAndRead(self):
    'Pasted copies, and which copies their lines are drawn to, are saved with the view.'
    self.m.setCanonicalViews(False)
    v = self.v
    v.doViewCopy(vos=[self.V(self.alice), self.V(self.bob)])
    v.context.view_paste(x=100, y=600)
    self.pump()
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
    rs = self.connected(self.r, w)
    self.assertEqual(len(rs), 2)
    self.assertEqual({(r.src.modelObject, r.dst.modelObject) for r in rs}, {(self.alice, self.bob)})
    self.assertEqual(len({id(r.src) for r in rs}), 2, "each line to its own copies")
    self.assertEqual(w.validate(), 0)

  def test1350notInCanonicalViews(self):
    """
    A canonical view has none of it: no menu items, and the keys (bound in
    every view) neither copy nor paste -- in the view or the model.
    """
    from sn.view.graphics import viewCopying
    from sn.model import copying
    v = self.v
    self.assertTrue(v.canonical())
    bob = self.V(self.bob)
    menu = tk.Menu(v.canvas)
    bob.addViewMenuItems(menu)
    labels = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) == "command"]
    self.assertFalse(any("in view" in l for l in labels), labels)
    bg = v.makeMenu(SimpleNamespace(x=10, y=10))
    self.assertFalse(any("in view" in l for l in self.menuLabels(bg)))
    viewCopying.clipboard, copying.clipboard = None, None
    bob.selected(True)
    for action in ("view copy", "view cut", "view paste"):
      v._editAction(action)
    self.pump()
    self.assertIsNone(viewCopying.clipboard)
    self.assertIsNone(copying.clipboard, "not the model's copy either")
    self.assertTrue(bob._isConnected())
    self.assertEqual(len(self.connected(self.bob)), 1)
    with self.assertRaises(ValueError):
      v.context.view_cut(bob)
    self.m.setCanonicalViews(False) # (copied in a view that may show copies: but not pasted into one that doesn't)
    v.doViewCopy(vos=[bob])
    self.m.setCanonicalViews(True)
    self.assertIsNotNone(viewCopying.pasteProblem(viewCopying.clipboard, v))
    with self.assertRaises(ValueError):
      v.context.view_paste()
    self.assertEqual(len(self.connected(self.bob)), 1)

  def menuLabels(self, menu) -> list[str]:
    'The labels of *menu*\'s commands, and of its cascades\' (at any depth).'
    ret:list[str] = []
    end = menu.index("end")
    for i in range(end + 1 if end is not None else 0):
      if menu.type(i) == "command":
        ret.append(menu.entrycget(i, "label"))
      elif menu.type(i) == "cascade":
        ret += self.menuLabels(menu.nametowidget(menu.entrycget(i, "menu")))
    return ret

  def test1360menusAndKeys(self):
    """
    Not canonical: a node's menu (and a line's) has "cut in view" and "copy
    in view", the background's "paste here in view", the menu bar's Edit menu
    all three (gone again when the model's made canonical); and the keys are
    bound on the canvas.
    """
    from util.utils import getMenuBar, getSubMenu
    from sn.view.graphics import viewCopying
    from sn.view.graphics.viewBase import KEY_VIEW_CUT, KEY_VIEW_COPY, KEY_VIEW_PASTE
    v = self.v
    for key in (KEY_VIEW_CUT, KEY_VIEW_COPY, KEY_VIEW_PASTE):
      self.assertTrue(v.canvas.bind(key[0]), key)
    self.m.setCanonicalViews(False)
    bob = self.V(self.bob)
    menu = tk.Menu(v.canvas)
    bob.addViewMenuItems(menu)
    commands = {menu.entrycget(i, "label"): menu.entrycget(i, "accelerator") for i in range(menu.index("end") + 1) if menu.type(i) == "command"}
    self.assertEqual(commands.get("cut in view"), KEY_VIEW_CUT[1])
    self.assertEqual(commands.get("copy in view"), KEY_VIEW_COPY[1])
    menu = tk.Menu(v.canvas)
    self.V(self.r).addViewMenuItems(menu)
    labels = self.menuLabels(menu)
    self.assertIn("copy in view", labels, "a line's too")
    self.assertFalse(any(l.startswith("show a copy") for l in labels), "but not \"show a copy\"")
    viewCopying.clipboard = None
    bg = v.makeMenu(SimpleNamespace(x=10, y=10))
    self.assertIn("paste here in view", self.menuLabels(bg))
    bar = getMenuBar()
    if bar is None:
      return
    v._menuBarItemsShown = True
    v._refreshMenuBarItems()
    edit = getSubMenu(bar, "Edit", makeIfNone=None)
    items = lambda: [edit.entrycget(i, "label") for i in range(edit.index("end") + 1) if edit.type(i) == "command"]
    now = items()
    for item in ("Cut in view", "Copy in view", "Paste in view"):
      self.assertIn(item, now)
    self.assertEqual(now.index("Cut in view"), now.index("Select All") + 1, "after Select All")
    self.m.setCanonicalViews(True)
    v._refreshMenuBarItems()
    self.assertFalse(any("in view" in l for l in items()), items())
    v.onWindowFocusOut()

if __name__ == "__main__":
  unittest.main()
