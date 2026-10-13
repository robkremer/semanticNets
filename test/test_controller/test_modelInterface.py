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
Created on Jun 5, 2026

@author: robkremer
'''
import unittest
import sn.controller.modelInterface
from pathlib import Path
from sn.model.model import Model, Relation, GraphObject, Node
from sn.controller.modelInterface import ModelContext

context:ModelContext
m:Model
FILE1:str = 'temp.xml'
FILE2:str = 'temp2.xml'

def printx(s:str):
  print(f'> {s}')
  print(eval(s))

nItems = 0 # The number of items in a new graph

class Test(unittest.TestCase):


  def setUp(self):
    pass


  def tearDown(self):
    pass



  def test0100basicObjects(self):
    global context
    global m
      
    Path(FILE1).unlink(missing_ok=True)
    Path(FILE2).unlink(missing_ok=True)
    Model._initCache()
    
    m = Model(FILE1)
    #logger.setLevel(logging.DEBUG)
    context = ModelContext(m)
    self.assertIn(f"/{FILE1}, <{nItems} items>", context.show(model=m, detail=True))
    self.assertIn(f"/{FILE1}, <{nItems} items>", context.show(detail=True))
    self.assertIn(f"/{FILE1}, <{nItems} items>", context.parser.parseLine("show --detail"))
    self.assertIn(f"/{FILE1}, <{nItems} items>", context.parser.parseLine("show"))

  def test0200defaultModelAndUndo(self):
    global context
    global m
    m = Model(FILE2) # doesn't exist so it's created.
    m.save()
    self.assertIn(f"/{FILE2}", context.default("model", m).url) # m == {FILE1})
    self.assertIn(f"/{FILE2}, <{nItems} items>", context.show(detail=True))
    context.parser.parseLine("undo")
    #print('-------- should be {FILE1} now -------------')
    self.assertIn(f"/{FILE1}, <{nItems} items>", context.show())
    self.assertIn(f"/{FILE2}", context.parser.parseLine(f"default model {FILE2}").url)
    
  def test0300Show(self):
    global context
    global m
    #print('-------- should be {FILE2} now -------------')
    self.assertIn(f"/{FILE2}, <{nItems} items>", context.parser.parseLine("show"))
    #print(context.parser.parseLine("help"))
    #print("-------")
    #printx('context.show("#1")')
    x = context.parser.parseLine("show 1 --d")
    self.assertIn('GraphObject(top, sn:/sn#1, <type>)', x) # names that are identifiers aren't quoted
    
    # this are in /sn now.
    # self.assertIn(f"/{FILE2}#1", x)
    # self.assertIn(f"/{FILE2} <{nItems} items>", context.show(detail=True))
    
  def test0400NewNodeAndUndo(self):
    global context
    global m
    # create fred isa person
    person = context.new_node(m["node"], "person", type=True)
    fred = context.new_node(m["person"], "fred", individual=True)
    self.assertTrue(context.query(["person", "fred"]))
    with self.assertRaises(KeyError):
      context.query(["fred", "person"]) # "fred" isn't a type
    self.assertIs(context.query(["person"]), person)
    self.assertIs(context.query(["fred"]), fred)
    self.assertTrue(context.query(["fred", "isa", "person"]))
    context.undo()
    with self.assertRaises(KeyError):
      context.query(["fred"]) # fred has been undone
    context.redo()
    self.assertTrue(context.query(["fred", "isa", "person"]))

  def test0500NewNodeAndUndo_asText(self):
    global context
    global m
    person = context.parser.parseLine("? person")
    fred = context.parser.parseLine("query fred")
    self.assertTrue(context.parser.parseLine("? person fred"))
    with self.assertRaises(KeyError):
      context.parser.parseLine("? fred person") # "fred" isn't a type
    self.assertIs(context.parser.parseLine("? person"), person)
    self.assertIs(context.parser.parseLine("? fred"), fred)
    self.assertTrue(context.parser.parseLine("? fred isa person"))
    context.parser.parseLine("undo")
    with self.assertRaises(KeyError):
      context.parser.parseLine("? fred") # fred has been undone
    context.redo()
    self.assertTrue(context.parser.parseLine("? fred isa person"))

  def test0600NewNodeAndUndo_asText(self):
    global context
    global m
    person = context.parser.parseLine("? person")
    fred = context.parser.parseLine("query fred")
    context.remove(person)
    with self.assertRaises(KeyError):
      context.query(["person"])
    self.assertIs(context.query(["?", "fred"])[0], context.query(["node"])) # parent(fred) defaults to node.
    self.assertEqual(len(context.query(["?", "fred"])), 1) # parent(fred) defaults to node.
    
    context.undo() # put person back
    self.assertIs(context.query(["person"]), person)
    # Note that the following 2 depend on getParents() (called indirectly by the
    # type query) deleting the inferred relations created by the above queries.
    self.assertIs(context.query(["?", "fred"])[0], context.query(["person"])) # parent(fred) defaults to node.
    self.assertEqual(len(context.query(["?", "fred"])), 1) # parent(fred) defaults to node.
    
  def test0700Relations(self):
    global context
    global m
    go:GraphObject = m["person"]
    assert isinstance(go, Node)
    person:Node = go
    sibling = context.new_relation([m.RELATION], "sibling", individual=False, type=True, destination=m["person"], source=m["person"])
    self.assertIsInstance(sibling, Relation, f'Expected a type Node, got {type(sibling)}: "{sibling}".')
    for tag in ("transitive", "symmetric", "irreflexive"): # relational properties are LOCAL tags on the type
      context.set_attribute(sibling, tag, True, type="bool")
    self.assertTrue(sibling.isSymmetric() and sibling.isTransitive() and sibling.isIrreflexive())
    alice = context.new_node(person, "alice", individual=True)
    self.assertIsInstance(alice, Node, f'Expected a type Node, got {type(alice)}: "{alice}".')
    bob = context.new_node(person, "bob", individual=True)
    self.assertIsInstance(bob, Node, f'Expected a type Node, got {type(bob)}: "{bob}".')
    context.assert_([alice, sibling, bob])
    self.assertTrue(context.query([alice, sibling, bob]))
    self.assertTrue(context.query([bob, sibling, 'alice']))
    self.assertFalse(context.query(['fred', sibling, 'alice']))
    self.assertFalse(context.query([alice, sibling, 'alice']))
    self.assertFalse(context.query([alice, sibling, alice]))
    self.assertFalse(context.query([alice, sibling, 'fred']))
    
  def test0800Asserts(self):
    global context
    global m
    
    def check(exp:list, type:bool=False):
      "Assert the expression and then check it it is True"
      ret = context.assert_(exp, type=type)
      self.assertTrue(context.query(exp))
      return ret
      
    person2 = check([m.NODE, "person2"], type=True)
    self.assertIs(context.query(["person2"]), person2)
    sibling2 = check([m.RELATION, "sibling2"], type=True)
    for tag in ("symmetric", "transitive", "irreflexive"): # relational properties are LOCAL tags on the type
      context.set_attribute(sibling2, tag, True, type="bool")
    sibling2b = context.assert_([person2, sibling2, person2])
    self.assertIs(sibling2, sibling2b)
    alice2 = check([person2, "alice2"])
    bob2 = check([person2, "bob2"])
    siblingInstance = check([alice2, sibling2, bob2])
    self.assertTrue(context.query([alice2, sibling2, bob2]))
    self.assertTrue(context.query([bob2, sibling2, 'alice2']))
    self.assertFalse(context.query([alice2, sibling2, 'alice2']))
    self.assertFalse(context.query(["alice2", sibling2, alice2]))
    
  def test0810Asserts_cmd(self):
    global context
    global m
    
    def check(exp:str):
      "Assert the expression and then check it it is True"
      ret = context.parser.parseLine(f'! {exp}')
      exp2 = exp.replace("--type", "")
      self.assertTrue(context.parser.parseLine(f'? {exp2}'))
      return ret
      
    person3 = check("node person3 --type")
    self.assertIs(context.parser.parseLine("? person3"), person3)
    sibling3 = check("relation sibling3 --type")
    for tag in ("symmetric", "transitive", "irreflexive"): # relational properties are LOCAL tags on the type
      context.parser.parseLine(f"set attribute sibling3 {tag} true --type bool")
    self.assertIs(context.parser.parseLine("? sibling3"), sibling3)
    sibling3b = context.assert_([person3, sibling3, person3])
    self.assertIs(sibling3, sibling3b)
    alice3 = check("person3 alice3")
    bob3 = check("person3 bob3")
    siblingInstance = check("alice3 sibling3 bob3")
    self.assertTrue(context.parser.parseLine("? alice3 sibling3 bob3"))
    self.assertTrue(context.parser.parseLine("? bob3 sibling3 alice3"))
    self.assertFalse(context.parser.parseLine("? alice3 sibling3 alice3"))
    
if __name__ == "__main__":
  #import sys;sys.argv = ['', 'Test.testName']
  unittest.main()