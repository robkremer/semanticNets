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
'''
  .. inheritance-diagram::
        Direction
        FindFree
        LayoutHieristic
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Feb 15, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

---------------
'''

import sn
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, override, Iterable
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from util.utils import Point, expandRect
from sn.model.model import GraphObject, Node
from util.utils import removeDuplicates

logger:sn.SNLogger = sn.getLogger(__name__)

LABEL_PLACEMENT_PREF = "gui/optimization/aggressiveLabelPlacement"
"The preference for how hard *FindFree* looks for a free spot for a relation's label: see *labelPlacementLevel()*."

LABEL_PLACEMENT_DEFAULT = sn.PREFS[LABEL_PLACEMENT_PREF][1]

def labelPlacementLevel() -> int:
  '''
  :returns: The *LABEL_PLACEMENT_PREF* preference, from 0 to 10: how far
    *FindFree* looks for a free spot for a relation's label. 0: it doesn't (the
    label stays where it's made, midway between the relation's ends); else up
    to *level* squared rings out from there (10: 100, as for nodes). The time
    taken grows with the square of that, so a lot in a crowded view, as when
    showing a big model.
  :rtype: int
  '''
  level = sn.snPrefs.get(LABEL_PLACEMENT_PREF, storeDefault=LABEL_PLACEMENT_DEFAULT, storeType=int) # (its note: see sn.PREFS)
  if not isinstance(level, (int, float, str)):
    return LABEL_PLACEMENT_DEFAULT
  try:
    return min(10, max(0, int(level)))
  except ValueError:
    return LABEL_PLACEMENT_DEFAULT

class Direction(Enum):
  UNSPECIFIED = 0
  SUB = 1
  SUPER = 2
  LATERAL = 3
  NEAREST = 4
  
def depth(obj:GraphObject) -> int:
  '''
  :param obj:
  :type obj: GraphObject
  :return: the isa-depth of *obj*.
  :rtype: int
  '''
  i:int = -1
  p = [obj]
  while len(p) > 0:
    q = []
    for pp in p:
      q += list(p[0].getParents())
    p = removeDuplicates(q)
    i += 1
  return i
  
  
class LayoutHieristic(ABC):
  '''
  classdocs
  '''


  def __init__(self, view):
    '''
    Constructor

    :param view:
    :type view:
    '''
    from sn.view.graphics.sngView import SNGView
    assert isinstance(view, SNGView)
    self.view = view
    
  def _setDirection(self, node:VObject, referenceNode:Optional[VObject], loc:Optional[Point]=None):
    '''
    :param node:
    :type node: VObject
    :param referenceNode:
    :type referenceNode: Optional[VObject]
    :param loc:
    :type loc: Optional[Point]
    :returns:
    :rtype:
    '''
    if loc is not None:
      return Direction.NEAREST
    if referenceNode is None: # and loc is None
      return Direction.LATERAL
    else: #referenceNode is not None and loc is None
      if node.modelObject.isa(referenceNode.modelObject):
        return Direction.SUB
      elif referenceNode:
        return Direction.SUPER
    
  def findOverlapping(self, rect:list[int], exclude:list[int]=[]) -> list[int]:
    '''
    :param rect:
    :type rect: list[int]
    :param exclude:
    :type exclude: list[int]
    :return: The (possible zero-length) list of 'vis/shape'-tagged tk.Canvas object ids
        that overlap with bounding box of *node*.
    :rtype: list[int]
    '''
    overlapping = self.view.intersectTag(self.view.canvas.find_overlapping(*rect), 'vis/shape', exclude)
    return overlapping
    
  def __call__(self, node:Optional[VObject]=None, **kwargs):
    '''
    :param node:
    :type node: Optional[VObject]
    :param kwargs:
    :type kwargs:
    '''
    if node is not None:
      self.placeNode(node, **kwargs)
    else:
      self.placeAll()

  @abstractmethod
  def placeNode(self, node:VObject, 
                referenceNode:Optional[VObject]=None, 
                direction:Direction=Direction.UNSPECIFIED, 
                loc:Optional[Point]=None, **kwargs) -> Point:
    '''
    :param node:
    :type node: VObject
    :param referenceNode:
    :type referenceNode: Optional[VObject]
    :param direction:
    :type direction: Direction
    :param loc:
    :type loc: Optional[Point]
    :param kwargs:
    :type kwargs:
    :returns:
    :rtype: Point
    '''
    pass
    
  @abstractmethod
  def placeAll(self):
    pass
    
class FindFree(LayoutHieristic):
  
  def __init__(self, view):
    '''
    :param view:
    :type view:
    '''
    super().__init__(view)
    self.quanta = 10
    'Used when searching for non-overlapping space'
    self.expandFactor_relations = 5
    self.expandFactor_nodes = 15
    'Clear space (view units) a node wants around it (relation labels: *expandFactor_relations*).'
    self.leftMargin = 30
    self.topMargin = 30
    self.limit = [self.leftMargin, self.topMargin, 10000, 10000]
    self.isaLevelSpacing = 120
    
  @override
  def placeNode(self, node:VObject, 
                referenceNode:Optional[VObject]=None, 
                direction:Direction=Direction.UNSPECIFIED, 
                loc:Optional[Point]=None,
                aggressive:bool=False, 
                **kwargs) -> Point:
    '''
    :param node:
    :type node: VObject
    :param referenceNode:
    :type referenceNode: Optional[VObject]
    :param direction:
    :type direction: Direction
    :param loc:
    :type loc: Optional[Point]
    :param aggressive:
    :type aggressive: bool
    :param kwargs:
    :type kwargs:
    :returns:
    :rtype: Point
    '''
    from sn.view.graphics.vrelations import VRelation
    expandFactor = self.expandFactor_relations \
          if node.modelObject is not None and node.modelObject.isIndividual() and isinstance(node, VRelation) \
          else self.expandFactor_nodes
    
    if direction == Direction.UNSPECIFIED:
      if loc is not None:
        direction = Direction.NEAREST
      # elif isinstance(node, VIsa):
      #   if referenceNode is not None and node.modelObject.to == referenceNode.modelObject:
      #     direction = Direction.SUPER
      #   else:
      #     direction = Direction.SUB
      elif referenceNode is not None:
        if node.modelObject.isa(referenceNode.modelObject):
          direction = Direction.SUB
        elif referenceNode.modelObject.isa(node.modelObject):
          direction = Direction.SUPER
        else:
          direction = Direction.LATERAL
      else:
        direction = Direction.LATERAL
        
    #direction = Direction.NEAREST # Get rid of this!!!! 
    assert direction != Direction.UNSPECIFIED   
        
    maxRings = 100 # (how far out to look for a free spot: see LABEL_PLACEMENT_PREF)
    if isinstance(node, VRelation):
      level = labelPlacementLevel()
      if level == 0: # (labels stay where they're made: midway between their ends)
        bb = node.boundingBox()
        return bb[0], bb[1]
      maxRings = level * level

    def place(rect:list[int], 
              expandFactor:int, 
              quanta:int=self.quanta, 
              limit:list[int]=self.limit, 
              exclude=[]) -> tuple[int, int]|None:
      assert len(rect) == 4
      rect = [int(i) for i in rect]
      assert len(limit) == 4
      limit = [int(i) for i in limit]
      w = rect[2] - rect[0]
      h = rect[3] - rect[1]
      assert w>0
      assert h>0
      
      for dist in range(0, maxRings): # the width/height of the rectangular scan
        yStart   = max(limit[1], rect[1]-dist*quanta)
        yEnd     = min(limit[3], rect[1]+dist*quanta)
        for y in range(yStart, yEnd+1, quanta):
          xStart = max(limit[0], rect[0]-dist*quanta)
          xEnd   = min(limit[2], rect[0]+dist*quanta)
          # the ring's perimeter: all of its top and bottom rows, just the ends of the others
          xIncr  = quanta if y==yStart or y==yEnd else max(1, xEnd-xStart)
          for x in range(xStart, xEnd+1, xIncr):
            r = [x, y, x+w, y+h]
            overlapping = self.findOverlapping(expandRect(r, expandFactor), exclude)
            if len(overlapping) == 0:
              return x,y
      return None # (nowhere free within maxRings)
      
    rect = node.boundingBox()
    if loc is not None:
      rect = [loc.x, loc.y, loc.x+rect[2]-rect[0], loc.y+rect[3]-rect[1]]
    # ignore our own shape and our own relations' label shapes (canvas item ids --
    # not rel._id, the view object's id, a different numbering altogether)
    exclude = [node._shape.id] + [rel._shape.id for rel in node.relations if rel._shape is not None and rel._shape.id is not None]
    
    topLimit = self.topMargin
    bottomLimit = 10000
    leftLimit = self.leftMargin
    rightLimit = 10000
    
    if direction == Direction.NEAREST:
      pass
      
    elif direction == Direction.SUB:
      if referenceNode is not None:
        topLimit = max(self.topMargin, referenceNode.boundingBox()[3]+expandFactor* \
           (2 if node.__class__ is referenceNode.__class__ else 1))
          
      else:
        topLimit = max(self.topMargin, rect[1])
      
    elif direction == Direction.SUPER:
      h = rect[3] - rect[1]
      if referenceNode is not None:
        bottomLimit = referenceNode.boundingBox()[1]-expandFactor
      else:
        bottomLimit = rect[1]-h-expandFactor
      if bottomLimit < h+2*expandFactor: # fix the problem of squeezing at the top
        bottomLimit = h+3*expandFactor
      
    elif direction == Direction.LATERAL:
      if referenceNode is not None:
        leftLimit = max(self.leftMargin, referenceNode.boundingBox()[2]+expandFactor)
      else:
        leftLimit = max(self.leftMargin, rect[0])
        
    if node.modelObject is not None and (node.modelObject.isType() or isinstance(node, Node)) and aggressive:
      topLimit = max(topLimit, self.isaLevelSpacing*depth(node.modelObject)+self.topMargin)
      
    # what a context contains (a relation's label too), dropped in its pane, stays in it (see SNGView.containmentHomes())
    if node.modelObject is not None:
      win, pane = self.view.containmentHomes([node]).get(node, (None, ""))
      cx, cy = node.centerPt()
      px1, py1, px2, py2 = self.view.homeRect(win, pane) if win is not None else (0, 0, -1, -1)
      if px1 <= cx <= px2 and py1 <= cy <= py2:
        w, h = rect[2] - rect[0], rect[3] - rect[1]
        inside = [max(leftLimit, px1 + expandFactor), max(topLimit, py1 + expandFactor),
                  min(rightLimit, px2 - expandFactor - w), min(bottomLimit, py2 - expandFactor - h)]
        if inside[0] <= inside[2] and inside[1] <= inside[3]:
          leftLimit, topLimit, rightLimit, bottomLimit = inside

    finalLimit = [int(i) for i in [leftLimit, topLimit, rightLimit, bottomLimit]]
    pt = place(rect, expandFactor=expandFactor, exclude=exclude, limit=finalLimit)
    if pt is None: # (nowhere free close enough: it stays where it is)
      bb = node.boundingBox()
      return bb[0], bb[1]
    
    # if pt[0]!=rect[0] or pt[1]!=rect[1]:
    #   logger.debug(f'Node "{node.modelObject.name}:{node.modelObject._id}" moving in direction {direction}, limit={finalLimit} to {pt}, ref={referenceNode}.')
    
    node.moveTo(*pt, adjustPos=False)
    
    return pt
    
      
      
              
  @override
  def placeAll(self):
    pass


def intoRect(box:list[float], rect:list[float], margin:float=0.0, topMargin:float|None=None) -> tuple[float, float]:
  '''
  How far to move *box* to put it inside *rect*, *margin* in from its edges
  (*topMargin* from its top, if given) -- the least move that does it; centred
  in an axis it's too big for.

  :param box: [x1, y1, x2, y2].
  :type box: list[float]
  :param rect: [x1, y1, x2, y2].
  :type rect: list[float]
  :param margin: The space to leave inside *rect*'s edges.
  :type margin: float
  :param topMargin: The space to leave at its top (default: *margin*).
  :type topMargin: float | None
  :returns: (dx, dy).
  :rtype: tuple[float, float]
  '''
  ret = []
  for k, before in ((0, margin), (1, margin if topMargin is None else topMargin)):
    lo, hi = rect[k] + before, rect[k + 2] - margin
    b1, b2 = box[k], box[k + 2]
    if b2 - b1 > hi - lo:
      ret.append((lo + hi) / 2 - (b1 + b2) / 2)
    elif b1 < lo:
      ret.append(lo - b1)
    elif b2 > hi:
      ret.append(hi - b2)
    else:
      ret.append(0.0)
  return ret[0], ret[1]

# ---- Gathering outliers ------------------------------------------------------

def _median(values:list[float]) -> float:
  '''
  :param values:
  :type values: list[float]
  :returns:
  :rtype: float
  '''
  if not values:
    return 0.0
  s = sorted(values)
  n = len(s)
  return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2

def gatherAxisShifts(intervals:list[tuple[float, float]], *,
                     gapFactor:float=6.0, minGap:float=300.0) -> list[float]:
  '''
  One axis of :py:func:`gatherShifts`: how far to shift each interval so that
  no group of intervals is stranded far from the main pack.

  The intervals are swept in order of their low ends, keeping track of the
  furthest high end so far; wherever the next interval starts more than
  *maxGap* beyond that, a new *run* begins. The run with the most intervals
  is the pack and stays put. Every oversized gap is shrunk to *targetGap*,
  and everything beyond it (away from the pack) shifts toward the pack by the
  amount removed -- so a stranded group keeps its internal arrangement.

  The thresholds come from the drawing itself: with *S* the median interval
  length and *G* the typical gap between consecutive runs of overlapping
  intervals, ``maxGap = max(gapFactor * max(G, S), minGap)`` and
  ``targetGap = max(G, S/2)``. *G* is the median of the *smaller half* of the
  gaps, so that it isn't dominated by the very outliers it's meant to find
  (in a small drawing, one or two huge gaps can be most of the gaps).

  It's O(n log n) (one sort) and uses no distances -- just comparisons and
  differences.

  :param intervals: (low, high) extents along one axis.
  :type intervals: list[tuple[float, float]]
  :param gapFactor: How many times the typical spacing a gap must exceed to
    count as stranding what lies beyond it.
  :type gapFactor: float
  :param minGap: No gap smaller than this counts as stranding, however
    tightly packed the rest of the drawing is -- so a normal (if loose)
    layout is left alone.
  :type minGap: float
  :returns: The shift for each interval, in the same order.
  :rtype: list[float]
  '''
  n = len(intervals)
  shifts = [0.0] * n
  if n < 3:
    return shifts
  order = sorted(range(n), key=lambda i: intervals[i][0])

  # the gaps between consecutive runs of overlapping intervals
  gaps:list[float] = []
  reach = intervals[order[0]][1]
  for i in order[1:]:
    lo, hi = intervals[i]
    if lo > reach:
      gaps.append(lo - reach)
    reach = max(reach, hi)
  S = _median([hi - lo for lo, hi in intervals])
  G = _median(sorted(gaps)[:max(1, len(gaps)//2)])
  maxGap = max(gapFactor * max(G, S), minGap)
  targetGap = max(G, S / 2)
  if maxGap <= 0:
    return shifts

  # split into runs at the oversized gaps
  runs:list[list[int]] = [[order[0]]]
  gapAfter:list[float] = []  # gapAfter[k] is the gap between runs k and k+1
  reach = intervals[order[0]][1]
  for i in order[1:]:
    lo, hi = intervals[i]
    if lo - reach > maxGap:
      gapAfter.append(lo - reach)
      runs.append([i])
    else:
      runs[-1].append(i)
    reach = max(reach, hi)
  if len(runs) == 1:
    return shifts

  pack = max(range(len(runs)), key=lambda k: len(runs[k]))
  removed = 0.0
  for k in range(pack + 1, len(runs)):  # beyond the pack's high end: shift down
    removed += gapAfter[k - 1] - targetGap
    for i in runs[k]:
      shifts[i] = -removed
  removed = 0.0
  for k in range(pack - 1, -1, -1):     # beyond its low end: shift up
    removed += gapAfter[k] - targetGap
    for i in runs[k]:
      shifts[i] = removed
  return shifts

def gatherShifts(boxes:list[list[float]], *, gapFactor:float=6.0, minGap:float=300.0) -> list[tuple[float, float]]:
  '''
  Herd outlying boxes back toward the main pack, treating the x and y axes
  independently (see :py:func:`gatherAxisShifts`): something flung far away on
  only one axis is only pulled back on that axis.

  :param boxes: [x1, y1, x2, y2] bounding boxes.
  :type boxes: list[list[float]]
  :param gapFactor:
  :type gapFactor: float
  :param minGap:
  :type minGap: float
  :returns: The (dx, dy) to move each box by, in the same order.
  :rtype: list[tuple[float, float]]
  '''
  dxs = gatherAxisShifts([(b[0], b[2]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  dys = gatherAxisShifts([(b[1], b[3]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  return list(zip(dxs, dys))

# ---- Gathering into a context window -----------------------------------------

def freeSpotIn(box:list[float], rect:list[float], obstacles:Iterable[list[float]], *,
               margin:float=10.0, topMargin:float|None=None, gap:float|tuple[float, float]=10.0, step:float=10.0,
               rows:bool=False) -> tuple[float, float]|None:
  '''
  How far to move *box* to put it inside *rect* (*margin* in from its edges;
  *topMargin* from its top, if given), clear of every one of *obstacles* by
  *gap* (or (across, down)), on a *step* grid: the spot nearest to where *intoRect()* would put it
  (a box that's already inside and clear stays put) -- or, with *rows*, the
  first free spot reading *rect* row by row from its top left (so things
  brought from far away are set out tidily).

  :param box: [x1, y1, x2, y2].
  :type box: list[float]
  :param rect: [x1, y1, x2, y2].
  :type rect: list[float]
  :param obstacles: Boxes to keep clear of.
  :type obstacles: Iterable[list[float]]
  :returns: (dx, dy) -- or None if there's no room.
  :rtype: tuple[float, float] | None
  '''
  obs = [o for o in obstacles]
  gx, gy = gap if isinstance(gap, tuple) else (gap, gap)
  w, h = box[2] - box[0], box[3] - box[1]
  lo_x, lo_y = rect[0] + margin, rect[1] + (margin if topMargin is None else topMargin)
  hi_x, hi_y = rect[2] - margin - w, rect[3] - margin - h
  if hi_x < lo_x or hi_y < lo_y:
    return None
  def clear(x:float, y:float) -> bool:
    return all(x + w + gx <= o[0] or o[2] + gx <= x or y + h + gy <= o[1] or o[3] + gy <= y for o in obs)
  nx, ny = int((hi_x - lo_x) // step), int((hi_y - lo_y) // step)
  spots = [(lo_x + i * step, lo_y + j * step) for i in range(nx + 1) for j in range(ny + 1)]
  if rows:
    spots.sort(key=lambda p: (p[1], p[0]))
  else:
    ex, ey = intoRect(box, rect, margin, topMargin)
    tx, ty = box[0] + ex, box[1] + ey # (where it would go, ignoring the obstacles)
    if clear(tx, ty):
      return ex, ey
    spots.sort(key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)
  for x, y in spots:
    if clear(x, y):
      return x - box[0], y - box[1]
  return None
