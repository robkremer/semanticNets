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
*VObject* is the superclass of VNode, VRelation.

  .. inheritance-diagram:: VObject Cache
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Visual Attributes
^^^^^^^^^^^^^^^^^

  - name: [``str``]
  - shape: [``str``]
  - minSize: [``int``]
  - maxSize: [``int``]
  - aspectRatio: [``float``]
  - fillColor: [color]
  - borderColor: [color]
  - borderWidth: [``int``]
  - borderSmooth: [``bool``] **not implemented**
  - textColor: [color]
  - textModifiesBB: [``bool``]
  - <role>.lineColor: [color] ``Relations`` only. **not implemented**
  - <role>.fillColor: [color] ``Relations`` only. **not implemented**
  - <role>.lineWidth: [``int``] ``Relations`` only. **not implemented**
  - <role>.nearEndShape: [``str``] ``{ arrow[(<innerLen>,<outerLen>,<width>)] | circle[(radius)] }`` ``Relations`` only. **not implemented**
  - <role>.farEndShape: [``str``] ``{ arrow[(<innerLen>,<outerLen>,<width>)] | circle[(radius)] }`` ``Relations`` only. **not implemented**

----------
'''
from __future__ import annotations
from typing import Any, Optional, Union, Iterable, Callable, override, cast,\
  Iterator
from types import NoneType
import tkinter as tk
import weakref
import traceback
import itertools
from abc import abstractmethod

from util.persistence.serialize import InstantiationInfo, ParamInfo, PropertyInfo
from util.commandParser import CompositeCommandMgr
from util.persistence.pRef import PRObject, PRDb, PReference #, DeletedObjectError
from util.observer import Observer, Subject
from util.utils import removeDuplicates, tag_bindRightMouse, tag_unbindRightMouse, s_CMD, s_SHIFT,\
  expandRect, overlaps, pointInPoly, showExceptionDialog
from util.tooltip import CreateToolTip
from util.command import CommandWrapper
from util.attributeEditor import getEditedAttrsCommandObj, applyEditAttrsBox,\
  editAttrsBox
from util.abstractGraph import AGObject
from util.dirtyable import Dirtyable
from util.errorReportingObject import ErrorReportingObject

import sn
from sn import snPrefs
from sn.model import GraphObject, Relation
from sn.model.model import UP_ARROW, IsaIndividual, Node
from sn.model import names
from sn.model.constraints import WHERE, CONSTRAINTS, CONSTRAINTS_NOTE, splitWhere, mergeConstraints, ConstraintError
from util.attribute import Attribute, VAR
from sn.view.graphics.decorators import WrappingText, Selected, Highlight, ContextFrame, MarkerContainer, NOMINAL_ASPECT,\
  Decorator, ShadowDecorator, DisabledSlash

import logging
logger:sn.SNLogger = sn.getLogger(__name__)

VATTRIBUTES:dict[str,Any] = { 
                    'name'               : '', 
                    'vis/shape'          : 'Rectangle', 
                    'vis/minSize'        : 30, 
                    'vis/maxSize'        : 1000, 
                    'vis/aspectRatio'    : 0.5, 
                    'vis/fillColor'      : 'white', 
                    'vis/borderColor'    : 'black',
                    'vis/borderWidth'        : 1, 
                    'vis/borderSmooth'   : False, 
                    'vis/textColor'      : 'black', 
                    'vis/textModifiesBB' : False,
                    'vis/titlebarColor'  : '', # (a context window's title bar; "": a tint of its border colour)
                    }
VREL_ATTRIBUTES:dict[str,Any] = VATTRIBUTES | \
                  { 
                    'vis/terminator1'    : "",
                    'vis/terminator2'    : "",
                    'vis/terminator3'    : "",
                    'vis/terminator4'    : "arrow",
                    'vis/lineColor'      : "black",
                    'vis/lineFillColor'  : "black",
                    'vis/lineType'       : "smooth",
                    'vis/lineWidth'      : 1,
                    }
                    
class Cache(dict[str,Any]):
  '''
  An empty class to stuff cached attributes in. Keys are restricted to all the 
  visual attributes included in *VATTRIBUTES*. And are automatically filled from
  the owner.modelObject or the defaults in  *VATTRIBUTES*.
  
    - *_roles* : (*VRelation* only) A list of *str* names of the roles. 
    - *_<rolename>__filler*: (VRelation* only) List of fillers for each role name 
  '''
  
  def __init__(self, owner):
    '''
    ;param owner: [VObject]

    :param owner:
    :type owner:
    '''
    from sn.view.graphics.vrelations import VRelation
    super().__init__()
    assert isinstance(owner, VObject)
    self._owner:weakref.ref = weakref.ref(owner)
    self.allkeys:dict = VREL_ATTRIBUTES if isinstance(owner, VRelation) else VATTRIBUTES
    
  def refresh(self, attr:Optional[str]=None, verbose:bool=False):
    '''
    :param attr: [default=None] The name of the attribute to refresh; if *attr*
        is not already in the cache, it will be added.
        If None, refresh ALL attributes from *VATTRIBUTES* that are already in the cache.
    :type attr: Optional[str]
    :param verbose: [default=False] If True, write out all the attributes from 
        *VATTRIBUTES* that are in the cache AFTER the update has occurred.
    :type verbose: bool
        
    Update *attr* from the model object.
    '''
    if self._owner() is None: return
    owner:VObject = self._owner()
    if owner.modelObject is None: return
    
    def refreshAttr(attr:str):
      assert owner is not None
      try:
        self[attr] = owner.modelObject[attr]
      except:
        self[attr] = self.allkeys[attr]
      
    if attr is None:
      for a in self:
        refreshAttr(a)
    else:
      refreshAttr(attr)
    if verbose:
      buf = ""
      for a in self:
        buf += f'{a}: {self[a]}\n'
      logger.info(buf)
      
  def __getitem__(self, key:str) -> Any:
    '''
    :param key:
    :type key: str
    :returns:
    :rtype: Any
    '''
    assert key in self.allkeys
    try:
      ret = super().__getitem__(key)
    except:
      self.refresh(key)
      try:
        ret = super().__getitem__(key)
      except:
        ret = self.allkeys[key]
    if key.endswith("Color") and ret: # (an inferred object's look: its own, faded -- see VObject.isInferred())
      owner = self._owner()
      if owner is not None and owner.isInferred():
        return fadeColor(owner.canvas, ret)
    return ret
      
  def __setitem__(self, key:str, val:Any) -> None:
    '''
    :param key:
    :type key: str
    :param val:
    :type val: Any
    '''
    assert key in self.allkeys
    super().__setitem__(key, val)
    
  def __contains__(self, key:str) -> bool:
    '''
    :param key:
    :type key: str
    :returns:
    :rtype: bool
    '''
    return key in self.allkeys
      

INFERRED_FADE = 0.4
"How much of its own colours an inferred object keeps (see *fadeColor()*): the rest is the canvas's background."

def fadeColor(canvas, color:str, amount:float=INFERRED_FADE) -> str:
  '''
  *color* faded toward *canvas*'s background: *amount* of the colour (1: the
  colour; 0: the background).

  :param canvas: A Tk canvas (or anything with *winfo_rgb()* and *cget("background")*).
  :type canvas:
  :param color: A Tk colour.
  :type color: str
  :param amount: How much of *color* to keep.
  :type amount: float
  :returns: The faded colour, as "#rrggbb" (*color* if it can't be read).
  :rtype: str
  '''
  try:
    fg = canvas.winfo_rgb(color)
    bg = canvas.winfo_rgb(canvas.cget("background"))
  except Exception:
    return color
  mix = [int((f * amount + b * (1 - amount)) / 257) for f, b in zip(fg, bg)]
  return "#{:02x}{:02x}{:02x}".format(*mix)

class VObject(AGObject["SNGView", "VRelation"], Observer, Dirtyable, ErrorReportingObject):
  '''
  An object that visually represents some object in a tygra *Model* that resides
  in a particular *SNCanvas* (which may include VObjects representing objects in
  several different tygra *Model* objects).
  
  The "size" and location of *VObject* considered to be that of the *self._shape*
  object, which in turn is controlled by the *self.boundingBox()* method. Note
  that decorators may be drawn outside of this bounding box.
  '''

  _tagCounter = itertools.count(1)
  "Source of unique canvas tags (see *self.tag*)."

  def __init__(self, view:"SNGView", modelObject:GraphObject|str,
               shape:Union[Any,str]="Rectangle",
               x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None,
               **kwargs):
    '''
    :param view: The SNGView object that "owners" this VObject.
    :type view: SNGView
    :param modelObject: The object in the model that this object represents.
    :type modelObject: GraphObject | str
    :param shape: [Union[tygra.view.shapes.Shape, str], default=...shapes.Rectangle] The basic shape of this object.
    :type shape: Union[Any, str]
    :param x: The upper left corner x coordinate
    :type x: Optional[int]
    :param y: The upper left corner y coordinate
    :type y: Optional[int]
    :param x1: The lower right corner x coordinate
    :type x1: Optional[int]
    :param y1: The lower right corner y coordinate
    :type y1: Optional[int]
    :param kwargs: Passed on to *super().__init__()*. *VObject* is normally
      combined with *AGRelation* via multiple inheritance (see *VRelation*),
      and the two share *AGObject* as a common ancestor -- calling *super()*
      cooperatively here (instead of separately naming *AGObject* and
      *PRObject*, as this used to) ensures that shared ancestor's *__init__*
      -- which registers this object with *view* -- runs exactly once no
      matter which subclass is being constructed, rather than once per
      inheritance path. *kwargs* is how *AGRelation*'s own *src*/*dst*
      constructor arguments -- which *VObject* has no use for itself -- get
      carried through to it along that same chain.
    :type kwargs: Any
    '''
    from sn.view.graphics.shapes import Shape
    from sn.view.graphics.vrelations import VRelation
    from sn.view.graphics.sngView import SNGView

    #check parameters
    assert isinstance(view, SNGView), f'Expecting SNGView type, got {type(SNGView)}'
    if isinstance(modelObject, str):
      self.readModelObjectRef:str = modelObject
      try:
        obj = PReference[GraphObject](modelObject)(relativeTo=view.model)
      except KeyError:
        obj = None
      modelObject = obj # type: ignore[assignment]
    assert isinstance(modelObject, (GraphObject,NoneType))
    assert isinstance(shape, (Shape,str)), f'Expected Shape or str, but got "{shape.__class__.__name__}"'

    # Set up the reference model object and it's cached details.
    # This needs to be done BEFORE super constructors are called in the case
    # of VRelations to prevent recursively calling this constructor.
    self._modelObject:GraphObject|None = modelObject

    self.cache:Cache = Cache(self)
    
    m = self._modelObject
    if m is not None:
      # these act as a cache, as it's relatively expensive to look up these values in the model object.
      self.cache['name'] = m.name
      for attrName, default in VATTRIBUTES.items():
        setattr(self.cache, attrName, m.get(attrName, default))      

    self.view:SNGView = view
    view.structureChanged()

    # *AGObject* is a common ancestor shared with *AGRelation* whenever this
    # is actually a *VRelation* (see that class's __init__ for the full
    # explanation of the diamond). This single cooperative super().__init__()
    # call reaches AGObject.__init__() -- and hence PRObject.__init__(),
    # which registers this object with *view* -- exactly once, however many
    # inheritance paths lead here. It used to be followed by a second,
    # separate PRObject.__init__(self, view) call further down (plus explicit
    # Dirtyable.__init__(self)/Observer.__init__(self) calls) -- that separate
    # call was the actual double-registration bug: every VObject was already
    # affected, not just VRelation, since Dirtyable/Observer are also reached
    # automatically via this same chain.
    super().__init__(db=view, **kwargs)
    assert self._id is not None
    
    if x  is None: x  = 0
    if y  is None: y  = 0
    if x1 is None: x1 = int(self.cache["vis/minSize"])
    if y1 is None: y1 = int(self.cache["vis/minSize"] * (self.cache["vis/aspectRatio"] or NOMINAL_ASPECT)) # aspectRatio is height/width
    assert isinstance(x , int) and not isinstance(x , bool)
    assert isinstance(y , int) and not isinstance(y , bool)
    assert isinstance(x1, int) and not isinstance(x1, bool)
    assert isinstance(y1, int) and not isinstance(y1, bool)
      
    self._drawVersion:int = -1
    self._boundingBox = [x, y, x1, y1]

    self.canvas:tk.Canvas = view.canvas
    self._updatingFromAttrs = False
    self.tooltip = None
    self.markerDecoratorOffset=0
    self.dragInfo = None
    self._deleted = False
    self._hidden = False
    self.userSized:bool = False
    "True once the user has sized the box by hand: it's then no longer fitted to its text (see *WrappingText.fitOwner()*) until \"fit to text\"."
    self.resizeInfo:tuple|None = None
    "While a corner handle is being dragged: (fixed opposite corner (view coords), bounding box before, userSized before)."

    if isinstance(shape, str):
      try:
        shape = self.strToShape(shape)
      except Exception as ex:
        logger.warning(f'Unknown shape "{shape}" in {self.__class__.__name__} constructor for object {self}. Using "RoundedRectangle" (exception="{ex}"')
        shape = self.strToShape("RoundedRectangle")
    assert isinstance(shape, Shape)
    self._shape = shape
    self.tag = f"VO{next(VObject._tagCounter)}"
    "This object's canvas tag: every canvas item drawn for it carries it. Deliberately NOT derived from *self._id*, which loading a view from a file may change after construction."
    
    # self.relations:list[VRelation] = []
    # 'CAUTION: This list of referenced relations MUST have exactly a one-to-one relation with every connecting role of every connecting relation.'
    
    self.decorators:dict[str, Decorator] = dict()
    self.makeDecorators()
    
    if self.modelObject is not None:
      self.modelObject.addObserver(self)
    # if _id is None: # being created by the user (not reading from persistent store)
    #   self._post__init__()
    
    self.validate()
    
    self.canvas.after(0, self._firstDraw)

  def _firstDraw(self) -> None:
    '''
    Draw this new object for the first time, and make its bindings: queued by
    the constructor, as it may be inside another object's construction. If it
    has been taken out of the view meanwhile (eg: erased by a category before
    the queue got to it), it isn't drawn now -- that would put it back on the
    canvas, though it isn't in the view -- but when it's put back (see
    *_reconnect()*).
    '''
    if not self._isConnected():
      self.__dict__["_firstDrawPending"] = True
      return
    self.__dict__["_firstDrawPending"] = False
    self.view.freshPaint()
    self.draw()
    self.makeBindings()
    
  # def _post__init__(self):
  #   self.view.freshPaint()
  #   self.draw()
  #   self.makeBindings()
  #   #self.adjustPos()
    
  # ---- PERSISTENCE -----------------------------------------------------------
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    from sn.view.graphics.sngView import SNGView
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("view", SNGView, lambda slf: cast(VObject, slf).view),
                     ParamInfo("modelObject", str, lambda slf: slf.modelObject.getPRef().tostring(slf.view.model))], #type: ignore[attr-defined]
            conKWArgs=[ParamInfo("x", int, lambda slf: int(slf.boundingBox()[0])), #type: ignore[attr-defined]
                       ParamInfo("y", int, lambda slf: int(slf.boundingBox()[1])), #type: ignore[attr-defined]
                       ParamInfo("x1", int, lambda slf: int(slf.boundingBox()[2])), #type: ignore[attr-defined]
                       ParamInfo("y1", int, lambda slf: int(slf.boundingBox()[3]))], #type: ignore[attr-defined]
            postconSetters=[PropertyInfo("userSized", bool,
                                         lambda slf: bool(getattr(slf, "userSized", False)),
                                         lambda slf, v: setattr(slf, "userSized", bool(v)),
                                         optional=True), # optional: views saved before it existed still load
                            PropertyInfo("collapsed", bool,
                                         lambda slf: bool(getattr(slf, "collapsed", False)),
                                         lambda slf, v: setattr(slf, "collapsed", bool(v)),
                                         optional=True),
                            PropertyInfo("expandedHeight", int,
                                         lambda slf: int(getattr(slf, "expandedHeight", None) or 0),
                                         lambda slf, v: setattr(slf, "expandedHeight", int(v) or None),
                                         optional=True)],
            finalSetters=[]
            )

  # ---- GETTERS AND SETTERS ---------------------------------------------------

  @property
  @override
  def name(self)->str:
    '''
    :returns:
    :rtype: str
    '''
    n = "?" if self.modelObject is None else self.modelObject["name"]
    return str(n)
    # assert n is None or type(n) is str, f'Expecting type str|None, got {n.__class__.__name__}'
    # return "" if n is None else n
    
  @property
  def modelObject(self) -> GraphObject|None:
    '''
    :returns: The corresponding model object.
    :rtype: GraphObject
    :raises ReferenceError: if there is not corresponding model object (deleted?)
    '''
    # try:
    #   ret:GraphObject|None = self._modelObject
    #   assert isinstance(ret, GraphObject)
    # except:
    #   logger.exception("Can't access model object.")
    #   ret = None
    # if ret is None:
    #   raise ReferenceError("model object not found.")
    # return ret
    return self._modelObject
  
  @property
  def relations(self) -> Iterator[VObject]:
    '''
    :returns:
    :rtype: Iterator[VObject]
    '''
    for vo in self._incoming + self._outgoing:
      yield vo
        
  def delete(self):
    """Removes this Node from the display, removing it from canvas's list."""
    if self._deleted:
      return
    self._deleted = True
    
    # # this check is necessary because the node being deleted might be a label for an relation
    if self in self.canvas.nodes():
      self.canvas.remove(self._id)
    count = self.modelObject.detach(self) # remove self from observers of the model object
    assert count > 0

    # remove all decorators
    keys = []
    for k in self.decorators: keys.append(k)
    for k in keys: 
      try: self.removeDecorator(key=k)
      except: pass

    # notify all VRelations
    for r in self.relations.copy():
      try: r.notifyNodeDeletion(self)
      except: pass
    self.relations = None
      
    if self._shape.id is not None:
      self.killBindings()
      self._shape.delete()

    self._shape = None
    self.decorators = None
    self.dragInfo = None

    if self in self.canvas.values():
      self.canvas.remove(self._id)
      
    self.cache = None
#    super().delete()

  def boundingBox(self, rect:list[int]=None, fast=False) -> list:
    '''
    Returns or sets the bounding box for the *VObject* in [minX, minY, maxX, maxY]
    form.  Checks *rect* for sanity (coordinates may be negative: the canvas
    extends every way -- see *SNGView.resetScrollRegion()*).
    
    The bounding box is strictly tracked by the *self.shape()* object. Thus, if 
    you change the boundingBox, this method assures that shape object tracks it
    (along with any decorators).

    :param rect:
    :type rect: list[int]
    :param fast:
    :type fast:
    :returns:
    :rtype: list
    '''
    if rect != None and rect != self._boundingBox:
      assert len(rect) == 4
      for i in range(4): # check type
        rect[i] = int(rect[i]) # assure rect is all ints
      if rect[0] >= rect[2]: # make sure x1 < x2
        z = rect[0]
        rect[0] = rect[2]
        rect[2] = z 
      if rect[1] >= rect[3]: # make sure y1 < y2
        z = rect[1]
        rect[1] = rect[3]
        rect[3] = z 
      # No clamp at any edge of the scroll region: objects may be moved (eg:
      # dragged) past it, and draw() then grows the region to include them
      # (see SNGView.resetScrollRegion()).
      self._boundingBox = rect.copy()
    
      if not fast:
        # Only minimums are enforced here: fitting the box to its text within
        # vis/maxSize and near vis/aspectRatio is WrappingText.fitOwner()'s job,
        # and a box deliberately sized otherwise (eg: resized by the user) must
        # be allowed to keep its shape.
        bb = self._boundingBox
        minX = self.cache['vis/minSize']
        if bb[2]-bb[0] < minX:
          bb[2] = bb[0]+minX
        minY = self.minHeight()
        if bb[3]-bb[1] < minY:
          bb[3] = bb[1]+minY
      
      # self.view.freshPaint()
      # self.draw()
      self.setDirty()

    return self._boundingBox

  def isHidden(self) -> bool:
    '''
    True iff this isn't drawn just now: it's in a hidden category (see
    *SNGView.visibility()*), or depends on something that is, or goes without
    saying (eg: a containment drawn as being inside a window). See
    *SNGView.shouldHide()*.

    :returns:
    :rtype: bool
    '''
    return self._hidden

  def _applyHidden(self) -> None:
    '''
    Show or hide all of this one's canvas items according to
    *SNGView.shouldHide()*; if that changes, the relations to and from it (and
    a window's contents) follow suit.
    '''
    if not self._isConnected() or self.canvas is None:
      return
    hide = self.view.shouldHide(self)
    c = self.canvas
    if hide:
      self._hideItems()
    else:
      self._showItems()
    if hide != self._hidden:
      self._hidden = hide
      if hide and self.selected():
        self.selected(False)
      dependents = [r for r in self.relations if r is not self]
      if self.isContextWindow():
        dependents += self.windowContents()
      c.after_idle(lambda: [d._applyHidden() for d in dependents if d._isConnected()])

  def _hideItems(self) -> None:
    '''
    Hide all this one's canvas items, noting each one's state first (some are
    deliberately "disabled"), for *_showItems()*. The note is kept here, not
    as canvas tags: redraws reset items' tags (eg: connectors.\\_upsertLine()).
    '''
    c = self.canvas
    prior:dict[int, str] = self.__dict__.setdefault("_priorStates", {})
    for i in c.find_withtag(self.tag):
      state = c.itemcget(i, "state")
      if state != "hidden":
        prior[i] = state
        c.itemconfigure(i, state="hidden")

  def _showItems(self) -> None:
    '''
    Undo *_hideItems()*: every hidden item of this one's goes back to its noted
    state (items made while hidden were noted when they were hidden). Nothing
    else hides a VObject's items, so all of them are shown.
    '''
    c = self.canvas
    prior:dict[int, str] = self.__dict__.get("_priorStates", {})
    for i in c.find_withtag(self.tag):
      if c.itemcget(i, "state") == "hidden":
        c.itemconfigure(i, state=prior.get(i, ""))
    prior.clear()

  def labelText(self) -> str:
    '''
    What this one's label says: its label template (see *labels*) expanded --
    its "vis/label" attribute if it has one, else the "gui/label" preference
    ("gui/relationLabel" for relations). A template that can't be expanded
    gives the name, with a warning.

    :returns:
    :rtype: str
    '''
    from sn.view.graphics.labels import expand, labelLookup, DEFAULT_LABEL, TemplateError
    mo = self.modelObject
    if mo is None:
      return "?"
    template = mo.get("vis/label", None)
    if not isinstance(template, str) or not template:
      pref = "gui/relationLabel" if isinstance(mo, Relation) else "gui/label"
      template = snPrefs.get(pref, storeDefault=DEFAULT_LABEL, storeType=str) # (its note: see sn.PREFS)
    try:
      return expand(str(template), labelLookup(mo)).strip()
    except TemplateError as ex:
      logger.warning(f'{mo.name}: bad label template: {ex}')
      return (mo.name or "").strip()

  categoryExempt:bool = False
  '''
  Shown although it's in a hidden category (see *SNGView.visibility()*): it was
  made (or shown explicitly) since the category was hidden. Hiding the category
  again hides it too.
  '''
  collapsed:bool = False
  "A context window shown as just its title bar (see *setCollapsed()*)."
  expandedHeight:int|None = None
  "A collapsed context window's height when it's expanded again."
  TOGGLE_WIDTH = 18
  "The width of a context window's collapse/expand triangle, at the left of its title bar."

  def fullBoundingBox(self) -> list:
    '''
    The bounding box -- as it is when expanded, for a collapsed context window (see *setCollapsed()*).

    :returns:
    :rtype: list
    '''
    bb = list(self.boundingBox())
    if self.collapsed:
      bb[3] = bb[1] + (self.expandedHeight or self.WINDOW_DEFAULT[1])
    return bb

  def toggleAt(self, x:float, y:float) -> bool:
    '''
    Whether (x, y) (view coords) is on a context window\'s collapse/expand triangle.

    :param x:
    :type x: float
    :param y:
    :type y: float
    :returns:
    :rtype: bool
    '''
    if not self.isContextWindow():
      return False
    x1, y1, _, _ = self.boundingBox()
    return x1 <= x <= x1 + self.TOGGLE_WIDTH and y1 <= y <= y1 + self.bannerHeight()

  def setCollapsed(self, collapsed:bool) -> None:
    '''
    Show a context window as just its title bar (*collapsed*), or in full. What
    it contains that's drawn inside it is hidden while it's collapsed (and moves
    with it); what it contains that's outside it stays, with its arcs to the
    title bar -- eg: a query's subject, out in the world. See
    *SNGContext.collapse()* for the undoable command.

    :param collapsed:
    :type collapsed: bool
    '''
    if collapsed == self.collapsed or not self.isContextWindow():
      return
    x1, y1, x2, y2 = self.boundingBox()
    if collapsed:
      self.expandedHeight = int(y2 - y1)
      self.collapsed = True
      self.reshape([x1, y1, x2, y1 + self.bannerHeight()])
    else:
      self.collapsed = False
      self.reshape([x1, y1, x2, y1 + (self.expandedHeight or self.WINDOW_DEFAULT[1])])
    self.view.applyVisibility()

  WINDOW_MIN = (160, 100)
  "The smallest a context window may be (view units)."
  WINDOW_DEFAULT = (320, 200)
  "A context window's size when it's first drawn (as a window)."
  BANNER = 18
  "The height (view units) of a context window's title banner."

  def isInferred(self) -> bool:
    '''
    True iff this shows something the reasoner concluded, not asserted (see
    *GraphObject.inferred*): it's drawn in its usual look, faded (see
    *fadeColor()*), and isn't saved with the view.

    :returns:
    :rtype: bool
    '''
    return bool(getattr(self.modelObject, "inferred", False))

  def isContextWindow(self) -> bool:
    '''
    True iff this is drawn as a window: an individual context -- a rule,
    query, ... (not the context/rule/query types themselves). See
    *decorators.ContextFrame*.

    :returns:
    :rtype: bool
    '''
    mo = self.modelObject
    try:
      if mo is None or not mo.isIndividual():
        return False
      # Asked very often (see SNGView.contextWindows(): for every object, each
      # time one is drawn), and isa() walks all the ancestors: so remembered,
      # for as long as the object's own types are the same. (Not noticed: an
      # ancestor further up made a kind of context meanwhile -- rare.)
      key = tuple(id(p) for p in mo.getParents())
      cached = self.__dict__.get("_contextWindowCache")
      if cached is not None and cached[0] == key:
        return cached[1]
      ret = mo.isa(mo.model.CONTEXT)
      self.__dict__["_contextWindowCache"] = (key, ret)
      return ret
    except Exception: # (eg: during construction)
      return False

  def bannerHeight(self) -> float:
    '''
    :returns:
    :rtype: float
    '''
    return self.BANNER

  def panes(self) -> dict[str, list[float]]:
    '''
    A context window's content areas (view coords), below its banner, by the
    containment relation they stand for: a rule's "antecedent" (left) and
    "consequent" (right); a definition's "definiendum" (left: the term
    defined) and "definiens" (right: its meaning); a requirement's
    "condition" (left) and "required" (right); any other context's single
    "contains" area.

    :returns:
    :rtype: dict[str, list[float]]
    '''
    x1, y1, x2, y2 = self.fullBoundingBox() # (a collapsed window's contents are still in it)
    top = y1 + self.bannerHeight()
    mo = self.modelObject
    for kind, (left, right) in (("RULE", ("antecedent", "consequent")), ("DEFINITION", ("definiendum", "definiens")),
                                ("REQUIREMENT", ("condition", "required"))):
      if mo is not None and mo.isa(getattr(mo.model, kind)):
        mid = (x1 + x2) / 2
        return {left: [x1, top, mid, y2], right: [mid, top, x2, y2]}
    return {"contains": [x1, top, x2, y2]}

  def paneAt(self, pt) -> str|None:
    '''
    The pane (see *panes()*) that the point *pt* (view coords) is in, or None.

    :param pt:
    :type pt:
    :returns:
    :rtype: str | None
    '''
    for name, (x1, y1, x2, y2) in self.panes().items():
      if x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2:
        return name
    return None

  def containmentOf(self, obj) -> list:
    '''
    The model relations by which this context contains *obj* (a model object).

    :param obj:
    :type obj:
    :returns:
    :rtype: list
    '''
    mo = self.modelObject
    if mo is None or obj is None:
      return []
    contains = mo.model.CONTAINS
    return [r for r, _ in mo._getOutgoing(lambda r: r.isIndividual() and r.isa(contains) and r.localDst is obj)]

  def windowContents(self) -> list[VObject]:
    '''
    The view objects this context contains that sit inside its window.

    :returns:
    :rtype: list[VObject]
    '''
    mo = self.modelObject
    if mo is None or not self.isContextWindow():
      return []
    contains = mo.model.CONTAINS
    ret:list[VObject] = []
    for r, _ in mo._getOutgoing(lambda r: r.isIndividual() and r.isa(contains)):
      vo = self.view.findViewObjectForGraphObject(r.localDst) if r.localDst is not None else None
      if vo is not None and vo is not self and vo not in ret and vo._isConnected() and self.paneAt(vo.centerPt()) is not None:
        ret.append(vo)
    return ret

  def carriedContents(self) -> list[VObject]:
    '''
    What moves with this context window when it's moved (see *moveTo()*): what
    belongs in it (see *SNGView.containmentHomes()*: what it contains, and the
    variables its contents use -- eg: a base rule's !a and !b), and anything
    else of what it contains that's drawn inside it (eg: a label placed by
    hand) and doesn't belong in another window.

    :returns:
    :rtype: list[VObject]
    '''
    if not self.isContextWindow():
      return []
    homes = self.view.containmentHomes()
    ret = [vo for vo, (w, _) in homes.items() if w is self]
    return ret + [vo for vo in self.windowContents() if vo not in homes and vo not in ret]

  def isResizable(self) -> bool:
    '''
    False iff "vis/minSize" == "vis/maxSize": the size is fixed, so it can\'t be resized by hand. (Windows always can be.)

    :returns:
    :rtype: bool
    '''
    return self.isContextWindow() or self.cache['vis/minSize'] != self.cache['vis/maxSize']

  def minHeight(self) -> float:
    '''
    The smallest height (view units) the bounding box may have: "vis/minSize" *
    "vis/aspectRatio" (*NOMINAL_ASPECT* if that's 0), but never less than one
    line of text.

    :returns:
    :rtype: float
    '''
    ret = self.cache['vis/minSize'] * (self.cache['vis/aspectRatio'] or NOMINAL_ASPECT)
    text = self.decorators.get("text") if getattr(self, "decorators", None) else None
    if isinstance(text, WrappingText) and self.modelObject is not None:
      ret = max(ret, text.lineHeight())
    return ret

  def shape(self, c:str=None):
    '''
    :param c: [str, default=None] The name of the new shape.
    :type c: str
    :return: [str] The name of this object's (possibly changed) shape.
    :rtype:
    :except Exception: if *c* is not the name of a known shape.
    
    If *c* is given, make self's shape the corresponding *Shape*. 
    
    Used by draw() when the shape is changed.
    '''
    if c is not None and c != type(self._shape).__name__:
      newShape = None
      try:
        newShape = self.strToShape(c)
      except Exception as ex:
        self.canvas.logger.write(f'Shape "{c}" is not known.', level="warning", exception=ex)
      if newShape is not None:
        self.killBindings()
        oldShape = self._shape
        self._shape = newShape
        self._shape.draw()
        self.canvas.lift(newShape.id, oldShape.id)
        oldShape.delete()
        #self.updateFromAttrs(['vis/fillColor', 'vis/borderColor'])
        self.makeBindings()
      self.setDirty()
    return type(self._shape).__name__ if self._shape is not None else None
  
  # ---- OBSERVER INTERFACE ----------------------------------------------------
    
  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]]) -> None:
      """
      Receive update from subject.

      :param subject:
      :type subject: Subject
      :param topics:
      :type topics: tuple[str, tuple[Any, ...]]
      """
      if getattr(self.view, "_closed", False): # (sent before the view's window closed: see SNGView.detachFromModel())
        return
      rm = False # flag for checking if "rm" is one of the topics
      try: # if this is a deletion, the object will fail validation on access
        assert subject is self.modelObject
      # except DeletedObjectError as ex:
      #   #assert subject is self._modelObject() #access without the checks
      #   #subject = subject()
      #   rm = True
      #   rmEx = ex
      except Exception as ex:
        logger.exception(f'{self.name}.update({subject}, {topics}): Unexpected subject.')
        return
      #logger.info(f"VObject.update({subject}, {topics}): executing.")
      vChanged = False
      for topic in topics:
        topicName = topic[0]
        if topicName == "new attribute" or topicName == "mod attribute": # no point in changing an object we're removing!
          attname, value = topic[1]
          if attname in VATTRIBUTES:
            #self.cache.refresh(attname)
            self.cache[attname] = value
            vChanged = True
          else: # (the label may show any attribute: see labelText())
            vChanged = True
        elif topicName == "del attribute":
          attname = topic[1][0]
          if attname in VATTRIBUTES:
            self.cache.refresh(attname)
          vChanged = True # (the label may show any attribute: see labelText())
          
        elif topicName in ("asserted", "inferred"): # (marked as asserted, or that undone: drawn faded or not -- see isInferred())
          vChanged = True
        elif topicName == "mod individual": # (made a type, or an individual: what it inherits may differ, and it may be in a hidden category now)
          self.cache.refresh()
          self.view._exemptIfFiltered(self)
          vChanged = True
        elif topicName == "rm":
          #self.canvas.remove(self._id)
          self.delete()
          rm = False
          break
        else:
          logger.warning(f'{self.name}: Unknown update({self.modelObject.name}, {topic})')
        
      
      # if rm: # we had a DeletedObjectError WITHOUT a "rm" topic -- something's wrong
      #   raise rmEx # is only in scope if rm is True
            
      if vChanged:
        self.view.freshPaint()
        self.draw() 

  def validate(self) -> list[str]:
    '''
    Populates (or clears) the *self.errors* list.

    :returns:
    :rtype: list[str]
    '''
    try:
      self.assertToStatusReport(self.modelObject is not None, 
        f'Model object is missing from Model: {self.readModelObjectRef if hasattr(self, "readModelObjectRef") else ""}', "E", 
        actions={"erase view object": lambda: [self._disconnect(), self.view.setDirty(), self.delete(), None][-1]}) #check model object is there.
      if self.modelObject is not None:
        model:GraphObject = self.modelObject
        for n in self.view.values(): # check for other objects referencing this one's model object
          if n is not self and n.modelObject is self.modelObject: # (the message only when it's needed: it's costly, and this is done for every object in the view)
            self.assertToStatusReport(False,
              f'View objects {self} and {n} both reference the same model object {self.modelObject}.', 'E', dict())
        model.clearStatusReport()
        model.validate()
        self._statusReport += model._statusReport
        self._addReasonerFindings()
    except Exception as ex:
      trace = traceback.format_exc()
      self.assertToStatusReport(False, 
          f'Unexpected exception during valication: {ex.__class__.__name__}: {ex}', 'E',
          {"view trace": lambda trace=trace, ex=ex: showExceptionDialog(self.canvas.winfo_toplevel(), name=ex.__class__.__name__, text=trace)})
    return self.statusReport()
    
  def _addReasonerFindings(self) -> None:
    '''
    Add the violations the view's last "reason" found for this object's model
    object (see *SNGView.reason()*) to the status report, with a one-click fix
    where there's an obvious one.
    '''
    reasoning = getattr(self.view, "reasoning", None)
    if reasoning is None or self.modelObject is None:
      return
    for v in reasoning.violationsFor(self.modelObject):
      actions:dict[str, Callable[[], None]] = {}
      if v.code in ("domain", "range"): # args: (relation type, endpoint, required type)
        _t, obj, required = v.args
        if obj.isIndividual() or not obj.isa(required):
          actions[f'make "{obj.name}" a "{required.name}"'] = \
            lambda o=obj, c=required: self.view.context.new_relation([self.view.model.ISA], individual=True,
                                                                      source=o, destination=c, model=self.view.model)
      if v.code == "variable_kind": # args: (the kind its name says, ...): make it that kind, or rename it for the kind it is
        actions.update(self._variableKindFixes(str(v.args[0]) == "individual"))
      self.assertToStatusReport(False, f'reasoner: {v.message}', "E" if v.severity == "error" else "W", actions)

  def _variableKindFixes(self, namedIndividual:bool) -> dict[str, Callable[[], None]]:
    '''
    The fixes for a variable whose name says it matches individuals (if
    *namedIndividual*; else types) but that's the other kind: make it the kind
    its name says (see *GraphObject.individualChangeProblem()*), or rename it
    for the kind it is (eg: ?x, a type, to ^x). Each is undoable, and the
    model's reasoned over again (silently) afterwards, so the warning goes.

    :param namedIndividual:
    :type namedIndividual: bool
    :returns: label -> action.
    :rtype: dict[str, Callable[[], None]]
    '''
    from sn.model import names
    mo = self.modelObject
    ret:dict[str, Callable[[], None]] = {}
    def then(fix:Callable[[], Any]) -> Callable[[], None]:
      def go() -> None:
        try:
          fix()
        except Exception as ex:
          logger.error(f'{mo.name}: {ex}')
          return
        self.view.reasonSilently()
      return go
    if mo is None or mo.model.writeLocked():
      return ret
    if mo.individualChangeProblem(namedIndividual) is None:
      ret[f'make it {"an individual" if namedIndividual else "a type"}'] = \
        then(lambda: self.view.context.set_kind(mo, "individual" if namedIndividual else "type"))
    prefixes = {kind: p for p, kind in getattr(names.grammar, "PREFIXES", {}).items()} # (the default grammar's: see names.NameGrammar)
    prefix = prefixes.get(names.NameKind.INDIVIDUAL if mo.isIndividual() else names.NameKind.TYPE)
    if prefix is not None:
      newName = prefix + names.stem(mo.name)
      ret[f'rename it {newName}'] = then(lambda: self.view.context.set_attribute(mo, "name", newName))
    return ret

  # ---- BINDINGS --------------------------------------------------------------
  
  def makeBindings(self):
    bindObj = self.tag #bindObj
    tag_bindRightMouse(self.canvas, bindObj, self.onRightMouse)
    self.canvas.tag_bind(bindObj, "<Button-1>", self.onButton_1)
    self.canvas.tag_bind(bindObj, "<B1-Motion>", self.onB1_Motion)
    self.canvas.tag_bind(bindObj, "<B1-ButtonRelease>", self.onB1_ButtonRelease)
    self.canvas.tag_bind(bindObj, "<Double-Button-1>", self.onDouble_1)
    self.canvas.tag_bind(bindObj, "<Enter>", self.onEnter)
    self.canvas.tag_bind(bindObj, "<Leave>", self.onLeave)
  # self.tooltip = CreateToolTip(self.canvas, self.tooltipFunc, bindObj, 
    #                              waitTime=1000, wrapLength=250, background="#FFFFC0")
    self.tooltip = CreateToolTip(self.canvas, self.tooltipFunc, self._shape.id, 
                                 waitTime=1000, wrapLength=250, background="#FFFFC0")
    
  def killBindings(self):
    bindObj = self.tag #bindObj
    tag_unbindRightMouse(self.canvas, bindObj)
    self.canvas.tag_unbind(bindObj, "<Button-1>")
    self.canvas.tag_unbind(bindObj, "<B1-Motion>")
    self.canvas.tag_unbind(bindObj, "<B1-ButtonRelease>")
    self.canvas.tag_unbind(bindObj, "<Double-Button-1>")
    if self.tooltip is not None:
      self.tooltip.delete()
      
  def onEnter(self, event):
    '''
    :param event: The Tk event.
    :type event:
    '''
    self.canvas.configure(cursor="hand")
    
  def onLeave(self, event):
    '''
    :param event: The Tk event.
    :type event:
    '''
    self.canvas.configure(cursor="arrow")
    
  def onRightMouse(self, event):
    """
    Creates and displays the node specific menu at the clicked location -- or,
    in the body of a (expanded) context window, the menu for making things in
    the pane clicked in (see *SNGView.addNewObjectMenus()*), as the
    background's makes them there: the window's own menu is on its title bar.

    :param event: The Tk event.
    :type event:
    :returns:
    :rtype:
    """
    self.view.addEventHandled(event)
    pt = self.view.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    pane = self.paneAt(pt) if self.isContextWindow() and not self.collapsed and self.view.isModelEditor() else None
    if pane is not None:
      m = tk.Menu(self.canvas)
      self.view.addNewObjectMenus(m, (pt[0], pt[1]), into=(self, pane))
    else:
      m = self.makeMenu()
    m.post(event.x_root, event.y_root)
    return 'break'

  def onButton_1(self, event): #get initial location of object to be moved
    """
    The mouse clicked on this node, so begin a mouse event capture. We will
    decide on if it's just a node move or a selection toggle in *self.onB1_Motion()*
    and *self.onB1ButtonRelease()*.

    :param event: The Tk event.
    :type event:
    :returns:
    :rtype:
    """
    # A context window's collapse/expand triangle
    if self.toggleAt(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)):
      self.view.addEventHandled(event)
      self.dragInfo = None
      self.view.context.collapse(self, not self.collapsed)
      return 'break'
    # A corner handle of a selected object: resize just this object.
    sel = self.decorators.get("selected")
    if isinstance(sel, Selected):
      corner = sel.handleAt(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
      if corner is not None:
        self.view.addEventHandled(event)
        self.dragInfo = None
        self._startResize(corner)
        return 'break'
    # A relation's terminal sits right on the edge of the object it connects,
    # so a press meant for the terminal usually lands on something else: this
    # object, or -- inside a context window -- the window. Whatever's under it,
    # a press within reach of a terminal grabs it: the same test that shows the
    # terminal cursor (see SNGView._relationTerminalNear()), so where the cursor
    # says a terminal can be dragged, it can.
    if self.view.grabTerminalNear(event):
      return 'break'
    self.view.addEventHandled(event)
    #print(f'onButton_1() event x={event.x}, y={event.y}, selected={self.selected()}')
    winX = self.canvas.canvasx(event.x) # convert widget-relative coords to canvas coords (accounts for scroll position)
    winY = self.canvas.canvasy(event.y)
    r = self.boundingBox()
    self.dragInfo = (r[0], r[1], winX, winY, False) # x,y,no-drag-motion-event
    # Record each object this drag might move's TRUE starting position, right
    # now before any <B1-Motion> tick has touched anything. onB1_Motion()
    # moves every object in self.view.selected (or just self) via direct
    # moveBy() calls that bypass the Command system entirely, so by the time
    # onB1_ButtonRelease() commits a _Move (on release), boundingBox() already
    # reflects where the drag ENDED, not where it started -- see _Move's own
    # oldPos docstring in sngView.py. Capturing it here and threading it
    # through to _Move(oldPos=...) is what lets undo() restore the whole
    # move, not just its last FindFree-driven leg.
    movedSet = self.view.selected if self.selected() else [self]
    self.dragStartPositions:dict["VObject", list[int]] = {n: n.boundingBox() for n in movedSet}
    # where the moved objects, and the relations they drag along, were -- to
    # tell what's been dropped into or dragged out of a context window (see
    # SNGView._updateContainment())
    self.dragStartCenters:dict["VObject", tuple] = {}
    self.dragAlong:set["VObject"] = set()
    "The relations that only move because their ends do."
    for n in movedSet:
      for vo in [n, *([] if n.isContextWindow() else n.relations)]:
        self.dragStartCenters.setdefault(vo, vo.centerPt())
        if vo is not n and vo not in movedSet:
          self.dragAlong.add(vo)
    self.old_suppressLocalLayout = self.view.suppressLocalLayout()
    self.view.suppressLocalLayout(True)
    return 'break'

  def onB1_Motion(self, event):
    """
    The mouse is moving while being captured by this node, so if we had clicked to start
    accepting events, just move the node to track the event, updating *self.dragInfo*.

    :param event: The Tk event.
    :type event:
    :returns:
    :rtype:
    """
    
    if self.resizeInfo is not None:
      self.view.addEventHandled(event)
      x, y = self.view.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
      self._resizeTo(x, y)
      return 'break'
    if self.dragInfo is not None:
      self.view.addEventHandled(event)
      winX = self.canvas.canvasx(event.x) # convert widget-relative coords to canvas coords (accounts for scroll position)
      winY = self.canvas.canvasy(event.y)
      dX = winX - self.dragInfo[2]
      dY = winY - self.dragInfo[3]
      #print(f'onB1_Motion() event({event.x},{event.y}), d=({dX},{dY}), selected={self.selected()}')
      self.view.freshPaint()
      # allowOverScrollRegionSE=True: a live drag needs to actually be able to
      # cross the SE edge of the current scroll region -- moveTo() otherwise
      # clamps to it unconditionally, which would mean the bounding box could
      # never exceed the region and draw()'s scroll-region-growth check
      # (self.view.resetScrollRegion()) could never fire.
      if self.selected():
        for n in self.view.selected:
          n.moveBy(dX, dY, adjustPos=False, fast=False, allowOverScrollRegionSE=True)
      else:
        self.moveBy(dX, dY, adjustPos=False, fast=False, allowOverScrollRegionSE=True)
      # reset the starting point for the next move
      self.dragInfo = (self.dragInfo[0], self.dragInfo[1], winX, winY, True) # x,y,drag-motion-event-occurred
      return 'break'
    #else:
      #print(f'non-drag onB1_Motion() event x={event.x}, y={event.y}')


  def onDouble_1(self, event):
    '''
    A double-click: its attributes, in the attribute editor -- as "edit
    attributes" (or "show attributes": see *attributesReadOnly()*) on its
    menu. (Not on a context window's collapse triangle: that's two toggles.)

    :param event: The Tk event.
    :type event:
    :returns:
    :rtype:
    '''
    self.view.addEventHandled(event)
    self.dragInfo = None
    if self.modelObject is None or self.toggleAt(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)):
      return 'break'
    self.onEditAttributes(disabled=self.attributesReadOnly())
    return 'break'

  def onB1_ButtonRelease(self, event): #reset data on release
    """
    Button one was released. If it was a drag, it was a move, and everything is fine except
    we call self.adjustPos() which may resolve overlap conflicts. If it was a click (no
    intervening <B1_Motion> events), toggle the selection state of the node.

    :param event: The Tk event.
    :type event:
    :returns:
    :rtype:
    """
    #from sn.view.vcommands import MoveCommand
    if self.resizeInfo is not None:
      self.view.addEventHandled(event)
      _anchor, oldBB, oldUserSized = self.resizeInfo
      self.resizeInfo = None
      bb = self.boundingBox()
      if bb != oldBB: # commit the whole drag as one undoable command
        self.view.context.resize(self, bb[0], bb[1], bb[2], bb[3], oldBB=oldBB, oldUserSized=oldUserSized)
      else:           # just a click on a handle
        self.userSized = oldUserSized
      return 'break'
    if self.dragInfo is not None:
      self.view.addEventHandled(event)
      if self.dragInfo[4]: # indicated there was a <B1_Motion> event, ie: this was a drag: wrap up a move.
        # Restore whatever suppression state was in effect before this drag
        # started (set in onButton_1()) *before* the final move below, so that
        # the release-time moveTo() (adjustPos defaults to True) is free to run
        # FindFree and resolve any overlaps -- that's the "everything is fine
        # except..." comment below: this is the one point in a drag where we
        # actually want the full layout resolution to run.
        self.view.suppressLocalLayout(self.old_suppressLocalLayout)
        # if False: #self.canvas.fieldsLayoutObj.active:
        #   bb = self.boundingBox()
        #   x, y, _, _ = bb
        #   if self.overlaps(bb, spacing=[20,10]):
        #     self.canvas.fieldsLayoutObj(self)
        # else:
        #   x, y = self.adjustPos()
        # #record a move command
        # self.canvas.doList.do(MoveCommand(self, (x, y), (self.dragInfo[0], self.dragInfo[1]), suppressFirst=False))
        # If this was a multi-selection drag, onB1_Motion() moved every object
        # in self.view.selected (not just self) via its own dX/dY loop. Only
        # ever committing self's final position here left the other selected
        # objects' moves un-recorded: they stayed visually moved with no
        # Command on the queue, so a single undo() only restored self while
        # everything else dragged along with it stayed put. Committing a
        # context.move() for every selected object -- wrapped in a
        # CompositeCommandMgr, the same mechanism this class already uses for
        # multi-attribute edits (see onEditAttributes() above) -- bundles them
        # into one CompositeCommand, so one undo()/redo() moves the whole
        # group together, matching what the drag itself did.
        #
        # oldPos=... : pass each object's TRUE pre-drag position (captured in
        # onButton_1(), before any <B1-Motion> tick moved anything) explicitly
        # to _Move, rather than letting it fall back to capturing
        # boundingBox() at do()-time -- which, for a live-dragged object,
        # already reflects where the drag ENDED, not where it started. See
        # _Move's oldPos docstring in sngView.py for the full explanation.
        movedObjects = self.view.selected if self.selected() else [self]
        with CompositeCommandMgr(self.view.context):
          for n in movedObjects:
            bb = n.boundingBox()
            startPos = self.dragStartPositions.get(n, bb)
            self.view.context.move(n, bb[0], bb[1], _oldPos=startPos)
          self.view._updateContainment(self.dragStartCenters, draggedAlong=self.dragAlong)
      else: # this was a click, not a drag: toggle the selection state
        s = event.state
        self.selected(not self.selected(), _multi=s_CMD(s) or s_SHIFT(s)) # toggle selected
      self.dragInfo = None
      return 'break'
      # TODO: add updating the boundingBox.

  def _startResize(self, corner:str) -> None:
    '''
    Begin dragging the *corner* ("nw", "ne", "se" or "sw") handle: the
    opposite corner stays fixed (see *_resizeTo()*).

    :param corner:
    :type corner: str
    '''
    bb = self.boundingBox()
    x1, y1, x2, y2 = bb
    anchor = {"nw": (x2, y2), "ne": (x1, y2), "se": (x1, y1), "sw": (x2, y1)}[corner]
    self.resizeInfo = (anchor, list(bb), self.userSized)
    self.userSized = True # so the box isn't refitted to its text mid-drag

  def _resizeTo(self, x:float, y:float) -> None:
    '''
    Resize so the dragged corner is at (x, y) (view coords), keeping the
    opposite corner fixed. The width is at least "vis/minSize" (but may exceed
    "vis/maxSize"); if "vis/aspectRatio" is non-zero the height follows the
    width, otherwise it follows the pointer, but not below *minHeight()*.
    Dragging past the fixed corner just flips to the normalized rectangle.

    :param x:
    :type x: float
    :param y:
    :type y: float
    '''
    assert self.resizeInfo is not None
    (ax, ay), _, _ = self.resizeInfo
    if self.isContextWindow(): # free aspect, window-sized minimums
      w = max(abs(x - ax), self.WINDOW_MIN[0])
      h = self.bannerHeight() if self.collapsed else max(abs(y - ay), self.WINDOW_MIN[1])
    else:
      aspect = self.cache['vis/aspectRatio']
      w = max(abs(x - ax), self.cache['vis/minSize'])
      h = max(w * aspect if aspect else abs(y - ay), self.minHeight())
    x1 = ax if x >= ax else ax - w
    y1 = ay if y >= ay else ay - h
    self.reshape([x1, y1, x1 + w, y1 + h], adjustPos=False)

  def reshape(self, bb:list[float]|list[int], adjustPos:bool=False) -> None:
    '''
    Set the bounding box to *bb* (position and size), letting relations follow
    and redrawing.

    :param bb:
    :type bb: list[float] | list[int]
    :param adjustPos:
    :type adjustPos: bool
    '''
    from sn.view.graphics.vrelations import VRelation
    self.boundingBox([int(v) for v in bb])
    for r in self.relations:
      assert isinstance(r, VRelation)
      r.notifyNodeMove(self, adjustPos=adjustPos)
    self.view.freshPaint()
    self.draw()
    self.setDirty()

  def fitToText(self) -> None:
    '''
    Undo any manual sizing: size the box to its text again (about its centre),
    and keep it fitted from now on. Undoable.
    '''
    text = self.decorators.get("text")
    if not isinstance(text, WrappingText):
      return
    bb = text.preferredBoundingBox()
    self.view.context.resize(self, bb[0], bb[1], bb[2], bb[3], userSized=False)

  # ---- MENUS -----------------------------------------------------------------
  
  def makeMenu(self) -> tk.Menu:
    '''
    :returns:
    :rtype: tk.Menu
    '''
    m = tk.Menu(self.canvas)
    if True: #app.DEBUG_MENUS:
      if self.modelObject is None:
        mtitle = "None"
      else:
        mtitle = f'#{self.modelObject.id}?name="{self.modelObject.name}"'
      m.add_command(label=f'#{self._id} -> {mtitle}', state=tk.DISABLED)
      m.add_separator()
    editable = self.view.isModelEditor()
    if editable:
      self.addModelEditingMenuItems(m)
      m.add_separator()
    else:
      m.add_command(label='<not a model editor>', state=tk.DISABLED)
    self.addViewMenuItems(m)
    # m.add_separator()
    # self.addDeletionMenuItems(m)
    # if app.DEBUG_MENUS:
    #   m.add_separator()
    #   m.add_command(label='validate', command=self.validate)
    if len(self._statusReport)>0:
      def show(slf):
        pass
      m.add_command(label='show error report', command=lambda slf=self: [slf.clearStatusReport(), self.validate(), slf.showErrorActionDialog(slf.canvas.winfo_toplevel())])
    if snPrefs.get("debug", False):
      m.add_separator()
      m.add_command(label="validate", command=lambda o=self: \
                                                (n := len(o.validate()), \
                                                 logger.info(f'"{o.name}": No errors detected.') if n==0 else logger.warning(f'"{o.modelObject.name}": detected {n} errors.'), \
                                                 o.view.freshPaint(), 
                                                 o.draw()))
      m.add_command(label="refresh cache", command=lambda: self.cache.refresh(verbose=True))
    return m
    
  # def _setCatchNewObjects(self):
  #   self._oldCatchNewObjects = self.canvas.shouldCatchNewObjects
  #   self.canvas.shouldCatchNewObjects = True
  #
  # def _resetCatchNewObjects(self):
  #   self.canvas.shouldCatchNewObjects = self._oldCatchNewObjects
  #

  def _systemLocked(self) -> bool:
    '''
    :returns: Whether its model object can't be edited here: it's a system
      object (unless "gui/allowEditingSystemObjects"), or the view isn't a
      model editor.
    :rtype: bool
    '''
    mo = self.modelObject
    return mo is None or (mo.isSystemObject() and not snPrefs.get("gui/allowEditingSystemObjects", storeDefault=False)) \
           or not self.view.isModelEditor()

  def attributesReadOnly(self) -> bool:
    '''
    :returns: Whether its attributes can only be looked at, not edited: it's
      inferred (see *isInferred()*), a system object (see *_systemLocked()*), or
      from another model than the view's.
    :rtype: bool
    '''
    mo = self.modelObject
    return mo is None or self.isInferred() or self._systemLocked() or self.view.model is not mo.model

  def addModelEditingMenuItems(self, menu:tk.Menu):
    '''
    :param menu:
    :type menu: tk.Menu
    '''
    if self.modelObject is None:
      return
    if self.isInferred(): # (the reasoner's: it can only be looked at, or made asserted -- see GraphObject.inferred)
      menu.add_command(label="show attributes", command=lambda: self.onEditAttributes(disabled=True))
      locked = self.modelObject.model.writeLocked()
      menu.add_command(label="mark as asserted" + (" (the model is write-locked)" if locked else ""),
                       state=tk.DISABLED if locked else tk.NORMAL,
                       command=lambda: self.view.context.mark_asserted(self.modelObject))
      menu.add_separator()
      return
    disabled = self._systemLocked()
    relInst =  self.modelObject.isIndividual() and isinstance(self.modelObject, Relation)
    remote = self.view.model != self.modelObject.model
    readOnly = self.attributesReadOnly()
    menu.add_command(label=f"{'show' if readOnly else 'edit'} attributes",
                     command=lambda: self.onEditAttributes(disabled=readOnly))
    if self.modelObject.isType():
      menu.add_command(label='make new instance', command=lambda: self.makeModelObjectSubtype(individual=True))
      menu.add_command(label='make new subtype', command=lambda: self.makeModelObjectSubtype(individual=False))
    if not (disabled or relInst):
      menu.add_cascade(label="make relation to...", menu=self._relationTypesMenu(menu))
    if not disabled:
      n = len(self.selectionOrSelf())
      menu.add_command(label="remove from model" + (f" ({n} selected)" if n > 1 else ""), accelerator="Shift-Delete",
                       state=tk.DISABLED if remote and n == 1 else tk.NORMAL,
                       command=lambda: self.view.doRemove(self.selectionOrSelf()))
    menu.add_command(label="cut", state=tk.DISABLED if disabled or remote else tk.NORMAL, command=lambda: self.copySelection(cut=True))
    menu.add_command(label="copy", command=self.copySelection)
    menu.add_command(label="copy as picture", command=lambda: self.copySelection(picture=True))
    menu.add_separator()

  def selectionOrSelf(self) -> list[VObject]:
    '''
    :returns: What a menu item acts on: everything selected, if this is; else just this.
    :rtype: list[VObject]
    '''
    if self.selected():
      return [vo for vo in self.view.selected if vo._isConnected()]
    return [self]

  def copySelection(self, cut:bool=False, picture:bool=False) -> None:
    '''
    Copy (or cut) what's selected, if this is; else just this (see
    *SNGView.doCopy()*) -- or copy a picture of it (see *SNGView.doCopyImage()*).

    :param cut:
    :type cut: bool
    :param picture:
    :type picture: bool
    '''
    if not self.selected():
      self.selected(True)
    if picture:
      self.view.doCopyImage()
    else:
      self.view.doCopy(cut=cut)
      
  def highlight(self, on:bool|None=None, negative:bool=False) -> bool:
    '''
    :param on: True to give this object a glow (see *decorators.Highlight*),
      False to remove it, None to just ask.
    :type on: bool | None
    :param negative: With *on*: in the "negative" colour (eg: a query with no answers).
    :type negative: bool
    :returns: Whether it's highlighted.
    :rtype: bool
    '''
    if on is True and "highlight" in self.decorators and self.decorators["highlight"].negative != negative:
      self.decorators["highlight"].delete() # (the other colour)
    if on is True and "highlight" not in self.decorators:
      self.decorators["highlight"] = Highlight(self, negative=negative)
      self.decorators["highlight"].draw()
    elif on is False and "highlight" in self.decorators:
      self.decorators["highlight"].delete()
    return "highlight" in self.decorators

  def answerQuery(self) -> None:
    '''
    Answer the query this context (eg: a query, or a rule's antecedent)
    describes: print the answers to the terminal, and highlight every object
    the variables matched (in this view), replacing any earlier highlights --
    and this context too, to say which query they answer: in the "negative"
    colour if there are none (see *highlight()*).
    '''
    from sn.model.reasoner import Reasoner, queryWarnings, reportedAnswers
    from sn.model import names
    if self.view.reasoning is None: # (so what the rules conclude exists is in the model, for the answers to show)
      self.view.reasonSilently()
    for w in queryWarnings(self.modelObject):
      logger.warning(w)
    try:
      rows = Reasoner.create(self.view.model).answer(self.modelObject)
    except Exception as ex:
      logger.error(f'Can\'t answer "{self.name}": {ex}')
      return
    print(f'{self.name}:')
    print(self.view.context._formatAnswers(reportedAnswers(rows), self.view.model)) # (not ?_hidden variables)
    self.view.clearHighlights()
    for row in rows:
      for v, x in row.items():
        if not isinstance(x, GraphObject) or names.isHiddenName(v.name): # (a hidden variable's value isn't an answer)
          continue
        # an answer's shown -- even if it's in a hidden or erased category (eg: inferred objects), or wasn't shown at all
        vo = self.view.findViewObjectForGraphObject(x) or self.view.makeViewObjectForGraphObject(x)
        if vo is not None:
          self.view._exemptIfFiltered(vo)
          vo.highlight(True)
      for r in self._answerRelations(row):
        rvo = self.view.findViewObjectForGraphObject(r) or self.view.makeViewObjectForGraphObject(r)
        if rvo is not None:
          self.view._exemptIfFiltered(rvo)
    self.highlight(True, negative=not rows) # (which query the highlights answer -- or that it answered "no")

  def _answerRelations(self, row:dict[GraphObject, Any]) -> list[Relation]:
    '''
    :param row: An answer to the query this context describes (see *answerQuery()*).
    :type row: dict[GraphObject, Any]
    :returns: The relations (asserted or inferred) the answer matched: for each
      relation in the query's pattern, those of its type (or a subtype) between
      what its ends stand for in *row*.
    :rtype: list[Relation]
    '''
    from sn.model.reasoner import patternOf
    byName = {k.name: v for k, v in row.items()}
    value = lambda x: byName.get(x.name) if x is not None and x.isVariable() else x
    ret:list[Relation] = []
    for t, s, d in patternOf(self.modelObject).triples:
      T, S, D = value(t), value(s), value(d)
      if not all(isinstance(o, GraphObject) for o in (T, S, D)): # (an open end, or an object only the reasoner knows of)
        continue
      ret += [r for r, other in S._getOutgoing(lambda r: r.isIndividual() and r.isa(T)) if other is D and r not in ret]
    return ret

  def showConclusions(self) -> None:
    '''
    Show what this rule concluded in the last "reason" (reasoning first if
    there are no results): print its conclusions to the terminal, and
    highlight every object (in this view) it concluded something about,
    replacing any earlier highlights.
    '''
    if self.view.reasoning is None:
      self.view.reason()
    reasoning = self.view.reasoning
    if reasoning is None:
      return
    lines = reasoning.ruleConclusions(self.modelObject, model=self.view.model)
    print(f'{self.name}: {len(lines)} conclusion(s)' + "".join("\n  " + l for l in lines))
    problems = [v for v in reasoning.violationsFor(self.modelObject) if v.code.startswith("rule")]
    for v in problems:
      print(f'  {v}')
    self.view.clearHighlights()
    for x in reasoning.ruleObjects(self.modelObject):
      vo = self.view.findViewObjectForGraphObject(x)
      if vo is not None:
        vo.highlight(True)

  def _relationTypesMenu(self, parent:tk.Menu) -> tk.Menu:
    '''
    The "make relation to..." submenu: a submenu of relation types for each
    ancestor model (the view model's super-models, nearest first) at the top,
    then the view model's own relation types. Each list is sorted by name.

    :param parent:
    :type parent: tk.Menu
    :returns:
    :rtype: tk.Menu
    '''
    def relTypes(model) -> list[Relation]:
      return sorted((r for r in model.values() if isinstance(r, Relation) and r.isType() and not r.isVariable()), # (a pattern's ?r isn't a type to make)
                    key=lambda r: r.name.lower())
    def add(menu:tk.Menu, r:Relation) -> None:
      menu.add_command(label=r.name, command=lambda r=r: self.view.makeRelationFrom(self, r))
    model = self.view.model
    ancestors:list = []
    pending = list(model.superDBs)
    while pending:
      m = pending.pop(0)
      if m is not model and m not in ancestors:
        ancestors.append(m)
        pending += list(m.superDBs)
    ret = tk.Menu(parent)
    for anc in ancestors:
      types = relTypes(anc)
      if types:
        sub = tk.Menu(ret)
        for r in types:
          add(sub, r)
        ret.add_cascade(label=anc.name, menu=sub)
    own = relTypes(model)
    if ancestors and own:
      ret.add_separator()
    for r in own:
      add(ret, r)
    return ret

  @abstractmethod
  def makeModelObjectSubtype(self, individual:bool) -> None:
    '''
    :param individual:
    :type individual: bool
    '''
    raise NotImplementedError("Must implement VObject.makeSubtypeMenuItemFun().")
    
  def addViewMenuItems(self, menu:tk.Menu):
    # from sn.view.vcommands import ExpandCommand, RemoveFromViewCommand
    # INSTANCE = "IsaIndividual (instance)"
    # SUBTYPE = "IsaIndividual (subtype)"
    # collect info about the relations
    # types = dict()  # {name: (modelOutgoingCount, modelIncomingCount, 
    #         #         viewOutgoingCount,  viewIncomingCount,  otherIsaTypeCount)}
    # types[INSTANCE] = (0,0,0,0)
    # types[SUBTYPE]  = (0,0,0,0)
    # total = (0,0)
    # for rr in self.modelObject.referencers:
    #   # get the VNode that matches the Node (if any)
    #   r = rr() # resolve the lazy reference
    #   vRelation = None
    #   for rv in self.relations:
    #     if rv.modelObject is r:
    #       vRelation = rv
    #       break
    #
    #   # abort if this relation (r) is in a hidden category
    #   if self.canvas.categories.isCategory(r, self.canvas.hiddenCategories): continue
    #
    #   name = r.name
    #   if name != "IsaIndividual":
    #     if name not in types: # add the name of the relation upon encountering a new one
    #       types[name] = (0,0,0,0)
    #     t = types[name]
    #   if r.to is self.modelObject: # we're the toNode: increment incoming model and (maybe) view count 
    #     if name == "IsaIndividual":
    #       name = SUBTYPE if r.from_['type'] else INSTANCE
    #       t = types[name]
    #     t = (t[0], t[1]+1, t[2], t[3]+(0 if vRelation is None else 1))
    #   else: # we're the froNode: increment outgoing model and (maybe) view count
    #     if name == "IsaIndividual":
    #       name = SUBTYPE if r.to['type'] else INSTANCE
    #       t = types[name]
    #     t = (t[0]+1, t[1], t[2]+(0 if vRelation is None else 1), t[3])
    #   types[name] = t
    #   total = (total[0]+1, total[1]+(0 if vRelation is None else 1))
    # if types[INSTANCE] == (0,0,0,0): del types[INSTANCE]
    # if types[SUBTYPE]  == (0,0,0,0): del types[SUBTYPE]
    #
    # # the expand menus
    # expMenu = tk.Menu(menu)
    # for k,v in types.items():
    #   subMenu = tk.Menu(expMenu)
    #   if v[0] > 0:
    #     if k == INSTANCE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and vn.modelObject is mr.from_ and not mr.to['type']
    #     elif k == SUBTYPE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and vn.modelObject is mr.from_ and mr.to['type']
    #     else:
    #       filtr = lambda vn, mr, label=k: \
    #               mr.name == label and vn.modelObject is mr.from_
    #     subMenu.add_command(label=f'outgoing ({v[0]})', \
    #         command=lambda f=filtr: self.canvas.doList.do(ExpandCommand(self, filtr=f)))
    #   if v[1] > 0:
    #     if k == INSTANCE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and vn.modelObject is mr.to and not mr.from_['type']
    #     elif k == SUBTYPE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and vn.modelObject is mr.to and mr.from_['type']
    #     else:
    #       filtr = lambda vn, mr, label=k: \
    #               mr.name == label and vn.modelObject is mr.to
    #     subMenu.add_command(label=f'incoming ({v[1]})', \
    #         command=lambda f=filtr: self.canvas.doList.do(ExpandCommand(self, filtr=f)))
    #   if v[0] > 0 and v[1] > 0:
    #     if k == INSTANCE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and not mr.from_['type']
    #     elif k == SUBTYPE:
    #       filtr = lambda vn, mr: \
    #               mr.name == "IsaIndividual" and mr.from_['type']
    #     else:
    #       filtr = lambda vn, mr, label=k: \
    #               mr.name == label
    #     subMenu.add_command(label=f'both ({v[0]+v[1]})', \
    #         command=lambda f=filtr: self.canvas.doList.do(ExpandCommand(self, filtr=f)))
    #   subMenu.add_separator()
    #   for mrr in self.modelObject.referencers:
    #     mr = mrr()
    #     if k in [INSTANCE, SUBTYPE]: name = "IsaIndividual"
    #     else: name = k
    #     if mr.name == name:
    #       arrow = '->' if mr.from_ is self.modelObject else '<-'
    #       other = mr.to if mr.from_ is self.modelObject else mr.from_
    #       filtr = lambda vn, mr, theMr=mr: mr is theMr
    #       subMenu.add_command(label=f'{k} {arrow} {other.name}',
    #             command = lambda f=filtr: self.canvas.doList.do(ExpandCommand(self, filtr=f)))
    #   expMenu.add_cascade(menu=subMenu, label=f'expand {k} relations ({v[0]+v[1]})')
    '''
    :param menu:
    :type menu: tk.Menu
    '''
    expMenu = tk.Menu()
    expMenu.add_command(label="expand all, 1 level" , command=lambda: self.view.context.expand(self))
    expMenu.add_command(label="expand all, 2 levels", command=lambda: self.view.context.expand(self, levels=1))
    expMenu.add_command(label="expand all, 3 levels", command=lambda: self.view.context.expand(self, levels=2))
    expMenu.add_command(label="expand all, 4 levels", command=lambda: self.view.context.expand(self, levels=3))
    menu.add_cascade(menu=expMenu, label="expand")
    n = len(self.selectionOrSelf())
    menu.add_command(label="erase from view" + (f" ({n} selected)" if n > 1 else ""), accelerator="Delete",
                     command=lambda: self.view.doErase(self.selectionOrSelf()))
    mo = self.modelObject
    if mo is not None and mo.isa(mo.model.CONTEXT) and mo is not mo.model.CONTEXT:
      menu.add_command(label="answer query", command=self.answerQuery)
    if mo is not None and mo.isIndividual() and (mo.isa(mo.model.RULE) or mo.isa(mo.model.DEFINITION)):
      menu.add_command(label="show conclusions", command=self.showConclusions)
    if "disabled" in self.decorators and mo is not None:
      disabled = mo.isDisabled()
      menu.add_command(label="enable" if disabled else "disable",
                       state=tk.DISABLED if mo.model is not self.view.model or mo.model.writeLocked() else tk.NORMAL,
                       command=lambda: self.view.context.set_attribute(mo, GraphObject.DISABLED, not disabled))
    if self.isContextWindow():
      menu.add_command(label="gather", command=lambda: self.view.gatherIntoWindow(self))
    if isinstance(self.decorators.get("text"), WrappingText):
      menu.add_command(label="fit to text", command=self.fitToText,
                       state=tk.NORMAL if self.userSized else tk.DISABLED)
         
  def onEditAttributes(self, disabled:bool=False):
    '''
    :param disabled:
    :type disabled: bool
    '''
    mo = self.modelObject
    edits = editAttrsBox(self.canvas, mo, title=str(mo), disabled=disabled)
    if not disabled and edits is not None:
      nameEdit = edits.get("name") # (the editor returns Attributes)
      typed = nameEdit.value if isinstance(nameEdit, Attribute) else nameEdit
      if isinstance(typed, str) and WHERE in typed:
        edits = self._whereEdits(edits, nameEdit, typed)
      if not edits:
        return
      with CompositeCommandMgr(self.view.context) as mgr:
        for key,value in edits.items():
          if value is None:
            self.view.context.delete_attribute(mo, key)
          else:
            self.view.context.set_attribute(mo, key, value)

  def _whereEdits(self, edits:dict, nameEdit:Any, typed:str) -> dict:
    '''
    A variable's name typed with constraints, eg: "?p :where: alive, age: 30":
    the edits for its name ("?p") and its "constraints" attribute (the typed
    constraints added to any it has; see *sn.model.constraints*). For anything
    but a variable, or constraints that can't be read, the name isn't changed
    (and a message says why).

    :param edits:
    :type edits: dict
    :param nameEdit:
    :type nameEdit: Any
    :param typed:
    :type typed: str
    :returns:
    :rtype: dict
    '''
    mo = self.modelObject
    name, text = splitWhere(typed)
    ret = {k: v for k, v in edits.items() if k != "name"}
    if not names.isVariableName(name):
      logger.error(f'"{typed}": only variables have constraints ({names.grammar.describe()}). The name wasn\'t changed.')
      return ret
    base = edits.get(CONSTRAINTS)
    base = (base.value if isinstance(base, Attribute) else base) if CONSTRAINTS in edits else mo.getLocal(CONSTRAINTS, None)
    try:
      merged = mergeConstraints(base, text or "")
    except ConstraintError as ex:
      logger.error(f'"{typed}": the constraints can\'t be read ({ex}). The name wasn\'t changed.')
      return ret
    if name != mo.name:
      if isinstance(nameEdit, Attribute):
        nameEdit.value = name
      else:
        nameEdit = name
      ret["name"] = nameEdit
    if merged != (base or ""):
      ret[CONSTRAINTS] = Attribute(merged, str, VAR, CONSTRAINTS_NOTE)
    return ret

  # ---- DRAWING ---------------------------------------------------------------
  
  def makeDecorators(self):
    notIsIsa = type(self.modelObject) is not IsaIndividual if self.modelObject is not None else True
    if self.isContextWindow():
      self.decorators["frame"] = ContextFrame(self) # a window, titled in its banner
    elif notIsIsa:
      self.decorators["text"] = WrappingText(self)
    self.decorators["markers"] = MarkerContainer(self)
    mo = self.modelObject
    try:
      if mo is not None and mo.isIndividual() and isinstance(mo, Node) and mo.isa(mo.model.CONTEXT): # (it may be disabled: see GraphObject.isDisabled())
        self.decorators["disabled"] = DisabledSlash(self)
    except Exception: # (eg: half-built)
      pass
    # shadow types only. The decorator is also drawn only while "gui/shadowTypes" is on (see ShadowDecorator.draw())
    if notIsIsa and self.modelObject is not None and self.modelObject.isType() and \
        snPrefs.get("gui/shadowTypes", storeDefault=True, storeType=bool): # (its note: see sn.PREFS)
      self.decorators["shadow"] = ShadowDecorator(self)
    # try:
    #   if self.modelObject.isType() or self.modelObject.isSystemObject:
    #     self.decorators["typeMarker"] = TypeMarker(self)
    # except Exception as ex:
    #   self.canvas.logger.write(f"failed to make 'typeMarker': {type(ex).__name__}: {ex}.", level="warning", exception=ex)

  def draw(self, fast=False, **kwargs):#, rect=None):
    '''
    :param fast:
    :type fast:
    :param kwargs:
    :type kwargs:
    '''
    if self._drawVersion >= self.view._drawVersion or not self._isConnected(): # (not if it's out of the view: drawing would show it again)
      return
    else: 
      self._drawVersion = self.view._drawVersion
    # a window is at least WINDOW_MIN (eg: when first drawn, or from an older view)
    if not fast and self.isContextWindow():
      x1, y1, x2, y2 = self.boundingBox()
      if self.collapsed: # (just the title bar -- eg: as saved)
        if y2 - y1 != self.bannerHeight() or x2 - x1 < self.WINDOW_MIN[0]:
          self.boundingBox([x1, y1, x1 + max(x2 - x1, self.WINDOW_MIN[0]), y1 + self.bannerHeight()])
      elif x2 - x1 < self.WINDOW_MIN[0] and y2 - y1 < self.WINDOW_MIN[1]: # (never been a window: eg: new)
        self.boundingBox([x1, y1, x1 + self.WINDOW_DEFAULT[0], y1 + self.WINDOW_DEFAULT[1]])
      elif x2 - x1 < self.WINDOW_MIN[0] or y2 - y1 < self.WINDOW_MIN[1]:
        self.boundingBox([x1, y1, x1 + max(x2 - x1, self.WINDOW_MIN[0]), y1 + max(y2 - y1, self.WINDOW_MIN[1])])
    # size the box to its text first, so the shape is drawn at the new size
    text = self.decorators.get("text")
    if not fast and isinstance(text, WrappingText):
      text.fitOwner()
    self._shape.draw(fast=fast, **kwargs) #self["boundingBox"])#rect)
    self.markerDecoratorOffset=0
    for d in sorted(self.decorators.values(), key=lambda d: d.priority):
      d.draw(fast=fast)

    self._applyHidden()

    # make sure this is reachable by resetting the bounding box if necessary
    bb = self.boundingBox()
    sr = self.view.scrollRegion
    if bb[0] < sr[0] or bb[1] < sr[1] or bb[2] > sr[2] or bb[3] > sr[3]:
      self.view.resetScrollRegion()
    
  def moveTo(self, x, y, *, allowOverScrollRegionSE=False, adjustPos=True, fast=False, carry=True):
    """ 
    Move so that the NW corner is on (x,y), informing all the decorators and 
    relations. A context window carries what's inside it along (unless
    *carry* is False: eg: a layout moving everything to where it computed),
    and isn't subject to overlap avoidance (it's meant to have things on it).

    :param x:
    :type x:
    :param y:
    :type y:
    :param allowOverScrollRegionSE:
    :type allowOverScrollRegionSE:
    :param adjustPos:
    :type adjustPos:
    :param fast:
    :type fast:
    :param carry: Whether a context window carries what's inside it along.
    :type carry: bool
    """
    bb = self.boundingBox(fast=fast)
    if self.isContextWindow():
      adjustPos = False
      dx, dy = x - bb[0], y - bb[1]
      if (dx or dy) and carry:
        # (not objects that are themselves being moved -- eg: also selected -- nor
        # floating relation labels: they follow their ends, so they'd move twice)
        floats = lambda vo: callable(getattr(vo, "floating", None)) and vo.modelObject is not None and vo.modelObject.isIndividual() and vo.floating()
        contents = self.carriedContents()
        carried = [vo for vo in contents if not (self.selected() and vo.selected()) and not floats(vo)]
        # ... and its containment links' labels, if they're pinned (they're drawn only when what they contain is out of the window)
        carried += [r for r in self.relations if getattr(r, "src", None) is self and getattr(r, "dst", None) in contents
                    and r not in carried and not floats(r) and not (self.selected() and r.selected())]
        # The window's own place first: a floating label that follows its ends
        # as they're carried is kept in its pane (see VRelation.placedLabel()) --
        # which must be where the window's going, not where it was.
        self.boundingBox([x, y, x+bb[2]-bb[0], y+bb[3]-bb[1]])
        for vo in carried:
          vo.moveBy(dx, dy, adjustPos=False, fast=fast)
    if bb[0] == x and bb[1] == y and not adjustPos:
      # We haven't actually moved and nobody asked for layout resolution, so
      # there's truly nothing to do. NOTE: this must NOT also skip when
      # adjustPos is True -- the drag-release call (onB1_ButtonRelease() ->
      # SNGContext._Move.do()) calls moveTo(x, y) with (x,y) equal to
      # wherever the drag already left the node, specifically *to* trigger
      # adjustPos()/FindFree overlap resolution at that spot. Returning here
      # regardless of adjustPos used to make that call a complete no-op, so
      # two objects dropped on top of each other would just stay stacked.
      return
    # sr = self.view.scrollRegion
    # if x<sr[0]: x = sr[0]
    # if y<sr[1]: y = sr[1]
    # if not allowOverScrollRegionSE:
    #   if x+bb[2]-bb[0]>sr[2]: x = sr[2]-(bb[2]-bb[0])
    #   if y+bb[3]-bb[1]>sr[3]: y = sr[3]-(bb[3]-bb[1])
    self.boundingBox([x, y, x+bb[2]-bb[0], y+bb[3]-bb[1]])
    if adjustPos:
      #The traditional way 
      self.adjustPos(fast=fast)
      
      # use the field animation layout
      # if hasattr(self.canvas, "fieldsLayoutObj") and self.canvas.fieldsLayoutObj is not None and self.overlaps(spacing=[20, 10]):
      #   self.canvas.fieldsLayoutObj.nextFrame(activeNodes=[self])
      
    if not fast:
      for r in self.relations:
        # Pass adjustPos through: during a live drag (adjustPos=False) relations
        # should still visually track this node's new position, but shouldn't
        # each run their own full adjustPos()/FindFree placement on every single
        # mouse-motion tick -- that's what was producing big visual jumps while
        # dragging. The full layout resolution now happens once, when moveTo()
        # is called with the default adjustPos=True (e.g. on button-release).
        r.notifyNodeMove(self, adjustPos=adjustPos)

    self.view.freshPaint()
    self.draw()
    self.setDirty()
    
      
  def moveBy(self, dx, dy, *, allowOverScrollRegionSE=False, adjustPos=True, fast=False, carry=True):
    '''
    :param dx:
    :type dx:
    :param dy:
    :type dy:
    :param allowOverScrollRegionSE:
    :type allowOverScrollRegionSE:
    :param adjustPos:
    :type adjustPos:
    :param fast:
    :type fast:
    :param carry: Whether a context window carries what's inside it along (see *moveTo()*).
    :type carry: bool
    '''
    bb = self.boundingBox(fast=fast)
    x = bb[0]+dx
    y = bb[1]+dy
    self.moveTo(x, y, allowOverScrollRegionSE=allowOverScrollRegionSE, adjustPos=adjustPos, fast=fast, carry=carry)
    
  def moveToCenterOn(self, x, y, adjustPos=True, fast=False):
    '''
    :param x:
    :type x:
    :param y:
    :type y:
    :param adjustPos:
    :type adjustPos:
    :param fast:
    :type fast:
    '''
    bb = self.boundingBox(fast=fast)
    width = abs(bb[2]-bb[0])
    height = abs(bb[3]-bb[1])
    x = int(x - (width/2))
    y = int(y - (height/2))
    self.moveTo(x, y, adjustPos=adjustPos, fast=fast)

  def centerPt(self):
    """
    Gets the center point of this shape.

    :returns:
    :rtype:
    """
    r = self.boundingBox()
    return (int((r[0]+r[2])/2), int((r[1]+r[3])/2))

  def containsPt(self, pt):
    '''
    :param pt:
    :type pt:
    :returns:
    :rtype:
    '''
    return pointInPoly(pt, self._shape.points())
    
  def adjustPos(self, aggressive:bool=False, fast=False) -> tuple[int,int]:
    '''
    :param aggressive:
    :type aggressive: bool
    :param fast:
    :type fast:
    :returns:
    :rtype: tuple[int, int]
    '''
    if fast:
      bb = self.boundingBox(fast=fast)
      return bb[0], bb[1]
    
    # use a regular layout  
    layout = self.view.localLayout
    if layout is not None:
      layout(self, aggressive=aggressive)
      for r in self.relations:
        layout(r, aggressive=aggressive)
    r = self.boundingBox(fast=fast)
    
    return r[0], r[1]
    
  def overlaps(self, bb:list=None, others:Iterable=None, spacing:Optional[list]=None) -> list: #list[VObject]:
    '''
    :param bb:
    :type bb: list
    :param others:
    :type others: Iterable
    :param spacing:
    :type spacing: Optional[list]
    :returns:
    :rtype: list
    '''
    if bb is None:
      bb = self.boundingBox() if spacing is None else expandRect(self.boundingBox(), spacing)
    if others is None:
      others = list(self.canvas.values()) #self.canvas.nodes + self.canvas.relations
      others.remove(self)
    else:
      if self in others:
        others = others.copy()
        others.remove(self)
    ret = []
    for n in others:
      nBB = n.boundingBox() if spacing is None else expandRect(n.boundingBox(), spacing)
      if overlaps(bb, nBB):
        ret.append(n)
    return ret

  def expand(self, 
             filter:Callable[[Any, Relation], bool]=lambda _vn, _mr: True, 
             expand=0,
             _done:dict[int, int]|None=None):
    """
    Show this object's relations that aren't shown yet (and so what's at their
    other ends) -- and, if *expand* > 0, expand each object at the other end of
    each of its relations (shown already or not) in turn, by *expand* - 1. So 0
    shows this object's neighbours, 1 their neighbours too, and so on.

    :param filter: Optional[Callable[[Self, Relation], bool]] A function *selfxRelation->bool*
        where that relation will only be expanded if the function returns *True* 
    :type filter: Callable[[Any, Relation], bool]
    :param expand: [Optional[int], default=0] The number of hops to expand beyond this
      object's neighbours.
    :type expand: int
    :param _done: (Internal) The objects expanded so far in this expansion
      (by *id()*), and by how many more hops: none is done twice to the same
      depth or less, as an expansion would otherwise grow exponentially with
      the depth (going back and forth along each relation, round each cycle).
    :type _done: dict[int, int] | None
    """
    from sn.view.graphics.vrelations import VRelation
    if _done is None:
      _done = {}
    mo = self.modelObject
    if mo is None or _done.get(id(self), -1) >= expand:
      return
    _done[id(self)] = expand
    # nothing in a hidden or erased category (see SNGView.visibility()): not
    # the relation, nor what it leads to
    def ok(rel:Relation) -> bool:
      if self.view.isFiltered(rel):
        return False
      other = rel.localDst if rel.localSrc is mo else rel.localSrc
      return not (other is not None and self.view.isFiltered(other)) and filter(self, rel)
    rels:list[Relation] = removeDuplicates([r for r, _ in mo._getIncoming(filtr=ok)] + [r for r, _ in mo._getOutgoing(filtr=ok)])
            
    # show the ones that aren't shown (with what's at their other ends: see VRelation._resolveEnd())
    new = [r for r in rels if self.view.findViewObjectForGraphObject(r) is None]
    if len(new) > 0:
      bb = self.boundingBox()
      x = bb[2] + 50
      y = len(new) * 25
      for r in new:
        self.view.makeViewObjectForGraphObject(r, atPoint=(x,y))
        y += 50

    if expand > 0: # and on to what's at their other ends
      for r in rels:
        vRel = self.view.findViewObjectForGraphObject(r)
        if not isinstance(vRel, VRelation):
          continue
        other = vRel.dst if vRel.src is self else vRel.src
        if other is not None and other is not self and other._isConnected():
          other.expand(filter=filter, expand=expand - 1, _done=_done)

  def strToShape(self, name):
    '''
    :param name:
    :type name:
    :returns:
    :rtype:
    '''
    from sn.view.graphics.shapes import Shape
    cls = Shape.getShapeClass(name)
    if cls is not None:
      return cls(self)
    raise TypeError("VNode.strToShape(): Do not know shape class '"+name+"'.")

  def selected(self, val:Optional[bool]=None, _multi:bool=False) -> bool|None:
    '''
    :param val:
    :type val: Optional[bool]
    :param _multi:
    :type _multi: bool
    :returns:
    :rtype: bool | None
    '''
    if val is not None:
      if val: # setting selected
        if "selected" not in self.decorators:
          self.decorators["selected"] = Selected(self)
          self.decorators["selected"].draw()
          if not _multi:
            for s in self.view.selected.copy():
              if s is not self: s.selected(False)
          self.view.selected.add(self)
      elif self.decorators is not None: # setting not selected
        if "selected" in self.decorators:
          self.decorators["selected"].delete()
          assert "selected" not in self.decorators
          self.draw()
          self.view.selected.discard(self)
    return "selected" in self.decorators if self.decorators is not None else None

  def tooltipFunc(self) -> str:
    '''
    :returns:
    :rtype: str
    '''
    tip = ""
    line = "\u2594"*18
    try:
      tip = self.name
      if snPrefs.get("debug", storeDefault=False):
        tip += f' ({self._id})'
      note = self.modelObject.get("note", None) if self.modelObject is not None else None
      if note is not None:
        #tip += f'\n{line*2}NOTE:{line*13}\n{note.value}'
        tip += f'\n{line}\nNOTE:\n{note}'
    except ReferenceError:
      return ""
    if snPrefs.get("debug", storeDefault=False) and snPrefs.get("debug_popupCache", storeDefault=True):
      if len(tip)>0 and tip[-1]!='\n':
        tip += "\n"
      #tip += f'\n{line*2}CACHE:{line*12}'
      tip += f'{line}\nCACHE:'
      for name in VATTRIBUTES:
        if name in self.cache:
          val = self.cache[name]
          tip += f'\n  "{name}": {str(val)} ({type(val).__name__})'
      # if hasattr(self.cache, "_roles"):
      #   tip += f'\n  "_roles": {str(self.cache._roles)}'
      #   for r in self.cache._roles:
      #     tip += f'\n  "_{r}__filler":'
      #     if hasattr(self.cache, f'_{r}__filler'):
      #       #tip += ": "
      #       objs = getattr(self.cache, f'_{r}__filler')
      #       for obj in objs:
      #         tip += f' {obj.getRelativeStringInContext(self.canvas)},'
    return tip
  
  def notifyDecoratorDeletion(self, decorator):
    '''
    :param decorator:
    :type decorator:
    '''
    self.removeDecorator(obj=decorator)

  def removeDecorator(self, key=None, obj=None):
    """
    :param key: A key in the decorator list.
    :type key:
    :param obj: An actual decorator object.
    :type obj:
    
    Removes a single decorator from the decorator list, either by *key* or by *obj*\\ .
    If the item is not found, nothing is done.
    """
    if key!=None:
      if key in self.decorators:
        self.decorators[key].delete()
        self.decorators.pop(key, None)
        return
    if obj!=None:
      for k,v in self.decorators.items():
        if v == obj:
          v.delete()
          self.decorators.pop(k, None) #should have been popped already by the delete() above...
          return

  @override
  def _disconnect(self, **kwargs) -> None:
    '''
    Remove this object from the view (eg: "erase from view"), keeping enough to
    put it back (see *_reconnect()*). Individual relations attached to it go
    with it; relation *types* attached to it stay, with that end left
    dangling -- a type is still meaningful without this object in view.

    :param kwargs:
    :type kwargs:
    '''
    from sn.view.graphics.vrelations import VRelation
    detached:list[tuple[VRelation, str]] = []
    for r in list(self._incoming) + list(self._outgoing):
      if isinstance(r, VRelation) and r._isConnected() and r.modelObject is not None and r.modelObject.isType():
        for end in ("src", "dst"):
          if getattr(r, end) is self:
            setattr(r, end, None) # (AGRelation's setter takes it off our lists too)
            detached.append((r, end))
    self._detachedTypeEnds = detached
    if self.selected(): # (out of the selection too: else deselecting it later -- eg: a click elsewhere -- would draw it again)
      self.selected(False)
    self.view.selected.discard(self)
    super()._disconnect(**kwargs)
    self.view.structureChanged()
    self._hideItems()
    for r, _ in detached:
      r.view.freshPaint()
      r.draw()
    
  @override
  def _reconnect(self, **kwargs):
    '''
    :param kwargs:
    :type kwargs:
    '''
    super()._reconnect(**kwargs)
    self.view.structureChanged()
    if self.__dict__.get("_firstDrawPending"): # (taken out before it was ever drawn: see _firstDraw())
      self._firstDraw()
    self._showItems() # (a redraw hides it again if it should be -- see _applyHidden())
    self._hidden = False
    for r, end in getattr(self, "_detachedTypeEnds", []): # re-attach the relation types' ends
      if r._isConnected() and getattr(r, end) is None:
        setattr(r, end, self)
        r.view.freshPaint()
        r.draw()
    self._detachedTypeEnds = []

  # def setHidden(self, hide:bool=True):
  #   '''
  #   "Unhooks" ("rehooks") from the view's list of objects and sets the graphics objects to
  #   state="hidden" ("normal"). Note that Nodes' .relations and Relations' arcs are not
  #   updated.  
  #   '''
  #   if hide == self._hidden:
  #     return
  #   if hide:
  #     if not self.isHidable():
  #       logger.error("Cannot hid an object that has any non-individual relations.")
  #     PRDb.remove(self.view, self._id) # both PRDb and SNCanvas have __setitem__()
  #     self.canvas.itemconfigure(self.tag, state="hidden")
  #   else:
  #     PRDb.__setitem__(self.view, self._id, self) # both PRDb and SNCanvas have __setitem__()
  #     self.canvas.itemconfigure(self.tag, state="normal")
  #   self.setDirty()
  #
  # def isHidden(self):
  #   return self._hidden
  #
  def isHidable(self) -> bool:
    '''
    An object is "hidable" only if ALL it's relations are instances.

    :returns:
    :rtype: bool
    '''
    # for r in self.relations:
    #   if r.modelObject.isType() and not r.isHidden():
    #     return False 
    return True

  # ---- RELATIONS -------------------------------------------------------------

  # def addRelation(self, relation): #, direction):
  #   from sn.view.graphics.vrelations import VRelation
  #   if not isinstance(relation, VRelation):
  #     raise TypeError("VNode.addRelation(): first argument must be of type VRelation.")
  #   self.relations.append(relation) #(relation, direction))
  #   #  relation.model.addObserver(self) # observer the relation MODEL

  def notifyRelationDeletion(self, relation):
    """
    This is the notification from removal of a relation VIEW.

    :param relation:
    :type relation:
    """
    for r in self.relations:
      if r == relation:
        self.relations.remove(r)
        break
        
  # ---- Debugging support -----------------------------------------------------
  
  @override
  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
    :rtype: str
    '''
    return self.tostring()
  
  @override
  def tostring(self, relativeTo:"SNGView"|None=None) -> str:
    '''
    :param relativeTo:
    :type relativeTo: 'SNGView' | None
    :returns:
    :rtype: str
    '''
    if self.modelObject is None:
      return f'{self.__class__.__name__}(?, {PReference.formatForURL(self, relativeTo, includeName=False)}, {self.readModelObjectRef if hasattr(self,"readModelObjectRef") else "?"})'
     
    name = self.modelObject.getLocal("name", None)
    if name is None:
      name = f'{UP_ARROW}"{self.modelObject.get("name")}"'
    return f'{self.__class__.__name__}({name}, {PReference.formatForURL(self, relativeTo, includeName=False)}, {self.modelObject.tostring(self.view.model)})'
  
  def __repr__(self):
    '''
    :returns: A string representation of this object.
    :rtype:
    '''
    return self.__str__()
  
  # def __hash__(self):
  #   return hash(self.idString)
    

