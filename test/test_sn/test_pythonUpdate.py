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
Updating a model the pythonParser plugin made (see its *parser.updateModel()*)
after the code's changed: what's still there keeps its node -- and its id --
corrected; what's new gets a new node; what's gone is removed; and the rest of
the model (objects and attributes of one's own) is left as it is.

Created on Oct 24, 2026

@author: robkremer
'''
import os
import tempfile
import textwrap
import unittest
from sn.model.model import Model, Node, Relation
from sn.plugins import importBundled
parser = importBundled("pythonParser", "parser")

BEFORE = textwrap.dedent('''\
  """The module."""
  import os

  class Shape:
    """A shape."""
    @property
    def size(self):
      return 1

    @size.setter
    def size(self, v):
      pass

    def area(self):
      return 0

  def helper(a):
    pass

  def later():
    pass
  ''')

AFTER = textwrap.dedent('''\
  """The module, changed."""
  import sys

  class Shape:
    @property
    def size(self):
      return 1

    @size.setter
    def size(self, v):
      pass

    def area(self, scale=1):
      """Its area."""
      return 0

    def helper(self):
      pass

  class later:
    pass
  ''')

class TestUpdateModel(unittest.TestCase):

  def setUp(self):
    Model._initCache()
    self.tmp = tempfile.TemporaryDirectory(prefix="snPythonUpdate-")
    self.folder = os.path.realpath(self.tmp.name)
    self.source = os.path.join(self.folder, "shapes.py")
    self.modelPath = os.path.join(self.folder, "shapes_py.snm")
    self.write(BEFORE)
    model = parser.buildModel(self.modelPath, parser.readModules([self.source]))
    model.save()
    self.before = self.nodes(model)
    model.unload()

  def tearDown(self):
    Model._initCache()
    self.tmp.cleanup()

  def write(self, text:str) -> None:
    with open(self.source, "w") as f:
      f.write(text)

  def nodes(self, model:Model) -> dict[str, list[Node]]:
    'The nodes the parser made, by qualified name (a doc string by "doc of " its owner\'s): in the order they were made.'
    ret:dict[str, list[Node]] = {}
    for o in sorted(model.values(), key=lambda o: int(o.id)):
      if o.model is model and isinstance(o, Node) and o.isIndividual():
        q = o.getLocal("qualified-name")
        if not isinstance(q, str):
          owners = [r.src for r in model.values() if isinstance(r, Relation) and r.dst is o and r.name == "has-doc"]
          q = "doc of " + str(owners[0].getLocal("qualified-name")) if owners else str(o.name)
        ret.setdefault(q, []).append(o)
    return ret

  def update(self, text:str|None=AFTER) -> tuple[Model, object]:
    if text is not None:
      self.write(text)
    model = Model(self.modelPath)
    return model, parser.updateModel(model, parser.readModules([self.source]))

  def ids(self, nodes:dict[str, list[Node]], name:str) -> list[int]:
    return [int(n.id) for n in nodes.get(name, [])]

  def test_keeps(self):
    'What\'s still in the code keeps its node, and its id -- corrected (eg: its doc string, its parameters, a function now a class).'
    model, done = self.update()
    after = self.nodes(model)
    for name in ("shapes", "shapes.Shape", "shapes.Shape.size", "shapes.Shape.area", "shapes.later", "doc of shapes"):
      self.assertEqual(self.ids(after, name), self.ids(self.before, name), name)
    self.assertEqual(len(after["shapes.Shape.size"]), 2) # (the getter and the setter: each its own, as before)
    self.assertEqual(after["doc of shapes"][0]["text"], "The module, changed.")
    self.assertEqual(after["shapes.Shape.area"][0]["parameters"], "self, scale=1")
    self.assertEqual([p.name for p in after["shapes.later"][0].getParents()], ["class"])
    self.assertIsNone(after["shapes.later"][0].getLocalAttr("parameters")) # (a function's: not a class's)

  def test_addsAndRemoves(self):
    'What\'s new gets a new node (a new id); what\'s gone is removed, with its relations.'
    model, done = self.update()
    after = self.nodes(model)
    highest = max(int(n.id) for ns in self.before.values() for n in ns)
    for name in ("sys", "shapes.Shape.helper", "doc of shapes.Shape.area"):
      self.assertTrue(after.get(name), name)
      self.assertGreater(int(after[name][0].id), highest, name)
    for name in ("os", "shapes.helper", "doc of shapes.Shape"):
      self.assertNotIn(name, after)
    self.assertEqual(done.summary(), "7 kept, 3 added, 3 removed") #type: ignore[attr-defined]
    imports = [(r.src.name, r.dst.name) for r in model.values() if isinstance(r, Relation) and r.model is model and r.name == "imports"]
    self.assertEqual(imports, [("shapes", "sys")])

  def test_again(self):
    'Updated again from the same code, nothing changes.'
    model, _ = self.update()
    model.save()
    model.unload()
    model, done = self.update(None)
    self.assertEqual(done.added + done.removed, []) #type: ignore[attr-defined]
    self.assertFalse(model.isDirty())

  def test_leavesOwn(self):
    'Objects and attributes of one\'s own are left as they are (but a relation to something removed goes with it).'
    model = Model(self.modelPath)
    nodes = self.nodes(model)
    shape, helper = nodes["shapes.Shape"][0], nodes["shapes.helper"][0]
    shape["my-note"] = "keep me"
    mine = Node(model, [model.NODE], individual=True, name="my own")
    Relation(model, [model.RELATION], mine, shape, individual=True)
    Relation(model, [model.RELATION], mine, helper, individual=True)
    model.save()
    model.unload()
    model, _ = self.update()
    after = self.nodes(model)
    self.assertEqual(after["shapes.Shape"][0].getLocal("my-note"), "keep me")
    self.assertIn("my own", after)
    mine = after["my own"][0]
    self.assertEqual([r.dst.name for r in model.values() if isinstance(r, Relation) and r.src is mine and r.name != "isa"], ["Shape"])

  def test_notOurs(self):
    'A model the parser didn\'t make isn\'t updated.'
    other = Model(os.path.join(self.folder, "other.snm"))
    with self.assertRaises(ValueError):
      parser.updateModel(other, parser.readModules([self.source]))

if __name__ == "__main__":
  unittest.main()
