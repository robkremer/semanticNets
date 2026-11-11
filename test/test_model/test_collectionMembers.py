'''
A collection holds its members by "contains" relations, like every box (a
context, eg: a rule, is a collection too): they're saved and read like any
other relations -- in order, whether the members are in the same model or
one it builds on (a super-model), and collections in collections. A member
taken out of its model (eg: deleted) goes with its relation. A file written
while collections kept their members in a list of their own has them made
into "contains" relations when it's read.

Created on Nov 11, 2026

@author: robkremer
'''
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from sn.model.model import Collection, GORef, Model, Node, Relation

class TestCollectionMembers(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def url(self, name:str) -> str:
    return (self.folder / name).as_uri()

  def reread(self, m:Model) -> Model:
    url = m.url
    m.save()
    Model._initCache()
    return Model.getDB(url)

  @staticmethod
  def collection(m:Model, name:str) -> Collection:
    return next(o for o in m.values() if isinstance(o, Collection) and o.model is m and o.name == name)

  def test_membersSaved(self):
    'Nodes, a relation and a collection, in order, read back as the same objects.'
    m = Model(self.url("c.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    b = Node(m, [m.NODE], individual=True, name="b")
    r = Relation(m, [m.RELATION], a, b, individual=True, name="r")
    inner = Collection(m, [m.COLLECTION], [b, a, r], individual=True, name="inner")
    Collection(m, [m.COLLECTION], [inner, a], individual=True, name="outer")
    m2 = self.reread(m)
    inner2, outer2 = self.collection(m2, "inner"), self.collection(m2, "outer")
    self.assertEqual([o.name for o in inner2.getMembers()], ["b", "a", "r"])
    self.assertIsInstance(list(inner2.getMembers())[2], Relation)
    self.assertEqual(list(outer2.getMembers()), [inner2, list(inner2.getMembers())[1]])

  def test_memberInSuperModel(self):
    'A member in a model this one builds on is found there.'
    o = Model(self.url("o.snm"))
    t = Node(o, [o.NODE], name="thing")
    o.save()
    m = Model(self.url("m.snm"))
    m.setSuperModels([o.url])
    x = Node(m, [t], individual=True, name="x")
    Collection(m, [m.COLLECTION], [t, x], individual=True, name="both")
    m2 = self.reread(m)
    members = list(self.collection(m2, "both").getMembers())
    self.assertEqual([str(p.name) for p in members], ["thing", "x"])
    self.assertIs(members[0].model, Model.getDB(o.url))

  def test_deletedMemberNotSaved(self):
    'A member taken out of its model is left out of the file.'
    m = Model(self.url("d.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    b = Node(m, [m.NODE], individual=True, name="b")
    Collection(m, [m.COLLECTION], [a, b], individual=True, name="c")
    b._disconnect()
    m2 = self.reread(m)
    self.assertEqual([o.name for o in self.collection(m2, "c").getMembers()], ["a"])

  def test_membersAreContainsRelations(self):
    'Members are what "contains" relations lead to: added, found, counted and removed through them.'
    m = Model(self.url("r.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    b = Node(m, [m.NODE], individual=True, name="b")
    c = Collection(m, [m.COLLECTION], [a], individual=True, name="c")
    r = c.addMember(b)
    self.assertIsInstance(r, Relation)
    assert r is not None
    self.assertTrue(r.isa(m.CONTAINS) and r.localSrc is c and r.localDst is b)
    self.assertIsNone(c.addMember(b)) # (a member already)
    self.assertEqual(list(c.getMembers()), [a, b])
    self.assertTrue(c.isMember(b) and c.countMembers() == 2)
    c.removeMember(a)
    self.assertEqual(list(c.getMembers()), [b])
    self.assertRaises(ValueError, c.removeMember, a)
    self.assertFalse(r.isPatternElement()) # (a plain collection's contents are facts)

  def test_contextsAreCollections(self):
    'A rule (Python class Node, SN type rule) is a collection: what its antecedent and consequent relations hold are its members.'
    m = Model(self.url("rule.snm"))
    rule = Node(m, [m.RULE], individual=True, name="rule")
    x = Node(m, [m.NODE], individual=True, name="?x")
    y = Node(m, [m.NODE], individual=True, name="?y")
    self.assertTrue(rule.isCollection())
    rule.addMember(x, m.ANTECEDENT)
    rule.addMember(y, m.CONSEQUENT)
    rule.addMember(x, m.CONSEQUENT) # (in both: a member once)
    self.assertEqual(list(rule.getMembers()), [x, y])
    self.assertRaises(TypeError, rule.addMember, x, m.ISA) # (not a containment relation)
    self.assertRaises(TypeError, x.addMember, y) # (not a collection)
    self.assertRaises(TypeError, m.COLLECTION.addMember, y) # (a type: not a box)

  def test_noMemberListWritten(self):
    'A collection\'s members are saved as its relations, not as a list of its own.'
    m = Model(self.url("new.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    Collection(m, [m.COLLECTION], [a], individual=True, name="c")
    m.save()
    self.assertNotIn('key="members"', (self.folder / "new.snm").read_text())

  def test_oldMemberListConverted(self):
    'A file written while collections kept a list of their members reads with them as "contains" relations, marked changed.'
    m = Model(self.url("old.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    b = Node(m, [m.NODE], individual=True, name="b")
    r = Relation(m, [m.RELATION], a, b, individual=True, name="r")
    inner = Collection(m, [m.COLLECTION], [], individual=True, name="inner")
    outer = Collection(m, [m.COLLECTION], [], individual=True, name="outer")
    old = {id(inner): [b, a, r], id(outer): [inner, a]}
    info = Collection.getInstantiationInfo.__func__ # type: ignore[attr-defined]
    def oldInfo(cls):
      ret = info(cls)
      for p in ret.finalSetters:
        if p.name == "members": # (as they were written)
          p.getter = lambda slf: [GORef.formatForURL(x, slf.db) for x in old.get(id(slf), [])] # type: ignore[attr-defined]
      return ret
    with mock.patch.object(Collection, "getInstantiationInfo", classmethod(oldInfo)):
      m.save()
    text = (self.folder / "old.snm").read_text()
    self.assertEqual(text.count('key="members"'), 2)
    Model._initCache()
    with self.assertLogs("sn.model.model", "WARNING") as logs:
      m2 = Model.getDB(m.url)
    self.assertTrue(any('"contains" relations now' in line for line in logs.output), logs.output)
    inner2, outer2 = self.collection(m2, "inner"), self.collection(m2, "outer")
    self.assertEqual([o.name for o in inner2.getMembers()], ["b", "a", "r"])
    self.assertEqual([o.name for o in outer2.getMembers()], ["inner", "a"])
    self.assertTrue(all(r.isa(m2.CONTAINS) for r in inner2._memberRelations()))
    self.assertTrue(m2.isDirty())
    m2.save() # (saved again: as relations)
    Model._initCache()
    m3 = Model.getDB(m.url)
    self.assertNotIn('key="members"', (self.folder / "old.snm").read_text())
    self.assertEqual([o.name for o in self.collection(m3, "inner").getMembers()], ["b", "a", "r"])
    self.assertFalse(m3.isDirty())

if __name__ == "__main__":
  unittest.main()
