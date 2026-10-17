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
Relation types in views: they never float (see *VRelation.floating()*) -- the
part that needs no screen, on stand-ins for the view objects.

Created on Oct 17, 2026

@author: robkremer
'''
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from sn.model.model import Model, Node, Relation
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.treeLayout import isMember, isLink

class StandInNode(VNode):
  "Stands in for a node in a view: its model object."
  def __init__(self, mo): self.mo = mo
  modelObject = property(lambda self: self.mo)

class StandInRelation(VRelation):
  "Stands in for a relation (or relation type) in a view."
  def __init__(self, mo, hidden=False): self.mo, self.hidden = mo, hidden
  modelObject = property(lambda self: self.mo)
  def _isConnected(self): return True
  def isHidden(self): return self.hidden

class Test(unittest.TestCase):

  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    m = self.m = Model(str(Path(self.tmp.name) / "t.snm"))
    person = Node(m, [m.NODE], name="person")
    self.hasParent = Relation(m, [m.RELATION], person, person, name="has-parent")
    a, b = Node(m, [person], individual=True, name="a"), Node(m, [person], individual=True, name="b")
    self.aParentB = Relation(m, [self.hasParent], a, b, individual=True)

  def tearDown(self):
    self.tmp.cleanup()

  def label(self, mo, floating):
    moves = []
    return SimpleNamespace(modelObject=mo, _floatingAnchor=floating, reposition=lambda: moves.append(1), moves=moves)

  def test0100typesNeverFloat(self):
    t = self.label(self.hasParent, False)
    self.assertFalse(VRelation.floating(t, True)) #type: ignore[arg-type]
    self.assertFalse(t._floatingAnchor)
    self.assertEqual(t.moves, [])                                 # (nothing changed: not repositioned)

  def test0200oldFloatingTypeIsPinned(self):
    t = self.label(self.hasParent, True)                          # (as read from an old view)
    self.assertTrue(VRelation.floating(t)) #type: ignore[arg-type]  # (until the view's drawn: see SNGView._pinRelationTypes())
    self.assertFalse(VRelation.floating(t, False)) #type: ignore[arg-type]
    self.assertEqual(t.moves, [1])

  def test0300individualsStillFloat(self):
    r = self.label(self.aParentB, False)
    self.assertTrue(VRelation.floating(r, True)) #type: ignore[arg-type]
    self.assertEqual(r.moves, [1])
    self.assertFalse(VRelation.floating(r, False)) #type: ignore[arg-type]

  def test0400typesAreLaidOutAsNodes(self):
    person = next(n for n in self.m.values() if getattr(n, "name", None) == "person")
    self.assertTrue(isMember(StandInNode(person)))
    self.assertTrue(isMember(StandInRelation(self.hasParent)))     # (a relation type: as a node)
    self.assertFalse(isMember(StandInRelation(self.aParentB)))     # (a label: between its ends)
    self.assertTrue(isLink(StandInRelation(self.aParentB)))
    self.assertFalse(isLink(StandInRelation(self.aParentB, hidden=True)))
    self.assertFalse(isLink(StandInRelation(self.hasParent)))      # (its ends are its domain and range)
    isa = next(r for r in self.m.values() if isinstance(r, Relation) and r.isIndividual() and r.src is self.hasParent)
    self.assertTrue(isLink(StandInRelation(isa)))                  # (has-parent isa relation: relates two types)

if __name__ == "__main__":
  unittest.main()
