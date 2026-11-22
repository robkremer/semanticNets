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
Relations between the same two things (either way round): their floating
labels are spread out across the line between the ends (see
*VRelation.betweenEnds()*), so their lines are drawn apart, not one on top
of another -- whether or not the view's dynamic layout places them: eg, when
a node's refitted to its text as its view is read (Rob, 2026-11-22). A view
saved with them on top of one another is spread out when it's read (see
*SNGView.spreadParallelLabels()*), and that's not a change to it.

Created on Nov 22, 2026

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
import tkinter as tk

import sn
from util import terminal
from sn.model.model import Model, Node, Relation

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
    alice (100,300) and bob (500,300): alice -likes-> bob, alice -knows-> bob,
    bob -admires-> alice; and carol (300,600), alice -likes-> carol.
    '''
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snParallelLabels-")
    self.folder = Path(self.tmp.name).resolve()
    self.m = m = Model((self.folder / "m.snm").as_uri())
    person = Node(m, [m.NODE], name="person")
    self.types = {n: Relation(m, parents=[m.RELATION], src=person, dst=person, name=n) for n in ("likes", "knows", "admires", "helps")}
    self.alice, self.bob, self.carol = (Node(m, [person], individual=True, name=n) for n in ("alice", "bob", "carol"))
    T = self.types
    self.rels = [Relation(m, [T["likes"]], self.alice, self.bob, individual=True),
                 Relation(m, [T["knows"]], self.alice, self.bob, individual=True),
                 Relation(m, [T["admires"]], self.bob, self.alice, individual=True)]
    self.other = Relation(m, [T["likes"]], self.alice, self.carol, individual=True)
    from sn.view.graphics.sngView import SNGView
    self.v = v = SNGView((self.folder / "v.snv").as_uri(), model=m)
    v.window.withdraw()
    v._askName = lambda mo, objectID=None: None
    for mo in (self.alice, self.bob, self.carol):
      v.makeViewObjectForGraphObject(mo)
    self.pump()
    self.centre(self.V(self.alice), 100, 300)
    self.centre(self.V(self.bob), 500, 300)
    self.centre(self.V(self.carol), 300, 600)
    for mo in (*self.rels, self.other):
      v.makeViewObjectForGraphObject(mo)
    self.pump()

  def tearDown(self):
    self.close(self.v)
    Model._initCache()
    self.tmp.cleanup()

  def close(self, v) -> None:
    if not v._closed:
      v.detachFromModel()
      self.app.terminalRegistry.unregisterWindow(v.window)
    if v.window.winfo_exists():
      v.window.destroy()
    self.pump()

  def pump(self, seconds:float=0.2) -> None:
    'Let the event loop run: the model\'s notifications, and what the view puts off till idle.'
    end = time.monotonic() + seconds
    while True:
      self.app.update()
      if time.monotonic() >= end:
        break
      time.sleep(0.01)

  def V(self, mo, v=None):
    'The view object of model object *mo*.'
    vo = (v or self.v).findViewObjectForGraphObject(mo)
    self.assertIsNotNone(vo, mo)
    return vo

  @staticmethod
  def centre(vo, cx:float, cy:float, adjustPos:bool=False) -> None:
    'Put *vo*\'s centre at (*cx*, *cy*) (not a command).'
    x1, y1, x2, y2 = vo.boundingBox()
    vo.moveTo(cx - (x2 - x1) / 2, cy - (y2 - y1) / 2, adjustPos=adjustPos)

  def reread(self, change=None):
    'Save the model and the view (after *change*, if given: eg: to the view\'s file), close the view, and read it again.'
    v = self.v
    self.m.save()
    v.save()
    url = v.url
    self.close(v)
    if change is not None:
      change()
    from sn.view.graphics.sngView import SNGView
    from util.persistence.pRef import PRDb
    PRDb.AllDBs.pop(url, None)
    self.v = w = SNGView.getDB(url)
    if not hasattr(w, "window") or w.window is None:
      self.app.openWindow(w)
    self.pump(0.5)
    return w

  @staticmethod
  def overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

  def assertApart(self, v=None, msg:str="") -> list[list[int]]:
    '''
    The labels of alice's and bob's relations aren't on one another; the first
    is midway between them, the others across the line between them (above
    and below it, as it's level).
    :returns: Their boxes.
    '''
    vrs = [self.V(r, v) for r in self.rels]
    boxes = [vr.boundingBox() for vr in vrs]
    for i, a in enumerate(boxes):
      for b in boxes[i + 1:]:
        self.assertFalse(self.overlap(a, b), f"{msg}: {boxes}")
    alice, bob = self.V(self.alice, v).centerPt(), self.V(self.bob, v).centerPt()
    xs = [vr.centerPt()[0] for vr in vrs]
    ys = sorted(vr.centerPt()[1] for vr in vrs)
    mid = (alice[0] + bob[0]) / 2
    self.assertLessEqual(max(xs) - min(xs), 2, f"{msg}: on one line across theirs: {xs}")
    self.assertLessEqual(abs(xs[0] - mid), 10, f"{msg}: about midway (between their edges): {xs}")
    self.assertLess(ys[0], alice[1], f"{msg}: {ys}")
    self.assertGreater(ys[2], alice[1], f"{msg}: {ys}")
    return boxes

  def test0100spreadWhenMade(self):
    'Made one after another (either way round), they\'re apart: the first midway.'
    vrs = [self.V(r) for r in self.rels]
    self.assertEqual([len(vr.parallels()) for vr in vrs], [3, 3, 3])
    self.assertEqual(self.V(self.other).parallels(), [self.V(self.other)])
    self.assertApart()
    alice, bob = self.V(self.alice).centerPt(), self.V(self.bob).centerPt()
    self.assertLessEqual(abs(vrs[0].centerPt()[1] - alice[1]), 3)

  def test0200apartWithoutTheLayout(self):
    '''
    Put between their ends with no free place looked for (as while an end's
    dragged, or when a node's refitted as its view's read), or with no
    dynamic layout at all, they're still apart -- across the line, however
    it runs.
    '''
    for vr in [self.V(r) for r in self.rels]:
      vr.reposition(adjustPos=False)
    self.assertApart(msg="put back between their ends")
    self.v.localLayout = None
    self.centre(self.V(self.bob), 500, 310) # (as a drag does: see VObject.moveTo())
    self.pump()
    self.assertApart(msg="end moved, no layout")
    self.centre(self.V(self.bob), 100, 700)
    self.pump()
    vrs = [self.V(r) for r in self.rels]
    boxes = [vr.boundingBox() for vr in vrs]
    self.assertFalse(any(self.overlap(a, b) for i, a in enumerate(boxes) for b in boxes[i + 1:]), boxes)
    xs = sorted(vr.centerPt()[0] for vr in vrs) # (beside one another, the line being upright)
    self.assertLess(xs[0], 100)
    self.assertGreater(xs[2], 100)

  def test0300apartWhenRefittedOnReading(self):
    '''
    A node whose size is a little off its text's (eg: saved with other font
    metrics) is refitted when its view's read, and its lines' labels put
    back between their ends: still apart (Rob, 2026-11-22: "freshly read
    from a file, multiple arcs with the same src and dst are drawn on top of
    one another"). Not a change to the view.
    '''
    alice = self.V(self.alice)
    bb = alice.boundingBox()
    alice.boundingBox([bb[0], bb[1], bb[2] + 5, bb[3]])
    w = self.reread()
    self.assertNotEqual(self.V(self.alice, w).boundingBox(), [bb[0], bb[1], bb[2] + 5, bb[3]], "refitted")
    self.assertApart(w, "read")
    self.assertFalse(w.isDirty(), "not a change")

  def test0400stackedSpreadOnReading(self):
    '''
    A view saved with them on top of one another (as before 2026-11-22) has
    them spread out when it's read: not a change to it. Ones apart already
    stay where they are.
    '''
    vo = self.V(self.other)
    self.centre(vo, 280, 470) # (somewhere of its own: it's alone)
    for vr in [self.V(r) for r in self.rels]:
      self.centre(vr, 300, 300)
    self.pump()
    otherAt = vo.boundingBox()
    w = self.reread()
    self.assertApart(w, "read")
    self.assertEqual(self.V(self.other, w).boundingBox(), otherAt)
    self.assertFalse(w.isDirty(), "not a change")
    boxes = [self.V(r, w).boundingBox() for r in self.rels]
    w = self.reread() # (as it was read: not moved again)
    self.assertEqual([self.V(r, w).boundingBox() for r in self.rels], boxes)

  def test0500oneMoreMovesNoOther(self):
    'Another one between them goes beside those there: none of them moves.'
    boxes = [self.V(r).boundingBox() for r in self.rels]
    self.rels.append(Relation(self.m, [self.types["helps"]], self.alice, self.bob, individual=True))
    self.v.makeViewObjectForGraphObject(self.rels[-1])
    self.pump()
    self.assertEqual([self.V(r).boundingBox() for r in self.rels[:3]], boxes)
    new = self.V(self.rels[-1]).boundingBox()
    for b in boxes:
      self.assertFalse(self.overlap(new, b), (new, boxes))

  def test0600pinnedTakesNoPlace(self):
    'A pinned label (see VRelation.floating()) stays where it is, and the floating ones are spread out without it.'
    vrs = [self.V(r) for r in self.rels]
    vrs[1].floating(False)
    self.centre(vrs[1], 300, 100)
    pinned = vrs[1].boundingBox().copy()
    self.assertEqual(vrs[0].parallels(), [vrs[0], vrs[2]])
    self.assertNotIn(vrs[1], vrs[2].parallels())
    for vr in (vrs[0], vrs[2]):
      vr.reposition(adjustPos=False)
    self.assertEqual(vrs[1].boundingBox(), pinned)
    a, b = vrs[0].boundingBox(), vrs[2].boundingBox()
    self.assertFalse(self.overlap(a, b), (a, b))

if __name__ == "__main__":
  unittest.main()
