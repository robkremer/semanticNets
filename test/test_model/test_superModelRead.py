'''
Reading a model that has a super-model (other than sn): the super-model is read
part-way through reading the model, and that mustn't lose any of the model's
own references (its isa's, its relations' ends).

Created on Oct 6, 2026

@author: robkremer
'''
import unittest
import tempfile
from pathlib import Path
from sn.model.model import Model, Node, Relation


class Test(unittest.TestCase):

  def test0100readWithSuperModel(self):
    with tempfile.TemporaryDirectory() as folder:
      folder = str(Path(folder).resolve()) # (macOS: /var is /private/var)
      basePath, mainPath = str(Path(folder, "base.snm")), str(Path(folder, "main.snm"))
      Model._initCache()
      base = Model(basePath)
      person = Node(base, [base.NODE], name="person")
      hasMother = Relation(base, [base.RELATION], person, person, name="has-mother")
      base.save()
      m = Model(mainPath)
      m.setSuperModels(["base.snm"])
      fred = Node(m, [person], individual=True, name="fred")
      barney = Node(m, [person], individual=True, name="barney")
      Relation(m, [hasMother], barney, fred, individual=True)
      m.save()

      Model._initCache()
      m = Model.getDB(Path(mainPath).as_uri())
      base = Model.getDB(Path(basePath).as_uri())
      self.assertIn(base, m.superDBs)
      person, hasMother = base["person"], base["has-mother"] # type: ignore[assignment]
      fred, barney = m["fred"], m["barney"] # type: ignore[assignment]
      self.assertIn(person, fred.getSupers())
      self.assertIn(person, barney.getSupers())
      [rel] = [o for o in m.values() if isinstance(o, Relation) and o.isIndividual() and o.isa(hasMother)]
      self.assertIs(rel.localSrc, barney)
      self.assertIs(rel.localDst, fred)
      Model._initCache()


if __name__ == "__main__":
  unittest.main()
