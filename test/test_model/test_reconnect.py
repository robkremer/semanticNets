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
Created on Sep 26, 2026

@author: robkremer
'''
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation, IsaIndividual
from sn.controller.modelInterface import ModelContext
from util.observer import Observer


class Recorder(Observer):
  def __init__(self):
    self.topics:list = []
  def update(self, subject, *topics):
    self.topics += [t for t in topics if t[0] in ("mod src", "mod dst")]


class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    Path("temp_reconnect.xml").unlink(missing_ok=True)
    Model._initCache()
    m = cls.m = Model("temp_reconnect.xml")
    cls.a, cls.b, cls.c = (Node(m, [m.NODE], name=n) for n in "abc")

  def test0100reconnectAndUndo(self):
    rel = Relation(self.m, [self.m.RELATION], self.a, self.b, individual=True)
    rec = Recorder()
    rel.attach(rec)
    cmd = ModelContext._Reconnect(rel, destination=self.c)
    cmd.do()
    self.assertIs(rel.dst, self.c)
    self.assertIs(rel.src, self.a)                       # untouched
    self.assertNotIn(rel, self.b._incoming)
    self.assertIn(rel, self.c._incoming)
    self.assertEqual(rec.topics, [("mod dst", (self.b, self.c))])
    cmd.undo()
    self.assertIs(rel.dst, self.b)
    self.assertIn(rel, self.b._incoming)
    self.assertNotIn(rel, self.c._incoming)
    self.assertEqual(rec.topics[-1], ("mod dst", (self.c, self.b)))

  def test0200reconnectSource(self):
    rel = Relation(self.m, [self.m.RELATION], self.a, self.b, individual=True)
    ModelContext._Reconnect(rel, source=self.c).do()
    self.assertIs(rel.src, self.c)
    self.assertIn(rel, self.c._outgoing)
    self.assertNotIn(rel, self.a._outgoing)

  def test0300repointIsaLink(self):
    t1 = Node(self.m, [self.m.NODE], name="t1")
    t2 = Node(self.m, [self.m.NODE], name="t2")
    x = Node(self.m, [t1], name="x")
    link = next(r for r, _ in x._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
    self.assertEqual(x.getParents(), [t1])
    cmd = ModelContext._Reconnect(link, destination=t2)
    cmd.do()
    self.assertEqual(x.getParents(), [t2])
    self.assertTrue(x.isa(t2))
    cmd.undo()
    self.assertEqual(x.getParents(), [t1])

  def test0500clearAnEnd(self):
    owns = Relation(self.m, [self.m.RELATION], self.a, self.c, name="ownsX")   # a type: range c
    rel = Relation(self.m, [owns], self.a, self.b, individual=True)
    cmd = ModelContext._Reconnect(rel, clear_destination=True)
    cmd.do()
    self.assertIsNone(rel.localDst)
    self.assertIs(rel.dst, self.c)                     # now inherited from its type
    self.assertNotIn(rel, self.b._incoming)
    cmd.undo()
    self.assertIs(rel.localDst, self.b)
    with self.assertRaises(ValueError):                # set and clear the same end
      ModelContext._Reconnect(rel, destination=self.c, clear_destination=True)
    link = next(r for r, _ in self.a._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
    with self.assertRaises(ValueError):                # isa links need both ends
      ModelContext._Reconnect(link, clear_destination=True)

  def test0400notARelation(self):
    with self.assertRaises(TypeError):
      ModelContext._Reconnect(self.a, destination=self.b)

  def test0900noIsaCycles(self):
    'An isa link can\'t make a type its own type, directly or not: not by making one, re-pointing one, or asserting one.'
    m = self.m
    t = Node(m, [m.NODE], name="t")
    sub = Node(m, [t], name="sub")
    c = ModelContext(m)
    isa = [r for r in t._outgoing if isinstance(r, IsaIndividual)][0]          # t isa node
    with self.assertRaises(ValueError):
      c.reconnect(isa, destination=t)                                         # t isa t
    with self.assertRaises(ValueError):
      c.reconnect(isa, destination=sub)                                       # t isa sub isa t
    with self.assertRaises(ValueError):
      c.new_relation([m.ISA], source=t, destination=t, individual=True)
    with self.assertRaises(ValueError):
      c.new_relation([m.ISA], source=t, destination=sub, individual=True)
    with self.assertRaises(ValueError):
      c.assert_(["sub", "t"])                                                 # (t is a sub)
    self.assertEqual(t.getParents(), [m.NODE])
    c.reconnect(isa, destination=self.a)                                      # (fine)
    self.assertEqual(t.getParents(), [self.a])

  def test1000oldSelfIsa(self):
    'An isa link from a type to itself (eg: in a file written before they were refused) is ignored, and reported, not fatal.'
    m = self.m
    r = Relation(m, [m.RELATION], name="has-grandparent")
    loop = IsaIndividual(m, r, r)                                             # (as an old file could have)
    self.assertEqual(r.getParents(), [m.RELATION])
    self.assertIn(m.RELATION, r.getSupers())
    self.assertEqual(r.get("vis/borderColor", None), m.RELATION.get("vis/borderColor", None)) # (attributes still inherited)
    r.clearStatusReport()
    errors = r.validate()
    self.assertTrue(any("isa link to itself" in e for e in errors))
    from sn.model.clingoReasoner import ClingoReasoner
    self.assertTrue(any(v.code == "isa_cycle" and v.subject is r for v in ClingoReasoner(m).run().violations))
    loop._disconnect()

  def test1100supersOfACycle(self):
    'getSupers() stops at an isa cycle (it doesn\'t go round it forever).'
    m = self.m
    x = Node(m, [m.NODE], name="x")
    y = Node(m, [x], name="y")
    loop = IsaIndividual(m, x, y)                                             # (x isa y isa x: as an old file could have)
    x.retract()
    self.assertIn(y, x.getSupers())
    self.assertIn(x, y.getSupers())
    loop._disconnect()


if __name__ == "__main__":
  unittest.main()
