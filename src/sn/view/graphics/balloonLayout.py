'''
Round layouts ("arrange now", and "keep arranged"): a view's nodes arranged in circles.

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

Kept arranged (see *_RoundLayout*), each group's laid out again after each
command, where it is (*groupOffset()*), and moved off any other
(*separateGroups()*).

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
from typing import Any, Callable, Collection, Generic, Hashable, Mapping, Optional, Sequence, TypeVar, override
from util.command import Command
from util.utils import Point
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import (LayoutHeuristic, LayoutParameter, LayoutMoves, FindFree, Direction,
                                     registerLayout, layoutSize, STATIC, DYNAMIC)
from sn.view.graphics.treeLayout import TreeLayout, isMember, isLink, PARENT_ENDS, NEAR_BIAS, _BoxIndex, nearestFree

K = TypeVar("K", bound=Hashable)

OTHERS = ("near", "rows", "leave")
'''What the balloon and radial layouts do with the nodes in no tree: put each
near the tree nodes it's related to, out beyond them, away from the middle of
their tree (see *placeNearGroups()*: those related to no tree in rows after
the trees); put them in rows after the trees; or leave them where they are.'''

TREES = ("joined", "apart")
'''What the balloon and radial layouts do with a tree whose root is related
(by any relation shown, but the trees') to a node in another tree: put it out
beyond that node, as if one of its children (see *_TreeRoundLayout._join()*);
or lay it out on its own, apart.'''

HUB_OTHERS = ("rows", "leave")
'''What the hub layout does with the nodes related to nothing: puts them in
rows after the rest; or leaves them where they are.'''

PARENT_GAP = math.pi / 2
'''The wedge (radians) a balloon's node keeps clear of its children, toward
its parent: where the relation from its parent comes in.'''

RADIAL_SPREAD = math.pi
'''The widest a node's children's wedges may be, side by side, in the radial layout
(see *radialPositions()*): the circles beyond it are moved out until they fit.'''

HUB_SPREAD = math.pi
'''The widest a hub layout's nodes below the hubs' own spokes spread their
children: so the branches keep going out, away from the hub, rather than
curling round it (see *hubPositions()*).'''

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
               edgeRoom:Optional[Mapping[K, float]], parentGap:float, spread:Optional[float]=None):
    self.kids, self.sizes, self.spacing, self.parentGap = kids, sizes, spacing, parentGap
    self.spread = spread
    "The widest a balloon's nodes below its root spread their children (else all but *parentGap*)."
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
      self._one(m, isRoot and m == n, m != n)
    return self.circles.pop(n)

  def _one(self, m, isRoot:bool, below:bool=False) -> None:
    r = radius(self.sizes[m])
    ks = self.kids.get(m, ())
    if not ks:
      self.circles[m], self.D[m], self.offsets[m] = [(0.0, 0.0, r)], 0.0, []
      return
    groups = [self.circles.pop(k) for k in ks]
    if below and self.spread is not None and len(ks) > 2: # (the biggest branches in the middle, going straight on)
      bySize = sorted(range(len(ks)), key=lambda i: (-len(groups[i]), i)) # (biggest first: from the middle out)
      middle:deque = deque()
      for j, i in enumerate(bySize):
        if j % 2:
          middle.appendleft(i)
        else:
          middle.append(i)
      ks, groups = [ks[i] for i in middle], [groups[i] for i in middle]
    # (each child's circle clear of this one's by its room; the rest of its subtree by the spacing)
    least = [max(-x + math.sqrt(max(0.0, (r + (self.room(k) if i == 0 else self.spacing) + cr) ** 2 - y * y))
                 for i, (x, y, cr) in enumerate(g)) for k, g in zip(ks, groups)]
    avail = 2 * math.pi if isRoot else 2 * math.pi - self.parentGap
    if below and self.spread is not None:
      avail = min(avail, self.spread)
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
  depth on a circle round it, and each node's subtree in a wedge just as wide
  as it needs -- the most, at any depth, that its nodes there take up (their
  circles, *spacing* apart), seen from the middle -- each node in the middle
  of its own, its children's wedges side by side (in order, clockwise) and
  centred on it, sharing out what's spare in its wedge -- but over no more
  than *RADIAL_SPREAD*: so each subtree stays close to the line out from the
  middle through its root, however big it is, rather than being spread
  round all the room its parent has. (The root's children go all round,
  from the top.) Each circle's as small as it can be: far enough out
  from the one before for the nodes on both (and *edgeRoom*), and for each
  node's children to fit in front of it (in the angle, seen from the middle,
  between the tangents to its circle where they meet the next) -- and all of
  them further out, in proportion, if the wedges wouldn't otherwise fit round.

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
    deepest = max(depth.values())
    maxR, maxRoom = [0.0] * (deepest + 1), [0.0] * (deepest + 1)
    for n, d in depth.items():
      maxR[d] = max(maxR[d], radius(sizes[n]))
      if d:
        maxRoom[d] = max(maxRoom[d], room(n))
    rho = [0.0]
    for d in range(1, deepest + 1):
      rho.append(max(rho[-1] + maxR[d - 1] + maxR[d] + maxRoom[d], maxR[d] + spacing / 2))
    # (the angle each node's circle takes up, seen from the middle; each subtree's: the most at any depth)
    own = lambda n: 2 * math.asin(min(1.0, (radius(sizes[n]) + spacing / 2) / rho[depth[n]]))
    def needs() -> dict[K, float]:
      need:dict[K, float] = {}
      for n in reversed(order):
        need[n] = max(own(n) if depth[n] else 0.0, sum(need[k] for k in kids[n]))
      return need
    atDepth:list[list[K]] = [[] for _ in range(deepest + 1)]
    for n in order:
      if kids[n]:
        atDepth[depth[n]].append(n)
    need = needs()
    for _ in range(1000):
      if need[root] > 2 * math.pi * (1 + 1e-9): # (too much for all round: every circle further out -- the angles shrink at least as much)
        f = need[root] / (2 * math.pi) * (1 + 1e-6)
        rho = [r * f for r in rho]
        need = needs()
        continue
      # (each node's children in front of it: within the angle seen from the middle where the next circle is
      # beyond the tangents to its own circle -- else the next circle out, and those beyond it, further out)
      grow = next((d for d in range(1, deepest) for n in atDepth[d]
                   if sum(need[k] for k in kids[n]) > RADIAL_SPREAD * (1 + 1e-9)), None)
      if grow is None:
        break
      step = 0.1 * rho[grow + 1]
      rho = rho[:grow + 1] + [r + step for r in rho[grow + 1:]]
      need = needs()
    angle, span = {root: 0.0}, {root: 2 * math.pi}
    for n in order: # (each node's children side by side, centred on it, sharing out what's spare in its wedge)
      if not kids[n]:
        continue
      total = sum(need[k] for k in kids[n])
      wide = span[n] if n is root else max(total, min(span[n], RADIAL_SPREAD))
      extra = (wide - total) / len(kids[n])
      s = -math.pi / 2 if n is root else angle[n] - wide / 2 # (the root's: all round, from the top)
      for k in kids[n]:
        span[k] = need[k] + extra
        angle[k] = s + span[k] / 2
        s += span[k]
    for n in order:
      p = rho[depth[n]]
      ret[n] = (p * math.cos(angle[n]), p * math.sin(angle[n]))
    trees.append((root, order, max(rho[depth[n]] + radius(sizes[n]) for n in order)))
  return ret, trees

def hubForest(nodes:Sequence[K], neighbours:Mapping[K, Sequence[K]], minSpokes:int=3,
              pinned:Collection[K]=()) -> tuple[list[tuple[list[K], dict[K, list[K]]]], list[K]]:
  '''
  Find the hubs of a graph, and their spokes: in each connected group of
  nodes, the hubs are those with at least *minSpokes* neighbours (or, if
  none has, the one with the most), the most first -- but only the core of
  them, those linked (through their spokes) to two others or more, once
  those linked to fewer are taken off, again and again (if none's left --
  eg: the hubs make a tree -- the one with the most neighbours, alone): one
  that hangs off another goes out beyond it, as its spokes do, so the ring
  is no bigger than the core needs. (Not a pinned hub: it's cut out, below.) Every
  other node is a spoke of the hub nearest it (the first of those as near),
  under the node next nearer it. The hubs are in order round a ring: each after the one
  most related to the one before (the relations between their spokes too).
  A *pinned* node (eg: one the user's put somewhere) that's a spoke, or one
  of a ring's hubs, is cut out of its group (with the spokes under it) as
  the only hub of a group of its own.

  :param nodes: The nodes, in order.
  :type nodes: Sequence[K]
  :param neighbours: What each is related to (both ways), in order.
  :type neighbours: Mapping[K, Sequence[K]]
  :param minSpokes: The least neighbours a hub has.
  :type minSpokes: int
  :param pinned: The nodes cut out of their groups.
  :type pinned: Collection[K]
  :returns: Each connected group of more than one node (in the order of
    *nodes*; one cut out right after the group it's cut from): its hubs, in
    order round its ring, and each node's children (the hubs the roots); and
    the nodes related to nothing.
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
    def spokes(hubs:list[K]) -> tuple[dict[K, K], dict[K, list[K]], dict[tuple[K, K], int]]:
      "Each node's hub, and its children (spokes of the nearest hub, under the node next nearer); and the links between the hubs' nodes."
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
      return owner, kids, links
    owner, kids, links = spokes(hubs)
    # (only the core on the ring: a hub linked to fewer than two others -- once those hanging off it are
    # taken off -- goes out beyond the hub it hangs off, in its balloon, as its spokes do)
    # (a pinned hub's cut out below anyway: never the core)
    core = {h for h in hubs if h not in pinned}
    pruned = True
    while pruned and core:
      pruned = False
      for h in list(core):
        if sum(1 for g in core if g is not h and (links.get((h, g)) or links.get((g, h)))) < 2:
          core.discard(h)
          pruned = True
    if len(core) < len(hubs):
      hubs = [h for h in hubs if h in core] or [next((h for h in hubs if h not in pinned), hubs[0])]
      owner, kids, links = spokes(hubs)
    ring = [hubs[0]]
    rest = hubs[1:]
    while rest:
      last = ring[-1]
      nxt = max(rest, key=lambda h: (links.get((last, h), 0), sum(links.get((r, h), 0) for r in ring), -index[h]))
      ring.append(nxt)
      rest.remove(nxt)
    groups.append((ring, kids))
    for p in comp: # (in the order met: a pinned node under another goes with neither)
      if p not in pinned:
        continue
      if p in ring:
        if len(ring) == 1:
          continue # (it's on its own already)
        ring.remove(p)
      else:
        parent = next(n for n in comp if p in kids[n])
        kids[parent].remove(p)
      groups.append(([p], kids)) # (the same children: each group's only its hubs' subtrees)
  return groups, isolated

def hubPositions(hubs:list[K], children:Mapping[K, Sequence[K]], sizes:Mapping[K, tuple[float, float]], *,
                 spacing:float=20.0, edgeRoom:Optional[Mapping[K, float]]=None,
                 parentGap:float=PARENT_GAP) -> tuple[dict[K, tuple[float, float]], float]:
  '''
  Lay out a connected group of hubs and their spokes (see *hubForest()*):
  each hub's spokes in a balloon round it (see *balloonPositions()*), and the
  hubs on a ring, in order (from the top, clockwise), their spokes spread
  round the way away from its middle (keeping *parentGap* toward the middle
  clear, for the relations between the hubs). Below the spokes, each node's
  children are spread over no more than *HUB_SPREAD*, facing away from it,
  the biggest branches in the middle: so the branches keep going out. The ring's as small as it can be with each
  hub's balloon in its own wedge (as for *balloonPositions()*). A single
  hub's balloon is all round it.

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
  b = _Balloons(children, sizes, spacing, edgeRoom, parentGap, spread=HUB_SPREAD)
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

def placeNearGroups(items:list[K], sizes:Mapping[K, tuple[float, float]], related:Mapping[K, Sequence[K]],
                    groups:list[dict[K, tuple[float, float]]], obstacles:Optional[list[list[Sequence[float]]]]=None, *,
                    spacing:float=20.0, room:Optional[Callable[[K, K], float]]=None,
                    bias:float=NEAR_BIAS) -> list[K]:
  '''
  Put nodes (eg: those in no tree) near the nodes they're related to, in
  laid-out groups (eg: trees, or hubs' groups): each in the group it's most
  related to (the first of those as much), out beyond the nodes it's related
  to there -- away from the group's middle (its (0, 0): eg: its root), from
  the middle of them, far enough for the relation's label (*room*) -- or, if
  that's taken, at the cheapest free place near there (see
  *treeLayout.nearestFree()*: moving back, toward the group's middle, costs
  *bias* times as much as moving on). Those related only to others of
  *items* are put once those are; those related to nothing placed aren't
  put anywhere.

  :param items: The nodes to put, in order.
  :type items: list[K]
  :param sizes: Every node's (width, height).
  :type sizes: Mapping[K, tuple[float, float]]
  :param related: What each of *items* is related to (in a group, or of *items*).
  :type related: Mapping[K, Sequence[K]]
  :param groups: Where each group's nodes' centres are, from its middle: those
    put are added to the group they go in.
  :type groups: list[dict[K, tuple[float, float]]]
  :param obstacles: For each group, boxes to keep clear of too (eg: relations' labels).
  :type obstacles: list[list[Sequence[float]]] | None
  :param spacing: The least space between a node put and anything else.
  :type spacing: float
  :param room: The space wanted between a node put and one it's related to
    (their circles: see *radius()*), if not *spacing*: eg: for the label of
    the relation between them.
  :type room: Callable[[K, K], float] | None
  :returns: Those not put (related to nothing placed).
  :rtype: list[K]
  '''
  roomFor = room or (lambda n, r: spacing)
  def box(n, c) -> list[float]:
    w, h = sizes[n]
    return [c[0] - w / 2, c[1] - h / 2, c[0] + w / 2, c[1] + h / 2]
  where = {n: gi for gi, g in enumerate(groups) for n in g}
  indexes = [_BoxIndex([box(n, c) for n, c in g.items()] + list((obstacles or [])[gi] if obstacles else []))
             for gi, g in enumerate(groups)]
  pending = list(items)
  while pending:
    ready = [n for n in pending if any(r in where for r in related.get(n, ()))]
    if not ready:
      break
    ready.sort(key=lambda n: -sum(1 for r in related.get(n, ()) if r in where)) # (the best anchored first; stable)
    for n in ready:
      rs = [r for r in related.get(n, ()) if r in where]
      counts:dict[int, int] = {}
      for r in rs:
        counts[where[r]] = counts.get(where[r], 0) + 1
      gi = max(counts, key=lambda i: (counts[i], -i))
      g = groups[gi]
      rs = [r for r in rs if where[r] == gi]
      ax, ay = sum(g[r][0] for r in rs) / len(rs), sum(g[r][1] for r in rs) / len(rs)
      length = math.hypot(ax, ay)
      if length < 1.0: # (at the middle: eg: related to the root -- straight down, then)
        ux, uy = 0.0, 1.0
      else:
        ux, uy = ax / length, ay / length
      out = max(radius(sizes[r]) + roomFor(n, r) for r in rs) + radius(sizes[n])
      w, h = sizes[n]
      x, y = nearestFree((w, h), (ax + ux * out - w / 2, ay + uy * out - h / 2), indexes[gi],
                         direction=(ux, uy), gap=spacing, bias=bias)
      g[n] = (x + w / 2, y + h / 2)
      where[n] = gi
      indexes[gi].add([x, y, x + w, y + h])
    done = set(ready)
    pending = [n for n in pending if n not in done]
  return pending

def topLefts(centres:Mapping[K, tuple[float, float]], sizes:Mapping[K, tuple[float, float]]) -> dict[K, tuple[float, float]]:
  ":returns: Where each node's top left is, from its centre: on whole units."
  return {n: (float(round(x - sizes[n][0] / 2)), float(round(y - sizes[n][1] / 2))) for n, (x, y) in centres.items()}

def groupOffset(group:Mapping[K, tuple[float, float]], refs:Sequence[K], known:Mapping[K, tuple[float, float]],
                current:Mapping[K, tuple[float, float]]) -> tuple[float, float]|None:
  '''
  Where a group laid out on its own (eg: a tree, from its root) goes, to stay
  where it is: so its *refs* (eg: its root, or its hubs) are -- on average --
  where they are now (in *known*); or, if none of them is known, so its
  nodes that are known are; or else its *refs*, or nodes, where they are
  (*current*: eg: just made).

  :param group: Where its nodes go (their top left), on its own.
  :type group: Mapping[K, tuple[float, float]]
  :param refs: Which of them it's anchored by.
  :type refs: Sequence[K]
  :param known: Where the nodes it knows are (their top left).
  :type known: Mapping[K, tuple[float, float]]
  :param current: Where all the nodes are (their top left).
  :type current: Mapping[K, tuple[float, float]]
  :returns: How far to move it (on whole units: so, if *group*'s on whole
    units, and as it was, it doesn't move); or None if none of its nodes is anywhere.
  :rtype: tuple[float, float] | None
  '''
  for where, among in ((known, refs), (known, group), (current, refs), (current, group)):
    ns = [n for n in among if n in where and n in group]
    if ns:
      return (float(round(sum(where[n][0] - group[n][0] for n in ns) / len(ns))),
              float(round(sum(where[n][1] - group[n][1] for n in ns) / len(ns))))
  return None

def separateGroups(groups:Sequence[Mapping[K, tuple[float, float]]], offsets:Sequence[tuple[float, float]],
                   sizes:Mapping[K, tuple[float, float]], *, gap:float=20.0) -> list[tuple[float, float]]:
  '''
  Move groups (eg: trees, each where it's anchored: see *groupOffset()*) so
  no node of one is on (or within *gap* of) a node of one before it: each, in
  order, the least distance it needs to (straight across, or up or down), or,
  if that won't do, below the rest. Node by node, not by the groups' boxes,
  so a group may be in a gap in another.

  :param groups: Where each group's nodes go (their top left), on its own.
  :type groups: Sequence[Mapping[K, tuple[float, float]]]
  :param offsets: How far each is moved, to start with.
  :type offsets: Sequence[tuple[float, float]]
  :param sizes: Each node's (width, height).
  :type sizes: Mapping[K, tuple[float, float]]
  :param gap: The least space between groups.
  :type gap: float
  :returns: How far each is moved (on whole units, if *offsets* are).
  :rtype: list[tuple[float, float]]
  '''
  index = _BoxIndex()
  placed:list[list[float]] = []
  ret:list[tuple[float, float]] = []
  for g, (dx, dy) in zip(groups, offsets):
    boxes = [[x + dx, y + dy, x + dx + sizes[n][0], y + dy + sizes[n][1]] for n, (x, y) in g.items()]
    sx, sy = _nearestClear(boxes, index, placed, gap) if boxes else (0.0, 0.0)
    ret.append((dx + sx, dy + sy))
    for b in boxes:
      b = [b[0] + sx, b[1] + sy, b[2] + sx, b[3] + sy]
      index.add(b)
      placed.append(b)
  return ret

def _nearestClear(boxes:list[list[float]], index:_BoxIndex, placed:list[list[float]], gap:float) -> tuple[float, float]:
  ":returns: The least move (see *separateGroups()*) that puts none of *boxes* on (or within *gap* of) one in *index*."
  def clearBy(sx:float, sy:float) -> bool:
    return not any(index.hits([b[0] + sx, b[1] + sy, b[2] + sx, b[3] + sy], gap) for b in boxes)
  if clearBy(0.0, 0.0):
    return 0.0, 0.0
  x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
  x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
  w, h = x1 - x0 + gap, y1 - y0 + gap
  near = [p for p in placed if p[0] < x1 + w and x0 - w < p[2] and p[1] < y1 + h and y0 - h < p[3]]
  candidates:set[tuple[float, float]] = set()
  for b in boxes:
    for p in near: # (just clear of it, each way)
      candidates.update(((float(math.ceil(p[2] + gap - b[0])), 0.0), (float(math.floor(p[0] - gap - b[2])), 0.0),
                         (0.0, float(math.ceil(p[3] + gap - b[1]))), (0.0, float(math.floor(p[1] - gap - b[3])))))
  for sx, sy in sorted(candidates, key=lambda c: (math.hypot(*c), c)):
    if clearBy(sx, sy):
      return sx, sy
  return 0.0, float(math.ceil(max(p[3] for p in placed) + gap - y0)) # (below everything)

def _byName(vo:VObject) -> tuple[str, int]:
  return (str(vo.modelObject.name).lower() if vo.modelObject is not None else "", vo._id)

class _Laid:
  '''
  What a round layout arranges, laid out (see *_RoundLayout._lay()*): each
  group on its own, and the nodes in none.
  '''
  def __init__(self, groups:list[dict[VObject, tuple[float, float]]], refs:list[list[VObject]],
               edges:list[tuple[VObject, VObject, VRelation]], sizes:dict[VObject, tuple[float, float]],
               rows:list[VObject], stay:list[VObject]):
    self.groups = groups
    "Where each group's nodes' centres go, on its own (those put near it too: see *placeNearGroups()*)."
    self.refs = refs
    "Which of each group's nodes it's anchored by, kept arranged (see *groupOffset()*): its root, or its hubs."
    self.edges = edges
    "(parent, child, relation): the relations from parents to children."
    self.sizes = sizes
    "Every node's (width, height)."
    self.rows = rows
    "The nodes in no group to put in rows after them."
    self.stay = stay
    "The nodes in no group left where they are."

class _RoundLayout(LayoutHeuristic):
  '''
  What the round layouts share: putting their groups (trees, or hubs' groups)
  in rows, the nodes they don't arrange in rows after them (see *OTHERS*, *HUB_OTHERS*),
  and the labels of the relations from parents to children between them.

  As a dynamic layout (see *adjust()*): after each command, each group is
  laid out again where it is -- its root (or its hubs, on average) where it
  is (see *groupOffset()*) -- and, if it would be on one before it (from the
  top), moved to the nearest clear place (see *separateGroups()*). A node
  the user drags (and drops) that isn't a group's root (or its only hub) is
  pinned there, as the root (only hub) of a group of its own, with what's
  under it, until the next static round layout; dropping a root moves its
  group. The nodes in no group are put as by the static layout, each time --
  except those the user drops somewhere, which are pinned there.
  '''
  CATEGORIES = (STATIC, DYNAMIC)

  def __init__(self, view, **kwargs):
    super().__init__(view, **kwargs)
    self.pins:set[int] = set()
    "The ids (*VObject._id*) of the nodes the user has dropped, pinned as roots of their own (see *adjust()*)."
    self.known:set[int]|None = None
    "The ids of the nodes it laid out last time (None: all those there are): a new one doesn't anchor its group."
    self._fallback = FindFree(view)
    "What places what it doesn't arrange (see *placeNode()*)."
    self._treeLayout:TreeLayout|None = None

  def _tree(self) -> TreeLayout:
    ":returns: A tree layout with its parameters: for what's arranged, and its trees."
    if self._treeLayout is None:
      kw = {k: v for k, v in self.params.items() if k in ("relation", "parentEnd", "spacing")}
      self._treeLayout = TreeLayout(self.view, **kw)
    return self._treeLayout

  def _lay(self, dynamic:bool) -> _Laid:
    '''
    :param dynamic: Whether it's for keeping things arranged: the pinned
      nodes roots of their own (see *pins*).
    :type dynamic: bool
    :returns: What's arranged, each group laid out on its own.
    :rtype: _Laid
    '''
    raise NotImplementedError

  def _pinnable(self, drops:list[VObject]) -> set[int]:
    ":returns: The ids of those of *drops* (dropped by the user) to pin: not the roots of their groups."
    raise NotImplementedError

  def _staysPut(self, node:VObject) -> bool:
    ":returns: Whether *node* (just made) is put in place by *adjust()*: else it's put somewhere free (see *placeNode()*)."
    raise NotImplementedError

  def _withLabels(self, positions:dict[VObject, tuple[float, float]], sizes:dict[VObject, tuple[float, float]],
                  edges:list[tuple[VObject, VObject, VRelation]]) -> dict[VObject, tuple[float, float]]:
    ":returns: *positions*, and where the labels of the relations between them go (see *_labelTargets()*, *_otherLabels()*)."
    ret:dict[VObject, tuple[float, float]] = {n: p for n, p in positions.items()}
    ret.update(self._labelTargets(positions, sizes, edges))
    ret.update(self._otherLabels(positions, sizes, edges))
    return ret

  @override
  def targets(self) -> dict[VObject, tuple[float, float]]:
    laid = self._lay(dynamic=False)
    positions = self._arrangeGroups(self._tree(), laid.groups, laid.sizes, laid.rows + laid.stay)
    return self._withLabels(positions, laid.sizes, laid.edges)

  @override
  def arranged(self, cmd:LayoutMoves) -> None:
    '''
    If the view's dynamic layout is a round layout, the static one starts it
    afresh: its pins are let go (see *adjust()*), and what it knows is what
    this arranges. (Undone with *cmd*.)
    '''
    dyn = self.view.localLayout
    if isinstance(dyn, _RoundLayout) and dyn is not self:
      oldPins, oldKnown = set(dyn.pins), dyn.known
      newKnown = {vo._id for vo in self._tree().scope()[0]}
      def do() -> None:
        dyn.pins, dyn.known = set(), set(newKnown)
      def undo() -> None:
        dyn.pins, dyn.known = set(oldPins), oldKnown
      cmd.also.append((do, undo))

  # ---- dynamic ---------------------------------------------------------------------

  def compute(self, fresh:set[int]=set()) -> dict[VObject, tuple[float, float]]:
    '''
    Kept arranged (see the class doc): where everything arranged goes.

    :param fresh: The ids of the nodes just pinned (dropped: see *adjust()*):
      their groups go to the nearest clear place after the rest (from where they were dropped).
    :type fresh: set[int]
    :returns: Where each node, and relation's label, goes (its top left).
    :rtype: dict[VObject, tuple[float, float]]
    '''
    laid = self._lay(dynamic=True)
    sizes, spacing, known = laid.sizes, float(self.params["spacing"]), self.known
    current:dict[VObject, tuple[float, float]] = {}
    for n in [*(n for g in laid.groups for n in g), *laid.stay]:
      bb = n.boundingBox()
      current[n] = (bb[0], bb[1])
    knownAt = {n: p for n, p in current.items() if known is None or n._id in known}
    rels = [topLefts(g, sizes) for g in laid.groups]
    offsets = [groupOffset(rel, refs, knownAt, current) or (0.0, 0.0) for rel, refs in zip(rels, laid.refs)]
    isFresh = [any(n._id in fresh for n in refs) for refs in laid.refs]
    def top(i:int) -> tuple[float, float]:
      return min(y for _, y in rels[i].values()) + offsets[i][1], min(x for x, _ in rels[i].values()) + offsets[i][0]
    order = sorted((i for i in range(len(rels)) if not isFresh[i]), key=top) + [i for i in range(len(rels)) if isFresh[i]]
    singles = [{n: current[n]} for n in laid.stay]
    shifts = separateGroups([rels[i] for i in order] + singles, [offsets[i] for i in order] + [(0.0, 0.0)] * len(singles),
                            sizes, gap=spacing)
    positions:dict[VObject, tuple[float, float]] = {}
    for g, (dx, dy) in zip([rels[i] for i in order] + singles, shifts):
      for n, (x, y) in g.items():
        positions[n] = (x + dx, y + dy)
    if laid.rows: # (after the rest, below)
      x0 = min((x for x, _ in positions.values()), default=40.0)
      cursor = max((y + sizes[n][1] for n, (_, y) in positions.items()), default=40.0 - 2 * spacing) + 2 * spacing
      width = max([ROW_LENGTH] + [x + sizes[n][0] - x0 for n, (x, _) in positions.items()])
      rows = self._tree()._rows(laid.rows, sizes, cursor, x0, cursor, [(None, [x0, cursor, x0 + width, cursor])]) #type: ignore[list-item]
      positions.update({n: (float(round(x)), float(round(y))) for n, (x, y) in rows.items()})
    return self._withLabels(positions, sizes, laid.edges)

  @override
  def placeNode(self, node:VObject, referenceNode:Optional[VObject]=None, direction:Direction=Direction.UNSPECIFIED,
                loc:Optional[Point]=None, **kwargs) -> Point|tuple[float, float]:
    '''
    What it arranges is put in place by *adjust()*, after the command that
    made or moved it: it stays where it is for now. Anything else goes in the
    nearest free place (see *FindFree*).
    '''
    if self._staysPut(node):
      bb = node.boundingBox()
      return bb[0], bb[1]
    return self._fallback.placeNode(node, referenceNode, direction, loc, **kwargs)

  def _adjustment(self, name:str, pinned:set[int]) -> LayoutMoves:
    '''
    :param name: What the undo menu calls it.
    :type name: str
    :param pinned: Ids of nodes to pin now (see *pins*).
    :type pinned: set[int]
    :returns: The moves that keep things arranged (see *compute()*), with
      *pinned* pinned, and what it knows updated: not done yet.
    :rtype: LayoutMoves
    '''
    oldPins, oldKnown = set(self.pins), self.known
    self.pins |= pinned # (for compute(): put back below, and done by the command)
    try:
      targets = self.compute(fresh=pinned)
    finally:
      self.pins = oldPins
    cmd = LayoutMoves(self.view, name, targets)
    newPins = oldPins | pinned
    newKnown = {vo._id for vo in self._tree().scope()[0]}
    def do() -> None:
      self.pins, self.known = set(newPins), set(newKnown)
    def undo() -> None:
      self.pins, self.known = set(oldPins), (set(oldKnown) if oldKnown is not None else None)
    if newPins != oldPins or newKnown != oldKnown:
      cmd.also.append((do, undo))
    return cmd

  @override
  def activate(self) -> None:
    '''
    Made the view's dynamic layout: arrange things as it keeps them, as one
    undoable command (if anything moves).
    '''
    self.known = None
    cmd = self._adjustment(f"keep arranged: {self.NAME}", set())
    if cmd.moves:
      self.view.context.doList.do(cmd)
    else: # (nothing to move: no undo entry, just what it knows)
      for do, _ in cmd.also:
        do()

  @override
  def adjust(self, command:Command) -> LayoutMoves|None:
    '''
    After a command: lay the groups out again (see *compute()*). A node the
    user dropped (see *SNGView._Move*) that isn't the root of its group is
    pinned where it's dropped (see *_pinnable()*).
    '''
    drops = [vo for vo in self._tree()._drops(command) if isMember(vo)]
    return self._adjustment(command.name, self._pinnable(drops) if drops else set())

  # ---- saving it with the view -----------------------------------------------------

  @override
  def extraState(self) -> dict[str, str]:
    return {"pins": ",".join(str(i) for i in sorted(self.pins))} if self.pins else {}

  @override
  def restoreExtraState(self, state:dict[str, str]) -> None:
    self.pins = {int(i) for i in state.get("pins", "").split(",") if i.strip().isdigit()}

  # ---- static ----------------------------------------------------------------------

  def _arrangeGroups(self, tree:TreeLayout, groups:list[dict[VObject, tuple[float, float]]],
                     sizes:dict[VObject, tuple[float, float]], others:list[VObject]) -> dict[VObject, tuple[float, float]]:
    '''
    :param tree: A tree layout (see *_tree()*): for the rows of *others*.
    :type tree: TreeLayout
    :param groups: Where each group's nodes' centres go, on its own.
    :type groups: list[dict[VObject, tuple[float, float]]]
    :param sizes: Every node's (width, height).
    :type sizes: dict[VObject, tuple[float, float]]
    :param others: The nodes not in a group.
    :type others: list[VObject]
    :returns: Where they go (their top left): the groups one after another
      in rows (see *ROW_LENGTH*), from the top left of what's arranged, and
      *others* in rows after them (unless they're to be left where they are: see *OTHERS*, *HUB_OTHERS*).
    :rtype: dict[VObject, tuple[float, float]]
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
    ret:dict[VObject, tuple[float, float]] = {}
    x, y, rowHeight = x0, y0, 0.0
    for t, b in zip(tops, boxes):
      w, h = b[2] - b[0], b[3] - b[1]
      if x > x0 and x + w > x0 + limit:
        x, y, rowHeight = x0, y + rowHeight + gap, 0.0
      for n, (px, py) in t.items():
        ret[n] = (px - b[0] + x, py - b[1] + y)
      x, rowHeight = x + w + gap, max(rowHeight, h)
    if others and self.params["others"] in ("rows", "near"): # (near: those related to nothing placed)
      cursor = y + rowHeight + gap if groups else y0
      ret.update(tree._rows(others, sizes, cursor, x0, y0, [(None, [x0, y0, x0 + limit, y0])])) #type: ignore[list-item]
    return {n: (float(round(px)), float(round(py))) for n, (px, py) in ret.items()}

  @staticmethod
  def _labelTargets(positions:dict[VObject, tuple[float, float]], sizes:dict[VObject, tuple[float, float]],
                    edges:list[tuple[VObject, VObject, VRelation]]) -> dict[VObject, tuple[float, float]]:
    '''
    :param edges: (parent, child, relation): the relations whose labels to put.
    :type edges: list[tuple[VObject, VObject, VRelation]]
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

  def _otherLabels(self, positions:dict[VObject, tuple[float, float]], sizes:dict[VObject, tuple[float, float]],
                   edges:list[tuple[VObject, VObject, VRelation]]) -> dict[VObject, tuple[float, float]]:
    '''
    :param edges: The relations whose labels are put already (see *_labelTargets()*).
    :type edges: list[tuple[VObject, VObject, VRelation]]
    :returns: Where the label of each other relation shown between the nodes
      arranged goes (its top left): midway between its ends' centres -- or,
      for more than one between the same two, side by side across the line
      between them, round the middle.
    :rtype: dict[VObject, tuple[float, float]]
    '''
    done = {id(r) for _, _, r in edges}
    pairs:dict[tuple[int, int], list[VRelation]] = {}
    for r in sorted((r for r in self.view.values() if isLink(r)), key=lambda r: r._id):
      if id(r) in done or r.src is r.dst \
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

  def _edgeRoom(self, edges:list[tuple[VObject, VObject, VRelation]]) -> dict[VObject, float]:
    ":returns: The room each child needs between it and its parent: its relation's label (its circle) and the spacing."
    spacing = float(self.params["spacing"])
    return {k: 2 * radius(layoutSize(r)) + spacing for _, k, r in edges}

class _TreeRoundLayout(_RoundLayout):
  '''
  A round layout of trees by a relation type (as *TreeLayout* finds them:
  see *TreeLayout.structure()*): *positions()* says where each tree's nodes go.
  Relation types shown are arranged as nodes are (see *treeLayout.isMember()*).
  '''
  PARAMETERS = (
    LayoutParameter("relation", "Relation", "relation", "isa",
                    note="Its subtypes too: each kind's children are together."),
    LayoutParameter("parentEnd", "The parent is the relation's", "choice", "destination", PARENT_ENDS,
                    note='Eg: the source for "includes" (a package includes its modules); '
                         'the destination for "isa" (a subtype isa its type).'),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("others", "Nodes in no tree", "choice", "near", OTHERS,
                    note='"near": each near what it\'s related to, out beyond it (those related to nothing '
                         'there in rows). "rows": in rows after the trees.'),
    LayoutParameter("trees", "Trees related to one another", "choice", "joined", TREES,
                    note='"joined": a tree whose root is related to a node in another (eg: by another relation '
                         'type) goes out beyond that node, as if one of its children. "apart": each on its own.'),
  )

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param kwargs: See *PARAMETERS*: relation (a relation type, or its name),
      parentEnd ("source" or "destination"), spacing, others (see *OTHERS*), trees (see *TREES*).
    '''
    super().__init__(view, **kwargs)
    if self.params["relation"] is None:
      self.params["relation"] = view.model.ISA
    if self.params["parentEnd"] not in PARENT_ENDS:
      raise ValueError(f'{type(self).__name__}: parentEnd must be one of {", ".join(PARENT_ENDS)}, not "{self.params["parentEnd"]}".')
    if self.params["others"] not in OTHERS:
      raise ValueError(f'{type(self).__name__}: others must be one of {", ".join(OTHERS)}, not "{self.params["others"]}".')
    if self.params["trees"] not in TREES:
      raise ValueError(f'{type(self).__name__}: trees must be one of {", ".join(TREES)}, not "{self.params["trees"]}".')

  @classmethod
  @override
  def parameterChanged(cls, view, name:str, values:dict[str, Any]) -> dict[str, Any]:
    "As *TreeLayout.parameterChanged()*: a relation type chosen, its parent end."
    return TreeLayout.parameterChanged(view, name, values)

  def positions(self, roots:list[VObject], kids:dict[VObject, list[VObject]], sizes:dict[VObject, tuple[float, float]],
                edgeRoom:dict[VObject, float]) -> tuple[dict[VObject, tuple[float, float]], list[tuple[VObject, list[VObject], float]]]:
    ":returns: As *balloonPositions()*."
    raise NotImplementedError

  @override
  def _lay(self, dynamic:bool) -> _Laid:
    tree = self._tree()
    tree.pins = set(self.pins) if dynamic else set()
    roots, children, parentRel, others, _ = tree.structure(dynamic=dynamic)
    if dynamic: # (in order of name, as arranged: not where they are)
      roots, others = sorted(roots, key=_byName), sorted(others, key=_byName)
      children = {p: [sorted(g, key=_byName) for g in gs] for p, gs in children.items()}
    kids = {p: [k for g in gs for k in g] for p, gs in children.items()}
    joins:list[tuple[VObject, VObject, VRelation]] = []
    if self.params["trees"] == "joined":
      roots, joins = self._join(roots, kids, {n._id for n in roots} & self.pins if dynamic else set())
    nodes = [*roots, *(k for ks in kids.values() for k in ks), *others]
    sizes = {n: layoutSize(n) for n in nodes}
    edges = [(tree._ends(r)[0], k, r) for k, r in parentRel.items()] + joins
    centres, trees = self.positions(roots, kids, sizes, self._edgeRoom(edges))
    groups = [{n: centres[n] for n in members} for _, members, _ in trees]
    mode = self.params["others"]
    stay = [n for n in others if mode == "leave" or (dynamic and n._id in self.pins)]
    staying = set(stay)
    rows = [n for n in others if n not in staying]
    if rows and mode == "near":
      rows = self._placeNear(groups, rows, sizes, edges)
    return _Laid(groups, [[root] for root, _, _ in trees], edges, sizes, rows, stay)

  @staticmethod
  def _join(roots:list[VObject], kids:dict[VObject, list[VObject]], pinned:set[int]) -> tuple[list[VObject], list[tuple[VObject, VObject, VRelation]]]:
    '''
    Join the trees related to one another (see *TREES*): a tree whose root is
    related (by any relation shown) to a node in another tree becomes one of
    that node's children (the last) -- so it's laid out out beyond it, along
    the way out from the middle, rather than wherever it was. From the biggest
    top tree (one whose root isn't related to another tree), each tree related
    to one joined so far is joined to it (to the first node it's related to,
    in order of the relations made), and so on; then from the biggest of the
    rest (tops first). (Not a pinned root: it stays where
    it's been dropped.)

    :param roots: The trees' roots.
    :type roots: list[VObject]
    :param kids: Each node's children: the joined trees' roots are added.
    :type kids: dict[VObject, list[VObject]]
    :param pinned: The ids of the roots that are pinned (see *pins*).
    :type pinned: set[int]
    :returns: The roots of the trees there are now (in order); and each tree
      joined: (the node it's joined to, its root, the relation between them).
    :rtype: tuple[list[VObject], list[tuple[VObject, VObject, VRelation]]]
    '''
    treeOf:dict[VObject, VObject] = {}
    size:dict[VObject, int] = {}
    for root in roots:
      stack = [root]
      while stack:
        n = stack.pop()
        if n not in treeOf:
          treeOf[n] = root
          stack.extend(kids.get(n, ()))
      size[root] = sum(1 for t in treeOf.values() if t is root)
    links:dict[VObject, list[tuple[VObject, VRelation]]] = {}
    for root in roots:
      if root._id in pinned:
        continue
      for r in sorted((r for r in root.relations if isLink(r)), key=lambda r: r._id):
        other = r.dst if r.src is root else r.src
        if other in treeOf and treeOf[other] is not root:
          links.setdefault(root, []).append((other, r))
    # (from the tops -- trees whose roots aren't related to another tree -- the biggest first; stable: in
    # order, among those as big)
    rest = sorted(roots, key=lambda r: (r in links, -size[r]))
    joined:set[VObject] = set()
    joins:list[tuple[VObject, VObject, VRelation]] = []
    while rest:
      joined.add(rest.pop(0))
      grew = True
      while grew:
        grew = False
        for root in list(rest):
          hit = next(((n, r) for n, r in links.get(root, ()) if treeOf[n] in joined), None)
          if hit is not None:
            kids.setdefault(hit[0], []).append(root)
            joins.append((hit[0], root, hit[1]))
            joined.add(root)
            rest.remove(root)
            grew = True
    under = {root for _, root, _ in joins}
    return [r for r in roots if r not in under], joins

  @override
  def _pinnable(self, drops:list[VObject]) -> set[int]:
    '''
    As *TreeLayout.adjust()*: a tree's child, or a node in no tree (not a root:
    it's kept where it is anyway) -- or, with the trees joined (see *TREES*),
    any root: it may be joined to another tree, as a child (pinned, it isn't).
    '''
    tree = self._tree()
    _, edges = tree.scope()
    children = {id(tree._ends(r)[1]) for r in edges}
    inTree = children | {id(tree._ends(r)[0]) for r in edges}
    joined = self.params["trees"] == "joined"
    return {vo._id for vo in drops if joined or id(vo) in children or id(vo) not in inTree}

  @override
  def _staysPut(self, node:VObject) -> bool:
    "As *TreeLayout.placeNode()*: a tree's node, or a tree relation's label."
    tree = self._tree()
    if not isMember(node):
      return tree._isEdge(node.modelObject)
    return any(isLink(r) and tree._isEdge(r.modelObject) for r in node.relations)

  def _placeNear(self, groups:list[dict[VObject, tuple[float, float]]], others:list[VObject],
                 sizes:dict[VObject, tuple[float, float]], edges:list[tuple[VObject, VObject, VRelation]]) -> list[VObject]:
    '''
    For *others* "near": put each node in no tree near the tree nodes it's
    related to (by any relation shown), in their tree, clear of its nodes and
    its relations' labels, with room for the label of the relation between
    them (see *placeNearGroups()*).

    :param groups: Where each tree's nodes' centres go, from its root: those put are added.
    :type groups: list[dict[VObject, tuple[float, float]]]
    :param others: The nodes in no tree.
    :type others: list[VObject]
    :param sizes: Every node's (width, height).
    :type sizes: dict[VObject, tuple[float, float]]
    :param edges: The tree relations (parent, child, relation).
    :type edges: list[tuple[VObject, VObject, VRelation]]
    :returns: Those not put (related to no tree): for the rows.
    :rtype: list[VObject]
    '''
    spacing = float(self.params["spacing"])
    ids = {id(n) for n in [*(n for g in groups for n in g), *others]}
    related:dict[VObject, list[VObject]] = {n: [] for n in others}
    between:dict[tuple[int, int], VRelation] = {}
    for n in others:
      for r in sorted((r for r in n.relations if isLink(r)), key=lambda r: r._id):
        other = r.dst if r.src is n else r.src
        if other is not n and id(other) in ids:
          if other not in related[n]:
            related[n].append(other)
          between.setdefault((id(n), id(other)), r)
          between.setdefault((id(other), id(n)), r)
    def room(n:VObject, r:VObject) -> float:
      rel = between.get((id(n), id(r)))
      return (2 * radius(layoutSize(rel)) if rel is not None else 0.0) + spacing
    obstacles = []
    for g in groups: # (the tree relations' labels, where they'll be)
      tops = {n: (cx - sizes[n][0] / 2, cy - sizes[n][1] / 2) for n, (cx, cy) in g.items()}
      boxes:list[Sequence[float]] = []
      for label, (x, y) in self._labelTargets(tops, sizes, edges).items():
        w, h = layoutSize(label)
        boxes.append([x, y, x + w, y + h])
      obstacles.append(boxes)
    return placeNearGroups(others, sizes, related, groups, obstacles, spacing=spacing, room=room)

@registerLayout
class BalloonLayout(_TreeRoundLayout):
  '''
  Arrange nodes as balloons (see *balloonPositions()*): trees by a relation
  type (*relation*) and its subtypes (as *TreeLayout* finds them), each
  node's children in a ring round it, each child's subtree a balloon of its
  own, spread round the way away from its parent. The trees are put one
  after another in rows, from the top left of what's arranged. The nodes in
  no tree are put near the tree nodes they're related to, out beyond them
  (and with their tree: those related to no tree in rows after the trees); in
  rows after the trees; or left where they are (*others*). Each tree
  relation's label goes on its line, between its ends; the others' midway
  between their ends. Kept arranged: see *_RoundLayout*.
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
  its own wedge. Otherwise (kept arranged too) as *BalloonLayout*.
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
  ends; the others' are left between their ends. Kept arranged: see
  *_RoundLayout* (a node dropped is cut out of its group: see *hubForest()*).

  Relation types shown are arranged as nodes are (see *treeLayout.isMember()*),
  by the relations they're an end of (eg: isa): not by their own ends (their
  domain and range). Nodes in a context window (or that are one) aren't arranged.
  '''
  NAME = "hubs"
  PARAMETERS = (
    LayoutParameter("minSpokes", "A hub has at least this many relations", "int", 3,
                    note="In a group with no such node, the one with the most is its hub."),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("others", "Nodes related to nothing", "choice", "rows", HUB_OTHERS,
                    note='"rows": in rows after the rest.'),
  )

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param kwargs: See *PARAMETERS*: minSpokes, spacing, others (see *HUB_OTHERS*).
    '''
    super().__init__(view, **kwargs)
    if self.params["others"] not in HUB_OTHERS:
      raise ValueError(f'HubLayout: others must be one of {", ".join(HUB_OTHERS)}, not "{self.params["others"]}".')

  def graph(self) -> tuple[list[VObject], dict[VObject, list[VObject]], dict[tuple[VObject, VObject], VRelation]]:
    '''
    :returns: What's arranged: the nodes (as *TreeLayout.scope()*), by name;
      what each is related to (by a relation shown, either way), by name; and
      a relation between each pair of them (the first made), both ways round.
    :rtype: tuple[list[VObject], dict[VObject, list[VObject]], dict[tuple[VObject, VObject], VRelation]]
    '''
    name = lambda vo: (str(vo.modelObject.name).lower() if vo.modelObject is not None else "", vo._id)
    nodes = sorted(self._tree().scope()[0], key=name)
    ids = {id(n) for n in nodes}
    neighbours:dict[VObject, list[VObject]] = {n: [] for n in nodes}
    between:dict[tuple[VObject, VObject], VRelation] = {}
    rels = sorted((r for r in self.view.values() if isLink(r) and id(r.src) in ids and id(r.dst) in ids and r.src is not r.dst), key=lambda r: r._id)
    for r in rels:
      a, b = r.src, r.dst
      if (a, b) not in between:
        between[(a, b)] = between[(b, a)] = r #type: ignore[index]
        neighbours[a].append(b) #type: ignore[index, arg-type]
        neighbours[b].append(a) #type: ignore[index, arg-type]
    return nodes, {n: sorted(ns, key=name) for n, ns in neighbours.items()}, between

  def _forest(self, dynamic:bool) -> tuple[list[VObject], list[tuple[list[VObject], dict[VObject, list[VObject]]]], list[VObject],
                                            dict[tuple[VObject, VObject], VRelation]]:
    ":returns: What's arranged (see *graph()*), its groups and the nodes related to nothing (see *hubForest()*), and the relations."
    nodes, neighbours, between = self.graph()
    pinned = [n for n in nodes if n._id in self.pins] if dynamic else []
    groups, isolated = hubForest(nodes, neighbours, max(1, int(self.params["minSpokes"])), pinned)
    return nodes, groups, isolated, between

  @override
  def _lay(self, dynamic:bool) -> _Laid:
    nodes, groups, isolated, between = self._forest(dynamic)
    sizes = {n: layoutSize(n) for n in nodes}
    spacing = float(self.params["spacing"])
    centres:list[dict[VObject, tuple[float, float]]] = []
    edges:list[tuple[VObject, VObject, VRelation]] = []
    for hubs, kids in groups:
      es = [(p, k, between[(p, k)]) for p, ks in kids.items() for k in ks]
      out = hubPositions(hubs, kids, sizes, spacing=spacing, edgeRoom=self._edgeRoom(es))[0]
      centres.append(out)
      edges += [e for e in es if e[0] in out] # (a group's kids are its whole connected group's: see hubForest())
    stay = [n for n in isolated if self.params["others"] == "leave" or (dynamic and n._id in self.pins)]
    staying = set(stay)
    return _Laid(centres, [hubs for hubs, _ in groups], edges, sizes, [n for n in isolated if n not in staying], stay)

  @override
  def _pinnable(self, drops:list[VObject]) -> set[int]:
    "Any node arranged but a group's only hub (it's kept where it is anyway)."
    nodes, groups, _, _ = self._forest(dynamic=True)
    inScope = set(nodes)
    sole = {hubs[0] for hubs, _ in groups if len(hubs) == 1}
    return {vo._id for vo in drops if vo in inScope and vo not in sole}

  @override
  def _staysPut(self, node:VObject) -> bool:
    "A node (or relation type: see *isMember()*) related to another, or a relation between two of them."
    if not isMember(node):
      return isinstance(node, VRelation) and isinstance(node.src, VObject) and isinstance(node.dst, VObject) \
             and isMember(node.src) and isMember(node.dst) and node.src is not node.dst
    return any(isLink(r) and r.src is not r.dst for r in node.relations)
