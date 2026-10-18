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
*removeDuplicateObjects()*: what *util.utils.removeDuplicates()* gives, but by
identity, in linear time -- as *getDescendants()*, *getSupers()* and
*VObject.expandableRelations()* use it.

Created on Oct 17, 2026

@author: robkremer
'''
import random
import unittest
from util.utils import removeDuplicates
from sn.model.model import Model, Node, removeDuplicateObjects


class Test(unittest.TestCase):

  def setUp(self):
    self.m = m = Model("temp_removeDuplicates.xml")
    self.top = Node(m, [m.NODE], name="t0")
    self.a = Node(m, [self.top], name="a")
    self.b = Node(m, [self.top], name="b")
    self.c = Node(m, [self.a, self.b], name="c")                     # (a diamond: t0's descendants reach c twice)
    self.d = Node(m, [self.c], name="d")

  def names(self, x):
    return [self.names(i) for i in x] if isinstance(x, list) else x.name

  def test0100sameAsRemoveDuplicates(self):
    'Lists with repeated objects; nested ones (asTree) with repeated sublists, and equal ones, too.'
    rnd = random.Random(17)
    pool = [self.top, self.a, self.b, self.c, self.d]
    def make(depth):
      ret = []
      for _ in range(rnd.randint(0, 6)):
        if depth and rnd.random() < 0.3:
          sub = make(depth - 1)
          ret.append(sub)
          if rnd.random() < 0.3:
            ret.append(sub if rnd.random() < 0.5 else list(sub))      # (the same sublist again, or an equal one)
        else:
          ret.append(rnd.choice(pool))
      return ret
    for _ in range(500):
      items = make(3)
      self.assertEqual(removeDuplicateObjects(items, asTree=True), removeDuplicates(items, asTree=True), self.names(items))
      flat = make(0)
      self.assertEqual(removeDuplicateObjects(flat), removeDuplicates(flat), self.names(flat))

  def test0200descendants(self):
    self.assertEqual(self.names(self.top.getDescendants()), ["a", "c", "d", "b"])
    self.assertEqual(self.names(self.top.getDescendants(asTree=True)), ["a", ["c", ["d"]], "b"])
    self.assertEqual(self.names(self.top.getDescendants(rmDups=False)), ["a", "c", "d", "b", "c", "d"])
    self.assertEqual(self.names(self.top.getDescendants(asTree=True, rmDups=False)), ["a", ["c", ["d", []]], "b", ["c", ["d", []]]]) # (rmDups=False: leaves' empty lists too)

  def test0300supers(self):
    self.assertEqual(self.names(self.d.getSupers()), ["c", "a", "t0", "node", "top", "b"])
    self.assertEqual(self.names(self.d.getSupers(asTree=True)), ["c", ["a", ["t0", ["node", ["top"]]], "b"]])
    self.assertEqual(self.names(self.d.getSupers(rmDups=False)), ["c", "a", "t0", "node", "top", "b", "t0", "node", "top"])


if __name__ == "__main__":
  unittest.main()
