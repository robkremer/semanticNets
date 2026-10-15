'''
Round layouts (static: "arrange now"): a view's nodes arranged in circles.

  - *BalloonLayout* ("balloon"): trees, by a relation type, as balloons: each
    node's children in a ring around it, each child's subtree a balloon of its
    own, fanned out away from its parent.
  - *RadialLayout* ("radial"): trees, by a relation type, in rings: each
    root in the middle, each depth on a circle around it, each subtree in a
    wedge as wide as it needs.
  - *HubLayout* ("hubs"): by every relation shown: the nodes with the most
    relations are the hubs, each with the nodes nearest it (its spokes) in a
    balloon around it, and the hubs of a connected group on a circle, their
    spokes fanned out away from its middle (where the relations between the
    hubs go).

The geometry, on its own (no view): *balloonPositions()*, *radialPositions()*,
*hubForest()* and *hubPositions()*. Each node's taken to be a circle, as wide
as its box's diagonal (so nothing overlaps, however it's turned). A node's
children's subtrees go round it each in its own wedge: the angle its nodes'
circles take up, seen from the node -- so none overlap, nor do the relations
from parents to children cross.

Created on Oct 14, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
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
from __future__ import annotations
import math
from collections import deque
from typing import Any, Generic, Hashable, Mapping, Optional, Sequence, TypeVar, override
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import LayoutHeuristic, LayoutParameter, registerLayout, layoutSize, STATIC
from sn.view.graphics.treeLayout import TreeLayout, PARENT_ENDS

K = TypeVar("K", bound=Hashable)

OTHERS = ("rows", "leave")
'''What a round layout does with the nodes it doesn't arrange (in no tree; for
the hubs, related to nothing): puts them in rows after the rest; or leaves
them where they are.'''

PARENT_GAP = math.pi / 2
'''The wedge (radians) a balloon's node keeps clear of its children, toward
its parent: where the relation from its parent comes in.'''

ROW_LENGTH = 1600.0
'''The longest a row of balloons (or radial trees, or groups of hubs) is,
unless one's longer: they're put one after another along it, then in another
row below.'''

def radius(size:tuple[float, float]) -> float:
  '''
  :param size: A box's (width, height).
  :type size: tuple[float, float]
  :returns: The radius of the circle round it: half its diagonal.
  :rtype: float
  '''
  return math.hypot(size[0], size[1]) / 2

def _forest(roots:list[K], children:Mapping[K, Sequence[K]]) -> tuple[list[K], dict[K, list[K]]]:
  '''
  :returns: The roots, without those met in a tree before; and each node's
    children, each node under the first parent it's met under, nearest the
    root (a node met again is left out there).
  '''
  seen:set[K] = set()
  kept:list[K] = []
  kids:dict[K, list[K]] = {}
  for root in roots:
    if root in seen:
      continue
    kept.append(root)
    seen.add(root)
    queue = deque([root])
    while queue:
      n = queue.popleft()
      ks:list[K] = []
      for k in children.get(n, ()):
        if k not in seen:
          seen.add(k)
          ks.append(k)
      kids[n] = ks
      queue.extend(ks)
  return kept, kids

Circle = tuple[float, float, float]
"A circle: (x, y, radius)."

def _extent(circles:Sequence[Circle], d:float, pad:float) -> tuple[float, float]|None:
  '''
  :param circles: A subtree's nodes' circles, from its root, facing along x.
  :param d: How far out from the middle its root is (facing out).
  :param pad: How much bigger to take each circle to be.
  :returns: The angles (radians: from the way to its root) the circles take
    up, seen from the middle: (least, most) -- or None if one's on the middle.
  '''
  lo, hi = math.inf, -math.inf
  for x, y, r in circles:
    px = d + x
    dist = math.hypot(px, y)
    if r + pad >= dist:
      return None
    phi, h = math.atan2(y, px), math.asin((r + pad) / dist)
    lo, hi = min(lo, phi - h), max(hi, phi + h)
  return lo, hi

def _ring(groups:Sequence[Sequence[Circle]], avail:float, pad:float, least:Sequence[float],
          centred:bool) -> tuple[float, list[float]]:
  '''
  Put some subtrees round a ring, each facing out: as small a ring as they
  fit round without overlapping -- the angles each takes up, seen from the
  middle (each circle *pad* bigger), adding up to no more than *avail* -- and
  then spread out evenly over it.

  :param groups: Each subtree's nodes' circles, from its root, facing along x.
  :param avail: The angle (radians) they may take up.
  :param pad: Half the least space between them.
  :param least: The least distance from the middle each may be.
  :param centred: If True, they go all round, the first straight ahead (at
    angle 0); else they're spread over -avail/2 .. avail/2.
  :returns: The ring's radius; and the angle of each subtree's root on it.
  '''
  def extents(d:float) -> list[tuple[float, float]]|None:
    ret = []
    for g in groups:
      e = _extent(g, d, pad)
      if e is None:
        return None
      ret.append(e)
    return ret
  def fits(d:float) -> bool:
    es = extents(d)
    return es is not None and sum(hi - lo for lo, hi in es) <= avail
  lo = max(least)
  if not fits(lo):
    hi = max(lo, 1.0) * 2
    while not fits(hi) and hi < 1e9:
      hi *= 2
    for _ in range(50):
      mid = (lo + hi) / 2
      if fits(mid):
        hi = mid
      else:
        lo = mid
    lo = hi
  es = extents(lo) or [(-avail / 2 / len(groups), avail / 2 / len(groups))] * len(groups)
  extra = (avail - sum(hi - lo_ for lo_, hi in es)) / len(groups) # (spread out evenly over what's free)
  at = es[0][0] - extra / 2 if centred else -avail / 2
  angles = []
  for elo, ehi in es:
    angles.append(at - elo + extra / 2)
    at += ehi - elo + extra
  return lo, angles

def _turned(circles:Sequence[Circle], d:float, a:float) -> list[Circle]:
  ":returns: *circles* (facing along x) with their root *d* out from the middle at angle *a*, facing out."
  c, s = math.cos(a), math.sin(a)
  return [(d * c + x * c - y * s, d * s + x * s + y * c, r) for x, y, r in circles]

class _Balloons(Generic[K]):
  '''
  Balloons (see *balloonPositions()*): how big each node's is (*measure()*),
  and where each node of one goes (*place()*).
  '''
  def __init__(self, kids:Mapping[K, Sequence[K]], sizes:Mapping[K, tuple[float, float]], spacing:float,
               edgeRoom:Optional[Mapping[K, float]], parentGap:float):
    self.kids, self.sizes, self.spacing, self.parentGap = kids, sizes, spacing, parentGap
    self.room = (lambda k: edgeRoom.get(k, spacing)) if edgeRoom else (lambda k: spacing)
    self.circles:dict = {}
    "The circles of each node measured (and not yet in its parent's), and its subtree's: from it, facing along x."
    self.D:dict = {}
    "The radius of the ring each node's children are on."
    self.offsets:dict = {}
    "Each node's children, and the angle of each from the way the node faces."

  def measure(self, n:K, isRoot:bool) -> list[Circle]:
    '''
    :param n: The root of a balloon.
    :param isRoot: Whether its children go all round it (else they keep
      clear of *parentGap*, behind it).
    :returns: The circles of its balloon's nodes, from it, facing along x (it first).
    '''
    order:list = []
    stack = [n]
    while stack:
      m = stack.pop()
      order.append(m)
      stack.extend(self.kids.get(m, ()))
    for m in reversed(order):
      self._one(m, isRoot and m == n)
    return self.circles.pop(n)

  def _one(self, m, isRoot:bool) -> None:
    r = radius(self.sizes[m])
    ks = self.kids.get(m, ())
    if not ks:
      self.circles[m], self.D[m], self.offsets[m] = [(0.0, 0.0, r)], 0.0, []
      return
    groups = [self.circles.pop(k) for k in ks]
    # (each child's circle clear of this one's by its room; the rest of its subtree by the spacing)
    least = [max(-x + math.sqrt(max(0.0, (r + (self.room(k) if i == 0 else self.spacing) + cr) ** 2 - y * y))
                 for i, (x, y, cr) in enumerate(g)) for k, g in zip(ks, groups)]
    avail = 2 * math.pi if isRoot else 2 * math.pi - self.parentGap
    d, angles = _ring(groups, avail, self.spacing / 2, least, centred=isRoot)
    circles:list[Circle] = [(0.0, 0.0, r)]
    for g, a in zip(groups, angles):
      circles += _turned(g, d, a)
    self.circles[m], self.D[m], self.offsets[m] = circles, d, list(zip(ks, angles))

  def place(self, n:K, centre:tuple[float, float], facing:float, out:dict) -> None:
    '''
    Put the centre of each node of *n*'s balloon (measured) in *out*.

    :param n: The root of a balloon.
    :param centre: Where its centre goes.
    :param facing: The way (radians) it faces: its children are spread
      round that way (all round it, if it was measured as a root).
    :param out: Where to put them.
    '''
    stack = [(n, centre, facing)]
    while stack:
      m, (cx, cy), f = stack.pop()
      out[m] = (cx, cy)
      d = self.D[m]
      for k, phi in self.offsets[m]:
        a = f + phi
        stack.append((k, (cx + d * math.cos(a), cy + d * math.sin(a)), a))

def balloonPositions(roots:list[K], children:Mapping[K, Sequence[K]], sizes:Mapping[K, tuple[float, float]], *,
                     spacing:float=20.0, edgeRoom:Optional[Mapping[K, float]]=None,
                     parentGap:float=PARENT_GAP) -> tuple[dict[K, tuple[float, float]], list[tuple[K, list[K], float]]]:
  '''
  Lay out some trees as balloons, each on its own: each node's children on a
  ring around it -- all round a root, from the top, clockwise; else spread
  round the way away from its parent, keeping *parentGap* behind it clear --
  each child's subtree a balloon of its own, each in its own wedge (the angle
  its nodes take up, seen from the parent, with *spacing* between), so none
  overlap (nor do the relations from parents to children cross). Each ring's
  as small as it can be, but far enough out for each child's *edgeRoom* (and
  for the rest of its subtree to be *spacing* clear of the parent).

  :param roots: The trees' roots.
  :type roots: list[K]
  :param children: Each node's children, in order. Each node is laid out
    once: under the first parent it's met under, nearest the root.
  :type children: Mapping[K, Sequence[K]]
  :param sizes: Each node's (width, height).
  :type sizes: Mapping[K, tuple[float, float]]
  :param spacing: The least space between neighbouring balloons.
  :type spacing: float
  :param edgeRoom: The space between a child (its circle) and its parent's, if
    not *spacing*: eg: for the label of the relation to it.
  :type edgeRoom: Mapping[K, float] | None
  :param parentGap: The angle (radians) a node keeps clear of its children, toward its parent.
  :type parentGap: float
  :returns: Where each node's centre goes, each tree's root at (0, 0); and
    each tree: its root, its nodes, and the radius of a circle round it.
  :rtype: tuple[dict[K, tuple[float, float]], list[tuple[K, list[K], float]]]
  '''
  kept, kids = _forest(roots, children)
  b = _Balloons(kids, sizes, spacing, edgeRoom, parentGap)
  ret:dict[K, tuple[float, float]] = {}
  trees:list[tuple[K, list[K], float]] = []
  for root in kept:
    circles = b.measure(root, True)
    out:dict[K, tuple[float, float]] = {}
    b.place(root, (0.0, 0.0), -math.pi / 2, out) # (facing up: its first child at the top)
    ret.update(out)
    trees.append((root, list(out), max(math.hypot(x, y) + r for x, y, r in circles)))
  return ret, trees

def radialPositions(roots:list[K], children:Mapping[K, Sequence[K]], sizes:Mapping[K, tuple[float, float]], *,
                    spacing:float=20.0, edgeRoom:Optional[Mapping[K, float]]=None) -> tuple[dict[K, tuple[float, float]], list[tuple[K, list[K], float]]]:
  '''
  Lay out some trees radially, each on its own: its root in the middle, each
  depth on a circle round it, and each node's subtree in a wedge (its
  children dividing it, from the top, clockwise), as wide as its leaves need
  (their circles, *spacing* apart), each node in the middle of its own. Each
  circle's as small as it can be with no node on another: far enough out
  from the one before for the nodes on both (and *edgeRoom*), and for each
  node on it to fit in its wedge.

  :param roots: The trees' roots.
  :type roots: list[K]
  :param children: Each node's children, in order (see *balloonPositions()*).
  :type children: Mapping[K, Sequence[K]]
  :param sizes: Each node's (width, height).
  :type sizes: Mapping[K, tuple[float, float]]
  :param spacing: The least space between neighbouring nodes.
  :type spacing: float
  :param edgeRoom: The space between a child (its circle) and its parent's, if
    not *spacing*: eg: for the label of the relation to it.
  :type edgeRoom: Mapping[K, float] | None
  :returns: Where each node's centre goes, each tree's root at (0, 0); and
    each tree: its root, its nodes, and the radius of a circle round it.
  :rtype: tuple[dict[K, tuple[float, float]], list[tuple[K, list[K], float]]]
  '''
  kept, kids = _forest(roots, children)
  room = (lambda k: edgeRoom.get(k, spacing)) if edgeRoom else (lambda k: spacing)
  ret:dict[K, tuple[float, float]] = {}
  trees:list[tuple[K, list[K], float]] = []
  for root in kept:
    order, depth = [root], {root: 0}
    i = 0
    while i < len(order):
      n = order[i]
      i += 1
      for k in kids[n]:
        depth[k] = depth[n] + 1
        order.append(k)
    weight:dict[K, float] = {}
    for n in reversed(order):
      weight[n] = max(2 * radius(sizes[n]) + spacing, sum(weight[k] for k in kids[n]))
    span, start, angle = {root: 2 * math.pi}, {root: -math.pi / 2}, {root: 0.0}
    for n in order:
      total = sum(weight[k] for k in kids[n])
      s = start[n]
      for k in kids[n]:
        span[k] = span[n] * weight[k] / total
        start[k], angle[k] = s, s + span[k] / 2
        s += span[k]
    deepest = max(depth.values())
    maxR, maxRoom = [0.0] * (deepest + 1), [0.0] * (deepest + 1)
    for n, d in depth.items():
      maxR[d] = max(maxR[d], radius(sizes[n]))
      if d:
        maxRoom[d] = max(maxRoom[d], room(n))
    rho = [0.0]
    for d in range(1, deepest + 1):
      need = rho[-1] + maxR[d - 1] + maxR[d] + maxRoom[d]
      for n in order:
        if depth[n] == d: # (its circle in its wedge)
          need = max(need, (radius(sizes[n]) + spacing / 2) / math.sin(min(span[n], math.pi) / 2))
      rho.append(need)
    for n in order:
      p = rho[depth[n]]
      ret[n] = (p * math.cos(angle[n]), p * math.sin(angle[n]))
    trees.append((root, order, max(rho[depth[n]] + radius(sizes[n]) for n in order)))
  return ret, trees

def hubForest(nodes:Sequence[K], neighbours:Mapping[K, Sequence[K]],
              minSpokes:int=3) -> tuple[list[tuple[list[K], dict[K, list[K]]]], list[K]]:
  '''
  Find the hubs of a graph, and their spokes: in each connected group of
  nodes, the hubs are those with at least *minSpokes* neighbours (or, if
  none has, the one with the most), the most first; every other node is a
  spoke of the hub nearest it (the first of those as near), under the node
  next nearer it. The hubs are in order round a ring: each after the one
  most related to the one before (the relations between their spokes too).

  :param nodes: The nodes, in order.
  :type nodes: Sequence[K]
  :param neighbours: What each is related to (both ways), in order.
  :type neighbours: Mapping[K, Sequence[K]]
  :param minSpokes: The least neighbours a hub has.
  :type minSpokes: int
  :returns: Each connected group of more than one node (in the order of
    *nodes*): its hubs, in order round its ring, and each node's children
    (the hubs the roots); and the nodes related to nothing.
  :rtype: tuple[list[tuple[list[K], dict[K, list[K]]]], list[K]]
  '''
  index = {n: i for i, n in enumerate(nodes)}
  nbrs = {n: list(dict.fromkeys(m for m in neighbours.get(n, ()) if m in index and m != n)) for n in nodes}
  for n in nodes: # (both ways)
    for m in nbrs[n]:
      if n not in nbrs[m]:
        nbrs[m].append(n)
  degree = {n: len(nbrs[n]) for n in nodes}
  groups:list[tuple[list[K], dict[K, list[K]]]] = []
  isolated:list[K] = []
  seen:set[K] = set()
  for first in nodes:
    if first in seen:
      continue
    comp = [first]
    seen.add(first)
    i = 0
    while i < len(comp):
      for m in nbrs[comp[i]]:
        if m not in seen:
          seen.add(m)
          comp.append(m)
      i += 1
    if len(comp) == 1:
      isolated.append(first)
      continue
    hubs = sorted((n for n in comp if degree[n] >= minSpokes), key=lambda n: (-degree[n], index[n])) \
           or [min(comp, key=lambda n: (-degree[n], index[n]))]
    owner = {h: h for h in hubs}
    kids:dict[K, list[K]] = {n: [] for n in comp}
    queue = deque(hubs)
    while queue:
      n = queue.popleft()
      for m in nbrs[n]:
        if m not in owner:
          owner[m] = owner[n]
          kids[n].append(m)
          queue.append(m)
    links:dict[tuple[K, K], int] = {}
    for n in comp:
      for m in nbrs[n]:
        a, b = owner[n], owner[m]
        if a != b:
          links[(a, b)] = links.get((a, b), 0) + 1
    ring = [hubs[0]]
    rest = hubs[1:]
    while rest:
      last = ring[-1]
      nxt = max(rest, key=lambda h: (links.get((last, h), 0), sum(links.get((r, h), 0) for r in ring), -index[h]))
      ring.append(nxt)
      rest.remove(nxt)
    groups.append((ring, kids))
  return groups, isolated

def hubPositions(hubs:list[K], children:Mapping[K, Sequence[K]], sizes:Mapping[K, tuple[float, float]], *,
                 spacing:float=20.0, edgeRoom:Optional[Mapping[K, float]]=None,
                 parentGap:float=PARENT_GAP) -> tuple[dict[K, tuple[float, float]], float]:
  '''
  Lay out a connected group of hubs and their spokes (see *hubForest()*):
  each hub's spokes in a balloon round it (see *balloonPositions()*), and the
  hubs on a ring, in order (from the top, clockwise), their spokes spread
  round the way away from its middle (keeping *parentGap* toward the middle
  clear, for the relations between the hubs). The ring's as small as it can
  be with each hub's balloon in its own wedge (as for *balloonPositions()*). A
  single hub's balloon is all round it.

  :param hubs: The hubs, in order round the ring.
  :type hubs: list[K]
  :param children: Each node's children (spokes, and their spokes).
  :type children: Mapping[K, Sequence[K]]
  :param sizes: Each node's (width, height).
  :type sizes: Mapping[K, tuple[float, float]]
  :param spacing: The least space between neighbouring balloons.
  :type spacing: float
  :param edgeRoom: As for *balloonPositions()*.
  :type edgeRoom: Mapping[K, float] | None
  :param parentGap: As for *balloonPositions()*.
  :type parentGap: float
  :returns: Where each node's centre goes, the ring's middle at (0, 0); and
    the radius of a circle round them all.
  :rtype: tuple[dict[K, tuple[float, float]], float]
  '''
  b = _Balloons(children, sizes, spacing, edgeRoom, parentGap)
  out:dict[K, tuple[float, float]] = {}
  if len(hubs) == 1:
    b.measure(hubs[0], True)
    b.place(hubs[0], (0.0, 0.0), -math.pi / 2, out)
  else:
    groups = [b.measure(h, False) for h in hubs]
    least = [max(-x + math.sqrt(max(0.0, (spacing / 2 + r) ** 2 - y * y)) for x, y, r in g) for g in groups]
    d, angles = _ring(groups, 2 * math.pi, spacing / 2, least, centred=True)
    for h, a in zip(hubs, angles):
      a -= math.pi / 2 # (the first at the top)
      b.place(h, (d * math.cos(a), d * math.sin(a)), a, out)
  return out, max(math.hypot(x, y) + radius(sizes[n]) for n, (x, y) in out.items())

class _RoundLayout(LayoutHeuristic):
  '''
  What the round layouts share: putting their groups (trees, or hubs' groups)
  in rows, the nodes they don't arrange in rows after them (see *OTHERS*),
  and the labels of the relations from parents to children between them.
  '''
  CATEGORIES = (STATIC,)

  def _tree(self) -> TreeLayout:
    ":returns: A tree layout with its parameters: for what's arranged, and its trees."
    kw = {k: v for k, v in self.params.items() if k in ("relation", "parentEnd", "spacing")}
    return TreeLayout(self.view, **kw)

  def _arrangeGroups(self, tree:TreeLayout, groups:list[dict[VNode, tuple[float, float]]],
                     sizes:dict[VNode, tuple[float, float]], others:list[VNode]) -> dict[VNode, tuple[float, float]]:
    '''
    :param tree: A tree layout (see *_tree()*): for the rows of *others*.
    :type tree: TreeLayout
    :param groups: Where each group's nodes' centres go, on its own.
    :type groups: list[dict[VNode, tuple[float, float]]]
    :param sizes: Every node's (width, height).
    :type sizes: dict[VNode, tuple[float, float]]
    :param others: The nodes not in a group.
    :type others: list[VNode]
    :returns: Where they go (their top left): the groups one after another
      in rows (see *ROW_LENGTH*), from the top left of what's arranged, and
      *others* in rows after them (or left where they are: see *OTHERS*).
    :rtype: dict[VNode, tuple[float, float]]
    '''
    spacing = float(self.params["spacing"])
    gap = 2 * spacing
    everything = [n for g in groups for n in g] + others
    bbs = [n.boundingBox() for n in everything]
    x0, y0 = (min(b[0] for b in bbs), min(b[1] for b in bbs)) if bbs else (40.0, 40.0)
    tops = []
    for g in groups:
      tops.append({n: (cx - sizes[n][0] / 2, cy - sizes[n][1] / 2) for n, (cx, cy) in g.items()})
    boxes = [[min(p[0] for p in t.values()), min(p[1] for p in t.values()),
              max(p[0] + sizes[n][0] for n, p in t.items()), max(p[1] + sizes[n][1] for n, p in t.items())] for t in tops]
    limit = max([ROW_LENGTH] + [b[2] - b[0] for b in boxes])
    ret:dict[VNode, tuple[float, float]] = {}
    x, y, rowHeight = x0, y0, 0.0
    for t, b in zip(tops, boxes):
      w, h = b[2] - b[0], b[3] - b[1]
      if x > x0 and x + w > x0 + limit:
        x, y, rowHeight = x0, y + rowHeight + gap, 0.0
      for n, (px, py) in t.items():
        ret[n] = (px - b[0] + x, py - b[1] + y)
      x, rowHeight = x + w + gap, max(rowHeight, h)
    if others and self.params["others"] == "rows":
      cursor = y + rowHeight + gap if groups else y0
      ret.update(tree._rows(others, sizes, cursor, x0, y0, [(None, [x0, y0, x0 + limit, y0])])) #type: ignore[list-item]
    return {n: (float(round(px)), float(round(py))) for n, (px, py) in ret.items()}

  @staticmethod
  def _labelTargets(positions:dict[VNode, tuple[float, float]], sizes:dict[VNode, tuple[float, float]],
                    edges:list[tuple[VNode, VNode, VRelation]]) -> dict[VObject, tuple[float, float]]:
    '''
    :param edges: (parent, child, relation): the relations whose labels to put.
    :type edges: list[tuple[VNode, VNode, VRelation]]
    :returns: Where each relation's label goes (its top left): on the line
      between its parent's and child's centres, in the middle of the space
      between their circles (see *radius()*).
    :rtype: dict[VObject, tuple[float, float]]
    '''
    ret:dict[VObject, tuple[float, float]] = {}
    for p, k, r in edges:
      if p not in positions or k not in positions:
        continue
      (px, py), (kx, ky) = positions[p], positions[k]
      pc = (px + sizes[p][0] / 2, py + sizes[p][1] / 2)
      kc = (kx + sizes[k][0] / 2, ky + sizes[k][1] / 2)
      d = math.hypot(kc[0] - pc[0], kc[1] - pc[1])
      if d == 0:
        continue
      t = (radius(sizes[p]) + d - radius(sizes[k])) / 2
      lw, lh = layoutSize(r)
      x, y = pc[0] + (kc[0] - pc[0]) * t / d, pc[1] + (kc[1] - pc[1]) * t / d
      ret[r] = (float(round(x - lw / 2)), float(round(y - lh / 2)))
    return ret

  def _otherLabels(self, positions:dict[VNode, tuple[float, float]], sizes:dict[VNode, tuple[float, float]],
                   edges:list[tuple[VNode, VNode, VRelation]]) -> dict[VObject, tuple[float, float]]:
    '''
    :param edges: The relations whose labels are put already (see *_labelTargets()*).
    :type edges: list[tuple[VNode, VNode, VRelation]]
    :returns: Where the label of each other relation shown between the nodes
      arranged goes (its top left): midway between its ends' centres -- or,
      for more than one between the same two, side by side across the line
      between them, round the middle.
    :rtype: dict[VObject, tuple[float, float]]
    '''
    done = {id(r) for _, _, r in edges}
    pairs:dict[tuple[int, int], list[VRelation]] = {}
    for r in sorted((r for r in self.view.values() if isinstance(r, VRelation)), key=lambda r: r._id):
      if id(r) in done or not r._isConnected() or r.isHidden() or r.src is r.dst \
         or r.src not in positions or r.dst not in positions: #type: ignore[operator]
        continue
      pairs.setdefault((min(id(r.src), id(r.dst)), max(id(r.src), id(r.dst))), []).append(r)
    spacing = float(self.params["spacing"])
    ret:dict[VObject, tuple[float, float]] = {}
    for rs in pairs.values():
      a, b = rs[0].src, rs[0].dst
      (ax, ay), (bx, by) = positions[a], positions[b] #type: ignore[index]
      ac = (ax + sizes[a][0] / 2, ay + sizes[a][1] / 2) #type: ignore[index]
      bc = (bx + sizes[b][0] / 2, by + sizes[b][1] / 2) #type: ignore[index]
      d = math.hypot(bc[0] - ac[0], bc[1] - ac[1]) or 1.0
      across = (-(bc[1] - ac[1]) / d, (bc[0] - ac[0]) / d)
      sizesOf = [layoutSize(r) for r in rs]
      step = max(radius(sz) for sz in sizesOf) * 2 + spacing / 2
      for i, (r, (lw, lh)) in enumerate(zip(rs, sizesOf)):
        off = (i - (len(rs) - 1) / 2) * step
        x, y = (ac[0] + bc[0]) / 2 + across[0] * off, (ac[1] + bc[1]) / 2 + across[1] * off
        ret[r] = (float(round(x - lw / 2)), float(round(y - lh / 2)))
    return ret

  def _edgeRoom(self, edges:list[tuple[VNode, VNode, VRelation]]) -> dict[VNode, float]:
    ":returns: The room each child needs between it and its parent: its relation's label (its circle) and the spacing."
    spacing = float(self.params["spacing"])
    return {k: 2 * radius(layoutSize(r)) + spacing for _, k, r in edges}

class _TreeRoundLayout(_RoundLayout):
  '''
  A round layout of trees by a relation type (as *TreeLayout* finds them:
  see *TreeLayout.structure()*): *positions()* says where each tree's nodes go.
  '''
  PARAMETERS = (
    LayoutParameter("relation", "Relation", "relation", "isa",
                    note="Its subtypes too: each kind's children are together."),
    LayoutParameter("parentEnd", "The parent is the relation's", "choice", "destination", PARENT_ENDS,
                    note='Eg: the source for "includes" (a package includes its modules); '
                         'the destination for "isa" (a subtype isa its type).'),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("others", "Nodes in no tree", "choice", "rows", OTHERS,
                    note='"rows": in rows after the trees.'),
  )

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param kwargs: See *PARAMETERS*: relation (a relation type, or its name),
      parentEnd ("source" or "destination"), spacing, others (see *OTHERS*).
    '''
    super().__init__(view, **kwargs)
    if self.params["relation"] is None:
      self.params["relation"] = view.model.ISA
    if self.params["parentEnd"] not in PARENT_ENDS:
      raise ValueError(f'{type(self).__name__}: parentEnd must be one of {", ".join(PARENT_ENDS)}, not "{self.params["parentEnd"]}".')
    if self.params["others"] not in OTHERS:
      raise ValueError(f'{type(self).__name__}: others must be one of {", ".join(OTHERS)}, not "{self.params["others"]}".')

  @classmethod
  @override
  def parameterChanged(cls, view, name:str, values:dict[str, Any]) -> dict[str, Any]:
    "As *TreeLayout.parameterChanged()*: a relation type chosen, its parent end."
    return TreeLayout.parameterChanged(view, name, values)

  def positions(self, roots:list[VNode], kids:dict[VNode, list[VNode]], sizes:dict[VNode, tuple[float, float]],
                edgeRoom:dict[VNode, float]) -> tuple[dict[VNode, tuple[float, float]], list[tuple[VNode, list[VNode], float]]]:
    ":returns: As *balloonPositions()*."
    raise NotImplementedError

  @override
  def targets(self) -> dict[VObject, tuple[float, float]]:
    tree = self._tree()
    roots, children, parentRel, others, _ = tree.structure(dynamic=False)
    kids = {p: [k for g in gs for k in g] for p, gs in children.items()}
    nodes = [*roots, *(k for ks in kids.values() for k in ks), *others]
    sizes = {n: layoutSize(n) for n in nodes}
    edges = [(tree._ends(r)[0], k, r) for k, r in parentRel.items()]
    centres, trees = self.positions(roots, kids, sizes, self._edgeRoom(edges))
    groups = [{n: centres[n] for n in members} for _, members, _ in trees]
    positions = self._arrangeGroups(tree, groups, sizes, others)
    ret:dict[VObject, tuple[float, float]] = {n: p for n, p in positions.items()}
    ret.update(self._labelTargets(positions, sizes, edges))
    ret.update(self._otherLabels(positions, sizes, edges))
    return ret

@registerLayout
class BalloonLayout(_TreeRoundLayout):
  '''
  Arrange nodes as balloons (see *balloonPositions()*): trees by a relation
  type (*relation*) and its subtypes (as *TreeLayout* finds them), each
  node's children in a ring round it, each child's subtree a balloon of its
  own, spread round the way away from its parent. The trees are put one
  after another in rows, from the top left of what's arranged; the nodes in
  no tree in rows after them, or left where they are (*others*). Each tree
  relation's label goes on its line, between its ends.
  '''
  NAME = "balloon"

  @override
  def positions(self, roots, kids, sizes, edgeRoom):
    return balloonPositions(roots, kids, sizes, spacing=float(self.params["spacing"]), edgeRoom=edgeRoom)

@registerLayout
class RadialLayout(_TreeRoundLayout):
  '''
  Arrange nodes radially (see *radialPositions()*): trees by a relation type
  (*relation*) and its subtypes (as *TreeLayout* finds them), each root in
  the middle of its tree, each depth on a circle round it, each subtree in
  its own wedge. Otherwise as *BalloonLayout*.
  '''
  NAME = "radial"

  @override
  def positions(self, roots, kids, sizes, edgeRoom):
    return radialPositions(roots, kids, sizes, spacing=float(self.params["spacing"]), edgeRoom=edgeRoom)

@registerLayout
class HubLayout(_RoundLayout):
  '''
  Arrange nodes round hubs (see *hubForest()* and *hubPositions()*), by every
  relation shown: in each connected group, the nodes with at least
  *minSpokes* relations (to different nodes) are hubs, each with its spokes
  (the nodes nearest it) in a balloon round it, and the hubs on a circle,
  their spokes spread round away from its middle -- where the relations
  between them go. The groups are put one after another in rows, from the
  top left of what's arranged; the nodes related to nothing in rows after
  them, or left where they are (*others*). The label of the relation from
  each spoke's hub (or the spoke it's under) goes on its line, between its
  ends; the others' are left between their ends.

  Nodes in a context window (or that are one) aren't arranged.
  '''
  NAME = "hubs"
  PARAMETERS = (
    LayoutParameter("minSpokes", "A hub has at least this many relations", "int", 3,
                    note="In a group with no such node, the one with the most is its hub."),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("others", "Nodes related to nothing", "choice", "rows", OTHERS,
                    note='"rows": in rows after the rest.'),
  )

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param kwargs: See *PARAMETERS*: minSpokes, spacing, others (see *OTHERS*).
    '''
    super().__init__(view, **kwargs)
    if self.params["others"] not in OTHERS:
      raise ValueError(f'HubLayout: others must be one of {", ".join(OTHERS)}, not "{self.params["others"]}".')

  def graph(self) -> tuple[list[VNode], dict[VNode, list[VNode]], dict[tuple[VNode, VNode], VRelation]]:
    '''
    :returns: What's arranged: the nodes (as *TreeLayout.scope()*), by name;
      what each is related to (by a relation shown, either way), by name; and
      a relation between each pair of them (the first made), both ways round.
    :rtype: tuple[list[VNode], dict[VNode, list[VNode]], dict[tuple[VNode, VNode], VRelation]]
    '''
    name = lambda vo: (str(vo.modelObject.name).lower() if vo.modelObject is not None else "", vo._id)
    nodes = sorted(self._tree().scope()[0], key=name)
    ids = {id(n) for n in nodes}
    neighbours:dict[VNode, list[VNode]] = {n: [] for n in nodes}
    between:dict[tuple[VNode, VNode], VRelation] = {}
    rels = sorted((r for r in self.view.values() if isinstance(r, VRelation) and r._isConnected() and not r.isHidden()
                   and id(r.src) in ids and id(r.dst) in ids and r.src is not r.dst), key=lambda r: r._id)
    for r in rels:
      a, b = r.src, r.dst
      if (a, b) not in between:
        between[(a, b)] = between[(b, a)] = r #type: ignore[index]
        neighbours[a].append(b) #type: ignore[index, arg-type]
        neighbours[b].append(a) #type: ignore[index, arg-type]
    return nodes, {n: sorted(ns, key=name) for n, ns in neighbours.items()}, between

  @override
  def targets(self) -> dict[VObject, tuple[float, float]]:
    nodes, neighbours, between = self.graph()
    groups, isolated = hubForest(nodes, neighbours, max(1, int(self.params["minSpokes"])))
    sizes = {n: layoutSize(n) for n in nodes}
    spacing = float(self.params["spacing"])
    centres:list[dict[VNode, tuple[float, float]]] = []
    edges:list[tuple[VNode, VNode, VRelation]] = []
    for hubs, kids in groups:
      es = [(p, k, between[(p, k)]) for p, ks in kids.items() for k in ks]
      edges += es
      centres.append(hubPositions(hubs, kids, sizes, spacing=spacing, edgeRoom=self._edgeRoom(es))[0])
    positions = self._arrangeGroups(self._tree(), centres, sizes, isolated)
    ret:dict[VObject, tuple[float, float]] = {n: p for n, p in positions.items()}
    ret.update(self._labelTargets(positions, sizes, edges))
    ret.update(self._otherLabels(positions, sizes, edges))
    return ret
