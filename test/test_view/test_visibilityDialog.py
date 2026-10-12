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
The order of "hide/erase by category > relation types..." (see
*sn.view.graphics.visibilityDialog.typeTree()*): the part that needs no screen.

Created on Oct 12, 2026

@author: robkremer
'''
import unittest
from sn.model.model import Model, Node, Relation
from sn.view.graphics.visibilityDialog import typeTree


class Test(unittest.TestCase):

  def test0100subtypesUnderTheirTypes(self):
    m = Model("temp_visibilityDialog.xml")
    thing = Node(m, [m.NODE], name="thing")
    rel = lambda name, *parents: Relation(m, list(parents) or [m.RELATION], thing, thing, name=name)
    includes = rel("includes")
    module, defines = rel("contains-module", includes), rel("defines", includes)
    method = rel("defines-method", defines)
    imports = rel("imports")
    tree = [(t.name, d) for t, d in typeTree([method, imports, includes, defines, module])]
    self.assertEqual(tree, [("imports", 0), ("includes", 0), ("contains-module", 1), ("defines", 1), ("defines-method", 2)])
    # a subtype whose supertype isn't offered is at the top
    self.assertEqual([(t.name, d) for t, d in typeTree([method, imports])], [("defines-method", 0), ("imports", 0)])


if __name__ == "__main__":
  unittest.main()
