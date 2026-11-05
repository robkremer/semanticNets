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
from sn.model.reasoner import Reasoner, Inferences
from sn.model.clingoReasoner import ClingoReasoner
from typing import TYPE_CHECKING, cast
try:
  from sn.model.nemoReasoner import NemoReasoner
except ModuleNotFoundError: # (an optional engine: pip install nemo-python)
  NemoReasoner = None # type: ignore[assignment,misc]
try:
  from sn.model.clipsReasoner import ClipsReasoner
except ModuleNotFoundError: # (an optional engine: pip install clipspy)
  ClipsReasoner = None # type: ignore[assignment,misc]
try:
  from sn.model.prologReasoner import PrologReasoner
except ImportError: # (an optional engine: SWI-Prolog, and pip install janus-swi)
  PrologReasoner = None # type: ignore[assignment,misc]

if TYPE_CHECKING: # (the spec is a mixin, so only the type checker sees it as a TestCase)
  _SpecBase = unittest.TestCase
else:
  _SpecBase = object


class ReasonerSpec(_SpecBase):
  '''
  The engine-independent specification of reasoner semantics. Every engine
  gets a subclass that also inherits *unittest.TestCase* and sets *ENGINE*.
  '''
  ENGINE:type[Reasoner]
  m:Model
  thing:Node; person:Node; car:Node; dog:Node; fred:Node; mary:Node; ann:Node; rex:Node; car1:Node
  tail:Node; puppy:Node; spot:Node; tail12:Node
  has:Relation; owns:Relation; ancestor:Relation; sibling:Relation; brother:Relation
  reasoner:Reasoner
  result:Inferences

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
    '''
    Between types, a relation means "every" at its source and "some" at its
    destination (A -r-> B: every A relates to some B), and the relational
    properties respect that: transitivity applies whatever the ends; symmetry
    only flips a relation to an individual (A -r-> x gives x -r-> A -- but
    A -r-> B says nothing about which B); reflexivity, irreflexivity and
    asymmetry are about individuals.
    '''
    m, _ = self._fresh("types")
    a, b, c = (Node(m, [m.NODE], name=n) for n in "abc")
    x = Node(m, [m.NODE], individual=True, name="x")
    partOf = Relation(m, [m.RELATION], name="partOf"); partOf["transitive"] = True
    near = Relation(m, [m.RELATION], name="near"); near["symmetric"] = True
    same = Relation(m, [m.RELATION], name="same"); same["reflexive"] = True
    other = Relation(m, [m.RELATION], name="other"); other["irreflexive"] = True
    Relation(m, [partOf], a, b, individual=True); Relation(m, [partOf], b, c, individual=True)
    Relation(m, [near], a, c, individual=True); Relation(m, [near], b, x, individual=True)
    Relation(m, [same], b, c, individual=True)
    Relation(m, [other], a, a, individual=True) # every a is other than some a: no violation
    r = self.ENGINE(m).run()
    self.assertIn(c, r.related(a, partOf))
    self.assertNotIn(a, r.related(c, near))
    self.assertIn(b, r.related(x, near))
    self.assertEqual(set(r.related(b, same)), {c})
    self.assertEqual(set(r.related(c, same)), set())
    self.assertFalse([v for v in r.violations if v.code == "irreflexive"])

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

  def test0890finishFindsTheBaseRulesOnce(self):
    '_finish() leaves out the base rules\' conclusions, finding the base rules once -- not once per conclusion.'
    import sn.model.reasoner as reasoner
    from sn.model.model import GraphObject
    from sn.model.reasoner import NewObject
    real = reasoner.baseRuleModels
    base = next(o for o in real()[0].values() if isinstance(o, GraphObject))
    mine = self.owns
    def finish(n):
      ret = Inferences(fired=[(base, self.owns, self.fred, self.car1)] * n + [(mine, self.owns, self.fred, self.car1)],
                       ruleIsa=[(base, self.fred, self.person)] * n,
                       newObjects=[NewObject(base, "?x", ())] * n + [NewObject(mine, "?y", ())])
      calls = []
      reasoner.baseRuleModels = lambda: [calls.append(1), real()][-1] # type: ignore[assignment]
      try:
        out = ClingoReasoner(self.m, showSysRules=False)._finish(ret)
      finally:
        reasoner.baseRuleModels = real
      self.assertEqual(out.fired, [(mine, self.owns, self.fred, self.car1)])
      self.assertEqual(out.ruleIsa, [])
      self.assertEqual([x.rule for x in out.newObjects], [mine])
      return len(calls)
    self.assertEqual(finish(100), finish(1))

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
      self.assertIn(self.tail, [o for r, o in self.rex.getRelatedTo() if r.isa(self.has) and r.inferred]) # (an inferred relation, in the model)
      self.assertNotIn(self.tail, self.rex.getRelatedTo(self.has, inferred=False))
      self.assertEqual(self.fred.getRelatedTo(self.owns).count(self.car1), 1) # asserted: not duplicated
    finally:
      clearReasoning(self.m)
    self.assertNotIn(self.tail, self.rex.getRelatedTo(self.has))

  def test0950inferredObjects(self):
    from sn.model.reasoner import reason, clearReasoning
    clearReasoning(self.m)
    dirty = self.m.isDirty()
    try:
      reason(self.m, "clingo")
      first = self.m.inferredObjects()
      rels = [r for r in first if isinstance(r, Relation) and r.isa(self.has) and r.localSrc is self.rex and r.localDst is self.tail]
      self.assertEqual(len(rels), 1)                                     # the inherited rex -has-> tail, as a relation
      self.assertTrue(all(r.inferred for r, _ in rels[0]._getOutgoing()))  # and its isa link
      self.assertEqual(self.m.isDirty(), dirty)                          # not something to save
      reason(self.m, "clingo")
      self.assertEqual({id(o) for o in self.m.inferredObjects()}, {id(o) for o in first}) # kept, not remade
      info = type(self.m).getInstantiationInfo()
      saved = cast(dict, next(p for p in info.postconSetters if p.name == "_db").getter(self.m))
      self.assertFalse(any(getattr(o, "inferred", False) for o in saved.values()))       # not saved
      self.m._writeLocked = True
      try:
        reason(self.m, "clingo")                                         # a write-locked model can be reasoned over
        self.assertTrue(self.m.writeLocked())
      finally:
        self.m._writeLocked = False
    finally:
      clearReasoning(self.m)
    self.assertEqual(self.m.inferredObjects(), [])

  def test0960markAsserted(self):
    from sn.model.reasoner import reason, clearReasoning
    from sn.controller.modelInterface import ModelContext
    clearReasoning(self.m)
    ctx = ModelContext(self.m)
    try:
      reason(self.m, "clingo")
      rel = next(r for r in self.m.inferredObjects() if isinstance(r, Relation) and r.isa(self.has) and r.localSrc is self.rex and r.localDst is self.tail)
      with self.assertRaises(PermissionError):                           # the reasoner's: not to be edited
        rel["note"] = "mine"
      with self.assertRaises(PermissionError):
        ctx.remove(rel)
      self.m._writeLocked = True
      try:
        with self.assertRaises(PermissionError):                         # not in a write-locked model
          ctx.mark_asserted(rel)
      finally:
        self.m._writeLocked = False
      self.m.setDirty(False)
      ctx.mark_asserted(rel)
      self.assertFalse(rel.inferred)
      self.assertFalse(any(r.inferred for r, _ in rel._getOutgoing()))  # its isa link too
      self.assertTrue(self.m.isDirty())                                  # a change to save
      saved = cast(dict, next(p for p in type(self.m).getInstantiationInfo().postconSetters if p.name == "_db").getter(self.m))
      self.assertIn(rel, list(saved.values()))
      reason(self.m, "clingo")                                           # not inferred again (it's asserted now)
      self.assertEqual([r for r in self.m.inferredObjects() if isinstance(r, Relation) and r.isa(self.has) and r.localSrc is self.rex and r.localDst is self.tail], [])
      ctx.undo()                                                         # inferred again
      self.assertTrue(rel.inferred)
    finally:
      clearReasoning(self.m)
      if rel._isConnected() and not rel.inferred: # (in case it failed half way)
        ctx.remove(rel)
      self.m.setDirty(False)

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


@unittest.skipIf(NemoReasoner is None, "the Nemo engine isn't installed (pip install nemo-python)")
class TestNemo(ReasonerSpec, unittest.TestCase):
  ENGINE = NemoReasoner # type: ignore[assignment]

  def test0600nativeQuery(self):
    self.assertEqual(NemoReasoner.language, "nemo")
    ans = self.reasoner.query('ans(?X) :- holds(?T,?F,?X), name(?T,"has"), name(?F,"fred").')
    self.assertEqual([a[0] for a in ans], [self.car1])
    with self.assertRaises(RuntimeError):
      self.reasoner.query('ans(?X) :- obj(?X), ~ans(?X).') # (not stratified: said, not a crash)

  def test0700registry(self):
    self.assertIsInstance(Reasoner.create(self.m, "nemo"), NemoReasoner)

  def test0710strings(self):
    'Strings Nemo can\'t write (it has no escapes) go there and back: names, attribute values, constraints.'
    from sn.model.reasoner import reasoningFor
    m, person = self._fresh("strings")
    odd = 'a "quoted" 100% \\ back\tslash\nline, é ✓'
    x = Node(m, [person], individual=True, name=odd)
    x["note"] = odd
    x["count"] = 3
    x["ok"] = True
    r = NemoReasoner(m)
    rows = r.query('ans(?N, ?V) :- attr(?X, "note", ?V), name(?X, ?N).')
    self.assertEqual(rows, [(odd, odd)])
    self.assertEqual(r.query('ans(?X) :- attr(?X, "count", 3), attr(?X, "ok", true).'), [(x,)])

  def test0720explain(self):
    'Nemo can say why a conclusion holds: the rules it follows by, down to what the model asserts.'
    r = NemoReasoner(self.m)
    self.assertIsNone(r.explain(self.ancestor, self.ann, self.fred)) # (no run yet)
    r.run()
    step = r.explain(self.ancestor, self.ann, self.fred)
    assert step is not None
    self.assertEqual((step.predicate, step.args), ("holds", (self.ancestor, self.ann, self.fred)))
    text = str(step)
    name = lambda o: o.tostring(relativeTo=self.m, format="friendly")
    self.assertIn('by the rule "transitive"', text)
    self.assertIn(f'{name(self.ann)} -{name(self.ancestor)}-> {name(self.mary)} (asserted)', text)
    self.assertIn(f'{name(self.mary)} -{name(self.ancestor)}-> {name(self.fred)} (asserted)', text)
    self.assertIn(f'{name(self.ancestor)} is transitive', text)
    self.assertNotIn("data(", text)                                      # (bookkeeping: brief leaves it out)
    self.assertIn("data(", "\n".join(step.lines(brief=False)))
    inherited = str(r.explain(self.has, self.rex, self.tail))
    self.assertIn(f'{name(self.dog)} -{name(self.has)}-> {name(self.tail)} (asserted)', inherited)
    self.assertIn(f'{name(self.rex)} isa {name(self.dog)}', inherited)
    self.assertIsNone(r.explain(self.ancestor, self.fred, self.ann))     # (doesn't hold)
    isa = str(r.explain(self.spot, self.thing, predicate="isa_star"))
    self.assertIn(f'{name(self.spot)} isa {name(self.puppy)}', isa)
    self.assertIn(f'{name(self.puppy)} isa {name(self.dog)}', isa)

  def test0730negatedAttributesInRules(self):
    '''
    A rule's "not" attribute test is about the attributes the model gives:
    Nemo needs the program stratified, and the rules' conclusions depend on the rules.
    '''
    m, person = self._fresh("notattr")
    a, b = (Node(m, [person], individual=True, name=n) for n in "ab")
    a["gender"] = "female"
    tagged = lambda: {(x.name, k, v) for _, x, k, v in NemoReasoner(m).run().ruleAttrs}
    def rule(name, test, conclusion):
      r = Node(m, [m.RULE], individual=True, name=name)
      X, X2 = Node(m, [person], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?x")
      X["constraints"] = test
      X2["constraints"] = conclusion
      Relation(m, [m.ANTECEDENT], r, X, individual=True)
      Relation(m, [m.CONSEQUENT], r, X2, individual=True)
    rule("unknown", "not gender", "unknown: yes")
    self.assertEqual(tagged(), {("b", "unknown", "yes")})
    rule("guess", "not gender: female", "gender: male")                   # (concludes what "unknown" tests: b's still unknown)
    self.assertEqual(tagged(), {("b", "unknown", "yes"), ("b", "gender", "male")})

  def test0740defaultEngine(self):
    'The "reasoner/engine" preference says which engine is used when none is named.'
    from unittest import mock
    from sn.model.reasoner import defaultEngine
    get = sn.snPrefs.get
    self.assertEqual(defaultEngine(), "clingo")
    with mock.patch.object(sn.snPrefs, "get", side_effect=lambda key, *a, **kw: "nemo" if key == "reasoner/engine" else get(key, *a, **kw)):
      self.assertEqual(defaultEngine(), "nemo")
      self.assertIsInstance(Reasoner.create(self.m), NemoReasoner)
    self.assertIsInstance(Reasoner.create(self.m), ClingoReasoner)

  def test0810explainCommand(self):
    from sn.controller.modelInterface import ModelContext
    from sn.model.model import IsaIndividual
    from sn.model.reasoner import reason, clearReasoning
    name = lambda o: o.tostring(relativeTo=self.m, format="friendly")
    ctx = ModelContext(self.m)
    text = ctx.parser.parseLine("explain ancestorOf ann fred") # (the type: its relations have its name too)
    self.assertIn('by the rule "transitive"', text)
    self.assertIn("doesn't hold", ctx.parser.parseLine("explain ancestorOf fred ann"))
    self.assertIn("data(", ctx.parser.parseLine("explain ancestorOf ann fred --full"))
    link = next(r for r in self.m.values() if isinstance(r, IsaIndividual) and r.src is self.spot)
    self.assertEqual(ctx.explain(link), f'{name(self.spot)} isa {name(self.puppy)}')
    clearReasoning(self.m)
    try:
      reason(self.m, "clingo") # (whichever engine reasoned: nemo explains)
      rel = next(r for r in self.m.inferredObjects() if isinstance(r, Relation) and r.isa(self.has) and r.localSrc is self.rex)
      text = ctx.explain(rel)
      self.assertTrue(text.startswith(f'{name(self.rex)} -{name(self.has)}-> {name(self.tail)}'), text)
      self.assertIn(f'{name(self.dog)} -{name(self.has)}-> {name(self.tail)} (asserted)', text)
    finally:
      clearReasoning(self.m)
    with self.assertRaises(TypeError):
      ctx.explain(self.fred)


@unittest.skipIf(ClipsReasoner is None, "the CLIPS engine isn't installed (pip install clipspy)")
class TestClips(ReasonerSpec, unittest.TestCase):
  ENGINE = ClipsReasoner # type: ignore[assignment]

  def test0600nativeQuery(self):
    self.assertEqual(ClipsReasoner.language, "clips")
    ans = self.reasoner.query('(defrule q (holds ?t ?f ?x) (name ?t "has") (name ?f "fred") => (assert (ans ?x)))')
    self.assertEqual([a[0] for a in ans], [self.car1])
    with self.assertRaises(RuntimeError) as cm:
      self.reasoner.query('(defrule q (obj ?x) (not (ans ?x)) => (assert (ans ?x)))') # (not stratified: said, not run)
    self.assertIn("stratified", str(cm.exception))
    with self.assertRaises(RuntimeError) as cm:
      self.reasoner.query('(defrule holds (obj ?x) => (assert (ans ?x)))') # (the rule base's name)
    self.assertIn("more than one rule named holds", str(cm.exception))

  def test0700registry(self):
    self.assertIsInstance(Reasoner.create(self.m, "clips"), ClipsReasoner)

  def test0710strings(self):
    'Strings, symbols and numbers go there and back: names, attribute values, constraints.'
    m, person = self._fresh("strings")
    odd = 'a "quoted" 100% \\ back\tslash\nline, é ✓ (not) ;'
    x = Node(m, [person], individual=True, name=odd)
    x["note"] = odd
    x["count"] = 3
    x["ok"] = True
    r = ClipsReasoner(m)
    rows = r.query('(defrule q (attr ?x "note" ?v) (name ?x ?n) => (assert (ans ?n ?v)))')
    self.assertEqual(rows, [(odd, odd)])
    self.assertEqual(r.query('(defrule q (attr ?x "count" 3) (attr ?x "ok" TRUE) => (assert (ans ?x)))'), [(x,)])

  def test0720stratified(self):
    'Each rule fires once what it tests with (not ...) is complete, whatever the order of the rules.'
    from sn.model.clipsReasoner import _rulesOf, _stratify
    rules, _ = _rulesOf("""
      (defrule c (b ?x) (not (a ?x)) => (assert (c ?x)))
      (defrule b1 (e ?x) => (assert (b ?x)))
      (defrule b2 (b ?x) (f ?x ?y) => (assert (b ?y)))
      (defrule a (b ?x) (g ?x) => (assert (a ?x)))
      (defrule d (c ?x) (not (b ?x)) => (assert (d ?x)))""")
    _stratify(rules)
    stratum = {r.name: r.stratum for r in rules}
    self.assertEqual(stratum["b1"], stratum["b2"])
    self.assertEqual(stratum["a"], stratum["b1"])
    self.assertGreater(stratum["c"], stratum["a"])
    self.assertGreater(stratum["d"], stratum["b1"])
    self.assertIn("(declare (salience -1))", next(r for r in rules if r.name == "c").salient())
    rules, _ = _rulesOf('(defrule p "comment" (q ?x) (not (p ?x)) => (assert (p ?x)))')
    with self.assertRaises(ValueError):
      _stratify(rules)

  def test0725ordered(self):
    'A compiled rule\'s conditions are matched in a good order: each sharing variables with those before it.'
    from sn.model.clipsReasoner import _ordered
    body = ["(data ?x)", "(data ?y)", "(data ?z)", "(holds ?t ?x ?y)", "(holds ?t ?y ?z)", "(prop ?t transitive)",
            "(test (neq ?x ?z))", "(not (attr ?x \"k\" ?v))", "(not (prop ?t symmetric))"]
    out = _ordered(body)
    self.assertEqual(sorted(out), sorted(body))
    self.assertEqual(out[0], "(prop ?t transitive)")                         # (a constant)
    self.assertEqual(out[1], "(not (prop ?t symmetric))")                    # (as soon as ?t is bound)
    self.assertLess(out.index("(holds ?t ?y ?z)"), out.index("(data ?z)"))   # (a relation before what's at its ends)
    self.assertLess(out.index("(holds ?t ?x ?y)"), out.index("(data ?x)"))
    self.assertGreater(out.index("(test (neq ?x ?z))"), out.index("(holds ?t ?y ?z)"))
    self.assertGreater(out.index('(not (attr ?x "k" ?v))'), out.index("(holds ?t ?x ?y)")) # (?v is its own)

  def test0730negatedAttributesInRules(self):
    '''
    A rule's "not" attribute test is about the attributes the model gives:
    the program must be stratified, and the rules' conclusions depend on the rules.
    '''
    m, person = self._fresh("notattr")
    a, b = (Node(m, [person], individual=True, name=n) for n in "ab")
    a["gender"] = "female"
    tagged = lambda: {(x.name, k, v) for _, x, k, v in ClipsReasoner(m).run().ruleAttrs}
    def rule(name, test, conclusion):
      r = Node(m, [m.RULE], individual=True, name=name)
      X, X2 = Node(m, [person], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?x")
      X["constraints"] = test
      X2["constraints"] = conclusion
      Relation(m, [m.ANTECEDENT], r, X, individual=True)
      Relation(m, [m.CONSEQUENT], r, X2, individual=True)
    rule("unknown", "not gender", "unknown: yes")
    self.assertEqual(tagged(), {("b", "unknown", "yes")})
    rule("guess", "not gender: female", "gender: male")                   # (concludes what "unknown" tests: b's still unknown)
    self.assertEqual(tagged(), {("b", "unknown", "yes"), ("b", "gender", "male")})


@unittest.skipIf(PrologReasoner is None, "the Prolog engine isn't installed (SWI-Prolog, and pip install janus-swi)")
class TestProlog(ReasonerSpec, unittest.TestCase):
  ENGINE = PrologReasoner # type: ignore[assignment]

  def test0600nativeQuery(self):
    self.assertEqual(PrologReasoner.language, "prolog")
    ans = self.reasoner.query('ans(X) :- name(T,"has"), name(F,"fred"), holds(T,F,X).')
    self.assertEqual([a[0] for a in ans], [self.car1])
    self.assertEqual(self.reasoner.query('ans(N) :- name(T,"has"), rel_type(T), aggregate_all(count, holds(T,_,_), N).'), # (Prolog's own predicates too)
                     [(len(self.reasoner.query('ans(S,D) :- name(T,"has"), rel_type(T), holds(T,S,D).')),)])
    with self.assertRaises(RuntimeError) as cm:
      self.reasoner.query('ans(X) :- nothing(X).')            # (an error as it runs: said)
    self.assertIn("nothing/1", str(cm.exception))
    with self.assertRaises(RuntimeError) as cm:
      self.reasoner.query('ans(X) :- obj(X).\nans(X :- obj(X).') # (where: the query's line 2)
    self.assertIn("the query, line 2", str(cm.exception))

  def test0700registry(self):
    self.assertIsInstance(Reasoner.create(self.m, "prolog"), PrologReasoner)

  def test0710strings(self):
    'Strings, symbols and numbers go there and back: names, attribute values, constraints.'
    m, person = self._fresh("strings")
    odd = 'a "quoted" 100% \\ back\tslash\nline, é ✓ (not) \'x\' \x01;'
    x = Node(m, [person], individual=True, name=odd)
    x["note"] = odd
    x["count"] = 3
    x["ok"] = True
    x["big"] = 2**70
    r = PrologReasoner(m)
    rows = r.query('ans(N,V) :- attr(X,"note",V), name(X,N).')
    self.assertEqual(rows, [(odd, odd)])
    self.assertEqual(r.query('ans(X) :- attr(X,"count",3), attr(X,"ok",true).'), [(x,)])
    self.assertEqual(r.query('ans(V) :- attr(_,"big",V).'), [(str(2**70),)])

  def test0720ordered(self):
    'A compiled rule\'s body runs in a good order: each literal sharing variables with those before it, tests once bound.'
    from sn.model.prologReasoner import _ordered
    body = ["data(X)", "data(Y)", "data(Z)", "holds(T,X,Y)", "holds(T,Y,Z)", "prop(T,'transitive')",
            "X \\== Z", 'not_exists(attr(X,"k",V))', "\\+ prop(T,'symmetric')"]
    out = _ordered(body)
    self.assertEqual(sorted(out), sorted(body))
    self.assertEqual(out[0], "prop(T,'transitive')")                        # (a constant)
    self.assertEqual(out[1], "\\+ prop(T,'symmetric')")                     # (as soon as T is bound)
    self.assertLess(out.index("holds(T,Y,Z)"), out.index("data(Z)"))       # (a relation before what's at its ends)
    self.assertLess(out.index("holds(T,X,Y)"), out.index("data(X)"))
    self.assertGreater(out.index("X \\== Z"), out.index("holds(T,Y,Z)"))
    self.assertGreater(out.index('not_exists(attr(X,"k",V))'), out.index("holds(T,X,Y)")) # (V is its own)

  def test0730negatedAttributesInRules(self):
    '''
    A rule's "not" attribute test is about the attributes the rules conclude
    too, as for clingo (Prolog's tabling has the well-founded semantics).
    '''
    m, person = self._fresh("notattr")
    a, b = (Node(m, [person], individual=True, name=n) for n in "ab")
    a["gender"] = "female"
    tagged = lambda engine: {(x.name, k, v) for _, x, k, v in Reasoner.create(m, engine).run().ruleAttrs}
    def rule(name, test, conclusion):
      r = Node(m, [m.RULE], individual=True, name=name)
      X, X2 = Node(m, [person], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?x")
      X["constraints"] = test
      X2["constraints"] = conclusion
      Relation(m, [m.ANTECEDENT], r, X, individual=True)
      Relation(m, [m.CONSEQUENT], r, X2, individual=True)
    rule("unknown", "not gender", "unknown: yes")
    self.assertEqual(tagged("prolog"), {("b", "unknown", "yes")})
    rule("guess", "not gender: female", "gender: male")                   # (concludes what "unknown" tests: b's gender is known now)
    self.assertEqual(tagged("prolog"), {("b", "gender", "male")})
    self.assertEqual(tagged("prolog"), tagged("clingo"))

  def test0740undecided(self):
    'A rule that negates what it concludes (a loop through "not": undecided): what depends on it isn\'t concluded, and the rest is.'
    m, person = self._fresh("undecided")
    a = Node(m, [person], individual=True, name="a")
    a["tall"] = True
    def rule(name, test, conclusion):
      r = Node(m, [m.RULE], individual=True, name=name)
      X, X2 = Node(m, [person], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?x")
      X["constraints"] = test
      X2["constraints"] = conclusion
      Relation(m, [m.ANTECEDENT], r, X, individual=True)
      Relation(m, [m.CONSEQUENT], r, X2, individual=True)
    rule("odd", "not odd", "odd: yes")
    rule("plain", "tall", "seen: yes")
    self.assertEqual({(x.name, k) for _, x, k, _v in PrologReasoner(m).run().ruleAttrs}, {("a", "seen")})


class TestEngines(unittest.TestCase):
  'Which engines there are, whether they\'re installed, and what a missing one says (none of it needs Nemo).'

  def setUp(self):
    from unittest import mock
    self.mock = mock
    self.engines = mock.patch.dict(Reasoner.engines) # (an engine "not installed" mustn't be registered)
    self.engines.start()
    self.addCleanup(self.engines.stop)

  def _notInstalled(self, engine:str, error:ImportError|None=None):
    'Patches that make *engine* look uninstalled (or broken: its import raises *error*).'
    from sn.model import reasoner
    from sn.model.reasoner import ENGINES
    Reasoner.engines.pop(engine, None)
    module = ENGINES[engine].module
    if error is None:
      error = ModuleNotFoundError(f"No module named '{module}'", name=module)
    def importModule(name, *args):
      raise error
    real = reasoner.importlib.util.find_spec
    return (self.mock.patch.object(reasoner, "import_module", importModule),
            self.mock.patch.object(reasoner.importlib.util, "find_spec",
                                   lambda name, *a: None if name == module else real(name, *a)))

  def test0100enginesAreTheSettingsChoices(self):
    'Every known engine is a choice of the "reasoner/engine" setting, and the other way round.'
    from sn.model.reasoner import ENGINES
    typ = sn.PREFS["reasoner/engine"][0]
    self.assertEqual(typ, f"choices[{','.join(ENGINES)}]")

  def test0110savedChoices(self):
    'Preferences saved when there were fewer engines get today\'s choices (keeping their value, if it\'s still one).'
    from util.attribute import Attribute, VAR_DEFAULTED
    from util.prefs import Prefs
    typ = sn.PREFS["reasoner/engine"][0]
    prefs = Prefs()
    prefs.setAttr("reasoner/engine", Attribute("nemo", "choices[clingo,nemo]", VAR_DEFAULTED, ""))
    sn.initPrefs(prefs)
    self.assertEqual((dict.get(prefs, "reasoner/engine").type, prefs["reasoner/engine"]), (typ, "nemo"))
    prefs.setAttr("reasoner/engine", Attribute("gone", "choices[clingo,gone]", VAR_DEFAULTED, ""))
    sn.initPrefs(prefs)
    self.assertEqual((dict.get(prefs, "reasoner/engine").type, prefs["reasoner/engine"]), (typ, "clingo"))

  def test0200installed(self):
    from sn.model.reasoner import engineInstalled, installedEngines
    self.assertTrue(engineInstalled("clingo"))
    self.assertIn("clingo", installedEngines())
    self.assertFalse(engineInstalled("bogus"))
    importing, finding = self._notInstalled("nemo")
    with importing, finding:
      self.assertFalse(engineInstalled("nemo"))
      self.assertNotIn("nemo", installedEngines())

  def test0300missing(self):
    'Making a reasoner by an engine that isn\'t installed says how to install it.'
    from sn.model.reasoner import EngineMissing
    importing, finding = self._notInstalled("nemo")
    with importing, finding, self.assertRaises(EngineMissing) as cm:
      Reasoner.create(None, "nemo") # type: ignore[arg-type]
    ex = cm.exception
    self.assertIsInstance(ex, ImportError)
    self.assertEqual((ex.engine, ex.package, ex.detail, ex.name), ("nemo", "nemo-python", "", "nmo_python"))
    self.assertIn("isn't installed", str(ex))
    self.assertIn("pip install nemo-python", str(ex))
    self.assertIn("Installing an engine", str(ex))

  def test0310broken(self):
    'An engine that\'s installed but won\'t load says why.'
    from sn.model.reasoner import EngineMissing
    importing, _finding = self._notInstalled("nemo", ImportError("DLL load failed", name="nmo_python.nmo_python"))
    with importing, self.assertRaises(EngineMissing) as cm:
      Reasoner.create(None, "nemo") # type: ignore[arg-type]
    self.assertEqual(cm.exception.detail, "DLL load failed")
    self.assertIn("isn't working (DLL load failed)", str(cm.exception))

  def test0320unknown(self):
    with self.assertRaises(ValueError) as cm:
      Reasoner.create(None, "bogus") # type: ignore[arg-type]
    self.assertIn("clingo, nemo", str(cm.exception))

  def test0400explainingEngine(self):
    'Explaining uses an engine that can: nemo, installed or not (then it says how to install it).'
    from sn.model.reasoner import explainingEngine
    self.assertEqual(explainingEngine(), "nemo")
    importing, finding = self._notInstalled("nemo")
    with importing, finding:
      self.assertEqual(explainingEngine(), "nemo")

  def test0600lookOutside(self):
    'In an app, an engine it doesn\'t include is looked for in a Python on the computer: the setting\'s, or one found.'
    import sys
    from sn.model.reasoner import EngineMissing, engineInstalled
    importing, finding = self._notInstalled("nemo")
    with importing, finding, self.mock.patch("util.localPython.addPackages", return_value=[]) as adding:
      self.assertFalse(engineInstalled("nemo"))                      # (not an app: its own Python is the one)
      adding.assert_not_called()
      with self.mock.patch.object(sys, "frozen", True, create=True):
        self.assertFalse(engineInstalled("nemo"))
        adding.assert_called_with(None)
        with self.assertRaises(EngineMissing):
          Reasoner.create(None, "nemo") # type: ignore[arg-type]
        get = sn.snPrefs.get
        with self.mock.patch.object(sn.snPrefs, "get", lambda key, *a, **kw: "/my/python" if key == "reasoner/python" else get(key, *a, **kw)):
          engineInstalled("nemo")
        adding.assert_called_with("/my/python")

  def test0610foundOutside(self):
    'An engine found in a Python on the computer is imported from there.'
    import sys
    from sn.model import reasoner
    class Found(Reasoner): # (stands for the engine, as its module would register it)
      def run(self): ...
      def answer(self, query): ...
    calls = []
    def importModule(name, *args):
      calls.append(name)
      if len(calls) == 1:
        raise ModuleNotFoundError("No module named 'nmo_python'", name="nmo_python")
      Reasoner.engines["nemo"] = Found
    Reasoner.engines.pop("nemo", None)
    with self.mock.patch.object(reasoner, "import_module", importModule), \
         self.mock.patch("util.localPython.addPackages", return_value=["/its/site-packages"]), \
         self.mock.patch.object(sys, "frozen", True, create=True):
      self.assertIsInstance(Reasoner.create(None, "nemo"), Found) # type: ignore[arg-type]
    self.assertEqual(calls, ["sn.model.nemoReasoner"] * 2)

  def test0500setDefaultEngine(self):
    'Choosing the default engine keeps the setting a choice (a plain value would make it any text).'
    from sn.model.reasoner import setDefaultEngine, defaultEngine
    before = sn.snPrefs.getAttr("reasoner/engine")
    wasDirty = sn.snPrefs.isDirty()
    try:
      setDefaultEngine("nemo")
      self.assertEqual(defaultEngine(), "nemo")
      self.assertEqual(sn.snPrefs.getAttr("reasoner/engine").type, sn.PREFS["reasoner/engine"][0])
    finally:
      sn.snPrefs["reasoner/engine"] = before
      if not wasDirty:
        sn.snPrefs.setDirty(False)
    self.assertEqual(defaultEngine(), before.value)


if __name__ == "__main__":
  unittest.main()
