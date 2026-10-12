'''
The tree layout (see *TreeLayout*): a view's nodes arranged as trees -- or a
forest -- by a relation type (and its subtypes): each node's children in a
column (or row) beside it, the next level out, each parent level with the
middle of its children, and the relations' labels lined up just before the
children. Static ("arrange now") and dynamic ("keep arranged": it opens up
for what's added, and closes up over what's removed or hidden).

*treePositions()* is the geometry, on its own (no view): where each node of
some trees goes.

Created on Oct 10, 2026

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
from typing import Any, Hashable, Optional, TypeVar, override
from util.command import Command
from util.utils import Point
from sn.model.model import GraphObject, IsaIndividual, Relation
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import (LayoutHeuristic, LayoutParameter, LayoutMoves, FindFree, Direction,
                                     registerLayout, layoutSize, STATIC, DYNAMIC)

K = TypeVar("K", bound=Hashable)

DIRECTIONS = ("right", "down", "left", "up")
"Which way a tree grows: from its root out to its leaves."

PARENT_ENDS = ("source", "destination")
'''Which end of a relation is the parent: eg: the source for "includes" (a
package includes its modules); the destination for "isa" (a subtype isa its
type) and "has-parent" (a child has-parent its parent).'''

OTHERS = ("leave", "rows")
'''What a static tree layout does with the nodes in no tree: leaves them where
they are, or puts them in rows (lines) after the trees.'''

LABEL_GAP = 12.0
"The space between a tree relation's label and the child it goes to."

MIN_LINE = 100.0
"The least length of line between a parent and a child's label (see *TreeLayout.levelGap()*)."

MIN_LEVEL_GAP = 60.0
"The least space between one level of a tree and the next."

MIN_ROW_LENGTH = 600.0
"The shortest the rows of nodes in no tree are (see *OTHERS*): otherwise, as long as the trees are deep."

def _flip(direction:str) -> bool:
  ":returns: Whether trees grow toward smaller coordinates (left, up)."
  return direction in ("left", "up")

def _vertical(direction:str) -> bool:
  ":returns: Whether trees grow along y (down, up)."
  return direction in ("down", "up")

def treePositions(roots:list[K], children:dict[K, list[list[K]]], sizes:dict[K, tuple[float, float]], *,
                  direction:str="right", spacing:float=20.0, levelGaps:Optional[dict[int, float]]=None,
                  levelGap:float=MIN_LEVEL_GAP) -> tuple[dict[K, tuple[float, float]], list[tuple[K, list[float]]]]:
  '''
  Lay out some trees, each on its own: the root at depth 0, each node's
  children at the next depth -- the depths in lines (columns, for "right"),
  each as deep as its deepest node, *levelGaps* apart -- the leaves *spacing*
  apart across, each parent level with the middle of its children, and the
  groups of a node's children *spacing* further apart.

  :param roots: The trees' roots.
  :type roots: list[K]
  :param children: Each node's children, in groups (eg: by the type of
    relation to them), in order. Each node is laid out once: under the first
    parent it's met under (a node met again is left out there).
  :type children: dict[K, list[list[K]]]
  :param sizes: Each node's (width, height).
  :type sizes: dict[K, tuple[float, float]]
  :param direction: Which way the trees grow: one of *DIRECTIONS*.
  :type direction: str
  :param spacing: The space between neighbouring nodes across a level.
  :type spacing: float
  :param levelGaps: The space between depth *n* and depth *n* + 1, by *n*, if not *levelGap*.
  :type levelGaps: dict[int, float] | None
  :param levelGap: The space between depths not in *levelGaps*.
  :type levelGap: float
  :returns: Where each node goes (its top left), with each tree's root at
    (0, 0) -- or, growing left or up, with its root's far side at 0 -- and
    each tree's nodes, and their bounding box (x1, y1, x2, y2), by root.
  :rtype: tuple[dict[K, tuple[float, float]], list[tuple[K, list[float]]]]
  '''
  gaps = levelGaps or {}
  vertical, flip = _vertical(direction), _flip(direction)
  depthSize = lambda n: sizes[n][1] if vertical else sizes[n][0]
  crossSize = lambda n: sizes[n][0] if vertical else sizes[n][1]
  ret:dict[K, tuple[float, float]] = {}
  trees:list[tuple[K, list[float]]] = []
  seen:set[K] = set()
  for root in roots:
    if root in seen:
      continue
    # the levels: which nodes are in this tree, at what depth
    depthOf:dict[K, int] = {}
    order:list[K] = []
    kidsOf:dict[K, list[list[K]]] = {}
    def visit(n:K, d:int) -> None:
      seen.add(n)
      depthOf[n] = d
      order.append(n)
      groups:list[list[K]] = []
      for g in children.get(n, []):
        kept = [k for k in g if k not in seen]
        for k in kept:
          seen.add(k)
        if kept:
          groups.append(kept)
      kidsOf[n] = groups
      for g in groups:
        for k in g:
          visit(k, d + 1)
    visit(root, 0)
    deepest = max(depthOf.values())
    extent = [0.0] * (deepest + 1)
    for n, d in depthOf.items():
      extent[d] = max(extent[d], depthSize(n))
    level = [0.0]
    for d in range(deepest):
      level.append(level[-1] + extent[d] + gaps.get(d, levelGap))
    # across: each leaf after the last; each parent level with the middle of its children
    cross:dict[K, float] = {}
    nextC = 0.0
    def place(n:K) -> None:
      nonlocal nextC
      start = nextC
      kids = kidsOf[n]
      if not kids:
        cross[n] = nextC
        nextC += crossSize(n) + spacing
        return
      for i, g in enumerate(kids):
        if i:
          nextC += spacing # (between groups)
        for k in g:
          place(k)
      first, last = kids[0][0], kids[-1][-1]
      centre = (cross[first] + crossSize(first) / 2 + cross[last] + crossSize(last) / 2) / 2
      c = centre - crossSize(n) / 2
      if c < start: # (bigger than its children: they move along, so it doesn't overlap what's before)
        shift = start - c
        stack = [k for g in kids for k in g]
        while stack:
          k = stack.pop()
          cross[k] += shift
          stack.extend(m for g in kidsOf[k] for m in g)
        nextC += shift
        c = start
      cross[n] = c
      nextC = max(nextC, c + crossSize(n) + spacing)
    place(root)
    box = [float("inf"), float("inf"), float("-inf"), float("-inf")]
    for n in order:
      at = level[depthOf[n]]
      at = -(at + depthSize(n)) if flip else at
      x, y = (cross[n], at) if vertical else (at, cross[n])
      ret[n] = (x, y)
      w, h = sizes[n]
      box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + h)]
    trees.append((root, box))
  return ret, trees

def treeMembers(root:K, children:dict[K, list[list[K]]], positions:dict[K, Any]) -> list[K]:
  '''
  :param root: A tree's root (see *treePositions()*).
  :type root: K
  :param children: As given to *treePositions()*.
  :type children: dict[K, list[list[K]]]
  :param positions: What *treePositions()* returned.
  :type positions: dict[K, Any]
  :returns: The nodes of its tree (as laid out: each under its first parent).
  :rtype: list[K]
  '''
  ret = [root]
  seen = {root}
  i = 0
  while i < len(ret):
    for g in children.get(ret[i], []):
      for k in g:
        if k not in seen and k in positions:
          seen.add(k)
          ret.append(k)
    i += 1
  return ret

def _overlaps(a:list[float], b:list[float], gap:float) -> bool:
  return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap

@registerLayout
class TreeLayout(LayoutHeuristic):
  '''
  Arrange nodes as trees by a relation type (*relation*) and its subtypes:
  each relation of one of those types (shown in the view) from a parent to a
  child -- which end's the parent is *parentEnd* -- puts the child one level
  out from the parent, the way the trees grow (*direction*). A node's
  children are grouped by which of *relation*'s direct subtypes they're
  related by (in the order those were made: eg: for "includes", a
  package's modules, then its sub-packages), and each group's in order. A
  node with more than one parent is put under the first; its other
  relations are left floating, as are those that would make a cycle. Each
  tree relation's label is put just before its child, on the straight line
  from the parent (so the labels line up, and the lines stay straight).

  Nodes in a context window (or that are one) aren't arranged.

  As a static layout (see *arrange()*): the children are in order of name;
  the trees are put one after another (across the way they grow) from the
  top left of what's arranged; and the nodes in no tree are left where
  they are, or put in rows after the trees (*others*).

  As a dynamic layout (see *adjust()*): after each command, the trees are
  laid out again, each from where its root is: children in the order they
  are already, and new ones after them, by name. So a tree opens up for
  what's added to it, and closes up over what's removed or hidden -- and
  what's after it, across (the trees and the nodes in no tree alongside it),
  moves along by as much (see *_keepPlaces()*). A tree node the user drags
  (and drops) takes its subtree with it: it's pinned there, as the root of a
  tree of its own (room is made for its subtree), until the next static
  tree layout. Nothing's left on another node: what would be is pushed
  further across.
  '''
  NAME = "tree"
  CATEGORIES = (STATIC, DYNAMIC)
  PARAMETERS = (
    LayoutParameter("relation", "Relation", "relation", "isa",
                    note="Its subtypes too: each kind's children are grouped together."),
    LayoutParameter("parentEnd", "The parent is the relation's", "choice", "destination", PARENT_ENDS,
                    note='Eg: the source for "includes" (a package includes its modules); '
                         'the destination for "isa" (a subtype isa its type).'),
    LayoutParameter("direction", "Grows", "choice", "right", DIRECTIONS),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("others", "Nodes in no tree", "choice", "leave", OTHERS,
                    note='"rows": in rows after the trees.', categories=(STATIC,)),
  )

  def __init__(self, view, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param kwargs: See *PARAMETERS*: relation (a relation type, or its name),
      parentEnd ("source" or "destination"), direction (see *DIRECTIONS*),
      spacing, others (see *OTHERS*: static only).
    '''
    super().__init__(view, **kwargs)
    if self.params["relation"] is None:
      self.params["relation"] = view.model.ISA
    if self.params["direction"] not in DIRECTIONS:
      raise ValueError(f'TreeLayout: direction must be one of {", ".join(DIRECTIONS)}, not "{self.params["direction"]}".')
    if self.params["parentEnd"] not in PARENT_ENDS:
      raise ValueError(f'TreeLayout: parentEnd must be one of {", ".join(PARENT_ENDS)}, not "{self.params["parentEnd"]}".')
    self.pins:set[int] = set()
    "The ids (*VObject._id*) of the tree nodes the user has dropped, pinned as roots of their own (see *adjust()*)."
    self.known:set[int]|None = None
    "The ids of the nodes it laid out last time (None: all those there are): a new one goes after the others."
    self._fallback = FindFree(view)
    "What places what isn't in a tree (see *placeNode()*)."

  @classmethod
  @override
  def parameterChanged(cls, view, name:str, values:dict[str, Any]) -> dict[str, Any]:
    '''
    A relation type chosen: its parent end is the destination for isa, and
    the source for others.
    '''
    if name == "relation" and values.get("relation") is not None:
      values["parentEnd"] = "destination" if values["relation"] is view.model.ISA else "source"
    return values

  # ---- what's arranged -----------------------------------------------------------

  def _isEdge(self, mo:GraphObject|None) -> bool:
    ":returns: Whether *mo* is a relation of the tree's relation type (or a subtype)."
    rel = self.params["relation"]
    if mo is None or not isinstance(mo, Relation) or not mo.isIndividual():
      return False
    if rel is self.view.model.ISA:
      return isinstance(mo, IsaIndividual)
    return not isinstance(mo, IsaIndividual) and (mo.isa(rel) or rel in mo.getParents())

  def _group(self, mo:Relation) -> int:
    '''
    :returns: Which group a child related by *mo* is in: 0 for the relation
      type itself; else 1 + which of its direct subtypes (in the order they
      were made) *mo* is a kind of.
    '''
    rel = self.params["relation"]
    cache = self.__dict__.setdefault("_groups", {})
    t = next((p for p in mo.getParents() if isinstance(p, Relation)), None)
    if t is None or t is rel:
      return 0
    if id(t) not in cache:
      subs = sorted((c for c in rel.getChildren() if isinstance(c, Relation) and c.isType()), key=lambda c: c._id)
      cache[id(t)] = next((i + 1 for i, s in enumerate(subs) if t is s or t.isa(s)), len(subs) + 1)
    return cache[id(t)]

  def scope(self) -> tuple[list[VNode], list[VRelation]]:
    '''
    :returns: What's arranged: the nodes shown (not hidden), not in a context
      window nor one; and the relations shown between them of the tree's type
      (see *relation*), not to themselves.
    :rtype: tuple[list[VNode], list[VRelation]]
    '''
    v = self.view
    windows = v.contextWindows()
    inWindows = {id(vo) for w in windows for vo in w.windowContents()} | {id(vo) for vo in v.containmentHomes()}
    nodes = [vo for vo in v.values() if isinstance(vo, VNode) and vo._isConnected() and not vo.isHidden()
             and vo.modelObject is not None and not vo.isContextWindow() and id(vo) not in inWindows]
    ids = {id(n) for n in nodes}
    edges = [r for r in v.values() if isinstance(r, VRelation) and r._isConnected() and not r.isHidden()
             and self._isEdge(r.modelObject) and id(r.src) in ids and id(r.dst) in ids and r.src is not r.dst]
    return nodes, edges

  def _ends(self, r:VRelation) -> tuple[VNode, VNode]:
    ":returns: (parent, child) of a tree relation."
    if self.params["parentEnd"] == "source":
      return r.src, r.dst #type: ignore[return-value]
    return r.dst, r.src #type: ignore[return-value]

  def structure(self, dynamic:bool) -> tuple[list[VNode], dict[VNode, list[list[VNode]]], dict[VNode, VRelation], list[VNode], list[VRelation]]:
    '''
    :param dynamic: Whether it's for keeping things arranged (see the class
      doc): children in the order they are, new ones after; pinned nodes the
      roots of their own trees. Else children in order of name.
    :type dynamic: bool
    :returns: The trees: their roots (in order across); each node's children,
      in groups (see the class doc); each child's tree relation (from its
      parent); the nodes in no tree; and the tree's type of relations that
      aren't tree relations (eg: to a second parent).
    :rtype: tuple[list[VNode], dict[VNode, list[list[VNode]]], dict[VNode, VRelation], list[VNode], list[VRelation]]
    '''
    nodes, edges = self.scope()
    vertical = _vertical(self.params["direction"])
    crossOf = lambda vo: vo.centerPt()[0] if vertical else vo.centerPt()[1]
    name = lambda vo: (str(vo.modelObject.name).lower() if vo.modelObject is not None else "", vo._id)
    known = self.known
    def key(vo:VNode) -> tuple:
      if not dynamic:
        return (0, *name(vo))
      if known is None or vo._id in known:
        return (0, crossOf(vo), vo._id)
      return (1, *name(vo)) # (new: after the others)
    pinned = {vo._id for vo in nodes} & self.pins if dynamic else set()
    parentRel:dict[VNode, VRelation] = {}
    for r in sorted(edges, key=lambda r: r._id): # (the first parent: the first related, of those not pinned)
      parent, child = self._ends(r)
      if child._id in pinned or child in parentRel:
        continue
      parentRel[child] = r
    # no cycles: a child that leads back to itself loses its parent there
    for child in list(parentRel):
      seen = {child}
      p = self._ends(parentRel[child])[0]
      while p in parentRel and p not in seen:
        seen.add(p)
        p = self._ends(parentRel[p])[0]
      if p is child:
        del parentRel[child]
    groups:dict[VNode, dict[int, list[VNode]]] = {}
    for child, r in parentRel.items():
      groups.setdefault(self._ends(r)[0], {}).setdefault(self._group(r.modelObject), []).append(child) #type: ignore[arg-type]
    children = {p: [sorted(g[i], key=key) for i in sorted(g)] for p, g in groups.items()}
    inTree = set(parentRel) | set(children)
    roots = sorted((n for n in nodes if n in inTree and n not in parentRel), key=key)
    others = sorted((n for n in nodes if n not in inTree), key=key)
    loose = [r for r in edges if parentRel.get(self._ends(r)[1]) is not r]
    return roots, children, parentRel, others, loose

  # ---- where things go -------------------------------------------------------------

  def levelGaps(self, children:dict[VNode, list[list[VNode]]], parentRel:dict[VNode, VRelation],
                roots:list[VNode]) -> dict[int, float]:
    '''
    :returns: The space between each depth of the trees and the next: room
      for the line to the widest label there (*MIN_LINE*), the label, and
      *LABEL_GAP* -- at least *MIN_LEVEL_GAP*.
    :rtype: dict[int, float]
    '''
    vertical = _vertical(self.params["direction"])
    ret:dict[int, float] = {}
    level = [(r, 0) for r in roots]
    seen = set(roots)
    while level:
      nxt = []
      for n, d in level:
        for g in children.get(n, []):
          for k in g:
            if k in seen:
              continue
            seen.add(k)
            w, h = layoutSize(parentRel[k])
            size = h if vertical else w
            ret[d] = max(ret.get(d, MIN_LEVEL_GAP), size + MIN_LINE + 2 * LABEL_GAP)
            nxt.append((k, d + 1))
      level = nxt
    return ret

  def _labelTargets(self, positions:dict[VNode, tuple[float, float]], sizes:dict[VNode, tuple[float, float]],
                    parentRel:dict[VNode, VRelation]) -> dict[VObject, tuple[float, float]]:
    '''
    :returns: Where each tree relation's label goes (its top left): on the
      straight line from its parent's centre to the middle of its child's near
      side, just before the child (*LABEL_GAP*), the way the tree grows.
    '''
    direction = self.params["direction"]
    ret:dict[VObject, tuple[float, float]] = {}
    for child, r in parentRel.items():
      parent = self._ends(r)[0]
      if parent not in positions or child not in positions:
        continue
      (px, py), (pw, ph) = positions[parent], sizes[parent]
      (cx, cy), (cw, ch) = positions[child], sizes[child]
      sx, sy = px + pw / 2, py + ph / 2
      # (toward the middle of the child's near side, not its centre: so the labels of a column of
      # children, however wide, are the same way along their lines, and as far apart as the children)
      dx = cx if direction == "right" else cx + cw if direction == "left" else cx + cw / 2
      dy = cy if direction == "down" else cy + ch if direction == "up" else cy + ch / 2
      lw, lh = layoutSize(r)
      if direction in ("right", "left"):
        x = cx - LABEL_GAP - lw / 2 if direction == "right" else cx + cw + LABEL_GAP + lw / 2
        y = sy + (dy - sy) * (x - sx) / (dx - sx) if dx != sx else (sy + dy) / 2
      else:
        y = cy - LABEL_GAP - lh / 2 if direction == "down" else cy + ch + LABEL_GAP + lh / 2
        x = sx + (dx - sx) * (y - sy) / (dy - sy) if dy != sy else (sx + dx) / 2
      ret[r] = (x - lw / 2, y - lh / 2)
    return ret

  def compute(self, dynamic:bool, fresh:set[int]=set()) -> tuple[dict[VObject, tuple[float, float]], list[VRelation]]:
    '''
    :param dynamic: Whether it's for keeping things arranged (see the class doc).
    :type dynamic: bool
    :param fresh: For *dynamic*: the ids of the nodes just pinned (dropped:
      see *adjust()*): where each was dropped, room is made for its subtree.
    :type fresh: set[int]
    :returns: Where everything arranged goes (its top left: nodes and tree
      relations' labels); and the tree's type of relations that aren't tree
      relations (see *structure()*).
    :rtype: tuple[dict[VObject, tuple[float, float]], list[VRelation]]
    '''
    roots, children, parentRel, others, loose = self.structure(dynamic)
    nodes = [*roots, *(k for gs in children.values() for g in gs for k in g), *others]
    sizes:dict[VNode, tuple[float, float]] = {}
    for n in nodes:
      sizes[n] = layoutSize(n)
    direction, spacing = self.params["direction"], float(self.params["spacing"])
    vertical = _vertical(direction)
    rel, trees = treePositions(roots, children, sizes, direction=direction, spacing=spacing,
                               levelGaps=self.levelGaps(children, parentRel, roots))
    positions:dict[VNode, tuple[float, float]] = {}
    gap = 2 * spacing # (between trees)
    if not dynamic:
      # one after another across, from the top left of what's arranged
      boxes = [n.boundingBox() for n in nodes]
      x0, y0 = (min(b[0] for b in boxes), min(b[1] for b in boxes)) if boxes else (40.0, 40.0)
      cursor = x0 if vertical else y0
      for root, box in trees:
        dx = cursor - box[0] if vertical else x0 - box[0]
        dy = y0 - box[1] if vertical else cursor - box[1]
        # (the root on whole units, as it'd be kept by the dynamic layout: the rest rounded the same way)
        dx, dy = round(rel[root][0] + dx) - rel[root][0], round(rel[root][1] + dy) - rel[root][1]
        for n in treeMembers(root, children, rel):
          positions[n] = (rel[n][0] + dx, rel[n][1] + dy)
        cursor += (box[2] - box[0] if vertical else box[3] - box[1]) + gap
      if self.params["others"] == "rows" and others:
        length = max([MIN_ROW_LENGTH] + [(b[3] - b[1]) if vertical else (b[2] - b[0]) for _, b in trees])
        along, lineSize = 0.0, 0.0
        for n in others:
          w, h = sizes[n]
          a, c = (h, w) if vertical else (w, h)
          if along > 0 and along + a > length:
            cursor, along, lineSize = cursor + lineSize + spacing, 0.0, 0.0
          positions[n] = (cursor, y0 + along) if vertical else (x0 + along, cursor)
          along, lineSize = along + a + spacing, max(lineSize, c)
    else:
      positions.update(self._keepPlaces(trees, children, rel, others, fresh, spacing))
    # whole units, as things are: so it's the same next time (the labels placed from where the nodes will be)
    positions = {n: (float(round(x)), float(round(y))) for n, (x, y) in positions.items()}
    ret:dict[VObject, tuple[float, float]] = {n: p for n, p in positions.items()}
    ret.update({r: (float(round(x)), float(round(y))) for r, (x, y) in self._labelTargets(positions, sizes, parentRel).items()})
    return ret, loose

  def _keepPlaces(self, trees:list[tuple[VNode, list[float]]], children:dict[VNode, list[list[VNode]]],
                  rel:dict[VNode, tuple[float, float]], others:list[VNode], fresh:set[int],
                  gap:float) -> dict[VNode, tuple[float, float]]:
    '''
    Dynamically: where the trees go -- each from where its root is -- and the
    nodes in no tree. When a tree grows or shrinks across (eg: something's
    added to it, or taken out), what's after it across, and alongside it (the
    trees and the nodes in no tree), moves along by as much: so things open up,
    and close up. (By the most, of the trees before it, if there's more than
    one.) A tree just dropped (see *fresh*) is taken to have been just its
    root, there: room is made for the rest. Then anything that would be on
    (or within *gap* of) a node already placed -- trees in order across, then
    the nodes in no tree -- is pushed further across, past it; but a tree just
    dropped goes to the nearest clear place, either way. Node by node, not by
    the trees' boxes, so a tree can be dropped in a gap in another.

    :param trees: The trees, laid out on their own (see *treePositions()*), by root.
    :type trees: list[tuple[VNode, list[float]]]
    :param children: As for *treePositions()*.
    :type children: dict[VNode, list[list[VNode]]]
    :param rel: Where *treePositions()* put each node, in its own tree.
    :type rel: dict[VNode, tuple[float, float]]
    :param others: The nodes in no tree.
    :type others: list[VNode]
    :param fresh: The ids of the trees' roots just dropped.
    :type fresh: set[int]
    :param gap: The space kept between nodes of different trees (and those in no tree).
    :type gap: float
    :returns: Where they go (their top left): those that move.
    :rtype: dict[VNode, tuple[float, float]]
    '''
    vertical = _vertical(self.params["direction"])
    known = self.known
    start = (lambda b: b[0]) if vertical else (lambda b: b[1])
    end = (lambda b: b[2]) if vertical else (lambda b: b[3])
    span = (lambda b: (b[1], b[3])) if vertical else (lambda b: (b[0], b[2]))
    def union(bs:list[list[float]]) -> list[float]:
      return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
    def shift(box:list[float], by:float) -> list[float]:
      return [box[0] + by, box[1], box[2] + by, box[3]] if vertical else [box[0], box[1] + by, box[2], box[3] + by]
    entries = []
    for root, box in trees:
      members = treeMembers(root, children, rel)
      if root._id in fresh: # (just dropped: it was only its root, there)
        old = list(root.boundingBox())
      else:
        old = union([m.boundingBox() for m in members if known is None or m._id in known] or [root.boundingBox()])
      entries.append((root, box, members, old))
    entries.sort(key=lambda e: start(e[3]))
    changes:list[tuple[list[float], float]] = [] # (a tree's box before, how much further across it ends now)
    def moveFor(box:list[float]) -> float:
      lo, hi = span(box)
      ds = [d for ob, d in changes if start(box) >= end(ob) - 1 and lo < span(ob)[1] and span(ob)[0] < hi]
      return max(ds) if ds else 0.0
    ret:dict[VNode, tuple[float, float]] = {}
    placed:list[list[float]] = [] # (the boxes of the nodes placed so far)
    def clear(boxes:list[list[float]]) -> float:
      '''How far across to move *boxes* so none is on (or within *gap* of) a node placed so far.'''
      total = 0.0
      for _ in range(len(placed) + 1): # (each push clears at least one more)
        push = max((end(p) + gap - start(b) for b in boxes for p in placed if _overlaps(b, p, gap)), default=0.0)
        if push <= 0:
          break
        boxes = [shift(b, push) for b in boxes]
        total += push
      return total
    def nearestClear(boxes:list[list[float]]) -> float:
      '''How far across -- either way: the least -- to move *boxes* so none is on (or within *gap* of) a node placed so far.'''
      lo, hi = min(span(b)[0] for b in boxes), max(span(b)[1] for b in boxes)
      near = [p for p in placed if p[0 if not vertical else 1] < hi + gap and lo - gap < p[2 if not vertical else 3]] # (alongside them)
      candidates = sorted({0.0} | {end(p) + gap - start(b) for b in boxes for p in near}
                                | {start(p) - gap - end(b) for b in boxes for p in near}, key=abs)
      for c in candidates:
        if not any(_overlaps(shift(b, c), p, gap) for b in boxes for p in near):
          return c
      return clear(boxes)
    for root, box, members, old in entries:
      rb = root.boundingBox()
      dx, dy = rb[0] - rel[root][0], rb[1] - rel[root][1]
      by = moveFor(old)
      dx, dy = (dx + by, dy) if vertical else (dx, dy + by)
      boxes = []
      for n in members:
        w, h = layoutSize(n)
        boxes.append([rel[n][0] + dx, rel[n][1] + dy, rel[n][0] + dx + w, rel[n][1] + dy + h])
      # (nodes, not the trees' boxes: a tree may be dropped in a gap in another; one just dropped goes to
      # the nearest clear place, either way -- where it was put, if that's clear -- others further along)
      push = nearestClear(boxes) if root._id in fresh else clear(boxes)
      dx, dy = (dx + push, dy) if vertical else (dx, dy + push)
      placed.extend(shift(b, push) for b in boxes)
      changes.append((old, end([box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy]) - end(old)))
      for n in members:
        ret[n] = (rel[n][0] + dx, rel[n][1] + dy)
    for n in sorted(others, key=lambda n: start(n.boundingBox())):
      b = list(n.boundingBox())
      moved = shift(b, moveFor(b))
      moved = shift(moved, clear([moved]))
      placed.append(moved)
      if moved != b:
        ret[n] = (moved[0], moved[1])
    return ret

  # ---- static ----------------------------------------------------------------------

  @override
  def targets(self) -> dict[VObject, tuple[float, float]]:
    return self.compute(dynamic=False)[0]

  @override
  def arranged(self, cmd:LayoutMoves) -> None:
    '''
    If the view's dynamic layout is a tree layout, the static one starts it
    afresh: its pins are let go (see *adjust()*), and what it knows is what
    this arranges. (Undone with *cmd*.)
    '''
    dyn = self.view.localLayout
    if isinstance(dyn, TreeLayout) and dyn is not self:
      oldPins, oldKnown = set(dyn.pins), dyn.known
      newKnown = {vo._id for vo in self.scope()[0]}
      def do() -> None:
        dyn.pins, dyn.known = set(), set(newKnown)
      def undo() -> None:
        dyn.pins, dyn.known = set(oldPins), oldKnown
      cmd.also.append((do, undo))

  # ---- dynamic ---------------------------------------------------------------------

  @override
  def placeNode(self, node:VObject, referenceNode:Optional[VObject]=None, direction:Direction=Direction.UNSPECIFIED,
                loc:Optional[Point]=None, **kwargs) -> Point|tuple[float, float]:
    '''
    A tree's node (or tree relation's label) is put in place by *adjust()*,
    after the command that made or moved it: it stays where it is for now.
    Anything else goes in the nearest free place (see *FindFree*).
    '''
    mo = node.modelObject
    if isinstance(node, VRelation):
      if self._isEdge(mo):
        bb = node.boundingBox()
        return bb[0], bb[1]
    elif isinstance(node, VNode) and mo is not None:
      if any(isinstance(r, VRelation) and self._isEdge(r.modelObject) for r in node.relations):
        bb = node.boundingBox()
        return bb[0], bb[1]
    return self._fallback.placeNode(node, referenceNode, direction, loc, **kwargs)

  def _drops(self, command:Command) -> list[VObject]:
    ":returns: What the user dragged and dropped in *command* (see *SNGView._Move*'s _drag)."
    ret:list[VObject] = []
    stack = [command]
    while stack:
      c = stack.pop()
      if getattr(c, "drag", False) and getattr(c, "obj", None) is not None:
        ret.append(c.obj) #type: ignore[attr-defined]
      stack.extend(getattr(c, "commands", None) or [])
    return ret

  def _adjustment(self, name:str, pinned:set[int]) -> LayoutMoves:
    '''
    :param name: What the undo menu calls it.
    :type name: str
    :param pinned: Ids of nodes to pin now (see *pins*).
    :type pinned: set[int]
    :returns: The moves that keep things arranged (see *compute()*), with
      *pinned* pinned, the relations that are no longer tree relations made to
      float, and what it knows updated: not done yet.
    :rtype: LayoutMoves
    '''
    oldPins, oldKnown = set(self.pins), self.known
    self.pins |= pinned # (for compute(): put back below, and done by the command)
    try:
      targets, loose = self.compute(dynamic=True, fresh=pinned)
    finally:
      self.pins = oldPins
    cmd = LayoutMoves(self.view, name, targets)
    newPins = oldPins | pinned
    newKnown = {vo._id for vo in self.scope()[0]}
    def do() -> None:
      self.pins, self.known = set(newPins), set(newKnown)
    def undo() -> None:
      self.pins, self.known = set(oldPins), (set(oldKnown) if oldKnown is not None else None)
    if newPins != oldPins or newKnown != oldKnown:
      cmd.also.append((do, undo))
    for r in loose: # (no longer a tree relation: its label floats between its ends again)
      if not r.floating():
        cmd.also.append((lambda r=r: r.floating(True), lambda r=r: r.floating(False)))
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
    else: # (nothing to move -- eg: just arranged by the static tree layout: no undo entry, just what it knows)
      for do, _ in cmd.also:
        do()

  @override
  def adjust(self, command:Command) -> LayoutMoves|None:
    '''
    After a command: lay the trees out again (see *compute()*). A tree node
    the user dropped (see *SNGView._Move*) that has a parent is pinned where
    it's dropped, as the root of a tree of its own (with its subtree).
    '''
    nodes, edges = self.scope()
    children = {id(self._ends(r)[1]) for r in edges}
    pinned = {vo._id for vo in self._drops(command) if isinstance(vo, VNode) and id(vo) in children}
    return self._adjustment(command.name, pinned)

  # ---- saving it with the view -----------------------------------------------------

  @override
  def extraState(self) -> dict[str, str]:
    return {"pins": ",".join(str(i) for i in sorted(self.pins))} if self.pins else {}

  @override
  def restoreExtraState(self, state:dict[str, str]) -> None:
    self.pins = {int(i) for i in state.get("pins", "").split(",") if i.strip().isdigit()}
