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
Created on Sep 28, 2026

@author: robkremer
'''
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation, IsaIndividual
from sn.model.clingoReasoner import ClingoReasoner
from sn.model.reasoner import ruleOf

class TestRules(unittest.TestCase):
  '''
  User rules (a rule's antecedent => its consequent), compiled into the
  reasoner. The examples are symmetry and transitivity: first with tags only
  the rules know about ("mirrored", "chained"), so the rules alone give the
  results; then with the built-in tags, where they must agree with the
  built-in reasoning.
  '''

  def setUp(self):
    Path("temp_rules.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    Model._initCache()
    m = self.m = Model("temp_rules.xml")
    self.person = Node(m, [m.NODE], name="person")
    self.likes = Relation(m, [m.RELATION], self.person, self.person, name="likes")
    self.anc = Relation(m, [m.RELATION], self.person, self.person, name="ancestor")
    self.sib = Relation(m, [m.RELATION], self.person, self.person, name="fullSibling")
    for tag in ("symmetric", "transitive", "irreflexive"):
      self.sib[tag] = True
    self.parent = Relation(m, [m.RELATION], self.person, self.person, name="parent")
    self.p = {n: Node(m, [self.person], individual=True, name=n) for n in ("alice", "bob", "carol", "dave", "fred")}

  # ---- helpers ---------------------------------------------------------------

  def rel(self, typ, src, dst):
    return Relation(self.m, [typ], src, dst, individual=True)

  def var(self, name, typ=None):
    return Node(self.m, [typ or self.m.NODE], individual=True, name=name)

  def relVar(self, name, **constraints):
    R = Relation(self.m, [self.m.RELATION], name=name)
    if constraints:
      R["constraints"] = ", ".join(k if v is True else f"{k}: {v}" for k, v in constraints.items())
    return R

  def rule(self, name, antecedent, consequent):
    r = Node(self.m, [self.m.RULE], individual=True, name=name)
    for x in antecedent:
      self.rel(self.m.ANTECEDENT, r, x)
    for x in consequent:
      self.rel(self.m.CONSEQUENT, r, x)
    return r

  def symmetryRule(self, tag, copies=False):
    'B -R-> A :- A -R-> B, R {tag}  (with *copies*: the consequent has its own ?A, ?B, ?R)'
    A, B, R = self.var("?A"), self.var("?B"), self.relVar("^R", **{tag: True})
    if copies:
      A2, B2, R2 = self.var("?A"), self.var("?B"), self.relVar("^R")
    else:
      A2, B2, R2 = A, B, R
    return self.rule(f"{tag} symmetry", [self.rel(R, A, B)], [self.rel(R2, B2, A2)])

  def transitivityRule(self, tag, distinct=False):
    'A -R-> C :- A -R-> B, B -R-> C, R {tag} [, A distinct C]'
    A, B, C, R = self.var("?A"), self.var("?B"), self.var("?C"), self.relVar("^R", **{tag: True})
    ante = [self.rel(R, A, B), self.rel(R, B, C)]
    if distinct:
      ante.append(self.rel(self.m.DISTINCT, A, C))
    return self.rule(f"{tag} transitivity", ante, [self.rel(R, A, C)])

  def reason(self):
    return ClingoReasoner(self.m).run()

  def pairs(self, triples, typ):
    return {(s.name, d.name) for t, s, d in triples if t is typ}

  # ---- tests -----------------------------------------------------------------

  def test0100symmetry(self):
    self.likes["mirrored"] = True
    self.rel(self.likes, self.p["alice"], self.p["bob"])
    r = self.symmetryRule("mirrored")
    res = self.reason()
    self.assertIn((r.name, "likes", "bob", "alice"), {(x.name, t.name, s.name, d.name) for x, t, s, d in res.fired})
    self.assertIn(("bob", "alice"), self.pairs(res.inferred, self.likes)) # (drawn as an inferred relation)
    self.assertEqual([v for v in res.violations if v.code.startswith("rule")], [])

  def test0110symmetryNeedsTheTag(self):
    self.rel(self.likes, self.p["alice"], self.p["bob"]) # likes isn't "mirrored"
    self.symmetryRule("mirrored")
    self.assertEqual(self.reason().fired, [])

  def test0120consequentCopies(self):
    'Variables are the same variable by name: the consequent may have its own ?A, ?B, ?R.'
    self.likes["mirrored"] = True
    self.rel(self.likes, self.p["alice"], self.p["bob"])
    self.symmetryRule("mirrored", copies=True)
    res = self.reason()
    self.assertIn(("bob", "alice"), self.pairs([(t, s, d) for _, t, s, d in res.fired], self.likes))
    self.assertIn(("bob", "alice"), self.pairs(res.inferred, self.likes))

  def test0200transitivity(self):
    self.anc["chained"] = True
    a, b, c, d = (self.p[n] for n in ("alice", "bob", "carol", "dave"))
    self.rel(self.anc, a, b); self.rel(self.anc, b, c); self.rel(self.anc, c, d)
    self.transitivityRule("chained")
    res = self.reason()
    self.assertEqual(self.pairs(res.holds, self.anc),
                     {("alice", "bob"), ("bob", "carol"), ("carol", "dave"),                  # asserted
                      ("alice", "carol"), ("bob", "dave"), ("alice", "dave")})                # concluded (recursively)

  def test0300agreesWithBuiltinSymmetry(self):
    s = self.sib
    self.rel(s, self.p["alice"], self.p["bob"]); self.rel(s, self.p["bob"], self.p["carol"])
    before = self.pairs(self.reason().holds, s)
    self.symmetryRule("symmetric")
    res = self.reason()
    self.assertEqual(self.pairs(res.holds, s), before)                         # nothing the built-in didn't already know
    self.assertEqual(self.pairs([(t, x, y) for _, t, x, y in res.fired], s),   # and the rule concluded each mirror image
                     {(y, x) for x, y in before})                               # (of everything, including its own conclusions)

  def test0310agreesWithBuiltinTransitivity(self):
    'Symmetric + transitive + irreflexive needs "distinct" in the rule, as the built-in has its special case.'
    s = self.sib
    self.rel(s, self.p["alice"], self.p["bob"]); self.rel(s, self.p["bob"], self.p["carol"])
    before = self.pairs(self.reason().holds, s)
    self.transitivityRule("transitive", distinct=True)
    res = self.reason()
    self.assertEqual(self.pairs(res.holds, s), before)
    self.assertTrue(all(x != y for x, y in self.pairs([(t, a, b) for _, t, a, b in res.fired], s)))
    self.assertEqual([v for v in res.violations if v.code == "irreflexive"], [])

  def test0400assertsAttributes(self):
    'A consequent variable\'s constraints are conclusions; queries see them.'
    fred, mary = self.p["fred"], self.p["alice"]
    self.rel(self.parent, fred, mary)
    P, C = self.var("?p"), self.var("?c")
    P2 = self.var("?p"); P2["constraints"] = "isParent"
    r = self.rule("parents", [self.rel(self.parent, P, C)], [P2])
    res = self.reason()
    self.assertEqual({(x.name, k, v) for _, x, k, v in res.ruleAttrs}, {("fred", "isParent", True)})
    q = Node(self.m, [self.m.QUERY], individual=True, name="parents?")
    X = self.var("?x"); X["constraints"] = "isParent"
    self.rel(self.m.CONTAINS, q, X)
    self.assertEqual([row[X] for row in ClingoReasoner(self.m).answer(q)], [fred])

  def test0500problems(self):
    'A rule that concludes something its antecedent doesn\'t bind (other than a new object) is reported, and not used.'
    self.likes["mirrored"] = True
    self.rel(self.likes, self.p["alice"], self.p["bob"])
    A, B = self.var("?A"), self.var("?B")
    Q = self.relVar("^Q")                                                        # a relation type can't be new
    r = self.rule("bad", [self.rel(self.likes, A, B)], [self.rel(Q, B, A)])
    self.assertEqual([c for c, _ in ruleOf(r).problems], ["rule_unbound"])
    res = self.reason()
    self.assertEqual(res.fired, [])
    self.assertEqual([(v.code, v.subject.name) for v in res.violations if v.code.startswith("rule")], [("rule_unbound", "bad")])
    B2 = self.var("?B"); B2["constraints"] = "age: ?a"                                         # nor a value variable
    self.assertIn("rule_unbound", [c for c, _ in ruleOf(self.rule("bad2", [self.rel(self.likes, A, B)], [B2])).problems])
    open_ = self.rule("open", [self.rel(self.likes, A, B)], [Relation(self.m, [self.likes], B, None, individual=True)])
    self.assertIn("rule_open_end", [c for c, _ in ruleOf(open_).problems])

  def test0600concludesIsa(self):
    'An isa link in the consequent: classification, with inheritance and queries following it.'
    m = self.m
    child = Node(m, [m.NODE], name="child"); candy = Node(m, [m.NODE], individual=True, name="candy")
    self.rel(self.likes, child, candy)                               # children like candy (inherited by each child)
    mary = Node(m, [m.NODE], individual=True, name="mary")          # (not a child -- yet)
    self.rel(self.parent, self.p["fred"], mary)
    P, C, C2 = self.var("?p"), self.var("?c"), self.var("?c")
    r = self.rule("children", [self.rel(self.parent, P, C)], [C2, IsaIndividual(m, C2, child)])
    self.assertEqual(ruleOf(r).problems, [])
    res = self.reason()
    self.assertEqual({(x.name, t.name) for _, x, t in res.ruleIsa}, {("mary", "child")})
    self.assertIn((mary, child), res.isa)
    self.assertIn(("mary", "candy"), self.pairs(res.inherited, self.likes))   # inherited through the concluded isa
    q = Node(m, [m.QUERY], individual=True, name="children?"); K = self.var("?k", child)
    self.rel(m.CONTAINS, q, K)
    self.assertEqual([row[K] for row in ClingoReasoner(m).answer(q)], [mary])

  def test0700newObjects(self):
    'A consequent variable the antecedent doesn\'t bind is a new object, one per match -- and rules don\'t chain on them.'
    m = self.m
    mother = Relation(m, [m.RELATION], self.person, self.person, name="mother")
    P, P2, M = self.var("?p", self.person), self.var("?p"), self.var("?m", self.person)
    M["constraints"] = "alive"
    r = self.rule("everyone has a mother", [P], [self.rel(mother, P2, M)])
    self.assertEqual([x.name for x in ruleOf(r).new], ["?m"])
    res = self.reason()                                   # (terminates: a new mother isn't matched as a ?p)
    self.assertEqual(len(res.newObjects), 5)
    self.assertEqual({dict(n.bindings)["?p"].name for n in res.newObjects}, set(self.p))
    self.assertEqual({s.name for _, t, s, d in res.fired}, set(self.p))
    self.assertTrue(all(any(x == n and t is self.person for _, x, t in res.ruleIsa) for n in res.newObjects))
    self.assertEqual(len([1 for _, x, k, v in res.ruleAttrs if k == "alive"]), 5)
    self.assertFalse(any(not hasattr(s, "tostring") or not hasattr(d, "tostring") for _, s, d in res.holds)) # (model objects only)
    self.assertTrue(any("(new ?m for ?p=alice" in line for line in res.ruleConclusions(r)))
    q = Node(m, [m.QUERY], individual=True, name="alive?"); X = self.var("?x", self.person); X["constraints"] = "alive"
    self.rel(m.CONTAINS, q, X)
    self.assertEqual(len(ClingoReasoner(m).answer(q)), 5)  # queries do see them

  def test0710newObjectsInTheModel(self):
    'What a rule concludes exists is put in the model, as inferred nodes, with its types, attributes and relations.'
    from sn.model.reasoner import reason, clearReasoning
    from sn.controller.modelInterface import ModelContext
    m = self.m
    mother = Relation(m, [m.RELATION], self.person, self.person, name="mother")
    P, P2, M = self.var("?p", self.person), self.var("?p"), self.var("?m", self.person)
    M["constraints"] = "alive"
    self.rule("everyone has a mother", [P], [self.rel(mother, P2, M)])
    reason(m)
    nodes = [o for o in m.inferredObjects() if isinstance(o, Node)]
    self.assertEqual(len(nodes), 5)
    alices = [n for n in nodes if n.name == "(m for alice)"]
    self.assertEqual(len(alices), 1)
    am = alices[0]
    self.assertTrue(am.isa(self.person))                                   # its type...
    self.assertIs(am.get("alive", None), True)                             # ... its attributes...
    self.assertIn(am, self.p["alice"].getRelatedTo(mother))                # ... and its relations
    self.assertFalse(am.isVariable())                                      # (not a pattern variable)
    reason(m)
    self.assertEqual({id(o) for o in m.inferredObjects() if isinstance(o, Node)}, {id(n) for n in nodes}) # kept
    rel = next(r for r, o in self.p["alice"]._getOutgoing(lambda r: r.inferred and r.isa(mother)))
    ModelContext(m).mark_asserted(am)                                      # with the relation the rule gave it
    self.assertFalse(am.inferred or rel.inferred)
    reason(m)                                                              # alice has a mother now: no new one...
    names = [o.name for o in m.inferredObjects() if isinstance(o, Node)]
    self.assertNotIn("(m for alice)", names)
    self.assertIn("(m for (m for alice))", names)                          # ... but she's a person: she has one
    clearReasoning(m)
    self.assertEqual([o for o in m.inferredObjects() if isinstance(o, Node)], [])
    self.assertTrue(am._isConnected())                                     # (asserted: stays)

  # ---- definitions (rules both ways) ------------------------------------------

  def definition(self, name, definiendum, definiens):
    d = Node(self.m, [self.m.DEFINITION], individual=True, name=name)
    for x in definiendum:
      self.rel(self.m.DEFINIENDUM, d, x)
    for x in definiens:
      self.rel(self.m.DEFINIENS, d, x)
    return d

  def concluded(self, res, d):
    return {(t.name, s.name, x.name) for r, t, s, x in res.fired if r is d and hasattr(s, "name") and hasattr(x, "name")}

  def test0800brother(self):
    'X -brother-> Y  <=>  X -full-sibling-> Y, Y {gender: male}: brothers from siblings, and siblings (and maleness) from brothers.'
    m, p = self.m, self.p
    brother = Relation(m, [m.RELATION], self.person, self.person, name="brother")
    X, Y = self.var("?X"), self.var("?Y")
    X2, Y2 = self.var("?X"), self.var("?Y"); Y2["constraints"] = "gender: male"
    d = self.definition("brother", [self.rel(brother, X, Y)], [self.rel(self.sib, X2, Y2), Y2])
    self.rel(self.sib, p["alice"], p["bob"]); p["bob"]["gender"] = "male"   # a male sibling...
    self.rel(brother, p["carol"], p["dave"])                                 # ... and an asserted brother
    res = self.reason()
    self.assertEqual([v for v in res.violations if v.code.startswith(("rule", "bad"))], [])
    got = self.concluded(res, d)
    self.assertIn(("brother", "alice", "bob"), got)                           # forward
    self.assertNotIn(("brother", "bob", "alice"), got)                        # (alice isn't male)
    self.assertIn(("fullSibling", "carol", "dave"), got)                      # backward: the relation...
    self.assertIn(("dave", "gender", "male"), {(x.name, k, v) for r, x, k, v in res.ruleAttrs if r is d}) # ... and the constraint
    self.assertIn(("carol", "dave"), self.pairs(res.holds, self.sib))

  def test0805inferredValues(self):
    'Attribute values a rule concludes for the model\'s own objects are inferred attributes: not saved, not read back, given ones win.'
    from sn.model.reasoner import reason, clearReasoning
    from util.attribute import AttributedObject
    m, p = self.m, self.p
    brother = Relation(m, [m.RELATION], self.person, self.person, name="brother")
    X, Y = self.var("?X"), self.var("?Y")
    X2, Y2 = self.var("?X"), self.var("?Y"); Y2["constraints"] = "gender: male"
    self.definition("brother", [self.rel(brother, X, Y)], [self.rel(self.sib, X2, Y2), Y2])
    self.rel(brother, p["carol"], p["dave"])                      # so dave is male
    m.setDirty(False)
    reason(m)
    dave = p["dave"]
    attr = dave.getLocalAttr("gender")
    self.assertTrue(attr is not None and attr.inferred and attr.value == "male")
    self.assertFalse(m.isDirty())                                 # not a change
    saved = next(q for q in AttributedObject.getInstantiationInfo().postconSetters if q.name == "attributes").getter(dave)
    self.assertNotIn("gender", saved)                             # not saved
    reason(m)
    self.assertIs(dave.getLocalAttr("gender"), attr)              # kept (and the reasoner didn't read it as given)
    dave["gender"] = "male"                                       # given now
    self.assertFalse(dave.getLocalAttr("gender").inferred)
    self.assertTrue(m.isDirty())
    reason(m)
    self.assertFalse(dave.getLocalAttr("gender").inferred)        # given beats inferred
    del dave["gender"]
    reason(m)
    clearReasoning(m)
    self.assertIsNone(dave.getLocalAttr("gender"))                # retracted

  def test0810typeDefinition(self):
    'x isa bachelor  <=>  x isa man, x {married: false}: classification both ways.'
    m = self.m
    man = Node(m, [self.person], name="man"); bachelor = Node(m, [self.person], name="bachelor")
    tom = Node(m, [man], individual=True, name="tom"); tom["married"] = False
    ben = Node(m, [bachelor], individual=True, name="ben")
    X = self.var("?x"); X2 = self.var("?x", man); X2["constraints"] = "married: false"
    d = self.definition("bachelor", [X, IsaIndividual(m, X, bachelor)], [X2])
    res = self.reason()
    isas = {(x.name, t.name) for r, x, t in res.ruleIsa if r is d and hasattr(x, "name")}
    self.assertIn(("tom", "bachelor"), isas)                                  # forward
    self.assertIn(("ben", "man"), isas)                                       # backward: its type...
    self.assertIn(("ben", "married", False), {(x.name, k, v) for r, x, k, v in res.ruleAttrs if r is d}) # ... and constraint
    self.assertFalse(any(l.startswith("ben") and "bachelor" in l for l in res.ruleConclusions(d)))  # (asserted: not news)

  def test0820grandparent(self):
    'X -grandparent-> Z  <=>  X -parent-> Y, Y -parent-> Z: an asserted grandparent implies some (new) parent in between.'
    m, p = self.m, self.p
    gp = Relation(m, [m.RELATION], self.person, self.person, name="grandparent")
    X, Z, X2, Y2, Z2 = (self.var(n) for n in ("?X", "?Z", "?X", "?Y", "?Z"))
    d = self.definition("grandparent", [self.rel(gp, X, Z)], [self.rel(self.parent, X2, Y2), self.rel(self.parent, Y2, Z2)])
    self.rel(self.parent, p["fred"], p["dave"]); self.rel(self.parent, p["dave"], p["bob"])
    self.rel(gp, p["alice"], p["carol"])
    res = self.reason()
    self.assertIn(("grandparent", "fred", "bob"), self.concluded(res, d))    # forward
    new = [n for n in res.newObjects if n.rule is d]
    self.assertEqual([(dict(n.bindings)["?X"].name, dict(n.bindings)["?Z"].name) for n in new], [("alice", "carol")])
    links = {(getattr(s, "name", "new"), getattr(x, "name", "new")) for r, t, s, x in res.fired if r is d and t is self.parent}
    self.assertEqual(links, {("alice", "new"), ("new", "carol")})            # backward, through the new parent

  # ---- "any" variables, chaining, constraints, the base rules -------------------

  def test0900anyVariables(self):
    'An "any" variable (!x) matches types as well as individuals; an ordinary one (?x) only one or the other.'
    m = self.m
    self.likes["mirrored"] = True
    cat, dog = Node(m, [m.NODE], name="cat"), Node(m, [m.NODE], name="dog")
    self.rel(self.likes, cat, dog)                                         # between types
    self.rel(self.likes, self.p["alice"], self.p["bob"])                   # between individuals
    self.symmetryRule("mirrored")                                          # ?A, ?B: individuals
    fired = lambda: {(s.name, d.name) for _, t, s, d in self.reason().fired if t is self.likes}
    self.assertEqual(fired(), {("bob", "alice"), ("alice", "bob")})                     # (and mirrored back)
    A, B, R = self.var("!A"), self.var("!B"), self.relVar("^R", mirrored=True)
    self.assertTrue(A.isVariable() and A.isAnyVariable() and not self.var("?C").isAnyVariable())
    self.rule("any symmetry", [self.rel(R, A, B)], [self.rel(R, B, A)])
    self.assertEqual(fired(), {("bob", "alice"), ("alice", "bob"), ("dog", "cat"), ("cat", "dog")})

  def test0905variableKinds(self):
    '''
    A variable's name says what it matches (see sn.model.names): ?x
    individuals, ^T types, !a either -- whether the object is an individual
    or a type. A mismatch (?x as a type, ^T as an individual) is a warning.
    '''
    m = self.m
    self.likes["mirrored"] = True
    cat, dog = Node(m, [m.NODE], name="cat"), Node(m, [m.NODE], name="dog")
    self.rel(self.likes, cat, dog)                                         # between types
    self.rel(self.likes, self.p["alice"], self.p["bob"])                   # between individuals
    fired = lambda: {(s.name, d.name) for _, t, s, d in self.reason().fired if t is self.likes}
    A, B, R = Node(m, [m.NODE], name="^A"), Node(m, [m.NODE], name="^B"), self.relVar("^R", mirrored=True)
    self.assertEqual((A.variableKind().value, self.var("?x").variableKind().value, self.var("!a").variableKind().value,
                      cat.variableKind().value), ("type", "individual", "any", "constant"))
    self.rule("type symmetry", [self.rel(R, A, B)], [self.rel(R, B, A)])
    self.assertEqual(fired(), {("dog", "cat"), ("cat", "dog")})            # (and mirrored back)
    self.assertEqual([v for v in self.reason().violations if v.code == "variable_kind"], [])
    # The name wins: an individual named ^C still matches types -- with a warning; likewise a type named ?D.
    C, D, R2 = self.var("^C"), Node(m, [m.NODE], name="?D"), self.relVar("^R", mirrored=True)
    self.rule("mismatched", [self.rel(R2, C, D)], [self.rel(R2, D, C)])
    self.assertEqual(fired(), {("dog", "cat"), ("cat", "dog")})            # (^C matches types; ?D, individuals: nothing)
    self.assertEqual({(v.subject.name, v.args[0]) for v in self.reason().violations if v.code == "variable_kind"},
                     {("^C", "type"), ("?D", "individual")})

  def test0906nameGrammar(self):
    '''
    The grammar of names is in one place (sn.model.names.NameGrammar.parse()),
    and replaceable: here, Prolog-style -- a capitalized name is an individual
    variable (and the rest is as before: the base rules use it).
    '''
    from sn.model import names
    class Prolog(names.NameGrammar):
      def parse(self, name):
        return (names.NameKind.INDIVIDUAL, name) if name[:1].isupper() else super().parse(name)
    m = self.m
    self.rel(self.likes, self.p["alice"], self.p["bob"])
    names.setGrammar(Prolog())
    try:
      X, Y = self.var("X", self.person), self.var("Y", self.person)
      self.assertTrue(X.isVariable() and not self.p["alice"].isVariable())
      self.rule("liked back", [self.rel(self.likes, X, Y)], [self.rel(self.likes, Y, X)])
      fired = {(s.name, d.name) for _, t, s, d in self.reason().fired if t is self.likes}
      self.assertEqual(fired, {("bob", "alice"), ("alice", "bob")})          # (and back)
    finally:
      names.setGrammar(names.NameGrammar())

  def test0910chainingOnNewObjects(self):
    'A rule that creates nothing matches the objects other rules create (one that creates objects doesn\'t: see test0700).'
    m = self.m
    mother = Relation(m, [m.RELATION], self.person, self.person, name="mother")
    child = Relation(m, [m.RELATION], self.person, self.person, name="child")
    P, P2, M = self.var("?p", self.person), self.var("?p"), self.var("?m", self.person)
    self.rule("everyone has a mother", [P], [self.rel(mother, P2, M)])
    X, Y = self.var("?x"), self.var("?y")
    r = self.rule("a mother's child", [self.rel(mother, X, Y)], [self.rel(child, Y, X)])
    res = self.reason()
    self.assertEqual(len([1 for x, t, s, d in res.fired if x is r and t is child]), 5)
    self.assertEqual(len(res.newObjects), 5)                              # (still terminates)

  def constraint(self, name, pattern, **attrs):
    c = Node(self.m, [self.m.CONSTRAINT], individual=True, name=name)
    for k, v in attrs.items():
      c[k] = v
    for x in pattern:
      self.rel(self.m.CONTAINS, c, x)
    return c

  def test0920constraints(self):
    'A constraint\'s pattern must not match: each match is a violation, as its attributes say.'
    X = self.var("?x")
    c = self.constraint("narcissism", [self.rel(self.likes, X, X)], report="?x", severity="warning",
                        message="{0} likes themselves")
    self.rel(self.likes, self.p["alice"], self.p["alice"])
    self.rel(self.likes, self.p["alice"], self.p["bob"])
    vs = [v for v in self.reason().violations if v.code == "narcissism"]
    self.assertEqual([(v.subject.name, v.severity, v.args) for v in vs], [("alice", "warning", ())])
    self.assertTrue(vs[0].message.endswith("likes themselves"), vs[0].message)
    c["report"] = "?y"                                                     # not one of its variables
    vs = self.reason().violations
    self.assertFalse(any(v.code == "narcissism" for v in vs))
    self.assertTrue(any(v.code == "constraint_report" and v.subject is c for v in vs))

  def test0930systemRules(self):
    'The base rules\' conclusions are plain inferences -- unless showSysRules.'
    self.rel(self.sib, self.p["alice"], self.p["bob"])
    hidden = ClingoReasoner(self.m, showSysRules=False).run()
    shown = ClingoReasoner(self.m, showSysRules=True).run()
    self.assertIn(("bob", "alice"), self.pairs(hidden.inferred, self.sib))
    self.assertEqual(hidden.fired, [])
    self.assertIn(("bob", "alice"), {(s.name, d.name) for r, t, s, d in shown.fired if r.name == "symmetric"})
    self.assertEqual(self.pairs(hidden.holds, self.sib), self.pairs(shown.holds, self.sib))

  def test0940baseRulesSuperModel(self):
    'The base rules are a (locked) super-model of every model -- but can\'t be removed, and aren\'t saved with it.'
    import tempfile
    from sn.model.reasoner import baseRuleModels
    base = baseRuleModels()
    self.assertTrue(base)
    for b in base:
      self.assertIn(b, self.m.superDBs)
      self.assertTrue(b.writeLocked())
      self.assertNotIn(b, b.superDBs)
      self.assertRaises(ValueError, self.m.removeSuperDB, b)
    self.assertEqual(self.m.superModelPaths(), [])
    self.m.setSuperModels([])
    self.assertEqual(self.m.superDBs, self.m.implicitSuperDBs())
    r = ClingoReasoner(self.m)
    self.assertFalse(any(o.model in base for o in r.objects()))           # rules, not data
    self.assertTrue(any(o.model in base for o in r.ruleObjects()))
    with tempfile.TemporaryDirectory() as folder:
      path = str(Path(folder, "m.xml"))
      self.m.save(saveas=path)
      text = Path(path).read_text(encoding="utf-8")
    self.assertNotIn("baseRules", text)
    self.assertIn("sn:/sn.xml", text)

if __name__ == "__main__":
  unittest.main()
