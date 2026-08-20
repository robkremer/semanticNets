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
import sn
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

import logging
from abc import ABC, abstractmethod
from sn.view.graphics.vnodes import VNode
from enum import Enum
from typing import Optional, override
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VIsa
from util.utils import Point, expandRect
from sn.model import GraphObject
from sn.model import Node
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
    from sn.view.graphics.view import SNView
    assert isinstance(view, SNView)
    self.view = view
    
  def _setDirection(self, node:VObject, referenceNode:Optional[VObject], loc:Optional[Point]=None):
    if loc is not None:
      return Direction.NEAREST
    if referenceNode is None: # and loc is None
      return Direction.LATERAL
    else: #referenceNode is not None and loc is None
      if node.isa(referenceNode):
        return Direction.SUB
      elif referenceNode:
        return Direction.SUPER
    
  def findOverlapping(self, rect:list[int], exclude:list[int]=[]) -> list[int]:
    '''
    :return: The (possible zero-length) list of "shape"-tagged tk.Canvas object ids
        that overlap with bounding box of *node*.
    '''
    overlapping = self.view.intersectTag(self.view.canvas.find_overlapping(*rect), "shape", exclude)
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
    self.expandFactor_nodes = 30
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
          if node.modelObject.isIndividual() and isinstance(node, VRelation) \
          else self.expandFactor_nodes
    
    if direction == Direction.UNSPECIFIED:
      if loc is not None:
        direction = Direction.NEAREST
      elif isinstance(node, VIsa):
        if referenceNode is not None and node.modelObject.to == referenceNode.modelObject:
          direction = Direction.SUPER
        else:
          direction = Direction.SUB
      elif referenceNode is not None:
        if node.isa(referenceNode):
          direction = Direction.SUB
        elif referenceNode.isa(node):
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
    exclude = [node._shape.id] + [rel._id for rel in node.relations]
    
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
        
    if (node.modelObject.isType() or isinstance(node, Node)) and aggressive:
      topLimit = max(topLimit, self.isaLevelSpacing*depth(node.modelObject)+self.topMargin)
      
    finalLimit = [int(i) for i in [leftLimit, topLimit, rightLimit, bottomLimit]]
    pt = place(rect, expandFactor=expandFactor, exclude=exclude, limit=finalLimit)
    
    if pt[0]!=rect[0] or pt[1]!=rect[1]:
      logger.debug(f'Node "{node.modelObject.name}:{node.modelObject._id}" moving in direction {direction}, limit={finalLimit} to {pt}, ref={referenceNode}.')
    
    node.moveTo(*pt, adjustPos=False)
    
    return pt
    
      
      
              
  @override
  def placeAll(self):
    pass
