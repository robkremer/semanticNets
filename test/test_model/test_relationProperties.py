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
Created on Sep 25, 2026

@author: robkremer
'''
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.controller.modelInterface import ModelContext
from util.attribute import Attribute, LOCAL, VAR_DEFAULTED


class Test(unittest.TestCase):
  '''
  The relational properties (symmetric, ...) are LOCAL tags on relation types:
  the key's presence is the tag, they aren't inherited, and individual
  relations take them from their immediate types.
  '''

  m:Model
  person:Node; ann:Node; bob:Node
  sibling:Relation; brother:Relation; sib1:Relation; bro1:Relation

  @classmethod
  def setUpClass(cls):
    Path("temp_relprops.xml").unlink(missing_ok=True)
    Model._initCache()
    m = cls.m = Model("temp_relprops.xml")
    cls.person  = Node(m, [m.NODE], name="person")
    cls.ann     = Node(m, [cls.person], individual=True, name="ann")
    cls.bob     = Node(m, [cls.person], individual=True, name="bob")
    cls.sibling = Relation(m, [m.RELATION], cls.person, cls.person, name="sibling")
    cls.sibling["symmetric"] = False # the value is ignored: the key is the tag
    cls.brother = Relation(m, [cls.sibling], cls.person, cls.person, name="brother")
    cls.sib1    = Relation(m, [cls.sibling], cls.ann, cls.bob, individual=True)
    cls.bro1    = Relation(m, [cls.brother], cls.bob, cls.ann, individual=True)

  def test0100types(self):
    self.assertTrue(self.sibling.isSymmetric())
    self.assertFalse(self.brother.isSymmetric()) # not inherited
    self.assertFalse(self.sibling.isTransitive())

  def test0200individualsAskTheirTypes(self):
    self.assertTrue(self.sib1.isSymmetric())
    self.assertFalse(self.bro1.isSymmetric())

  def test0300isa(self):
    self.assertTrue(self.m.ISA.isTransitive())
    self.assertTrue(self.m.ISA.isReflexive())
    isaLink = next(r for r,_ in self.ann._getOutgoing() if r.isa(self.m.ISA) and r is not self.m.ISA)
    self.assertTrue(isaLink.isTransitive())

  def test0400removal(self):
    rel = Relation(self.m, [self.m.RELATION], name="temp")
    rel["asymmetric"] = True
    self.assertTrue(rel.isAsymmetric())
    self.assertFalse(rel.isSymmetric())
    del rel["asymmetric"]
    self.assertFalse(rel.isAsymmetric())

  def test0500setAttributeCommandWithRecord(self):
    # the attribute editor hands the controller complete Attribute records
    rel = Relation(self.m, [self.m.RELATION], name="temp2")
    cmd = ModelContext._Set_attribute(rel, "transitive", Attribute(True, bool, LOCAL))
    cmd.do()
    self.assertTrue(rel.isTransitive())
    cmd.undo()
    self.assertFalse(rel.isTransitive())
    cmd = ModelContext._Set_attribute(rel, "note", Attribute("hi", str, VAR_DEFAULTED))
    cmd.do()
    self.assertEqual(rel["note"], "hi")
    cmd.undo()
    self.assertNotIn("note", rel)

  def test0600domainAndRange(self):
    from sn.model.model import IsaIndividual
    from util.observer import Observer
    self.assertIs(self.sibling.domain, self.person)
    self.assertIs(self.sibling.range, self.person)
    self.assertIs(self.brother.domain, self.person)   # set locally on brother too
    sub = Relation(self.m, [self.sibling], name="halfSibling")
    self.assertIs(sub.domain, self.person)           # inherited from sibling
    class Recorder(Observer):
      topics:list = []
      def update(self, subject, *topics): self.topics += [t[0] for t in topics]
    rec = Recorder(); sub.attach(rec)
    sub.range = self.ann                             # through the dst setter: observers told
    self.assertIs(sub.dst, self.ann)
    self.assertIn("mod dst", rec.topics)
    for individual in (self.sib1, next(r for r, _ in self.ann._getOutgoing() if isinstance(r, IsaIndividual))):
      with self.assertRaises(TypeError):
        individual.domain
      with self.assertRaises(TypeError):
        individual.range = self.bob

  def test0700localEndpoints(self):
    sub = Relation(self.m, [self.sibling], name="stepSibling") # no endpoints of its own
    self.assertIsNone(sub.localSrc)
    self.assertIs(sub.src, self.person)                        # inherited from sibling
    self.assertFalse(sub.hasLocalSrc())
    self.assertIs(self.sib1.localSrc, self.ann)
    self.assertIs(self.sib1.localDst, self.bob)
    self.assertTrue(self.sib1.hasLocalDst())
    with self.assertRaises(AttributeError):                    # read-only: set src/dst instead
      sub.localSrc = self.ann # type: ignore[misc]

  def test0800inheritorsNotified(self):
    from util.observer import Observer
    thing = Node(self.m, [self.m.NODE], name="thing2"); car = Node(self.m, [thing], name="car2")
    t   = Relation(self.m, [self.m.RELATION], self.person, thing, name="uses")
    sub = Relation(self.m, [t], name="usesDaily")                          # inherits both ends
    own = Relation(self.m, [t], self.person, car, name="drives")         # has its own ends
    below = Relation(self.m, [own], name="drivesFast")                   # inherits from own, not t
    r1 = Relation(self.m, [sub], self.ann, None, individual=True)        # inherits dst (via sub)
    r2 = Relation(self.m, [t], self.ann, thing, individual=True)         # own dst
    class Recorder(Observer):
      def __init__(self): self.topics = []
      def update(self, subject, *topics): self.topics += [x[0] for x in topics]
    recs = {o: Recorder() for o in (sub, own, below, r1, r2)}
    for o, r in recs.items(): o.attach(r)
    t.range = car
    got = lambda o: [x for x in recs[o].topics if "inherited" in x]
    self.assertEqual(got(sub), ["mod inherited dst"])
    self.assertEqual(got(r1), ["mod inherited dst"])     # two levels down
    self.assertEqual(got(r2), [])                        # its own dst
    self.assertEqual(got(own), [])                       # its own dst ...
    self.assertEqual(got(below), [])                     # ... so nothing below it inherits t's
    self.assertIs(r1.dst, car)


  def test0900reflexiveTo(self):
    'A reflexive relation relates its source to itself too: once, by each relation.'
    m = self.m
    same = Relation(m, [m.RELATION], self.person, self.person, name="sameAs"); same["reflexive"] = True
    x = Node(m, [self.person], individual=True, name="x9")
    y = Node(m, [self.person], individual=True, name="y9")
    r = Relation(m, [same], x, y, individual=True)
    self.assertEqual(set(x.getRelatedTo(same)), {x, y})
    self.assertEqual(sorted(o.name for rr, o in x.getRelatedTo() if rr is r), ["x9", "y9"])

  def test0910reflexiveFrom(self):
    'getRelatedFrom() treats a reflexive relation as getRelatedTo() does, from the other end.'
    m = self.m
    same = Relation(m, [m.RELATION], self.person, self.person, name="sameAs2"); same["reflexive"] = True
    x = Node(m, [self.person], individual=True, name="x91")
    y = Node(m, [self.person], individual=True, name="y91")
    r = Relation(m, [same], x, y, individual=True)
    self.assertEqual(set(y.getRelatedFrom(same)), {x, y})
    self.assertEqual(sorted(o.name for rr, o in y.getRelatedFrom() if rr is r), ["x91", "y91"])
    self.assertEqual(set(x.getRelatedFrom(same)), set()) # (nothing relates to x)

  def test0920irreflexive(self):
    'Neither direction relates an object to itself by an irreflexive relation, even by an explicit loop.'
    m = self.m
    other = Relation(m, [m.RELATION], self.person, self.person, name="otherThan"); other["irreflexive"] = True
    x = Node(m, [self.person], individual=True, name="x92")
    y = Node(m, [self.person], individual=True, name="y92")
    r = Relation(m, [other], x, y, individual=True)
    loop = Relation(m, [other], x, x, individual=True)
    self.assertEqual(x.getRelatedTo(other), [y])
    self.assertEqual(y.getRelatedFrom(other), [x])
    self.assertEqual(x.getRelatedFrom(other), [])
    self.assertEqual([o for rr, o in x.getRelatedTo() if rr in (r, loop)], [y])
    self.assertEqual([o for rr, o in x.getRelatedFrom() if rr in (r, loop)], [])


if __name__ == "__main__":
  unittest.main()
