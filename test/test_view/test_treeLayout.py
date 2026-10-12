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
The tree layout's geometry (see *sn.view.graphics.treeLayout.treePositions()*):
the part that needs no screen.

Created on Oct 10, 2026

@author: robkremer
'''
import random
import tempfile
import unittest
from pathlib import Path
from sn.model.model import Model, Node, Relation
from sn.view.graphics.layout import relationTypes, relationNamed, nodeTypes
from sn.view.graphics.treeLayout import treePositions, treeMembers, placeNear

def boxes(pos, sizes):
  return {n: (x, y, x + sizes[n][0], y + sizes[n][1]) for n, (x, y) in pos.items()}

def overlapping(bs):
  items = list(bs.items())
  return [(a, b) for i, (a, p) in enumerate(items) for b, q in items[i + 1:]
          if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]]

def centre(b):
  return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


class Test(unittest.TestCase):

  def setUp(self):
    self.sizes = {n: (60, 30) for n in "rabcdefgh"}

  def test0100rightFan(self):
    pos, trees = treePositions(["r"], {"r": [["a", "b", "c"]]}, self.sizes, spacing=10, levelGap=100)
    self.assertEqual(pos["r"][0], 0)
    for k in "abc":
      self.assertEqual(pos[k][0], 60 + 100)                          # one column, a level gap out
    self.assertEqual([pos[k][1] for k in "abc"], [0, 40, 80])          # in order, spacing apart
    self.assertEqual(centre(boxes(pos, self.sizes)["r"])[1], 55)       # level with their middle
    self.assertEqual(trees, [("r", [0, 0, 220, 110])])

  def test0200groupsFurtherApart(self):
    pos, _ = treePositions(["r"], {"r": [["a", "b"], ["c"]]}, self.sizes, spacing=10, levelGap=100)
    self.assertEqual([pos[k][1] for k in "abc"], [0, 40, 90])          # an extra spacing between groups

  def test0300otherDirections(self):
    kids = {"r": [["a", "b"]]}
    down, _ = treePositions(["r"], kids, self.sizes, direction="down", spacing=10, levelGap=100)
    self.assertEqual([down[k] for k in "ab"], [(0, 130), (70, 130)])   # a row below
    left, _ = treePositions(["r"], kids, self.sizes, direction="left", spacing=10, levelGap=100)
    self.assertEqual(left["r"][0], -60)                                # the root's far side at 0
    self.assertEqual(left["a"][0], -60 - 100 - 60)                     # to the left
    up, _ = treePositions(["r"], kids, self.sizes, direction="up", spacing=10, levelGap=100)
    self.assertEqual(up["a"][1], -30 - 100 - 30)                       # above

  def test0400levelGaps(self):
    pos, _ = treePositions(["r"], {"r": [["a"]], "a": [["b"]]}, self.sizes, levelGaps={0: 50, 1: 200})
    self.assertEqual([pos[k][0] for k in "rab"], [0, 110, 110 + 60 + 200])

  def test0500bigParentDoesntOverlap(self):
    sizes = dict(self.sizes, b=(60, 300))                              # far taller than its one child
    kids = {"r": [["a", "b"]], "b": [["c"]], "a": [["d"]]}
    pos, _ = treePositions(["r"], kids, sizes, spacing=10, levelGap=100)
    self.assertEqual(overlapping(boxes(pos, sizes)), [])
    self.assertGreaterEqual(pos["b"][1], pos["a"][1] + 30 + 10)

  def test0600firstParentOnly(self):
    kids = {"r": [["a", "b"]], "a": [["c"]], "b": [["c", "d"]]}       # c under a and b
    pos, _ = treePositions(["r"], kids, self.sizes, spacing=10, levelGap=100)
    self.assertEqual(len(pos), 5)
    self.assertEqual(treeMembers("r", kids, pos), ["r", "a", "b", "c", "d"])
    self.assertEqual(overlapping(boxes(pos, self.sizes)), [])

  def test0700forestEachOnItsOwn(self):
    pos, trees = treePositions(["r", "e"], {"r": [["a"]], "e": [["f", "g"]]}, self.sizes)
    self.assertEqual(pos["r"], (0, 0))
    self.assertEqual(pos["e"][0], 0)                                   # each root at depth 0
    self.assertEqual([t[0] for t in trees], ["r", "e"])

  def test0800randomTreesDontOverlap(self):
    rnd = random.Random(7)
    for direction in ("right", "down", "left", "up"):
      for _ in range(20):
        n = rnd.randint(2, 60)
        sizes = {i: (rnd.randint(20, 140), rnd.randint(15, 80)) for i in range(n)}
        kids:dict = {}
        for i in range(1, n):
          kids.setdefault(rnd.randrange(i), []).append(i)
        groups = {p: [ks[:len(ks) // 2], ks[len(ks) // 2:]] if len(ks) > 2 else [ks] for p, ks in kids.items()}
        pos, _ = treePositions([0], groups, sizes, direction=direction, spacing=5, levelGap=40)
        self.assertEqual(len(pos), n)
        self.assertEqual(overlapping(boxes(pos, sizes)), [], f"{direction}: {groups}")

  def test0850compactTucksIn(self):
    # a: one child with a deep, narrow chain; b: a leaf -- b tucks in beside a's chain
    sizes = {n: (60, 30) for n in ["r", "a", "b", "a1", "a2", "a3", "a4"]}
    kids = {"r": [["a", "b"]], "a": [["a1", "a2", "a3", "a4"]]}
    loose, _ = treePositions(["r"], kids, sizes, spacing=10, levelGap=100)
    tight, _ = treePositions(["r"], kids, sizes, spacing=10, levelGap=100, compact=True)
    self.assertEqual(loose["b"][1], 4 * 40)                           # after all of a's leaves
    self.assertEqual(tight["b"][1], loose["a"][1] + 40)               # just after a itself: its level is clear
    self.assertEqual(overlapping(boxes(tight, sizes)), [])
    self.assertEqual([tight[k][0] for k in kids["a"][0]], [loose[k][0] for k in kids["a"][0]]) # (the same depths)

  def test0860compactRandomTrees(self):
    rnd = random.Random(11)
    for direction in ("right", "down", "left", "up"):
      for _ in range(30):
        n = rnd.randint(2, 80)
        sizes = {i: (rnd.randint(20, 140), rnd.randint(15, 80)) for i in range(n)}
        kids:dict = {}
        for i in range(1, n):
          kids.setdefault(rnd.randrange(i), []).append(i)
        groups = {p: [ks[:len(ks) // 2], ks[len(ks) // 2:]] if len(ks) > 2 else [ks] for p, ks in kids.items()}
        loose, lt = treePositions([0], groups, sizes, direction=direction, spacing=5, levelGap=40)
        tight, tt = treePositions([0], groups, sizes, direction=direction, spacing=5, levelGap=40, compact=True)
        self.assertEqual(len(tight), n)
        self.assertEqual(overlapping(boxes(tight, sizes)), [], f"{direction}: {groups}")
        across = (lambda b: b[2] - b[0]) if direction in ("down", "up") else (lambda b: b[3] - b[1])
        self.assertLessEqual(across(tt[0][1]), across(lt[0][1]) + 1e-6)  # never bigger across
        # each level's nodes are in the same order across as the loose layout's: the relations don't cross
        a = 0 if direction in ("down", "up") else 1
        d = 1 - a
        for depth in {loose[i][d] for i in range(n)}:
          level = [i for i in range(n) if loose[i][d] == depth]
          self.assertEqual(sorted(level, key=lambda i: loose[i][a]), sorted(level, key=lambda i: tight[i][a]))

  def test0870nearBesideWhatItsRelatedTo(self):
    placed = {"a": [0, 0, 60, 30], "b": [0, 100, 60, 130]}
    sizes = {"x": (40, 20), "y": (40, 20)}
    pos, left = placeNear(["x", "y"], sizes, {"x": ["a", "b"], "y": []}, placed, [], spacing=10, beyond=50)
    self.assertEqual(pos["x"], (60 + 50, 65 - 10))                    # beyond them, level with their middle
    self.assertEqual(left, ["y"])                                      # related to nothing placed
    down, _ = placeNear(["x"], sizes, {"x": ["a"]}, {"a": placed["a"]}, [], direction="down", spacing=10, beyond=50)
    self.assertEqual(down["x"], (10, 30 + 50))                         # below, under its middle

  def test0880nearMovesOnRatherThanBack(self):
    placed = {"a": [0, 0, 60, 30]}
    sizes = {"x": (40, 20)}
    blocker = [110, -20, 150, 50]                                      # just where x would go
    pos, _ = placeNear(["x"], sizes, {"x": ["a"]}, placed, [blocker], spacing=10, beyond=50)
    x, y = pos["x"]
    box = [x, y, x + 40, y + 20]
    self.assertFalse(box[0] < blocker[2] + 10 and blocker[0] < box[2] + 10 and box[1] < blocker[3] + 10 and blocker[1] < box[3] + 10)
    self.assertGreaterEqual(x, 110)                                    # not back toward a: on, or across

  def test0890nearChainsAndDoesntOverlap(self):
    rnd = random.Random(5)
    placed = {f"t{i}": [0, i * 40, 80, i * 40 + 30] for i in range(10)}
    items = [f"n{i}" for i in range(30)]
    sizes = {n: (rnd.randint(20, 90), rnd.randint(15, 40)) for n in items}
    related = {n: [f"t{rnd.randrange(10)}"] for n in items[:20]}
    related.update({n: [items[rnd.randrange(20)]] for n in items[20:]})  # (related only to others of them)
    pos, left = placeNear(items, sizes, related, placed, [], spacing=5)
    self.assertEqual(left, [])
    self.assertEqual(sorted(pos), sorted(items))
    allBoxes = {**{k: tuple(b) for k, b in placed.items()}, **{n: (x, y, x + sizes[n][0], y + sizes[n][1]) for n, (x, y) in pos.items()}}
    self.assertEqual(overlapping(allBoxes), [])

  def test0900relationTypesFromSuperModels(self):
    # a layout's relation (eg: "includes", in an ontology the model's built on) is found by name: a saved
    # view's tree layout lost it, as Model.values() has only the model's own objects
    with tempfile.TemporaryDirectory() as folder:
      folder = str(Path(folder).resolve()) # (macOS: /var is /private/var)
      Model._initCache()
      base = Model(str(Path(folder, "base.snm")))
      thing = Node(base, [base.NODE], name="thing")
      includes = Relation(base, [base.RELATION], thing, thing, name="includes")
      base.save()
      m = Model(str(Path(folder, "main.snm")))
      m.setSuperModels(["base.snm"])
      local = Relation(m, [m.RELATION], thing, thing, name="likes")
      names = [r.name for r in relationTypes(m)]
      self.assertEqual(names[0], "isa")
      self.assertIn("includes", names)
      self.assertIn("likes", names)
      self.assertNotIn("contains", names)                              # (the system's: not offered)
      self.assertIs(relationNamed(m, "includes"), includes)
      self.assertIs(relationNamed(m, "likes"), local)
      person = Node(m, [thing], name="person")
      self.assertEqual([n.name for n in nodeTypes(m)], ["person", "thing"]) # (the super-model's too; not the system's "node")

if __name__ == "__main__":
  unittest.main()
