'''
Copying a model with its views and super-models, as a unit (sn.model.fileCopies):
what goes, and the copies -- read where they are, with the originals gone --
refer to one another.

Created on Nov 18, 2026

@author: robkremer
'''
import logging
import shutil
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, IsaIndividual
from sn.model.directory import Directory, Folder
from sn.model.fileCopies import FileSet, copyFiles, copyURLs

VIEW = '''<?xml version='1.0' encoding='utf-8'?>
<document>
  <head>
    <property key="format" value="XML3" />
    <property key="type" value="sn.view.graphics.sngView.SNGView" />
    <property key="url" value="{url}" />
    <property key="model" value="family.snm" />
  </head>
  <object type="sn.view.graphics.sngView.SNGView" id="1">
    <property key="nextID" type="int" value="3" />
    <property key="_db">
      <object type="util.persistence.serialize.strdict">
        <property key="1"><object type="sn.view.graphics.vnodes.VNode"><property key="modelObject" type="str" value="#{fred}" /></object></property>
        <property key="2"><object type="sn.view.graphics.vnodes.VNode"><property key="modelObject" type="str" value="{person}" /></object></property>
      </object>
    </property>
  </object>
</document>
'''

class Test(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.root = root = Path(self.tmp.name).resolve()
    (root / "far/away/lib").mkdir(parents=True)
    (root / "a/b/models").mkdir(parents=True)
    onto = Model(str(root / "far/away/lib/onto.snm"))
    person = Node(onto, [onto.NODE], name="person")
    onto.save()
    m = Model(str(root / "a/b/models/family.snm"))
    m.setSuperModels([onto.url]) # (far away: absolute)
    fred = Node(m, [person], individual=True, name="fred")
    m.save()
    self.assertTrue(f'"{onto.url}#' in (root / "a/b/models/family.snm").read_text()) # (absolute)
    (root / "a/b/models/family.snv").write_text(VIEW.format(url=(root / "a/b/models/family.snv").as_uri(),
                                                        fred=fred._id, person=f"{onto.url}#{person._id}"))
    self.personID, self.fredID = person._id, fred._id
    Model._initCache()
    self.directory = Directory()
    list(self.directory.scan([Folder(str(root / "a/b/models"))]))
    self.family = [e for e in self.directory.models() if e.name == "family"][0]

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def test0100whatGoes(self):
    files = FileSet(self.directory, [self.family])
    self.assertEqual([(i.name, i.why, i.needed, i.include) for i in files.items],
                     [("family.snm", "picked", False, True),
                      ("family.snv", 'a view of "family.snm"', False, True),
                      ("onto.snm", 'used by "family.snm"', True, True)])
    self.assertEqual(files.outside(), {})
    files.items[2].include = False
    self.assertEqual(files.outside(), {str(self.root / "far/away/lib/onto.snm"): {"family.snm", "family.snv"}})
    moving = FileSet(self.directory, [self.family], move=True)
    self.assertEqual([i.include for i in moving.items], [True, True, False]) # (what it uses stays, unless ticked)
    view = self.family.views[0]
    self.assertEqual([(i.name, i.why) for i in FileSet(self.directory, [view]).items],
                     [("family.snv", "picked"), ("family.snm", 'the model of "family.snv"'),
                      ("onto.snm", 'used by "family.snv"')])

  def test0200copiesReferToCopies(self):
    files = FileSet(self.directory, [self.family])
    web = self.root / "web"
    copied = copyFiles(files, str(web))
    self.assertEqual(sorted(p.name for p in web.iterdir()), ["family.snm", "family.snv", "onto.snm"])
    self.assertEqual(copyURLs(copied)[(self.root / "a/b/models/family.snm").as_uri()], (web / "family.snm").as_uri())
    shutil.rmtree(self.root / "a")
    shutil.rmtree(self.root / "far") # (only the copies are left)
    logger = logging.getLogger("util.persistence.pRef")
    with self.assertNoLogs(logger, level="WARNING"): # (eg: "... was copied or moved from ...")
      m = Model.getDB((web / "family.snm").as_uri())
    onto = Model.getDB((web / "onto.snm").as_uri())
    self.assertIn(onto, m.superDBs)
    isa = [r for r in m["fred"]._outgoing if isinstance(r, IsaIndividual)][0]
    self.assertIs(isa.localDst, onto["person"])
    self.assertEqual(m.previousURL, (self.root / "a/b/models/family.snm").as_uri())
    view = (web / "family.snv").read_text()
    self.assertIn('<property key="model" value="family.snm" />', view)
    self.assertIn(f'value="onto.snm#{self.personID}"', view)

  def test0300servedFrom(self):
    files = FileSet(self.directory, [self.family])
    copyFiles(files, str(self.root / "web"), servedFrom="https://example.org/models/")
    text = (self.root / "web/family.snm").read_text()
    self.assertIn('<property key="url" value="https://example.org/models/family.snm" />', text)
    self.assertIn('<item value="onto.snm" />', text)
    self.assertNotIn(str(self.root), text.replace((self.root / "a/b/models/family.snm").as_uri(), "")) # (only where it came from)


if __name__ == "__main__":
  unittest.main()
