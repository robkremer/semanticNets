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
from typing import Any, Hashable, Iterable, Mapping, Optional, Sequence, TypeVar, override
from util.command import Command
from util.utils import Point
from sn.model.model import GraphObject, Relation
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import (LayoutHeuristic, LayoutParameter, LayoutMoves, FindFree, Direction,
                                     registerLayout, layoutSize, STATIC, DYNAMIC,
                                     _BoxIndex) # (_BoxIndex: for those that import it from here)
from sn.view.graphics.relationTable import (RelationTable, RelationRoles, PARENT_ENDS, SHAPES, PULLS, IGNORED,
                                            TERMINALS) # (PARENT_ENDS, ...: for those that import them from here)

K = TypeVar("K", bound=Hashable)

DIRECTIONS = ("right", "down", "left", "up")
"Which way a tree grows: from its root out to its leaves."


OTHERS = ("leave", "rows", "near")
'''What a static tree layout does with the nodes in no tree: leaves them where
they are; puts them in rows (lines) after the trees; or puts each near the
nodes it's related to, the way the trees grow (see *placeNear()*) -- and
those related to none of them in rows after the trees.'''

NEAR_BIAS = 4.0
'''How much more it costs a node placed near its relations (see *placeNear()*)
to move back against the way the trees grow than to move on, or across.'''

NEAR_STEP = 10.0
"The grid a node placed near its relations is put on (see *placeNear()*)."

NEAR_MAX_RINGS = 400
"How far out (in *NEAR_STEP*s) *placeNear()* looks for a free spot."

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

def treePositions(roots:list[K], children:dict[K, list[list[K]]], sizes:Mapping[K, tuple[float, float]], *,
                  direction:str="right", spacing:float=20.0, levelGaps:Optional[dict[int, float]]=None,
                  levelGap:float=MIN_LEVEL_GAP, compact:bool=False) -> tuple[dict[K, tuple[float, float]], list[tuple[K, list[float]]]]:
  '''
  Lay out some trees, each on its own: the root at depth 0, each node's
  children at the next depth -- the depths in lines (columns, for "right"),
  each as deep as its deepest node, *levelGaps* apart -- the leaves *spacing*
  apart across, each parent level with the middle of its children, and the
  groups of a node's children *spacing* further apart.

  :param roots: The trees' roots.
  :param children: Each node's children, in groups (eg: by the type of
    relation to them), in order. Each node is laid out once: under the first
    parent it's met under (a node met again is left out there).
  :param sizes: Each node's (width, height).
  :param direction: Which way the trees grow: one of *DIRECTIONS*.
  :param spacing: The space between neighbouring nodes across a level.
  :param levelGaps: The space between depth *n* and depth *n* + 1, by *n*, if not *levelGap*.
  :param levelGap: The space between depths not in *levelGaps*.
  :param compact: If False, each subtree is wholly after the one before it,
    across (its leaves after the last of the one before's). If True, each is
    only as far along as the depths they both have need: a subtree tucks in
    beside the one before wherever that one's deeper levels leave room (each
    depth's extent across -- its contour -- is kept, much as in the
    Reingold-Tilford tree drawing). The depths are the same either way; and
    either way, nothing overlaps, and the relations from parents to children
    don't cross.
  :returns: Where each node goes (its top left), with each tree's root at
    (0, 0) -- or, growing left or up, with its root's far side at 0 -- and
    each tree's nodes, and their bounding box (x1, y1, x2, y2), by root.
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
    if compact:
      packed = _packed(root, kidsOf, depthOf, crossSize, spacing)
      _record(ret, trees, root, order, packed, level, depthOf, depthSize, sizes, vertical, flip)
      continue
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
    _record(ret, trees, root, order, cross, level, depthOf, depthSize, sizes, vertical, flip)
  return ret, trees

def _record(ret:dict, trees:list, root, order:list, cross:dict, level:list[float], depthOf:dict,
            depthSize, sizes:Mapping, vertical:bool, flip:bool) -> None:
  '''
  For *treePositions()*: put a tree's nodes where they go -- at their depth's
  level, and *cross* across -- in *ret*, and its root and box in *trees*.
  '''
  box = [float("inf"), float("inf"), float("-inf"), float("-inf")]
  for n in order:
    at = level[depthOf[n]]
    at = -(at + depthSize(n)) if flip else at
    x, y = (cross[n], at) if vertical else (at, cross[n])
    ret[n] = (x, y)
    w, h = sizes[n]
    box = [min(box[0], x), min(box[1], y), max(box[2], x + w), max(box[3], y + h)]
  trees.append((root, box))

def _packed(root:K, kidsOf:dict[K, list[list[K]]], depthOf:dict[K, int], crossSize, spacing:float) -> dict[K, float]:
  '''
  For *treePositions()*, compact: where each of a tree's nodes goes across
  (its near side): each subtree is laid out on its own, keeping its contour
  -- each depth's extent across -- and each child's subtree is put as near
  the ones before it as their contours allow, at the depths they both have
  (*spacing* apart; another *spacing* between groups). Each parent is level
  with the middle of its first and last children.

  :returns: Each node's position across, the least 0.
  '''
  def pack(n:K) -> tuple[dict[K, float], dict[int, list[float]]]:
    d, size = depthOf[n], crossSize(n)
    kids = kidsOf[n]
    if not kids:
      return {n: 0.0}, {d: [0.0, size]}
    pos:dict[K, float] = {}
    contour:dict[int, list[float]] = {}
    for gi, g in enumerate(kids):
      for ki, k in enumerate(g):
        kp, kc = pack(k)
        if pos:
          gap = spacing * (2 if gi and not ki else 1) # (another spacing between groups)
          off = max((contour[lv][1] + gap - kc[lv][0] for lv in kc if lv in contour), default=0.0)
        else:
          off = 0.0
        for m, c in kp.items():
          pos[m] = c + off
        for lv, (top, bottom) in kc.items():
          if lv in contour:
            contour[lv] = [min(contour[lv][0], top + off), max(contour[lv][1], bottom + off)]
          else:
            contour[lv] = [top + off, bottom + off]
    first, last = kids[0][0], kids[-1][-1]
    pos[n] = (pos[first] + crossSize(first) / 2 + pos[last] + crossSize(last) / 2) / 2 - size / 2
    contour[d] = [pos[n], pos[n] + size]
    return pos, contour
  pos, _ = pack(root)
  low = min(pos.values())
  return {n: c - low for n, c in pos.items()}

def treeMembers(root:K, children:dict[K, list[list[K]]], positions:dict[K, Any]) -> list[K]:
  '''
  :param root: A tree's root (see *treePositions()*).
  :param children: As given to *treePositions()*.
  :param positions: What *treePositions()* returned.
  :returns: The nodes of its tree (as laid out: each under its first parent).
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

def nearestFree(size:tuple[float, float], at:tuple[float, float], index:_BoxIndex, *, direction:str|tuple[float, float]="right",
                gap:float=20.0, bias:float=NEAR_BIAS, step:float=NEAR_STEP, maxRings:int=NEAR_MAX_RINGS) -> tuple[float, float]:
  '''
  :param size: A box's (width, height).
  :param at: Where it'd best go (its top left).
  :param index: The boxes it mustn't be on (or within *gap* of).
  :param direction: Which way the trees grow (see *DIRECTIONS*), or a unit
    vector (x, y): moving on that way costs what the distance is; back,
    *bias* times as much; across, the distance.
  :returns: The cheapest free place (its top left) on a *step* grid around *at*
    (looking out *maxRings* steps) -- or *at*, if there's none.
  '''
  w, h = size
  def cost(dx:float, dy:float) -> float:
    if isinstance(direction, tuple):
      along, across = dx * direction[0] + dy * direction[1], dy * direction[0] - dx * direction[1]
    else:
      along, across = {"right": (dx, dy), "left": (-dx, dy), "down": (dy, dx), "up": (-dy, dx)}[direction]
    return (along if along >= 0 else -along * bias) + abs(across)
  best:tuple[float, float]|None = None
  bestCost = float("inf")
  for k in range(maxRings + 1):
    if k * step >= bestCost: # (nothing further out is cheaper: each costs at least its distance)
      break
    ring = [(i, j) for i in range(-k, k + 1) for j in ((-k, k) if abs(i) < k else range(-k, k + 1))] if k else [(0, 0)]
    for c, (i, j) in sorted((cost(i * step, j * step), (i, j)) for i, j in ring):
      if c >= bestCost:
        break
      x, y = at[0] + i * step, at[1] + j * step
      if not index.hits([x, y, x + w, y + h], gap):
        best, bestCost = (x, y), c
        break
  return best if best is not None else at

def placeNear(items:list[K], sizes:Mapping[K, tuple[float, float]], related:dict[K, list[K]],
              placed:Mapping[K, Sequence[float]], obstacles:Sequence[Sequence[float]], *, direction:str="right",
              spacing:float=20.0, beyond:float=MIN_LEVEL_GAP, bias:float=NEAR_BIAS) -> tuple[dict[K, tuple[float, float]], list[K]]:
  '''
  Put nodes (eg: those in no tree) near the nodes they're related to: each
  just beyond the furthest of them the way the trees grow (*beyond* past it),
  level (across) with the middle of them -- or, if that's taken, at the
  cheapest free place near there (see *nearestFree()*: moving back, against
  the way the trees grow, costs *bias* times as much as moving on). Those
  related only to others of *items* are put once those are; those related to
  nothing placed aren't put anywhere.

  :param items: The nodes to put, in order.
  :param sizes: Their (width, height).
  :param related: What each is related to (any of *placed*, or of *items*).
  :param placed: Where the nodes already placed are: their boxes.
  :param obstacles: Boxes to keep clear of too (*spacing*): eg: relations' labels.
  :returns: Where each of *items* put goes (its top left); and those not put.
  '''
  boxes = dict(placed)
  index = _BoxIndex([*boxes.values(), *obstacles])
  ret:dict[K, tuple[float, float]] = {}
  pending = list(items)
  while pending:
    ready = [n for n in pending if any(r in boxes for r in related.get(n, ()))]
    if not ready:
      break
    ready.sort(key=lambda n: -sum(1 for r in related.get(n, ()) if r in boxes)) # (the best anchored first; stable)
    for n in ready:
      rs = [boxes[r] for r in related.get(n, ()) if r in boxes]
      if not rs: # (can't happen: they only gain anchors)
        continue
      w, h = sizes[n]
      if direction in ("right", "left"):
        y = sum((b[1] + b[3]) / 2 for b in rs) / len(rs) - h / 2
        x = max(b[2] for b in rs) + beyond if direction == "right" else min(b[0] for b in rs) - beyond - w
      else:
        x = sum((b[0] + b[2]) / 2 for b in rs) / len(rs) - w / 2
        y = max(b[3] for b in rs) + beyond if direction == "down" else min(b[1] for b in rs) - beyond - h
      x, y = nearestFree((w, h), (x, y), index, direction=direction, gap=spacing, bias=bias)
      ret[n] = (x, y)
      boxes[n] = [x, y, x + w, y + h]
      index.add(boxes[n])
    done = set(ready)
    pending = [n for n in pending if n not in done]
  return ret, pending

def isMember(vo:VObject) -> bool:
  '''
  :param vo: A view object.
  :returns: Whether *vo* is something the layouts that arrange nodes (tree,
    balloon, radial, hubs) arrange as a node: a node, or a relation type (it
    has a place of its own, as a node does) -- not an individual relation's
    label, which goes between its ends.
  '''
  mo = vo.modelObject
  return mo is not None and (isinstance(vo, VNode) or (isinstance(vo, VRelation) and mo.isType()))

def isLink(r:Any) -> bool:
  '''
  :param r: A view object.
  :returns: Whether *r* is a relation shown that relates two things laid out
    (see *isMember()*): an individual relation, connected and not hidden -- not
    a relation type: its ends are its domain and range, not things it relates.
  '''
  return isinstance(r, VRelation) and r.modelObject is not None and not r.modelObject.isType() \
         and r._isConnected() and not r.isHidden()

class Terminal:
  '''
  A relation type's link to one of its own ends -- its domain or its range
  (see *relationTable.TERMINALS*) -- laid out as if it were a relation from
  the relation type to that end: one with no label of its own (the relation
  type is laid out as a node is: see *isMember()*).
  '''
  modelObject = None
  "(No relation in the model: see *RelationRoles.role()*, for the relation types' own ends.)"

  def __init__(self, relType:VRelation, end:VObject, which:int):
    '''
    :param relType: The relation type.
    :param end: Its source (domain) or destination (range).
    :param which: 0 for its source, 1 for its destination.
    '''
    self.src, self.dst, self.which = relType, end, which

  def __repr__(self) -> str:
    return f"Terminal({self.src}, {self.dst})"

def upgradeRelation(state:dict[str, str]) -> dict[str, str]:
  '''
  For the layouts that took a single relation type ("relation", and
  "parentEnd") before they took a table of them ("relations": see
  *relationTable.RelationTable.single()*): convert what an older version saved.

  :param state: What was saved (see *layout.LayoutHeuristic.upgradeParameters()*).
  :returns: It, converted.
  '''
  if "relation" in state and "relations" not in state:
    state = dict(state)
    end = state.pop("parentEnd", None)
    state["relations"] = RelationTable.single(state.pop("relation"), end if end in PARENT_ENDS else None).encode()
  return state

def relationsParameter(kwargs:dict[str, Any], relation:Any, parentEnd:str|None) -> dict[str, Any]:
  '''
  For the layouts that take a table of relation types: *kwargs*, with a single
  relation type given the old way (*relation*, *parentEnd*: eg: by a program)
  as the table that's like it (see *relationTable.RelationTable.single()*) --
  its parent end the destination if none's given, as it was -- unless a
  table's given too.
  '''
  if relation is not None and kwargs.get("relations") is None:
    kwargs = dict(kwargs, relations=RelationTable.single(relation, parentEnd or "destination"))
  return kwargs

RELATIONS_NOTE = ('Each row covers its subtypes too (unless they have rows of their own). "shapes the tree": '
                  'its relations relate parents to children (higher rows first: eg: a node with two parents '
                  'goes under the higher). "pulls together": only for joining trees and putting nodes near '
                  'what they\'re related to.')
"What the dialog says under the relation table (see *relationTable.RelationTable*)."

def _overlaps(a:list[float], b:list[float], gap:float) -> bool:
  return a[0] < b[2] + gap and b[0] < a[2] + gap and a[1] < b[3] + gap and b[1] < a[3] + gap

@registerLayout
class TreeLayout(LayoutHeuristic):
  '''
  Arrange nodes as trees by the relation types in a table (*relations*: see
  *relationTable.RelationTable*) whose rows shape the trees: each relation
  of one of those types (shown in the view) from a parent to a child --
  which end's the parent its row says -- puts the child one level out from
  the parent, the way the trees grow (*direction*). A node's children (laid
  out one after another across, or -- *compact* -- tucked in beside each
  other where there's room: see *treePositions()*) are grouped by the row
  they're related by, and then by which of its relation type's direct
  subtypes (in the order those were made: eg: for "includes", a package's
  modules, then its sub-packages), and each group's in order. A node with
  more than one parent is put under the one related by the highest row (the
  first related, of those); its other relations are left floating, as are
  those that would make a cycle. Each tree relation's label is put just
  before its child, on the straight line from the parent (so the labels line
  up, and the lines stay straight). The rows that pull things together (and
  those that shape the trees) are what join trees (see *balloonLayout.TREES*)
  and put the nodes in no tree near what they're related to (*others*).

  Relation types shown are arranged as nodes are (see *isMember()*): eg: by
  isa, has-parent under has-ancestor -- and, by the table's row for them (see
  *relationTable.TERMINALS*), by their own ends (their domain and range), as
  if each were related to them. Nodes in a context window (or that are one)
  aren't arranged.

  As a static layout (see *arrange()*): the children are in order of name;
  the trees are put one after another (across the way they grow) from the
  top left of what's arranged; and the nodes in no tree are left where
  they are, put in rows after the trees, or put near what they're related
  to (*others*: see *OTHERS*).

  As a dynamic layout (see *adjust()*): after each command, the trees are
  laid out again, each from where its root is: children in the order they
  are already, and new ones after them, by name. So a tree opens up for
  what's added to it, and closes up over what's removed or hidden -- and
  what's after it, across (the trees and the nodes in no tree alongside it),
  moves along by as much (see *_keepPlaces()*). A tree node the user drags
  (and drops) takes its subtree with it: it's pinned there, as the root of a
  tree of its own (room is made for its subtree), until the next static
  tree layout. The nodes in no tree are left where they are, put in rows
  after the trees, or put near what they're related to (*others*), again
  each time -- except those the user drops somewhere, which are pinned
  there too. Nothing's left on another node: what would be is pushed
  further across.
  '''
  NAME = "tree"
  CATEGORIES = (STATIC, DYNAMIC)
  PARAMETERS = (
    LayoutParameter("relations", "Relations", "relations", None, note=RELATIONS_NOTE),
    LayoutParameter("direction", "Grows", "choice", "right", DIRECTIONS),
    LayoutParameter("spacing", "Space between neighbours", "int", 20),
    LayoutParameter("compact", "Compact: subtrees tuck in beside each other", "bool", False,
                    note="Each subtree only as far along as the levels it shares with the one before need."),
    LayoutParameter("others", "Nodes in no tree", "choice", "leave", OTHERS,
                    note='"rows": in rows after the trees. "near": each near what it\'s related to, the way the '
                         'trees grow (those related to nothing there in rows). Kept arranged, one you move stays '
                         'where you put it.'),
  )

  def __init__(self, view, relation:Any=None, parentEnd:str|None=None, **kwargs):
    '''
    :param view:
    :type view: SNGView
    :param relation: The simple way to give the table (*relations*), for a
      single relation type (a *Relation*, or its name): it shapes the trees;
      every other relation pulls things together (see
      *relationTable.RelationTable.single()*). Not if *relations* is given.
    :param parentEnd: With *relation*: which end of its relations is the
      parent: "source" or "destination" (the default).
    :param kwargs: See *PARAMETERS*: relations (a *relationTable.RelationTable*,
      or its text: by default, as *relation* isa), direction (see *DIRECTIONS*),
      spacing, compact (see *treePositions()*), others (see *OTHERS*: static only).
    '''
    super().__init__(view, **relationsParameter(kwargs, relation, parentEnd))
    if self.params["relations"] is None:
      self.params["relations"] = RelationTable.single("isa")
    if self.params["direction"] not in DIRECTIONS:
      raise ValueError(f'TreeLayout: direction must be one of {", ".join(DIRECTIONS)}, not "{self.params["direction"]}".')
    if parentEnd is not None and parentEnd not in PARENT_ENDS:
      raise ValueError(f'TreeLayout: parentEnd must be one of {", ".join(PARENT_ENDS)}, not "{parentEnd}".')
    self._roles:RelationRoles|None = None
    self.pins:set[int] = set()
    "The ids (*VObject._id*) of the tree nodes the user has dropped, pinned as roots of their own (see *adjust()*)."
    self.known:set[int]|None = None
    "The ids of the nodes it laid out last time (None: all those there are): a new one goes after the others."
    self._fallback = FindFree(view)
    "What places what isn't in a tree (see *placeNode()*)."

  @classmethod
  @override
  def upgradeParameters(cls, state:dict[str, str]) -> dict[str, str]:
    ":returns: *state*, with a single relation type saved by an older version as a table (see *upgradeRelation()*)."
    return upgradeRelation(state)

  # ---- what's arranged -----------------------------------------------------------

  @property
  def roles(self) -> RelationRoles:
    ":returns: The relation table, for the view's model (see *RelationRoles*): found afresh each time things are arranged."
    if self._roles is None:
      self._roles = self.params["relations"].roles(self.view.model)
    return self._roles

  def _role(self, r:Any) -> str:
    ":returns: What a relation shown, or a relation type's link to an end (see *Terminal*), does (see *relationTable.ROLES*)."
    return self.roles.role(r.modelObject)

  def _order(self, r:Any) -> tuple[int, int, int]:
    ":returns: How highly a tree relation is ranked (lower first): by its row, then in the order made."
    if isinstance(r, Terminal):
      return self.roles.rank(None), r.src._id, r.which
    return self.roles.rank(r.modelObject), r._id, 0

  def terminals(self, ids:set[int], nodes:Iterable[VObject]) -> list[Terminal]:
    '''
    :param ids: The ids (*id()*) of what's arranged.
    :param nodes: What's arranged.
    :returns: The links of the relation types among *nodes* to their own ends
      that are arranged too (see *Terminal*): source first.
    '''
    ret:list[Terminal] = []
    for t in nodes:
      if isinstance(t, VRelation):
        for which, end in enumerate((t.src, t.dst)):
          if isinstance(end, VObject) and end is not t and id(end) in ids and not (which and end is t.src):
            ret.append(Terminal(t, end, which))
    return ret

  def related(self, n:VObject, ids:set[int]) -> list[tuple[VObject, Any]]:
    '''
    :param n: Something arranged (see *isMember()*).
    :param ids: The ids (*id()*) of what's arranged.
    :returns: What else arranged *n* is related to by the rows of the table
      that aren't ignored (see *relationTable.ROLES*): each once, with the
      (first) relation -- or relation type's link to its end (see *Terminal*)
      -- between them; by relations in the order made, then the ends.
    '''
    terminalsCount = self.roles.role(None) != IGNORED
    ret:dict[int, tuple[VObject, Any]] = {}
    def add(other:Any, r:Any) -> None:
      if isinstance(other, VObject) and other is not n and id(other) in ids and id(other) not in ret:
        ret[id(other)] = (other, r)
    for r in sorted((r for r in n.relations if isinstance(r, VRelation)), key=lambda r: r._id):
      if isLink(r):
        if self._role(r) != IGNORED:
          add(r.dst if r.src is n else r.src, r)
      elif terminalsCount and isMember(r): # (a relation type n is an end of)
        add(r, Terminal(r, n, 0 if r.src is n else 1))
    if terminalsCount and isinstance(n, VRelation) and isMember(n):
      for which, end in enumerate((n.src, n.dst)):
        add(end, Terminal(n, end, which)) #type: ignore[arg-type]
    return list(ret.values())

  def shaped(self, node:VObject) -> bool:
    '''
    :param node: Something arranged (see *isMember()*).
    :returns: Whether it's related to anything by a relation that shapes the
      trees (see *relationTable.SHAPES*): so it may be in a tree.
    '''
    if any(isLink(r) and self._isEdge(r.modelObject) for r in node.relations):
      return True
    if self.roles.role(None) != SHAPES:
      return False
    return any(isMember(r) for r in node.relations if isinstance(r, VRelation)) or \
           (isinstance(node, VRelation) and any(isinstance(e, VObject) and e is not node for e in (node.src, node.dst)))

  def _isEdge(self, mo:GraphObject|None) -> bool:
    ":returns: Whether *mo* is a relation whose row shapes the trees (see *relationTable.SHAPES*)."
    if mo is None or not isinstance(mo, Relation) or not mo.isIndividual():
      return False
    return self.roles.role(mo) == SHAPES

  def _group(self, r:Any) -> tuple[int, int]:
    '''
    :returns: Which group a child related by *r* is in: by its row, then by
      which of its relation type's direct subtypes (see *RelationRoles.group()*).
    '''
    return self.roles.rank(r.modelObject), self.roles.group(r.modelObject)

  def scope(self) -> tuple[list[VObject], list[Any]]:
    '''
    :returns: What's arranged: the nodes and relation types shown (see
      *isMember()*: not hidden), not in a context window nor one; and the
      relations shown between them whose rows shape the trees (see
      *relations*), not to themselves -- and the relation types' links to
      their ends, if their row does (see *Terminal*).
    '''
    v = self.view
    windows = v.contextWindows()
    inWindows = {id(vo) for w in windows for vo in w.windowContents()} | {id(vo) for vo in v.containmentHomes()}
    nodes = [vo for vo in v.values() if vo is not None and isMember(vo) and vo._isConnected() and not vo.isHidden()
             and not vo.isContextWindow() and id(vo) not in inWindows]
    ids = {id(n) for n in nodes}
    edges:list[Any] = [r for r in v.values() if isLink(r) and self._isEdge(r.modelObject) and id(r.src) in ids and id(r.dst) in ids and r.src is not r.dst]
    if self.roles.role(None) == SHAPES:
      edges += self.terminals(ids, nodes)
    return nodes, edges

  def _ends(self, r:Any) -> tuple[VObject, VObject]:
    ":returns: (parent, child) of a tree relation (or a relation type's link to an end: see *Terminal*), as its row says."
    if self.roles.parentEnd(r.modelObject) == "source":
      return r.src, r.dst #type: ignore[return-value]
    return r.dst, r.src #type: ignore[return-value]

  def structure(self, dynamic:bool) -> tuple[list[VObject], dict[VObject, list[list[VObject]]], dict[VObject, Any], list[VObject], list[VRelation]]:
    '''
    :param dynamic: Whether it's for keeping things arranged (see the class
      doc): children in the order they are, new ones after; pinned nodes the
      roots of their own trees. Else children in order of name.
    :returns: The trees: their roots (in order across); each node's children,
      in groups (see the class doc); each child's tree relation (from its
      parent: a relation, or a relation type's link to an end -- see
      *Terminal*); the nodes in no tree; and the relations whose rows shape
      the trees that aren't tree relations (eg: to a second parent).
    '''
    self._roles = None # (afresh: the model's relation types may have changed)
    nodes, edges = self.scope()
    vertical = _vertical(self.params["direction"])
    crossOf = lambda vo: vo.centerPt()[0] if vertical else vo.centerPt()[1]
    name = lambda vo: (str(vo.modelObject.name).lower() if vo.modelObject is not None else "", vo._id)
    known = self.known
    def key(vo:VObject) -> tuple:
      if not dynamic:
        return (0, *name(vo))
      if known is None or vo._id in known:
        return (0, crossOf(vo), vo._id)
      return (1, *name(vo)) # (new: after the others)
    pinned = {vo._id for vo in nodes} & self.pins if dynamic else set()
    parentRel:dict[VObject, Any] = {}
    for r in sorted(edges, key=self._order): # (the first parent: by the highest row, the first related, of those not pinned)
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
    groups:dict[VObject, dict[tuple[int, int], list[VObject]]] = {}
    for child, r in parentRel.items():
      groups.setdefault(self._ends(r)[0], {}).setdefault(self._group(r), []).append(child)
    children = {p: [sorted(g[i], key=key) for i in sorted(g)] for p, g in groups.items()}
    inTree = set(parentRel) | set(children)
    roots = sorted((n for n in nodes if n in inTree and n not in parentRel), key=key)
    others = sorted((n for n in nodes if n not in inTree), key=key)
    loose = [r for r in edges if isinstance(r, VRelation) and parentRel.get(self._ends(r)[1]) is not r]
    return roots, children, parentRel, others, loose

  # ---- where things go -------------------------------------------------------------

  def levelGaps(self, children:dict[VObject, list[list[VObject]]], parentRel:dict[VObject, Any],
                roots:list[VObject]) -> dict[int, float]:
    '''
    :returns: The space between each depth of the trees and the next: room
      for the line to the widest label there (*MIN_LINE*), the label, and
      *LABEL_GAP* -- at least *MIN_LEVEL_GAP* (all there is between a relation
      type and its end: see *Terminal*).
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
            if isinstance(parentRel[k], VRelation):
              w, h = layoutSize(parentRel[k])
              ret[d] = max(ret.get(d, MIN_LEVEL_GAP), (h if vertical else w) + MIN_LINE + 2 * LABEL_GAP)
            else: # (no label)
              ret[d] = ret.get(d, MIN_LEVEL_GAP)
            nxt.append((k, d + 1))
      level = nxt
    return ret

  def _labelTargets(self, positions:dict[VObject, tuple[float, float]], sizes:dict[VObject, tuple[float, float]],
                    parentRel:dict[VObject, Any]) -> dict[VObject, tuple[float, float]]:
    '''
    :returns: Where each tree relation's label goes (its top left): on the
      straight line from its parent's centre to the middle of its child's near
      side, just before the child (*LABEL_GAP*), the way the tree grows. (Not
      a relation type's link to its end: it has no label -- see *Terminal*.)
    '''
    direction = self.params["direction"]
    ret:dict[VObject, tuple[float, float]] = {}
    for child, r in parentRel.items():
      parent = self._ends(r)[0]
      if not isinstance(r, VRelation) or parent not in positions or child not in positions:
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
    :param fresh: For *dynamic*: the ids of the nodes just pinned (dropped:
      see *adjust()*): where each was dropped, room is made for its subtree.
    :returns: Where everything arranged goes (its top left: nodes and tree
      relations' labels); and the tree's type of relations that aren't tree
      relations (see *structure()*).
    '''
    roots, children, parentRel, others, loose = self.structure(dynamic)
    nodes = [*roots, *(k for gs in children.values() for g in gs for k in g), *others]
    sizes:dict[VObject, tuple[float, float]] = {}
    for n in nodes:
      sizes[n] = layoutSize(n)
    direction, spacing = self.params["direction"], float(self.params["spacing"])
    vertical = _vertical(direction)
    rel, trees = treePositions(roots, children, sizes, direction=direction, spacing=spacing,
                               levelGaps=self.levelGaps(children, parentRel, roots), compact=bool(self.params["compact"]))
    positions:dict[VObject, tuple[float, float]] = {}
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
      inRows = others if self.params["others"] == "rows" else []
      if self.params["others"] == "near" and others:
        positions = {n: (float(round(x)), float(round(y))) for n, (x, y) in positions.items()} # (as kept arranged: the same)
        near, inRows = self._placeNear(others, positions, sizes, parentRel)
        positions.update(near)
        if inRows: # (the rows after everything placed: the trees, and those near them)
          ends = [(p[0] + sizes[n][0]) if vertical else (p[1] + sizes[n][1]) for n, p in positions.items()]
          cursor = max([cursor - gap, *ends]) + gap
      if inRows:
        positions.update(self._rows(inRows, sizes, cursor, x0, y0, trees))
    else:
      mode = self.params["others"]
      # (in a fixed order -- by name -- so placing them again places them the same: not by where they are)
      movable = [] if mode == "leave" else \
                sorted((n for n in others if n._id not in self.pins), key=lambda n: (str(n.modelObject.name).lower(), n._id)) #type: ignore[union-attr]
      stay = [n for n in others if n not in set(movable)] # (those the user's put somewhere: see adjust())
      positions.update(self._keepPlaces(trees, children, rel, stay, fresh, spacing))
      if movable:
        positions = {n: (float(round(x)), float(round(y))) for n, (x, y) in positions.items()} # (as arranged now: the same)
        base = dict(positions)
        for n in stay:
          if n not in base:
            bb = n.boundingBox()
            base[n] = (bb[0], bb[1])
        inRows = movable
        if mode == "near":
          near, inRows = self._placeNear(movable, base, sizes, parentRel)
          positions.update(near)
          base.update(near)
        if inRows: # (after everything else, across)
          extents = [(p[0], p[1], p[0] + sizes[n][0], p[1] + sizes[n][1]) for n, p in base.items()]
          x0, y0 = (min(b[0] for b in extents), min(b[1] for b in extents)) if extents else (40.0, 40.0)
          cursor = (max(b[2] for b in extents) if vertical else max(b[3] for b in extents)) + gap if extents else (x0 if vertical else y0)
          positions.update(self._rows(inRows, sizes, cursor, x0, y0, trees))
    # whole units, as things are: so it's the same next time (the labels placed from where the nodes will be)
    positions = {n: (float(round(x)), float(round(y))) for n, (x, y) in positions.items()}
    ret:dict[VObject, tuple[float, float]] = {n: p for n, p in positions.items()}
    ret.update({r: (float(round(x)), float(round(y))) for r, (x, y) in self._labelTargets(positions, sizes, parentRel).items()})
    return ret, loose

  def _rows(self, nodes:list[VObject], sizes:dict[VObject, tuple[float, float]], cursor:float, x0:float, y0:float,
            trees:list[tuple[VObject, list[float]]]) -> dict[VObject, tuple[float, float]]:
    '''
    For *others* "rows": put *nodes* in rows (lines along the way the trees
    grow), starting *cursor* across, from *x0* or *y0* along: each row as long
    as the trees are deep (at least *MIN_ROW_LENGTH*).

    :returns: Where they go (their top left).
    '''
    vertical, spacing = _vertical(self.params["direction"]), float(self.params["spacing"])
    length = max([MIN_ROW_LENGTH] + [(b[3] - b[1]) if vertical else (b[2] - b[0]) for _, b in trees])
    ret:dict[VObject, tuple[float, float]] = {}
    along, lineSize = 0.0, 0.0
    for n in nodes:
      w, h = sizes[n]
      a, c = (h, w) if vertical else (w, h)
      if along > 0 and along + a > length:
        cursor, along, lineSize = cursor + lineSize + spacing, 0.0, 0.0
      ret[n] = (cursor, y0 + along) if vertical else (x0 + along, cursor)
      along, lineSize = along + a + spacing, max(lineSize, c)
    return ret

  def _placeNear(self, others:list[VObject], positions:dict[VObject, tuple[float, float]],
                 sizes:dict[VObject, tuple[float, float]], parentRel:dict[VObject, Any]) -> tuple[dict[VObject, tuple[float, float]], list[VObject]]:
    '''
    For *others* "near": where each node in no tree goes, near the nodes it's
    related to (by the rows that aren't ignored: see *related()*), clear of
    the trees' nodes and their relations' labels (see *placeNear()*).

    :param others: The nodes in no tree.
    :param positions: Where the trees' nodes are going.
    :param sizes: Everything's (width, height).
    :param parentRel: The tree relations (see *structure()*).
    :returns: Where those put go; and those related to nothing placed (for the rows).
    '''
    ids = {id(n) for n in [*positions, *others]}
    related:dict[VObject, list[VObject]] = {n: [other for other, _ in self.related(n, ids)] for n in others}
    placed = {n: [x, y, x + sizes[n][0], y + sizes[n][1]] for n, (x, y) in positions.items()}
    labels = []
    for label, (x, y) in self._labelTargets(positions, sizes, parentRel).items():
      w, h = layoutSize(label)
      labels.append([x, y, x + w, y + h])
    return placeNear(others, sizes, related, placed, labels, direction=self.params["direction"],
                     spacing=float(self.params["spacing"]))

  def _keepPlaces(self, trees:list[tuple[VObject, list[float]]], children:dict[VObject, list[list[VObject]]],
                  rel:dict[VObject, tuple[float, float]], others:list[VObject], fresh:set[int],
                  gap:float) -> dict[VObject, tuple[float, float]]:
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
    :param children: As for *treePositions()*.
    :param rel: Where *treePositions()* put each node, in its own tree.
    :param others: The nodes in no tree.
    :param fresh: The ids of the trees' roots just dropped.
    :param gap: The space kept between nodes of different trees (and those in no tree).
    :returns: Where they go (their top left): those that move.
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
    ret:dict[VObject, tuple[float, float]] = {}
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
    if not isMember(node):
      if self._isEdge(node.modelObject):
        bb = node.boundingBox()
        return bb[0], bb[1]
    else:
      if self.shaped(node):
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
    :param pinned: Ids of nodes to pin now (see *pins*).
    :returns: The moves that keep things arranged (see *compute()*), with
      *pinned* pinned, the relations that are no longer tree relations made to
      float, and what it knows updated: not done yet.
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
    it's dropped, as the root of a tree of its own (with its subtree); a
    node in no tree the user dropped is pinned there too, so it's left
    there, not put in rows or near what it's related to (see *others*).
    '''
    self._roles = None # (afresh: the model's relation types may have changed)
    nodes, edges = self.scope()
    children = {id(self._ends(r)[1]) for r in edges}
    inTree = children | {id(self._ends(r)[0]) for r in edges}
    pinned = {vo._id for vo in self._drops(command) if isMember(vo)
              and (id(vo) in children or id(vo) not in inTree)} # (a child, or in no tree: not a root -- it's kept where it is anyway)
    return self._adjustment(command.name, pinned)

  # ---- saving it with the view -----------------------------------------------------

  @override
  def extraState(self) -> dict[str, str]:
    return {"pins": ",".join(str(i) for i in sorted(self.pins))} if self.pins else {}

  @override
  def restoreExtraState(self, state:dict[str, str]) -> None:
    self.pins = {int(i) for i in state.get("pins", "").split(",") if i.strip().isdigit()}
