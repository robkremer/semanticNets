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
The choices and filters behind "expand by relation..." (see
*sn.view.graphics.expandDialog*): the parts that need no screen.

Created on Oct 10, 2026

@author: robkremer
'''
import unittest
from types import SimpleNamespace
from sn.model.model import Model, Node, Relation
from sn.view.graphics.expandDialog import relationChoices, choiceFilter, OUT, IN, BOTH


class Test(unittest.TestCase):

  def setUp(self):
    self.m = m = Model("temp_expandDialog.xml")
    self.person = Node(m, [m.NODE], name="person")
    self.parent = Relation(m, [m.RELATION], self.person, self.person, name="has-parent")
    self.father = Relation(m, [self.parent], self.person, self.person, name="has-father")
    self.mother = Relation(m, [self.parent], self.person, self.person, name="has-mother")
    self.sibling = Relation(m, [m.RELATION], self.person, self.person, name="has-sibling")
    self.sibling["symmetric"] = True
    p = lambda n: Node(m, [self.person], individual=True, name=n)
    self.edna, self.fred, self.wilma, self.tex, self.kid = p("edna"), p("fred"), p("wilma"), p("tex"), p("kid")
    rel = lambda t, s, d: Relation(m, [t], s, d, individual=True)
    self.rels = [rel(self.father, self.edna, self.fred), rel(self.mother, self.edna, self.wilma),
                 rel(self.sibling, self.edna, self.tex), rel(self.mother, self.kid, self.edna)]

  def tearDown(self):
    Model._initCache()

  def labels(self):
    return {(c.type.name, c.direction): c.count for c in relationChoices(self.edna, self.rels)}

  def test0100choices(self):
    'Each type each way round, with counts; a supertype two of them share; a symmetric type once.'
    got = self.labels()
    self.assertEqual(got[("has-father", OUT)], 1)
    self.assertEqual(got[("has-mother", OUT)], 1)          # (her mother)
    self.assertEqual(got[("has-mother", IN)], 1)           # (her child's)
    self.assertEqual(got[("has-parent", OUT)], 2)          # (has-father and has-mother: both kinds of parent)
    self.assertNotIn(("has-parent", IN), got)              # (only one type that way: no need)
    self.assertEqual(got[("has-sibling", BOTH)], 1)
    self.assertNotIn(("relation", OUT), got)               # (not the system's relation)

  def test0200filters(self):
    vo = SimpleNamespace(modelObject=self.edna)
    choices = {(c.type.name, c.direction): c for c in relationChoices(self.edna, self.rels)}
    follows = lambda f: {r.getParents()[0].name + ("<" if r.localDst is self.edna else ">") for r in self.rels if f(vo, r)}
    self.assertEqual(follows(choiceFilter("chosen", [choices[("has-parent", OUT)]])), {"has-father>", "has-mother>"})
    self.assertEqual(follows(choiceFilter("chosen", [choices[("has-mother", IN)]])), {"has-mother<"})
    self.assertEqual(follows(choiceFilter("all outgoing", [])), {"has-father>", "has-mother>", "has-sibling>"}) # (symmetric: both ways)
    self.assertEqual(follows(choiceFilter("all incoming", [])), {"has-mother<", "has-sibling>"})
    self.assertEqual(len(follows(choiceFilter("all", []))), 4)

  def test0300hidden(self):
    'Relations in a hidden category are choices too, counted as hidden; a chosen type is followed even so.'
    isas = [r for r in self.edna._outgoing if type(r).__name__ == "IsaIndividual"] # (edna isa person)
    rels = self.rels + isas
    choices = {(c.type.name, c.direction): c for c in relationChoices(self.edna, rels, hidden=lambda r: type(r).__name__ == "IsaIndividual")}
    isa = choices[("isa", OUT)]
    self.assertEqual((isa.count, isa.hidden), (1, 1))
    self.assertIn("hidden", isa.label())
    self.assertEqual(choices[("has-father", OUT)].hidden, 0)
    self.assertTrue(getattr(choiceFilter("chosen", [isa]), "showsHidden", False))
    self.assertFalse(getattr(choiceFilter("all", []), "showsHidden", False))     # (all: categories still apply)


if __name__ == "__main__":
  unittest.main()
