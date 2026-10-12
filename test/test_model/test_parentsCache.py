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
The cache of an object's parents (see *GraphObject.getParents()*): it's
used only until relations change, so a change to the isa links shows at once.

Created on Oct 12, 2026

@author: robkremer
'''
import unittest
from sn.model.model import Model, Node, Relation, IsaIndividual


class Test(unittest.TestCase):

  def setUp(self):
    self.m = m = Model("temp_parentsCache.xml")
    self.animal = Node(m, [m.NODE], name="animal")
    self.pet = Node(m, [m.NODE], name="pet")
    self.dog = Node(m, [self.animal], name="dog")

  def names(self, o):
    return [p.name for p in o.getParents()]

  def test0100cachedAndCopied(self):
    self.assertEqual(self.names(self.dog), ["animal"])
    got = self.dog.getParents()
    got.append(self.pet)                                             # (a caller changing what it's given)
    self.assertEqual(self.names(self.dog), ["animal"])

  def test0200addedIsaShows(self):
    self.assertEqual(self.names(self.dog), ["animal"])
    link = IsaIndividual(self.m, self.dog, self.pet)
    self.assertEqual(self.names(self.dog), ["animal", "pet"])
    link._disconnect()                                               # (eg: deleted, undoably)
    self.assertEqual(self.names(self.dog), ["animal"])
    link._reconnect()                                                # (eg: undone)
    self.assertEqual(self.names(self.dog), ["animal", "pet"])

  def test0300changedEndShows(self):
    link = next(r for r, _ in self.dog._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
    self.assertEqual(self.names(self.dog), ["animal"])
    link.dst = self.pet
    self.assertEqual(self.names(self.dog), ["pet"])
    cat = Node(self.m, [self.animal], name="cat")
    self.assertEqual(self.names(cat), ["animal"])
    link.src = cat                                                   # (now cat isa pet, and dog has none of its own)
    self.assertEqual(self.names(cat), ["animal", "pet"])
    self.assertEqual(self.names(self.dog), ["node"])

  def test0400removedParentShows(self):
    self.assertTrue(self.dog.isa(self.animal))
    self.animal._disconnect()                                        # (its isa links go with it)
    self.assertFalse(any(p is self.animal for p in self.dog.getParents()))
    self.animal._reconnect()
    self.assertTrue(self.dog.isa(self.animal))


if __name__ == "__main__":
  unittest.main()
