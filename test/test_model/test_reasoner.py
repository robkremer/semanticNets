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
Created on Sep 24, 2026

@author: robkremer
'''
import unittest
import sn
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.model.reasoner import Reasoner


class Test(unittest.TestCase):

  @classmethod
  def setUpClass(cls):
    Path("temp_reasoner.xml").unlink(missing_ok=True)
    Model._initCache()
    m = cls.m = Model("temp_reasoner.xml")
    cls.thing  = Node(m, [m.NODE], name="thing")
    cls.person = Node(m, [cls.thing], name="person")
    cls.car    = Node(m, [cls.thing], name="car")
    cls.dog    = Node(m, [cls.thing], name="dog")
    cls.fred   = Node(m, [cls.person], individual=True, name="fred")
    cls.mary   = Node(m, [cls.person], individual=True, name="mary")
    cls.ann    = Node(m, [cls.person], individual=True, name="ann")
    cls.rex    = Node(m, [cls.dog], individual=True, name="rex")
    cls.car1   = Node(m, [cls.car], individual=True, name="car1")

    # relation types form their own hierarchy: owns isa has
    cls.has  = Relation(m, [m.RELATION], cls.thing, cls.thing, name="has")
    cls.owns = Relation(m, [cls.has], cls.person, cls.thing, name="owns")
    cls.ancestor = Relation(m, [m.TRANSITIVE], cls.person, cls.person, name="ancestorOf")

    Relation(m, [cls.owns], cls.fred, cls.car1, individual=True)
    Relation(m, [cls.owns], cls.rex, cls.car1, individual=True)   # domain violation
    Relation(m, [cls.ancestor], cls.ann, cls.mary, individual=True)
    Relation(m, [cls.ancestor], cls.mary, cls.fred, individual=True)

    # properties are tags that don't inherit: brother isa sibling; only sibling is symmetric
    cls.sibling = Relation(m, [m.RELATION], cls.person, cls.person, name="sibling")
    cls.sibling["symmetric"] = True
    cls.brother = Relation(m, [cls.sibling], cls.person, cls.person, name="brother")
    Relation(m, [cls.brother], cls.fred, cls.ann, individual=True)

    # relation inheritance: dog -has-> tail gives rex -has-> tail, unless refined
    cls.tail   = Node(m, [cls.thing], name="tail")
    cls.puppy  = Node(m, [cls.dog], name="puppy")
    cls.spot   = Node(m, [cls.puppy], individual=True, name="spot")
    cls.tail12 = Node(m, [cls.tail], individual=True, name="tail12")
    Relation(m, [cls.has], cls.dog, cls.tail, individual=True)
    Relation(m, [cls.has], cls.spot, cls.tail12, individual=True)
    cls.result = Reasoner(m).run()

  def test0100relationHierarchy(self):
    r = self.result
    self.assertIn(self.car1, r.related(self.fred, self.owns))
    self.assertIn(self.car1, r.related(self.fred, self.has)) # owns isa has
    # ...but that's mere subsumption, so not reported as a new inference
    self.assertNotIn((self.has, self.fred, self.car1), [(t,s,d) for t,s,d in r.inferred])

  def test0200transitive(self):
    r = self.result
    self.assertIn(self.fred, r.related(self.ann, self.ancestor))
    self.assertTrue(any(t is self.ancestor and s is self.ann and d is self.fred for t,s,d in r.inferred))

  def test0300isa(self):
    self.assertTrue(any(x is self.fred and t is self.thing for x,t in self.result.isa))

  def test0400violationsAndClassification(self):
    r = self.result
    domain = [v for v in r.violations if v.code == "domain"]
    self.assertTrue(any(v.args[1] is self.rex and v.args[2] is self.person for v in domain),
                    [str(v) for v in r.violations])
    self.assertTrue(any(x is self.rex and c is self.person for x,c in r.classify))
    self.assertFalse(any(v.args[1] is self.fred for v in domain))

  def test0250propertiesDontInherit(self):
    r = self.result
    self.assertIn(self.fred, r.related(self.ann, self.sibling))    # sibling is symmetric
    self.assertNotIn(self.fred, r.related(self.ann, self.brother)) # brother isn't

  def test0260relationInheritance(self):
    r = self.result
    self.assertIn(self.tail, r.related(self.rex, self.has))
    self.assertIn(self.tail, r.related(self.puppy, self.has))
    self.assertTrue(any(t is self.has and x is self.rex and d is self.tail for t,x,d in r.inherited))
    # spot's tail12 (isa tail) refines the inherited has -> tail
    self.assertEqual(r.related(self.spot, self.has), [self.tail12])

  def test0500query(self):
    ans = Reasoner(self.m).query('ans(X) :- holds(T,F,X), name(T,"has"), name(F,"fred").')
    self.assertEqual([a[0].name for a in ans], ["car1"])


if __name__ == "__main__":
  unittest.main()
