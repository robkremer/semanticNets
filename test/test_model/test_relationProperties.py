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
Created on Sep 25, 2026

@author: robkremer
'''
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.controller.modelInterface import ModelContext
from util.attribute import Attribute, LOCAL, VAR_DEFAULTED


class Test(unittest.TestCase):
  '''
  The relational properties (symmetric, ...) are LOCAL tags on relation types:
  the key's presence is the tag, they aren't inherited, and individual
  relations take them from their immediate types.
  '''

  @classmethod
  def setUpClass(cls):
    Path("temp_relprops.xml").unlink(missing_ok=True)
    Model._initCache()
    m = cls.m = Model("temp_relprops.xml")
    cls.person  = Node(m, [m.NODE], name="person")
    cls.ann     = Node(m, [cls.person], individual=True, name="ann")
    cls.bob     = Node(m, [cls.person], individual=True, name="bob")
    cls.sibling = Relation(m, [m.RELATION], cls.person, cls.person, name="sibling")
    cls.sibling["symmetric"] = False # the value is ignored: the key is the tag
    cls.brother = Relation(m, [cls.sibling], cls.person, cls.person, name="brother")
    cls.sib1    = Relation(m, [cls.sibling], cls.ann, cls.bob, individual=True)
    cls.bro1    = Relation(m, [cls.brother], cls.bob, cls.ann, individual=True)

  def test0100types(self):
    self.assertTrue(self.sibling.isSymmetric())
    self.assertFalse(self.brother.isSymmetric()) # not inherited
    self.assertFalse(self.sibling.isTransitive())

  def test0200individualsAskTheirTypes(self):
    self.assertTrue(self.sib1.isSymmetric())
    self.assertFalse(self.bro1.isSymmetric())

  def test0300isa(self):
    self.assertTrue(self.m.ISA.isTransitive())
    self.assertTrue(self.m.ISA.isReflexive())
    isaLink = next(r for r,_ in self.ann._getOutgoing() if r.isa(self.m.ISA) and r is not self.m.ISA)
    self.assertTrue(isaLink.isTransitive())

  def test0400removal(self):
    rel = Relation(self.m, [self.m.RELATION], name="temp")
    rel["asymmetric"] = True
    self.assertTrue(rel.isAsymmetric())
    self.assertFalse(rel.isSymmetric())
    del rel["asymmetric"]
    self.assertFalse(rel.isAsymmetric())

  def test0500setAttributeCommandWithRecord(self):
    # the attribute editor hands the controller complete Attribute records
    rel = Relation(self.m, [self.m.RELATION], name="temp2")
    cmd = ModelContext._Set_attribute(rel, "transitive", Attribute(True, bool, LOCAL))
    cmd.do()
    self.assertTrue(rel.isTransitive())
    cmd.undo()
    self.assertFalse(rel.isTransitive())
    cmd = ModelContext._Set_attribute(rel, "note", Attribute("hi", str, VAR_DEFAULTED))
    cmd.do()
    self.assertEqual(rel["note"], "hi")
    cmd.undo()
    self.assertNotIn("note", rel)


if __name__ == "__main__":
  unittest.main()
