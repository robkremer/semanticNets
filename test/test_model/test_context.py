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


class Test(unittest.TestCase):
  '''
  Contexts (rules, ...): what a context contains is a pattern, not data.
  '''

  @classmethod
  def setUpClass(cls):
    Path("temp_context.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    Model._initCache()
    m = cls.m = Model("temp_context.xml")
    cls.person = Node(m, [m.NODE], name="person"); cls.head = Node(m, [m.NODE], name="head")
    cls.parent = Relation(m, [m.RELATION], cls.person, cls.person, name="parent")
    cls.child  = Relation(m, [m.RELATION], cls.person, cls.person, name="child")
    cls.has    = Relation(m, [m.RELATION], cls.person, cls.head, name="has")
    Relation(m, [cls.has], cls.person, cls.head, individual=True)           # every person has a head
    # the world
    cls.fred = Node(m, [cls.person], individual=True, name="fred")
    cls.mary = Node(m, [cls.person], individual=True, name="mary")
    cls.real = Relation(m, [cls.parent], cls.fred, cls.mary, individual=True)
    # a rule: ?x -parent-> ?y  =>  ?y -child-> ?x
    cls.rule = Node(m, [m.RULE], name="child-rule")
    cls.x = Node(m, [cls.person], individual=True, name="?x")
    cls.y = Node(m, [cls.person], individual=True, name="?y")
    cls.ante = Relation(m, [cls.parent], cls.x, cls.y, individual=True)
    cls.cons = Relation(m, [cls.child], cls.y, cls.x, individual=True)
    cls.containers = [Relation(m, [m.ANTECEDENT], cls.rule, o, individual=True) for o in (cls.x, cls.y, cls.ante)] + \
                     [Relation(m, [m.CONSEQUENT], cls.rule, o, individual=True) for o in (cls.x, cls.y, cls.cons)]
    # a pattern mentioning a constant: fred -parent-> ?z
    cls.z = Node(m, [cls.person], individual=True, name="?z")
    cls.fredPattern = Relation(m, [cls.parent], cls.fred, cls.z, individual=True)
    Relation(m, [m.ANTECEDENT], cls.rule, cls.fredPattern, individual=True)

  def test0100systemTypes(self):
    m = self.m
    self.assertTrue(m.RULE.isa(m.CONTEXT))
    self.assertTrue(m.ANTECEDENT.isa(m.CONTAINS) and m.CONSEQUENT.isa(m.CONTAINS))
    self.assertIs(m.CONTAINS.domain, m.CONTEXT)
    self.assertIs(m.ANTECEDENT.domain, m.RULE)
    self.assertIs(m.CONSEQUENT.range, m.TOP)

  def test0200patternElements(self):
    isaLink = lambda o: next(r for r, _ in o._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
    for o in (self.x, self.y, self.ante, self.cons, self.fredPattern, isaLink(self.x)):
      self.assertTrue(o.isPatternElement(), o)
    for o in (self.fred, self.mary, self.real, self.rule, self.person, self.parent, isaLink(self.fred), *self.containers):
      self.assertFalse(o.isPatternElement(), o)

  def test0300getRelatedTo(self):
    self.assertEqual(self.fred.getRelatedTo(self.parent), [self.mary])  # not ?z
    self.assertEqual(self.mary.getRelatedFrom(self.parent), [self.fred])
    self.assertIn(self.y, self.x.getRelatedTo(self.parent))           # a variable still sees its pattern

  def test0400reasonerIgnoresPatterns(self):
    r = ClingoReasoner(self.m)
    res = r.run()
    pattern = {id(o) for o in (self.x, self.y, self.z, self.ante, self.cons, self.fredPattern)}
    self.assertFalse([str(v) for v in res.violations if id(v.subject) in pattern])
    # no facts about/with pattern elements -- except the (real) containment relations: "the rule contains ?x"
    containment = lambda t: t[1] is self.rule and (t[0] is self.m.RELATION or t[0].isa(self.m.CONTAINS))
    self.assertFalse([t for t in res.holds if (id(t[1]) in pattern or id(t[2]) in pattern) and not containment(t)])
    self.assertIn(self.x, res.related(self.rule, self.m.ANTECEDENT))       # (those are there)
    self.assertEqual(set(r.instances(self.person)), {self.fred, self.mary})  # ?x etc. aren't instances
    self.assertIn(self.head, r.related(self.fred, self.has))              # inheritance still works for data...
    self.assertNotIn(self.head, res.related(self.x, self.has))           # ...but not onto variables
    self.assertEqual(r.related(self.fred, self.parent), [self.mary])


class TestQueries(unittest.TestCase):
  '''
  Answering queries: a context's pattern matched against the model (and what
  the reasoner infers).
  '''

  @classmethod
  def setUpClass(cls):
    Path("temp_query.xml").unlink(missing_ok=True) # (saved at exit by an earlier run)
    Model._initCache()
    m = cls.m = Model("temp_query.xml")
    cls.person = Node(m, [m.NODE], name="person"); cls.dog = Node(m, [m.NODE], name="dog")
    cls.sib = Relation(m, [m.RELATION], cls.person, cls.person, name="fullSibling")
    for tag in ("symmetric", "transitive", "irreflexive"):
      cls.sib[tag] = True
    cls.parent = Relation(m, [m.RELATION], cls.person, cls.person, name="parent")
    cls.alice, cls.bob, cls.carol, cls.fred, cls.mary = (Node(m, [cls.person], individual=True, name=n)
                                                         for n in ("alice", "bob", "carol", "fred", "mary"))
    cls.rex = Node(m, [cls.dog], individual=True, name="rex")
    Relation(m, [cls.sib], cls.alice, cls.bob, individual=True)
    Relation(m, [cls.sib], cls.bob, cls.carol, individual=True)
    Relation(m, [cls.parent], cls.fred, cls.mary, individual=True)
    cls.reasoner = ClingoReasoner(m)

  def query(self, name:str, *parts):
    '''A query node containing *parts* (relations and/or variables).'''
    q = Node(self.m, [self.m.QUERY], individual=True, name=name)
    for x in parts:
      Relation(self.m, [self.m.CONTAINS], q, x, individual=True)
    return q

  def var(self, name, typ=None):
    return Node(self.m, [typ or self.m.NODE], individual=True, name=name)

  def rows(self, q):
    return [{v.name: x for v, x in row.items()} for row in self.reasoner.answer(q)]

  def test0100hasSibling(self):
    p = self.var("?person", self.person)
    q = self.query("has sibling", Relation(self.m, [self.sib], self.alice, p, individual=True))
    self.assertEqual({r["?person"] for r in self.rows(q)}, {self.bob, self.carol}) # inferred (transitive), not alice herself

  def test0200twoVariables(self):
    a, b = self.var("?a", self.person), self.var("?b", self.person)
    q = self.query("siblings", Relation(self.m, [self.sib], a, b, individual=True))
    pairs = {(r["?a"], r["?b"]) for r in self.rows(q)}
    abc = (self.alice, self.bob, self.carol)
    self.assertEqual(pairs, {(x, y) for x in abc for y in abc if x is not y})

  def test0300yesNo(self):
    yes = self.query("alice-carol", Relation(self.m, [self.sib], self.alice, self.carol, individual=True))
    no = self.query("alice-fred", Relation(self.m, [self.sib], self.alice, self.fred, individual=True))
    self.assertEqual(self.reasoner.answer(yes), [{}])
    self.assertEqual(self.reasoner.answer(no), [])

  def test0400variableType(self):
    x = self.var("?pet", self.dog)
    self.assertEqual([r["?pet"] for r in self.rows(self.query("dogs", x))], [self.rex]) # not the pattern's own variables

  def test0500relationVariable(self):
    r = self.var("?r")
    rel = Relation(self.m, [self.m.RELATION], self.fred, self.mary, individual=True)
    rel.connect()  # (keeps fred/mary)
    q = Node(self.m, [self.m.QUERY], individual=True, name="how related")
    pat = Relation(self.m, [self.m.RELATION], self.fred, self.mary, individual=True)
    # make the pattern relation's type the variable ?r: re-parent its isa link
    from sn.model.model import IsaIndividual
    link = next(x for x, _ in pat._getOutgoing(lambda x: isinstance(x, IsaIndividual)))
    link.dst = r
    Relation(self.m, [self.m.CONTAINS], q, pat, individual=True)
    self.assertIn(self.parent, {row["?r"] for row in self.rows(q)})

  def test0600unterminated(self):
    q = self.query("fred has a child", Relation(self.m, [self.parent], self.fred, None, individual=True))
    self.assertEqual(self.reasoner.answer(q), [{}])
    q2 = self.query("mary has a child", Relation(self.m, [self.parent], self.mary, None, individual=True))
    self.assertEqual(self.reasoner.answer(q2), [])

  def test0700ruleAntecedent(self):
    x, y = self.var("?x", self.person), self.var("?y", self.person)
    rule = Node(self.m, [self.m.RULE], individual=True, name="child rule")
    Relation(self.m, [self.m.ANTECEDENT], rule, Relation(self.m, [self.parent], x, y, individual=True), individual=True)
    Relation(self.m, [self.m.CONSEQUENT], rule, Relation(self.m, [self.sib], y, x, individual=True), individual=True) # (not a condition)
    self.assertEqual(self.rows(rule), [{"?x": self.fred, "?y": self.mary}])

  def test0800command(self):
    from sn.controller.modelInterface import ModelContext
    p = self.var("?kin", self.person)
    self.query("bobsSiblings", Relation(self.m, [self.sib], self.bob, p, individual=True))
    out = ModelContext(self.m).parser.parseLine("answer query bobsSiblings")
    self.assertEqual(sorted(out.splitlines()), sorted(f"?kin = {o.tostring(relativeTo=self.m, format='friendly')}"
                                                      for o in (self.alice, self.carol)))

  def test0900distinct(self):
    m = self.m
    self.assertTrue(m.DISTINCT.isSymmetric() and m.DISTINCT.isIrreflexive())
    tom = Node(m, [self.person], individual=True, name="tom")
    Relation(m, [self.parent], self.fred, tom, individual=True)            # fred's children: mary, tom
    def twoChildren(name, distinct:bool):
      x, c1, c2 = self.var("?x" + name, self.person), self.var("?c1" + name, self.person), self.var("?c2" + name, self.person)
      parts = [Relation(m, [self.parent], x, c1, individual=True), Relation(m, [self.parent], x, c2, individual=True)]
      if distinct:
        parts.append(Relation(m, [m.DISTINCT], c1, c2, individual=True))
      return {(r["?c1" + name], r["?c2" + name]) for r in self.rows(self.query("two children " + name, *parts))}
    self.assertEqual(twoChildren("A", False), {(a, b) for a in (self.mary, tom) for b in (self.mary, tom)})
    self.assertEqual(twoChildren("B", True), {(self.mary, tom), (tom, self.mary)})

  def test1000constraints(self):
    '''A variable's constraints (its "constraints" attribute) constrain what it matches: ?x {key}, ?x {key: value}, ?x {key: ?v}.'''
    m = self.m
    self.alice["age"] = 30; self.bob["age"] = 30; self.carol["age"] = 5
    R = Relation(m, [m.RELATION], name="^R"); R["constraints"] = "symmetric"
    self.assertEqual(R.formatConstraints(), "{symmetric}")
    self.assertEqual({r["^R"] for r in self.rows(self.query("symmetric types", R))}, {self.sib, m.DISTINCT})
    notSym = Relation(m, [m.RELATION], name="^S"); notSym["constraints"] = "symmetric: false, transitive: false"
    self.assertNotIn(self.sib, {r["^S"] for r in self.rows(self.query("not symmetric", notSym))})
    p = self.var("?p", self.person); p["constraints"] = "age"
    self.assertEqual({r["?p"] for r in self.rows(self.query("has an age", p))}, {self.alice, self.bob, self.carol})
    p30 = self.var("?p30", self.person); p30["constraints"] = "age:30"
    self.assertEqual(p30.formatConstraints(), "{age: 30}")
    self.assertEqual({r["?p30"] for r in self.rows(self.query("aged 30", p30))}, {self.alice, self.bob})
    x, y = self.var("?x", self.person), self.var("?y", self.person)
    x["constraints"] = "age: ?a"; y["constraints"] = "age: ?a"
    rows = self.rows(self.query("same age", x, y, Relation(m, [m.DISTINCT], x, y, individual=True)))
    self.assertEqual({(r["?x"], r["?y"]) for r in rows}, {(self.alice, self.bob), (self.bob, self.alice)})
    self.alice["constraints"] = "age: 99"
    self.assertEqual(self.alice.constraints(), {}) # (only variables have constraints)
    bad = self.var("?bad", self.person); bad["constraints"] = "age: 'unterminated"
    self.assertIsNotNone(bad.constraintsError())
    with self.assertRaises(ValueError):
      self.reasoner.answer(self.query("bad", bad))

  def test1100constraintSyntax(self):
    from sn.model.constraints import parseConstraints, formatConstraints, splitWhere, mergeConstraints, PRESENT, ValueVar, ConstraintError
    c = parseConstraints("alive, age: 30, owner: ?o, nick: 'Big, Al', ok: false, ratio: 1.5, colour: dark red, code: '42'")
    self.assertEqual(c, {"alive": PRESENT, "age": 30, "owner": "?o", "nick": "Big, Al", "ok": False, "ratio": 1.5,
                         "colour": "dark red", "code": "42"})
    self.assertIsInstance(c["owner"], ValueVar)
    self.assertNotIsInstance(parseConstraints("x: '?o'")["x"], ValueVar)       # (quoted: text)
    self.assertEqual(parseConstraints(formatConstraints(c)), c)                # (round trip)
    self.assertEqual(formatConstraints(c), "alive, age: 30, owner: ?o, nick: 'Big, Al', ok: false, ratio: 1.5, colour: dark red, code: '42'")
    self.assertEqual(splitWhere("?p :where: alive, age: 30"), ("?p", "alive, age: 30"))
    self.assertEqual(splitWhere("?p"), ("?p", None))
    self.assertEqual(mergeConstraints("alive, age: 30", "age: 31, tall"), "alive, age: 31, tall")
    for bad in ("age:", "age: 'x", ": 3", "a b", "a: 1, a: 2", "a: b: c"):
      with self.assertRaises(ConstraintError, msg=bad):
        parseConstraints(bad)

  def test1110negatedConstraintSyntax(self):
    from sn.model.constraints import parseConstraints, formatConstraints, constraintItems, mergeConstraints, Not, PRESENT, ValueVar, ConstraintError
    c = parseConstraints("gender, not gender: female, not alive, not colour: red, not colour: 'dark blue', not: 3")
    self.assertEqual(c, {"gender": PRESENT, "not gender": ("female",), "not alive": (PRESENT,),
                         "not colour": ("red", "dark blue"), "not": 3})          # ("not" alone is a key)
    self.assertEqual(constraintItems(c), [("gender", PRESENT), ("gender", Not("female")), ("alive", Not(PRESENT)),
                                          ("colour", Not("red")), ("colour", Not("dark blue")), ("not", 3)])
    self.assertEqual(formatConstraints(c), "gender, not gender: female, not alive, not colour: red, not colour: dark blue, not: 3")
    self.assertEqual(parseConstraints(formatConstraints(c)), c)                # (round trip)
    self.assertIsInstance(constraintItems(parseConstraints("not age: ?a"))[0][1].value, ValueVar)
    self.assertNotEqual(Not(1), Not(True))
    self.assertEqual(mergeConstraints("not gender: female", "gender: male"), "not gender: female, gender: male")
    for bad in ("not gender: female, not gender: female", "not a b"):
      with self.assertRaises(ConstraintError, msg=bad):
        parseConstraints(bad)

  def test1200migration(self):
    '''Constraints stored the old way (as a variable's own attributes) are moved into its "constraints" attribute.'''
    from sn.model.constraints import migrateConstraints
    m = self.m
    old = self.var("?old", self.person); old["alive"] = True; old["age"] = 30; old["same"] = "?a"
    msgs = migrateConstraints(m)
    self.assertEqual(len([x for x in msgs if x.startswith("?old")]), 1)
    self.assertEqual(old.getLocal("constraints"), "alive, age: 30, same: ?a")
    self.assertNotIn("age", dict.keys(old))

if __name__ == "__main__":
  unittest.main()
