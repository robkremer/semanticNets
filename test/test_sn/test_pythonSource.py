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
Finding a chunk of source again (see the pythonParser plugin's *source*):
by name, by grep, by its first line, or a guess -- after the file's been
edited in the ways that each of them is for.

Created on Oct 14, 2026

@author: robkremer
'''
import ast
import os
import tempfile
import textwrap
import unittest
from sn.model.model import Relation
from sn.plugins import importBundled
source = importBundled("pythonParser", "source")
parser = importBundled("pythonParser", "parser")
locate, chunkAttrs, NAME, GREP, FUZZY, GUESS = source.locate, source.chunkAttrs, source.NAME, source.GREP, source.FUZZY, source.GUESS

ORIGINAL = textwrap.dedent('''\
  import os

  class Shape:
    def __init__(self, n):
      self.n = n

    @property
    def size(self):
      return self.n

    @size.setter
    def size(self, v):
      self.n = v

    def area(self, scale=1):
      return self.n * self.n * scale

  class Other:
    def __init__(self):
      pass

  def helper(a, b):
    return a + b

  if __name__ == "__main__":
    print(helper(1, 2))
  ''')

def attrs(text, *names):
  'The attributes the parser keeps for the chunk *names* of *text* (see chunkAttrs()), and its line.'
  tree = ast.parse(text)
  node = source._byName(tree, list(names), 0)
  assert node is not None
  return node.lineno, chunkAttrs(node, text.split("\n"))

class Test(unittest.TestCase):

  def setUp(self):
    self.folder = tempfile.TemporaryDirectory()
    self.addCleanup(self.folder.cleanup)
    self.path = os.path.join(self.folder.name, "shapes.py")

  def write(self, text):
    with open(self.path, "w") as f:
      f.write(text)

  def find(self, before, after, *names):
    line, a = attrs(before, *names)
    self.write(after)
    return locate(self.path, list(names), line, a[".signature-line"], a[".source-hash"])

  def test0100unchanged(self):
    loc = self.find(ORIGINAL, ORIGINAL, "Shape", "area")
    self.assertEqual((loc.how, loc.line, loc.changed), (NAME, 15, False))
    self.assertEqual(loc.text, "  def area(self, scale=1):\n    return self.n * self.n * scale")
    line, a = attrs(ORIGINAL, "Shape", "area")
    self.assertEqual(a["end-line"], 16)
    self.assertEqual(a[".signature-line"], "def area(self, scale=1):")

  def test0200moved(self):
    after = ORIGINAL.replace("import os\n", "import os\nimport sys\n\n\nX = 1\n")
    loc = self.find(ORIGINAL, after, "Shape", "area")
    self.assertEqual((loc.how, loc.line, loc.changed), (NAME, 19, False))

  def test0300changed(self):
    loc = self.find(ORIGINAL, ORIGINAL.replace("* scale", "* scale * 2"), "Shape", "area")
    self.assertEqual((loc.how, loc.line, loc.changed), (NAME, 15, True))
    loc = self.find(ORIGINAL, ORIGINAL.replace("* scale", "* scale   "), "Shape", "area") # (trailing space)
    self.assertFalse(loc.changed)

  def test0400decoratorsAndSameNames(self):
    loc = self.find(ORIGINAL, ORIGINAL, "Shape", "size")       # (the getter's line: 8)
    self.assertEqual((loc.start, loc.line, loc.end), (7, 8, 9))
    line, a = attrs(ORIGINAL, "Shape", "size")
    self.write(ORIGINAL)
    setter = locate(self.path, ["Shape", "size"], 12)          # (near the setter)
    self.assertEqual((setter.start, setter.line), (11, 12))
    self.assertEqual(self.find(ORIGINAL, ORIGINAL, "Other", "__init__").line, 19) # (not Shape's)

  def test0500unparsable(self):
    broken = ORIGINAL.replace("import os", "import os(") # (doesn't parse)
    loc = self.find(ORIGINAL, broken, "Other", "__init__")
    self.assertEqual((loc.how, loc.line, loc.end, loc.changed), (GREP, 19, 20, False))
    loc = self.find(ORIGINAL, broken, "Shape", "size")
    self.assertEqual((loc.how, loc.start, loc.line), (GREP, 7, 8))
    loc = self.find(ORIGINAL, broken, "__main__")
    self.assertEqual((loc.how, loc.line, loc.end), (GREP, 25, 26))

  def test0600renamed(self):
    loc = self.find(ORIGINAL, ORIGINAL.replace("def helper(a, b)", "def helpers(a, b)"), "helper")
    self.assertEqual((loc.how, loc.line, loc.end, loc.changed), (FUZZY, 22, 23, True))

  def test0700gone(self):
    after = ORIGINAL.replace("def helper(a, b):\n  return a + b\n", "")
    loc = self.find(ORIGINAL, after, "helper")
    self.assertEqual((loc.how, loc.line), (GUESS, 22))
    self.assertIsNone(loc.changed)

  def test0800noFile(self):
    loc = locate(os.path.join(self.folder.name, "nope.py"), ["f"], 3)
    self.assertFalse(loc.found)
    self.assertIn("can't be read", loc.problem or "")
    self.assertEqual(loc.text, "")

  def test0900fromAModel(self):
    readModules, buildModel = parser.readModules, parser.buildModel
    pkg = os.path.join(self.folder.name, "pkg")
    os.mkdir(pkg)
    with open(os.path.join(pkg, "__init__.py"), "w") as f:
      f.write("def top():\n  pass\n")
    with open(os.path.join(pkg, "shapes.py"), "w") as f:
      f.write(ORIGINAL)
    m = buildModel(os.path.join(self.folder.name, "pkg_py.snm"), readModules([pkg]))
    nodes = {n.get("qualified-name", None): n for n in m.values() if n.isIndividual()}
    area = nodes["pkg.shapes.Shape.area"]
    self.assertEqual((area["line"], area["end-line"]), (15, 16))
    self.assertEqual(source.moduleOf(area), nodes["pkg.shapes"])
    with open(os.path.join(pkg, "shapes.py"), "w") as f:
      f.write("# moved down\n" + ORIGINAL)
    loc = source.locateNode(area)
    assert loc is not None
    self.assertEqual((loc.how, loc.line, loc.changed), (NAME, 16, False))
    self.assertEqual(source.locateNode(nodes["pkg.shapes.__main__"]).line, 26) # type: ignore[union-attr]
    self.assertIsNone(source.locateNode(nodes["pkg.shapes"]))       # (a module: no chunk)
    loc = source.locateNode(nodes["pkg.top"])                      # (in a package's __init__.py)
    assert loc is not None
    self.assertEqual((loc.how, loc.line, os.path.basename(loc.path)), (NAME, 1, "__init__.py"))

  def test1000reexportedBase(self):
    'A base imported from a module that imports it from another (eg: Command, from util.commandParser, defined in util.command) is still inherited from; and so is a generic one (eg: Base[T]).'
    readModules, buildModel = parser.readModules, parser.buildModel
    pkg = os.path.join(self.folder.name, "pkg")
    os.mkdir(pkg)
    for name, text in (("__init__.py", ""),
                       ("base.py", "class Base:\n  def go(self):\n    pass\n"),
                       ("middle.py", "from pkg.base import Base\n"),
                       ("again.py", "from .middle import Base as B\n"),
                       ("sub.py", "from pkg.middle import Base\nfrom pkg import again\n"
                                  "class Sub(Base):\n  def go(self):\n    pass\n"
                                  "class Sub2(again.B):\n  pass\n"
                                  "class Gen[T](Base):\n  pass\n"
                                  "class Sub3[T](Gen[T], again.B[int]):\n  pass\n")):
      with open(os.path.join(pkg, name), "w") as f:
        f.write(text)
    m = buildModel(os.path.join(self.folder.name, "pkg_py.snm"), readModules([pkg]))
    nodes = {n.get("qualified-name", None): n for n in m.values() if n.isIndividual()}
    inherits = {(str(r.src.get("qualified-name", None)), str(r.dst.get("qualified-name", None)))
                for r in m.values() if isinstance(r, Relation) and r.isIndividual() and str(r.getParents()[0].name) == "inherits-from"}
    self.assertEqual(inherits, {("pkg.sub.Sub", "pkg.base.Base"), ("pkg.sub.Sub2", "pkg.base.Base"),
                                ("pkg.sub.Gen", "pkg.base.Base"), ("pkg.sub.Sub3", "pkg.sub.Gen"), ("pkg.sub.Sub3", "pkg.base.Base")})
    self.assertIn("overriding-method", {str(p.name) for p in nodes["pkg.sub.Sub.go"].getParents()})

  def test1100dependsOnType(self):
    'A class depends-on-type the analysed classes its attributes are of: annotated, made, or given (as an annotated parameter).'
    readModules, buildModel = parser.readModules, parser.buildModel
    pkg = os.path.join(self.folder.name, "pkg")
    os.mkdir(pkg)
    for name, text in (("__init__.py", ""),
                       ("things.py", "class Node:\n  pass\nclass Edge:\n  pass\nclass Graph:\n  pass\n"
                                     "class Label:\n  pass\nclass Unused:\n  pass\n"),
                       ("user.py", textwrap.dedent('''\
                         from dataclasses import dataclass
                         from typing import Optional
                         from pkg import things
                         from pkg.things import Node, Edge, Graph, Label, Unused

                         @dataclass
                         class Holder:
                           node: Node
                           count: int = 0

                         class User:
                           def __init__(this, g:"Graph", label:Label|None=None):
                             this.nodes:list[Node] = []
                             this.edges = {}
                             this.edges2:"dict[str, Optional[Edge]]" = {}
                             this.graph = g
                             this.label = label
                             this.holder = Holder(Node())
                             this.me:User|None = None
                             things.Unused()       # (not an attribute)
                           @staticmethod
                           def make(x:Unused):
                             x.y = Unused()        # (not self's)
                         '''))):
      with open(os.path.join(pkg, name), "w") as f:
        f.write(text)
    m = buildModel(os.path.join(self.folder.name, "pkg_py.snm"), readModules([pkg]))
    deps = {(str(r.src.get("qualified-name", None)), str(r.dst.get("qualified-name", None)))
            for r in m.values() if isinstance(r, Relation) and r.isIndividual() and str(r.getParents()[0].name) == "depends-on-type"}
    self.assertEqual(deps, {("pkg.user.Holder", "pkg.things.Node")}
                     | {("pkg.user.User", f"pkg.things.{c}") for c in ("Node", "Edge", "Graph", "Label")}
                     | {("pkg.user.User", "pkg.user.Holder")})

if __name__ == "__main__":
  unittest.main()
