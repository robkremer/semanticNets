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
from sn.model.clingoReasoner import ClingoReasoner


class ReasonerSpec:
  '''
  The engine-independent specification of reasoner semantics. Every engine
  gets a subclass that also inherits *unittest.TestCase* and sets *ENGINE*.
  '''
  ENGINE:type[Reasoner]

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
    cls.ancestor = Relation(m, [m.RELATION], cls.person, cls.person, name="ancestorOf")
    cls.ancestor["transitive"] = True
    cls.ancestor["asymmetric"] = True

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
    cls.reasoner = cls.ENGINE(m)
    cls.result = cls.reasoner.run()

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

  def test0240asymmetric(self):
    self.assertFalse([v for v in self.result.violations if v.code == "asymmetric"])
    Path("temp_reasoner_asym.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    m = Model("temp_reasoner_asym.xml") # a separate model, so the cycle doesn't disturb the others
    person = Node(m, [m.NODE], name="person")
    a, b, c = (Node(m, [person], individual=True, name=n) for n in "abc")
    anc = Relation(m, [m.RELATION], person, person, name="ancestorOf")
    anc["transitive"] = True
    anc["asymmetric"] = True
    for s_, d in ((a,b), (b,c), (c,a)):
      Relation(m, [anc], s_, d, individual=True)
    bad = [v for v in self.ENGINE(m).violations() if v.code == "asymmetric"]
    self.assertTrue(bad)
    self.assertTrue(all(v.subject is anc for v in bad))

  def test0245equivalenceMinusIdentity(self):
    Path("temp_reasoner_sib.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    m = Model("temp_reasoner_sib.xml")
    person = Node(m, [m.NODE], name="person")
    a, b, c, d = (Node(m, [person], individual=True, name=n) for n in "abcd")
    sib = Relation(m, [m.RELATION], person, person, name="fullSibling")
    for tag in ("symmetric", "transitive", "irreflexive"):
      sib[tag] = True
    Relation(m, [sib], a, b, individual=True)
    Relation(m, [sib], b, c, individual=True)
    r = self.ENGINE(m).run()
    rel = lambda x: set(r.related(x, sib))
    self.assertEqual(rel(a), {b, c})                     # symmetric + transitive ...
    self.assertEqual(rel(c), {a, b})
    self.assertFalse(any(v.code == "irreflexive" for v in r.violations), [str(v) for v in r.violations])  # ... but no x -> x
    Relation(m, [sib], d, d, individual=True)            # an ASSERTED self-sibling is still an error
    self.assertTrue(any(v.code == "irreflexive" and v.args[0] is d for v in self.ENGINE(m).run().violations))
    # a transitive, irreflexive relation that isn't symmetric keeps the plain rule: a cycle is an error
    before = Relation(m, [m.RELATION], person, person, name="before")
    before["transitive"] = True; before["irreflexive"] = True
    Relation(m, [before], a, b, individual=True); Relation(m, [before], b, a, individual=True)
    self.assertTrue(any(v.code == "irreflexive" and v.subject is before for v in self.ENGINE(m).run().violations))

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

  def _fresh(self, name):
    Path(f"temp_reasoner_{name}.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    m = Model(f"temp_reasoner_{name}.xml") # a separate model, so it doesn't disturb the others
    return m, Node(m, [m.NODE], name="person")

  def test0270propertiesOfTypes(self):
    'The relational properties apply between types too, not just individuals.'
    m, _ = self._fresh("types")
    a, b, c = (Node(m, [m.NODE], name=n) for n in "abc")
    partOf = Relation(m, [m.RELATION], name="partOf"); partOf["transitive"] = True
    near = Relation(m, [m.RELATION], name="near"); near["symmetric"] = True
    same = Relation(m, [m.RELATION], name="same"); same["reflexive"] = True
    Relation(m, [partOf], a, b, individual=True); Relation(m, [partOf], b, c, individual=True)
    Relation(m, [near], a, c, individual=True)
    Relation(m, [same], b, c, individual=True)
    r = self.ENGINE(m).run()
    self.assertIn(c, r.related(a, partOf))
    self.assertIn(a, r.related(c, near))
    self.assertEqual(set(r.related(b, same)), {b, c})
    self.assertEqual(set(r.related(c, same)), {c})

  def test0275reflexive(self):
    m, person = self._fresh("refl")
    x, y = (Node(m, [person], individual=True, name=n) for n in "xy")
    same = Relation(m, [m.RELATION], person, person, name="same"); same["reflexive"] = True
    Relation(m, [same], x, y, individual=True)
    r = self.ENGINE(m).run()
    self.assertEqual(set(r.related(x, same)), {x, y})
    self.assertEqual(set(r.related(y, same)), {y})
    self.assertTrue(any(t is same and s is y and d is y for t, s, d in r.inferred))

  def test0280propertiesOfRuleObjects(self):
    'The objects the rules create get the relational properties too: a new twin is a twin both ways.'
    m, person = self._fresh("twins")
    for n in ("ann", "bob"):
      Node(m, [person], individual=True, name=n)
    twin = Relation(m, [m.RELATION], person, person, name="twin"); twin["symmetric"] = True
    rule = Node(m, [m.RULE], individual=True, name="everyone has a twin")
    P, P2, T = Node(m, [person], individual=True, name="?p"), Node(m, [m.NODE], individual=True, name="?p"), \
               Node(m, [person], individual=True, name="?t")
    Relation(m, [m.ANTECEDENT], rule, P, individual=True)
    Relation(m, [m.CONSEQUENT], rule, Relation(m, [twin], P2, T, individual=True), individual=True)
    q = Node(m, [m.QUERY], individual=True, name="twins?")
    X, Y = Node(m, [m.NODE], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?y")
    Relation(m, [m.CONTAINS], q, Relation(m, [twin], X, Y, individual=True), individual=True)
    rows = self.ENGINE(m).answer(q)
    self.assertEqual(len(rows), 4, rows) # ann -> her twin, her twin -> ann; the same for bob

  def test0285violationsOfProperties(self):
    m, person = self._fresh("props")
    a, b = (Node(m, [person], individual=True, name=n) for n in "ab")
    asym = Relation(m, [m.RELATION], person, person, name="asym"); asym["asymmetric"] = True
    Relation(m, [asym], a, b, individual=True); Relation(m, [asym], b, a, individual=True)
    Relation(m, [asym], a, a, individual=True)
    bad = Relation(m, [m.RELATION], person, person, name="bad")
    bad["reflexive"] = True; bad["irreflexive"] = True
    vs = self.ENGINE(m).run().violations
    asyms = sorted((tuple(x.name for x in v.args), v.severity) for v in vs if v.code == "asymmetric" and v.subject is asym)
    self.assertEqual(asyms, [(("a", "a"), "error"), (("a", "b"), "error")]) # once per pair
    conflict = [v for v in vs if v.code == "property_conflict" and v.subject is bad]
    self.assertEqual(len(conflict), 1)
    self.assertTrue(conflict[0].message.endswith("is both reflexive and irreflexive"), conflict[0].message)
    self.assertEqual([str(x) for x in conflict[0].args], ["reflexive", "irreflexive"])
    self.assertFalse(any(v.code == "irreflexive" and v.subject is bad for v in vs)) # (bad relates nothing)

  def test0290noSystemNoise(self):
    'The results are about the model (and its super-models), with no trace of how the reasoner works.'
    m, person = self._fresh("noise")
    a = Node(m, [person], individual=True, name="a")
    r = self.ENGINE(m).run()
    models = {id(m), id(m.TOP.model)}
    for t, s, d in r.holds:
      self.assertTrue(all(id(x.model) in models for x in (t, s, d)), (t, s, d))
    self.assertEqual(r.fired, [])
    self.assertEqual([v for v in r.violations if v.code.startswith("rule")], [])

  def test0500portableQueries(self):
    r = self.reasoner
    self.assertEqual(r.related(self.fred, self.has), [self.car1])
    self.assertEqual(r.relatedFrom(self.car1, self.owns), [self.fred, self.rex])
    self.assertTrue(r.isa(self.spot, self.dog))
    self.assertFalse(r.isa(self.rex, self.person))
    self.assertEqual(set(r.instances(self.dog)), {self.rex, self.spot})
    self.assertTrue(r.violations(self.fred) == [])


class TestClingo(ReasonerSpec, unittest.TestCase):
  ENGINE = ClingoReasoner

  def test0900getRelatedToUsesReasoning(self):
    from sn.model.reasoner import reason, clearReasoning
    clearReasoning(self.m)
    self.assertNotIn(self.tail, self.rex.getRelatedTo(self.has))     # inherited from dog: the model alone can't see it
    self.assertEqual(self.car1.getRelatedFrom(self.ancestor), [])    # nothing matches: [] (not IndexError)
    try:
      reason(self.m, "clingo")
      self.assertIn(self.tail, self.rex.getRelatedTo(self.has))
      self.assertTrue(self.rex.isRelatedTo(self.has, self.tail))
      self.assertIn(self.rex, self.tail.getRelatedFrom(self.has))
      self.assertIn((self.has, self.tail), [(r, o) for r, o in self.rex.getRelatedTo() if r is self.has])
      self.assertNotIn(self.tail, self.rex.getRelatedTo(self.has, inferred=False))
      self.assertEqual(self.fred.getRelatedTo(self.owns).count(self.car1), 1) # asserted: not duplicated
    finally:
      clearReasoning(self.m)
    self.assertNotIn(self.tail, self.rex.getRelatedTo(self.has))

  def test0800reportAndCommands(self):
    from sn.controller.modelInterface import ModelContext
    name = lambda o: o.tostring(relativeTo=self.m, format="friendly")
    report = self.result.report(self.m)
    self.assertIn(f'{name(self.rex)}, the source of', report)                     # the domain violation
    self.assertIn(f'is not in the domain of {name(self.owns)} ({name(self.person)})', report)
    self.assertIn(f'{name(self.ann)} -ancestorOf-> {name(self.fred)}', report)     # inferred
    self.assertIn(f'{name(self.rex)} -has-> {name(self.tail)}', report)            # inherited
    self.assertIn(f'{name(self.rex)} -isa-> {name(self.person)}', report)          # suggested classification
    ctx = ModelContext(self.m)
    self.assertEqual(ctx.parser.parseLine("reason"), report)
    ans = ctx.parser.parseLine('ask reasoner \'ans(X) :- holds(T,F,X), name(T,"has"), name(F,"fred").\'')
    self.assertEqual(ans, name(self.car1))

  def test0600nativeQuery(self):
    self.assertEqual(ClingoReasoner.language, "asp")
    ans = self.reasoner.query('ans(X) :- holds(T,F,X), name(T,"has"), name(F,"fred").')
    self.assertEqual([a[0] for a in ans], [self.car1])

  def test0700registry(self):
    self.assertIsInstance(Reasoner.create(self.m, "clingo"), ClingoReasoner)


if __name__ == "__main__":
  unittest.main()
