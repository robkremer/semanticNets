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
The round layouts' geometry (see *sn.view.graphics.balloonLayout*): the part
that needs no screen.

Created on Oct 14, 2026

@author: robkremer
'''
import math
import random
import unittest
from sn.view.graphics.balloonLayout import balloonPositions, radialPositions, hubForest, hubPositions, radius, placeNearGroups

def boxes(centres, sizes):
  return {n: (x - sizes[n][0] / 2, y - sizes[n][1] / 2, x + sizes[n][0] / 2, y + sizes[n][1] / 2) for n, (x, y) in centres.items()}

def overlapping(bs):
  items = list(bs.items())
  return [(a, b) for i, (a, p) in enumerate(items) for b, q in items[i + 1:]
          if p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]]

def randomTree(rnd, n):
  sizes = {i: (rnd.randint(20, 140), rnd.randint(15, 80)) for i in range(n)}
  kids:dict = {}
  for i in range(1, n):
    kids.setdefault(rnd.randrange(i), []).append(i)
  return sizes, kids

def crosses(a, b, c, d):
  ":returns: Whether segments ab and cd cross (not just touch at an end)."
  def side(p, q, r):
    return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
  return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


class Test(unittest.TestCase):

  def setUp(self):
    self.sizes = {n: (60, 30) for n in "rabcdefgh"}

  def test0100balloonRing(self):
    pos, trees = balloonPositions(["r"], {"r": ["a", "b", "c", "d"]}, self.sizes, spacing=10)
    self.assertEqual(pos["r"], (0.0, 0.0))
    ds = [math.hypot(*pos[k]) for k in "abcd"]
    for d in ds:
      self.assertAlmostEqual(d, ds[0])                                   # all on one ring
    self.assertAlmostEqual(pos["a"][0], 0, places=6)                     # the first at the top
    self.assertLess(pos["a"][1], 0)
    self.assertGreater(pos["b"][0], 0)                                   # then clockwise
    self.assertEqual(overlapping(boxes(pos, self.sizes)), [])
    self.assertEqual(trees[0][0], "r")
    self.assertEqual(sorted(trees[0][1]), list("abcdr"))
    self.assertAlmostEqual(trees[0][2], ds[0] + radius((60, 30)))

  def test0200balloonFacesAwayFromParent(self):
    pos, _ = balloonPositions(["r"], {"r": ["a"], "a": ["b", "c", "d"]}, self.sizes, spacing=10)
    # a is straight above r; its children are spread round above it, none back down toward r
    self.assertAlmostEqual(pos["a"][0], 0, places=6)
    for k in "bcd":
      v = (pos[k][0] - pos["a"][0], pos[k][1] - pos["a"][1])
      self.assertLess(pos["a"][1], 0)
      self.assertLess(abs(math.atan2(v[0], -v[1])), math.pi - math.pi / 4 + 1e-9)  # out of the gap behind a

  def test0300edgeRoom(self):
    near, _ = balloonPositions(["r"], {"r": ["a"]}, self.sizes, spacing=10)
    far, _ = balloonPositions(["r"], {"r": ["a"]}, self.sizes, spacing=10, edgeRoom={"a": 200})
    self.assertAlmostEqual(math.hypot(*far["a"]) - math.hypot(*near["a"]), 190)

  def test0400firstParentOnly(self):
    pos, trees = balloonPositions(["r", "a"], {"r": ["a", "b"], "a": ["c"], "b": ["c", "d"]}, self.sizes)
    self.assertEqual(len(pos), 5)
    self.assertEqual(len(trees), 1)                                      # a's in r's tree: not a root of its own

  def test0500balloonRandomTreesDontOverlapOrCross(self):
    rnd = random.Random(3)
    for _ in range(40):
      n = rnd.randint(2, 80)
      sizes, kids = randomTree(rnd, n)
      pos, trees = balloonPositions([0], kids, sizes, spacing=5)
      self.assertEqual(len(pos), n)
      self.assertEqual(overlapping(boxes(pos, sizes)), [], kids)
      edges = [(p, k) for p, ks in kids.items() for k in ks]
      for i, (a, b) in enumerate(edges):
        for c, d in edges[i + 1:]:
          if len({a, b, c, d}) == 4:
            self.assertFalse(crosses(pos[a], pos[b], pos[c], pos[d]), f"{(a, b)} x {(c, d)}: {kids}")
      for m in pos:                                                       # all inside its balloon
        self.assertLessEqual(math.hypot(*pos[m]) + radius(sizes[m]), trees[0][2] + 1e-6)

  def test0600radialRings(self):
    kids = {"r": ["a", "b", "c"], "a": ["d", "e"], "c": ["f"]}
    pos, _ = radialPositions(["r"], kids, self.sizes, spacing=10)
    self.assertEqual(pos["r"], (0.0, 0.0))
    d1 = [math.hypot(*pos[k]) for k in "abc"]
    d2 = [math.hypot(*pos[k]) for k in "def"]
    for d in d1:
      self.assertAlmostEqual(d, d1[0])                                   # each depth on one circle
    for d in d2:
      self.assertAlmostEqual(d, d2[0])
    self.assertGreater(d2[0], d1[0])
    self.assertEqual(overlapping(boxes(pos, self.sizes)), [])

  def test0700radialRandomTreesDontOverlap(self):
    rnd = random.Random(5)
    for _ in range(40):
      n = rnd.randint(2, 80)
      sizes, kids = randomTree(rnd, n)
      pos, _ = radialPositions([0], kids, sizes, spacing=5)
      self.assertEqual(len(pos), n)
      self.assertEqual(overlapping(boxes(pos, sizes)), [], kids)

  def test0800hubForest(self):
    # two stars (h1: a b c; h2: d e f), their hubs related; x and y related only to each other; z to nothing
    edges = [("h1", "a"), ("h1", "b"), ("h1", "c"), ("h2", "d"), ("h2", "e"), ("h2", "f"), ("h1", "h2"),
             ("c", "g"), ("x", "y")]
    nodes = ["a", "b", "c", "d", "e", "f", "g", "h1", "h2", "x", "y", "z"]
    nbrs:dict = {n: [] for n in nodes}
    for a, b in edges:
      nbrs[a].append(b)
    groups, isolated = hubForest(nodes, nbrs, minSpokes=3)
    self.assertEqual(isolated, ["z"])
    self.assertEqual(len(groups), 2)
    hubs, kids = groups[0]
    self.assertEqual(sorted(hubs), ["h1", "h2"])
    self.assertEqual(sorted(kids["h1"]), ["a", "b", "c"])                # h2's a hub: not h1's spoke
    self.assertEqual(sorted(kids["h2"]), ["d", "e", "f"])
    self.assertEqual(kids["c"], ["g"])                                    # under the spoke nearer it
    self.assertEqual(groups[1][0], ["x"])                                 # no hub: the one with the most (the first)
    self.assertEqual(groups[1][1]["x"], ["y"])

  def test0900hubRingOrder(self):
    # hubs in a chain p - q - r - s (each with spokes), given most-connected first: the ring follows the chain
    nbrs:dict = {}
    def link(a, b):
      nbrs.setdefault(a, []).append(b)
      nbrs.setdefault(b, []).append(a)
    for h in "pqrs":
      for i in range(3 if h != "q" else 4):
        link(h, f"{h}{i}")
    link("p", "q"); link("q", "r"); link("r", "s")
    groups, _ = hubForest(sorted(nbrs), nbrs, minSpokes=3)
    ring = groups[0][0]
    self.assertEqual(ring[0], "q")                                        # the most related first
    for a, b in zip(ring, ring[1:]):
      self.assertIn(b, nbrs[a] + [x for y in nbrs[a] for x in nbrs.get(y, [])])

  def test1000hubPositionsDontOverlap(self):
    rnd = random.Random(9)
    for _ in range(30):
      n = rnd.randint(3, 90)
      nodes = list(range(n))
      nbrs:dict = {i: [] for i in nodes}
      for i in range(1, n):
        j = rnd.randrange(i) if rnd.random() < 0.5 else rnd.randrange(max(1, i // 8))  # some big hubs
        nbrs[i].append(j)
      for _ in range(n // 5):                                             # and some cycles
        a, b = rnd.randrange(n), rnd.randrange(n)
        if a != b:
          nbrs[a].append(b)
      sizes = {i: (rnd.randint(20, 140), rnd.randint(15, 80)) for i in nodes}
      groups, isolated = hubForest(nodes, nbrs, minSpokes=4)
      placed = 0
      for hubs, kids in groups:
        pos, r = hubPositions(hubs, kids, sizes, spacing=5)
        placed += len(pos)
        self.assertEqual(overlapping(boxes(pos, sizes)), [], (hubs, kids))
        for m in pos:
          self.assertLessEqual(math.hypot(*pos[m]) + radius(sizes[m]), r + 1e-6)
      self.assertEqual(placed + len(isolated), n)                         # every node somewhere

  def test1100twoHubsFaceApart(self):
    kids = {"p": ["a", "b"], "q": ["c", "d"]}
    sizes = {n: (60, 30) for n in "pqabcd"}
    pos, _ = hubPositions(["p", "q"], kids, sizes, spacing=10)
    self.assertLess(pos["p"][1], 0)                                        # p at the top, q at the bottom
    self.assertGreater(pos["q"][1], 0)
    for k in "ab":
      self.assertLess(pos[k][1], pos["p"][1])                             # p's spokes above it: away from the middle
    for k in "cd":
      self.assertGreater(pos[k][1], pos["q"][1])

  def test1200nearGoesOutBeyond(self):
    sizes = {n: (60, 30) for n in "rabcxyz"}
    pos, _ = balloonPositions(["r"], {"r": ["a", "b", "c"]}, sizes, spacing=10)
    group = dict(pos)
    left = placeNearGroups(["x", "y", "z"], sizes, {"x": ["b"], "y": ["x"], "z": []}, [group], spacing=10)
    self.assertEqual(left, ["z"])                                         # related to nothing placed: not put
    self.assertIn("x", group)
    self.assertIn("y", group)                                             # (via x: once x's put)
    out = lambda n: math.hypot(*group[n])
    self.assertGreater(out("x"), out("b"))                                # beyond b, away from the middle
    cos = (group["x"][0] * group["b"][0] + group["x"][1] * group["b"][1]) / (out("x") * out("b"))
    self.assertGreater(cos, 0.9)                                          # the same way out as b
    self.assertGreater(out("y"), out("x"))
    self.assertEqual(overlapping(boxes(group, sizes)), [])

  def test1300nearRoomForTheLabel(self):
    sizes = {n: (60, 30) for n in "rax"}
    group = {"r": (0.0, 0.0), "a": (0.0, -100.0)}
    placeNearGroups(["x"], sizes, {"x": ["a"]}, [group], spacing=10, room=lambda n, r: 150)
    gap = math.hypot(group["x"][0] - group["a"][0], group["x"][1] - group["a"][1]) - 2 * radius((60, 30))
    self.assertGreaterEqual(gap, 150 - 1e-6)

  def test1400nearTheGroupMostRelated(self):
    sizes = {n: (60, 30) for n in ["p", "q", "p1", "q1", "q2", "x"]}
    g1 = {"p": (0.0, 0.0), "p1": (0.0, 80.0)}
    g2 = {"q": (0.0, 0.0), "q1": (80.0, 0.0), "q2": (-80.0, 0.0)}
    placeNearGroups(["x"], sizes, {"x": ["p1", "q1", "q2"]}, [g1, g2], spacing=10)
    self.assertIn("x", g2)
    self.assertNotIn("x", g1)

  def test1500nearRandomDontOverlap(self):
    rnd = random.Random(13)
    for _ in range(30):
      n = rnd.randint(3, 50)
      sizes, kids = randomTree(rnd, n)
      pos, _ = balloonPositions([0], kids, sizes, spacing=5)
      group = dict(pos)
      extra = list(range(n, n + rnd.randint(1, 20)))
      sizes.update({i: (rnd.randint(20, 140), rnd.randint(15, 80)) for i in extra})
      related = {i: [rnd.randrange(i)] for i in extra}
      left = placeNearGroups(extra, sizes, related, [group], spacing=5)
      self.assertEqual(left, [])
      self.assertEqual(overlapping(boxes(group, sizes)), [])

if __name__ == "__main__":
  unittest.main()
