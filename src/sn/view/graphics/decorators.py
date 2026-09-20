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
        Decorator
        Marker
        MarkerContainer
        MarkerWithTooltip
        Selected
        WrappingText
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Feb 3, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

------------------
'''

import logging
import weakref
from abc import ABC, abstractmethod
from math import sqrt
from typing import override, Callable, Optional, Union, Any
import sn
from sn import snPrefs
#from sn.view import tooltip
from util.tooltip import CreateToolTip

logger:sn.SNLogger = sn.getLogger(__name__)

DOT = '\u23FA'

##########################################################################################
################################ D E C O R A T O R S #####################################
##########################################################################################

class Decorator(ABC):
  def __init__(self, owner, priority:int=0):
    '''
    :param owner: The *VObject* this decorator is attached to.
    :param priority: [int, default=0] Where this decorator draws relative to
      the owner's other decorators, lowest first -- see *VObject.draw()*,
      which draws *self.decorators.values()* sorted by this. Ties keep
      insertion order (Python's sort is stable), so existing decorators are
      unaffected by just leaving this at its default.

      This only orders decorators *within one VObject's own draw() call* --
      it can't reach across to order against a *different* VObject's items,
      since canvas stacking is one global list, not per-object (see
      *ShadowDecorator*, which needs exactly that and uses
      *canvas.tag_lower()* instead).
    :type priority: int
    '''
    from sn.view.graphics.vobjects import VObject
    assert isinstance(owner, VObject)

    super().__init__()

    self._owner = weakref.ref(owner)
    self.kind = type(self).__name__
    self.deleted:bool = False
    self.priority:int = priority

  @property
  def owner(self):
    return self._owner()

  def delete(self):
    if self.deleted: return
    self.deleted = True
    self.owner.notifyDecoratorDeletion(self)

  @abstractmethod
  def draw(self, fast=False, **kwargs):
    pass

class Text(Decorator):
  def __init__(self, owner, **kwargs):
    super().__init__(owner)
    self.id = None # The id of the canvas item
    self.kwargs = kwargs
    if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
    if "anchor"  not in self.kwargs: self.kwargs["anchor"]  = "center"
    if "font"    not in self.kwargs: self.kwargs["font"]    = (self.owner.view._fontFace, int(self.owner.view._fontSize*self.owner.view._scale))
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = "black"

  def updateKwargs(self):
    self.kwargs["fill"] = self.owner.cache["vis/textColor"]
      
  @override
  def draw(self, fast=False, **kwargs):
    if not fast:
      self.updateKwargs() # first update from the GraphObject.
    self.kwargs.update(kwargs) # then from the parameters
    self.setText(fast=fast)
    self.setFontToScale()
    x, y = self.getCoords()
    if self.id is None:
      self.kwargs["state"] = "disabled"
      self.kwargs["tags"] = [self.owner.tag, 'text']
      self.id = self.owner.canvas.create_text(x, y, **self.kwargs)
    else:
      self.owner.canvas.coords(self.id, x, y)
      self.owner.canvas.itemconfigure(self.id, **self.kwargs)
      
  def getCoords(self) -> tuple[int, int]:
    x, y = self.owner.centerPt()
    x += 3
    return self.owner.view.viewToWindow(x,y)
      
  def setText(self, fast=False) -> str:
    name = self.owner.modelObject.name if self.owner.modelObject is not None else "?"
    if name is None:
      text = ""
    else:
      text = name.strip()
    self.kwargs['text'] = text
    return text
          
  def setFontToScale(self):
    self.kwargs["font"] = (self.owner.view._fontFace, int(self.owner.view._fontSize * self.owner.view._scale))

  @override
  def delete(self):
    if self.deleted: return
    super().delete()
    self.owner.canvas.delete(self.id)
    self.kwargs = None #type: ignore[assignment]
  
class WrappingText(Text):

  def __init__(self, owner, **kwargs):
    super().__init__(owner, **kwargs)
    self.text = None
    self.minSize = -1
    self.aspectRatio = 0

  @override
  def setText(self, fast=False):
    super().setText
    dirty = False
    text = super().setText(fast=fast)
    self.kwargs['text'] = text
    if text != self.text: 
      dirty = True
      self.text = text
    minSize = self.owner.cache["vis/minSize"]
    if minSize != self.minSize: 
      dirty = True
      self.minSize = minSize
    aspectRatio = self.owner.cache["vis/aspectRatio"]
    if aspectRatio != self.aspectRatio: 
      dirty = True
      self.aspectRatio = aspectRatio

    # We may need to change the size of the Shape
    if dirty and self.owner.cache["vis/textModifiesBB"]:
      area = len(text)*160
      width = sqrt(area/aspectRatio) # area = width * width*aspectRatio
      if width > minSize: # we need to make the Shape bigger
        self.kwargs["width"] = width
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)
        height = area/width
        bb = self.owner.boundingBox(fast=fast)
        if bb[2]!=width or bb[3]!=height:
          self.owner.boundingBox([bb[0], bb[1], bb[0]+width, bb[1]+height], fast=fast)

    self.owner.canvas.itemconfigure(self.id, **self.kwargs)
          
class Marker:
  SIZE = [6,6]
  def __init__(self, owner, label:str, fg:str, bg:str, condition:Callable):
    self.owner = owner
    self.label:str = label
    self.fg:str = fg
    self.bg:str = bg
    self.condition:Callable = condition
    self.kwargs:dict[str, Any] = dict()
    self.kwargs2:dict[str, Any] = dict()
    self.id = None # The id of the shape canvas item
    self.id2 = None # The id of the text canvas item
    self.deleted = False
    
  def draw(self, at:list[int]) -> bool:
    '''
    :return: *True* iff the item actually drew (ie: *self.condition()* returns *True*
    '''
    if not self.condition(self.owner):
      self.erase()
      return False
      
    if self.id is None:       
      self.kwargs["state"] = "normal"
      self.kwargs["tags"] = [self.owner.tag, 'text']
      if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
      if "anchor"   not in self.kwargs: self.kwargs["anchor"]  = "center"
      if "font"     not in self.kwargs: self.kwargs["font"]    = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
      self.kwargs["text"] = self.label if self.label != 'E' else str(len(self.owner.statusReport()))
      self.kwargs["fill"] = self.fg
      if "fill"     not in self.kwargs2: self.kwargs2["fill"]    = self.bg
      if "outline"  not in self.kwargs2: self.kwargs2["outline"] = ""
      self.kwargs2["tags"] = [self.owner.tag]
      self.id2 = self.owner.canvas.create_oval(
                  self.owner.view.viewToWindow(
                  [at[0]-Marker.SIZE[0], 
                   at[1]-Marker.SIZE[1], 
                   at[0]+Marker.SIZE[0], 
                   at[1]+Marker.SIZE[1]]),
                   **self.kwargs2)
      self.id   = self.owner.canvas.create_text(self.owner.view.viewToWindow(at[0])[0], self.owner.view.viewToWindow(at[1])[0], **self.kwargs)
      #self.id   = self.owner.canvas.create_text(at[0], at[1], **self.kwargs)
    else:   
      #self.kwargs.update(kwargs)
      if self.id is not None:
        self.owner.canvas.coords(self.id2, 
                  self.owner.view.viewToWindow(
                  [at[0]-Marker.SIZE[0], 
                   at[1]-Marker.SIZE[1], 
                   at[0]+Marker.SIZE[0], 
                   at[1]+Marker.SIZE[1]]))
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(at[0], at[1]))
        self.kwargs["font"] = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)
        self.owner.canvas.itemconfigure(self.id2, **self.kwargs2)
    return True
    
  def erase(self):
    if self.id is not None:
      self.owner.canvas.delete(self.id)
      self.id = None
    if self.id2 is not None:
      self.owner.canvas.delete(self.id2)
      self.id2 = None

  def delete(self):
    if self.deleted: return
    self.owner.canvas.delete(self.id)
    self.owner.canvas.delete(self.id2)
    self.deleted = True

    
class MarkerWithTooltip(Marker):
  
  def __init__(self, owner, label:str, fg:str, bg:str, condition:Callable, tooltipFunc:Union[Callable,str]):
    super().__init__(owner, label, fg, bg, condition)
    self.tooltipFunc = tooltipFunc

  def draw(self, at:list[int]) -> bool:
    '''
    :return: *True* iff the item actually drew (ie: *self.condition()* returns *True*
    '''
    self.tooltip:Optional[CreateToolTip] = None
    new = True if self.id is None else False
    ret = super().draw(at)
    if not ret:
      return ret
    if new:
      self.tooltip = CreateToolTip(self.owner.canvas, self.tooltipFunc, self.id, 
                                 waitTime=1000, wrapLength=250, background="#FFFFC0")
    return ret

  def erase(self):
    if self.tooltip is not None:
      self.tooltip.delete()
      self.tooltip = None
    super().erase()

  def delete(self):
    if self.deleted: return
    if self.tooltip is not None:
      self.tooltip.delete()
      self.tooltip = None
    super().delete()


class MarkerContainer(Decorator):

  def __init__(self, owner):
    Decorator.__init__(self, owner)
    self.markers = [
        MarkerWithTooltip(owner, "E", "white", "red", 
               lambda owner=self.owner: len(owner._statusReport)>0,
               lambda owner=self.owner: DOT + ' ' + (f'\n{DOT} '.join(owner.statusReport()))),
        MarkerWithTooltip(owner, "S", "yellow", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.modelObject.isSystemObject() and snPrefs.get("gui/showSystemTags", storeDefault=True),
               "System: Object is a fixed system object"),
        MarkerWithTooltip(owner, "T", "lawn green", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.modelObject.isType() and snPrefs.get("gui/showTypeTags", storeDefault=True),
               "Type: object is a Type object (as opposed to an Individual)"),
        MarkerWithTooltip(owner, "R", "cyan", "gray50", 
               lambda owner=self.owner: owner.modelObject is not None and owner.view.model != owner.modelObject.model and snPrefs.get("gui/showRemoteTags", storeDefault=True),
               lambda owner=self.owner: f'Remote: Object is from another model: {owner.modelObject.model.url}')
        ]

  @override
  def delete(self):
    for m in self.markers:
      m.delete()
    return Decorator.delete(self)

  @override
  def draw(self, fast=False, **kwargs):
    bb = self.owner.boundingBox()
    pt = [bb[0]-Marker.SIZE[0], bb[1]-Marker.SIZE[1]]
    for m in self.markers:
      if m.draw(pt):
        pt[0] += (2*Marker.SIZE[0])
    return Decorator.draw(self, fast, **kwargs)

  
# class Marker2(Decorator):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner)
#     self.kwargs = kwargs
#     self.offset = (-3,-3)
#     self.size = (6,6) # actually, this is half of the size
#
#   def delete(self):
#     if self.deleted: return
#     super().delete()
#     self.kwargs = None
#
#   def getOffset(self) -> list:
#     offset = [self.offset[0]+self.owner.markerDecoratorOffset, self.offset[1]]
#     self.owner.markerDecoratorOffset += (2 * self.size[0] + 1)
#     return offset
#
# class CircleMarker(Marker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.id2 = None
#
#   @abstractmethod
#   def setArgs(self):
#     pass
#
#   def draw(self, fast=False, **kwargs):
#     if self.id is None:       
#       self.kwargs["state"] = "normal"
#       self.kwargs["tags"] = [self.owner.tag, 'text']
#       if "justify" not in self.kwargs: self.kwargs["justify"] = "center"
#       if "anchor"   not in self.kwargs: self.kwargs["anchor"]  = "center"
#       if "font"     not in self.kwargs: self.kwargs["font"]    = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
#       if "fill"     not in self.kwargs: self.kwargs["fill"]    = "white"
#       self.setArgs()
#       x, y, _, _ = self.owner.boundingBox(fast=fast)
#       offset = self.getOffset()
#       self.id2 = self.owner.canvas.create_oval(
#                   self.owner.view.viewToWindow(
#                   [x+offset[0]-self.size[0], 
#                    y+offset[1]-self.size[1], 
#                    x+offset[0]+self.size[0], 
#                    y+offset[1]+self.size[1]]),
#                    **self.kwargs2)
#       self.id   = self.owner.canvas.create_text(x+offset[0], y+offset[1], **self.kwargs)
#     else:   
#       self.kwargs.update(kwargs)
#       if self.id is not None:
#         self.setArgs()
#         x, y, _, _ = self.owner.boundingBox(fast=fast)
#         offset = self.getOffset()
#         self.owner.canvas.coords(self.id2, 
#                   self.owner.view.viewToWindow(
#                   [x+offset[0]-self.size[0], 
#                    y+offset[1]-self.size[1], 
#                    x+offset[0]+self.size[0], 
#                    y+offset[1]+self.size[1]]))
#         self.owner.canvas.coords(self.id, self.owner.view.viewToWindow([x+offset[0], y+offset[1]]))
#         self.kwargs["font"] = ("TkSmallCaptionFont", int(self.owner.view._fontSize * self.owner.view._scale))
#         self.owner.canvas.itemconfigure(self.id, **self.kwargs)
#         self.owner.canvas.itemconfigure(self.id2, **self.kwargs2)
#
#   def delete(self):
#     if self.deleted: return
#     super().delete()
#     self.owner.canvas.delete(self.id)
#     self.owner.canvas.delete(self.id2)
#     self.kwargs2 = None
#
# class TypeMarker(CircleMarker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.kwargs2 = {"tags": [self.owner.tag], "fill": "grey", "outline": ""}
#
#   def setArgs(self):
#     label = ""
#     if self.owner.modelObject.isSystemObject():
#       label += "S"
#     if self.owner.modelObject.isType():
#       label += "T"
#     self.kwargs["text"] = label
#     self.kwargs["fill"] = "lawn green"
#
#     self.kwargs2["fill"] = "black" if self.owner.modelObject.isSystemObject else "grey"
#
# class ErrorMarker(CircleMarker):
#   def __init__(self, owner, **kwargs):
#     super().__init__(owner, **kwargs)
#     self.kwargs2 = {"tags": [self.owner.tag], "fill": "red", "outline": ""}
#
#   def setArgs(self):
#     self.kwargs["text"] = "X"      
#     self.kwargs2["fill"] = "red"
    
class Selected(Decorator):
  def __init__(self, owner, **kwargs):
    super().__init__(owner)
    self.id = None
    self.kwargs = kwargs
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = ""
    if "width"   not in self.kwargs: self.kwargs["width"]   = 3
    if "outline" not in self.kwargs: self.kwargs["outline"] = "blue"
    if "dash"    not in self.kwargs: self.kwargs["dash"]    = (1,6)

  def draw(self, fast=False, **kwargs):
    self.kwargs.update(kwargs)
    if self.id is None:
      self.kwargs["tags"] = [self.owner.tag, 'selection']
      rect = self.owner.boundingBox(fast=fast)
      rect = self.owner.view.viewToWindow(rect)
      self.id = self.owner.canvas.create_rectangle(rect, **self.kwargs)
    else:
      rect = self.owner.boundingBox(fast=fast)
      rect = self.owner.view.viewToWindow(rect)
      self.owner.canvas.coords(self.id, rect)
      self.owner.canvas.itemconfigure(self.id, **self.kwargs)

  def delete(self):
    if self.deleted: return
    super().delete()
    self.owner.canvas.delete(self.id)
    self.kwargs = None


class ShadowDecorator(Decorator):
  '''
  Draws a plain "duplicate shape, grey, one z-order lower" drop shadow behind
  the owner's own shape -- the standard tk drop-shadow technique, rather than
  anything Pillow/raster-based (too costly to redraw/rescale for this).

  Only drawn for snPrefs["gui/showIndividualShadow"] is True.

  Does NOT yet support "vis/shadowColor" or any other attribute-driven
  customization -- the constructor *kwargs* are the only knob for now. See
  *Shape.shapeOptionsMap* / *Shape.updateKwargs()* for the pattern to follow
  if/when that's added later.
  '''
  def __init__(self, owner, offset:tuple[int,int]=(4,4), **kwargs):
    '''
    :param owner: The *VObject* this decorator is attached to.
    :param offset: [tuple[int,int], default=(4,4)] The (dx, dy) the shadow is
      shifted from the real shape, added directly to the coordinates
      *Shape.points()* / *Oval.boundingBox()* themselves work in -- see
      *draw()*, which otherwise mirrors *Shape.draw()* / *Oval.draw()*
      coordinate handling exactly so the shadow tracks the real shape.
    :type offset: tuple[int,int]
    :param kwargs: extra tk canvas item options for the shadow item; "fill"
      and "outline" default to a plain grey/none if not given.
    '''
    # priority=-10 only orders this decorator among the owner's *own*
    # decorators (see Decorator.priority) -- the actual "always at the very
    # back of the whole canvas" guarantee comes from tag_lower() in draw(),
    # below, not from priority.
    super().__init__(owner, priority=-10)
    self.id:int|None = None # the id of the canvas item
    self.offset = offset
    self.kwargs = kwargs
    
    if "fill"    not in self.kwargs: self.kwargs["fill"]    = "" if owner.cache['vis/fillColor'] == "" else "gray70"
    if "outline" not in self.kwargs: self.kwargs["outline"] = "" if owner.cache['vis/borderColor'] == "" else "gray70"

  def _offsetPoints(self, points:list[float]) -> list[float]:
    dx, dy = self.offset
    return [p + (dx if i%2==0 else dy) for i, p in enumerate(points)]

  def _erase(self):
    if self.id is not None:
      self.owner.canvas.delete(self.id)
      self.id = None

  @override
  def draw(self, fast=False, **kwargs):
    '''
    Shadow visibility isn't a persisted attribute -- like *MarkerContainer*'s
    marker *condition*\\ s, it's just re-derived every draw: Individuals get
    a shadow, Types don't. If *self.owner.modelObject.isType()*, any existing
    shadow item is erased and we return immediately.
    '''
    if not snPrefs.get("gui/showIndividualShadow", storeDefault=True, storeType=bool):
      self._erase()
      return

    self.kwargs.update(kwargs)
    shape = self.owner._shape

    # Oval.draw() renders a true ellipse via create_oval() (unlike the other
    # Shapes, which are all polygons) and applies viewToWindow() consistently
    # on both create and redraw -- mirror that exactly rather than using
    # Oval.points(), which is only a 24-vertex polygon *approximation* used
    # for hit-testing, not what actually gets drawn.
    from sn.view.graphics.shapes import Oval
    if isinstance(shape, Oval):
      bb = self.owner.boundingBox(fast=fast)
      bb = [bb[0]+self.offset[0], bb[1]+self.offset[1], bb[2]+self.offset[0], bb[3]+self.offset[1]]
      if self.id is None:
        self.id = self.owner.canvas.create_oval(self.owner.view.viewToWindow(bb), **self.kwargs)
        self.owner.canvas.itemconfigure(self.id, tags=[self.owner.tag, 'shadow'])
      else:
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(bb))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)
    else:
      # Shape.draw() itself has a create/redraw asymmetry -- create_polygon()
      # gets raw points() with no viewToWindow(), while the redraw coords()
      # call applies viewToWindow() -- mirror it exactly so the shadow stays
      # pixel-aligned with the real shape at any zoom/scroll.
      if self.id is None:
        pts = self._offsetPoints(shape.points(fast=fast))
        self.id = self.owner.canvas.create_polygon(pts, **self.kwargs)
        self.owner.canvas.itemconfigure(self.id, tags=[self.owner.tag, 'shadow'])
      else:
        pts = self._offsetPoints(shape.points(fast=fast))
        self.owner.canvas.coords(self.id, self.owner.view.viewToWindow(pts))
        self.owner.canvas.itemconfigure(self.id, **self.kwargs)

    # Always re-assert absolute-bottom stacking: tag_lower() with a single
    # argument moves this item to the bottom of the *whole* canvas, so this
    # is enough to keep every shadow behind every real shape and decorator,
    # with no need to coordinate across VObjects.
    self.owner.canvas.tag_lower(self.id)

  @override
  def delete(self):
    if self.deleted: return
    super().delete()
    self._erase()
    self.kwargs = None

