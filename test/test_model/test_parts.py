'''
A rule, definition or requirement holds its graphs in parts: plain contexts
it holds by antecedent, consequent, definiendum, definiens, condition or
required relations (SN subtypes of contains), each containing its graph by
plain "contains" relations. The relation's SN type says what the part is to
its box. Files written before there were parts (rule -antecedent-> ?x) are
converted as they're read, keeping each relation (and its id).

Created on Nov 11, 2026

@author: robkremer
'''
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation

class TestParts(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()
    self.m = Model((self.folder / "parts.snm").as_uri())

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def rel(self, typ, src, dst):
    return Relation(self.m, [typ], src, dst, individual=True)

  def box(self, typ, name="box"):
    return Node(self.m, [typ], individual=True, name=name)

  def test_partTypes(self):
    'What a box\'s parts can be, from the SN types of contains relations whose source its SN type is (or an ancestor of it).'
    m = self.m
    names = lambda t: [r.name for r in self.box(t).partTypes()]
    self.assertEqual(names(m.RULE), ["antecedent", "consequent"])
    self.assertEqual(names(m.DEFINITION), ["definiendum", "definiens"])
    self.assertEqual(names(m.REQUIREMENT), ["condition", "required"])
    self.assertEqual(names(m.QUERY), [])
    self.assertEqual(names(m.COLLECTION), [])
    # a box of a new SN type, with a part of its own: eg, a rule with exceptions
    ruleish = Node(m, [m.RULE], name="defeasible rule")
    unless = Relation(m, [m.CONTAINS], ruleish, m.TOP, name="unless")
    self.assertEqual([t.name for t in self.box(ruleish).partTypes()], ["antecedent", "consequent", "unless"])
    self.assertIs(unless.src, ruleish)

  def test_tilesParts(self):
    'A rule, definition and requirement draw their parts side by side, by default; other boxes don\'t.'
    m = self.m
    for t, tiles in ((m.RULE, True), (m.DEFINITION, True), (m.REQUIREMENT, True), (m.QUERY, False),
                     (m.CONSTRAINT, False), (m.CONTEXT, False), (m.COLLECTION, False)):
      self.assertEqual(self.box(t).tilesParts(), tiles, t.name)
    r = self.box(m.RULE)
    r["vis/tileParts"] = False
    self.assertFalse(r.tilesParts())

  def test_partFor(self):
    'A part is a plain context, named for what it is: made once, then found.'
    m = self.m
    r = self.box(m.RULE)
    a = r.partFor(m.ANTECEDENT)
    self.assertIs(r.partFor(m.ANTECEDENT), a)
    self.assertEqual(a.name, "antecedent")
    self.assertEqual(a.getParents(), [m.CONTEXT])
    self.assertTrue(a.isPart())
    self.assertEqual(a.partOwners(), [r])
    c = r.partFor(m.CONSEQUENT)
    self.assertEqual(r.parts(), [a, c])
    self.assertEqual(r.parts(m.CONSEQUENT), [c])
    self.assertEqual([x.partType() for x in r.partRelations()], [m.ANTECEDENT, m.CONSEQUENT])

  def test_whatIsAPart(self):
    'Held by an SN subtype of contains (not plain contains), and a collection that isn\'t a variable.'
    m = self.m
    r = self.box(m.RULE)
    x = Node(m, [m.NODE], individual=True, name="?x")
    v = Node(m, [m.CONTEXT], individual=True, name="?c")
    plain = self.box(m.CONTEXT, "nested")
    self.assertFalse(self.rel(m.ANTECEDENT, r, x).isPartRelation())       # (old shape: what the antecedent holds directly)
    self.assertFalse(self.rel(m.ANTECEDENT, r, v).isPartRelation())       # (a variable over contexts)
    self.assertFalse(self.rel(m.CONTAINS, r, plain).isPartRelation())     # (a box in the box)
    self.assertTrue(self.rel(m.ANTECEDENT, r, self.box(m.CONTEXT, "a")).isPartRelation())
    self.assertEqual(r.parts(), [next(o for o in m.values() if o.name == "a")])

  def test_contentsArePatterns(self):
    'What a part contains is quoted, like what a rule held directly: not facts.'
    m = self.m
    r = self.box(m.RULE)
    a, b = Node(m, [m.NODE], individual=True, name="a"), Node(m, [m.NODE], individual=True, name="b")
    likes = Relation(m, [m.RELATION], m.NODE, m.NODE, name="likes")
    inPart = self.rel(likes, a, b)
    self.rel(m.CONTAINS, r.partFor(m.ANTECEDENT), inPart)
    self.assertTrue(inPart.isPatternElement())
    self.assertFalse(self.rel(likes, b, a).isPatternElement())

  def test_convertToParts(self):
    'What a box holds directly by antecedent, consequent, ... moves into its parts: the same relations (and ids), as "contains".'
    m = self.m
    r = self.box(m.RULE)
    xs = [Node(m, [m.NODE], individual=True, name=n) for n in ("?x", "?y", "?z")]
    old = [self.rel(m.ANTECEDENT, r, xs[0]), self.rel(m.ANTECEDENT, r, xs[1]), self.rel(m.CONSEQUENT, r, xs[2])]
    ids = [o._id for o in old]
    self.assertEqual(m.convertToParts(r), 3)
    a, c = r.parts()
    self.assertEqual([p.name for p in (a, c)], ["antecedent", "consequent"])
    self.assertEqual([o._id for o in old], ids)
    self.assertTrue(all(o.getParents() == [m.CONTAINS] for o in old))
    self.assertEqual([o.src for o in old], [a, a, c])
    self.assertEqual(list(a.getMembers()), xs[:2])
    self.assertEqual(m.convertToParts(r), 0) # (nothing left to move)
    # more held directly later goes into the part there is
    self.rel(m.ANTECEDENT, r, xs[2])
    self.assertEqual(m.convertToParts(r), 1)
    self.assertEqual(r.parts(m.ANTECEDENT), [a])
    self.assertEqual(list(a.getMembers()), xs)

  def test_oldFileConverted(self):
    'A file written before parts reads with its rules\' graphs in parts, marked changed; saved, it reads as is.'
    m = self.m
    r = self.box(m.RULE, "rule")
    d = self.box(m.DEFINITION, "definition")
    x, y = Node(m, [m.NODE], individual=True, name="?x"), Node(m, [m.NODE], individual=True, name="?y")
    self.rel(m.ANTECEDENT, r, x); self.rel(m.CONSEQUENT, r, y)
    self.rel(m.DEFINIENDUM, d, x); self.rel(m.DEFINIENS, d, y)
    url = m.url
    m.save()
    Model._initCache()
    with self.assertLogs("sn.model.model", "WARNING") as logs:
      m2 = Model.getDB(url)
    self.assertTrue(any("moved into parts" in line for line in logs.output), logs.output)
    named = lambda mm, n: next(o for o in mm.values() if o.model is mm and o.name == n)
    r2, d2 = named(m2, "rule"), named(m2, "definition")
    self.assertEqual([p.name for p in r2.parts()], ["antecedent", "consequent"])
    self.assertEqual([p.name for p in d2.parts()], ["definiendum", "definiens"])
    self.assertEqual([o.name for o in r2.parts()[0].getMembers()], ["?x"])
    self.assertTrue(m2.isDirty())
    m2.save()
    Model._initCache()
    with self.assertNoLogs("sn.model.model", "WARNING"):
      m3 = Model.getDB(url)
    self.assertEqual([p.name for p in named(m3, "rule").parts()], ["antecedent", "consequent"])
    self.assertFalse(m3.isDirty())

if __name__ == "__main__":
  unittest.main()
