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
from sn.model.model import Model
from traceback import format_exc
from concurrent.futures.thread import ThreadPoolExecutor
from concurrent.futures._base import Future
from concurrent.futures.process import ProcessPoolExecutor
import sn

'''
Created on Nov 19, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''

import logging
import weakref
from typing import Optional, Generator, override, Tuple, TYPE_CHECKING, Any
from time import monotonic_ns
from math import sqrt, acos, pi
from random import random
from threading import Thread
import queue

from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView as SNView # (the old SNView's successor)

logger:sn.SNLogger = sn.getLogger(__name__)

class WeakrefError(Exception):
  'Specific error for FieldsLayout to signal the destruction of the owner SNView object'
  pass

def isEligible(obj:VObject) -> bool:
  '''
  Whether *obj* takes part in the fields layout as a body of its own: shown
  nodes, context windows and relation types -- not individual relations (their
  labels float between their ends) or hidden objects. What a context contains
  is a body inside its window (see *Snapshot.owners*).

  :param obj: A view object.
  :type obj: VObject
  :returns: True iff *obj* is laid out.
  :rtype: bool
  '''
  mo = obj.modelObject
  if mo is None or not obj._isConnected() or obj.isHidden():
    return False
  return not (isinstance(obj, VRelation) and not mo.isType())

PANE_MARGIN = 10.0
"The space (view units) a layout keeps between what a context window contains and the edges of its pane."
PANE_LABEL = 12.0
"The extra space it keeps at the top of a labelled pane (a rule's or definition's), for the label."

FLOW_DIRECTIONS:dict[str, tuple[float, float]] = {
  "down": (0.0, 1.0), "up": (0.0, -1.0), "right": (1.0, 0.0), "left": (-1.0, 0.0),
  "down-right": (0.7071, 0.7071), "down-left": (-0.7071, 0.7071),
  "up-right": (0.7071, -0.7071), "up-left": (-0.7071, -0.7071)}
"The directions a layout's current can flow in (see *FieldsLayout.flowDirection*), as unit vectors (y is down)."

class Snapshot:
  '''
  The layout's view of the graph at one moment, as plain numbers -- so the
  forces can be calculated away from the GUI (eg: in a thread: Tk isn't
  thread-safe).

  What a context contains (see *SNGView.containmentHomes()*) is a body in its
  window: it's kept in its pane (a rule's antecedent, ...), and it's pushed and
  pulled only by the other bodies in the same window -- a relation to something
  outside pulls the window (or the window it's in, ...) instead. It moves with
  its window, and within it.
  '''
  def __init__(self, view:SNView, relationWeights:dict[str, float], flowRelation:Any=None):
    '''
    Take the snapshot (on the GUI thread).

    :param flowRelation: If given, a relation type: its relations are recorded,
      by direction, in *directed* (for a layout's current: see *forces()*).
    :type flowRelation: Relation|None

    :param view: The view to lay out.
    :type view: SNView
    :param relationWeights: The weight (0..1) of each relation type by name; "*" for the rest.
    :type relationWeights: dict[str, float]
    '''
    homes = view.containmentHomes()
    self.objects:list[VObject] = [vo for vo in view.values() if vo is not None and (isEligible(vo) or self._placed(vo, homes))]
    index = {id(vo): i for i, vo in enumerate(self.objects)}
    self.pinned:set[int] = {i for i, vo in enumerate(self.objects) if isinstance(vo, VRelation) and vo.modelObject.isIndividual() and vo.floating()}
    "The relations' labels (by index) that float now, but are placed in their panes: moving them pins them (see *_placed()*)."
    self.owners:list[int|None] = [None] * len(self.objects)
    "The window (by index) each object is in (see *SNGView.containmentHomes()*), or None for one out on the canvas."
    self.regions:list[tuple[float, float, float, float]|None] = [None] * len(self.objects)
    "The area (x1, y1, x2, y2) the contained objects' footprints are kept in: their panes, less a margin; None for the rest."
    for i, vo in enumerate(self.objects):
      w, pane = homes.get(vo, (None, ""))
      if w is not None and id(w) in index:
        self.owners[i] = index[id(w)]
        x1, y1, x2, y2 = view.homeRect(w, pane)
        top = PANE_LABEL if len(w.panes()) > 1 else 0.0
        self.regions[i] = (x1 + PANE_MARGIN, y1 + PANE_MARGIN + top, x2 - PANE_MARGIN, y2 - PANE_MARGIN)
    self.chains:list[list[int]] = []
    "Each object (by index), then the window it's in, the window that's in, ..., out to the canvas."
    for i in range(len(self.objects)):
      chain = [i]
      while (o := self.owners[chain[-1]]) is not None and len(chain) <= len(self.objects):
        chain.append(o)
      self.chains.append(chain)
    self.passengers:dict[int, list[VObject]] = {}
    '''
    What moves with each window (by index) that isn't a body itself: what it
    contains that's hidden (eg: in a collapsed window), and labels placed by
    hand inside it.
    '''
    floats = lambda vo: isinstance(vo, VRelation) and vo.floating() # (follows its ends: not moved itself)
    parents:dict[VObject, VObject] = {vo: w for vo, (w, _) in homes.items() if id(vo) not in index and not floats(vo)}
    for w in view.contextWindows():
      for vo in w.windowContents():
        if id(vo) not in index and not floats(vo):
          parents.setdefault(vo, w)
    for vo in parents:
      w, steps = parents[vo], 0
      while id(w) not in index and w in parents and steps < len(parents):
        w, steps = parents[w], steps + 1
      if id(w) in index:
        self.passengers.setdefault(index[id(w)], []).append(vo)
    self.positions:list[tuple[float, float]] = [vo.centerPt() for vo in self.objects]
    "The objects' centres, in the same order."
    self.halfSizes:list[tuple[float, float]] = []
    '''
    The objects' half widths and heights about their centres, in the same order:
    distances are measured between their edges. A node's size includes its
    label's text, if that spills outside its box (eg: a long name in a box of
    fixed size) -- what you see is what's kept apart.
    '''
    for vo, (cx, cy) in zip(self.objects, self.positions):
      x1, y1, x2, y2 = vo.boundingBox()
      text = None if isinstance(vo, VRelation) else vo.decorators.get("text")
      tb = view.canvas.bbox(text.id) if text is not None and getattr(text, "id", None) is not None else None
      if tb: # (window coordinates -> view coordinates)
        tx1, ty1, tx2, ty2 = view.windowToView(*tb)
        x1, y1, x2, y2 = min(x1, tx1), min(y1, ty1), max(x2, tx2), max(y2, ty2)
      self.halfSizes.append((max(cx - x1, x2 - cx), max(cy - y1, y2 - cy)))
    default = float(relationWeights.get("*", 0.5))
    links:dict[tuple[int, int], float] = {}
    def link(a:Any, b:Any, weight:float) -> None:
      i, j = index.get(id(a)), index.get(id(b))
      if i is not None and j is not None and i != j and weight > 0.0:
        links[(min(i, j), max(i, j))] = max(weight, links.get((min(i, j), max(i, j)), 0.0))
    for vo in self.objects:
      for rel in vo.relations:
        if not isinstance(rel, VRelation) or rel.modelObject is None or not rel._isConnected():
          continue
        weight = float(relationWeights.get(rel.modelObject.name, default))
        if rel.modelObject.isType() or id(rel) in index: # (a relation type, or a placed label, is a body itself: attached to it)
          link(vo, rel, weight)
        else: # (an individual relation: its ends attract one another)
          other = rel.dst if rel.src is vo else rel.src
          link(vo, other, weight)
      if isinstance(vo, VRelation): # (a relation type, or a placed label: attracted to its ends)
        weight = float(relationWeights.get(vo.modelObject.name, default))
        for end in (vo.src, vo.dst):
          link(vo, end, weight)
    lifted:dict[tuple[int, int], float] = {}
    for (i, j), w in links.items():
      pair = self.siblings(i, j)
      if pair is not None:
        key = (min(pair), max(pair))
        lifted[key] = max(w, lifted.get(key, 0.0))
    self.links:list[tuple[int, int, float]] = [(i, j, w) for (i, j), w in lifted.items()]
    '''
    (i, j, weight): pairs of objects (by index) attracted to one another: always
    in the same window (or both out on the canvas) -- see *siblings()*.
    '''
    self.directed:list[tuple[int, int]] = []
    "(src, dst): the objects (by index) at the ends of each relation of the flow relation type."
    if flowRelation is not None:
      seen:set[tuple[int, int]] = set()
      for rel in view.values():
        mo = rel.modelObject if isinstance(rel, VRelation) else None
        if mo is None or not mo.isIndividual() or not rel._isConnected():
          continue
        try:
          if not mo.isa(flowRelation):
            continue
        except Exception:
          continue
        i, j = index.get(id(rel.src)), index.get(id(rel.dst))
        pair = self.siblings(i, j) if i is not None and j is not None else None
        # (only out on the canvas: the current layers the canvas, not inside windows)
        if pair is not None and self.owners[pair[0]] is None and pair not in seen:
          seen.add(pair)
          self.directed.append(pair)
    self.ranks:dict[int, int] = rankOf(self.directed)
    "Each object in a directed relation (by index): its layer -- 0 for those with no dst (eg: root classes), then one more than its deepest dst's."

  @staticmethod
  def _placed(vo:VObject, homes:dict) -> bool:
    '''
    Whether *vo* is a relation's label that's laid out as a body in its context
    window (see *SNGView.containmentHomes()*): one the window contains whose
    place floating between its ends wouldn't say which pane it's in -- an end
    is elsewhere, eg: on the other side, or astride the divider (as in a rule
    saying a -r-> b gives b -r-> a) -- or one placed by hand (it doesn't float).

    :param vo: A view object.
    :type vo: VObject
    :param homes: Where contained objects belong (see *SNGView.containmentHomes()*).
    :type homes: dict
    :returns: True iff it's laid out in its pane.
    :rtype: bool
    '''
    if not isinstance(vo, VRelation) or vo not in homes or vo.modelObject is None or not vo.modelObject.isIndividual() \
       or not vo._isConnected() or vo.isHidden():
      return False
    if not vo.floating():
      return True
    return any(not isinstance(e, VObject) or homes.get(e) != homes[vo] for e in (vo.src, vo.dst))

  def siblings(self, i:int, j:int) -> tuple[int, int]|None:
    '''
    What a relation between objects *i* and *j* pulls together: they
    themselves if they're in the same window (or both out on the canvas);
    otherwise the windows they're in (or they themselves) that are side by
    side, in the innermost window that has them both (or out on the canvas).

    :param i: An object's index.
    :type i: int
    :param j: Another object's index.
    :type j: int
    :returns: The pair (by index), in the same order; None if one is (in) the other.
    :rtype: tuple[int, int] | None
    '''
    ci, cj = self.chains[i], self.chains[j]
    inJ = set(cj)
    common = next((a for a in ci if a in inJ), None)
    if common == i or common == j:
      return None
    if common is None:
      return ci[-1], cj[-1]
    return ci[ci.index(common) - 1], cj[cj.index(common) - 1]

def rankOf(directed:list[tuple[int, int]]) -> dict[int, int]:
  '''
  Layer the objects of *directed* (src, dst) relations: an object with no dst
  (eg: a root class, for isa) is rank 0; any other is one more than its
  highest-ranked dst. (Cycles are cut off after as many rounds as there are
  objects.)

  :param directed: (src, dst) pairs of object indices.
  :type directed: list[tuple[int, int]]
  :returns: Each object's rank.
  :rtype: dict[int, int]
  '''
  dsts:dict[int, list[int]] = {}
  for s, d in directed:
    dsts.setdefault(s, []).append(d)
    dsts.setdefault(d, [])
  rank = {i: 0 for i in dsts}
  for _ in range(len(dsts)):
    changed = False
    for s, ds in dsts.items():
      r = max((rank[d] + 1 for d in ds), default=0)
      if r > rank[s]:
        rank[s], changed = r, True
    if not changed:
      break
  return rank

def gap(snap:Snapshot, i:int, j:int) -> tuple[float, float, float]:
  '''
  How far apart objects *i* and *j* of *snap* are: the distance between their
  edges (0 if they overlap), and the unit vector from *j*'s centre to *i*'s
  (random if their centres coincide).

  :param snap: The graph.
  :type snap: Snapshot
  :param i: An object's index.
  :type i: int
  :param j: Another object's index.
  :type j: int
  :returns: (gap, ux, uy).
  :rtype: tuple[float, float, float]
  '''
  (xi, yi), (xj, yj) = snap.positions[i], snap.positions[j]
  dx, dy = xi - xj, yi - yj
  if dx == 0 and dy == 0: # (exactly on top of one another: some direction)
    dx, dy = random() - 0.5, random() - 0.5
  r = sqrt(dx * dx + dy * dy)
  (wi, hi), (wj, hj) = snap.halfSizes[i], snap.halfSizes[j]
  gx, gy = max(abs(dx) - (wi + wj), 0.0), max(abs(dy) - (hi + hj), 0.0)
  return sqrt(gx * gx + gy * gy), dx / r, dy / r

def misalignment(snap:Snapshot, flow:tuple[float, float]) -> float:
  '''
  :param snap: The graph.
  :type snap: Snapshot
  :param flow: The current's direction (a unit vector).
  :type flow: tuple[float, float]
  :returns: How far, in all, the relations in *snap.directed* are from pointing
    upstream (from src to dst): the sum of their angles off it, each from 0
    (in line) to 1 (backwards).
  :rtype: float
  '''
  tx, ty = -flow[0], -flow[1]
  total = 0.0
  for s, d in snap.directed:
    vx, vy = snap.positions[d][0] - snap.positions[s][0], snap.positions[d][1] - snap.positions[s][1]
    r = sqrt(vx * vx + vy * vy)
    if r > 0:
      total += acos(max(-1.0, min(1.0, (vx * tx + vy * ty) / r))) / pi
  return total

def forces(snap:Snapshot, e:float, gMaxDist:float, k:float, kMinDist:float, maxDisplacement:float,
           flow:tuple[float, float]|None=None, flowStrength:float=0.0, flowSpacing:float=40.0,
           heat:float=0.0, arranging:bool=False, layerGain:float=0.2, straighten:bool=False,
           pull:float=30.0) -> list[tuple[float, float]]:
  '''
  The displacement of each object in *snap* (in its order), with distances
  measured between the objects' edges (see *gap()*), so big objects -- context
  windows, long labels -- are as solid as they look:

  - repulsion between every two objects less than *gMaxDist* apart, of *e* /
    gap (like charged particles: as between centres for small objects), along
    the line between their centres -- overlapping objects push hardest;
  - attraction along links, stretched beyond *kMinDist* (like elastic bands),
    which pull until the objects' edges nearly touch;

  - with a *flow* direction, a current: the objects of *snap.directed*'s
    relations are layered along it by rank (see *rankOf()*) -- dsts upstream
    of their srcs, eg: for "isa" flowing down, superclasses above their
    subclasses: a class diagram -- each pulled (by up to *flowStrength*) to
    its layer, *flowSpacing* apart (between edges). The layers are centred on
    where those objects are, and what's left of any overall drift is taken
    out, so the current arranges things without carrying them away. (Across
    the current, repulsion and the relations' pull arrange them as usual.);

  each capped at *maxDisplacement* in x and in y.

  What's in a context window (see *Snapshot.owners*) is pushed and pulled only
  by what's in the same window, and kept in its pane (see *Snapshot.regions*):
  anything outside it floats in (by up to *pull*, or a quarter of the way, in a
  step), and nothing inside it is moved out. Its move is on top of its
  window's: it moves with the window, and within it.

  The canvas's top and left edges
  are kept by sliding the whole arrangement down or right exactly as needed, so
  no object's footprint -- its box and any text
  spilling out of it -- goes off them, without stopping objects there one by one.
  Plain arithmetic: safe in a thread.

  :param snap: The graph.
  :type snap: Snapshot
  :param e: The repulsive strength of objects for one another.
  :type e: float
  :param gMaxDist: The furthest apart (between edges) objects repel one another.
  :type gMaxDist: float
  :param k: The stiffness of the links.
  :type k: float
  :param kMinDist: The gap below which links don't pull.
  :type kMinDist: float
  :param maxDisplacement: The most an object moves (in x and in y) in one step.
  :type maxDisplacement: float
  :param flow: The current's direction, a unit vector (see *FLOW_DIRECTIONS*); None for none.
  :type flow: tuple[float, float]|None
  :param flowStrength: The most the current pushes an object in a step.
  :type flowStrength: float
  :param flowSpacing: The gap (between edges, along the current) it puts between a relation's dst and src.
  :type flowSpacing: float
  :param heat: The most each object is jiggled at random (in x and in y) in a step: lets the layout out of
    dead ends (eg: a tree pointing straight against the current), as in simulated annealing.
  :type heat: float
  :param arranging: While the current is first arranging things: objects it layers repel one another only
    across it, so they can slide past one another to their layers (eg: a tree turning around). (Objects in the
    same layer always repel one another only across it: they're on one line.)
  :type arranging: bool
  :param layerGain: The fraction of the way to its layer the current pulls an object in a step (up to *flowStrength*).
  :type layerGain: float
  :param straighten: Put the objects the current layers onto their layers' lines: along the current, they move
    only toward their layers (other forces act on them only across it).
  :type straighten: bool
  :param pull: The least a contained object outside its pane is moved toward it in a step (when it's further).
  :type pull: float
  :returns: (dx, dy) for each object: how far it moves on the canvas (with its window's move).
  :rtype: list[tuple[float, float]]
  '''
  n = len(snap.positions)
  fx, fy = [0.0] * n, [0.0] * n
  across = flow is not None and arranging # (ranked objects repel only across the current: see *arranging*)
  owners = snap.owners
  for i in range(n): # repulsion (only between objects in the same window, or both out on the canvas)
    for j in range(i + 1, n):
      if owners[i] != owners[j]:
        continue
      g, ux, uy = gap(snap, i, j)
      if g > gMaxDist:
        continue
      f = e / max(g, 1.0) # (overlapping: the strongest push)
      px, py = ux * f, uy * f
      # (only across the current: between objects it layers, while it's arranging
      # them; and between objects in the same layer, always -- they're on one line)
      if flow is not None and i in snap.ranks and j in snap.ranks and (across or snap.ranks[i] == snap.ranks[j]):
        a = px * flow[0] + py * flow[1]
        px, py = px - a * flow[0], py - a * flow[1]
      fx[i] += px; fy[i] += py
      fx[j] -= px; fy[j] -= py
  for i, j, w in snap.links: # attraction
    g, ux, uy = gap(snap, i, j)
    if g <= kMinDist:
      continue
    f = g * (g - kMinDist) * k * w
    fx[i] -= ux * f; fy[i] -= uy * f
    fx[j] += ux * f; fy[j] += uy * f
  if flow is not None and flowStrength > 0 and snap.ranks: # the current: layers along it
    ux, uy = flow
    ranked = list(snap.ranks)
    along = lambda i: snap.halfSizes[i][0] * abs(ux) + snap.halfSizes[i][1] * abs(uy) # (half its extent along the current)
    sizes = sorted(along(i) for i in ranked)
    layer = flowSpacing + 2 * sizes[len(sizes) // 2] # (the distance between layers: by a typical size -- repulsion keeps big ones clear)
    proj = {i: snap.positions[i][0] * ux + snap.positions[i][1] * uy for i in ranked} # (how far downstream each is)
    meanProj = sum(proj.values()) / len(ranked)
    meanRank = sum(snap.ranks[i] for i in ranked) / len(ranked)
    for i in ranked: # (each pulled to its layer, the layers centred where the ranked objects are)
      off = meanProj + (snap.ranks[i] - meanRank) * layer - proj[i]
      f = max(-flowStrength, min(flowStrength, off * layerGain))
      if straighten: # (along the current: only toward its layer's line)
        a = fx[i] * ux + fy[i] * uy
        fx[i] -= a * ux; fy[i] -= a * uy
      fx[i] += ux * f; fy[i] += uy * f
  if heat > 0: # (random jiggling)
    for i in range(n):
      fx[i] += (random() * 2 - 1) * heat
      fy[i] += (random() * 2 - 1) * heat
  cap = lambda v: max(-maxDisplacement, min(maxDisplacement, v))
  capped = [(cap(fx[i]), cap(fy[i])) for i in range(n)]
  if not n:
    return []
  top = [i for i in range(n) if owners[i] is None] # (out on the canvas: the rest move with their windows)
  if ((flow is not None and flowStrength > 0) or heat > 0) and top: # (no overall drift: take out the average movement)
    mx, my = sum(capped[i][0] for i in top) / len(top), sum(capped[i][1] for i in top) / len(top)
    for i in top:
      capped[i] = (capped[i][0] - mx, capped[i][1] - my)
  for i in range(n): # (what's in a window: in its pane -- in its window's frame, as its window moves it too)
    region = snap.regions[i]
    if region is None:
      continue
    d = list(capped[i])
    for k in (0, 1):
      p, h = snap.positions[i][k], snap.halfSizes[i][k]
      lo, hi = region[k] + h, region[k + 2] - h # (where its centre may be)
      if lo > hi: # (too big for the pane: centred in it)
        lo = hi = (lo + hi) / 2
      if p < lo or p > hi: # (outside: floats in)
        dist = (lo if p < lo else hi) - p
        step = min(abs(dist), max(pull, abs(dist) * 0.25))
        d[k] = step if dist > 0 else -step
      else: # (inside: stays in)
        d[k] = max(lo, min(hi, p + d[k])) - p
    capped[i] = (d[0], d[1])
  # Keep everything on the canvas (x, y >= 0) by sliding the whole arrangement,
  # not by stopping objects at the edge one by one -- that would block them
  # (eg: a tree turning around) and skew the layout.
  over = lambda k: min(snap.positions[i][k] + capped[i][k] - snap.halfSizes[i][k] for i in top) # (the furthest footprint edge, after the step)
  sx, sy = (max(0.0, -over(0)), max(0.0, -over(1))) if top else (0.0, 0.0) # (exactly enough: never short, or objects would hit the edge one by one)
  for i in top:
    capped[i] = (capped[i][0] + sx, capped[i][1] + sy)
  ret:list[tuple[float, float]] = list(capped)
  for i in sorted(range(n), key=lambda i: len(snap.chains[i])): # (windows before what's in them: each moves with its window)
    o = owners[i]
    if o is not None:
      ret[i] = (capped[i][0] + ret[o][0], capped[i][1] + ret[o][1])
  return ret

class FieldsLayout():
  '''
  The animation layout -- a "physics" layout: objects repel one another like similarly charged
  particles, and relations pull what they connect together like elastic bands
  -- run as an animation, step by step, until nothing moves much (or it's
  stopped). Context windows move as wholes, carrying their contents, which
  are laid out inside them, each in its pane (see *Snapshot*).

  Each step's forces are calculated from a *Snapshot* of the graph (see
  *forces()*); here, on the GUI thread, a step at a time between Tk events (see
  *FieldsLayout_threaded* for doing it in a thread). The whole run is one
  undoable command.

  Use:

    .. code-block:: python

        f = FieldsLayout(view, ...)
        f()        # start (or keep going)
        f.kill()   # stop
  '''
  def __init__(self, view:SNView,
               e:float=1000.0, gMaxDist:float=200.0,
               k:float=0.005,  kMinDist:float=0.0,
               displacementSensitivity=5.0, maxDisplacement=10.0,
               dtime=100):
    '''
    :param view: The view to lay out.
    :type view: SNView
    :param e: The "gravitational constant": the repulsive strength of objects for one another.
    :type e: float
    :param gMaxDist: The furthest apart (view units) objects repel one another.
    :type gMaxDist: float
    :param k: The "spring constant" (stiffness) of relations.
    :type k: float
    :param kMinDist: The distance below which relations don't pull.
    :type kMinDist: float
    :param displacementSensitivity: An object moves only if it'd move at least this much (abs(dx) + abs(dy)); when none would, it's converged.
    :type displacementSensitivity: float
    :param maxDisplacement: The most an object moves (in x and in y) in one step: prevents wild jumps.
    :type maxDisplacement: float
    :param dtime: The time (ms) between steps.
    :type dtime: int
    '''
    self.e:float = float(e)
    'The "gravitational constant": repulsive strength of objects for one another.'
    self.gMaxDist:float = float(gMaxDist)
    'The furthest apart that *e* takes effect.'
    self.k:float = float(k)
    'The "spring constant" (spring stiffness): the attractive force of a relation.'
    self.kMinDist:float = float(kMinDist)
    'The minimum distance that *k* takes effect.'
    self.displacementSensitivity:float = float(displacementSensitivity)
    'An object moves only if it would move at least this much: the higher, the sooner the animation stops.'
    self.maxDisplacement:float = float(maxDisplacement)
    'The maximum x- or y-direction displacement in any one step. Prevents wild displacements.'
    self.dtime:int = int(dtime)
    'The time (ms) between steps.'
    self.relationWeights:dict[str, float] = {"*": 0.5}
    self.flowDirection:str|None = None
    'The direction of the current (a key of *FLOW_DIRECTIONS*, eg: "down"), or None for none (see *forces()*).'
    self.flowStrength:float = 6.0
    'The most the current pushes an object in a step.'
    self.flowSpacing:float = 40.0
    'The gap (between edges, along the current) it puts between a relation\'s dst and src.'
    self.layerGain:float = 0.2
    'While the current arranges things: the fraction of the way to its layer an object is pulled in a step.'
    self.settleLayerGain:float = 0.5
    'Once arranged, while settling: the same, stiffer -- to straighten the layers.'
    self.heat:float = 6.0
    '''
    While the current flows: the most each object is jiggled at random in a step
    (scaled by *temperature*, so it fades as the layout cools) -- to shake the
    layout out of dead ends, eg: a tree pointing straight against the current.
    '''
    self.flowRelation:Any = None
    'The relation type the current lines up (its dst upstream of its src); None for "isa".'
    self.patience:int = 8
    'Steps without real progress (see *progress*) before cooling down (see *temperature*).'
    self.progress:float = 0.95
    'Progress means the total movement in a step falling below this fraction of the best so far.'
    self.cooling:float = 0.7
    'What *temperature* is multiplied by when there\'s no progress.'
    self.temperature:float = 1.0
    '''
    Scales how far an object may move in a step (*maxDisplacement*). It starts
    at 1, and cools when the layout stops making progress -- eg: jiggling back
    and forth about a balance point -- so the jiggles shrink, until they're too
    small to count (see *displacementSensitivity*) and the run ends.
    '''
    self._best:float = float("inf")
    self._stalled:int = 0
    self._misalignment:float|None = None
    self._bestMisalignment:float = float("inf")
    self._arranged:bool = False
    self._straightening:int = 0
    self._straightened:bool = False
    self.straightenSteps:int = 40
    '''
    With a current: once the layout has settled, at most this many more steps put
    the layered objects onto their layers' lines (see *forces()*'s *straighten*)
    -- the physics's arrangement across the current stays.
    '''
    self.alignPatience:int = 20
    'While a current flows: steps without the relations coming further into line before it stops arranging and settles (see *_cool()*).'
    self.alignProgress:float = 0.05
    'While a current flows: how much the total misalignment must fall to count as coming further into line.'
    self.placeLabels:bool = True
    '''
    Whether a run ends by finding free places for the floating relation labels
    (see *_settleLabels()*). That can take a while in a crowded view; turned
    off, eg: while starting run after run, the labels just stay between their
    ends (see *settleLabels()* to place them later).
    '''
    self._killFlag = False
    self.active = False
    'Indicates the animation is running.'
    self._start:dict[int, tuple[VObject, list[int]]] = {} # id(vo) -> (vo, its bounding box when the run started): for the undo
    self._wasFloating:dict[int, bool] = {} # id(label) -> whether it floated when the run started, for the labels it pinned: for the undo
    self._pins:set[int] = set() # id(label) of the floating labels this step places (see Snapshot.pinned)
    self._view = weakref.ref(view)

  @property
  def view(self) -> SNView:
    '''
    :returns: The view laid out.
    :rtype: SNView
    :raises WeakrefError: If the view has gone.
    '''
    ret = self._view()
    if ret is None:
      raise WeakrefError()
    return ret

  def __call__(self, obj:Optional[VObject]=None, autoOff:bool=True):
    '''
    Start the animation (or, if it's running, carry on).

    :param obj: Ignored (kept for compatibility: the whole view is laid out).
    :type obj: Optional[VObject]
    :param autoOff: If True, stop when nothing moves much any more; else, run until *kill()*.
    :type autoOff: bool
    '''
    if self.active:
      return
    self._killFlag = False
    self._start, self._wasFloating = {}, {}
    self.temperature, self._best, self._stalled = 1.0, float("inf"), 0
    self._misalignment, self._bestMisalignment, self._arranged = None, float("inf"), False
    self._straightening, self._straightened = 0, False
    self.active = True
    logger.info("FieldsLayout animation on")
    self._call(autoOff)

  def kill(self, obj:Optional[VObject]=None):
    '''
    Stop the animation (after the current step).

    :param obj: Ignored.
    :type obj: Optional[VObject]
    '''
    self._killFlag = True

  def setRelationWeight(self, relationName:str, weight:float=0.5):
    '''
    Give the named relation a weight between 0.0 and 1.0. You can use "*" to
    assign a default weight. Thus, setRelationWeight('*', 0.0) and
    setRelationWeight('isa', 1.0) will only make use of isa relations.

    :param relationName: A relation type's name, or "*" for all the others.
    :type relationName: str
    :param weight: Its weight (clipped to 0..1): how strongly it pulls.
    :type weight: float
    '''
    self.relationWeights[relationName] = max(0.0, min(1.0, float(weight)))

  def _snapshot(self) -> Snapshot:
    '''
    :returns: A snapshot of the view now (on the GUI thread).
    :rtype: Snapshot
    '''
    flowing = self.flowDirection in FLOW_DIRECTIONS
    relation = (self.flowRelation or self.view.model.ISA) if flowing else None
    return Snapshot(self.view, self.relationWeights, relation)

  def _forces(self, snap:Snapshot) -> list[tuple[VObject, tuple[float, float]]]:
    '''
    :param snap: The graph.
    :type snap: Snapshot
    :returns: (object, (dx, dy)) for the objects that should move this step.
    :rtype: list[tuple[VObject, tuple[float, float]]]
    '''
    flow = FLOW_DIRECTIONS.get(self.flowDirection or "")
    # (how far, in all, the current's relations are from in line: see _cool(); None while there's no current)
    self._misalignment = misalignment(snap, flow) if flow is not None else None
    # (once arranged, while settling, the layers are straightened: the pull to them
    # stiffens, and doesn't fade as it cools -- the cooling step limit still ends the run)
    settling = flow is not None and self._arranged
    straighten = flow is not None and self._straightening > 0
    moves = forces(snap, self.e, self.gMaxDist, self.k, self.kMinDist,
                   self.maxDisplacement * (1.0 if straighten else self.temperature),
                   flow=flow, flowStrength=self.maxDisplacement if straighten else self.flowStrength * (1.0 if settling else self.temperature),
                   layerGain=self.settleLayerGain if settling else self.layerGain, straighten=straighten,
                   flowSpacing=self.flowSpacing, heat=(self.heat * self.temperature) if flow is not None and not straighten else 0.0,
                   arranging=flow is not None and not self._arranged)
    self._pins = {id(snap.objects[i]) for i in snap.pinned}
    # (an object moves if it moves enough -- or if its window does: it mustn't be left behind)
    moving:set[int] = set()
    ret:list[tuple[VObject, tuple[float, float]]] = []
    for i in sorted(range(len(moves)), key=lambda i: len(snap.chains[i])):
      dx, dy = moves[i]
      if abs(dx) + abs(dy) > self.displacementSensitivity or (snap.owners[i] in moving and (dx or dy)):
        moving.add(i)
        ret.append((snap.objects[i], (dx, dy)))
        ret += [(vo, (dx, dy)) for vo in snap.passengers.get(i, ())]
    return ret

  def _call(self, autoOff:bool):
    '''
    Do one step: snapshot, forces, moves (here, all on the GUI thread).

    :param autoOff: As for *__call__()*.
    :type autoOff: bool
    '''
    try:
      changes = self._forces(self._snapshot())
    except WeakrefError: # (the view has gone)
      return
    except Exception:
      logger.exception("Exception during FieldsLayout processing.")
      changes = []
    self._commitChanges(changes, autoOff)

  def _commitChanges(self, changes:list[tuple[VObject, tuple[float, float]]], autoOff:bool):
    '''
    Make a step's moves (on the GUI thread), and queue the next step -- or end
    the run, recording it as one undoable command.

    :param changes: (object, (dx, dy)) to move.
    :type changes: list[tuple[VObject, tuple[float, float]]]
    :param autoOff: As for *__call__()*.
    :type autoOff: bool
    '''
    try:
      view = self.view
    except WeakrefError:
      return
    if view.suppressLocalLayout(): # (something's being dragged: don't fight the user -- try again later)
      changes = []
      moved = True
    else:
      for vo, (dx, dy) in changes:
        if vo._isConnected():
          self._start.setdefault(id(vo), (vo, list(vo.boundingBox())))
          if id(vo) in self._pins: # (a floating label placed in its pane: pinned there -- see Snapshot._placed())
            self._wasFloating.setdefault(id(vo), vo.floating())
            vo._floatingAnchor = False
          vo.moveBy(dx, dy, adjustPos=False, carry=False) # (a window's contents have moves of their own)
      moved = len(changes) > 0
      self._cool(sum(abs(dx) + abs(dy) for _, (dx, dy) in changes))
      # (settled, with a current: straighten its layers before stopping -- see *straightenSteps*)
      if self.flowDirection in FLOW_DIRECTIONS and not self._killFlag and (not moved or self.temperature < 0.1):
        if self._straightening == 0 and not self._straightened:
          self._straightening, self._straightened, moved = self.straightenSteps, True, True
        elif self._straightening > 0:
          self._straightening -= 1
          moved = self._straightening > 0 and moved
    if (moved or not autoOff) and not self._killFlag:
      view.canvas.winfo_toplevel().after(self.dtime, lambda: self._call(autoOff))
    else:
      self._finish()

  def settleLabels(self) -> None:
    '''
    Find free places for the floating relation labels now (see
    *_settleLabels()*), as the end of a run does if *placeLabels* is on: eg:
    when it's turned on after runs without it. Not while a run is going: the
    end of the run does it.
    '''
    if self.active:
      return
    try:
      view = self.view
    except WeakrefError:
      return
    self._settleLabels(view)

  def _settleLabels(self, view:SNView) -> None:
    '''
    What a move does when it's dropped, for every floating relation label: put
    it back between its ends, and if it lands on something, find it a free place
    nearby (see *VRelation.reposition()*: the local layout). During the run the
    labels just follow their ends -- relations aren't bodies in the layout --
    so they can end up on top of objects (eg: a node in a layer between the
    relation's ends). Labels placed by hand (not floating) stay put, as they
    do after an ordinary move.

    :param view: The view laid out.
    :type view: SNView
    '''
    for vo in list(view.values()):
      if isinstance(vo, VRelation) and vo._isConnected() and not vo.isHidden() and vo.modelObject is not None \
         and vo.modelObject.isIndividual() and vo.floating():
        try:
          vo.reposition(adjustPos=True)
        except Exception:
          logger.exception(f"FieldsLayout: couldn't settle the label of {vo.name}")

  def _cool(self, energy:float):
    '''
    Note a step's total movement, *energy*: if it hasn't fallen meaningfully
    (see *progress*) for *patience* steps, the layout isn't converging -- it's
    jiggling about a balance point -- so cool down (see *temperature*).

    While a current flows (see *flowDirection*), there's first an arranging
    phase, with no cooling at all, as long as the current's relations keep
    coming into line (their *misalignment()* falls by at least
    *alignProgress* within *alignPatience* steps): turning a tree around takes
    a while, and starts slowly. Then it settles, as above.

    :param energy: The total of how far everything moved in the step.
    :type energy: float
    '''
    if self._misalignment is None: # (no current this step: progress afresh if one starts)
      self._bestMisalignment = float("inf")
    elif not self._arranged:
      if self._misalignment < self._bestMisalignment - self.alignProgress:
        self._bestMisalignment, self._stalled = self._misalignment, 0
      else:
        self._stalled += 1
        if self._stalled >= self.alignPatience:
          self._arranged, self._stalled = True, 0
          logger.debug(f"FieldsLayout: arranged (misalignment {self._misalignment:.2f}); settling")
      return
    if energy < self._best * self.progress:
      self._best, self._stalled = energy, 0
      return
    self._stalled += 1
    if self._stalled >= self.patience:
      self.temperature *= self.cooling
      self._best, self._stalled = energy, 0 # (progress from here on is measured afresh)
      logger.debug(f"FieldsLayout: not converging; cooling to {self.temperature:.3f}")

  def _finish(self):
    '''
    End the run: let the floating relation labels find free places (see
    *_settleLabels()*), and record all its moves as one undoable command.
    '''
    self.active = False
    logger.info("FieldsLayout animation off")
    start, self._start = self._start, {}
    wasFloating, self._wasFloating = self._wasFloating, {}
    try:
      view = self.view
    except WeakrefError:
      return
    if self.placeLabels:
      self._settleLabels(view)
    moved = [(vo, bb) for vo, bb in start.values() if vo._isConnected() and list(vo.boundingBox()) != bb]
    if moved:
      from util.commandParser import CompositeCommandMgr
      with CompositeCommandMgr(view.context):
        for vo, bb in moved:
          now = vo.boundingBox()
          view.context.move(vo, now[0], now[1], _oldPos=bb, adjustPos=False, _carry=False, _wasFloating=wasFloating.get(id(vo)))

class FieldsLayout_threaded(FieldsLayout):
  '''
  A *FieldsLayout* whose forces are calculated in a thread, so the GUI stays
  responsive with large graphs: each step's *Snapshot* is taken, and its moves
  made, on the GUI thread; only the arithmetic (*forces()*) is done in the
  thread -- which touches no GUI objects (Tk isn't thread-safe).
  '''
  POLL_MS = 15
  "How often (ms) the GUI thread checks whether the thread's step is done."

  @override
  def _call(self, autoOff:bool):
    '''
    Take a snapshot, and calculate its forces in a thread. The thread makes no
    Tk calls at all -- it just leaves its result -- and the GUI thread picks it
    up (see *_poll()*): the safe way with Tk, whatever thread Tk's event loop
    runs in.

    :param autoOff: As for *FieldsLayout.__call__()*.
    :type autoOff: bool
    '''
    try:
      snap = self._snapshot()
      top = self.view.canvas.winfo_toplevel()
    except WeakrefError:
      return
    result:queue.SimpleQueue = queue.SimpleQueue()
    def work():
      try:
        result.put((self._forces(snap), None))
      except Exception:
        result.put(([], format_exc()))
    Thread(target=work, daemon=True).start()
    top.after(self.POLL_MS, lambda: self._poll(result, autoOff))

  def _poll(self, result:queue.SimpleQueue, autoOff:bool):
    '''
    On the GUI thread: if the thread's step is done, make its moves (see
    *_commitChanges()*); otherwise check again shortly.

    :param result: Where the thread leaves (changes, error).
    :type result: queue.SimpleQueue
    :param autoOff: As for *FieldsLayout.__call__()*.
    :type autoOff: bool
    '''
    try:
      changes, error = result.get_nowait()
    except queue.Empty:
      try:
        self.view.canvas.winfo_toplevel().after(self.POLL_MS, lambda: self._poll(result, autoOff))
      except WeakrefError:
        pass
      return
    if error:
      logger.error(f"Exception during FieldsLayout processing: {error}")
    self._commitChanges(changes, autoOff)

try: # (the "bones" engine, for FieldsLayout_threadPool only -- from the older tygra projects; not installed here)
  from fieldLayout import UpdateRec, Graph, Point, ID, Op, BNode, \
      OP_NEW_NODE, OP_NEW_REL, OP_DEL_NODE, OP_DEL_REL, OP_MOD_POS, OP_MOD_WEIGHT, \
      FIELD_LAYOUT_PARAMS
except ImportError:
  pass
    
  
# class BonesGraph:
#
#   def __init__(self, relationWeights:dict[str,float]={"*":0.5}):
#     self.nodes:dict[id, BNode] = dict()
#     self.relationWeights:dict[str, float] = relationWeights
#     self.defaultWeight = self.relationWeights["*"] if "*" in self.relationWeights else 0.5
    
def makeBonesGraph(view:SNView, defaultWeight:float=0.5, relationWeights:dict[str,float]=dict()):
  
  '''
  :param view:
  :type view: SNView
  :param defaultWeight:
  :type defaultWeight: float
  :param relationWeights:
  :type relationWeights: dict[str, float]
  :returns:
  :rtype:
  '''
  nodes:dict[id, BNode] = dict()
  
  def addNode(vnode:VObject) -> ID:
    if not isEligible(vnode):
      return None
    id_ = vnode._id
    if id_ in nodes:
      return id_
    bnode = BNode(id_, vnode.centerPt())
    nodes[id_] = bnode
    # scan the relations
    for rel in vnode.relations:
      weight = relationWeights.get(rel.modelObject.name, defaultWeight)
      if weight <= 0.0:
        continue
      try:
        if rel.modelObject.isType():
          other:VObject = rel
        else:
          other:VObject = rel.roles["src"][0].vobject()
          if vnode is other:
            other = rel.roles["dst"][0].vobject()
          if vnode is other: #self-reference, ignore it
            continue 
        if other.modelObject.isIndividual() and isinstance(other,VRelation):
          continue # ignore relations to relation instances as they float, so we can't know where they go
      except:
        logger.warning(f"BonesGraph.addNode(): couldn't get other end of relations for object {vnode.modelObject.name}")
        continue
      o = addNode(other)
      if o is not None:
        bnode.rels.append((o, weight))
    # scan the roles (if this is a relation)
    if isinstance(vnode, VRelation) and (weight := relationWeights.get(vnode.modelObject.name, defaultWeight) > 0.0):
      for other in [x[0].vobject() for x in vnode.roles.values()]:
        if other is None: continue
        o = addNode(other)
        if o is not None:
          bnode.rels.append((o, weight))
    return id_ 
  
  for obj in view._objects.values():
    addNode(obj)
  
  return nodes
    
    
  

class FieldsLayout_threadPool(FieldsLayout):
  
  def __init__(self, view:SNView, 
               e:float=1000.0, gMaxDist:float=200.0, 
               k:float=0.005,  kMinDist:float=0.0, 
               displacementSensitivity=5.0, maxDisplacement=10.0, 
               dtime=100,
               autoOff=False):
    '''
    :param view:
    :type view: SNView
    :param e:
    :type e: float
    :param gMaxDist:
    :type gMaxDist: float
    :param k:
    :type k: float
    :param kMinDist:
    :type kMinDist: float
    :param displacementSensitivity:
    :type displacementSensitivity:
    :param maxDisplacement:
    :type maxDisplacement:
    :param dtime:
    :type dtime:
    :param autoOff:
    :type autoOff:
    '''
    assert isinstance(view, SNView)
    self.e:float        = float(e)
    'The "gravitational constant": repulsive strength of nodes (and relation types) to one another' 
    self.gMaxDist:float = float(gMaxDist)
    'The maximum 2d distance that e takes effect.'
    self.k:float        = float(k) 
    'The "spring constant" (spring stiffness): The attractive force of a relation'
    self.kMinDist:float = float(kMinDist)
    'The minimum 2d distance that *k* takes effect.'
    self.displacementSensitivity:float = float(displacementSensitivity)
    'The higher the number, the faster the algorithm comes to convergence'
    self.maxDisplacement:float = float(maxDisplacement)
    'The maximum x- or y-direction displacement that can happen in any once cycle. Prevents wild displacements.'
    self.dtime:int      = int(dtime)
    'The time (in ms) that the algorithm "rests" between activation.'
    self.dtime2:int     = int(dtime*4)
    'The max time (approximate) that the algorithm with run for before giving up control back to *mainloop*.'
    self.autoOff:bool   = autoOff
    'Iff true, the automation should be turned off when the layout converges.'
    
    self.active = False
    self._view = weakref.ref(view)
    self._killFlag = False # the global killflag
    #self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fields", initializer=fieldLayout.init)
    self.pool = ProcessPoolExecutor(max_workers=1, initializer=fieldLayout.init)
    print("ProcessPoolExecutor initialized")
    self.waiting:bool = False # used in self._resubmit to handle a suppressLocalLayout state

  @override
  def __call__(self, obj:Optional[VObject]=None, autoOff:bool=True):
    '''
    :param obj:
    :type obj: Optional[VObject]
    :param autoOff:
    :type autoOff: bool
    '''
    if obj is not None: #TODO fix this temporary patch
      return
    self.active = True
    self.waiting = False
    graph = makeBonesGraph(self.view)
    print(f"Animation on ({len(graph)})")
    self.job = self.pool.submit(fieldLayout.call, "newFrame", 
                                graph=graph, 
                                obj=obj._id if obj is not None else None)
    self.job.add_done_callback(lambda future: self.view.after(self._updateFromBones, future))

  def newNode(self, id:ID, pos:Point):
    '''
    :param id:
    :type id: ID
    :param pos:
    :type pos: Point
    '''
    self.pool.submit(fieldLayout.worker.newNode, id=id, pos=pos)
                                       
  def newRel(self, id1:ID, id2:ID, weight:float):
    '''
    :param id1:
    :type id1: ID
    :param id2:
    :type id2: ID
    :param weight:
    :type weight: float
    '''
    self.pool.submit(fieldLayout.worker.newRel, id1=id1, id2=id2, weight=weight)
                                       
  def delNode(self, id:ID):
    '''
    :param id:
    :type id: ID
    '''
    self.pool.submit(fieldLayout.worker.delNode, id=id)
                                       
  def delRel(self, id1:ID, id2:ID):
    '''
    :param id1:
    :type id1: ID
    :param id2:
    :type id2: ID
    '''
    self.pool.submit(fieldLayout.worker.delRel, id1=id1, id2=id2)
                                       
  def updatePos(self, id:ID, pos:Point):
    '''
    :param id:
    :type id: ID
    :param pos:
    :type pos: Point
    '''
    self.pool.submit(fieldLayout.worker.updatePos, id=id, pos=pos)
                                       
  def updateWeight(self, id1:ID, id2:ID, weight:float):
    '''
    :param id1:
    :type id1: ID
    :param id2:
    :type id2: ID
    :param weight:
    :type weight: float
    '''
    self.pool.submit(fieldLayout.worker.updateWeight, id1=id1, id2=id2, weight=weight)
    
  def updateSettings(self, **kwargs) -> Future: # A future object
    '''
    :param kwargs:
    :type kwargs:
    :return: A *future* object that can safely be ignored, but refers to remote
      worker's parameters table if *kwargs* is empty.
    :rtype: Future
    '''
    print("FieldsLayout_threadPool.updateSettings()")
    if len(kwargs) == 0:
      job = self.pool.submit(fieldLayout.worker.updateSettings)
      return job # a future object
    for k,v in kwargs.items():
      assert k in FIELD_LAYOUT_PARAMS
    print(f'updating settings {str(kwargs)}')
    try:
      job = self.pool.submit(fieldLayout.worker.updateSettings, **kwargs)
      print("done submit")
    except:
      logger.exception("FieldsLayout_threadPool.updateSettings():")
    return job
    
                                       
  def _updateFromBones(self, future:Future)->bool:
    '''
    This is the callback from the *ThreadPoolExecutor* after the layout job has
    completed. Schedule the result into *tkinter's* mainloop (*self._drawFromBones()*).
    
    Calls *self._drawFromBones()* (ono the mainloop).

    :param future:
    :type future: Future
    :returns:
    :rtype: bool
    '''
    try:
      bones = future.result(timeout=2)
      self.view.canvas.winfo_toplevel().after(100, lambda bones=bones: self._drawFromBones(bones))
    except:
      logger.exception("Animation raised an exception.")
    
  def _drawFromBones(self, bones:dict[ID, Point]):
    '''
    Move the *VObjects* in the view from the data in the *dict[ID, Point]*. This 
    needs to be executed in tk's mainloop.
     
    Calls *self._resubmit()* if necessary.

    :param bones:
    :type bones: dict[ID, Point]
    '''
    print(f"drawing from bones ({len(bones)})")
    for k,v in bones.items():
      self.view[k].moveTo(v[0], v[1], adjustPos=False)
    # if we're an ongoing animation resubmit
    if (len(bones)>0 or not self.autoOff) and not self._killFlag:
      self._resubmit()
    else:
      self.active = False
      self._killFlag = False
      print("Animation off")
    
  def _resubmit(self):
    '''
    Checks waiting state and calls itself on the mainloop (delayed) if we're waiting.
    Otherwise submits to the worker in other interpreter with a callback to 
    *self.updateFromBones()*.
    '''
    if self.waiting: # we are waiting for suppressLayout to clear
      if self.view.suppressLocalLayout(): # ...and we're still waiting
        print("waiting...")
        self.view.canvas.winfo_toplevel().after(500, self._resubmit)
      else: # we were waiting, but the suppresslayout has cleared: need to reset the graph
        print("waiting off")
        self.waiting = False
        self()
    elif self.view.suppressLocalLayout():
      print("start waiting")
      self.waiting = True
      self.view.canvas.winfo_toplevel().after(500, self._resubmit)
    else:
      print("submitting")
      self.job = self.pool.submit(fieldLayout.call, "newFrame")
      #self.job.add_done_callback(self._updateFromBones)
      self.job.add_done_callback(lambda future: self.view.after(self._updateFromBones, future))
  
# def testBones(view:SNView):
#   bg = BonesGraph()
#   # i = 0
#   # for obj in view._objects.values():
#   #   if bg.addNode(obj) is not None:
#   #     i += 1
#   #   if i>10: break
#   bg.setView(view)
#   for k,v in bg.nodes.items():
#     print('{:5d}: {!s:s}'.format(k, v))
    
    