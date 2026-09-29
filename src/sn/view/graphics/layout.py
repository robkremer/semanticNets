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
from typing import Optional, override
from sn.view.graphics.vnodes import VNode
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from util.utils import Point, expandRect
from sn.model.model import GraphObject, Node
from util.utils import removeDuplicates

logger:sn.SNLogger = sn.getLogger(__name__)

class Direction(Enum):
  UNSPECIFIED = 0
  SUB = 1
  SUPER = 2
  LATERAL = 3
  NEAREST = 4
  
def depth(obj:GraphObject) -> int:
  '''
  :return: the isa-depth of *obj*.
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
    '''
    from sn.view.graphics.sngView import SNGView
    assert isinstance(view, SNGView)
    self.view = view
    
  def _setDirection(self, node:VObject, referenceNode:Optional[VObject], loc:Optional[Point]=None):
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
    :return: The (possible zero-length) list of 'vis/shape'-tagged tk.Canvas object ids
        that overlap with bounding box of *node*.
    '''
    overlapping = self.view.intersectTag(self.view.canvas.find_overlapping(*rect), 'vis/shape', exclude)
    return overlapping
    
  def __call__(self, node:Optional[VObject]=None, **kwargs):
    if node is not None:
      self.placeNode(node, **kwargs)
    else:
      self.placeAll()

  @abstractmethod
  def placeNode(self, node:VObject, 
                referenceNode:Optional[VObject]=None, 
                direction:Direction=Direction.UNSPECIFIED, 
                loc:Optional[Point]=None, **kwargs) -> Point:
    pass
    
  @abstractmethod
  def placeAll(self):
    pass
    
class FindFree(LayoutHieristic):
  
  def __init__(self, view):
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
        
    def place(rect:list[int], 
              expandFactor:int, 
              quanta:int=self.quanta, 
              limit:list[int]=self.limit, 
              exclude=[]):
      assert len(rect) == 4
      rect = [int(i) for i in rect]
      assert len(limit) == 4
      limit = [int(i) for i in limit]
      w = rect[2] - rect[0]
      h = rect[3] - rect[1]
      assert w>0
      assert h>0
      
      for dist in range(0, 100): # the width/height of the rectangular scan
        yStart   = max(limit[1], rect[1]-dist*quanta)
        yEnd     = min(limit[3], rect[1]+dist*quanta)
        for y in range(yStart, yEnd+1, quanta):
          xStart = max(limit[0], rect[0]-dist*quanta)
          xEnd   = min(limit[2], rect[0]+dist*quanta)
          xIncr  = max(1, (xEnd-xStart) if y==yStart or y==yEnd else quanta)
          for x in range(xStart, xEnd+1, xIncr):
            r = [x, y, x+w, y+h]
            overlapping = self.findOverlapping(expandRect(r, expandFactor), exclude)
            if len(overlapping) == 0:
              return x,y
              
      
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
      
    finalLimit = [int(i) for i in [leftLimit, topLimit, rightLimit, bottomLimit]]
    pt = place(rect, expandFactor=expandFactor, exclude=exclude, limit=finalLimit)
    
    # if pt[0]!=rect[0] or pt[1]!=rect[1]:
    #   logger.debug(f'Node "{node.modelObject.name}:{node.modelObject._id}" moving in direction {direction}, limit={finalLimit} to {pt}, ref={referenceNode}.')
    
    node.moveTo(*pt, adjustPos=False)
    
    return pt
    
      
      
              
  @override
  def placeAll(self):
    pass


# ---- Gathering outliers ------------------------------------------------------

def _median(values:list[float]) -> float:
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
  :param gapFactor: How many times the typical spacing a gap must exceed to
    count as stranding what lies beyond it.
  :param minGap: No gap smaller than this counts as stranding, however
    tightly packed the rest of the drawing is -- so a normal (if loose)
    layout is left alone.
  :returns: The shift for each interval, in the same order.
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
  :returns: The (dx, dy) to move each box by, in the same order.
  '''
  dxs = gatherAxisShifts([(b[0], b[2]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  dys = gatherAxisShifts([(b[1], b[3]) for b in boxes], gapFactor=gapFactor, minGap=minGap)
  return list(zip(dxs, dys))
