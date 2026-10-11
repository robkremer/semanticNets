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
import unittest
from sn.view.graphics.treeLayout import treePositions, treeMembers

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


if __name__ == "__main__":
  unittest.main()
