'''
Created on Apr 30, 2026

@author: robkremer
'''
import unittest
from util.persistence.pRef import PRDb
from sn.model.model import GraphObject, Model, Node, Relation
from util.attribute import NOVALUE
from pathlib import Path


class Test(unittest.TestCase):


  def setUp(self):
    pass


  def tearDown(self):
    pass


  def test0000ModelBase(self):
    Path("temp.xml").unlink(missing_ok=True)
    Model._initCache()
    
    model:Model = Model("temp.xml")
    self.assertIsInstance(model, Model)
    self.assertEqual(model.RELATION.getSupers(), [model.TOP])
    self.assertEqual(model.NODE.getSupers(), [model.TOP])
    self.assertEqual(model.TOP.getSupers(), [])
    self.assertEqual(set(model.ISA.getSupers()), set([model.TRANSITIVE, model.RELATION, model.TOP, model.REFLEXIVE]))
    self.assertEqual(model.ISA.getSupers(asTree=True), [model.REFLEXIVE, [model.RELATION, [model.TOP]], model.TRANSITIVE])
    self.assertEqual(model.ISA.isa(asTree=True), [model.ISA, [model.REFLEXIVE, [model.RELATION, [model.TOP]], model.TRANSITIVE]])
    self.assertEqual(model.ISA.name, "isa")
    self.assertEqual(list(model.ISA._getOutgoing())[0][0].name, "isa")

  def test0100nodes(self):
    model = Model.getDB("temp.xml") # already in memory from the first test
    person = Node(model, [model.NODE], name="person")
    fred = Node(model, [person], individual=True)
    self.assertEqual(fred.getSupers(), [person, model.NODE, model.TOP])
    self.assertEqual(fred.name, "<name not set>")
    fred["name"] = "fred"
    self.assertEqual(fred.name, "fred")
    self.assertTrue(model["fred"])
    
  def test0200disconnect(self):
    model = Model.getDB("temp.xml") # already in memory from the first test
    fred:Node = model["fred"]
    self.assertFalse(fred.validate())
    person:Node = model["person"]
    self.assertFalse(person.validate())
    self.assertIs(model["fred"], fred)
    self.assertTrue(fred.isa(person))
    self.assertEqual(person.getChildren(), [fred])
    fred._disconnect()
    with self.assertRaises(KeyError):
      model["fred"]
    fred._reconnect()
    self.assertIs(model["fred"], fred)
    self.assertTrue(fred.isa(person))
    self.assertEqual(person.getChildren(), [fred])
    self.assertFalse(fred.validate())
    self.assertFalse(person.validate())
    self.assertFalse(model.validate())
    
  def test0300relations(self):
    sn = Model.getDB("$sn")
    # node <: top,node by getRelatedTo, isRelatedTo
    self.assertEqual(set(sn.NODE.getRelatedTo(sn.ISA)), set((sn.TOP, sn.NODE)))
    self.assertEqual(set(sn.NODE.isRelatedTo (sn.ISA)), set((sn.TOP, sn.NODE)))
    self.assertTrue(sn.NODE.isRelatedTo (sn.ISA, sn.TOP))
    self.assertTrue(sn.NODE.isRelatedTo (sn.ISA, sn.NODE))
    self.assertEqual(set(sn.NODE.isa()), set((sn.TOP, sn.NODE)))
    self.assertTrue(sn.NODE.isa(sn.TOP))
    # equality <: transitive,reflexive,symmetric,relation,top by getRelatedTo, isRelatedTo
    self.assertEqual(set(sn.EQUALITY.getRelatedTo(sn.ISA)), set((sn.EQUALITY,sn.TRANSITIVE,sn.REFLEXIVE,sn.SYMMETRIC,sn.RELATION,sn.TOP)))
    self.assertEqual(set(sn.EQUALITY.isRelatedTo (sn.ISA)), set((sn.EQUALITY,sn.TRANSITIVE,sn.REFLEXIVE,sn.SYMMETRIC,sn.RELATION,sn.TOP)))
    self.assertTrue(sn.EQUALITY.isRelatedTo (sn.ISA, sn.SYMMETRIC))
    self.assertFalse(sn.EQUALITY.isRelatedTo (sn.ISA, sn.NODE))
    self.assertEqual(set(sn.EQUALITY.isa()), set((sn.EQUALITY,sn.TRANSITIVE,sn.REFLEXIVE,sn.SYMMETRIC,sn.RELATION,sn.TOP)))
    self.assertTrue(sn.EQUALITY.isa(sn.RELATION))
    # isRelatedFrom, getRelatedFrom
    self.assertTrue(sn.TOP.isRelatedFrom(sn.ISA, sn.NODE))
    self.assertTrue(sn.TOP.isRelatedFrom(sn.ISA, sn.RELATION))
    self.assertTrue(sn.TOP.isRelatedFrom(sn.ISA, sn.TRANSITIVE))
    self.assertTrue(sn.TOP.isRelatedFrom(sn.ISA, sn.EQUALITY))
    self.assertEqual(set(sn.RELATION.isRelatedFrom(sn.ISA)), set((sn.TRANSITIVE, sn.SYMMETRIC, sn.REFLEXIVE, sn.IRREFLEXIVE, sn.EQUALITY, sn.ISA)))
    

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testModel']
    unittest.main()