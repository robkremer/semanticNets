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
import sn
from sn.model.model import Relation
from typing import Iterable, Callable, Collection, Mapping, Sequence, cast
from util.utils import expandRect
from util.command import Command
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import clearOf, freeSpotIn
from util.commandParser import CompositeCommandMgr
from sn.view.graphics.viewCommands import _ContainCreated
from sn.view.graphics.viewBase import ViewBase

logger:sn.SNLogger = sn.getLogger(__name__)

# ---- The geometry of containment: rectangles and centres ([x1, y1, x2, y2] and (x, y), view coords) ----

BOTH_PANES = "both"
"The pseudo-pane (see *homePane()*) of something a rule or definition uses on both sides: astride the divider."

def rectArea(r:Sequence[float]) -> float:
  ':returns: The area of rectangle *r*.'
  return (r[2] - r[0]) * (r[3] - r[1])

def paneAt(panes:Mapping[str, Sequence[float]], pt:Sequence[float]) -> str|None:
  '''
  :param panes: A window's panes (see *VObject.panes()*), by name.
  :type panes: Mapping[str, Sequence[float]]
  :param pt: A point.
  :type pt: Sequence[float]
  :returns: The pane *pt* is in (edges included: on the divider, the first,
    the left one), or None.
  :rtype: str | None
  '''
  for name, (x1, y1, x2, y2) in panes.items():
    if x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2:
      return name
  return None

def windowAt[W](pt:Sequence[float], windows:Mapping[W, tuple[Sequence[float], Mapping[str, Sequence[float]]]]) -> W|None:
  '''
  The innermost window with a pane at *pt*: what's dropped there goes in it.

  :param pt: A point.
  :type pt: Sequence[float]
  :param windows: The windows: each one's (box, panes).
  :type windows: Mapping[W, tuple[Sequence[float], Mapping[str, Sequence[float]]]]
  :returns: Of those with a pane at *pt*, the smallest (the first, of equals); or None.
  :rtype: W | None
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
  :type center: Sequence[float]
  :param windows: The windows that have it: each one's (box, panes).
  :type windows: Mapping[W, tuple[Sequence[float], Mapping[str, Sequence[float]]]]
  :param biggerThan: Only windows bigger than this (an area): for a window,
    its own area -- a window belongs only in a bigger one (so nesting can't
    go round in circles).
  :type biggerThan: float | None
  :returns: The window; or None, if there's none (bigger).
  :rtype: W | None
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
  it on, or astride the divider (*BOTH_PANES*) if they use it on both (or
  somewhere not in a pane).

  :param panes: The window's panes, by name.
  :type panes: Mapping[str, Sequence[float]]
  :param center: Its centre.
  :type center: Sequence[float]
  :param says: If the window contains it: whether its containment says it's in a pane.
  :type says: Callable[[str], bool] | None
  :param used: If it doesn't: the panes in which the window's contents use it (None: not in a pane).
  :type used: Collection[str | None] | None
  :returns: The pane's name, or *BOTH_PANES*.
  :rtype: str
  '''
  if len(panes) == 1:
    return next(iter(panes))
  if used is not None:
    return cast(str, next(iter(used))) if len(used) == 1 and None not in used else BOTH_PANES
  here = paneAt(panes, center)
  said = [p for p in panes if says is not None and says(p)]
  if said:
    return here if here is not None and here in said else said[0]
  if here is not None:
    return here
  return min(panes, key=lambda p: abs((panes[p][0] + panes[p][2]) / 2 - center[0])) # (the nearer pane)

def sharedPane(a:str, b:str) -> str:
  '''
  :returns: The pane a relation belongs in whose ends belong in panes *a* and
    *b* of the same window: theirs; or, if they differ, the one that isn't
    astride the divider (*BOTH_PANES*), or astride it if neither is.
  :rtype: str
  '''
  panes = {a, b}
  if len(panes) > 1:
    panes.discard(BOTH_PANES)
  return panes.pop() if len(panes) == 1 else BOTH_PANES

def homeRect(panes:Mapping[str, Sequence[float]], pane:str) -> list[float]:
  '''
  :param panes: A window's panes, by name.
  :type panes: Mapping[str, Sequence[float]]
  :param pane: One of them, or *BOTH_PANES* (for a window with two).
  :type pane: str
  :returns: The area what belongs in *pane* is kept in: the pane; or, for
    *BOTH_PANES*, a band astride the divider, a third of the window wide.
  :rtype: list[float]
  '''
  if pane != BOTH_PANES:
    return list(panes[pane])
  left, right = panes.values()
  half = (right[2] - left[0]) / 6
  return [left[2] - half, left[1], left[2] + half, left[3]]

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
  :type panes: Mapping[str, Sequence[float]]
  :param old: Its centre before (a relation's: its label's), or None if it's new.
  :type old: Sequence[float] | None
  :param target: Whether the window is the one it's landed in.
  :type target: bool
  :param contained: Whether the window contains it now.
  :type contained: bool
  :param windowMove: If the window moved too: its centre (before, after) --
    whether it was in the window is judged by where it was relative to it.
  :type windowMove: tuple[Sequence[float], Sequence[float]] | None
  :param endCentres: If it's a relation dragged along by its ends: their centres.
  :type endCentres: Sequence[Sequence[float]] | None
  :returns: "in" (to be contained by the pane it's landed in: the caller
    checks it isn't already), "out" (no longer contained), or None (left be).
  :rtype: str | None
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

    :returns:
    :rtype: list[VObject]
    '''
    version = self.__dict__.get("_structureVersion", 0)
    cached = self.__dict__.get("_contextWindowsCache")
    if cached is not None and cached[0] == version:
      return cached[1]
    ret = [w for w in self.values() if w is not None and not isinstance(w, VRelation) and w._isConnected() and w.isContextWindow()]
    self.__dict__["_contextWindowsCache"] = (version, ret)
    return ret

  BOTH_PANES = BOTH_PANES
  "The pseudo-pane (see *containmentHomes()*) of something a rule or definition uses on both sides: astride the divider."

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
    variable used on both sides belongs astride the divider (*BOTH_PANES*).

    And a relation the context doesn't contain, whose two ends both belong in
    the same window, belongs there too (eg: a pattern relation's isa link to
    its type variable, !a -^r-> !b to ^r): in its ends' pane -- or, if they're
    in different ones, the one that isn't astride the divider, or astride it
    if neither is.

    :param among: Just these view objects (default: all of them).
    :type among: Iterable[VObject] | None
    :param window: Just what this window contains (and its contents use), as
      if it were the only one (default: all the windows).
    :type window: VObject | None
    :returns: Each contained view object: (its window, the pane's name).
    :rtype: dict[VObject, tuple[VObject, str]]
    '''
    m = self.model
    byObj:dict[int, dict[VObject, list[Relation]]] = {} # id(contained model object) -> {window: its containments of it}
    uses:dict[int, dict[VObject, set[str|None]]] = {}   # id(variable) -> {window: the panes of the contained relations using it}
    for w in (self.contextWindows() if window is None else [window]):
      mo = w.modelObject
      if mo is None:
        continue
      panes = w.panes()
      for r, _ in mo._getOutgoing(lambda r: r.isIndividual() and r.isa(m.CONTAINS)):
        d = r.localDst
        if d is None or d is mo:
          continue
        byObj.setdefault(id(d), {}).setdefault(w, []).append(r)
        if isinstance(d, Relation) and d.isIndividual():
          pane = "contains" if "contains" in panes else next((p for p in panes if r.isa(self._paneType(p))), None)
          for e in (d.localSrc, d.localDst, *d.getParents()):
            if e is not None and e is not mo and e.isVariable():
              uses.setdefault(id(e), {}).setdefault(w, set()).add(pane)
    if not byObj:
      return {}
    memo:dict[int, tuple[VObject, str]|None] = {}
    def home(vo:VObject) -> tuple[VObject, str]|None: # (remembered: a relation's ends are asked for again and again)
      if id(vo) not in memo:
        memo[id(vo)] = None # (so a relation between relations can't go round in circles)
        memo[id(vo)] = homeOf(vo)
      return memo[id(vo)]
    def between(vo:VRelation) -> tuple[VObject, str]|None: # (a relation whose ends belong in the same window)
      if vo.modelObject.isa(m.CONTAINS) or not all(isinstance(e, VObject) and e._isConnected() for e in (vo.src, vo.dst)): # type: ignore[union-attr]
        return None
      hs, hd = home(vo.src), home(vo.dst) #type: ignore[arg-type]
      if hs is None or hd is None or hs[0] is not hd[0]:
        return None
      return hs[0], sharedPane(hs[1], hd[1])
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
        return w, homePane(w.panes(), center, says=lambda p: any(r.isa(self._paneType(p)) for r in cands[w]))
      return w, homePane(w.panes(), center, used=cands[w]) # (used, not contained: on the side it's used on, or astride the divider)
    ret:dict[VObject, tuple[VObject, str]] = {}
    for vo in (self.values() if among is None else among):
      if vo is not None and (h := home(vo)) is not None:
        ret[vo] = h
    return ret

  def homeRect(self, w:VObject, pane:str) -> list[float]:
    '''
    The area (view coords) of window *w* that what belongs in its *pane* (see
    *containmentHomes()*) is kept in: the pane; or, for *BOTH_PANES*, a band
    astride the divider, a third of the window wide.

    :param w: A context window.
    :type w: VObject
    :param pane: One of its panes' names, or *BOTH_PANES*.
    :type pane: str
    :returns: [x1, y1, x2, y2].
    :rtype: list[float]
    '''
    return homeRect(w.panes(), pane)

  BUMP_GAP = 12.0
  "How far outside a window (view units) something that doesn't belong in it is put (see *bumpIntruders()*)."

  def windowChain(self, vo:VObject, homes:dict[VObject, tuple[VObject, str]]) -> list[VObject]:
    '''
    :param vo:
    :type vo: VObject
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :returns: The window *vo* belongs in, the window that one's in, and so on out.
    :rtype: list[VObject]
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

    :param vo:
    :type vo: VObject
    :param w:
    :type w: VObject
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :rtype: bool
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
    :rtype: list[VObject]
    '''
    return [w for w in self.contextWindows() if not w.isHidden()]

  def awayFromWindows(self, vo:VObject, box:list[float], homes:dict[VObject, tuple[VObject, str]],
                      obstacles:list[list[float]]=[], gap:float|None=None) -> tuple[float, float]|None:
    '''
    How far to move *vo*, were its box *box*, to be clear of every context
    window it doesn't belong in (see *belongsIn()*) -- the least move, keeping
    it in its own pane if it's in it now (see *containmentHomes()*), and off
    *obstacles* if it can be (see *layout.clearOf()*).

    :param vo:
    :type vo: VObject
    :param box: Its box, there.
    :type box: list[float]
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :param obstacles: Boxes not to land on.
    :type obstacles: list[list[float]]
    :param gap: The clearance (default: *BUMP_GAP*).
    :type gap: float | None
    :returns: (dx, dy) -- (0, 0) if it's clear already -- or None if there's no place.
    :rtype: tuple[float, float] | None
    '''
    windows = self._visibleWindows()
    keepOut = [list(w.boundingBox()) for w in windows if w is not vo and not self.belongsIn(vo, w, homes)]
    if not keepOut:
      return 0.0, 0.0
    within = None
    if (home := homes.get(vo)) is not None:
      r = self.homeRect(*home)
      cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
      if r[0] <= cx <= r[2] and r[1] <= cy <= r[3] and box[2] - box[0] <= r[2] - r[0] and box[3] - box[1] <= r[3] - r[1]:
        within = r # (it's in its pane: it stays in it)
    return clearOf(box, keepOut, obstacles, within=within, gap=self.BUMP_GAP if gap is None else gap)

  def _intrudes(self, vo:VObject, w:VObject, homes:dict[VObject, tuple[VObject, str]]) -> bool:
    '''
    :returns: Whether *vo* overlaps window *w* without belonging in it (see
      *belongsIn()*). Of two windows overlapping, neither in the other, the
      smaller is the one that\'s in the way.
    :rtype: bool
    '''
    if vo is w or self.belongsIn(vo, w, homes):
      return False
    a, b = vo.boundingBox(), w.boundingBox()
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
    :rtype: list[tuple[VObject, list[int], list[int]]]
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
      if not any(self._intrudes(vo, w, homes) for w in windows):
        continue
      old = list(vo.boundingBox())
      if floats(vo):
        cast(VRelation, vo).reposition(adjustPos=False) # (back between its ends -- out of the window: see VRelation.placedLabel())
      else:
        carried = set(vo.carriedContents()) if isWindow(vo) else set()
        near = expandRect(old, 400)
        obstacles = [list(o.boundingBox()) for o in objs if o is not vo and o not in carried and not isWindow(o) and not floats(o)
                     and (b := o.boundingBox())[0] < near[2] and near[0] < b[2] and b[1] < near[3] and near[1] < b[3]]
        d = self.awayFromWindows(vo, old, homes, obstacles)
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

    :param item:
    :type item: int
    :param ownerTag: The tag of the view object it's the shadow of.
    :type ownerTag: str
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

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
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

    :param pt:
    :type pt:
    :param exclude:
    :type exclude: Iterable[VObject]
    :returns:
    :rtype: VObject | None
    '''
    return windowAt(pt, {w: (w.boundingBox(), w.panes()) for w in self.contextWindows()
                         if w not in exclude and not w.collapsed}) # (not a collapsed one: what's dropped there couldn't be seen)

  def _paneType(self, pane:str) -> Relation:
    '''
    :param pane:
    :type pane: str
    :returns:
    :rtype: Relation
    '''
    m = self.model
    return {"contains": m.CONTAINS, "antecedent": m.ANTECEDENT, "consequent": m.CONSEQUENT,
            "definiendum": m.DEFINIENDUM, "definiens": m.DEFINIENS, "condition": m.CONDITION, "required": m.REQUIRED}[pane]

  def _containNewRelation(self, mgr:CompositeCommandMgr, creator:Command, typ:Relation, fromNode:VObject, toNode:VObject) -> None:
    '''
    A relation being made (by the queued command *creator*) from *fromNode* to
    *toNode* whose label will sit (midway between them) in a context window's
    pane is contained by it -- eg: one drawn between two things in a rule's
    antecedent is part of the antecedent.

    :param mgr:
    :type mgr: CompositeCommandMgr
    :param creator:
    :type creator: Command
    :param typ:
    :type typ: Relation
    :param fromNode:
    :type fromNode: VObject
    :param toNode:
    :type toNode: VObject
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
      mgr._addCommand(_ContainCreated(self.model, self._paneType(w.paneAt(pt)), w.modelObject, creator)) #type: ignore[arg-type]

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

    Relations in *draggedAlong* only moved because an end did, so their
    labels' positions say little: one is put in a window only if both its
    ends are in the window, and taken out only if neither end is. (Otherwise
    moving ?x in a rule would pull in, eg: its isa link to a type outside.)

    Call inside a *CompositeCommandMgr*, so it's undone with the move.

    :param oldCenters:
    :type oldCenters: dict[VObject, tuple[float, float] | None]
    :param draggedAlong:
    :type draggedAlong: Iterable[VObject]
    '''
    if not self.isModelEditor(): # (containment's in the model: a locked view just moves things)
      return
    along = set(draggedAlong)
    m = self.model
    windows = self.contextWindows()
    def nestedIn(w:VObject, outer:VObject) -> bool: # w is on outer's window (at any depth)?
      inner = outer.windowContents() if outer.isContextWindow() else []
      return w in inner or any(nestedIn(w, i) for i in inner if i.isContextWindow())
    for vo, old in oldCenters.items():
      mo = vo.modelObject
      if mo is None or not vo._isConnected() or not self._containable(vo):
        continue
      new = vo.centerPt()
      target = self._windowAt(new, exclude=[w for w in windows if w is vo or nestedIn(w, vo)])
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
          want = self._paneType(w.paneAt(new)) #type: ignore[arg-type]
          if any(r.isa(want) for r in rels):
            continue
          others = [r for r in rels if any(r.isa(t) for t in (m.ANTECEDENT, m.CONSEQUENT, m.DEFINIENDUM, m.DEFINIENS, m.CONDITION, m.REQUIRED))]
          if len(others) > 1: # in both panes: leave it be
            continue
          for r in others:    # switched panes
            self.context.remove(r)
          self.context.new_relation([want], individual=True, source=w.modelObject, destination=mo, model=self.model)
        elif move == "out":
          for r in rels:
            self.context.remove(r)

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
    :type w: VObject
    '''
    if not w.isContextWindow():
      return
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    margin = 10.0
    near = 100.0 # (how far out of its pane something can be and still be just nudged in; otherwise it's set out in rows)
    topMargin = 22.0 if len(w.panes()) > 1 else margin # (room for the pane labels)
    allHomes = self.containmentHomes()
    def elsewhere(vo:VObject) -> bool: # (in another window that has it)
      other = allHomes.get(vo, (None, None))[0]
      return other is not None and other is not w and other.paneAt(vo.centerPt()) is not None
    homes = {vo: pane for vo, (_, pane) in self.containmentHomes(window=w).items()
             if not floats(vo) and not elsewhere(vo)}
    def inside(box:list[float], rect:list[float]) -> bool:
      return rect[0] <= box[0] and rect[1] <= box[1] and box[2] <= rect[2] and box[3] <= rect[3]
    toMove = sorted((vo for vo, pane in homes.items() if not inside(vo.boundingBox(), self.homeRect(w, pane))),
                    key=lambda vo: (vo.boundingBox()[1], vo.boundingBox()[0]))
    if not toMove:
      logger.info(f'"{w.name}": nothing to gather.')
      return
    # Plan it all first (the commands only run when the composite ends): where each goes, and how
    # big the window must be.
    moving = set(toMove)
    labels = [o.boundingBox() for o in self.values() if o is not None and floats(o) and (o.src in moving or o.dst in moving)] # type: ignore[attr-defined]
    gap = (max([margin, *((b[2] - b[0]) + 2 * margin for b in labels)]), # (room between things for the labels between them)
           max([margin, *((b[3] - b[1]) + 2 * margin for b in labels)]))
    W = list(w.fullBoundingBox()) # (as expanded, if it's collapsed)
    def rectIn(pane:str, bb:list[float]) -> list[float]: # (the pane's rect if the window were *bb*: see VObject.panes())
      r, sx = self.homeRect(w, pane), (bb[2] - bb[0]) / (W[2] - W[0])
      return [bb[0] + (r[0] - W[0]) * sx, r[1], bb[0] + (r[2] - W[0]) * sx, r[3] + bb[3] - W[3]]
    obstacles = []
    for o in self.values():
      if o is None or o is w or o in moving or not o._isConnected() or o.isHidden():
        continue
      if floats(o) and any(e in moving for e in (o.src, o.dst)): # type: ignore[attr-defined]
        continue # (it'll follow its ends)
      b = list(o.boundingBox())
      if not isinstance(o, VRelation) and o.isContextWindow() and b[0] <= W[0] and b[1] <= W[1] and W[2] <= b[2] and W[3] <= b[3]:
        continue # (a window w is in)
      obstacles.append(b)
    bb, moves = list(W), []
    for vo in toMove:
      box = list(vo.boundingBox())
      while True:
        rect = rectIn(homes[vo], bb)
        inRect = [o for o in obstacles if o[0] < rect[2] and rect[0] < o[2] and o[1] < rect[3] and rect[1] < o[3]]
        out = max(rect[0] - box[0], box[2] - rect[2], rect[1] - box[1], box[3] - rect[3])
        if (d := freeSpotIn(box, rect, inRect, margin=margin, topMargin=topMargin, gap=gap, rows=out > near)) is not None:
          break
        # No room: grow down by its height -- and wider, if it's too wide for its pane (the panes
        # share the width).
        short = (box[2] - box[0]) + 2 * margin - (rect[2] - rect[0])
        bb[2] += short * (bb[2] - bb[0]) / (rect[2] - rect[0]) if short > 0 else 0
        bb[3] += (box[3] - box[1]) + gap[1] + margin
      placed = [box[0] + d[0], box[1] + d[1], box[2] + d[0], box[3] + d[1]]
      obstacles.append(placed)
      moves.append((vo, box, placed))
    with CompositeCommandMgr(self.context):
      if w.collapsed:
        self.context.collapse(w, False)
      if bb != W:
        self.context.resize(w, bb[0], bb[1], bb[2], bb[3])
      for vo, box, placed in moves:
        self.context.move(vo, placed[0], placed[1], _oldPos=box, adjustPos=False)
    self.resetScrollRegion(shrink=True)
    logger.info(f'"{w.name}": gathered {len(toMove)} object{"" if len(toMove) == 1 else "s"}.')
