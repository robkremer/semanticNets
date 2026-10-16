#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
Commands as typed at the terminal: *new node*, *new relation* and *query*.

Created on Oct 15, 2026

@author: robkremer
'''
import io
import unittest
from contextlib import redirect_stdout
from sn.model.model import Model, Node, Relation
from sn.controller.modelInterface import ModelContext
from util.persistence.pRef import DuplicateNameError


class Test(unittest.TestCase):

  def setUp(self):
    self.m = Model(f"temp_terminalCommands_{self._testMethodName}.xml") # (models are cached by name)
    self.c = ModelContext(self.m)
    self.line = self.c.parser.parseLine

  def tearDown(self):
    from sn.model.reasoner import clearReasoning
    clearReasoning(self.m)

  def test0100newNode(self):
    animal = self.line("new node node --type --name animal")
    self.assertIsInstance(animal, Node)
    self.assertTrue(animal.isType())
    self.assertEqual(animal.getParents(), [self.m.NODE])
    pet = self.line("new node node --type --name pet")
    dog = self.line("new node animal pet --type --name dog") # several parents
    self.assertEqual(dog.getParents(), [animal, pet])
    fido = self.line("new node dog --name fido")
    self.assertTrue(fido.isIndividual())
    self.assertTrue(self.line("query animal fido"))
    self.line("undo")
    with self.assertRaises(Exception):
      self.line("query fido")

  def test0200newNodeBadParent(self):
    with self.assertRaisesRegex(ValueError, 'no object "nosuch"'):
      self.line("new node nosuch --name x")
    with self.assertRaisesRegex(ValueError, "must be a node"):
      self.line("new node relation --name x")

  def test0300newRelation(self):
    self.line("new node node --type --name person")
    fred = self.line("new node person --name fred")
    mary = self.line("new node person --name mary")
    likes = self.line("new relation relation --type --name likes")
    self.assertIsInstance(likes, Relation)
    self.assertTrue(likes.isType())
    r = self.line("new relation likes --source fred --destination mary")
    self.assertTrue(r.isIndividual())
    self.assertIs(r.src, fred)
    self.assertIs(r.dst, mary)
    self.assertEqual(self.line("query fred likes ?"), [mary])
    with self.assertRaisesRegex(ValueError, "must be a relation"):
      self.line("new relation fred")
    with self.assertRaisesRegex(ValueError, 'no object "nosuch"'):
      self.line("new relation nosuch")

  def test0400queryPrintsNothing(self):
    self.line("new node node --type --name person")
    self.line("new node person --type --name person") # a duplicate name: the lookup used to print the whole model
    out = io.StringIO()
    with redirect_stdout(out):
      try:
        self.line("query ? isa person")
      except Exception:
        pass
      self.line("query node *")
    self.assertEqual(out.getvalue(), "")

  def test0500transitiveQueryAfterReasoning(self):
    from sn.model.reasoner import reason
    for line in ("new node node --type --name person",
                 "new relation relation --type --name has-ancestor",
                 "set attribute has-ancestor transitive yes",
                 "new relation has-ancestor --type --name has-parent"):
      self.line(line)
    bob, alice, carol, dave = (self.line(f"new node person --name {n}") for n in ("bob", "alice", "carol", "dave"))
    for src, dst in (("alice", "bob"), ("carol", "alice"), ("dave", "carol")):
      self.line(f"new relation has-parent --source {src} --destination {dst}")
    self.assertEqual(self.line("query dave has-ancestor ?"), [carol, alice, bob]) # (has-parents are has-ancestors, which chain)
    self.assertEqual(self.line("query dave has-parent ?"), [carol]) # (has-parent itself isn't transitive)
    reason(self.m, "clingo")
    self.assertCountEqual(self.line("query dave has-ancestor ?"), [carol, alice, bob]) # (not the types, nor twice)
    self.assertEqual(self.line("query dave has-parent ?"), [carol])
    self.assertCountEqual(self.line("query ? has-ancestor bob"), [alice, carol, dave])
    self.assertTrue(self.line("query dave has-ancestor bob"))

  def test0600transitiveQuery(self):
    for line in ("new node node --type --name person",
                 "new relation relation --type --name has-ancestor",
                 "set attribute has-ancestor transitive yes",
                 "new relation has-ancestor --type --name has-parent"):
      self.line(line)
    bob, alice, carol, dave = (self.line(f"new node person --name {n}") for n in ("bob", "alice", "carol", "dave"))
    for src, dst in (("alice", "bob"), ("carol", "alice")):
      self.line(f"new relation has-parent --source {src} --destination {dst}")
    self.line("new relation has-ancestor --source dave --destination carol")
    # (has-ancestor is transitive: it goes on through has-parents, as they're has-ancestors, but not through isa)
    self.assertEqual(self.line("query dave has-ancestor ?"), [carol, alice, bob])
    self.assertCountEqual(self.line("query ? has-ancestor bob"), [alice, carol, dave])

  def _searchModel(self) -> tuple:
    self.line("new node node --type --name person")
    fred = self.line("new node person --name fred")
    alfred = self.line('new node person --name "Alfred the Great"')
    parent = self.line("new relation relation --type --name has-parent")
    r = self.line('new relation has-parent --source fred --destination "Alfred the Great"')
    return fred, alfred, parent, r

  def test0700modelSearch(self):
    fred, alfred, parent, r = self._searchModel()
    m = self.m
    self.assertEqual(m.search("fred"), [fred, alfred])
    self.assertEqual(m.search("fred", wholeWord=True), [fred])
    self.assertEqual(m.search("Fred", matchCase=True), [])
    self.assertEqual(m.search("FRED", wholeWord=True), [fred])
    self.assertEqual(m.search("parent", wholeWord=True), [parent, r]) # ("-" separates words)
    self.assertEqual(m.search("^(fred|alfred)", regex=True), [fred, alfred])
    self.assertEqual(m.search("isa"), []) # (not isa links)
    self.assertEqual(m.search("^contains$", regex=True), [])
    self.assertEqual([o.name for o in m.search("^contains$", regex=True, superModels=True)][:1], ["contains"])
    with self.assertRaises(Exception):
      m.search("(", regex=True)

  def test0800searchCommand(self):
    self._searchModel()
    out = self.line("search fred")
    self.assertIn("Nodes (2):", out)
    self.assertNotIn("Relations", out)
    self.assertIn('"Alfred the Great"#', out)
    out = self.line("find parent -w")
    self.assertIn("Relations (2):", out)
    self.assertIn("fred#", out.splitlines()[-1]) # (a relation shows its ends)
    self.assertIn("Nothing", self.line("search Fred --match-case"))
    self.assertIn("Relations", self.line("search ^contains$ -r -s"))
    with self.assertRaisesRegex(ValueError, "regular expression"):
      self.line('search "(" --regex')

  def test0900namesWithSpaces(self):
    self.line("new node node --type --name person")
    dog = self.line('new node person --name "big dog"')
    fred = self.line("new node person --name fred")
    self.line("new relation relation --type --name likes")
    self.assertIs(self.line('query "big dog"'), dog)
    self.assertIs(self.line("query 'big dog'"), dog)
    self.assertIs(self.line('query "#big dog"'), dog)
    r = self.line('new relation likes --source fred --destination "big dog"')
    self.assertIs(r.dst, dog)
    self.assertEqual(self.line('query fred likes ?'), [dog])
    self.assertTrue(self.line('query fred likes "big dog"'))
    self.line('set attribute "big dog" colour brown')
    self.assertEqual(self.line('get attribute "big dog" colour'), "brown")

  def test1000unknownNames(self):
    self.line("new node node --type --name person")
    self.line("new node person --name fred")
    self.line("new relation relation --type --name likes")
    for line, name in (('query "no body"', "no body"),
                       ("query nobody", "nobody"),
                       ("new relation likes --source fred --destination nobody", "nobody"),
                       ('new relation likes --source "no body" --destination fred', "no body"),
                       ('set attribute "no body" colour brown', "no body"),
                       ('get attribute nobody colour', "nobody"),
                       ('remove "no body"', "no body")):
      with self.subTest(line=line):
        with self.assertRaisesRegex(ValueError, f'no object named "{name}"'):
          self.line(line)

  def test1100ambiguousNames(self):
    self.line("new node node --type --name person")
    self.line("new node person --name fred")
    self.line("new node person --name mary")
    self.line("new relation relation --type --name likes")
    self.line("new relation likes --source fred --destination mary") # (named "likes" too)
    for line, option in (("reconnect likes --source mary", "relation"),
                         ("remove likes", "object"),
                         ("set kind likes type", "object"),
                         ("mark asserted likes", "object")):
      with self.subTest(line=line):
        with self.assertRaisesRegex(ValueError, f'^{option}: .*"#likes" resolves to multiple objects') as cm:
          self.line(line)
        self.assertIsInstance(cm.exception.__cause__, DuplicateNameError)
    with self.assertRaisesRegex(ValueError, '^relation: There\'s no object named "nobody"'):
      self.line("reconnect nobody")

if __name__ == "__main__":
  unittest.main()
