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
        Shape
        Rectangle
        RightParallelogram
        LeftParallelogram
        FileFolder
        TopPentagon
        RightPentagon
        LeftPentagon
        Hexagon
        RoundedShape
        RoundedRectangle
        Oval
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Jan 30, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

-------------
'''

from typing import Optional
import tkinter as tk
from math import cos, sin, pi

from util.utils import allConcreteSubclasses
from sn.view.graphics.vobjects import VObject

import logging
import weakref
logger:sn.SNLogger = sn.getLogger(__name__)

##########################################################################################
################################### S H A P E S ##########################################
##########################################################################################

class Shape:
  '''
  A 'abstract' base class for all *VObject* shapes. The position and size of the
  shape is delegated to the *self.vobject.boundingBox()* method. 
    
  This class supports the 
  implementation of a shape being a list of points: list of numbers where the
  even (starting with zero) indices are x's and the odd indices are y's. 
  Must have an even number of elements.
  '''
  @classmethod
  def isPublic(cls):
    '''
    A method to be overridden by decsendant classes to indicate weather the
    class is "virtual" or not. Here, not being "virtual" indicates the class
    should not be directoy instantiated.
    '''
    return False

  @classmethod
  def getShapeClass(cls, name:str):
    '''
    :return: the class (<: *Shape* ) whose class name is *name* or *None* if there
            is no such class. 
    '''
    try:
      klass = globals()[name]
    except:
      return None
    if issubclass(klass, Shape):
      return klass
    return None
  
  @classmethod
  def shapeValidator(cls, name:Optional[str]=None) -> str|list[str]:
    '''
    :param name: [Optional[str] The name to to search for or *None* to return a 
      list of all known concrete subclasses of *Shape* .
    :return: the class (<: *Shape* ) whose class name is *name* or *None* if there
            is no such class. If *name* is *None*, returns a list of all known 
            concrete subclasses of *Shape* .
    '''
    if name is None:
      classes = allConcreteSubclasses(Shape)
      return [c.__name__ for c in classes if c.isPublic()]
    c = Shape.getShapeClass(name)
    if c is None:
      raise ValueError(f'Shape.shapeValidator(): name "{name}" is not the name of a subclass of Shape.')
    return c.__name__

  @classmethod
  def getShapeNames(cls):
    ':return: a list of all known concrete subclasses of *Shape* .'
    return Shape.shapeValidator()

  def __init__(self, vobject:VObject, **kwargs):
    """
    :param vobject: The "owner"
    """
    assert isinstance(vobject, VObject)
    self._vobject = weakref.ref(vobject)
    'A weakref to the "owner" *VObject*. Should NOT be accessed directly, but through the *vobject* property.'
    self.id:int|None = None 
    'ID int of the canvas tk draw item, NOT the persistence ID'
    self.kwargs = kwargs
    'The tk arguments to specify the attributes of the shape'
    
    if "fill" not in self.kwargs: self.kwargs["fill"] = "old lace" 
    if "outline" not in self.kwargs: self.kwargs["outline"] = "black" 
    
  def delete(self):
    # remove the shape
    if self.id is not None:
      self.vobject.canvas.delete(self.id)
    self._vobject = None # type: ignore[assignment]
    self.kwargs = None # type: ignore[assignment]
    
  @property
  def vobject(self) -> VObject:
    '''
    The *VNode* that owns this shape. Implemented as a weakref under the covers.
    '''
    if self._vobject is None:
      raise LookupError("VObject appears to have been deleted.")
    ret = self._vobject()
    if ret is None:
      raise MemoryError("VObject appears to have been deleted.")
    return ret
         
  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [0.0, 0.0, 
            1.0, 0.0, 
            1.0, 1.0, 
            0.0, 1.0] # bounding box rectangle
  
  def points(self, rect:Optional[list[float]]=None, fast=False) -> list[float]:
    """
    :param rect: a rectangle taken as the bounding box for this Shape's points
          in VIEW coordinates. 
    :return: Returns the vertex points fitted to *rect* if it's given, otherwise 
          *self.boundingBox()*\\ , in VEIW coordinates (not WINDOW coordinates).
          
    If subclasses have properly overridden the *template()* method, there should
    be no need to override this method.
    """
    if rect is None:
      rect = self.vobject.boundingBox(fast=fast)
    return self.transform(rect, fast=fast) # points in WINDOW coordinates
  
  def transform(self, new:list[int|float], adj:Optional[list[int]]=[0,0,1,1], 
                pointsVector:Optional[list[float]]=None, fast=False) -> list[float]:
    """
    :param new: [list[int], len=4] The new boundng box
    :param adj: [Optional[list[int]], len=4, default=[0,0,1,1]] The adjustment factor
        for the transformation [xoffset, yoffset, xmagnification, ymagnification].
    :param pointsVector: [list[float], len=even, default=self.template()] A points-pair template with all 
          points 0.0>=p<=1.0. Usually from *self.template()* .
    :return: the transform of the points vector to fit the new bounding box
    """
    assert len(new) == 4
    if adj is None: adj = self.vobject.boundingBox(fast=fast)
    assert len(adj) == 4
    if pointsVector is None: pointsVector = self.template()
    assert len(pointsVector)%2 == 0
    for i in pointsVector:
      assert i>=0.0 and i<=1.0

    oox = adj[0] # adj offset
    nox = new[0] # new offset
    owx = abs(adj[2] - adj[0]) # adj width
    nwx = abs(new[2] - new[0]) # new width
    stretchx = nwx/owx
    ooy = adj[1] # adj offset
    noy = new[1] # new offset
    owy = abs(adj[3] - adj[1]) # adj height
    nwy = abs(new[3] - new[1]) # new height
    stretchy = nwy/owy
    newPoints = []
    for i in range(0, len(pointsVector), 2):
      x = float((pointsVector[i]   - oox) * stretchx + nox)
      y = float((pointsVector[i+1] - ooy) * stretchy + noy)
      newPoints.append(x)
      newPoints.append(y)
    return newPoints

  shapeOptionsMap:dict[str,str] = {
    'vis/borderColor': "outline",
    'vis/fillColor': "fill",
    'vis/borderWidth': "width",
    }
    #TODO: 'vis/borderSmooth': "smooth", # seems to be am unknown option, contrary to the doc.
    
  def updateKwargs(self):
    if self.vobject.modelObject is None:
      return
    attrkeys = self.vobject.modelObject.keys()
    for opt in self.shapeOptionsMap.keys():
      if opt in attrkeys:
        val = self.vobject.cache[opt]
        self.kwargs[self.shapeOptionsMap[opt]] = val

  def checkShape(self) -> bool:
    '''
    Check if the shape has changed, and if it has, replace *self* in self.vobject
    and return *True*, else return *False*. The caller should return immediately
    if this method returns *True*.
    '''      
    try: # The shape attribute may not have been declared yet during initialization
      if self.vobject.cache["vis/shape"] != self.__class__.__name__:
        self.vobject.shape(self.vobject.cache["vis/shape"]) #TODO: check this
        return True
    except:
      pass
    return False
    
  def draw(self, fast=False, **kwargs) -> int|None:
    # if self.vobject is None: #premature update during a shape change?
    #   return None
    if not fast and self.checkShape(): return None
    if not fast: # first update from the GraphObject.
      self.updateKwargs() 
    self.kwargs.update(kwargs) # then from the parameters
    if self.id is None: # original draw
      self.id = self.vobject.canvas.create_polygon(self.points(fast=fast), **self.kwargs)
      self.vobject.canvas.itemconfigure(self.id, tags=[self.vobject.tag, 'vis/shape'])
    else: # a redraw
      try:
        self.vobject.canvas.coords(self.id, self.vobject.view.viewToWindow(self.points(fast=fast)))
        self.vobject.canvas.itemconfigure(self.id, **self.kwargs)
      except Exception as ex:
        raise ex
    return self.id
    
class Rectangle(Shape):
  @classmethod
  def isPublic(cls): return True


class RightParallelogram(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [self.cutIn  , 0,
        1           , 0,
        1-self.cutIn, 1,
        0           , 1]
  

class LeftParallelogram(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [0           , 0,
        1-self.cutIn, 0,
        1           , 1,
        self.cutIn  , 1]

class FileFolder(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    d = 0.3 # fraction the tab covers
    s = 0.02 # slope offset of the tab edge
    return [0,    self.cutIn,
        1-d,  self.cutIn,
        1-d+s,  0,
        1-s,  0,
        1,    self.cutIn,
        1,    1,
        0,    1]

class TopPentagon(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [0,  0+self.cutIn,
        0.5,0,
        1,  0+self.cutIn,
        1,  1,
        0,  1]

class RightPentagon(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [0      ,    0,
        1-self.cutIn,    0,
        1      ,    0.5,
        1-self.cutIn,    1,
        0      ,    1]

class LeftPentagon(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [self.cutIn, 0,
        1         , 0,
        1         , 1,
        self.cutIn, 1,
        0         ,  0.5]

class Hexagon(Shape):
  def __init__(self, vnode, cutIn=0.05, **kwargs):
    self.cutIn = cutIn
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self): 
    """
    Templates always return a list of vertex points bound by a [0,0,1,1] rectangle.
    Subclasses should override this to yield their own shape vertices.
    """
    return [self.cutIn  , 0,
        1-self.cutIn, 0,
        1           , 0.5,
        1-self.cutIn, 1,
        self.cutIn  , 1,
        0           , 0.5]

class RoundedShape(Shape):
  def __init__(self, vnode, sharpness=1.5, **kwargs):
    """
    Based on https://stackoverflow.com/questions/44099594/how-to-make-a-tkinter-canvas-rectangle-with-rounded-corners.
    """
    self.sharpness = sharpness
    if "smooth" not in kwargs:
      kwargs["smooth"] = tk.TRUE

    super().__init__(vnode, **kwargs)

  def points(self, rect:Optional[list[float]]=None, fast=False) -> list[float]: 
    sharpness = self.sharpness
    polyPoints = self.template()
    
    # The sharpness here is just how close the sub-points
    # are going to be to the vertex. The more the sharpness,
    # the more the sub-points will be closer to the vertex.
    # (This is not normalized)
    if sharpness < 1.5:
      sharpness = 1.5

    x = [] #vector of all the x coordinates
    y = [] #vector of all the y coordinates
    for i in range(0, len(polyPoints), 2):
      x.append(polyPoints[i])
      y.append(polyPoints[i+1])

    ratioMultiplier = sharpness - 1
    ratioDividend = sharpness

    # Array to store the points
    points = []

    # Iterate over the x points
    for i in range(len(x)):
      # Set vertex
      points.append(x[i])
      points.append(y[i])

      # If it's not the last point
      if i != (len(x) - 1):
        # Insert submultiples points. The more the sharpness, the more these points will be
        # closer to the vertex.
        points.append((ratioMultiplier*x[i] + x[i + 1])/ratioDividend)
        points.append((ratioMultiplier*y[i] + y[i + 1])/ratioDividend)
        points.append((ratioMultiplier*x[i + 1] + x[i])/ratioDividend)
        points.append((ratioMultiplier*y[i + 1] + y[i])/ratioDividend)
      else:
        # Insert submultiples points.
        points.append((ratioMultiplier*x[i] + x[0])/ratioDividend)
        points.append((ratioMultiplier*y[i] + y[0])/ratioDividend)
        points.append((ratioMultiplier*x[0] + x[i])/ratioDividend)
        points.append((ratioMultiplier*y[0] + y[i])/ratioDividend)
        # Close the polygon
        points.append(x[0])
        points.append(y[0])

    if rect is None:
      rect = self.vobject.boundingBox(fast=fast)
    return self.transform(rect, pointsVector=points, fast=fast) # points in WINDOW coordinates

class RoundedRectangle(RoundedShape):
  def __init__(self, vnode, sharpness=2, **kwargs):
    assert isinstance(sharpness, (float,int))
    super().__init__(vnode, sharpness, **kwargs)
    
  @classmethod
  def isPublic(cls): return True

class Oval(Shape):

  vertexCount = 24
  'Number of polygon vertices used to approximate the ellipse for points()/containsPt().'

  def __init__(self, vnode, **kwargs):
    super().__init__(vnode, **kwargs)

  @classmethod
  def isPublic(cls): return True

  def template(self):
    """
    Approximates the ellipse inscribed in the [0,0,1,1] unit square as a
    regular polygon, so that Shape.points() (and hence VObject.containsPt(),
    which calls pointInPoly() on those points) tests against something close
    to the real oval boundary.

    Without this override, Oval inherited Shape's default template() — the
    four corners of the unit square — so containsPt() on an Oval-shaped
    VObject was actually testing against its bounding *rectangle*, not the
    ellipse: a line aimed at a round node would clip to the corner of its
    invisible bounding box rather than the visible curve.

    draw() is unaffected — it still renders a true Tk oval via create_oval;
    this polygon exists only for points()/containsPt() and other
    polygon-based geometry (e.g. connectors.py's boundary clipping).

    :rtype: list[float]
    """
    n = self.vertexCount
    cx = cy = r = 0.5
    pts = []
    for i in range(n):
      theta = 2 * pi * i / n
      pts.append(cx + r * cos(theta))
      pts.append(cy + r * sin(theta))
    return pts

  def draw(self, fast=False, **kwargs) -> int|None:
    if not fast and self.checkShape(): return None
    if not fast: # first update from the GraphObject.
      self.updateKwargs() 
    self.kwargs.update(kwargs) # then from the parameters
    bb = self.vobject.boundingBox(fast=fast)
    
    if self.id is None: 
      self.id = self.vobject.canvas.create_oval(self.vobject.view.viewToWindow(bb), **self.kwargs)
      self.vobject.canvas.itemconfigure(self.id, tags=[self.vobject.tag, 'vis/shape'])
    else:
      self.vobject.canvas.coords(self.id, self.vobject.view.viewToWindow(bb))
      self.vobject.canvas.itemconfigure(self.id, **self.kwargs)
    return self.id
  

