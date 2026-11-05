'''
A second isa link between the same two objects: refused by the commands
(see *GraphObject.parentProblem()*), and -- from an old file -- listed once
and reported, with an action that removes it.

Created on Nov 4, 2026

@author: robkremer
'''
import unittest
from sn.model.model import Model, Node, IsaIndividual
from sn.controller.modelInterface import ModelContext


class Test(unittest.TestCase):

  def setUp(self):
    self.m = m = Model(f"temp_isaLinks_{self._testMethodName}.xml") # (models are cached by name)
    self.person = Node(m, [m.NODE], name="person")
    self.pet = Node(m, [m.NODE], name="pet")
    self.fred = Node(m, [self.person], individual=True, name="fred")
    self.c = ModelContext(m)

  def tearDown(self):
    Model._initCache()

  def link(self, child, parent) -> IsaIndividual:
    return next(r for r in child._outgoing if isinstance(r, IsaIndividual) and r.localDst is parent)

  def test0100secondRefused(self):
    self.assertIsNotNone(self.fred.parentProblem(self.person))
    self.assertIsNone(self.fred.parentProblem(self.person, except_=self.link(self.fred, self.person)))
    self.assertIsNone(self.fred.parentProblem(self.pet))
    with self.assertRaises(ValueError):
      self.c.new_relation("isa", source=self.fred, destination=self.person)
    self.c.parser.parseLine("assert person fred") # (already: nothing to do -- not an error)
    self.assertEqual(len(self.fred.isaLinksTo(self.person)), 1)

  def test0200moveOntoAParentItHas(self):
    self.c.new_relation("isa", source=self.fred, destination=self.pet)
    toPet = self.link(self.fred, self.pet)
    with self.assertRaises(ValueError):
      self.c.reconnect(toPet, destination=self.person)
    self.c.reconnect(toPet, destination=self.pet) # (its own: fine)
    self.assertIs(toPet.localDst, self.pet)

  def test0300fromAnOldFile(self):
    extra = IsaIndividual(self.m, self.fred, self.person) # (as an old file may have)
    self.assertEqual(self.fred.getParents(), [self.person])
    report = self.fred.validate()
    self.assertTrue(any("more than one isa link" in str(r) for r in report), report)
    remove = [a["remove the extra isa link"] for _, text, a in self.fred._statusReport if "more than one isa link" in text]
    self.assertEqual(len(remove), 1)
    remove[0]()
    self.assertEqual(len(self.fred.isaLinksTo(self.person)), 1)
    self.assertEqual(self.fred.getParents(), [self.person])


if __name__ == "__main__":
  unittest.main()
