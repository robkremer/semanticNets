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
*sn.view.graphics.layout.depth()*: the isa-depth that aggressive placement uses
to put a type at its level.

Created on Oct 18, 2026

@author: robkremer
'''
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node
from sn.view.graphics.layout import depth


class Test(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory()
    self.m = Model(str(Path(self.tmp.name)/"depth.xml"))

  def tearDown(self):
    self.tmp.cleanup()

  def test0100chain(self):
    m = self.m
    a = Node(m, [m.NODE], name="a")
    b = Node(m, [a], name="b")
    self.assertEqual(depth(m.TOP), 0)
    self.assertEqual(depth(b), depth(a) + 1)
    self.assertEqual(depth(a), depth(m.NODE) + 1)

  def test0200longestPath(self):
    '''The first parent is shallower than another: the deeper one counts.'''
    m = self.m
    a = Node(m, [m.NODE], name="a")
    b = Node(m, [a], name="b")
    c = Node(m, [b], name="c")
    d = Node(m, [m.NODE, c], name="d")
    self.assertEqual(d.getParents()[0], m.NODE)
    self.assertEqual(depth(d), depth(c) + 1)


if __name__ == "__main__":
  unittest.main()
