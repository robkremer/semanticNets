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

----------
'''
from __future__ import annotations
from typing import Any, Optional, Union, Callable, override, cast,\
  Iterable, Iterator, TYPE_CHECKING
from types import NoneType
import tkinter as tk
import weakref
import traceback
import itertools
from abc import abstractmethod

from util.persistence.serialize import InstantiationInfo, ParamInfo, PropertyInfo
from util.commandParser import CompositeCommandMgr
from util.persistence.pRef import PReference
from util.observer import Observer, Subject
from util.utils import tag_bindRightMouse, tag_unbindRightMouse, s_CMD, s_SHIFT, s_ALT,\
  pointInPoly, showExceptionDialog
from util.tooltip import CreateToolTip
from util.attributeEditor import editAttrsBox
from util.abstractGraph import AGObject
from sn import hooks
from sn.hooks import HookContext
from util.dirtyable import Dirtyable
from util.errorReportingObject import ErrorReportingObject

import sn
from sn import snPrefs
from sn.model import GraphObject, Relation
from sn.model.model import UP_ARROW, IsaIndividual, Node, removeDuplicateObjects
from sn.model import names
from sn.model.constraints import WHERE, CONSTRAINTS, CONSTRAINTS_NOTE, splitWhere, mergeConstraints, ConstraintError
from util.attribute import Attribute, VAR
from sn.view.graphics.decorators import WrappingText, Selected, Highlight, ContextFrame, MarkerContainer, NOMINAL_ASPECT,\
  Decorator, ShadowDecorator, DisabledSlash

if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView
  from sn.view.graphics.vrelations import VRelation

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
  '''
  
  def __init__(self, owner):
    '''
    ;param owner: [VObject]
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
    :param verbose: [default=False] If True, write out all the attributes from 
        *VATTRIBUTES* that are in the cache AFTER the update has occurred.
        
    Update *attr* from the model object.
    '''
    owner:VObject|None = self._owner()
    if owner is None: return
    mo = owner.modelObject
    if mo is None: return
    
    def refreshAttr(attr:str):
      try:
        self[attr] = mo[attr]
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
    The cached value for *key*: looked up if it isn't cached (or the default); a colour of an inferred
    object's, faded.
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
    Cache *val* for *key*.
    '''
    assert key in self.allkeys
    super().__setitem__(key, val)
    
  def __contains__(self, key:object) -> bool:
    '''
    Whether *key* is one it caches.
    '''
    return key in self.allkeys
      

INFERRED_FADE = 0.4
"How much of its own colours an inferred object keeps (see *fadeColor()*): the rest is the canvas's background."

def fadeColor(canvas, color:str, amount:float=INFERRED_FADE) -> str:
  '''
  *color* faded toward *canvas*'s background: *amount* of the colour (1: the
  colour; 0: the background).

  :param canvas: A Tk canvas (or anything with *winfo_rgb()* and *cget("background")*).
  :param color: A Tk colour.
  :param amount: How much of *color* to keep.
  :returns: The faded colour, as "#rrggbb" (*color* if it can't be read).

  Remembered on *canvas* for its background at the time (read each call, so
  a changed background -- eg: the *gui/backgroundColor* preference on a new
  canvas, or *configure(background=...)* -- gets its own): an inferred
  object's colours are asked for often (see *Cache.__getitem__()*), and the
  two *winfo_rgb()* calls are most of the cost.
  '''
  try:
    background = canvas.cget("background")
    memo = getattr(canvas, "__dict__", {}).setdefault("_fadedColors", {})
    key = (color, background, amount)
    ret = memo.get(key)
    if ret is not None:
      return ret
    fg = canvas.winfo_rgb(color)
    bg = canvas.winfo_rgb(background)
  except Exception:
    return color
  mix = [int((f * amount + b * (1 - amount)) / 257) for f, b in zip(fg, bg)]
  ret = memo[key] = "#{:02x}{:02x}{:02x}".format(*mix)
  return ret

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
    :param modelObject: The object in the model that this object represents.
    :param shape: [Union[tygra.view.shapes.Shape, str], default=...shapes.Rectangle] The basic shape of this object.
    :param x: The upper left corner x coordinate
    :param y: The upper left corner y coordinate
    :param x1: The lower right corner x coordinate
    :param y1: The lower right corner y coordinate
    :param kwargs: Passed on to *super().__init__()*. *VObject* is normally
      combined with *AGRelation* via multiple inheritance (see *VRelation*),
      and the two share *AGObject* as a common ancestor -- calling *super()*
      cooperatively here (not separately naming *AGObject* and *PRObject*)
      ensures that shared ancestor's *__init__* -- which registers this
      object with *view* -- runs exactly once no matter which subclass is
      being constructed, not once per inheritance path. *kwargs* is how *AGRelation*'s own *src*/*dst*
      constructor arguments -- which *VObject* has no use for itself -- get
      carried through to it along that same chain.
    :type kwargs: Any
    '''
    from sn.view.graphics.shapes import Shape
    from sn.view.graphics.sngView import SNGView

    #check parameters
    assert isinstance(view, SNGView), f'Expecting SNGView type, got {type(SNGView)}'
    if isinstance(modelObject, str):
      self.readModelObjectRef:str = modelObject
      ref = view.model.replacedRef(modelObject) if hasattr(view.model, "replacedRef") else modelObject # (see Model.replaceSuperModel())
      try:
        obj = PReference[GraphObject](ref)(relativeTo=view.model)
      except Exception as ex: # (eg: its model's gone, or it's been deleted from it: see validate())
        from sn.model.model import unresolvedReason
        obj = None
        self.__dict__["_missingReason"] = reason = unresolvedReason(ref, ex)
        view.__dict__.setdefault("_unresolved", []).append((ref, reason))
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
      self.cache['name'] = m.name # (the rest are filled in as they're asked for: see Cache.__getitem__())

    self.view:SNGView = view
    view.structureChanged()

    # *AGObject* is a common ancestor shared with *AGRelation* whenever this
    # is actually a *VRelation* (see that class's __init__ for the full
    # explanation of the diamond). This single cooperative super().__init__()
    # call reaches AGObject.__init__() -- and hence PRObject.__init__(),
    # which registers this object with *view* -- exactly once, however many
    # inheritance paths lead here. Dirtyable and Observer are reached along the
    # same chain: don't call PRObject.__init__(), Dirtyable.__init__() or
    # Observer.__init__() separately as well -- a second PRObject.__init__()
    # would register every VObject (not just a VRelation) twice.
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
    self._boundingBox:list = [x, y, x1, y1]

    self.canvas:tk.Canvas = view.canvas
    self._updatingFromAttrs = False
    self.tooltip:CreateToolTip|None = None
    self.markerDecoratorOffset=0
    self.dragInfo:tuple|None = None
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
    
    self.decorators:dict[str, Decorator] = dict()
    self.makeDecorators()
    
    if self.modelObject is not None:
      self.modelObject.addObserver(self)
    
    self.validate()
    
    if view.__dict__.get("_firstDrawsDeferred"): # (read with its view: drawn with it -- see _firstDraw() -- or when it's put back, if it's been taken out)
      self.__dict__["_firstDrawPending"] = True
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
    if self.view.__dict__.get("_firstDrawsDeferred") or self.__dict__.get("_drawnWithView"):
      return # (a view being read draws everything at once, when it's built -- whether that's before or after this: see SNGView._drawAllAfterRead())
    if not self._isConnected():
      self.__dict__["_firstDrawPending"] = True
      return
    self.__dict__["_firstDrawPending"] = False
    self.view.freshPaint()
    self.draw()
    self.makeBindings()
    
  # ---- PERSISTENCE -----------------------------------------------------------
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    from sn.view.graphics.sngView import SNGView
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("view", SNGView, lambda slf: cast(VObject, slf).view),
                     ParamInfo("modelObject", str, lambda slf: slf.modelObject.getPRef().tostring(slf.view.model) #type: ignore[attr-defined]
                               if slf.modelObject is not None #type: ignore[attr-defined] # (missing from its model -- eg: deleted from it while the view was closed: still missing, as read)
                               else getattr(slf, "readModelObjectRef", ""))],
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
                                         lambda slf, v: setattr(slf, "expandedHeight", int(v) or None), # type: ignore[arg-type]
                                         optional=True)],
            finalSetters=[]
            )

  # ---- GETTERS AND SETTERS ---------------------------------------------------

  @property
  @override
  def name(self)->str:
    n = "?" if self.modelObject is None else self.modelObject["name"]
    return str(n)
    
  @property
  def modelObject(self) -> GraphObject|None:
    '''
    :returns: The corresponding model object.
    :raises ReferenceError: if there is not corresponding model object (deleted?)
    '''
    return self._modelObject
  
  @property
  def relations(self) -> Iterator[VRelation]:
    '''
    The relations to and from this object.
    '''
    for vo in self._incoming + self._outgoing:
      yield vo

  def boundingBox(self, rect:list[int]|None=None, fast=False) -> list:
    '''
    Returns or sets the bounding box for the *VObject* in [minX, minY, maxX, maxY]
    form.  Checks *rect* for sanity (coordinates may be negative: the canvas
    extends every way -- see *SNGView.resetScrollRegion()*).
    
    The bounding box is strictly tracked by the *self.shape()* object. Thus, if 
    you change the boundingBox, this method assures that shape object tracks it
    (along with any decorators).
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
        bb:list = self._boundingBox
        minX = self.cache['vis/minSize']
        if bb[2]-bb[0] < minX:
          bb[2] = bb[0]+minX
        minY = self.minHeight()
        if bb[3]-bb[1] < minY:
          bb[3] = bb[1]+minY
      
      self.setDirty()

    return self._boundingBox

  def isHidden(self) -> bool:
    '''
    True iff this isn't drawn just now: it's in a hidden category (see
    *SNGView.visibility()*), or depends on something that is, or goes without
    saying (eg: a containment drawn as being inside a window). See
    *SNGView.shouldHide()*.
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
      dependents:list[VObject] = [r for r in self.relations if r is not self]
      if self.isContextWindow():
        dependents += self.windowContents()
      c.after_idle(lambda: [d._applyHidden() for d in dependents if d._isConnected()]) # type: ignore[func-returns-value]

  def _hideItems(self) -> None:
    '''
    Hide all this one's canvas items, noting each one's state first (some are
    deliberately "disabled"), for *_showItems()*. The note is kept here, not
    as canvas tags: redraws reset items' tags (eg: connectors.\\_upsertLine()).
    Put off to the end, within *SNGView.batchedItemStates()*.
    '''
    self.__dict__["_itemsHidden"] = True # (for _showItems())
    pending = self.view.__dict__.get("_pendingItemStates")
    if pending is not None:
      pending[id(self)] = (self, True)
      return
    for i in self.canvas.find_withtag(self.tag):
      self._hideItem(i)

  def _hideItem(self, i:int) -> None:
    '''
    :param i: One of its canvas items: hidden, noting its state (see *_hideItems()*).
    '''
    c = self.canvas
    state = c.itemcget(i, "state")
    if state != "hidden":
      self.__dict__.setdefault("_priorStates", {})[i] = state
      c.itemconfigure(i, state="hidden")

  def _showItems(self) -> None:
    '''
    Undo *_hideItems()*: every hidden item of this one's goes back to its noted
    state (items made while hidden were noted when they were hidden). Nothing
    else hides a VObject's items, so all of them are shown. Put off to the
    end, within *SNGView.batchedItemStates()*.
    If none of its items was ever hidden (the usual case: eg: every redraw of
    a relation), it's skipped: looking its items up searches the whole canvas,
    which made showing all of a big model quadratic.
    '''
    pending = self.view.__dict__.get("_pendingItemStates")
    if not self.__dict__.get("_itemsHidden") and (pending is None or id(self) not in pending):
      return
    if pending is not None:
      pending[id(self)] = (self, False)
      return
    self.__dict__["_itemsHidden"] = False
    for i in self.canvas.find_withtag(self.tag):
      self._showItem(i)
    self.__dict__.get("_priorStates", {}).clear()

  def _showItem(self, i:int) -> None:
    '''
    :param i: One of its canvas items: shown again, as it was (see *_showItems()*).
    '''
    c = self.canvas
    prior:dict[int, str] = self.__dict__.get("_priorStates", {})
    if c.itemcget(i, "state") == "hidden":
      c.itemconfigure(i, state=prior.pop(i, ""))

  def labelText(self) -> str:
    '''
    What this one's label says: its label template (see *labels*) expanded --
    its "vis/label" attribute if it has one, else the "gui/label" preference
    ("gui/relationLabel" for relations). A template that can't be expanded
    gives the name, with a warning.
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
      return expand(str(template), labelLookup(mo), self.templateCall("vis/label")).strip()
    except TemplateError as ex:
      logger.warning(f'{mo.name}: bad label template: {ex}')
      return (mo.name or "").strip()

  def templateCall(self, key:str) -> Callable[[str], str]:
    '''
    :param key: The attribute (or preference) the template's from: eg: "vis/tooltip".
    :returns: The *call* for *labels.expand()*: what a hook returns, called on
      its model object (see *sn.hooks*), as a string ("" for None, or if it
      can't be called).
    '''
    def call(ref:str) -> str:
      ret = hooks.call(ref, self.modelObject, HookContext(key=key, vobject=self, view=self.view))
      return "" if ret is None else str(ret)
    return call

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
    '''
    bb = list(self.boundingBox())
    if self.collapsed:
      bb[3] = bb[1] + (self.expandedHeight or self.WINDOW_DEFAULT[1])
    return bb

  def toggleAt(self, x:float, y:float) -> bool:
    '''
    Whether (x, y) (view coords) is on a context window\'s collapse/expand triangle.
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
    '''
    return bool(getattr(self.modelObject, "inferred", False))

  def isContextWindow(self) -> bool:
    '''
    True iff this is drawn as a window: an individual context -- a rule,
    query, ... (not the context/rule/query types themselves). See
    *decorators.ContextFrame*.
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
    How tall a context window's banner (its title bar) is.
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
    '''
    for name, (x1, y1, x2, y2) in self.panes().items():
      if x1 <= pt[0] <= x2 and y1 <= pt[1] <= y2:
        return name
    return None

  def containmentOf(self, obj) -> list:
    '''
    The model relations by which this context contains *obj* (a model object).
    '''
    mo = self.modelObject
    if mo is None or obj is None:
      return []
    contains = mo.model.CONTAINS
    return [r for r, _ in mo._getOutgoing(lambda r: r.isIndividual() and r.isa(contains) and r.localDst is obj)]

  def windowContents(self) -> list[VObject]:
    '''
    The view objects this context contains that sit inside its window.
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
    '''
    if not self.isContextWindow():
      return []
    homes = self.view.containmentHomes()
    ret = [vo for vo, (w, _) in homes.items() if w is self]
    return ret + [vo for vo in self.windowContents() if vo not in homes and vo not in ret]

  def isResizable(self) -> bool:
    '''
    False iff "vis/minSize" == "vis/maxSize": the size is fixed, so it can\'t be resized by hand. (Windows always can be.)
    '''
    return self.isContextWindow() or self.cache['vis/minSize'] != self.cache['vis/maxSize']

  def minHeight(self) -> float:
    '''
    The smallest height (view units) the bounding box may have: "vis/minSize" *
    "vis/aspectRatio" (*NOMINAL_ASPECT* if that's 0), but never less than one
    line of text.
    '''
    ret = self.cache['vis/minSize'] * (self.cache['vis/aspectRatio'] or NOMINAL_ASPECT)
    text = self.decorators.get("text") if getattr(self, "decorators", None) else None
    if isinstance(text, WrappingText) and self.modelObject is not None:
      ret = max(ret, text.lineHeight())
    return ret

  def shape(self, c:str|None=None):
    '''
    :param c: [str, default=None] The name of the new shape.
    :return: [str] The name of this object's (possibly changed) shape.
    :except Exception: if *c* is not the name of a known shape.
    
    If *c* is given, make self's shape the corresponding *Shape*. 
    
    Used by draw() when the shape is changed.
    '''
    if c is not None and c != type(self._shape).__name__:
      newShape = None
      try:
        newShape = self.strToShape(c)
      except Exception as ex:
        logger.warning(f'Shape "{c}" is not known: {ex}')
      if newShape is not None:
        self.killBindings()
        oldShape = self._shape
        self._shape = newShape
        self._shape.draw()
        self.canvas.lift(newShape.id, oldShape.id)
        oldShape.delete()
        self.makeBindings()
      self.setDirty()
    return type(self._shape).__name__ if self._shape is not None else None
  
  # ---- OBSERVER INTERFACE ----------------------------------------------------
    
  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]]) -> None:
      """
      Receive update from subject.
      """
      if getattr(self.view, "_closed", False): # (sent before the view's window closed: see SNGView.detachFromModel())
        return
      try: # if this is a deletion, the object will fail validation on access
        assert subject is self.modelObject
      except Exception:
        logger.exception(f'{self.name}.update({subject}, {topics}): Unexpected subject.')
        return
      vChanged = False
      for topic in topics:
        topicName = topic[0]
        if topicName == "new attribute" or topicName == "mod attribute": # no point in changing an object we're removing!
          attname, value = topic[1]
          if attname in VATTRIBUTES:
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
        else:
          logger.warning(f'{self.name}: Unknown update({self.modelObject.name}, {topic})')
        
      if vChanged:
        self.view.freshPaint()
        self.draw() 

  def validate(self) -> list[str]:
    '''
    Populates (or clears) the *self.errors* list.
    '''
    try:
      self.assertToStatusReport(self.modelObject is not None, 
        f'Model object is missing from Model: {self.readModelObjectRef if hasattr(self, "readModelObjectRef") else ""}'
        + (f' ({self.__dict__["_missingReason"]})' if self.__dict__.get("_missingReason") else ""), "E", 
        actions={"erase view object": lambda: [self._disconnect(), self.view.setDirty(), None][-1]}) #check model object is there.
      if self.modelObject is not None:
        model:GraphObject = self.modelObject
        for n in self.view.viewObjectsFor(model): # check for other objects referencing this one's model object
          if n is not self: # (the message only when it's needed: it's costly, and this is done for every object in the view)
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
          {"view trace": lambda trace=trace, ex=ex: showExceptionDialog(self.canvas.winfo_toplevel(), title=ex.__class__.__name__, text=trace)}) # type: ignore[misc]
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
            lambda o=obj, c=required: self.view.context.new_relation([self.view.model.ISA], individual=True, # type: ignore[misc]
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

    :returns: label -> action.
    '''
    from sn.model import names
    mo = self.modelObject
    ret:dict[str, Callable[[], None]] = {}
    if mo is None or not self.view.isModelEditor():
      return ret
    def then(fix:Callable[[], Any]) -> Callable[[], None]:
      def go() -> None:
        try:
          fix()
        except Exception as ex:
          logger.error(f'{mo.name}: {ex}')
          return
        self.view.reasonSilently()
      return go
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
    self.tooltip = CreateToolTip(self.canvas, self.tooltipFunc, self._shape.id, 
                                 waitTime=1000, wrapLength=self.tooltipWrap, background="#FFFFC0", # type: ignore[arg-type] # (CreateToolTip takes a callable too)
                                 font=self.tooltipFont)
    
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
    '''
    self.canvas.configure(cursor="hand2")
    
  def onLeave(self, event):
    '''
    :param event: The Tk event.
    '''
    self.canvas.configure(cursor="arrow")
    
  def onRightMouse(self, event):
    """
    Creates and displays the node specific menu at the clicked location -- or,
    in the body of a (expanded) context window, the menu for making things in
    the pane clicked in (see *SNGView.addNewObjectMenus()*), as the
    background's makes them there: the window's own menu is on its title bar.

    :param event: The Tk event.
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
    """
    from sn.view.graphics.layout import finishTween
    finishTween(self.view) # (a layout's smooth move under way: done, before this is picked up)
    # Cmd-press: the view pans, Option-press: it zooms (see SNGView.onButton_1()),
    # so leave the press to the canvas; a Cmd-click that doesn't drag still
    # toggles this one's selection
    if s_CMD(event.state) or s_ALT(event.state):
      self.dragInfo = None
      self.view._panClicked = self
      return None
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
    winX = self.canvas.canvasx(event.x) # convert widget-relative coords to canvas coords (accounts for scroll position)
    winY = self.canvas.canvasy(event.y)
    r = self.boundingBox()
    self.dragInfo = (r[0], r[1], winX, winY, False) # x,y,press-x,press-y (canvas coords),no-drag-motion-event
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
    self.dragStartCenters:dict["VObject", tuple[float,float]|None] = {}
    self.dragAlong:set["VObject"] = set()
    "The relations that only move because their ends do."
    for n in movedSet:
      for vo in [n, *([] if n.isContextWindow() else n.relations)]:
        self.dragStartCenters.setdefault(vo, vo.centerPt())
        if vo is not n and vo not in movedSet:
          self.dragAlong.add(vo)
    # (put back on the release, drag or click -- see onB1_ButtonRelease())
    self.old_suppressLocalLayout = self.view.suppressLocalLayout()
    self.view.suppressLocalLayout(True)
    return 'break'

  def onB1_Motion(self, event):
    """
    The mouse is moving while being captured by this node, so if we had clicked to start
    accepting events, just move the node to track the event, updating *self.dragInfo*.

    :param event: The Tk event.
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
      # How far the pointer's gone since the press, in view units (canvas
      # coordinates are zoomed: at 200% a pixel is half a view unit). Each
      # object goes to where it started plus that -- not moved by each tick's
      # step, which (positions being whole numbers) loses the fractions, and
      # the object falls behind the pointer.
      dX, dY = self.view.windowToView(winX - self.dragInfo[2], winY - self.dragInfo[3])
      self.view.freshPaint()
      # allowOverScrollRegionSE=True: a live drag needs to actually be able to
      # cross the SE edge of the current scroll region -- moveTo() otherwise
      # clamps to it unconditionally, which would mean the bounding box could
      # never exceed the region and draw()'s scroll-region-growth check
      # (self.view.resetScrollRegion()) could never fire.
      for n, start in self.dragStartPositions.items():
        n.moveTo(round(start[0] + dX), round(start[1] + dY), adjustPos=False, fast=False, allowOverScrollRegionSE=True)
      self.dragInfo = (*self.dragInfo[:4], True) # x,y,press-x,press-y,drag-motion-event-occurred
      return 'break'


  def onDouble_1(self, event):
    '''
    A double-click: the hook its model object's *DOUBLE_CLICK* attribute
    names (eg: set on its type), if it has one that can be called, and applies
    to it (see *sn.hooks*); else its attributes, in the attribute editor -- as "edit
    attributes" (or "show attributes": see *attributesReadOnly()*) on its
    menu. (Not on a context window's collapse triangle: that's two toggles.)

    :param event: The Tk event.
    '''
    self.view.addEventHandled(event)
    self.dragInfo = None
    if self.modelObject is None or self.toggleAt(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)):
      return 'break'
    ref = self.modelObject.get(self.DOUBLE_CLICK, None)
    if hooks.isReference(ref) and hooks.resolve(ref) is not None:
      context = self.hookContext(self.DOUBLE_CLICK)
      if hooks.applies(ref, self.modelObject, context):
        hooks.call(ref, self.modelObject, context)
        return 'break'
    self.onEditAttributes(disabled=self.attributesReadOnly())
    return 'break'

  def onB1_ButtonRelease(self, event): #reset data on release
    """
    Button one was released. If it was a drag, it was a move, and everything is fine except
    we call self.adjustPos() which may resolve overlap conflicts. If it was a click (no
    intervening <B1_Motion> events), toggle the selection state of the node.

    :param event: The Tk event.
    """
    # Whatever the press was for, put back the suppression state it changed
    # (see onButton_1()) -- for a click too, and for the second press of a
    # double-click (which clears dragInfo): left suppressed, the animation
    # layout thinks something's still being dragged, and stands still for good.
    # For a drag, that's before the final move below, so that the release-time
    # moveTo() (adjustPos defaults to True) is free to run FindFree and resolve
    # any overlaps -- that's the "everything is fine except..." comment below:
    # the one point in a drag where we actually want the full layout
    # resolution to run.
    if "old_suppressLocalLayout" in self.__dict__:
      self.view.suppressLocalLayout(self.__dict__.pop("old_suppressLocalLayout"))
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
        # A multi-selection drag moved every object in self.view.selected (see
        # onB1_Motion()), so each one's move is recorded -- all in one
        # CompositeCommandMgr, so one undo()/redo() moves the whole group, as
        # the drag did.
        #
        # _oldPos=... : each object's true pre-drag position (captured in
        # onButton_1(), before any <B1-Motion> tick moved anything), given to
        # _Move explicitly: its boundingBox() at do()-time is where the drag
        # ended, not where it started (see _Move's _oldPos in sngContext.py).
        movedObjects = self.view.selected if self.selected() else [self]
        with CompositeCommandMgr(self.view.context):
          for n in movedObjects:
            bb = n.boundingBox()
            startPos = self.dragStartPositions.get(n, bb)
            self.view.context.move(n, bb[0], bb[1], _oldPos=startPos, _drag=True)
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
    Its context menu: its hooks' items, the model-editing ones (in a model editor), and the view's.
    '''
    m = tk.Menu(self.canvas)
    if True: #app.DEBUG_MENUS:
      if self.modelObject is None:
        mtitle = "None"
      else:
        mtitle = f'#{self.modelObject.id}?name="{self.modelObject.name}"'
      m.add_command(label=f'#{self._id} -> {mtitle}', state=tk.DISABLED)
      m.add_separator()
    if self.addHookMenuItems(m):
      m.add_separator()
    editable = self.view.isModelEditor()
    if editable:
      self.addModelEditingMenuItems(m)
      m.add_separator()
    elif self.modelObject is not None:
      m.add_command(label="show attributes", command=lambda: self.onEditAttributes(disabled=True))
      m.add_command(label="(the model can't be changed in this view)", state=tk.DISABLED)
      m.add_separator()
    self.addViewMenuItems(m)
    if len(self._statusReport)>0:
      def show(slf):
        pass
      m.add_command(label='show error report', command=lambda slf=self: [slf.clearStatusReport(), self.validate(), slf.showErrorActionDialog(slf.canvas.winfo_toplevel())]) # type: ignore[misc]
    if snPrefs.get("debug", False):
      m.add_separator()
      def validate(o:VObject=self) -> None:
        n = len(o.validate())
        if n == 0:
          logger.info(f'"{o.name}": No errors detected.')
        else:
          logger.warning(f'"{o.modelObject.name}": detected {n} errors.') # type: ignore[union-attr]
        o.view.freshPaint()
        o.draw()
      m.add_command(label="validate", command=validate)
      def refreshCache() -> None: # (and redraw it, to show what's refreshed)
        self.cache.refresh(verbose=True)
        self.view.freshPaint()
        self.draw()
      m.add_command(label="refresh cache", command=refreshCache)
    return m
    
  def _systemLocked(self) -> bool:
    '''
    :returns: Whether its model object can't be edited here: it's a system
      object (unless "gui/allowEditingSystemObjects"), or the view isn't a
      model editor.
    '''
    mo = self.modelObject
    return mo is None or (mo.isSystemObject() and not snPrefs.get("gui/allowEditingSystemObjects", storeDefault=False)) \
           or not self.view.isModelEditor()

  def attributesReadOnly(self) -> bool:
    '''
    :returns: Whether its attributes can only be looked at, not edited: it's
      inferred (see *isInferred()*), a system object (see *_systemLocked()*), or
      from another model than the view's.
    '''
    mo = self.modelObject
    return mo is None or self.isInferred() or self._systemLocked() or self.view.model is not mo.model

  def addModelEditingMenuItems(self, menu:tk.Menu):
    '''
    Add the items for editing its model object to *menu* (just looking, for an inferred object).
    '''
    mo = self.modelObject
    if mo is None:
      return
    if self.isInferred(): # (the reasoner's: it can only be looked at, or made asserted -- see GraphObject.inferred)
      menu.add_command(label="show attributes", command=lambda: self.onEditAttributes(disabled=True))
      locked = mo.model.writeLocked()
      menu.add_command(label="mark as asserted" + (" (the model is write-locked)" if locked else ""),
                       state=tk.DISABLED if locked else tk.NORMAL,
                       command=lambda: self.view.context.mark_asserted(mo))
      menu.add_separator()
      return
    disabled = self._systemLocked()
    relInst =  mo.isIndividual() and isinstance(mo, Relation)
    remote = self.view.model != mo.model
    readOnly = self.attributesReadOnly()
    menu.add_command(label=f"{'show' if readOnly else 'edit'} attributes",
                     command=lambda: self.onEditAttributes(disabled=readOnly))
    if mo.isType():
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

  MENU_PREFIX = ".menu/"
  '''The start of the attributes that add items to an object's menu (see
  *addHookMenuItems()*): eg: ".menu/Show source", or ".menu/Source/Open" (in a
  "Source" submenu).'''

  DOUBLE_CLICK = ".doubleClick"
  "The attribute naming a hook run on a double-click, instead of showing the attributes (see *onDouble_1()*)."

  def hookContext(self, key:str) -> HookContext:
    '''
    :param key: The attribute naming the hook: eg: ".menu/Show source".
    :returns: How a hook's used from this object (see *sn.hooks*).
    '''
    return HookContext(key=key, vobject=self, view=self.view, selection=self.selectionOrSelf())

  def addHookMenuItems(self, menu:tk.Menu) -> bool:
    '''
    Add an item to *menu* for each of its model object's *MENU_PREFIX*
    attributes -- its own, and those it inherits (eg: from a type, for all its
    instances) -- calling the hook its value names (see *sn.hooks*), sorted
    by path: a "/" in the path makes a submenu. One whose hook doesn't apply to
    it (see *sn.hooks.applies()*: eg: one meant for a type's instances, on the
    type) is left out; one whose hook can't be called (eg: its module isn't
    trusted) is there, but disabled (why is logged).

    :returns: Whether it added any.
    '''
    mo = self.modelObject
    if mo is None:
      return False
    found = {path: ref for path, ref in hooks.hookAttributes(mo, self.MENU_PREFIX).items()
             if hooks.applies(ref, mo, self.hookContext(self.MENU_PREFIX + path))}
    submenus:dict[str, tk.Menu] = {}
    for path, ref in found.items():
      *folders, label = [p.strip() for p in path.split("/")]
      parent, sofar = menu, ""
      for f in folders:
        sofar += "/" + f
        if sofar not in submenus:
          submenus[sofar] = tk.Menu(parent)
          parent.add_cascade(label=f, menu=submenus[sofar])
        parent = submenus[sofar]
      key = self.MENU_PREFIX + path
      parent.add_command(label=label or path,
                         state=tk.NORMAL if hooks.resolve(ref) is not None else tk.DISABLED,
                         command=lambda r=ref, k=key: hooks.call(r, mo, self.hookContext(k))) # type: ignore[misc]
    return bool(found)

  def selectionOrSelf(self) -> list[VObject]:
    '''
    :returns: What a menu item acts on: everything selected, if this is; else just this.
    '''
    if self.selected():
      return [vo for vo in self.view.selected if vo._isConnected()]
    return [self]

  def copySelection(self, cut:bool=False, picture:bool=False) -> None:
    '''
    Copy (or cut) what's selected, if this is; else just this (see
    *SNGView.doCopy()*) -- or copy a picture of it (see *SNGView.doCopyImage()*).
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
    :param negative: With *on*: in the "negative" colour (eg: a query with no answers).
    :returns: Whether it's highlighted.
    '''
    if on is True and "highlight" in self.decorators and cast(Highlight, self.decorators["highlight"]).negative != negative:
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
    mo = self.modelObject
    assert mo is not None
    if self.view.reasoning is None: # (so what the rules conclude exists is in the model, for the answers to show)
      self.view.reasonSilently()
    for w in queryWarnings(mo):
      logger.warning(w)
    try:
      rows = Reasoner.create(self.view.model).answer(mo)
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
    :returns: The relations (asserted or inferred) the answer matched: for each
      relation in the query's pattern, those of its type (or a subtype) between
      what its ends stand for in *row*.
    '''
    from sn.model.reasoner import patternOf
    byName = {k.name: v for k, v in row.items()}
    value = lambda x: byName.get(x.name) if x is not None and x.isVariable() else x
    ret:list[Relation] = []
    assert self.modelObject is not None
    for t, s, d in patternOf(self.modelObject).triples:
      T, S, D = value(t), value(s), value(d)
      if not (isinstance(T, GraphObject) and isinstance(S, GraphObject) and isinstance(D, GraphObject)): # (an open end, or an object only the reasoner knows of)
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
    '''
    def relTypes(model) -> list[Relation]:
      return sorted((r for r in model.values() if isinstance(r, Relation) and r.isType() and not r.isVariable()), # (a pattern's ?r isn't a type to make)
                    key=lambda r: r.name.lower())
    def add(menu:tk.Menu, r:Relation) -> None:
      menu.add_command(label=r.name, command=lambda r=r: self.view.makeRelationFrom(self, r)) # type: ignore[misc]
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
    Make a subtype (or, if *individual*, an instance) of its model object.
    '''
    raise NotImplementedError("Must implement VObject.makeSubtypeMenuItemFun().")
    
  def addViewMenuItems(self, menu:tk.Menu):
    '''
    Add the view's items to *menu*: expand, erase, and so on.
    '''
    targets = self.selectionOrSelf()
    n = len(targets)
    also = [vo for vo in targets if vo is not self] # (expanded with it: see expand())
    selected = f", {n} selected" if n > 1 else ""
    expMenu = tk.Menu()
    expMenu.add_command(label="1 level" , command=lambda: self.view.context.expand(self, also=also))
    expMenu.add_separator()
    expMenu.add_command(label="2 levels", command=lambda: self.view.context.expand(self, levels=1, also=also))
    expMenu.add_command(label="3 levels", command=lambda: self.view.context.expand(self, levels=2, also=also))
    expMenu.add_command(label="4 levels", command=lambda: self.view.context.expand(self, levels=3, also=also))
    rels = removeDuplicateObjects([r for vo in targets for r in vo.expandableRelations()])
    menu.add_cascade(menu=expMenu, label=f"expand all ({len(rels)}{selected})")
    menu.add_command(label="expand by relation..." + (f" ({n} selected)" if n > 1 else ""), command=self.expandByRelation)
    menu.add_command(label="erase from view" + (f" ({n} selected)" if n > 1 else ""), accelerator="Delete",
                     command=lambda: self.view.doErase(self.selectionOrSelf()))
    menu.add_command(label="erase everything else" + (" (keep the selection)" if n > 1 else ""),
                     command=lambda: self.view.doEraseOthers(self.selectionOrSelf()))
    mo = self.modelObject
    if mo is not None and mo.isa(mo.model.CONTEXT) and mo is not mo.model.CONTEXT:
      menu.add_command(label="answer query", command=self.answerQuery)
    if mo is not None and mo.isIndividual() and (mo.isa(mo.model.RULE) or mo.isa(mo.model.DEFINITION)):
      menu.add_command(label="show conclusions", command=self.showConclusions)
    if "disabled" in self.decorators and mo is not None:
      disabled = mo.isDisabled()
      menu.add_command(label="enable" if disabled else "disable",
                       state=tk.DISABLED if mo.model is not self.view.model or not self.view.isModelEditor() else tk.NORMAL,
                       command=lambda: self.view.context.set_attribute(mo, GraphObject.DISABLED, not disabled))
    if self.isContextWindow():
      menu.add_command(label="gather", command=lambda: self.view.gatherIntoWindow(self))
    if isinstance(self.decorators.get("text"), WrappingText):
      menu.add_command(label="fit to text", command=self.fitToText,
                       state=tk.NORMAL if self.userSized else tk.DISABLED)
         
  def onEditAttributes(self, disabled:bool=False):
    '''
    Show its model object's attributes in an editor (*disabled*: just to look), and make the changes made
    there.
    '''
    mo = self.modelObject
    assert mo is not None
    edits = editAttrsBox(self.canvas, mo, title=str(mo), disabled=disabled)
    if not disabled and edits is not None:
      nameEdit = edits.get("name") # (the editor returns Attributes)
      typed = nameEdit.value if isinstance(nameEdit, Attribute) else nameEdit
      if isinstance(typed, str) and WHERE in typed:
        edits = self._whereEdits(edits, nameEdit, typed)
      if not edits:
        return
      with CompositeCommandMgr(self.view.context):
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
    '''
    mo = self.modelObject
    assert mo is not None
    name, text = splitWhere(typed)
    ret = {k: v for k, v in edits.items() if k != "name"}
    if not names.isVariableName(name):
      logger.error(f'"{typed}": only variables have constraints ({names.grammar.describe()}). The name wasn\'t changed.')
      return ret
    base = edits.get(CONSTRAINTS)
    base = (base.value if isinstance(base, Attribute) else base) if CONSTRAINTS in edits else mo.getLocal(CONSTRAINTS, None)
    try:
      merged = mergeConstraints(base, text or "") # type: ignore[arg-type]
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

  def draw(self, fast=False, **kwargs):#, rect=None):
    '''
    Draw it (or draw it again), with its decorators -- unless it's been drawn since the view last changed, or
    it's out of the view.
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
    # size the box to its text first, so the shape is drawn at the new size -- for the shape it'll be
    # drawn as (the room for the text depends on it): eg: its type's "vis/shape", when it's first drawn
    text = self.decorators.get("text")
    if not fast and isinstance(text, WrappingText):
      if self._shape is not None:
        self._shape.checkShape()
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
        floats = lambda vo: callable(getattr(vo, "floating", None)) and vo.floating()
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
      # adjustPos()/FindFree overlap resolution at that spot: skipping it
      # would leave two objects dropped on top of each other stacked.
      return
    self.boundingBox([x, y, x+bb[2]-bb[0], y+bb[3]-bb[1]])
    if adjustPos:
      #The traditional way 
      self.adjustPos(fast=fast)
      
    if not fast:
      for r in self.relations:
        # Pass adjustPos through: during a live drag (adjustPos=False) relations
        # should still visually track this node's new position, but shouldn't
        # each run their own full adjustPos()/FindFree placement on every single
        # mouse-motion tick (which makes big visual jumps while dragging). The
        # full layout resolution happens once, when moveTo()
        # is called with the default adjustPos=True (e.g. on button-release).
        r.notifyNodeMove(self, adjustPos=adjustPos)

    self.view.freshPaint()
    self.draw()
    self.setDirty()
    
      
  def moveBy(self, dx, dy, *, allowOverScrollRegionSE=False, adjustPos=True, fast=False, carry=True):
    '''
    :param carry: Whether a context window carries what's inside it along (see *moveTo()*).
    :type carry: bool
    '''
    bb = self.boundingBox(fast=fast)
    x = bb[0]+dx
    y = bb[1]+dy
    self.moveTo(x, y, allowOverScrollRegionSE=allowOverScrollRegionSE, adjustPos=adjustPos, fast=fast, carry=carry)
    
  def moveToCenterOn(self, x, y, adjustPos=True, fast=False):
    '''
    Move it so its centre is at (*x*, *y*) (see *moveTo()*).
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
    """
    r = self.boundingBox()
    return (int((r[0]+r[2])/2), int((r[1]+r[3])/2))

  def containsPt(self, pt):
    '''
    Whether *pt* is inside its shape.
    '''
    return pointInPoly(pt, self._shape.points())
    
  def adjustPos(self, aggressive:bool=False, fast=False) -> tuple[int,int]:
    '''
    Put it somewhere suitable by the view's dynamic layout, and its relations' labels too: where it is then
    (its top left).
    '''
    if fast:
      bb = self.boundingBox(fast=fast)
      return bb[0], bb[1]
    
    # use a regular layout  
    layout = self.view.localLayout
    if layout is not None and not self.__dict__.get("_placedLater"):
      layout(self, aggressive=aggressive)
      for r in self.relations: # (their labels, which follow their ends: not relation types -- they have places of their own, as nodes do)
        if (r.modelObject is None or not r.modelObject.isType()) and not r.__dict__.get("_placedLater"):
          layout(r, aggressive=aggressive)
    rect = self.boundingBox(fast=fast)
    
    return rect[0], rect[1]
    

  BATCH_PLACED = 20
  '''The most new nodes an expansion has the view's dynamic layout place one by
  one (see *expand()*): more are placed all at once.'''

  def expand(self, 
             filter:Callable[[Any, Relation], bool]=lambda _vn, _mr: True, 
             expand=0,
             _done:dict[int, int]|None=None,
             _exempted:list|None=None,
             also:Iterable[VObject]=()):
    """
    Show this object's relations that aren't shown yet (and so what's at their
    other ends) -- and, if *expand* > 0, expand each object at the other end of
    each of its relations (shown already or not) in turn, by *expand* - 1. So 0
    shows this object's neighbours, 1 their neighbours too, and so on. Each of
    *also* (eg: the rest of the selection) is expanded the same way, in the
    same pass: what they bring in is placed with what this one does.

    What it brings in is placed by the view's dynamic layout, if it has one
    (see *SNGView.localLayout*), once it's all made: up to *BATCH_PLACED*
    nodes one by one, as anything new is (see *SNGView._placeNew()*); more
    all at once -- the nodes (see *layout.LayoutHeuristic.placeBatch()*),
    then, once they're put between their ends, the relations' labels (see
    *layout.LayoutHeuristic.placeLabels()*). One by one, each is placed
    clear of everything placed before it, which for thousands takes minutes.

    :param filter: Optional[Callable[[Self, Relation], bool]] A function *selfxRelation->bool*
        where that relation will only be expanded if the function returns *True* 
    :param expand: [Optional[int], default=0] The number of hops to expand beyond this
      object's neighbours.
    :type expand: int
    :param _done: (Internal) The objects expanded so far in this expansion
      (by *id()*), and by how many more hops: none is done twice to the same
      depth or less, as an expansion would otherwise grow exponentially with
      the depth (going back and forth along each relation, round each cycle).
    :param _exempted: (Internal) If *filter* has a true "showsHidden" (see
      *expandDialog.choiceFilter()*: relation types asked for by name), the
      relations it follows are followed even in a hidden or erased category,
      and they and what they lead to are shown anyway (see
      *SNGView._exemptIfFiltered()*): each one shown so is added to this, so
      it can be hidden again (eg: on an undo).
    :param also: Other objects to expand with this one (see above).
    """
    from sn.view.graphics.vrelations import VRelation
    from sn.view.graphics.viewCommands import ViewDoList
    view = self.view
    layout = view.localLayout
    def expandAll(done:dict[int, int]) -> None:
      for vo in [self, *also]:
        if vo._isConnected():
          vo._expand(filter, expand, done, _exempted)
    if _done is not None or layout is None or not view.canvas or view.reading:
      expandAll({} if _done is None else _done)
      return
    had = {id(vo) for vo in view.values() if vo is not None}
    view.localLayout = None # type: ignore[assignment] # (nothing's placed as it's made -- see SNGView.makeViewObjectForGraphObject(): it's placed below)
    try:
      expandAll({})
    finally:
      view.localLayout = layout
    made = [vo for vo in view.values() if isinstance(vo, VObject) and id(vo) not in had and vo._isConnected()]
    nodes = [vo for vo in made if not isinstance(vo, VRelation) and not vo.isHidden()]
    if len(nodes) <= self.BATCH_PLACED:
      for vo in nodes: # (as they'd have been placed as they were made)
        under = view._newObjectLocation(vo.modelObject)[2] # type: ignore[arg-type]
        view.canvas.after_idle(lambda vo=vo, under=under: view._placeNew(vo, under)) #type: ignore[misc]
      return
    labels = [vo for vo in made if isinstance(vo, VRelation) and (vo.modelObject is None or not vo.modelObject.isType())]
    for r in labels: # (not placed one by one when they're first put between their ends: see adjustPos())
      r.__dict__["_placedLater"] = True
    layout.placeBatch(nodes, self)
    def placeLabels() -> None:
      for r in labels:
        r.__dict__.pop("_placedLater", None)
      if view.localLayout is not layout or not view.canvas:
        return
      layout.placeLabels([r for r in labels if r._isConnected() and not r.isHidden()])
      if isinstance(view.context.doList, ViewDoList): # (the layout keeps them arranged with the rest, now they're here)
        view.context.doList.adjustAgain()
    view.canvas.after(0, placeLabels) # (after each is first put between its ends: queued as it was made -- see VRelation)

  def _expand(self, filter:Callable[[Any, Relation], bool], expand:int, _done:dict[int, int], _exempted:list|None) -> None:
    '''
    *expand()*, but nothing it makes is placed: what's made is left where it's made.
    '''
    from sn.view.graphics.vrelations import VRelation
    mo = self.modelObject
    if mo is None or _done.get(id(self), -1) >= expand:
      return
    _done[id(self)] = expand
    withHidden = bool(getattr(filter, "showsHidden", False))
    rels = self.expandableRelations(filter, withHidden=withHidden)
            
    # show the ones that aren't shown (with what's at their other ends: see VRelation._resolveEnd())
    for r in rels:
      if self.view.findViewObjectForGraphObject(r) is None:
        self.view.makeViewObjectForGraphObject(r)

    if withHidden: # (asked for by name: shown, even in a hidden category -- and what they lead to)
      for r in rels:
        vRel = self.view.findViewObjectForGraphObject(r)
        if not isinstance(vRel, VRelation):
          continue
        for vo in (vRel, vRel.src, vRel.dst):
          if isinstance(vo, VObject) and vo._isConnected() and vo.modelObject is not None \
              and not vo.categoryExempt and self.view.isFiltered(vo.modelObject):
            self.view._exemptIfFiltered(vo)
            if _exempted is not None:
              _exempted.append(vo)

    if expand > 0: # and on to what's at their other ends
      for r in rels:
        vRel = self.view.findViewObjectForGraphObject(r)
        if not isinstance(vRel, VRelation):
          continue
        other = vRel.dst if vRel.src is self else vRel.src
        if other is not None and other is not self and other._isConnected():
          other._expand(filter, expand - 1, _done, _exempted)

  def expandableRelations(self, filter:Callable[[Any, Relation], bool]=lambda _vo, _r: True, withHidden:bool=False) -> list[Relation]:
    '''
    :param filter: As for *expand()*.
    :param withHidden: Those in hidden or erased categories too.
    :returns: The relations *expand()* follows from this object: its own, in
      and out (and symmetric ones both ways), that *filter* allows -- but not
      (unless *withHidden*) any in a hidden or erased category (see
      *SNGView.visibility()*), nor any that lead to something that is.
    '''
    mo = self.modelObject
    if mo is None:
      return []
    def ok(rel:Relation) -> bool:
      if withHidden:
        return filter(self, rel)
      if self.view.isFiltered(rel):
        return False
      other = rel.localDst if rel.localSrc is mo else rel.localSrc
      return not (other is not None and self.view.isFiltered(other)) and filter(self, rel)
    return removeDuplicateObjects([r for r, _ in mo._getIncoming(filtr=ok)] + [r for r, _ in mo._getOutgoing(filtr=ok)])

  def expandByRelation(self) -> None:
    '''
    "expand by relation...": ask which of its relations to follow, and how
    far (see *expandDialog*), then expand it so (one undo) -- and, if it's
    selected, everything else selected too (the choices are all of theirs).
    '''
    from sn.view.graphics.expandDialog import ExpandDialog
    if self.modelObject is None:
      return
    targets = [vo for vo in self.selectionOrSelf() if vo.modelObject is not None]
    if self not in targets:
      targets.insert(0, self)
    title = f'Expand "{self.name}"' if len(targets) == 1 else f'Expand {len(targets)} selected objects'
    answer = ExpandDialog(self.canvas, title, self.expandChoices(targets)).show()
    if answer is not None:
      filt, levels = answer
      self.view.context.expand(self, levels=levels - 1, _filter=filt, also=[vo for vo in targets if vo is not self])

  def expandChoices(self, targets:list[VObject]) -> list:
    '''
    :returns: The "expand by relation..." choices for expanding *targets* (see
      *expandDialog.relationChoices()*): each one's, with those of the same
      type and way round merged (their counts added up).
    '''
    from sn.view.graphics.expandDialog import relationChoices, OUT, IN, BOTH
    view = self.view
    merged:dict = {}
    for vo in targets:
      mo = vo.modelObject
      if mo is None:
        continue
      hidden = lambda r, mo=mo: view.isFiltered(r) or any(e is not None and e is not mo and view.isFiltered(e) for e in (r.localSrc, r.localDst))
      for c in relationChoices(mo, vo.expandableRelations(withHidden=True), hidden=hidden): # type: ignore[misc]
        key = (id(c.type), c.direction)
        if key in merged:
          merged[key].count += c.count
          merged[key].hidden += c.hidden
        else:
          merged[key] = c
    return sorted(merged.values(), key=lambda c: (c.type.name or "", [OUT, BOTH, IN].index(c.direction))) # (as relationChoices() sorts them)

  def strToShape(self, name):
    '''
    A shape for this object, of the shape class named *name* (a TypeError if there's none).
    '''
    from sn.view.graphics.shapes import Shape
    cls = Shape.getShapeClass(name)
    if cls is not None:
      return cls(self)
    raise TypeError("VNode.strToShape(): Do not know shape class '"+name+"'.")

  def selected(self, val:Optional[bool]=None, _multi:bool=False) -> bool|None:
    '''
    Whether it's selected; with *val*, select it (deselecting the rest, unless *_multi*) or deselect it first.
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

  def tooltipFont(self) -> Any:
    '''
    :returns: The font its tooltip's in: its model object's "vis/tooltipFont"
      (eg: "TkFixedFont", for code; or "Menlo 11"), if it has one; else None
      (Tk's default).
    '''
    try:
      font = self.modelObject.get("vis/tooltipFont", None) if self.modelObject is not None else None
    except ReferenceError:
      return None
    return font if isinstance(font, str) and font.strip() else None

  def tooltipWrap(self) -> int:
    '''
    :returns: The width its tooltip wraps at, in pixels: its model object's
      "vis/tooltipWrap" (0: no wrapping: eg, for code), if it has one; else 250.
    '''
    try:
      wrap = self.modelObject.get("vis/tooltipWrap", None) if self.modelObject is not None else None
      return max(0, int(wrap)) if wrap is not None and not isinstance(wrap, bool) else 250 # type: ignore[arg-type]
    except (ReferenceError, ValueError, TypeError):
      return 250

  def tooltipFunc(self) -> str:
    '''
    What its tooltip says: its tooltip template (see *labels*) expanded -- its
    model object's "vis/tooltip" attribute if it has one (eg: set on its type),
    else the "gui/tooltip" preference -- cut short at "gui/tooltipMaxLines"
    lines. (When debugging: its id too, and its cached drawing attributes.)
    '''
    from sn.view.graphics.labels import expand, labelLookup, DEFAULT_TOOLTIP, TemplateError
    tip = ""
    try:
      mo = self.modelObject
      tip = self.name or ""
      if mo is not None:
        template = mo.get("vis/tooltip", None)
        if not isinstance(template, str) or not template:
          template = snPrefs.get("gui/tooltip", storeDefault=DEFAULT_TOOLTIP, storeType=str) # (its note: see sn.PREFS)
        try:
          tip = expand(str(template), labelLookup(mo), self.templateCall("vis/tooltip")).strip("\n")
        except TemplateError as ex:
          logger.warning(f'{mo.name}: bad tooltip template: {ex}')
      maxLines = snPrefs.get("gui/tooltipMaxLines", storeDefault=40, storeType=int)
      lines = tip.split("\n")
      if isinstance(maxLines, int) and 0 < maxLines < len(lines):
        tip = "\n".join(lines[:maxLines]) + f"\n\u2026 ({len(lines) - maxLines} more lines)"
      if snPrefs.get("debug", storeDefault=False):
        first, nl, rest = tip.partition("\n")
        tip = f'{first} ({self._id}){nl}{rest}'
    except ReferenceError:
      return ""
    if snPrefs.get("debug", storeDefault=False) and snPrefs.get("debug_popupCache", storeDefault=True):
      if len(tip)>0 and tip[-1]!='\n':
        tip += "\n"
      line = "\u2594"*18
      tip += f'{line}\nCACHE:'
      for name in VATTRIBUTES:
        if name in self.cache:
          val = self.cache[name]
          tip += f'\n  "{name}": {str(val)} ({type(val).__name__})'
    return tip
  
  def notifyDecoratorDeletion(self, decorator):
    '''
    *decorator* deleted itself: forget it.
    '''
    self.removeDecorator(obj=decorator)

  def removeDecorator(self, key=None, obj=None):
    """
    :param key: A key in the decorator list.
    :param obj: An actual decorator object.
    
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

  # ---- Debugging support -----------------------------------------------------
  
  @override
  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
    '''
    return self.tostring()
  
  @override
  def tostring(self, relativeTo:"SNGView"|None=None) -> str:
    if self.modelObject is None:
      return f'{self.__class__.__name__}(?, {PReference.formatForURL(self, relativeTo, includeName=False)}, {self.readModelObjectRef if hasattr(self,"readModelObjectRef") else "?"})'
     
    name = self.modelObject.getLocal("name", None)
    if name is None:
      name = f'{UP_ARROW}"{self.modelObject.get("name")}"'
    return f'{self.__class__.__name__}({name}, {PReference.formatForURL(self, relativeTo, includeName=False)}, {self.modelObject.tostring(self.view.model)})'
  
  def __repr__(self):
    '''
    :returns: A string representation of this object.
    '''
    return self.__str__()
