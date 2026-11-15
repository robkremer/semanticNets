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
A relation's scope -- the box (context) that holds it -- is said by its ends,
not by where its label happens to land (see
*sn.view.graphics.viewContainment.relationScope()*): the innermost box both
its ends are in, or the global context if there's none; from a variable, the
variable's box. Drawn, or moved later: its label dragged, an end moved into
or out of a box, or a box moved into another.

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
from sn.model.model import Model, Node, Relation, IsaIndividual

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
    Boxes A (with box A1 in it), B and C, and rule R, laid out so (eg) a
    relation from alice to bob would have its label midway, in A::

      A [0,0 600,300]: alice (60,150), carol (60,250)    B [650,0 950,300]: bob (690,150)
        A1 [330,40 590,290]: erin (460,160)               dave, out in the world (780,450)
      C [1100,0 1400,300]: frank (1150,150)
      R [0,500 600,800]: antecedent ?x (60,650), ?y (240,650); consequent (300..600)
    '''
    from sn.view.graphics.sngView import SNGView
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snRelationScope-")
    self.folder = Path(self.tmp.name).resolve()
    self.m = m = Model((self.folder / "m.snm").as_uri())
    self.person = person = Node(m, [m.NODE], name="person")
    self.likes = Relation(m, parents=[m.RELATION], src=person, dst=person, name="likes")
    box = lambda name: Node(m, [m.COLLECTION], individual=True, name=name)
    self.A, self.A1, self.B, self.C = A, A1, B, C = tuple(box(n) for n in ("A", "A1", "B", "C"))
    self.R = R = Node(m, [m.RULE], individual=True, name="R")
    who = lambda name: Node(m, [person], individual=True, name=name)
    self.alice, self.carol, self.bob, self.dave, self.erin, self.frank, self.x, self.y = \
      (who(n) for n in ("alice", "carol", "bob", "dave", "erin", "frank", "?x", "?y"))
    for b, inside in ((A, [self.alice, self.carol, A1]), (A1, [self.erin]), (B, [self.bob]), (C, [self.frank])):
      for o in inside:
        b.addMember(o)
    ant = R.partFor(m.ANTECEDENT)
    R.partFor(m.CONSEQUENT)
    ant.addMember(self.x)
    ant.addMember(self.y)
    self.v = v = SNGView((self.folder / "v.snv").as_uri(), model=m)
    v.window.withdraw()
    v._askName = lambda mo, objectID=None: None
    v.showAllModel()
    self.pump()
    V = self.V
    mine = {A, A1, B, C, R, self.alice, self.carol, self.bob, self.dave, self.erin, self.frank, self.x, self.y}
    others = [o for o in v.values() if o is not None and o.modelObject is not None and o.modelObject not in mine
              and not hasattr(o, "src") and not o.isTiledPart()]
    for i, o in enumerate(others): # (out of the way)
      o.moveTo(80 * i, 1500, adjustPos=False)
    for b, bb in ((A, [0, 0, 600, 300]), (A1, [330, 40, 590, 290]), (B, [650, 0, 950, 300]), (C, [1100, 0, 1400, 300]),
                  (R, [0, 500, 600, 800])):
      V(b).reshape(bb)
    for o, (cx, cy) in ((self.alice, (60, 150)), (self.carol, (60, 250)), (self.erin, (460, 160)), (self.bob, (690, 150)),
                        (self.dave, (780, 450)), (self.frank, (1150, 150)), (self.x, (60, 650)), (self.y, (240, 650))):
      self.centre(V(o), cx, cy)
    self.pump()
    self.assertEqual(self.holders(self.alice), ["A"])
    self.assertEqual(self.holders(self.x), ["R/antecedent"])

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
    'The view object of model object *mo*.'
    vo = self.v.findViewObjectForGraphObject(mo)
    self.assertIsNotNone(vo, mo)
    return vo

  @staticmethod
  def centre(vo, cx:float, cy:float) -> None:
    'Put *vo*\'s centre at (*cx*, *cy*) (not a command).'
    x1, y1, x2, y2 = vo.boundingBox()
    vo.moveTo(cx - (x2 - x1) / 2, cy - (y2 - y1) / 2, adjustPos=False)

  def holders(self, mo) -> list[str]:
    'The names of the windows that hold *mo* (and, for a rule, the pane), sorted.'
    ret = []
    for w in self.v.contextWindows():
      for r in w.containmentOf(mo):
        pane = w.paneOfRelation(r)
        ret.append(w.modelObject.name if len(w.panes()) == 1 else f"{w.modelObject.name}/{pane}")
    return sorted(ret)

  def draw(self, src, dst) -> Relation:
    'Draw a "likes" relation from *src* to *dst* (model objects), as the view\'s menu does.'
    before = set(id(o) for o in self.m.values() if o is not None)
    self.v.makeRelation(self.V(src), self.V(dst), self.likes)
    self.pump()
    made = [o for o in self.m.values() if o is not None and id(o) not in before and isinstance(o, Relation)
            and o.isa(self.likes) and o.localSrc is src and o.localDst is dst]
    self.assertEqual(len(made), 1)
    return made[0]

  def drag(self, vo, cx:float, cy:float) -> None:
    'Drag *vo* so its centre\'s at (*cx*, *cy*), and drop it, as VObject.onButton_1() and onB1_ButtonRelease() do.'
    v = self.v
    old, along = {vo: vo.centerPt()}, set()
    if hasattr(vo, "src") or not vo.isContextWindow():
      for r in vo.relations:
        if r is not vo:
          old.setdefault(r, r.centerPt())
          along.add(r)
    start = list(vo.boundingBox())
    floated = vo.floating() if hasattr(vo, "src") else None # (a drop pins a label)
    self.centre(vo, cx, cy) # (as the drag moves it, before it's dropped)
    x, y = vo.boundingBox()[:2]
    with CompositeCommandMgr(v.context):
      v.context.move(vo, x, y, _oldPos=start, _drag=True, _wasFloating=floated)
      v._updateContainment(old, draggedAlong=along)
    self.pump()

  def inside(self, vo, box) -> bool:
    'Whether *vo*\'s centre is in a pane of *box*\'s window (a model object).'
    return self.V(box).paneAt(vo.centerPt()) is not None

  # ---- drawn -------------------------------------------------------------------

  def test0100acrossBoxesIsGlobal(self):
    'From something in one box to something in another: in neither -- though its label lands in the first.'
    r = self.draw(self.alice, self.bob)
    vr = self.V(r)
    self.assertEqual(self.holders(r), [])
    self.assertFalse(self.inside(vr, self.A), "its label's pushed out of the box it isn't in")
    self.assertFalse(self.inside(vr, self.B))

  def test0110toTheWorldIsGlobal(self):
    'From something in a box to something outside every box: the global context\'s.'
    r = self.draw(self.alice, self.dave)
    self.assertEqual(self.holders(r), [])

  def test0120withinABox(self):
    'Between two things in a box: the box\'s.'
    r = self.draw(self.alice, self.carol)
    self.assertEqual(self.holders(r), ["A"])
    self.assertTrue(self.inside(self.V(r), self.A))

  def test0130intoANestedBox(self):
    'From something in a box to something in a box inside it: the outer box\'s -- the innermost both are in.'
    r = self.draw(self.carol, self.erin)
    self.assertEqual(self.holders(r), ["A"])
    r2 = self.draw(self.erin, self.bob)
    self.assertEqual(self.holders(r2), [])

  def test0140fromAVariable(self):
    '''
    From a rule\'s variable to something out in the world: the rule\'s (the variable means nothing outside it) --
    in the part its label lands in (in a rule, the label says which part: see test0250labelSwitchesPanes), or
    else the variable\'s.
    '''
    r = self.draw(self.x, self.dave)            # (its label lands in the consequent: dave's up to the right)
    self.assertEqual(self.holders(r), ["R/consequent"])
    self.centre(self.V(self.dave), 100, 950)    # (below the antecedent: its label lands outside the rule)
    r2 = self.draw(self.dave, self.y)
    self.assertEqual(self.holders(r2), ["R/antecedent"])
    r3 = self.draw(self.y, self.x)
    self.assertEqual(self.holders(r3), ["R/antecedent"])

  def test0150undone(self):
    'Undoing the drawing takes it away, containment and all.'
    r = self.draw(self.alice, self.carol)
    self.v.context.undo()
    self.pump()
    self.assertIsNone(self.v.findViewObjectForGraphObject(r))
    self.assertEqual(self.holders(r), [])

  # ---- moved later ---------------------------------------------------------------

  def test0200endMovedOut(self):
    'An end moved out of the box: the relation goes with the border it now crosses -- to the global context; back in, back in the box.'
    r = self.draw(self.alice, self.carol)
    self.assertEqual(self.holders(r), ["A"])
    self.drag(self.V(self.carol), 300, 450)
    self.assertEqual(self.holders(self.carol), [])
    self.assertEqual(self.holders(r), [])
    self.drag(self.V(self.carol), 60, 250)
    self.assertEqual(self.holders(self.carol), ["A"])
    self.assertEqual(self.holders(r), ["A"])
    self.v.context.undo() # (each drop is undone with its containment)
    self.pump()
    self.assertEqual(self.holders(r), [])
    self.v.context.undo()
    self.pump()
    self.assertEqual(self.holders(r), ["A"])

  def test0210endMovedIn(self):
    'Both ends in a box once one\'s moved in: the box\'s.'
    r = self.draw(self.alice, self.dave)
    self.assertEqual(self.holders(r), [])
    self.drag(self.V(self.dave), 200, 120)
    self.assertEqual(self.holders(self.dave), ["A"])
    self.assertEqual(self.holders(r), ["A"])

  def test0220endMovedIntoANestedBox(self):
    'Both ends moved into the box inside: the inner box\'s, not the outer\'s too.'
    r = self.draw(self.carol, self.erin)
    self.assertEqual(self.holders(r), ["A"])
    self.drag(self.V(self.carol), 420, 240)
    self.assertEqual(self.holders(self.carol), ["A1"])
    self.assertEqual(self.holders(r), ["A1"])

  def test0230labelDraggedOut(self):
    'Its label dragged out of the box its ends are in: still the box\'s -- and the label\'s put back in it.'
    r = self.draw(self.alice, self.carol)
    vr = self.V(r)
    self.drag(vr, 300, 420)
    self.assertEqual(self.holders(r), ["A"])
    self.assertTrue(self.inside(vr, self.A), "put back in its box")

  def test0240labelDraggedIn(self):
    'The label of a relation across boxes dragged into one: still in neither -- and pushed out of it.'
    r = self.draw(self.alice, self.bob)
    vr = self.V(r)
    self.drag(vr, 800, 250)
    self.assertEqual(self.holders(r), [])
    self.assertFalse(self.inside(vr, self.B), "pushed out of the box it isn't in")

  def test0250labelSwitchesPanes(self):
    'In a rule, its label says which part it\'s in: dragged into the consequent, it\'s the consequent\'s.'
    r = self.draw(self.x, self.y)
    self.assertEqual(self.holders(r), ["R/antecedent"])
    self.drag(self.V(r), 450, 700)
    self.assertEqual(self.holders(r), ["R/consequent"])
    self.drag(self.V(r), 450, 950)      # (out of the rule: still the consequent's, and put back in it)
    self.assertEqual(self.holders(r), ["R/consequent"])
    self.assertEqual(self.V(self.R).paneAt(self.V(r).centerPt()), "consequent")
    self.drag(self.V(r), 150, 720)
    self.assertEqual(self.holders(r), ["R/antecedent"])

  def test0260variableMovedKeepsItsRelations(self):
    '''
    A relation from a variable stays in the variable's rule when the variable's moved; but moving a variable
    doesn't put its isa link to its SN type, out in the world, in the rule.
    '''
    self.centre(self.V(self.dave), 100, 950)
    self.pump()
    r = self.draw(self.x, self.dave)
    isa = next(o for o in self.m.values() if isinstance(o, IsaIndividual) and o.localSrc is self.x)
    self.assertEqual(self.holders(isa), [])
    self.drag(self.V(self.x), 120, 740)
    self.assertEqual(self.holders(r), ["R/antecedent"])
    self.assertEqual(self.holders(isa), [])

  def test0270boxMovedIntoABox(self):
    'A box dropped into another: a relation from something in it to something in the other is now the other\'s; out again, the global context\'s.'
    r = self.draw(self.frank, self.bob)
    self.assertEqual(self.holders(r), [])
    vB, vC = self.V(self.B), self.V(self.C)
    vB.reshape([650, 0, 1050, 400])
    self.pump()
    vC.reshape([1100, 0, 1250, 120])
    self.centre(self.V(self.frank), 1175, 70)
    self.pump()
    self.drag(vC, 950, 300)
    self.assertEqual(self.holders(self.C), ["B"])
    self.assertEqual(self.holders(r), ["B"])
    self.drag(vC, 1300, 300)
    self.assertEqual(self.holders(self.C), [])
    self.assertEqual(self.holders(r), [])

  # ---- hidden ------------------------------------------------------------------

  def test0300hiddenInBoxesToo(self):
    '''
    Hiding a relation SN type's category hides its relations in plain boxes (collections) as well as those out in
    the world; hiding a node SN type's category, its individuals in plain boxes too. But what a rule holds (its
    relations and variables) is shown whatever its category: hiding part of a pattern would change what it says.
    Hiding is the viewer's: it changes nothing in the model. Undone, all shown again.
    '''
    v = self.v
    rels = [self.draw(self.alice, self.bob), self.draw(self.alice, self.carol), self.draw(self.carol, self.erin)]
    inRule = self.draw(self.y, self.x)
    self.assertEqual([self.holders(r) for r in rels + [inRule]], [[], ["A"], ["A"], ["R/antecedent"]])
    boxes = [self.A, self.A1, self.B, self.C, self.R]
    people = [self.alice, self.carol, self.bob, self.erin]
    variables = [self.x, self.y]
    count = len(list(self.m.values()))
    for category, hidden in ((v.relationCategory("likes"), rels), (v.nodeCategory("person"), people + rels)):
      v.context.visibility(category, "hide")
      self.pump()
      self.assertEqual([mo.name for mo in hidden if not self.V(mo).isHidden()], [], category)
      self.assertEqual([mo.name for mo in boxes + variables + [inRule] if self.V(mo).isHidden()], [], category)
      if category.startswith("relations"):
        self.assertEqual([mo.name for mo in people if self.V(mo).isHidden()], [], category)
      self.assertEqual(len(list(self.m.values())), count)
      self.assertEqual([self.holders(r) for r in rels + [inRule]], [[], ["A"], ["A"], ["R/antecedent"]])
      v.context.undo()
      self.pump()
      self.assertEqual([mo.name for mo in people + variables + rels if self.V(mo).isHidden()], [], category)

class TestGeometry(unittest.TestCase):
  'The scope rule itself (see *relationScope()*): on lists of boxes, innermost first.'

  def test_commonBox(self):
    from sn.view.graphics.viewContainment import commonBox
    self.assertEqual(commonBox(["A1", "A"], ["A"]), "A")
    self.assertEqual(commonBox(["A"], ["B"]), None)
    self.assertEqual(commonBox(["A"], []), None)
    self.assertEqual(commonBox([], []), None)
    self.assertEqual(commonBox(["A1", "A", "Q"], ["B", "Q"]), "Q")

  def test_relationScope(self):
    from sn.view.graphics.viewContainment import relationScope
    self.assertEqual(relationScope(["A"], ["A"]), ("A", None))
    self.assertEqual(relationScope(["A"], ["B"]), (None, None))         # (across boxes: the global context)
    self.assertEqual(relationScope(["A"], []), (None, None))            # (to the world)
    self.assertEqual(relationScope(["A1", "A"], ["A"]), ("A", None))   # (the innermost both are in)
    self.assertEqual(relationScope(["R"], [], srcVariable=True), (None, "R"))  # (from a variable: its box)
    self.assertEqual(relationScope([], ["R"], dstVariable=True), (None, "R"))
    self.assertEqual(relationScope(["R"], ["R"], srcVariable=True, dstVariable=True), ("R", None))
    self.assertEqual(relationScope(["R", "Q"], ["Q"], srcVariable=True), ("Q", "R"))

if __name__ == "__main__":
  unittest.main()
