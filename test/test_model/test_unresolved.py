'''
Reading a model with references to objects in other models that can't be
followed -- there's no model at the URL, or it has no such object: each is
reported, plainly, when the model's read.

Created on Oct 13, 2026

@author: robkremer
'''
import re
import unittest
import tempfile
from pathlib import Path
from sn.model.model import Model, Node, IsaIndividual


class Test(unittest.TestCase):
  '''References to objects in other models that can't be followed: reported plainly when a model's read.'''

  def test0100reported(self):
    with tempfile.TemporaryDirectory() as folder:
      basePath, mainPath = str(Path(folder, "base.snm")), str(Path(folder, "main.snm"))
      base = Model(basePath)
      person = Node(base, [base.NODE], name="person")
      base.save()
      m = Model(mainPath)
      m.setSuperModels(["base.snm"])
      Node(m, [person], individual=True, name="fred")
      m.save()
      text = Path(mainPath).read_text(encoding="utf-8")
      self.assertIn("base.snm#", text)
      cases = (("gone.snm#", 'there\'s no model at'), (None, "has no object #9999"))
      for replacement, expected in cases:
        Model._initCache()
        if replacement is None: # (the model's there, but not the object)
          broken = re.sub(r'base\.snm#\d+', "base.snm#9999", text)
        else:
          broken = text.replace("base.snm#", replacement)
        Path(mainPath).write_text(broken, encoding="utf-8")
        with self.assertLogs("sn.model.model", level="WARNING") as logs:
          m = Model.getDB(Path(mainPath).as_uri())
        message = "\n".join(logs.output)
        self.assertIn("couldn't be followed", message)
        self.assertIn("fred isa \u2192", message)
        self.assertIn(expected, message)
        fred = m["fred"]
        [isa] = [r for r in fred._outgoing if isinstance(r, IsaIndividual)]
        self.assertIsNone(isa.localDst)
        self.assertTrue(any(expected in str(x) for x in isa.statusReport()))
      Model._initCache()


if __name__ == "__main__":
  unittest.main()
