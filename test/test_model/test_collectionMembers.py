'''
A collection keeps its members when its model is saved and read again: in
order, whether they're in the same model or one it builds on (a super-model),
and collections in collections. A member taken out of its model (eg:
deleted) isn't saved; a file written before collections kept their members
reads as one with none.

Created on Nov 11, 2026

@author: robkremer
'''
import re
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Collection, Model, Node, Relation

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

  def test_oldFileHasNoMembers(self):
    'A file written before collections kept their members reads, with none.'
    m = Model(self.url("old.snm"))
    a = Node(m, [m.NODE], individual=True, name="a")
    Collection(m, [m.COLLECTION], [a], individual=True, name="c")
    m.save()
    path = self.folder / "old.snm"
    text = path.read_text()
    old, n = re.subn(r'\s*<property key="members">.*?</property>', "", text, flags=re.S)
    self.assertEqual(n, 1)
    path.write_text(old)
    Model._initCache()
    m2 = Model.getDB(m.url)
    self.assertEqual(self.collection(m2, "c").countMembers(), 0)
    self.assertTrue(any(o.name == "a" for o in m2.values() if isinstance(o, Node) and o.model is m2))

if __name__ == "__main__":
  unittest.main()
