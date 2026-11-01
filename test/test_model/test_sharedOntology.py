'''
Models sharing a super-model (eg: an ontology on the web): objects referring
to a model that isn't one of their model's super-models are noticed
(Model.unlistedModels()); a super-model can be replaced by a copy
(Model.replaceSuperModel()) -- and the model's views follow it when they're
read (Model.replacedRef()); a type deleted from it is reported.

Created on Oct 13, 2026

@author: robkremer
'''
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, IsaIndividual


class Test(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.folder = Path(self.tmp.name).resolve()
    base = Model(str(self.folder / "base.snm"))
    self.person = Node(base, [base.NODE], name="person")
    base.save()
    shutil.copy(self.folder / "base.snm", self.folder / "copy.snm")   # (eg: moved to the web)
    self.base = base
    self.m = m = Model(str(self.folder / "main.snm"))
    m.setSuperModels(["base.snm"])
    self.fred = Node(m, [self.person], individual=True, name="fred")

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def isaOf(self, obj):
    return [r for r in obj._outgoing if isinstance(r, IsaIndividual)][0]

  def test0100unlisted(self):
    self.assertEqual(self.m.unlistedModels(), {})
    self.m.removeSuperDB(self.base)
    self.assertEqual(self.m.unlistedModels(), {self.base: 1})

  def test0110droppedStillReferredTo(self):
    'A super-model its objects refer to can\'t just be dropped from the list: nothing changes.'
    with self.assertRaises(ValueError) as cm:
      self.m.setSuperModels([])
    self.assertIn("base.snm", str(cm.exception))
    self.assertIn(self.base, self.m.superDBs)
    self.assertEqual(self.m.unlistedModels(), {})

  def test0120copyInItsPlace(self):
    'A copy listed in its place: the references follow it (as replaceSuperModel()).'
    with self.assertLogs("sn.model.model", level="WARNING"):
      self.m.setSuperModels(["copy.snm"])
    copy = Model.getDB((self.folder / "copy.snm").as_uri())
    self.assertIs(self.isaOf(self.fred).localDst, copy["person"])
    self.assertNotIn(self.base, self.m.superDBs)
    self.assertEqual(self.m.unlistedModels(), {})
    self.assertEqual(self.m.replacedModels, {self.base.url: copy.url})

  def test0200replace(self):
    copy = Model.getDB((self.folder / "copy.snm").as_uri())
    self.assertIsNot(copy, self.base)
    self.assertEqual(self.m.replaceSuperModel(self.base, copy), 1)
    self.assertIs(self.isaOf(self.fred).localDst, copy["person"])
    self.assertIn(copy, self.m.superDBs)
    self.assertNotIn(self.base, self.m.superDBs)
    self.assertEqual(self.m.unlistedModels(), {})
    self.assertEqual(self.m.replacedModels, {self.base.url: copy.url})
    # a view's reference to the old one is taken to be to the new one
    self.assertEqual(self.m.replacedRef(self.base.url + "#256"), copy.url + "#256")
    self.assertEqual(self.m.replacedRef("#12"), "#12")
    # saved and read again: the same
    self.m.save()
    text = (self.folder / "main.snm").read_text(encoding="utf-8")
    Model._initCache()
    m = Model.getDB((self.folder / "main.snm").as_uri())
    self.assertEqual(m.replacedModels, {self.base.url: copy.url})
    self.assertEqual(self.isaOf(m["fred"]).localDst.db.url, copy.url)
    self.assertIn("replacedModels", text[:text.index("</head>")])

  def test0300notACopy(self):
    'Nothing changes if the replacement lacks an object referred to (or it\'s a different one).'
    other = Model(str(self.folder / "other.snm"))
    Node(other, [other.NODE], name="something else")
    with self.assertRaises(ValueError) as cm:
      self.m.replaceSuperModel(self.base, other)
    self.assertIn("person", str(cm.exception))
    self.assertIs(self.isaOf(self.fred).localDst, self.person)
    self.assertEqual(self.m.replacedModels, {})

  def test0300readWithSameNamedCopy(self):
    '''
    A model read whose objects refer to a model that isn't one of its
    super-models (eg: a plugin's copy of an ontology), while one of its
    super-models is a copy of it by the same name: they're made to refer to
    that, and it says so.
    '''
    (self.folder / "web").mkdir()
    shutil.copy(self.folder / "base.snm", self.folder / "web" / "base.snm")
    self.m.save()
    text = (self.folder / "main.snm").read_text(encoding="utf-8")
    text = text.replace('<item value="base.snm" />', '<item value="web/base.snm" />')
    self.assertIn('"base.snm#', text) # (the objects still refer to the other one)
    (self.folder / "main.snm").write_text(text, encoding="utf-8")
    Model._initCache()
    with self.assertLogs("sn.model.model", level="WARNING") as logs:
      m = Model.getDB((self.folder / "main.snm").as_uri())
    web = Model.getDB((self.folder / "web" / "base.snm").as_uri())
    self.assertIs(self.isaOf(m["fred"]).localDst, web["person"])
    self.assertEqual(m.unlistedModels(), {})
    self.assertTrue(m.isDirty())
    self.assertTrue(any("now refer to the same objects" in line for line in logs.output))

  def test0400deletedType(self):
    'A type deleted from the super-model: the object says so (its isa link is left unconnected).'
    self.m.save()
    text = (self.folder / "main.snm").read_text(encoding="utf-8")
    (self.folder / "main.snm").write_text(re.sub(r'base\.snm#\d+', "base.snm#9999", text), encoding="utf-8")
    Model._initCache()
    with self.assertLogs("sn.model.model", level="WARNING"):
      m = Model.getDB((self.folder / "main.snm").as_uri())
    fred = m["fred"]
    self.assertTrue(any("Its type couldn't be found" in str(x) and "#9999" in str(x) for x in fred.validate()))


if __name__ == "__main__":
  unittest.main()
