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
Cut, copy and paste (see *sn.model.copying*, *ModelContext.copy()*,
*cut()* and *paste()*). Nothing here is saved.

Created on Oct 8, 2026

@author: robkremer
'''
import unittest
from sn.model.model import Model, Node, Relation, IsaIndividual
from sn.model import copying
from sn.controller.modelInterface import ModelContext


class Test(unittest.TestCase):

  def setUp(self):
    self.m = m = Model("temp_copyPaste.xml")
    self.person = Node(m, [m.NODE], name="person")
    self.brother = Relation(m, [m.RELATION], self.person, self.person, name="has-brother")
    self.sister = Relation(m, [m.RELATION], self.person, self.person, name="has-sister")
    # the brother rule: ?x -has-brother-> ?y => ?y -has-brother-> ?x (as it'd be drawn: each pane its own variables)
    self.rule = Node(m, [m.RULE], individual=True, name="brother rule")
    def var(name:str, pane:Relation) -> Node:
      v = Node(m, [self.person], individual=True, name=name)
      Relation(m, [pane], self.rule, v, individual=True)
      return v
    x, y = var("?x", m.ANTECEDENT), var("?y", m.ANTECEDENT)
    self.ante = Relation(m, [self.brother], x, y, individual=True)
    Relation(m, [m.ANTECEDENT], self.rule, self.ante, individual=True)
    x2, y2 = var("?x", m.CONSEQUENT), var("?y", m.CONSEQUENT)
    self.cons = Relation(m, [self.brother], y2, x2, individual=True)
    Relation(m, [m.CONSEQUENT], self.rule, self.cons, individual=True)
    self.rule["note"] = "a note"
    self.fred = Node(m, [self.person], individual=True, name="fred")
    self.c = ModelContext(m)
    copying.clipboard = None

  def tearDown(self):
    copying.clipboard = None
    Model._initCache()

  def contentsOf(self, rule):
    return [o for o in copying.contents(rule) if not isinstance(o, Relation) or not o.isa(self.m.CONTAINS)]

  def test0100copyRule(self):
    m, c = self.m, self.c
    before = set(m.keys())
    c.copy([self.rule])
    made = c.paste()
    new = set(m.keys()) - before
    self.assertEqual(len(made), len(copying.clipboard.entries))
    self.assertEqual({o.id for o in made}, new)                  # all new ids
    rule2 = made[0]
    self.assertIsNot(rule2, self.rule)
    self.assertEqual(rule2.name, "brother rule")
    self.assertEqual(rule2.getLocal("note"), "a note")
    self.assertTrue(rule2.isa(m.RULE) and rule2.isIndividual())
    old, cpy = self.contentsOf(self.rule), self.contentsOf(rule2)
    self.assertEqual(len(old), len(cpy))
    self.assertFalse(any(a is b for a in old for b in cpy))      # the contents are copies
    rels = [o for o in cpy if isinstance(o, Relation)]
    self.assertEqual(len(rels), 2)
    for r in rels:
      self.assertTrue(r.isa(self.brother))                       # the same (uncopied) type
      self.assertIn(r.src, cpy)                                  # ends: the copies
      self.assertIn(r.dst, cpy)
    self.assertEqual(sorted(o.name for o in cpy), sorted(o.name for o in old))
    self.assertEqual(rule2.model, m)

  def test0200modifyTheCopy(self): # (the use case: copy the brother rule, make it a sister rule)
    c = self.c
    c.copy([self.rule])
    rule2 = c.paste()[0]
    rel = [o for o in self.contentsOf(rule2) if isinstance(o, Relation)][0]
    isa = [r for r in rel._outgoing if isinstance(r, IsaIndividual)][0]
    c.reconnect(isa, destination=self.sister)
    self.assertTrue(rel.isa(self.sister))
    self.assertFalse(self.ante.isa(self.sister))                 # the original's untouched
    self.assertTrue(self.ante.isa(self.brother))

  def test0300undoRedo(self):
    m, c = self.m, self.c
    before = set(m.keys())
    c.copy([self.rule])
    made = c.paste()
    after = set(m.keys())
    c.undo()
    self.assertEqual(set(m.keys()), before)
    c.redo()
    self.assertEqual(set(m.keys()), after)
    self.assertTrue(all(o._isConnected() for o in made))
    self.assertEqual(len(self.contentsOf(made[0])), len(self.contentsOf(self.rule)))

  def test0400pasteTwice(self):
    m, c = self.m, self.c
    c.copy([self.fred])
    a, b = c.paste()[0], c.paste()[0]
    self.assertIsNot(a, b)
    self.assertEqual(a.name, "fred")
    self.assertEqual(a.getParents(), [self.person])

  def test0500snapshot(self): # (what's pasted is what was copied)
    c = self.c
    c.copy([self.fred])
    self.fred["name"] = "frederick"
    self.assertEqual(c.paste()[0].name, "fred")

  def test0600sharedEnds(self): # (a relation copied without its ends relates the same objects)
    m, c = self.m, self.c
    alice = Node(m, [self.person], individual=True, name="alice")
    r = Relation(m, [self.sister], self.fred, alice, individual=True)
    c.copy([r])
    r2 = c.paste()[0]
    self.assertIsNot(r2, r)
    self.assertIs(r2.src, self.fred)
    self.assertIs(r2.dst, alice)
    self.assertTrue(r2.isa(self.sister))

  def test0700cut(self):
    m, c = self.m, self.c
    before = set(m.keys())
    c.cut([self.rule])
    self.assertFalse(self.rule._isConnected())
    self.assertFalse(self.ante._isConnected())                  # its contents go too
    self.assertTrue(self.fred._isConnected())
    c.undo()
    self.assertEqual(set(m.keys()), before)
    c.redo()
    rule2 = c.paste()[0]                                         # (the clipboard has it)
    self.assertEqual(rule2.name, "brother rule")
    self.assertEqual(len(self.contentsOf(rule2)), 6)

  def test0800crossModel(self):
    c = self.c
    c.copy([self.fred])
    other = Model("temp_copyPaste2.xml")
    with self.assertRaises(ValueError) as cm:                    # (other doesn't build on m: fred's type isn't there)
      c.paste(model=other)
    self.assertIn("doesn't build on", str(cm.exception))
    sub = Model("temp_copyPaste3.xml")
    sub.setSuperModels([self.m.url])
    fred2 = c.paste(model=sub)[0]                                # (sub does)
    self.assertIs(fred2.model, sub)
    self.assertTrue(fred2.isa(self.person))

  def test0900nothing(self):
    with self.assertRaises(ValueError):
      self.c.paste()

  def test1000removedReference(self):
    c = self.c
    c.copy([self.fred])
    c.remove(self.person)
    with self.assertRaises(ValueError) as cm:
      c.paste()
    self.assertIn("removed", str(cm.exception))


if __name__ == "__main__":
  unittest.main()
