'''
A graphical view's context windows (*ContainmentMixin*): one of the parts of
*sn.view.graphics.sngView.SNGView* (see *viewBase*).

Created on Oct 18, 2026 (from sngView.py)

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
import sn
from sn.model.model import GraphObject, Relation
from typing import Iterable, Callable, Collection, Mapping, Sequence, cast
from util.utils import expandRect
from util.command import Command
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import clearOf, freeSpotIn
from util.commandParser import CompositeCommandMgr
from sn.view.graphics.viewCommands import _ContainCreated, _Refresh
from sn.view.graphics.viewBase import ViewBase

logger:sn.SNLogger = sn.getLogger(__name__)

# ---- The geometry of containment: rectangles and centres ([x1, y1, x2, y2] and (x, y), view coords) ----

def rectArea(r:Sequence[float]) -> float:
  ':returns: The area of rectangle *r*.'
  return (r[2] - r[0]) * (r[3] - r[1])

def rectInside(box:Sequence[float], rect:Sequence[float], inset:float=0.0) -> bool:
  '''
  :param inset: How far in from *rect*'s edges *box* must be.
  :returns: Whether *box* is wholly inside *rect* (edges included).
  '''
  return rect[0] + inset <= box[0] and rect[1] + inset <= box[1] and box[2] <= rect[2] - inset and box[3] <= rect[3] - inset

PANE_INSET = 2.0
'''How far (view units) in from its pane's edges something must be to be in
it (see *ContainmentMixin.keepInPanes()*): not on the window's edge, or the
divider, where it would look astride it.'''

def rectsOverlap(a:Sequence[float], b:Sequence[float]) -> bool:
  ':returns: Whether rectangles *a* and *b* overlap (not just touch).'
  return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]

def paneAt(panes:Mapping[str, Sequence[float]], pt:Sequence[float]) -> str|None:
  '''
  :param panes: A window's panes (see *VObject.panes()*), by name.
  :param pt: A point.
  :returns: The pane *pt* is in (edges included: on the divider, the first,
    the left one), or None.
  '''
  for name, (x1, y1, x2, y2) in panes.items():
    if x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2:
      return name
  return None

def windowAt[W](pt:Sequence[float], windows:Mapping[W, tuple[Sequence[float], Mapping[str, Sequence[float]]]]) -> W|None:
  '''
  The innermost window with a pane at *pt*: what's dropped there goes in it.

  :param pt: A point.
  :param windows: The windows: each one's (box, panes).
  :returns: Of those with a pane at *pt*, the smallest (the first, of equals); or None.
  '''
  return min((w for w, (_, panes) in windows.items() if paneAt(panes, pt) is not None),
             key=lambda w: rectArea(windows[w][0]), default=None)

def homeWindow[W](center:Sequence[float], windows:Mapping[W, tuple[Sequence[float], Mapping[str, Sequence[float]]]],
                  biggerThan:float|None=None) -> W|None:
  '''
  Which of the windows that contain something (or whose contents use it) it
  belongs in: the innermost one whose pane it's in; or, if it's in none, the
  smallest (the innermost, if they're nested).

  :param center: Its centre.
  :param windows: The windows that have it: each one's (box, panes).
  :param biggerThan: Only windows bigger than this (an area): for a window,
    its own area -- a window belongs only in a bigger one (so nesting can't
    go round in circles).
  :returns: The window; or None, if there's none (bigger).
  '''
  cands = [w for w in windows if biggerThan is None or rectArea(windows[w][0]) > biggerThan]
  inside = [w for w in cands if paneAt(windows[w][1], center) is not None]
  return min(inside or cands, key=lambda w: rectArea(windows[w][0]), default=None)

def homePane(panes:Mapping[str, Sequence[float]], center:Sequence[float], *,
             says:Callable[[str], bool]|None=None, used:Collection[str|None]|None=None) -> str:
  '''
  Which pane of its window (see *homeWindow()*) something belongs in. In a
  window with one pane, that. Else, if the window contains it (*says*): the
  pane its containment says (antecedent, consequent, ...) -- the one it's in,
  if it says both -- or, for a plain "contains", the one it's in (or the
  nearer). If the window's contents only use it (*used*): the side they use
  it on -- the first (leftmost: eg, a rule's antecedent) if they use it on
  more than one; or, if one that uses it is held by a plain "contains" (which
  puts it in whichever pane it's in: None), the pane it's in (or the nearer).
  Never astride a divider: whatever's in a window is wholly in one of its
  panes (see *ContainmentMixin.keepInPanes()*).

  :param panes: The window's panes, by name, left to right.
  :param center: Its centre.
  :param says: If the window contains it: whether its containment says it's in a pane.
  :param used: If it doesn't: the panes in which the window's contents use it (None: not in a pane).
  :returns: The pane's name.
  '''
  if len(panes) == 1:
    return next(iter(panes))
  here = paneAt(panes, center)
  if used is not None:
    named = [p for p in panes if p in used]
    if named and None not in used:
      return named[0]
  else:
    said = [p for p in panes if says is not None and says(p)]
    if said:
      return here if here is not None and here in said else said[0]
  if here is not None:
    return here
  return min(panes, key=lambda p: abs((panes[p][0] + panes[p][2]) / 2 - center[0])) # (the nearer pane)

def sharedPane(panes:Mapping[str, Sequence[float]], a:str, b:str) -> str:
  '''
  :param panes: A window's panes, by name, left to right.
  :returns: The pane a relation belongs in whose ends belong in panes *a* and
    *b* of the same window: theirs; or, if they differ, the first (leftmost)
    of them -- so its label isn't astride the divider.
  '''
  if a == b:
    return a
  order = list(panes)
  return min((a, b), key=lambda p: order.index(p) if p in order else len(order))

def homeRect(panes:Mapping[str, Sequence[float]], pane:str) -> list[float]:
  '''
  :param panes: A window's panes, by name.
  :param pane: One of them.
  :returns: The area what belongs in *pane* is kept in: the pane.
  '''
  return list(panes[pane])

def containmentMove(panes:Mapping[str, Sequence[float]], old:Sequence[float]|None, *, target:bool, contained:bool,
                    windowMove:tuple[Sequence[float], Sequence[float]]|None=None,
                    endCentres:Sequence[Sequence[float]]|None=None) -> str|None:
  '''
  What moving something does to a window's containment of it: landing in the
  window (the innermost one there: see *windowAt()*) puts it in; leaving the
  window takes it out; and containment of something that was outside the
  window (eg: out in the "real world", with its contains arc showing) is
  left alone, as is a window it neither was nor is in.

  A relation dragged along by its ends (*endCentres*) says little by where
  its label is: it's put in only if both its ends are in the window, and
  taken out only if neither is (so moving ?x in a rule doesn't pull in its
  isa link to a type outside).

  :param panes: The window's panes, by name (where it is now).
  :param old: Its centre before (a relation's: its label's), or None if it's new.
  :param target: Whether the window is the one it's landed in.
  :param contained: Whether the window contains it now.
  :param windowMove: If the window moved too: its centre (before, after) --
    whether it was in the window is judged by where it was relative to it.
  :param endCentres: If it's a relation dragged along by its ends: their centres.
  :returns: "in" (to be contained by the pane it's landed in: the caller
    checks it isn't already), "out" (no longer contained), or None (left be).
  '''
  if endCentres is not None:
    endsIn = sum(1 for c in endCentres if paneAt(panes, c) is not None)
    if target and endsIn < 2:
      return None
    if not target and contained and endsIn > 0:
      return None
  if target:
    return "in"
  if contained and old is not None:
    if windowMove is not None:
      (bx, by), (ax, ay) = windowMove
      old = (old[0] + ax - bx, old[1] + ay - by)
    if paneAt(panes, old) is not None:
      return "out"
  return None

class ContainmentMixin(ViewBase):
  '''
  The context windows of a view (*sn.view.graphics.sngView.SNGView*): rules,
  definitions, queries and constraints drawn as windows holding what they
  contain. Where each thing belongs (its window and pane), keeping out of
  windows it doesn't belong in (bumping it out), stacking windows, what's
  dropped into or dragged out of one (and the "contains" relations that go
  with it), and gathering what belongs in a window into it.
  '''

  def contextWindows(self) -> list[VObject]:
    '''
    The view objects drawn as context windows (see *VObject.isContextWindow()*).
    Asked for every object each time one's drawn, so remembered until the
    view or model changes (see *structureChanged()*).
    '''
    version = self.__dict__.get("_structureVersion", 0)
    cached = self.__dict__.get("_contextWindowsCache")
    if cached is not None and cached[0] == version:
      return cached[1]
    ret = [w for w in self.values() if w is not None and not isinstance(w, VRelation) and w._isConnected() and w.isContextWindow()
           and not w.isTiledPart()] # (a pane of its box's window)
    self.__dict__["_contextWindowsCache"] = (version, ret)
    return ret

  def _containmentMaps(self, window:VObject|None=None) -> tuple[dict[int, dict[VObject, list[Relation]]], dict[int, dict[VObject, set[str|None]]]]:
    '''
    What *containmentHomes()* works from, from the model: {id(contained model
    object): {window: its containments of it}} and {id(variable): {window:
    the panes of the contained relations using it}} -- for every window, or
    just *window*. Asked for by every floating label as it's placed (eg: each
    relation of a dragged node, every tick), so remembered until the view's
    structure changes (see *structureChanged()*: objects added or deleted,
    retyped or renamed, or a relation's end moved).
    '''
    version = self.__dict__.get("_structureVersion", 0)
    cache = self.__dict__.setdefault("_containmentMapsCache", {})
    key = id(window) if window is not None else None
    hit = cache.get(key)
    if hit is not None and hit[0] == version:
      return hit[1], hit[2]
    if len(cache) > 64: # (windows come and go: don't keep every one's for ever)
      cache.clear()
    m = self.model
    byObj:dict[int, dict[VObject, list[Relation]]] = {} # id(contained model object) -> {window: its containments of it}
    uses:dict[int, dict[VObject, set[str|None]]] = {}   # id(variable) -> {window: the panes of the contained relations using it}
    for w in (self.contextWindows() if window is None else [window]):
      mo = w.modelObject
      if mo is None:
        continue
      for pane, r, d in w.paneContents(): # (what its parts contain, if it tiles them: see VObject.paneContents())
        if d is mo:
          continue
        byObj.setdefault(id(d), {}).setdefault(w, []).append(r)
        if isinstance(d, Relation) and d.isIndividual():
          for e in (d.localSrc, d.localDst, *d.getParents()):
            if e is not None and e is not mo and e.isVariable():
              uses.setdefault(id(e), {}).setdefault(w, set()).add(pane)
    cache[key] = (version, byObj, uses)
    return byObj, uses

  def containmentHomes(self, among:Iterable[VObject]|None=None, window:VObject|None=None) -> dict[VObject, tuple[VObject, str]]:
    '''
    Where each contained object belongs: the context window, and its pane
    (see *VObject.panes()*), that it should sit in -- what layouts keep it in
    (see *homeRect()*).

    What a context contains directly -- nodes, relation types, and relations
    (their labels) -- belongs in it. So do the variables a contained relation
    uses but the context doesn't contain itself: its ends (eg: the base rules'
    !a and !b) and its type (?r). An object contained by (or used in) more than
    one context (eg: by a rule and by another window on the rule) belongs in
    the innermost one whose pane it's in, or, if it's in none, the smallest
    (the innermost, if they're nested). A window belongs only in a bigger
    window (so nesting can't go round in circles).

    In a rule or definition, the pane is the one its containment says
    (antecedent, consequent, definiendum, definiens) -- the one it's in, if
    it's in both -- or, for a plain "contains", the one it's in (or nearer). A
    variable used on both sides belongs in the first, the left one (eg: the
    antecedent, where it's matched): nothing's astride a divider.

    And a relation the context doesn't contain, whose two ends both belong in
    the same window, belongs there too (eg: a pattern relation's isa link to
    its type variable, !a -^r-> !b to ^r): in its ends' pane -- or, if they're
    in different ones, the left one.

    :param among: Just these view objects (default: all of them).
    :param window: Just what this window contains (and its contents use), as
      if it were the only one (default: all the windows).
    :returns: Each contained view object: (its window, the pane's name).
    '''
    m = self.model
    byObj, uses = self._containmentMaps(window)
    if not byObj:
      return {}
    memo:dict[int, tuple[VObject, str]|None] = {}
    def home(vo:VObject) -> tuple[VObject, str]|None: # (remembered: a relation's ends are asked for again and again)
      if id(vo) not in memo:
        memo[id(vo)] = None # (so a relation between relations can't go round in circles)
        memo[id(vo)] = homeOf(vo)
      return memo[id(vo)]
    def chain(h:tuple[VObject, str]|None) -> list[tuple[VObject, str]]: # (the window something belongs in, the one that's in, and so on out)
      ret:list[tuple[VObject, str]] = []
      while h is not None and all(h[0] is not w for w, _ in ret):
        ret.append(h)
        h = home(h[0])
      return ret
    def between(vo:VRelation) -> tuple[VObject, str]|None: # (a relation whose ends belong in the same window: or one nested in it)
      if vo.modelObject.isa(m.CONTAINS) or not all(isinstance(e, VObject) and e._isConnected() for e in (vo.src, vo.dst)): # type: ignore[union-attr]
        return None
      hs, hd = home(vo.src), home(vo.dst) #type: ignore[arg-type]
      if hs is None or hd is None:
        return None
      if hs[0] is hd[0]:
        return hs[0], sharedPane(hs[0].panes(), hs[1], hd[1])
      # (one end in a window inside the other's: the innermost window both are in, and the pane each is in --
      # or the window inside it that's carrying it is)
      outer = {id(w): p for w, p in chain(hd)}
      for w, p in chain(hs):
        if id(w) in outer:
          return w, sharedPane(w.panes(), p, outer[id(w)])
      return None
    def homeOf(vo:VObject) -> tuple[VObject, str]|None:
      mo = vo.modelObject if vo is not None else None
      if mo is None or not vo._isConnected():
        return None
      direct = id(mo) in byObj
      if not direct and (id(mo) not in uses or (isinstance(vo, VRelation) and mo.isIndividual())):
        return between(vo) if isinstance(vo, VRelation) else None
      cands:dict = byObj[id(mo)] if direct else uses[id(mo)]
      isWindow = not isinstance(vo, VRelation) and vo.isContextWindow()
      center = vo.centerPt()
      w = homeWindow(center, {w: (w.fullBoundingBox(), w.panes()) for w in cands if w is not vo},
                     biggerThan=rectArea(vo.fullBoundingBox()) if isWindow else None)
      if w is None:
        return None
      if direct:
        return w, homePane(w.panes(), center, says=lambda p: any(w.paneOfRelation(r) == p for r in cands[w]))
      return w, homePane(w.panes(), center, used=cands[w]) # (used, not contained: on the side it's used on -- the left, if both)
    ret:dict[VObject, tuple[VObject, str]] = {}
    for vo in (self.values() if among is None else among):
      if vo is not None and (h := home(vo)) is not None:
        ret[vo] = h
    return ret

  def homeRect(self, w:VObject, pane:str) -> list[float]:
    '''
    The area (view coords) of window *w* that what belongs in its *pane* (see
    *containmentHomes()*) is kept in: the pane.

    :param w: A context window.
    :param pane: One of its panes' names.
    :returns: [x1, y1, x2, y2].
    '''
    return homeRect(w.panes(), pane)

  BUMP_GAP = 12.0
  "How far outside a window (view units) something that doesn't belong in it is put (see *bumpIntruders()*)."

  def windowChain(self, vo:VObject, homes:dict[VObject, tuple[VObject, str]]) -> list[VObject]:
    '''
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :returns: The window *vo* belongs in, the window that one's in, and so on out.
    '''
    ret:list[VObject] = []
    w = homes.get(vo, (None, ""))[0]
    while w is not None and w is not vo and w not in ret:
      ret.append(w)
      w = homes.get(w, (None, ""))[0]
    return ret

  def belongsIn(self, vo:VObject, w:VObject, homes:dict[VObject, tuple[VObject, str]]) -> bool:
    '''
    Whether *vo* may be in context window *w*: it's *w*; *w* contains it (or
    its contents use it), directly or by way of a window in *w*; it's a window
    that *w* is in; or it's a relation to or from *w*, or *w*'s containment of
    something (drawn as being inside it).

    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    '''
    if vo is w or w in self.windowChain(vo, homes) or vo in self.windowChain(w, homes):
      return True
    if isinstance(vo, VRelation) and (w in (vo.src, vo.dst) or vo.inWindow()):
      return True
    mo = vo.modelObject
    return mo is not None and bool(w.containmentOf(mo))

  def _visibleWindows(self) -> list[VObject]:
    '''
    :returns: The context windows that are drawn.
    '''
    return [w for w in self.contextWindows() if not w.isHidden()]

  def awayFromWindows(self, vo:VObject, box:list[float], homes:dict[VObject, tuple[VObject, str]],
                      obstacles:list[list[float]]=[], gap:float|None=None, also:Iterable[VObject]=()) -> tuple[float, float]|None:
    '''
    How far to move *vo*, were its box *box*, to be clear of every context
    window it doesn't belong in (see *belongsIn()*) -- the least move, keeping
    it in its own pane if it's in it now (see *containmentHomes()*), and off
    *obstacles* if it can be (see *layout.clearOf()*).

    :param box: Its box, there.
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :param obstacles: Boxes not to land on.
    :param gap: The clearance (default: *BUMP_GAP*).
    :param also: Windows to be clear of although it belongs in them (eg: one
      it's half out of, that may hold it from outside: see *keepInPanes()*).
    :returns: (dx, dy) -- (0, 0) if it's clear already -- or None if there's no place.
    '''
    windows = self._visibleWindows()
    also = list(also)
    keepOut = [list(w.boundingBox()) for w in windows if w is not vo and (w in also or not self.belongsIn(vo, w, homes))]
    if not keepOut:
      return 0.0, 0.0
    within = None
    if (home := homes.get(vo)) is not None:
      r = self.homeRect(*home)
      cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
      if r[0] <= cx <= r[2] and r[1] <= cy <= r[3] and box[2] - box[0] <= r[2] - r[0] and box[3] - box[1] <= r[3] - r[1]:
        within = r # (it's in its pane: it stays in it)
    return clearOf(box, keepOut, obstacles, within=within, gap=self.BUMP_GAP if gap is None else gap)

  def _intrudes(self, vo:VObject, w:VObject, homes:dict[VObject, tuple[VObject, str]], box:Sequence[float]|None=None) -> bool:
    '''
    :param box: What *vo* covers (see *VObject.drawnBox()*), if the caller has it.
    :returns: Whether *vo* overlaps window *w* (its text too, where that
      overflows its shape) without belonging in it (see *belongsIn()*). Of two
      windows overlapping, neither in the other, the smaller is the one
      that\'s in the way.
    '''
    if vo is w or self.belongsIn(vo, w, homes):
      return False
    a, b = (vo.drawnBox() if box is None else box), w.boundingBox()
    if not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]):
      return False
    if not isinstance(vo, VRelation) and vo.isContextWindow():
      area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
      return (area(a), vo._id) < (area(b), w._id) # (the smaller yields)
    return True

  def bumpIntruders(self) -> list[tuple[VObject, list[int], list[int]]]:
    '''
    Push everything drawn in a context window it doesn't belong in (see
    *belongsIn()*: eg: something a window was dropped on, or uncovered by
    expanding it, or whose containment was removed) out of it -- each the
    least it takes (see *awayFromWindows()*), onto a free place if there's one
    near. Windows go first (carrying their contents), then nodes, then
    relations' labels; a floating label is put back between its ends (see
    *VRelation.reposition()*), which keeps it out of windows itself. Done
    after every command (see *ViewDoList*), not in the middle of a drag.

    :returns: (object, its box before, after) for each one moved, in order.
    '''
    windows = self._visibleWindows()
    if not windows:
      return []
    homes = self.containmentHomes()
    objs = [o for o in self.values() if o is not None and o._isConnected() and not o.isHidden()]
    isWindow = lambda o: not isinstance(o, VRelation) and o.isContextWindow()
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    rank = lambda o: 0 if isWindow(o) else 2 if isinstance(o, VRelation) else 1
    moves:list[tuple[VObject, list[int], list[int]]] = []
    for vo in sorted(objs, key=rank):
      drawn = vo.drawnBox()
      if not any(self._intrudes(vo, w, homes, drawn) for w in windows):
        continue
      old = list(vo.boundingBox())
      if floats(vo):
        cast(VRelation, vo).reposition(adjustPos=False) # (back between its ends -- out of the window: see VRelation.placedLabel())
      else:
        carried = set(vo.carriedContents()) if isWindow(vo) else set()
        near = expandRect(old, 400)
        obstacles = [b for o in objs if o is not vo and o not in carried and not isWindow(o) and not floats(o)
                     and rectsOverlap(b := o.drawnBox(), near)]
        d = self.awayFromWindows(vo, drawn, homes, obstacles)
        if d is None or d == (0.0, 0.0):
          continue
        vo.moveTo(old[0] + d[0], old[1] + d[1], adjustPos=False)
      new = list(vo.boundingBox())
      if new != old:
        moves.append((vo, old, new))
        if isWindow(vo):
          homes = self.containmentHomes() # (what's where has changed)
    if moves:
      logger.info(f"moved {len(moves)} object{'' if len(moves) == 1 else 's'} out of windows {'it doesn' if len(moves) == 1 else 'they don'}'t belong in.")
    return moves

  def restackWindows(self) -> None:
    '''
    Put the context windows beneath everything else, each above the window
    it's on (see *containmentHomes()*): a window inside another is drawn on
    top of it, whichever was drawn last.
    '''
    windows = self.contextWindows()
    if not windows or self.canvas is None:
      return
    homes = {vo: w for vo, (w, _) in self.containmentHomes(windows).items()} if len(windows) > 1 else {}
    def depth(w:VObject) -> int:
      d = 0
      while (w := homes.get(w)) is not None and d < len(windows): #type: ignore[assignment]
        d += 1
      return d
    for w in sorted(windows, key=depth, reverse=True): # (the innermost lowered first: the outermost ends up at the bottom)
      self.canvas.tag_lower(w.tag)
    # the shadows and highlights on a window go just in front of it (see placeBehind()): the outermost first, so the innermost wins
    c = self.canvas
    for w in sorted(windows, key=depth):
      frame = w._shape.id if w._shape is not None else None
      bb = c.bbox(frame) if frame is not None else None
      if bb:
        for item in c.find_overlapping(*bb):
          tags = c.gettags(item)
          if ("shadow" in tags or "highlight" in tags) and w.tag not in tags:
            c.tag_raise(item, frame)

  def placeBehind(self, item:int, ownerTag:str) -> None:
    '''
    Stack something drawn behind a view object -- a type's shadow, or a
    highlight's glow (canvas *item*: see *decorators.ShadowDecorator*,
    *decorators.Highlight*) -- behind everything, but just in front of the
    topmost context window it's on (other than its owner's, tagged
    *ownerTag*), so the window doesn't hide it (windows are beneath
    everything: see *restackWindows()*). One spatial query
    (find_overlapping()) each.

    :param ownerTag: The tag of the view object it's the shadow of.
    '''
    c = self.canvas
    bb = c.bbox(item)
    frames = [i for i in c.find_overlapping(*bb) if "context-frame" in (tags := c.gettags(i)) and ownerTag not in tags] if bb else []
    if frames:
      c.tag_raise(item, frames[-1]) # (find_overlapping() gives them bottom to top)
    else:
      c.tag_lower(item)

  def _containable(self, vo:VObject) -> bool:
    '''
    Whether *vo* takes part in containment-by-position: not containment
    relations themselves, nor relations to or from a window.
    '''
    mo = vo.modelObject
    if mo is None or vo.isHidden() or vo.isInferred(): # (not what can't be seen, or the reasoner's: see GraphObject.inferred)
      return False
    if isinstance(vo, VRelation):
      if mo.isa(self.model.CONTAINS):
        return False
      for end in (vo.src, vo.dst):
        if isinstance(end, VObject) and not isinstance(end, VRelation) and end.isContextWindow():
          return False
    return True

  def _windowAt(self, pt, exclude:Iterable[VObject]=()) -> VObject|None:
    '''
    The innermost context window with a pane at *pt* (view coords), other than those in *exclude*.
    '''
    return windowAt(pt, {w: (w.boundingBox(), w.panes()) for w in self.contextWindows()
                         if w not in exclude and not w.collapsed}) # (not a collapsed one: what's dropped there couldn't be seen)

  def _containCommand(self, w:VObject, pane:str, target:GraphObject|None=None, creator:Command|None=None) -> _ContainCreated:
    '''
    A command that puts *target* (or what the queued command *creator*
    makes) in context window *w*'s *pane* (see *VObject.paneHolder()*): a
    "contains" relation from the window's box, or from the part the pane
    shows -- made first (a context, held by the pane's relation type), if
    the box has no part of that SN type yet.
    '''
    holder, typ, partType = w.paneHolder(pane)
    owner = w.modelObject
    assert owner is not None
    return _ContainCreated(self.model, typ, holder, creator, target=target, # type: ignore[arg-type]
                           partOf=(owner, partType) if holder is None else None) # type: ignore[arg-type]

  def _queue(self, command:Command) -> None:
    '''
    Do *command* -- queued in the composite command being made, if there is one (see *CompositeCommandMgr*).
    '''
    capture = getattr(self.context, "_capture", None)
    if capture is not None:
      capture._addCommand(command)
    else:
      self.context.doList.do(command)

  def _containNewRelation(self, mgr:CompositeCommandMgr, creator:Command, typ:Relation, fromNode:VObject, toNode:VObject) -> None:
    '''
    A relation being made (by the queued command *creator*) from *fromNode* to
    *toNode* whose label will sit (midway between them) in a context window's
    pane is contained by it -- eg: one drawn between two things in a rule's
    antecedent is part of the antecedent.
    '''
    if typ.isa(self.model.CONTAINS) or any(e.isContextWindow() for e in (fromNode, toNode) if not isinstance(e, VRelation)):
      return
    # where its label will go (see VRelation.gapMidpoint())
    from sn.view.graphics.connectors import _clipToEdgeStraight, _farPointAlong, _sub
    cs, cd = fromNode.centerPt(), toNode.centerPt()
    if fromNode is toNode or cs == cd or fromNode.containsPt(cd) or toNode.containsPt(cs):
      a, b = cs, cd
    else:
      a = _clipToEdgeStraight(fromNode, _farPointAlong(fromNode, _sub(cd, cs)))
      b = _clipToEdgeStraight(toNode, _farPointAlong(toNode, _sub(cs, cd)))
    pt = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
    w = self._windowAt(pt)
    if w is not None:
      mgr._addCommand(self._containCommand(w, cast(str, w.paneAt(pt)), creator=creator))

  def _updateContainment(self, oldCenters:dict[VObject, tuple[float,float]|None],
                         draggedAlong:Iterable[VObject]=()) -> None:
    '''
    Bring the contexts' containment into line with where the objects in
    *oldCenters* now sit. Positions are centres (a relation's is its label's);
    *oldCenters* maps each object to where it was, or None if it's new. For
    each object:

    - Landing in a window's pane (the innermost window, if they're nested)
      makes it contained by that pane's relation type (contains, or a rule's
      antecedent/consequent). Switching a rule's panes swaps the type -- unless
      it's in both, which only an explicit relation can say.
    - Leaving a window it was in removes that window's containment of it.
    - Containment of an object sitting outside the window (eg: out in the "real
      world", with its contains arc showing) is left alone.
    - A window goes into another only if that's a plain context (one pane,
      "contains"): not into a rule, definition or requirement.

    Relations in *draggedAlong* only moved because an end did, so their
    labels' positions say little: one is put in a window only if both its
    ends are in the window, and taken out only if neither end is. (Otherwise
    moving ?x in a rule would pull in, eg: its isa link to a type outside.)

    Call inside a *CompositeCommandMgr*, so it's undone with the move.
    '''
    if not self.isModelEditor(): # (containment's in the model: a locked view just moves things)
      return
    along = set(draggedAlong)
    m = self.model
    windows = self.contextWindows()
    changed = False
    def nestedIn(w:VObject, outer:VObject) -> bool: # w is on outer's window (at any depth)?
      inner = outer.windowContents() if outer.isContextWindow() else []
      return w in inner or any(nestedIn(w, i) for i in inner if i.isContextWindow())
    def usedBy(w:VObject, mo:GraphObject) -> list[VObject]: # the view objects of the relations w contains that use variable mo
      if not mo.isVariable() or w.modelObject is None:
        return []
      ret = []
      for _, _, d in w.paneContents():
        if isinstance(d, Relation) and d.isIndividual() and any(e is mo for e in (d.localSrc, d.localDst, *d.getParents())):
          ret += [vo for vo in self.viewObjectsFor(d) if vo._isConnected()]
      return ret
    for vo, old in oldCenters.items():
      mo = vo.modelObject
      if mo is None or not vo._isConnected() or not self._containable(vo):
        continue
      new = vo.centerPt()
      isWindow = not isinstance(vo, VRelation) and vo.isContextWindow()
      # (a window goes only into a plain context: one dropped on a rule, say, is just on it -- and pushed off)
      target = self._windowAt(new, exclude=[w for w in windows if w is vo or nestedIn(w, vo) or (isWindow and "contains" not in w.panes())])
      ends = [e.centerPt() for e in (vo.src, vo.dst) if isinstance(e, VObject)] if vo in along and isinstance(vo, VRelation) else None
      for w in windows:
        if w is vo:
          continue
        rels = w.containmentOf(mo)
        if w is not target and not rels: # (neither in it nor was: nothing to do)
          continue
        wOld = oldCenters.get(w)
        move = containmentMove(w.panes(), old, target=w is target, contained=bool(rels),
                               windowMove=(wOld, w.centerPt()) if wOld is not None else None, endCentres=ends)
        if move == "in":
          want = cast(str, w.paneAt(new))
          if any(w.paneOfRelation(r) in (want, None) for r in rels): # (None: a plain "contains", in whichever pane it's in)
            continue
          others = [r for r in rels if w.paneOfRelation(r) not in (want, None)]
          if len(others) > 1: # in more than one pane: leave it be
            continue
          for r in others:    # switched panes
            self.context.remove(r)
          self._queue(self._containCommand(w, want, target=mo))
          changed = True
        elif move == "out":
          users = usedBy(w, mo)
          if users and not all(u in oldCenters for u in users): # (left behind: it'd mean nothing out here)
            logger.warning(f'"{mo.name}" stays in "{w.modelObject.name}": '
                           f'{", ".join(dict.fromkeys(str(u.name) for u in users))} there use{"s" if len(users) == 1 else ""} it. '
                           f'To take it out, take {"that" if len(users) == 1 else "those"} out too.')
            continue
          for r in rels:
            self.context.remove(r)
          changed = True
    if changed:
      # What the windows contain is remembered from the model (see _containmentMaps()) and read again as soon
      # as this command's done -- by _BumpIntruders, which puts what's astride a divider wholly in its pane --
      # but the model's notifications of the change, which forget it, come later (see Model.notifyLater()).
      # Forgotten now, and again once the changes above are made: the move before them in the composite
      # (its dynamic layout placing the dropped object) may have read it again, from the model as it was.
      self.structureChanged()
      self._queue(_Refresh(self.structureChanged))

  def gatherIntoWindow(self, w:VObject) -> None:
    '''
    Move what context window *w* contains (and the variables its contents
    use) into it, each into its pane (see *containmentHomes()*), at a free
    spot -- as near as can be to where it was, if that's just outside its
    pane; otherwise set out in rows from the pane's top left, far enough
    apart for the labels of the relations between them -- as one undoable
    command. What's already in its pane stays put, and so does what sits in
    another window that also contains it. If there's no room, the window
    grows downward. A collapsed window is expanded first. Floating relations
    (their labels) aren't moved: they follow their ends.

    :param w: A context window (see *VObject.isContextWindow()*).
    '''
    if not w.isContextWindow():
      return
    plan = self._gatherPlan(w)
    if plan is None:
      logger.info(f'"{w.name}": nothing to gather.')
      return
    bb, moves = plan
    with CompositeCommandMgr(self.context):
      if w.collapsed:
        self.context.collapse(w, False)
      if bb != list(w.fullBoundingBox()):
        self.context.resize(w, bb[0], bb[1], bb[2], bb[3])
      for vo, box, placed in moves:
        self.context.move(vo, placed[0], placed[1], _oldPos=box, adjustPos=False)
    self.resetScrollRegion(shrink=True)
    logger.info(f'"{w.name}": gathered {len(moves)} object{"" if len(moves) == 1 else "s"}.')

  def _gatherPlan(self, w:VObject, which:Callable[[VObject], bool]|None=None,
                  homes:dict[VObject, tuple[VObject, str]]|None=None) -> tuple[list[float], list[tuple[VObject, list[float], list[float]]]]|None:
    '''
    Where to put what context window *w* holds that isn't in its pane (see
    *gatherIntoWindow()*), and how big *w* must be for it.

    :param which: Just those of them this says (default: all).
    :param homes: *containmentHomes()*, if the caller has it.
    :returns: *w*'s box (as expanded, if it's collapsed: grown, if need be),
      and (object, its box now, its box there) for each to move -- or None if
      there's nothing to move.
    '''
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    margin = 10.0
    near = 100.0 # (how far out of its pane something can be and still be just nudged in; otherwise it's set out in rows)
    topMargin = 22.0 if len(w.panes()) > 1 else margin # (room for the pane labels)
    allHomes = self.containmentHomes() if homes is None else homes
    def elsewhere(vo:VObject) -> bool: # (in another window that has it)
      other = allHomes.get(vo, (None, None))[0]
      return other is not None and other is not w and other.paneAt(vo.centerPt()) is not None
    homes = {vo: pane for vo, (_, pane) in self.containmentHomes(window=w).items()
             if not floats(vo) and not elsewhere(vo) and (which is None or which(vo))}
    toMove = sorted((vo for vo, pane in homes.items() if not rectInside(vo.drawnBox(), self.homeRect(w, pane), PANE_INSET)), # (its text too, where it overflows)
                    key=lambda vo: (vo.boundingBox()[1], vo.boundingBox()[0]))
    if not toMove:
      return None
    # Plan it all first (the commands only run when the composite ends): where each goes, and how
    # big the window must be.
    moving = set(toMove)
    carried = {c for vo in toMove if not isinstance(vo, VRelation) and vo.isContextWindow() for c in vo.carriedContents()} # (they go with their window)
    labels = [o.boundingBox() for o in self.values() if o is not None and floats(o) and (o.src in moving or o.dst in moving)] # type: ignore[attr-defined]
    gap = (max([margin, *((b[2] - b[0]) + 2 * margin for b in labels)]), # (room between things for the labels between them)
           max([margin, *((b[3] - b[1]) + 2 * margin for b in labels)]))
    W = list(w.fullBoundingBox()) # (as expanded, if it's collapsed)
    def rectIn(pane:str, bb:list[float]) -> list[float]: # (the pane's rect if the window were *bb*: see VObject.panes())
      r, sx = self.homeRect(w, pane), (bb[2] - bb[0]) / (W[2] - W[0])
      return [bb[0] + (r[0] - W[0]) * sx, r[1], bb[0] + (r[2] - W[0]) * sx, r[3] + bb[3] - W[3]]
    obstacles = []
    for o in self.values():
      if o is None or o is w or o in moving or o in carried or not o._isConnected() or o.isHidden():
        continue
      if floats(o) and any(e in moving or e in carried for e in (o.src, o.dst)): # type: ignore[attr-defined]
        continue # (it'll follow its ends)
      if not self.belongsIn(o, w, allHomes):
        continue # (it'll be pushed out, if it's in the way: see bumpIntruders())
      b = o.drawnBox()
      if not isinstance(o, VRelation) and o.isContextWindow() and b[0] <= W[0] and b[1] <= W[1] and W[2] <= b[2] and W[3] <= b[3]:
        continue # (a window w is in)
      obstacles.append(b)
    bb, moves = list(W), []
    for vo in toMove:
      box = vo.drawnBox() # (planned by what it covers: its text too)
      while True:
        rect = rectIn(homes[vo], bb)
        inRect = [o for o in obstacles if o[0] < rect[2] and rect[0] < o[2] and o[1] < rect[3] and rect[1] < o[3]]
        out = max(rect[0] - box[0], box[2] - rect[2], rect[1] - box[1], box[3] - rect[3])
        rows = out > near
        # (set out in rows, there's room for the labels between things; nudged in, it's kept as clear of what's
        # near as it takes not to land on it -- not moved away for its labels, nor the window grown for them)
        if (d := freeSpotIn(box, rect, inRect, margin=margin, topMargin=topMargin, gap=gap if rows else margin, rows=rows)) is not None:
          break
        # No room: wider, if it's too wide for its pane (the panes share the width); else grow down by its height.
        short = (box[2] - box[0]) + 2 * margin - (rect[2] - rect[0])
        if short > 0:
          bb[2] += math.ceil(short * (bb[2] - bb[0]) / (rect[2] - rect[0]))
        else:
          bb[3] += (box[3] - box[1]) + gap[1] + margin
      obstacles.append([box[0] + d[0], box[1] + d[1], box[2] + d[0], box[3] + d[1]])
      now = [float(v) for v in vo.boundingBox()]
      moves.append((vo, now, [now[0] + d[0], now[1] + d[1], now[2] + d[0], now[3] + d[1]]))
    return bb, moves

  def holdsOnlyInside(self, w:VObject) -> bool:
    '''
    Whether what context window *w* holds must be inside it: a window with
    more than one pane (eg: a rule's antecedent and consequent), or whose
    parts are its panes (see *GraphObject.tilesParts()*). What its parts
    hold can't be shown from outside -- the parts aren't drawn, so neither
    are their "contains" arcs -- and outside, nothing would say which part
    holds it. (What a one-pane window holds may be out in the world, its
    arc drawn: eg, a query's subject.)
    '''
    mo = w.modelObject
    return len(w.panes()) > 1 or (mo is not None and bool(mo.tilesParts()))

  def misplaced(self, homes:dict[VObject, tuple[VObject, str]]|None=None) -> tuple[dict[VObject, list[VObject]], list[tuple[VObject, VObject]]]:
    '''
    What's not wholly where it belongs (see *containmentHomes()*): astride the
    edge of its window, or of its pane (eg: a rule's divider), or outside a
    window it can't be outside. Each is to be brought wholly into its pane --
    if it's a variable (it means something only in its pattern), or its window
    holds only what's inside it (see *holdsOnlyInside()*), or its centre's
    in the window (where a drop would have put it) -- or else pushed wholly
    out of the window, its arc drawn. Not floating relation labels (they
    follow their ends, kept in their panes: see *VRelation.placedLabel()*),
    nor what's in a hidden or collapsed window.

    :param homes: *containmentHomes()*, if the caller has it.
    :returns: Each window's objects to bring into their panes; and (object,
      window) for each to push out of the window it's half in.
    '''
    homes = self.containmentHomes() if homes is None else homes
    bringIn:dict[VObject, list[VObject]] = {}
    pushOut:list[tuple[VObject, VObject]] = []
    for vo, (w, pane) in homes.items():
      mo = vo.modelObject
      if mo is None or not vo._isConnected() or vo.isHidden() or w.isHidden() or w.collapsed \
         or (isinstance(vo, VRelation) and vo.floating()):
        continue
      box = vo.drawnBox() # (its text too, where it overflows)
      if rectInside(box, self.homeRect(w, pane), PANE_INSET):
        continue
      if (not isinstance(vo, VRelation) and mo.isVariable()) or self.holdsOnlyInside(w) or w.paneAt(vo.centerPt()) is not None:
        bringIn.setdefault(w, []).append(vo)
      elif rectsOverlap(box, w.boundingBox()):
        pushOut.append((vo, w))
    return bringIn, pushOut

  def strayVariables(self, homes:dict[VObject, tuple[VObject, str]]|None=None) -> dict[VObject, list[VObject]]:
    '''
    The variables outside the window they belong in (see
    *containmentHomes()*): a variable means something only in its pattern,
    so one out on the canvas -- eg: put there by "show all", or a layout --
    is never where it's meant to be. Not those of a collapsed or hidden window.
    (They're among what *keepInPanes()* puts back.)

    :param homes: *containmentHomes()*, if the caller has it.
    :returns: Each window's strays.
    '''
    homes = self.containmentHomes() if homes is None else homes
    ret:dict[VObject, list[VObject]] = {}
    for vo, (w, _) in homes.items():
      mo = vo.modelObject
      if mo is None or isinstance(vo, VRelation) or vo.isHidden() or w.isHidden() or w.collapsed or not mo.isVariable():
        continue
      if not vo.isContextWindow() and w.paneAt(vo.centerPt()) is None:
        ret.setdefault(w, []).append(vo)
    return ret

  def keepInPanes(self) -> list[tuple[VObject, list[int], list[int]]]:
    '''
    Leave nothing astride a window's edge or a divider between its panes,
    nor outside a window it can't be outside (see *misplaced()*): each is
    put wholly in its pane, at a free spot -- nudged in, if it's near, or
    else set out in rows, as *gatherIntoWindow()* would (growing the window
    if there's no room) -- or, if it may be outside and its centre is,
    pushed wholly out, the least it takes (see *awayFromWindows()*). So
    there's never any doubt which window, or which side of a rule, holds
    something. Done after every command (see *ViewDoList*), with
    *bumpIntruders()*, and when a view's read.

    :returns: (object, its box before, after) for each one moved or resized, in order.
    '''
    moves:list[tuple[VObject, list[int], list[int]]] = []
    placed:set[VObject] = set()
    pushed:set[VObject] = set()
    for _ in range(3): # (a window grown for what's put in it moves its dividers, and what it's in may have to make room too)
      homes = self.containmentHomes()
      bringIn, pushOut = self.misplaced(homes)
      if not bringIn and not pushOut:
        break
      before = len(moves)
      for w in sorted(bringIn, key=lambda w: len(self.windowChain(w, homes))): # (the outermost first: a window carries what's in it)
        plan = self._gatherPlan(w, which=set(bringIn[w]).__contains__, homes=homes)
        if plan is None:
          continue
        bb, planned = plan
        old = list(w.boundingBox())
        if bb != old:
          w.reshape(bb)
          moves.append((w, old, list(w.boundingBox())))
        for vo, box, there in planned:
          vo.moveTo(there[0], there[1], adjustPos=False)
          moves.append((vo, [int(v) for v in box], list(vo.boundingBox())))
          placed.add(vo)
          pushed.discard(vo)
      for vo, w in pushOut:
        old = list(vo.boundingBox())
        near = expandRect(old, 400)
        obstacles = [b for o in self.values() if o is not None and o is not vo and o is not w and o._isConnected() and not o.isHidden()
                     and not (isinstance(o, VRelation) and o.floating()) and not (not isinstance(o, VRelation) and o.isContextWindow())
                     and rectsOverlap(b := o.drawnBox(), near)]
        d = self.awayFromWindows(vo, vo.drawnBox(), homes, obstacles, also=[w])
        if d is None or d == (0.0, 0.0):
          continue
        vo.moveTo(old[0] + d[0], old[1] + d[1], adjustPos=False)
        moves.append((vo, old, list(vo.boundingBox())))
        pushed.add(vo)
        placed.discard(vo)
      if len(moves) == before:
        break
    if (n := len(placed)):
      logger.info(f"put {n} object{' wholly in its pane' if n == 1 else 's wholly in their panes'}.")
    if (n := len(pushed)):
      logger.info(f"moved {n} object{'' if n == 1 else 's'} wholly out of the window{' it was' if n == 1 else 's they were'} astride.")
    return moves

  def tidyWindows(self) -> bool:
    '''
    Put what the windows hold wholly in their panes (see *keepInPanes()*),
    and push what's in a window it doesn't belong in out of it (see
    *bumpIntruders()*): eg, when a view saved before either was done (or
    by a program) is read. Not undoable. (When a view's read, it's not a
    change: it's not marked changed for it.)

    :returns: Whether anything moved.
    '''
    if not self.contextWindows():
      return False
    try:
      return bool(self.keepInPanes() + self.bumpIntruders())
    except Exception: # (a view that can't be tidied can still be shown)
      logger.exception("couldn't put what the windows hold in their panes")
      return False

  def followPanes(self, w:VObject, old:Sequence[float]) -> list[tuple[VObject, list[int], list[int]]]:
    '''
    Context window *w* has been resized by hand, from *old*: if it has more
    than one pane (eg: a rule), what's in its panes moves across with them,
    in proportion to its width (the panes share it equally: so each thing
    keeps its place in its pane, and the divider doesn't pass over it). Up
    and down, it stays put -- and anything the resize leaves outside its pane
    is put back in it afterwards (see *keepInPanes()*).

    :param old: Its box before.
    :returns: (object, its box before, after) for each one moved.
    '''
    new = list(w.boundingBox())
    if len(w.panes()) < 2 or old[2] <= old[0] or (new[0], new[2]) == (old[0], old[2]):
      return []
    scale = (new[2] - new[0]) / (old[2] - old[0])
    moves:list[tuple[VObject, list[int], list[int]]] = []
    for vo in w.carriedContents():
      if isinstance(vo, VRelation) and vo.floating(): # (it follows its ends)
        continue
      box = list(vo.boundingBox())
      cx, cy = vo.centerPt()
      if not (old[0] <= cx <= old[2] and old[1] <= cy <= old[3]): # (it wasn't in the window)
        continue
      dx = round(new[0] + (cx - old[0]) * scale - cx)
      if dx:
        vo.moveTo(box[0] + dx, box[1], adjustPos=False)
        moves.append((vo, box, list(vo.boundingBox())))
    return moves
