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
from sn.view.graphics.balloonLayout import (balloonPositions, radialPositions, hubForest, hubPositions, radius, placeNearGroups,
                                            topLefts, groupOffset, separateGroups)

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

  # ---- kept arranged ----------------------------------------------------------------

  def tlBoxes(self, groups, offsets, sizes):
    return {n: (x + dx, y + dy, x + dx + sizes[n][0], y + dy + sizes[n][1])
            for g, (dx, dy) in zip(groups, offsets) for n, (x, y) in g.items()}

  def test1600anchoredAtTheRoot(self):
    pos, _ = balloonPositions(["r"], {"r": ["a", "b"]}, self.sizes, spacing=10)
    rel = topLefts(pos, self.sizes)
    now = {"r": (500.0, 300.0), "a": (0.0, 0.0), "b": (9.0, 9.0)}         # (only the root counts)
    off = groupOffset(rel, ["r"], now, now)
    self.assertEqual((rel["r"][0] + off[0], rel["r"][1] + off[1]), (500.0, 300.0))
    # a child added: the root stays where it is (not back at the top left)
    pos2, _ = balloonPositions(["r"], {"r": ["a", "b", "c"]}, self.sizes, spacing=10)
    rel2 = topLefts(pos2, self.sizes)
    now2 = {n: (rel[n][0] + off[0], rel[n][1] + off[1]) for n in rel}
    off2 = groupOffset(rel2, ["r"], now2, {**now2, "c": (0.0, 0.0)})
    self.assertEqual((rel2["r"][0] + off2[0], rel2["r"][1] + off2[1]), (500.0, 300.0))

  def test1610anchorFallsBack(self):
    rel = {"r": (0.0, 0.0), "a": (100.0, 0.0), "b": (0.0, 100.0)}
    # the root's new (unknown): the known nodes stay where they are, on average
    off = groupOffset(rel, ["r"], {"a": (110.0, 5.0), "b": (10.0, 105.0)}, {"r": (0.0, 0.0), "a": (110.0, 5.0), "b": (10.0, 105.0)})
    self.assertEqual(off, (10.0, 5.0))
    # nothing known: where the root is now (eg: just made)
    self.assertEqual(groupOffset(rel, ["r"], {}, {"r": (7.0, 8.0)}), (7.0, 8.0))
    self.assertIsNone(groupOffset(rel, ["r"], {}, {}))

  def test1620hubRingAnchoredByItsHubs(self):
    nbrs:dict = {}
    def link(a, b):
      nbrs.setdefault(a, []).append(b)
      nbrs.setdefault(b, []).append(a)
    for h in "pq":
      for i in range(3):
        link(h, f"{h}{i}")
    link("p", "q")
    sizes = {n: (50, 20) for n in nbrs}
    (hubs, kids), = hubForest(sorted(nbrs), nbrs)[0]
    rel = topLefts(hubPositions(hubs, kids, sizes, spacing=10)[0], sizes)
    now = {n: (x + 300, y - 40) for n, (x, y) in rel.items()}
    self.assertEqual(groupOffset(rel, hubs, now, now), (300.0, -40.0))  # as it is: it stays
    # a spoke added: the hubs stay where they were, on average
    link("p", "p3")
    sizes["p3"] = (50, 20)
    (hubs2, kids2), = hubForest(sorted(nbrs), nbrs)[0]
    rel2 = topLefts(hubPositions(hubs2, kids2, sizes, spacing=10)[0], sizes)
    off = groupOffset(rel2, hubs2, now, {**now, "p3": (0.0, 0.0)})
    for axis in (0, 1):
      before = sum(now[h][axis] for h in hubs) / 2
      after = sum(rel2[h][axis] + off[axis] for h in hubs2) / 2
      self.assertLessEqual(abs(before - after), 0.5)

  def test1700separateLeavesClearGroups(self):
    sizes = {n: (40, 20) for n in "abcd"}
    groups = [{"a": (0.0, 0.0), "b": (100.0, 0.0)}, {"c": (0.0, 0.0), "d": (0.0, 100.0)}]
    offsets = [(0.0, 0.0), (500.0, 500.0)]
    self.assertEqual(separateGroups(groups, offsets, sizes, gap=10), offsets)
    # one in a gap in the other (node by node, not by their boxes): left there
    offsets = [(0.0, 0.0), (45.0, 0.0)]
    groups = [{"a": (0.0, 0.0), "b": (100.0, 0.0)}, {"c": (0.0, 0.0)}]
    self.assertEqual(separateGroups(groups, offsets, sizes, gap=5), offsets)

  def test1710separateMovesTheLaterTheLeast(self):
    sizes = {n: (40, 20) for n in "abc"}
    groups = [{"a": (0.0, 0.0), "b": (0.0, 30.0)}, {"c": (0.0, 0.0)}]
    shifts = separateGroups(groups, [(0.0, 0.0), (30.0, 5.0)], sizes, gap=10)
    self.assertEqual(shifts[0], (0.0, 0.0))                              # the first stays
    self.assertEqual(shifts[1], (50.0, 5.0))                             # the other just clear, to the right
    self.assertEqual(overlapping(self.tlBoxes(groups, shifts, sizes)), [])

  def test1720separateRandomIsClearAndStable(self):
    rnd = random.Random(17)
    for _ in range(20):
      groups, offsets, sizes, key = [], [], {}, 0
      for _ in range(rnd.randint(2, 6)):
        n = rnd.randint(1, 15)
        sz, kids = randomTree(rnd, n)
        sz = {key + i: s for i, s in sz.items()}
        kids = {key + p: [key + k for k in ks] for p, ks in kids.items()}
        sizes.update(sz)
        groups.append(topLefts(balloonPositions([key], kids, sz, spacing=5)[0], sz))
        offsets.append((float(rnd.randint(0, 600)), float(rnd.randint(0, 600))))
        key += n
      shifts = separateGroups(groups, offsets, sizes, gap=10)
      bs = self.tlBoxes(groups, shifts, sizes)
      grown = {n: (b[0] - 5, b[1] - 5, b[2] + 5, b[3] + 5) for n, b in bs.items()}  # (gap apart: half each)
      groupOf = {n: i for i, g in enumerate(groups) for n in g}
      self.assertEqual([p for p in overlapping(grown) if groupOf[p[0]] != groupOf[p[1]]], [])
      self.assertEqual(separateGroups(groups, shifts, sizes, gap=10), shifts)  # (again: nothing moves)

  def test1800pinnedSpokeCutOut(self):
    edges = [("h", "a"), ("h", "b"), ("h", "c"), ("c", "g"), ("c", "k")]
    nbrs:dict = {}
    for a, b in edges:
      nbrs.setdefault(a, []).append(b)
    nodes = ["a", "b", "c", "g", "h", "k"]
    groups, _ = hubForest(nodes, nbrs, minSpokes=3, pinned=["c"])
    self.assertEqual([hubs for hubs, _ in groups], [["h"], ["c"]])
    kids = groups[0][1]
    self.assertEqual(sorted(kids["h"]), ["a", "b"])                     # c's no longer under h ...
    self.assertEqual(sorted(groups[1][1]["c"]), ["g", "k"])              # ... and takes its spokes with it
    pos, _ = hubPositions(*groups[0], {n: (40, 20) for n in nodes}, spacing=10)
    self.assertEqual(sorted(pos), ["a", "b", "h"])
    pos, _ = hubPositions(*groups[1], {n: (40, 20) for n in nodes}, spacing=10)
    self.assertEqual(sorted(pos), ["c", "g", "k"])

  def test1810pinnedHubLeavesTheRing(self):
    nbrs:dict = {}
    def link(a, b):
      nbrs.setdefault(a, []).append(b)
      nbrs.setdefault(b, []).append(a)
    for h in "pqr":
      for i in range(3):
        link(h, f"{h}{i}")
    link("p", "q"); link("q", "r")
    groups, _ = hubForest(sorted(nbrs), nbrs, pinned=["r"])
    self.assertEqual(len(groups), 2)
    self.assertNotIn("r", groups[0][0])
    self.assertEqual(groups[1][0], ["r"])
    pos, _ = hubPositions(*groups[1], {n: (40, 20) for n in nbrs}, spacing=10)
    self.assertEqual(sorted(pos), ["r", "r0", "r1", "r2"])
    # the only hub of its group pinned: nothing to cut out
    groups2, _ = hubForest(sorted(nbrs), nbrs, pinned=["p", "q", "r"])
    self.assertEqual(sorted(h for hubs, _ in groups2 for h in hubs), ["p", "q", "r"])
    self.assertEqual(len(groups2), 3)

  def test1820pinnedChildIsARootWhereItsDropped(self):
    # (as TreeLayout.structure() does: a pinned child's the root of a tree of its own)
    pos, _ = balloonPositions(["r", "a"], {"r": ["b"], "a": ["c", "d"]}, self.sizes, spacing=10)
    trees = {"r": ["r", "b"], "a": ["a", "c", "d"]}
    now = {"r": (100.0, 100.0), "a": (900.0, 50.0), "b": (0.0, 0.0), "c": (0.0, 0.0), "d": (0.0, 0.0)}
    for root, members in trees.items():
      rel = topLefts({n: pos[n] for n in members}, self.sizes)
      off = groupOffset(rel, [root], now, now)
      self.assertEqual((rel[root][0] + off[0], rel[root][1] + off[1]), now[root])

if __name__ == "__main__":
  unittest.main()
