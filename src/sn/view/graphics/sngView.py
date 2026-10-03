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
from sn import snPrefs
import sn
from sn.model.constraints import WHERE, CONSTRAINTS, CONSTRAINTS_NOTE, splitWhere, mergeConstraints, ConstraintError
from util.attribute import Attribute, VAR
from sn.model.model import Model, Node, Relation, Collection, IsaIndividual,\
  GraphObject, GORef
from sn.controller.modelInterface import ModelContext

from typing import cast, override, Any, Iterable, Callable, Optional
from util.utils import bindRightMouse, fixURL, isValidURL, urlExists, expandRect,\
  flattenPairs, s_SHIFT, normalizeRect
from sn.view.graphics.utils import eventEqual, addToMenuBar, addCheckToMenuBar, removeFromMenuBar
from util.terminal import inputAsync
from util.persistence.pRef import PRDb, PReference
from util.observer import Subject, Observer
from util.attributeEditor import applyEditAttrsBox
from sn.view.textUserInterface import UIContext, SNTerminalWidget
from util.command import Command
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import FindFree, gatherShifts
from sn.view.graphics.decorators import NOMINAL_ASPECT
from util.commandParser import CompositeCommandMgr
from util.utils import Categories
from math import sqrt
from util.persistence.serialize import InstantiationInfo, PropertyInfo,\
  ParamInfo, Serializable, SerializableType
from util.persistence.serialize import DEFAULT_STRATEGY
from sn.view.graphics.guiApp import Application, AppWindow
import threading
from util.abstractGraph import AbstractGraph
from util.dirtyable import Dirtyable
from copy import copy
from collections import namedtuple
#from sn.view.graphics.vobjects import VObject

logger:sn.SNLogger = sn.getLogger(__name__)

'''
The Canvas that handles Semantic Nets visual graphics representing objects in
one of more models (but having a single default model).

Created on Aug 21, 2026

@author: robkremer
'''
import tkinter as tk

KEY_UNDO =                  ('<Command-KeyPress-z>'       , 'cmd+z')
KEY_REDO =                  ('<Shift-Command-KeyPress-Z>' , 'shift+cmd+Z')
KEY_REPAINT =               ('<Command-KeyPress-r>'       , 'cmd+r')
KEY_CLEAR_HIGHLIGHTS =      ('<Escape>'                   , 'esc')
KEY_VALIDATE =              ('<Command-KeyPress-v>'       , 'cmd+v')
KEY_TOGGLE_FIELDS_LAYOUT =  ('<Command-KeyPress-f>'       , 'cmd+f')

class SNGContext(UIContext):
  #from sn.view.graphics.vobjects import VObject
  @override
  def __init__(self, model:Model, view:SNGView):
    '''
    :param model:
    :type model: Model
    :param view:
    :type view: SNGView
    '''
    super().__init__(model)
    self.view:SNGView = view
    self.defaults["view"] = view
    
  @override
  def _defineDecoders(self):
    '''
    :returns:
    :rtype:
    '''
    def getVObject(s:str, d:dict, **kwargs) -> "VObject": #type: ignore[name-defined]
      try:
        ret = self.view.get(s)
        assert isinstance(ret, VObject)
        return ret
      except Exception as ex:
        raise ex
    super()._defineDecoders()
    self.decoders["VObject"] = lambda s, d=self.defaults, **kwargs: getVObject(s,d,**kwargs)
    
  def _setView(self, view:SNGView):
    '''
    :param view:
    :type view: SNGView
    '''
    self.view = view
    self.defaults["view"] = self.view
    
  def move(self, obj:"VObject", x:int|float, y:int|float, _oldPos:list[int]|None=None, adjustPos:bool=True): #type: ignore[name-defined]
    '''
    This is a dummy graphic command.

    :param obj:
    :type obj: VObject
    :param x:
    :type x: int | float
    :param y:
    :type y: int | float
    :param _oldPos:
    :type _oldPos: list[int] | None
    :param adjustPos:
    :type adjustPos: bool
    '''
    print ("dummy graphic command")
    
  class _Move(Command):
    def __init__(self, obj:"VObject", x:int|float, y:int|float, _oldPos:list[int]|None=None, adjustPos:bool=True): #type: ignore[name-defined]
      '''
      :param obj:
      :type obj: VObject
      :param x:
      :type x: int | float
      :param y:
      :type y: int | float
      :param adjustPos: [default=True] Passed to *obj.moveTo()*: whether to let
        the local layout heuristic (FindFree) nudge *obj* off anything it
        lands on. Moves that must land exactly where computed (eg: gathering
        outliers) pass False.
      :type adjustPos: bool
      :param _oldPos: [Optional] The object's true position *before the drag
        that produced (x,y) began* -- eg: *self.dragInfo[0], self.dragInfo[1]*,
        captured in *VObject.onButton_1()* at mouse-down, before any
        *<B1-Motion>* tick has moved anything. If omitted, *do()* falls back
        to capturing *obj.boundingBox()* at *do()*-time instead, but that's
        almost never what you want here: by the time a drag's *do()* runs (on
        button-release, via *context.move()*), *onB1_Motion()* has already
        repositioned *obj* via direct *moveBy()* calls that never touch the
        Command system, so a *do()*-time capture only ever sees where the
        drag *ended* (or, after *FindFree* has additionally perturbed that
        via *adjustPos()*, not even that) -- never where the object was
        before the user picked it up. Passing the true pre-drag position
        explicitly is what lets a single *undo()* restore the whole move
        rather than just its last FindFree-driven leg.
      :type _oldPos: Optional[list[int]]
      '''
      super().__init__("move")
      self.obj:VObject = obj
      self.oldPos:list[int]|None = list(_oldPos) if _oldPos is not None else None
      self.x, self.y = x, y
      self.adjustPos = adjustPos
      if isinstance(self.obj, VRelation):
        self.floating:bool = self.obj.floating()

    @override
    def do(self) -> None:
      super().do()
      if self.oldPos is None:
        self.oldPos = self.obj.boundingBox()
      self.obj.moveTo(self.x, self.y, adjustPos=self.adjustPos)
      self.obj.view.repaintSoon() # (not now: a layout's run is many moves -- see repaintSoon())
  
    @override
    def undo(self):
      super().undo()
      assert self.oldPos is not None
      # adjustPos=False: undo must restore the EXACT prior position, not run
      # FindFree overlap-resolution again. moveTo()'s default (adjustPos=True)
      # is correct for do() -- it's what lets a drag-release resolve two
      # objects dropped on top of each other -- but the same default in
      # undo() meant that if anything now occupies oldPos (e.g. something
      # else was moved there in the meantime), FindFree would silently bump
      # this object to some other free spot instead of back to oldPos. That
      # made undo look "random": the Command queue's own bookkeeping was
      # always correct, but the object could visibly land somewhere other
      # than where it started. adjustPos=False is the same mechanism
      # notifyNodeMove()/reposition() already use during a live drag tick,
      # for the identical reason -- see VRelation.reposition()'s docstring.
      self.obj.moveTo(self.oldPos[0], self.oldPos[1], adjustPos=False)
      if isinstance(self.obj, VRelation):
        self.obj.floating(self.floating)
      self.obj.view.repaintSoon()
      
    @override
    def delete(self):
      super().delete()
      self.obj = None #type: ignore[assignment]
      
    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return f'{super().__str__()} {self.obj.name} {self.x} {self.y}'

  def resize(self, obj:"VObject", x1:int, y1:int, x2:int, y2:int, #type: ignore[name-defined]
             userSized:bool=True, oldBB:list[int]|None=None, oldUserSized:bool|None=None):
    '''
    Set the bounding box of a view object (its position and size).

    :param obj:
    :type obj: VObject
    :param x1:
    :type x1: int
    :param y1:
    :type y1: int
    :param x2:
    :type x2: int
    :param y2:
    :type y2: int
    :param userSized:
    :type userSized: bool
    :param oldBB:
    :type oldBB: list[int] | None
    :param oldUserSized:
    :type oldUserSized: bool | None
    '''
    print ("dummy graphic command")

  class _Resize(Command):
    def __init__(self, obj:"VObject", x1:int, y1:int, x2:int, y2:int, #type: ignore[name-defined]
                 userSized:bool=True, oldBB:list[int]|None=None, oldUserSized:bool|None=None):
      '''
      :param obj:
      :type obj: VObject
      :param x1:
      :type x1: int
      :param y1:
      :type y1: int
      :param x2:
      :type x2: int
      :param y2:
      :type y2: int
      :param userSized: [default=True] Whether the result counts as sized by
        the user (so it's no longer fitted to its text) -- False for "fit to text".
      :type userSized: bool
      :param oldBB: [Optional] The bounding box before -- for a resize that
        was already applied live (eg: a handle drag), since by *do()*-time
        the object already has its new box. Captured at *do()* if omitted.
      :type oldBB: list[int] | None
      :param oldUserSized: [Optional] *obj.userSized* before; likewise.
      :type oldUserSized: bool | None
      '''
      super().__init__("resize")
      self.obj:VObject = obj
      self.bb:list[int] = [int(x1), int(y1), int(x2), int(y2)]
      self.userSized:bool = userSized
      self.oldBB:list[int]|None = list(oldBB) if oldBB is not None else None
      self.oldUserSized:bool|None = oldUserSized

    @override
    def do(self) -> None:
      super().do()
      if self.oldBB is None:
        self.oldBB = list(self.obj.boundingBox())
      if self.oldUserSized is None:
        self.oldUserSized = self.obj.userSized
      self.obj.userSized = self.userSized
      text = self.obj.decorators.get("text")
      if not self.userSized and hasattr(text, "_fitted"):
        text._fitted = None #type: ignore[union-attr] # fitted to its text from now on
      self.obj.reshape(self.bb)

    @override
    def undo(self):
      super().undo()
      assert self.oldBB is not None and self.oldUserSized is not None
      self.obj.userSized = self.oldUserSized
      self.obj.reshape(self.oldBB)

    @override
    def delete(self):
      super().delete()
      self.obj = None #type: ignore[assignment]

    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return f'{super().__str__()} {self.obj.name} {" ".join(str(v) for v in self.bb)}'

  def collapse(self, obj:"VObject", collapsed:bool=True): #type: ignore[name-defined]
    '''
    Show a context window as just its title bar (or, with *collapsed* False, in full).

    :param obj:
    :type obj: VObject
    :param collapsed:
    :type collapsed: bool
    '''
    print ("dummy graphic command")

  class _Collapse(Command):
    def __init__(self, obj:"VObject", collapsed:bool=True): #type: ignore[name-defined]
      '''
      Show a context window as just its title bar (or, with *collapsed* False,
      in full). See *VObject.setCollapsed()*.

      :param obj:
      :type obj: VObject
      :param collapsed:
      :type collapsed: bool
      '''
      super().__init__("collapse" if collapsed else "expand")
      self.obj:VObject = obj
      self.collapsed:bool = collapsed
      self.old:bool = obj.collapsed

    @override
    def do(self) -> None:
      super().do()
      self.obj.setCollapsed(self.collapsed)

    @override
    def undo(self):
      super().undo()
      self.obj.setCollapsed(self.old)

    @override
    def delete(self):
      super().delete()
      self.obj = None #type: ignore[assignment]

    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return f'{super().__str__()} {self.obj.name}'

  def represent(self, object:list[GraphObject]):
    '''
    Show the in the GUI, the give model objects.
    
    :param object: One or more model objects.
    :type object: list[GraphObject|str]
    :param view: The view to add to.
    :type view: SNGView
    :returns: None
    '''
    print ("dummy graphic command")
  
  class _Represent(Command):
    def __init__(self, objects:list[GraphObject|str], view:SNGView|None=None):
      '''
      Show the in the GUI, the give model objects.
      
      :param object: One or more model objects.
      :type object: list[GraphObject|str]
      :param objects:
      :type objects: list[GraphObject | str]
      :param view: The view to add to.
      :type view: SNGView
      :returns: None
      '''
      super().__init__("represent")
      assert view is not None
      self.view:SNGView = view
      assert isinstance(self.view, SNGView), f'Expected SNGView, got {type(self.view)}.'
      self.modelObjects:list[GraphObject] = []
      assert isinstance(self.modelObjects, list), f'Expected list, got {type(self.modelObjects)}.'
      n:GraphObject|str
      for n in objects: # convert from str to GraphObject if necessary
        temp:Any = PReference.eval(n) if type(n) is str else n
        assert isinstance(temp, GraphObject)
        self.modelObjects.append(temp)
      self.vobjects:list[VObject] = []
          
        #assert isinstance(n, GraphObject), f'Expected GraphObject, got {type(n)}.'
  
    @override
    def do(self) -> None:
      def callback(verb:str, tup:tuple):
        if verb == 'new': # tup is (id, VObject)
          self.vobjects.append(tup[1])
      super().do()
      view = self.view
      if len(self.vobjects) == 0: # first call
        # setup a callback to place an newly created VObjects in self.vobjects
        detachCode = view.attachCallback(callback)
        for mo in self.modelObjects:
          self.view.makeViewObjectForGraphObject(mo) # seems odd, but the callback should add this to self.vobjects
        view.detachCallback(detachCode) # kill the callback
        for mo in self.modelObjects: # (asked for explicitly: shown even if in a hidden category)
          vo = self.view.findViewObjectForGraphObject(mo)
          if vo is not None:
            self.view._exemptIfFiltered(vo)
      else: # subsequent call (redo)
        # Nodes first: a node's _reconnect() also restores the relations it
        # kept a reference to (see AGObject._disconnect()/_reconnect()), from
        # the kept end. Reconnecting such a relation first would append it to
        # that kept end a second time.
        n:VObject
        for n in sorted(self.vobjects, key=lambda vo: isinstance(vo, VRelation)):
          if not n._isConnected():
            n._reconnect()
  
    @override
    def undo(self):
      super().undo()
      # Newest first; disconnecting a node also disconnects its relations, so
      # some of these may already be gone.
      for vo in reversed(self.vobjects):
        if vo._isConnected():
          vo._disconnect()
  
    @override
    def delete(self):
      super().delete()
      self.modelObjects = None # type: ignore[assignment]
      self.view = None # type: ignore[assignment]
      self.vobjects = None # type: ignore[assignment]
  
    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      params = ' '.join([mo.name for mo in self.modelObjects])
      return f'{super().__str__()} {" ".join([mo.name for mo in self.modelObjects])} --view {self.view}'


  # This is just a signature -- the behaviour is in class _New_node.
  def erase(self, object:VObject): # pylint: disable=redefined-builtin
    '''
    Delete a *GraphObject*.
    
    :param object: The *VObject* to delete from the view.
    :type object: VObject
    '''
    pass
    
  class _Erase(Command):
    def __init__(self, object:VObject): # pylint: disable=redefined-builtin
      '''
      Delete a object from it's model.
      
      :param object: The object to delete from the view.
      :type object: VObject
      '''
      # param checking...
      super().__init__("remove")
      self.objects:list[VObject] = list(object.view.selected) if object.selected() else [object]
    
    @override
    def do(self):
      super().do()
      for obj in self.objects:
        if obj._isConnected():
          obj._disconnect()
  
    @override
    def undo(self):
      super().undo()
      for obj in self.objects:
        if not obj._isConnected():
          obj._reconnect()
      
    @override
    def delete(self):
      super().delete()
      self.objects = []
      
    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return f'{super().__str__()} {self.objects[0].getPRef().tostring()}'


  def visibility(self, category:str, mode:str="hide"):
    '''
    Show, hide or erase a category of objects in the view (see
    *SNGView.categories*). Hidden objects stay in the view, just not drawn;
    erased ones are taken out of the view (not the model). Either way, *expand*
    won't bring in more of them.

    :param category: The category's name, eg: "types", "isa individuals".
    :type category: str
    :param mode: "show", "hide" or "erase".
    :type mode: str
    '''
    print ("dummy graphic command")

  class _Visibility(Command):
    def __init__(self, category:str, mode:str="hide", view:SNGView|None=None):
      '''
      Show, hide or erase a category of objects in the view.

      :param category: The category's name, eg: "types", "isa individuals".
      :type category: str
      :param mode: "show", "hide" or "erase".
      :type mode: str
      :param view:
      :type view: SNGView | None
      '''
      super().__init__("visibility")
      assert view is not None
      if category not in view.categories.keys():
        raise ValueError(f'Unknown category "{category}": expected one of {", ".join(view.categories.keys())}.')
      if mode not in ("show", "hide", "erase"):
        raise ValueError(f'Unknown mode "{mode}": expected show, hide or erase.')
      self.view:SNGView = view
      self.category, self.mode = category, mode
      self.oldMode:str = view.hides.get(category, "show")
      self.erased:list[VObject] = []

    @override
    def do(self) -> None:
      super().do()
      v = self.view
      if self.mode == "show":
        v.hides.pop(self.category, None)
      else:
        v.hides[self.category] = self.mode
        for vo in v.values(): # (hiding again hides what was shown anyway since)
          if vo is not None and vo.categoryExempt and vo.modelObject is not None \
             and v.categories.isCategory(vo.modelObject, [self.category]):
            vo.categoryExempt = False
      if self.mode == "erase":
        if not self.erased: # (first time: what to erase)
          victims = [vo for vo in v.values() if vo is not None and vo._isConnected() and vo.modelObject is not None
                     and v.categories.isCategory(vo.modelObject, [self.category])]
          for w in [vo for vo in victims if not isinstance(vo, VRelation) and vo.isContextWindow()]:
            victims += [c for c in w.windowContents() if c not in victims] # (not left floating)
          # nodes first: that takes their relations too
          self.erased = sorted(victims, key=lambda vo: isinstance(vo, VRelation))
        for vo in self.erased:
          if vo._isConnected():
            vo._disconnect()
      v.setDirty()
      v.applyVisibility()

    @override
    def undo(self):
      super().undo()
      v = self.view
      if self.oldMode == "show":
        v.hides.pop(self.category, None)
      else:
        v.hides[self.category] = self.oldMode
      for vo in self.erased: # (nodes first, as in _Represent)
        if not vo._isConnected():
          vo._reconnect()
      v.setDirty()
      v.applyVisibility()

    @override
    def delete(self):
      super().delete()
      self.view = None # type: ignore[assignment]
      self.erased = []

    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return f'{super().__str__()} {self.category} {self.mode}'

  def expand(self, object:GraphObject):
    '''
    This is a dummy graphic command.

    :param object:
    :type object: GraphObject
    '''
    print ("dummy graphic command")
    
  class _Expand(Command):
    def __init__(self, object:VObject, *, levels:int=0, _filter:Callable[[Any, Relation], bool]=lambda _vn, _mr: True):
      '''
      :param object:
      :type object: VObject
      :param levels:
      :type levels: int
      :param _filter:
      :type _filter: Callable[[Any, Relation], bool]
      '''
      super().__init__("expand")
      self.obj:VObject = object
      self.levels:int = levels
      self.filter:Callable[[Any, Relation], bool] = _filter
      self.createdObjects:list[VObject] = []
      self.originalDo:bool = True
            
    @override
    def do(self) -> None:
      Command.do(self)
      if self.originalDo:
        self.originalDo = False
        self.createdObjects = []
        view:SNGView =self.obj.view
        detachCode = view.attachCallback(lambda com, tup: self.createdObjects.append(tup[1]) if com=='new' else 0) # (tup is (id, VObject))
        self.obj.expand(filter=self.filter, expand=self.levels)
        view.detachCallback(detachCode)
      else: # redo: nodes first (see _Represent.do())
        for obj in sorted(self.createdObjects, key=lambda vo: isinstance(vo, VRelation)):
          if not obj._isConnected():
            obj._reconnect()
  
    @override
    def undo(self):
      Command.undo(self)
      for obj in reversed(self.createdObjects):
        if obj._isConnected():
          obj._disconnect()
        
    @override
    def delete(self): # (as _Represent's: the objects are out of the view already, if undone -- just let them go)
      super().delete()
      self.createdObjects = [] # (not None: the view's notices of them can still arrive -- see do())
  
    @override
    def __str__(self):
      '''
      :returns: A readable string for this object.
      :rtype:
      '''
      return Command.__str__(self)

    

class _ContainCreated(Command):
  '''
  Contains, in *context*, the relation that the command *creator* creates --
  *creator* being queued earlier in the same composite command, so the relation
  doesn't exist yet when this is made. See *SNGView._containNewRelation()*.
  '''
  def __init__(self, model:Model, typ:Relation, context:GraphObject, creator:Command):
    '''
    :param model:
    :type model: Model
    :param typ:
    :type typ: Relation
    :param context:
    :type context: GraphObject
    :param creator:
    :type creator: Command
    '''
    super().__init__("contain")
    self.model, self.typ, self.context, self.creator = model, typ, context, creator
    self.relation:Relation|None = None

  @override
  def do(self) -> Relation|None:
    '''
    :returns:
    :rtype: Relation | None
    '''
    super().do()
    if self.relation is None:
      created = getattr(self.creator, "relation", None)
      if created is None:
        return None
      self.relation = Relation(db=self.model, parents=[self.typ], src=self.context, dst=created, individual=True)
    else:
      self.relation._reconnect()
    return self.relation

  @override
  def undo(self):
    '''
    :returns:
    :rtype:
    '''
    super().undo()
    if self.relation is not None:
      self.relation._disconnect()
    return self.relation

class SNGView(AbstractGraph["VObject", "VRelation"], Observer, Dirtyable):
  '''
  The persistent container of VObjects.
  '''

  # makingRelationData = namedtuple('makingRelationData', 'originNode typ lineID')
  ElasticLineChoiceData:tuple[VObject, int, Callable[[VObject],bool], Callable[[VObject,VObject],Any]] \
            = namedtuple('ElasticLineChoiceData', 'originNode lineID filter callback onEmpty', defaults=(None,))

  def __new__(cls, url:str, model:Model, *, mode="w", geometry:str="300x400+20+20", _reading:bool=False):
    '''
    :param url:
    :type url: str
    :param model:
    :type model: Model
    :param mode:
    :type mode:
    :param geometry:
    :type geometry: str
    :param _reading:
    :type _reading: bool
    :returns:
    :rtype:
    '''
    if url is None:
      url = fixURL(model.url, extension=".snv", replaceExt=True, mode="w")[0]
    return PRDb.__new__(cls, url, mode=mode, memoryResident=False, _reading=_reading)

  def __init__(self, url:str, model:Model, *, mode="w", geometry:str="300x400+20+20", _reading:bool=False):
    '''
    :param url:
    :type url: str
    :param model:
    :type model: Model
    :param mode:
    :type mode:
    :param geometry:
    :type geometry: str
    :param _reading:
    :type _reading: bool
    '''
    if hasattr(self, "_initialized"): # This means the __new__ method has returned an existing object, so don't truck over it!
      return
    if url is None:
      url = fixURL(model.url, extension=".snv", replaceExt=True, mode="w")[0]

    self._scale:float = 1.0
    self._fontFace:str = "Arial"
    self._fontSize:float = 10.0

    PRDb.__init__(self, url, memoryResident=False, _reading=_reading)
    Dirtyable.__init__(self)
          
    self.model:Model = model

    # global way to get the tk application-root window
    self.root = tk._default_root # type: ignore[attr-defined] # @UndefinedVariable 
    
    self.window = AppWindow(self.root, url, geometry)
    self.window.view = self  # so AppWindow's focus handling can dispatch to this SNGView (see onWindowFocusIn()/onWindowFocusOut())
    self.canvas:tk.Canvas = self.window.appPanedWidget.canvasFrame.canvas
    self.terminalFrame = self.window.appPanedWidget.textDisplayFrame
    
    # set up the context
    self.context:SNGContext = SNGContext(model, self)
    
    # set up the terminal
    self.terminal = SNTerminalWidget(self.model, self.terminalFrame, context=self.context)
    self.terminal.pack(fill=tk.BOTH, expand=True)
    self.window.appPanedWidget.canvasFrame.terminal = self.terminal
    # This window's terminal is the single routing target for BOTH the
    # SNTerminalWidget itself and the graphics editor (SNGFrame) — bind
    # focus on every widget in the window (not just the terminal) so that
    # clicking into the graphics editor also makes its output land here.
    self.window._bindFocusRouting(self.window, self.terminal) # type: ignore[arg-type]
    # Also register the app window/terminal pair directly, independent of Tk
    # focus — lets TerminalRegistry's active-window fallback (wm stackorder)
    # find this terminal even for interactions (e.g. SNCanvas's right-click
    # popup menu) that never move Tk's logical keyboard focus at all.
    self.window._root().terminalRegistry.registerWindow(self.window, self.terminal) #type: ignore[attr-defined]

    model.addObserver(self)
    self._closed:bool = False
    "Set when the view's window is closed (see *detachFromModel()*): it then ignores the model's updates."
    
    # self.context._setView(self) # make this view the view of the context. #TODO: hackey ...
    self.selected:set[VObject] = set()
    'The set of currently selected VObjects.'
    self._suppressLocalLayout = False
    'Temporarily suppress automatic layout. Necessary during drag operations, etc.'
    self.localLayout = FindFree(self)

    self._eventHandled:Optional[tk.Event] = None
    "Set by a contained VObject/item-level handler (via addEventHandled()) to mark that it already handled a mouse event, so this canvas's own (separately-dispatched) widget-level binding for the same event -- e.g. onRightMouse() -- can skip its generic handling. See isEventHandled()/addEventHandled()/removeEventHandled()."

    self._deletedGraphObjectsCache:dict[int,VObject] = dict[int,VObject]()
    "Used by update to store deleted VObjects matching deleted GraphObjects in case they are restored."
    
    self._drawVersion:int = 0
    self.scrollRegion:tuple = (0, 0, 4000, 3000)

    self.makeBindings()
     
    # self._makingRelationFrom:SNGView.makingRelationData|None = None
    self._elasticLineChoiceData:SNGView.ElasticLineChoiceData|None = None
    self._selectionBoxInfo:list[Any]|None = None
    self._cursorBeforeTerminal:str = "arrow"
    self._inferences:list[dict[str, Any]] = []
    "The inferred/inherited relations drawn as dashed lines (see *drawInferences()*)."
    "The cursor to restore when the pointer moves off a relation terminal (see *_updateTerminalCursor()*)."
    self._scrolling:bool = False

    self.categories:Categories[GraphObject] = Categories[GraphObject]()
    "Named categories of model objects, for hiding or erasing from the view (see *visibility()*)."
    m = self.model
    self.categories.addCategory("system objects",  lambda mo: mo.isSystemObject())
    self.categories.addCategory("isa individuals", lambda mo: isinstance(mo, IsaIndividual))
    self.categories.addCategory("higher-order isa relations", # (an individual relation's isa to its relation type)
                                lambda mo: isinstance(mo, IsaIndividual) and isinstance(mo.src, Relation) and mo.src.isIndividual()
                                           and isinstance(mo.dst, Relation) and mo.dst.isType())
    self.categories.addCategory("types",           lambda mo: mo.isType())
    self.categories.addCategory("non-local",       lambda mo: mo.model is not self.model)
    self.categories.addCategory("rules",           lambda mo: mo.isIndividual() and mo.isa(m.RULE))
    self.categories.addCategory("queries",         lambda mo: mo.isIndividual() and mo.isa(m.QUERY))
    self.hides:dict[str, str] = {}
    "The categories currently hidden or erased: category name -> \"hide\" or \"erase\". Saved with the view."
    

  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    '''
    :returns:
    :rtype: InstantiationInfo
    '''
    def finalize(slf:Serializable, _:SerializableType):
      assert isinstance(slf, SNGView), f'Expected SNGView for param 1, got {type(slf)}.'
      for rel in list(slf.values()):
        if isinstance(rel, VRelation):
          rel.connect()
      slf.canvas.after_idle(lambda slf=slf: [slf.applyVisibility(), slf._restoreAnimationState(), slf.resetScrollRegion(), slf.setDirty(False)]) # type: ignore[misc]
    ret:InstantiationInfo = super().getInstantiationInfo()
    # ret.class_ = cls
    # (its model's URL relative to the view's file if they're side by side -- see PRDb.relativeURL() -- so
    # a view and model copied together stay together; a relative URL is resolved against the view's file on reading)
    ret.conArgs.append(ParamInfo("model", str, getter=lambda slf: PRDb.relativeURL(cast(SNGView,slf).model.url),
                                 setter=lambda m: Model(cast(str,m))))
    ret.conKWArgs.append(ParamInfo("geometry", str, getter=lambda slf: cast(SNGView,slf).window.geometry()))
    ret.postconSetters.append(PropertyInfo("hides", str,
        lambda slf: ",".join(f"{k}={v}" for k, v in cast(SNGView, slf).hides.items()),
        lambda slf, v: setattr(slf, "hides", dict(kv.split("=", 1) for kv in str(v).split(",") if "=" in kv)),
        optional=True)) # optional: views saved before it existed still load
    ret.postconSetters.append(PropertyInfo("animation", str,
        lambda slf: cast(SNGView, slf)._animationState(),
        lambda slf, v: setattr(slf, "_pendingAnimation", str(v)), # (applied once the view is built: see _restoreAnimationState())
        optional=True))
    ret.finalSetters.append(PropertyInfo("_", bool, setter=finalize))
    return ret

  
  @override
  def save(self, saveas:Optional[str]=None, overwrite=False, format:str=DEFAULT_STRATEGY) -> None:
    '''
    :param saveas:
    :type saveas: Optional[str]
    :param overwrite:
    :type overwrite:
    :param format:
    :type format: str
    '''
    super().save(saveas=saveas, overwrite=overwrite, format=format)
    self.setDirty(False)

  def doSaveView(self) -> None:
    '''
    Save this view. This is the target the "File | Save view" menu item
    (added/removed by *onWindowFocusIn()*/*onWindowFocusOut()* below) is
    wired to while this view's window is focused -- kept as its own method
    (rather than wiring the menu straight to *save()*) since Rob's planning
    sibling "Save model", "Save view as...", "Save model as..." commands
    here too, and this is the natural place for any save-view-specific
    behavior (confirmation, status message, ...) if/when it needs more than
    a plain save.

    :rtype: None
    '''
    self.save(overwrite=True)

  def doCloseModel(self) -> None:
    '''
    Close this view's model: the target of the "File | Close model" menu item
    (added/removed like "Save view": see *onWindowFocusIn()*). See
    *Application.closeModel()*.

    :rtype: None
    '''
    if self.model is not None:
      self.root.closeModel(self.model)

  def onWindowFocusIn(self) -> None:
    '''
    This view's *AppWindow* just gained focus -- add (or, if already
    present from some other cause, replace) the "File | Save view" menu
    item so it's wired to this view's *doSaveView()*.

    Called by *AppWindow._onWindowFocusIn()*. Since only one *AppWindow* is
    ever focused at a time, and each focused window's *SNGView* calls this
    on the way in, this is enough to guarantee "Save view" always targets
    whichever view the user is actually looking at -- no shared
    "currently active view" bookkeeping needed anywhere else.

    :rtype: None
    '''
    addToMenuBar("File|Save view", self.doSaveView)
    addToMenuBar("File|Close model", self.doCloseModel)
    addCheckToMenuBar("View|Animation toolbar", self._animationToolbarShown(), self._onAnimationToolbarItem,
                      cascadePositions={"View": 1})

  def onWindowFocusOut(self) -> None:
    '''
    This view's *AppWindow* just lost focus -- or is being closed outright
    -- so withdraw the "File | Save view" menu item.

    Called by *AppWindow._onWindowFocusOut()* (via *_checkStillActive()*)
    when focus genuinely leaves this window, and by
    *Application._closeWindow()* when this window is closed (which isn't
    guaranteed to first fire a Tk focus-out event). Safe to call even if
    this view never added the item (e.g. its window was never focused) --
    *removeFromMenuBar()* is a no-op in that case.

    :rtype: None
    '''
    removeFromMenuBar("File|Save view")
    removeFromMenuBar("File|Close model")
    removeFromMenuBar("View|Animation toolbar")

  ANIMATION_SETTINGS = ("flowStrength", "e", "k", "heat")
  "The animation layout's numeric settings saved with the view (see *_animationState()*)."

  def _animationState(self) -> str:
    '''
    :returns: What's saved with the view about its animation layout: whether
      the animation toolbar is shown, and the settings it shows -- eg:
      "toolbar=1;direction=down;follows=isa;labels=1;flowStrength=6.0;e=1000.0;k=0.005;heat=6.0".
    :rtype: str
    '''
    layout = self.animationLayout()
    parts = {"toolbar": "1" if self._animationToolbarShown().get() else "0",
             "direction": layout.flowDirection or "none",
             "follows": (layout.flowRelation or self.model.ISA).name,
             "labels": "1" if layout.placeLabels else "0"}
    parts.update({k: repr(float(getattr(layout, k))) for k in self.ANIMATION_SETTINGS})
    return ";".join(f"{k}={v}" for k, v in parts.items())

  def _restoreAnimationState(self) -> None:
    '''
    Once a read view is built: put its saved animation layout settings back,
    and show its animation toolbar if it was shown (see *_animationState()*).
    '''
    text = self.__dict__.pop("_pendingAnimation", None)
    if not text:
      return
    try:
      state = dict(kv.split("=", 1) for kv in text.split(";") if "=" in kv)
      layout = self.animationLayout()
      direction = state.get("direction", "none")
      layout.flowDirection = None if direction == "none" else direction
      follows = state.get("follows")
      if follows and follows != self.model.ISA.name:
        layout.flowRelation = next((r for r in self.model.values() if isinstance(r, Relation) and r.isType() and r.name == follows), None)
      for k in self.ANIMATION_SETTINGS:
        if k in state:
          setattr(layout, k, float(state[k]))
      layout.placeLabels = state.get("labels", "1") != "0"
      if state.get("toolbar") == "1":
        self.showAnimationToolbar(True)
    except Exception:
      logger.exception(f"{self.name}: couldn't restore its animation settings ({text!r})")

  def setAnimationSetting(self, attr:str, value:Any) -> None:
    '''
    Change one of the animation layout's settings (eg: from the toolbar or the
    menu) -- marking the view changed, as they're saved with it.

    :param attr: The layout's attribute, eg: "flowDirection" or "heat".
    :type attr: str
    :param value: Its new value.
    :type value: Any
    '''
    layout = self.animationLayout()
    if getattr(layout, attr, None) != value:
      setattr(layout, attr, value)
      self.setDirty()

  def _animationToolbarShown(self) -> tk.BooleanVar:
    '''
    :returns: Whether this view's animation toolbar is shown -- what "View | Animation toolbar" shows (and sets).
    :rtype: tk.BooleanVar
    '''
    var = self.__dict__.get("_toolbarVar")
    if var is None:
      var = self._toolbarVar = tk.BooleanVar(self.canvas, value=False)
    return var

  def _onAnimationToolbarItem(self) -> None:
    'The "View | Animation toolbar" item was chosen: its check mark is already set; show or hide accordingly.'
    self.showAnimationToolbar(self._animationToolbarShown().get())

  def toggleAnimationToolbar(self) -> None:
    'Show the animation toolbar if it\'s hidden, or hide it if it\'s shown.'
    self.showAnimationToolbar(not self._animationToolbarShown().get())

  def showAnimationToolbar(self, show:bool=True) -> None:
    '''
    Show (or hide) the animation toolbar (see *animationToolbar*) across the top of
    this view's window.

    :param show: True to show it; False to hide it.
    :type show: bool
    '''
    from sn.view.graphics.animationToolbar import AnimationToolbar
    bar = self.__dict__.get("_animationToolbar")
    if show:
      if bar is None:
        bar = self._animationToolbar = AnimationToolbar(self.window, self)
      bar.pack(side=tk.TOP, fill=tk.X, before=self.window.appPanedWidget)
      bar.startPolling()
    elif bar is not None:
      bar.stopPolling()
      bar.pack_forget()
    if self._animationToolbarShown().get() != show:
      self._animationToolbarShown().set(show)
      self.setDirty() # (saved with the view)

  @override
  def _register(self, value: VObject, _id:Optional[int]=None) -> int: # type: ignore[override]
    '''
    Overrides the 
    :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
    to restrict contained objects to :py:class:`GraphObject` subtypes. 
    *This violates subsumption rules, but that's what we want here!* 
    
    Also sets the dirty bit and notifies any observers ("add GraphObject" (GraphObject))

    :param value:
    :type value: VObject
    :param _id:
    :type _id: Optional[int]
    :returns:
    :rtype: int
    '''
    assert isinstance(value, VObject), \
        f'Models are restricted to containing only GraphObject subtypes; got a {value.__class__.__name__} type.'
    self.setDirty()
    ret = super()._register(value, _id)
    return ret
    
  @override
  def _unregister(self, _id:int) -> None:
    '''
    Overrides the 
    :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
    to also set the dirty bit and notify any observers () 

    :param _id:
    :type _id: int
    '''
    super()._unregister(_id)
    self.setDirty()
    
  @override
  def detachFromModel(self) -> None:
    '''
    The view's window is closing: stop observing the model, and stop each of
    the view's objects observing its model object -- the model stays in memory
    (it may have other views), and its changes mustn't reach a window that's
    gone. Notifications already on their way are ignored (see *_closed*).
    '''
    self._closed = True
    self.model.detach(self)
    for vo in list(self._db.values()):
      if vo is None:
        continue
      try:
        mo = vo.modelObject
      except Exception: # (eg: its model object has been deleted)
        continue
      if mo is not None:
        mo.detach(vo)

  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]])->None:
    '''
    :param subject:
    :type subject: Subject
    :param topics:
    :type topics: tuple[str, tuple[Any, ...]]
    '''
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vnodes import VNode
    from sn.view.graphics.vrelations import VRelation #, VIsa
    assert isinstance(subject, Model), f'Expected Model, got {type(subject)}.'
    if getattr(self, "_closed", False): # (a notification sent before the window closed: see detachFromModel())
      return
    self.structureChanged() # (eg: an object retyped: maybe now a context window)
    logger.info(f'SNGView.update({subject.name}, {len(topics)} topics):')
    for t in topics:
      topicName:str = t[0]
      topicData:tuple[Any, ...] = t[1]
      match t:
      #  if topicName == 'add GraphObject':
        # case ['add GraphObject', topicData]:
        case ['new', topicData]:
          modelID = topicData[0]
          
          # if this is one we've seen before, just restore it
          if modelID in self._deletedGraphObjectsCache:
            vObject:VObject = self._deletedGraphObjectsCache[modelID]
            vObject._reconnect()
            return
          
          modelObj = topicData[1]
          logger.info(f'  Creating V{modelObj.__class__.__name__} for model object {modelObj}:{modelObj.__class__.__name__}')
          if (modelObj.isType() or isinstance(modelObj, Node)) and self.canvas: 
            applyEditAttrsBox(self.canvas, modelObj, title=modelObj.name, editKey="name")
            # a variable's name may be typed with constraints: "?p :where: alive" (see sn.model.constraints)
            if WHERE in modelObj.name:
              self._applyWhere(modelObj)
          typ:type = type(modelObj)
          newObj:VObject|None = None
          if typ is Collection:
            pass
          elif typ is Node:
            # findViewObjectForGraphObject() first: a VObject for modelObj may
            # already exist even though this is the FIRST time this method is
            # hearing about it. A Relation's endpoints get resolved eagerly
            # during its own VRelation's construction (VRelation.connect() ->
            # makeViewObjectForGraphObject()), so if some other, already-
            # -processed 'add GraphObject' topic's VRelation happened to
            # reference this Node as its src/dst before this topic got here,
            # that resolution already created (and registered) this Node's
            # VObject -- constructing another one here would silently produce
            # a second, orphaned VObject for the same model object.
            newObj = self.makeViewObjectForGraphObject(modelObj) or VNode(self, modelObj)
          elif issubclass(typ, Relation) and self._erasedRelation(modelObj):
            pass # (see visibility())
          elif issubclass(typ, Relation):
            # Same reasoning as the Node case above, but this is where it
            # actually bites: GraphObject.__init__() creates an IsaIndividual
            # parent-link whose src is the very Relation being constructed, so
            # that IsaIndividual's own VRelation -- if ITS 'add GraphObject'
            # topic happens to be processed before this one -- resolves (and
            # so creates) a VRelation for THIS modelObj via
            # makeViewObjectForGraphObject() before we ever get here. Without
            # this check, this branch would then unconditionally build a
            # SECOND, redundant VRelation for the same Relation.
            newObj = self.makeViewObjectForGraphObject(modelObj) or VRelation(self, modelObj)
          # elif typ is IsaIndividual:
          #   newObj = VIsa(self, modelObj)
          else:
            logger.error(f"VObject subtype not implemented for model type {typ.__name__}.")
          if newObj is not None: # (made just now, in a hidden category: shown anyway -- see _exemptIfFiltered())
            self._exemptIfFiltered(newObj)
  
        # elif topicName == 'del GraphObject':
        case ["reasoned", _] | ["reasoning cleared", _]:
          self._showReasoning()

        case ["del", topicData]:
          modelID = topicData[0]
          obj:VObject|None = self.findViewObjectForGraphObject(lambda vo: vo.modelObject is not None and vo.modelObject.id==modelID)
          if obj is not None:
            obj._disconnect()
            self._deletedGraphObjectsCache[modelID] = obj
          
        case [topicName, topicData]:
          logger.warning(f'Unsupported topic "{topicName}": {topicData}')

  def suppressLocalLayout(self, suppress:str|bool|None=None):
    '''
    :param suppress:
    :type suppress: str | bool | None
    :returns:
    :rtype:
    '''
    if suppress is not None:
      if isinstance(suppress, str):
        self._suppressLocalLayout = suppress.lower() in ['true', 't', 'yes', 'y', 'on']
      else:
        assert isinstance(suppress, bool)
        self._suppressLocalLayout = suppress
    return self._suppressLocalLayout

  def intersectTag(self, ids:Iterable[int], tag:str, exclude:list[int]|int=[]) -> list[int]:
    '''
    :param ids: [Iterable[int]] An *Iterable* of *ints* representing *Canvas* ids.
    :type ids: Iterable[int]
    :param tag: [str] A *str* *Canvas* tag.
    :type tag: str
    :param exclude: [list[int] or int, default=[]] A list of *int* representing *Canvas* ids.
    :type exclude: list[int] | int
    :return: A list of all ids in *ids* that have tag *tag* that are not in *exclude*.
    :rtype: list[int]

    Used by *sn.view.graphics.layout.LayoutHieristic.findOverlapping()* (e.g. FindFree) to
    filter the results of *self.canvas.find_overlapping()* down to just the shape items
    it cares about. This was previously only defined on *view.py*'s (unused-at-runtime)
    *SNView*, not on this, the actual *SNGView* class that *VObject.view* is -- so any
    local-layout call that hit an overlap raised AttributeError here instead of resolving it.
    '''
    if isinstance(exclude, int): exclude = [exclude]
    if not self.canvas:
      return []
    ret = []
    for id in ids:
      if tag in self.canvas.gettags(id) and id not in exclude:
        ret.append(id)
    return ret

  ### Operations #######################################################################

  def makeViewObjectForGraphObject(self, mObject:GraphObject,
                                   atPoint:tuple[float, float]|None=None,
                                   expand:int=0,
                                   filter:Callable[[Any, Relation], bool]=lambda vn, mr: True) \
                                   ->"VObject": 
    '''
    Either make or find (depending if there is already a VObject representing
    *mObject* in the view) a VObect that represents *mObject*.
    
    :param mObject: A model object.
    :type mObject: GraphObject
    :param atPoint: [Optional, 2-Tuple[float]] The point where the new object
        should be displayed if it has to be created.
    :type atPoint: tuple[float, float] | None
    :param expand: [Optional[int], default=None] The number of hops to expand.
    :type expand: int
    :param filter: Optional[Callable[[Self, Relation], bool]] A function *selfxRelation->bool*
        where that relation will only be expanded if the function returns *True*
    :type filter: Callable[[Any, Relation], bool]
    :return: If there is a *VObject* currently in the display representing *mObject* then
        that is returned, otherwise an attempt is make to create such an object referencing
        *mObject* and that is returned.
    :rtype: VObject
    '''
    from sn.view.graphics.vrelations import VRelation
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vnodes import VNode
    # make certain we don't make a duplicate    #createdVObjects:set[VObject] = set()
    ret = self.findViewObjectForGraphObject(mObject)
    created = ret is None
    if ret is None:
      if isinstance(mObject, Relation):
        ret = VRelation(self, modelObject=mObject)
      elif isinstance(mObject, (Node,GraphObject)):
        minSize = mObject.get('vis/minSize', snPrefs.get("gui/NodeMinSize", storeDefault=30))
        assert isinstance(minSize, (float,int))
        sizex = float(minSize)
        aspectRatio = mObject.get('vis/aspectRatio', snPrefs.get("gui/NodeAspectRatio", storeDefault=1.5))
        assert isinstance(aspectRatio, (float,int))
        sizey = int(sizex * (aspectRatio or NOMINAL_ASPECT)) # vis/aspectRatio is height/width; 0 means free
        if atPoint is None:
          x, y = self.findAGoodLocation(mObject)
        else:
          x, y = int(atPoint[0]), int(atPoint[1])
        ret = VNode(self, mObject, x=x, y=y, x1=int(x + sizex), y1=int(y + sizey))
      else:
        raise AttributeError(f'SNView.makeViewObjectforGraphObject(): unexpected model object type: {mObject.__class__.__name__}.')

    assert isinstance(ret, VObject), f'SNView.makeViewObjectForGraphObject(): Unexpected return type "{ret.__class__.__name__}".'
    if created:
      # Not now: we may be inside another object's construction (eg: a relation
      # resolving its ends), and that object isn't finished yet.
      if self.canvas:
        self.canvas.after_idle(lambda vo=ret: self._attachDanglingEnds(vo)) #type: ignore[misc]
      else:
        self._attachDanglingEnds(ret)
    if expand > 0:
      ret.expand(filter=filter, expand=expand - 1)
    return ret
  
  def findAGoodLocation(self, mObject:GraphObject) -> tuple[int,int]:
    '''
    :param mObject:
    :type mObject: GraphObject
    :returns:
    :rtype: tuple[int, int]
    '''
    mParents = mObject.getParents()
    mParent = mParents[0] if len(mParents) > 0 else None
    vParent = self.findViewObjectForGraphObject(mParent) if mParent is not None else None
    if vParent is None:
      x, y = self.cursorViewPoint()
    else:
      bb = vParent.boundingBox()
      x = bb[0]
      y = bb[1] + 120
    return x, y

  def cursorViewPoint(self) -> tuple[int, int]:
    '''
    :returns: The graphics cursor's position in view coordinates (ie: allowing
      for the canvas's scroll position and the zoom). If the cursor isn't over
      the canvas (eg: the command came from the text terminal), the top-left
      of the visible part of the canvas instead, so the result is on screen.
      (0, 0) if there's no canvas.
    :rtype: tuple[int, int]
    '''
    if not self.canvas:
      return 0, 0
    c = self.canvas
    # pointer position relative to the canvas widget
    wx = c.winfo_pointerx() - c.winfo_rootx()
    wy = c.winfo_pointery() - c.winfo_rooty()
    if not (0 <= wx < c.winfo_width() and 0 <= wy < c.winfo_height()):
      wx, wy = 20, 20
    x, y = self.windowToView(c.canvasx(wx), c.canvasy(wy))
    return int(x), int(y)

  def _attachDanglingEnds(self, vo:VObject) -> None:
    '''
    *vo* has just been added to the view: relations already here whose own
    endpoint is *vo*'s model object, but which were left dangling because it
    wasn't shown (eg: top -- see *VRelation._resolveEnd()* -- or an erased
    object), attach to it.

    :param vo:
    :type vo: VObject
    '''
    from sn.view.graphics.vrelations import VRelation
    if not vo._isConnected() or vo.modelObject is None: # (gone again meanwhile)
      return
    for r in list(self._db.values()):
      # skip anything not fully constructed (a relation that's still being made
      # resolves its own ends)
      if not isinstance(r, VRelation) or r is vo or r.modelObject is None or not r._isConnected() \
         or not hasattr(r, "_floatingAnchor") or not hasattr(r, "_drawVersion"):
        continue
      try:
        changed = False
        for end in ("src", "dst"):
          own = r.modelObject.localSrc if end == "src" else r.modelObject.localDst
          if own is vo.modelObject and getattr(r, end) is None:
            setattr(r, end, vo)
            changed = True
        if changed:
          self.freshPaint()
          r.draw()
      except Exception:
        logger.exception(f"_attachDanglingEnds(): attaching {r} to {vo}:")

  def findViewObjectForGraphObject(self, mObject:GraphObject|Callable[[VObject],bool]) -> VObject|None:
    '''
    :param mObject: A model object or a boolean function taking a VObject
    :type mObject: GraphObject|Callable[[VObject],bool]
    :return: A *VObject* currently in the display representing *mObject*, or *None* if there is not such object.
    :rtype: VObject | None
    '''
    if isinstance(mObject, GraphObject):
      for obj in self.values():
        if obj is not None and obj.modelObject is mObject:  # already displayed?
          return obj
    else:
      for obj in self.values():
        if obj is not None and mObject(obj):  # already displayed?
          return obj
    # raise AttributeError(f'Expected a param of type GraphObject, but got type {mObject.__class__.__name__}')
    return None

  def validate(self, refresh:bool=False) -> int:
    '''
    :param refresh:
    :type refresh: bool
    :returns:
    :rtype: int
    '''
    errCount = 0
    vobjs:list[VObject] = list(self._db.values())
    for n in vobjs:
      errCount += len(n.validate())
    if errCount == 0:
      logger.info("All nodes and relations passed validation.")
    else:
      logger.warning(f"Found {errCount} validation faults.")
    i:int = 0
    length = len(vobjs)
    for vobj in vobjs:
      i += 1
      count:list = []
      for j in range(i, length):
        if vobj.modelObject is vobjs[j].modelObject:
          count.append(vobjs[j])
      if len(count) > 0:
        logger.error(f'Found {len(count)+1} visual objects representing model object {vobj.modelObject.name if vobj.modelObject is not None else "<None>"}#{vobj.modelObject.id if vobj.modelObject is not None else "<None>"}: {[o.id for o in [vobj]+count]}.' )
        errCount += 1
    if errCount and refresh and self.canvas:
      self.freshPaint()
      self.repaint()
    return errCount

  def showAllModel(self):
    x:int = 10
    y:int = 10
    minSize = snPrefs.get('gui/NodeMinSize', storeDefault=30, storeType=int)
    assert isinstance(minSize, (int,float))
    sizex:int = int(minSize)
    aspectRatio = snPrefs.get('gui/NodeAspectRatio', storeDefault=1.5, storeType=float)
    assert isinstance(aspectRatio, (int,float))
    sizey:int = int(sizex * float(aspectRatio))
    grid = (sizex * 2, sizey * 2)
    numNodes = len(self.model) - len(self)
    gridCount = int(sqrt(numNodes)) if numNodes>0 else 0
    blockSize = gridCount * grid[1] + y
    for mnode in self.model.values():
      # if self.categories.isCategory(mnode, self.hiddenCategories):
      #   continue
      if self.isFiltered(mnode):
        continue
      vObj = self.findViewObjectForGraphObject(mnode)
      if vObj is None:
        n = self.makeViewObjectForGraphObject(mnode, atPoint=(x, y))
        if y < blockSize:
          y += grid[1]
        else:
          x += grid[0]
          y = 10
        self.localLayout(n)
    # for mrel in self.model.relations:
    #   if self.categories.isCategory(mrel, self.hiddenCategories) or \
    #       all(map(lambda obj: self.categories.isCategory(obj, self.hiddenCategories), 
    #               map(lambda role: role["filler"], list(chain(mrel.roles.values()))))):
    #     continue  
    #   vObj = self.findViewObjectForGraphObject(mrel)
    #   if vObj is None:
    #     try:
    #       r = self.makeViewObjectForGraphObject(mrel)
    #       self.localLayout(r)
    #     except Exception as ex:
    #       logger.write(f'Could not instantiate VObject for {type(mrel).__name__} {mrel.idString} "{mrel["label"]}": {type(ex).__name__}("{ex}")', level='warning', exception=ex)


# class SNCanvas(tk.Canvas):
#   '''
#   classdocs
#   '''
#
#   def __init__(self, master:SNGViewFrame, **kwargs):
#     '''
#     Constructor
#     '''
#     #assert isinstance(master, SNGViewFrame), f'Expected SNGViewFrame, got {type(master)}'
#     tk.Canvas.__init__(self, master, kwargs)
#     self.create_text(10, 10, text=f'Model: {self.model}')
#     #self.after(30, print, "hello from the graphics display")
#
#     self._scale:float = 1.0
#     self._fontFace:str = "Arial"
#     self._fontSize:float = 10.0
#
#     self._eventHandled:Optional[tk.Event] = None
#     "Set by a contained VObject/item-level handler (via addEventHandled()) to mark that it already handled a mouse event, so this canvas's own (separately-dispatched) widget-level binding for the same event -- e.g. onRightMouse() -- can skip its generic handling. See isEventHandled()/addEventHandled()/removeEventHandled()."
#
#     self.makeBindings()
#     self._drawVersion:int = 0
#     self.scrollRegion:tuple = (0, 0, 4000, 3000)
#

  # @property
  # def model(self) -> Model:
  #   return cast(SNGViewFrame, self.master).model
  #
  # @property
  # def context(self) -> ModelContext:
  #   return cast(SNGViewFrame, self.master).context
    
  # ---- Event handling --------------------------------------------------------

  def makeBindings(self):
    '''
    Create the bindings for the *Canvas* object.
    '''
    self.canvas.bind("<Enter>", self.onEnter)
    
    # For making relations
    self.canvas.bind("<B1-ButtonRelease>", self.onB1_ButtonRelease)
    self.canvas.bind("<Motion>", self.onMotion)

    # for popup menu
    bindRightMouse(self.canvas, self.onRightMouse)  # lambda e: self.backgroundMenu(e).post(e.x_root, e.y_root))

    # scroll using mouse click-and-drag
    self.canvas.bind("<Button-1>", self.onButton_1)
    self.canvas.bind("<B1-Motion>", self.onB1_Motion)
    # # scroll using two-finger drag
    self.canvas.bind('<MouseWheel>', self.onMouseWheel)
    self.canvas.bind('<Shift-MouseWheel>', self.onShift_MouseWheel)
    #
    # undo/redo
    self.canvas.bind(KEY_UNDO[0], self.onUndo)
    self.canvas.bind(KEY_REDO[0], self.onRedo)
    
    # repaint
    self.canvas.bind(KEY_REPAINT[0], self.repaint)

    # abandon an elastic-line choice (or, if there's none, clear the highlights)
    self.canvas.bind(KEY_CLEAR_HIGHLIGHTS[0], self.cancelElasticLine)
    
    # # validate
    # self.canvas.bind(KEY_VALIDATE[0], lambda _x: self.validate(refresh=True))
    #
    # # fields layout
    # self.canvas.bind(KEY_TOGGLE_FIELDS_LAYOUT[0], lambda _x: self.onToggleFieldsLayout())

  def onEnter(self, _event:tk.Event) -> None:
    '''
    Give this *Canvas* Tk keyboard focus whenever the mouse enters it.

    All of this class's key bindings (KEY_UNDO, KEY_REDO, KEY_REPAINT, ...)
    are bound directly on *self.canvas* -- like any Tk widget-level binding,
    those only fire while the canvas itself holds keyboard focus, and
    nothing else in this window (e.g. clicking into the canvas, as opposed
    to some other widget such as the terminal) ever calls *focus_set()* on
    it. Without this, the canvas can easily end up never holding focus at
    all, so a key like Cmd-Z is delivered nowhere and its binding never
    fires, even though the binding itself is set up correctly. This mirrors
    the equivalent binding in the older, now-superseded *sn.view.graphics.
    view.SNView* (see its own *onEnter()*), which was dropped somewhere
    along the way when this class superseded it.

    :param _event: The Tk *<Enter>* event (unused).
    :type _event: tk.Event
    :rtype: None
    '''
    self.canvas.focus_set()

  def onUndo(self, event:tk.Event):
    '''
    :param event: The Tk event.
    :type event: tk.Event
    '''
    self.context.undo()
    self.addEventHandled(event)
    
  def onRedo(self, event:tk.Event):
    '''
    :param event: The Tk event.
    :type event: tk.Event
    '''
    self.context.redo()
    self.addEventHandled(event)
    
  def onMotion(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :type event: tk.Event
    :return: None
    
    If there's a _elasticLineChoiceData going on (elastic line), then continue the
    animation. 

    Called on the *<Motion>* event (when the mouse moves with no buttons pressed).
    Note that selection boxes and scrolling are handled by *self.onB1_Motion()*.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If *self._makingRelaionFrom* is not *None*, redraw the "making relation" line.

    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    # if self._makingRelationFrom is not None:
    #   self.canvas.coords(self._makingRelationFrom.lineID,
    #         flattenPairs([self.viewToWindow(self._makingRelationFrom.node.centerPt()),
    #                   (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))]))
    if self._elasticLineChoiceData is not None:
      self._trackElasticLine(event)
      return
    self._updateTerminalCursor(event)

  TERMINAL_CURSOR = "center_ptr"
  "The cursor shown while the pointer is over a relation terminal that can be dragged to a new src/dst."

  def _relationTerminalNear(self, x:float, y:float) -> VRelation|None:
    '''
    :param x: Canvas (window) coordinates.
    :type x: float
    :param y: See *x*.
    :type y: float
    :returns: An editable relation with a terminal within reach of (x, y) --
      ie: one that a press there would grab (see *VRelation.grabTerminal()*)
      -- or None. Only objects drawn near (x, y) are examined.
    :rtype: VRelation | None
    '''
    r = VRelation.TERMINAL_HIT_RADIUS
    items = self.canvas.find_overlapping(x - r, y - r, x + r, y + r)
    if not items:
      return None
    # Match on each object's own *tag* rather than parsing an id out of it: a
    # tag is fixed when the object is created, and loading a view from a file
    # can give the object a different id afterwards.
    byTag = {vo.tag: vo for vo in self._db.values() if vo is not None}
    candidates:dict[int, VRelation] = {}
    for item in items:
      for tag in self.canvas.gettags(item):
        vo = byTag.get(tag)
        if vo is not None:
          if isinstance(vo, VRelation):
            candidates[id(vo)] = vo
          else: # a node: a terminal of its relations may be on its edge
            for rel in vo.relations:
              candidates[id(rel)] = rel
    for rel in candidates.values():
      if rel._endpointsEditable() and rel._terminalAt(x, y) is not None:
        return rel
    return None

  def grabTerminalNear(self, event:tk.Event) -> bool:
    '''
    If a button-1 press is within reach of an editable relation's terminal --
    whatever's under it: the object the relation connects, a context window
    it's drawn in, or the background -- grab that terminal (see
    *VRelation.grabTerminal()*).

    :param event: The Tk event.
    :type event: tk.Event
    :returns: True iff it did (so the caller shouldn't start its own drag).
    :rtype: bool
    '''
    rel = self._relationTerminalNear(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    return rel is not None and rel.grabTerminal(event)

  HANDLE_CURSORS = {"nw": "top_left_corner", "ne": "top_right_corner",
                    "se": "bottom_right_corner", "sw": "bottom_left_corner"}
  "The cursors shown over a selected object's corner (resize) handles."

  def _handleNear(self, x:float, y:float) -> str|None:
    '''
    The corner of the selected object\'s resize handle at canvas (x, y), or None.

    :param x:
    :type x: float
    :param y:
    :type y: float
    :returns:
    :rtype: str | None
    '''
    from sn.view.graphics.decorators import Selected
    for obj in self.selected:
      sel = obj.decorators.get("selected") if obj.decorators else None
      if isinstance(sel, Selected):
        corner = sel.handleAt(x, y)
        if corner is not None:
          return corner
    return None

  def _updateTerminalCursor(self, event:tk.Event) -> None:
    '''
    Show a corner cursor (*HANDLE_CURSORS*) over a resize handle, or
    *TERMINAL_CURSOR* over a draggable relation terminal, restoring whatever
    cursor was there before (eg: the "hand" a node's *onEnter()* set) when the
    pointer moves off.

    :param event: The Tk event.
    :type event: tk.Event
    '''
    x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
    corner = self._handleNear(x, y)
    if corner is not None:
      want:str|None = self.HANDLE_CURSORS[corner]
    elif self._relationTerminalNear(x, y) is not None:
      want = self.TERMINAL_CURSOR
    else:
      want = None
    ours = {self.TERMINAL_CURSOR, *self.HANDLE_CURSORS.values()}
    current = str(self.canvas.cget("cursor"))
    if want is not None:
      if current != want:
        if current not in ours:
          self._cursorBeforeTerminal = current # (an item's <Enter>/<Leave> may have changed it meanwhile)
        self.canvas.configure(cursor=want)
    elif current in ours:
      self.canvas.configure(cursor=self._cursorBeforeTerminal or "arrow")

  def _trackElasticLine(self, event:tk.Event) -> None:
    '''
    Stretch the elastic line (see *elasticLineChoice()*) to the cursor.

    :param event: The Tk event.
    :type event: tk.Event
    '''
    assert self._elasticLineChoiceData is not None
    self.canvas.coords(self._elasticLineChoiceData.lineID,
          flattenPairs([self.viewToWindow(self._elasticLineChoiceData.originNode.centerPt()),
                    (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))]))

  def onButton_1(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :type event:
    :return: *None*
    
    If the SHIFT key is pressed: start a drag-scroll. Otherwise, unselect 
    everything and prepare for a possible selection box animation (if we get a 
    move event).

    Called on the *<Button-1>* event (when the mouse button 1 is pressed).

    * If *self._makeRelationFrom* is not *None*, return.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If the shift key is pressed start a scroll action and return.

    * Otherwise unselect everything and start a selection box action by setting
      up *self._selectionBoxInfo*.

    """
    # ignore if making a relation
    # if self._makingRelationFrom is not None: return
    if self._elasticLineChoiceData is not None: return

    # check of a widget has handled the event
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None

    # a relation's terminal, over the background (see grabTerminalNear())
    if not s_SHIFT(event.state) and self.grabTerminalNear(event):
      self.removeEventHandled(event)
      return None

    # shift-Button1 down: scroll
    if s_SHIFT(event.state):
      self._scrolling = True
      self.canvas.scan_mark(int(self.canvas.canvasx(event.x)), int(self.canvas.canvasy(event.y)))
      return

    # plain Button1 down: multi-select box
    for s in self.selected.copy():  # unselect everything
      s.selected(False)
    # 0:rect, 1:event-x, 2:event-y, 3:activated

    rect = self.viewToWindow(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    #rect = self.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
    #rect = [self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)]
    self._selectionBoxInfo = [
        self.canvas.create_rectangle(rect, fill="", width=3, outline="blue", dash=(1,6)), 
        rect[0], #event.x, 
        rect[1], #event.y, 
        False]

  def onB1_Motion(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :type event:
    :return: None
    
    If we are either drag-scrolling or drag-drawing a multi-selection
    box, continue the action.

    Called on the *<B1-Motion>* event (when the mouse moves with button1 pressed).

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If *self._scrolling* is not *None*, call *self.scan_dragto()*.

    * If *self._selectionBoxInfo* is not *None*, redraw the elastic selection box,
      using *self._selectionBoxInfo[3]* to note that the selection box is active.

    """
    try:
      # check of a widget has handled the event
      if self.isEventHandled(event):
        self.removeEventHandled(event)
        return None
  
      # an elastic line started by a press-and-drag (eg: grabbing a relation's
      # terminal -- see VRelation.onButton_1()) follows the drag
      if self._elasticLineChoiceData is not None:
        self._trackElasticLine(event)
        return

      # continue scrolling
      if self._scrolling:
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        return
  
      # adjust selection box
      if self._selectionBoxInfo is not None:
        self._selectionBoxInfo[3] = True # activated
        bb = self.viewToWindow(normalizeRect([self._selectionBoxInfo[1], self._selectionBoxInfo[2], self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)]))
        self.canvas.coords(self._selectionBoxInfo[0], bb)
    except:
      logger.exception("SNView.onB1_Motion()")

  def elasticLineChoice(self, originNode:VObject, 
                        callback:Callable[[VObject, VObject], Any],
                        filter:Callable[[VObject],bool]=lambda x: True, 
                        arrowHeads:int=2, color:str="cyan",
                        onEmpty:Callable[[VObject], Any]|None=None):
    '''
    Animate an elastic line from the *originNode* to the cursor to select an
    object for which *filter* returns True, then call *callback* with the *originNode*
    and the selected object.
    
    :param originNode: The object to root the elastic line one (and used as the first
      parameter to *callback*.
    :type originNode: VObject
    :param callback: The method to call after a selected selection.
    :type callback: Callable[[VObject, VObject], Any]
    :param filter: Objects are only selected if *filter(<obj>)* returns True. 
      [Optional, default=always True]
    :type filter: Callable[[VObject],bool]
    :param arrowHeads: 0=no arrowheads, 1=arrowhead at the origin, 2=arrowhead
      at the cursor, 3=arrowhead at both ends. For anything larger, just he lowest
      2 bits will be used. [Optional, default=2]
    :type arrowHeads: int
    :param color:
    :type color: str
    :param onEmpty: If given, called with *originNode* when the line is dropped
      on empty space (no object at all under the cursor); otherwise that
      abandons the choice, as Escape always does (see *cancelElasticLine()*).
    :type onEmpty: Callable[[VObject], Any] | None
    '''
    assert isinstance(originNode, VObject)
    arrowHeads %= 4 # strip any high bits
    match arrowHeads:
      case 1: arrow = tk.FIRST
      case 2: arrow = tk.LAST
      case 3: arrow = tk.BOTH
      case _: arrow = tk.NONE
    lineID = self.canvas.create_line( #type: ignore[call-overload]
      self.viewToWindow(flattenPairs([originNode.centerPt(), originNode.centerPt()])),
      fill=color, width=3, arrow=arrow)
    self._elasticLineChoiceData = SNGView.ElasticLineChoiceData(originNode, lineID, filter, callback, onEmpty)
    self.canvas.focus_set() # so Escape reaches us (see cancelElasticLine())

  def cancelElasticLine(self, event:tk.Event|None=None) -> None:
    '''
    Abandon an elastic-line choice in progress (bound to Escape) -- or, if there is none, clear the highlights.

    :param event: The Tk event.
    :type event: tk.Event | None
    '''
    if self._elasticLineChoiceData is not None:
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      self._elasticLineChoiceData = None
    else:
      self.clearHighlights()

  def clearHighlights(self) -> None:
    'Remove every object\'s highlight glow (see *VObject.highlight()*).'
    for vo in list(self._db.values()):
      if vo is not None and getattr(vo, "decorators", None) is not None:
        vo.highlight(False)

  def onB1_ButtonRelease(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :type event: tk.Event
    :return: None
    
    Depending on the context, finish creating a Relation or create a selection
    set from the selection box that just finished.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Set *self._scrolling* to *None*.

    * If *self._makingRelaionFrom* is not *None*:

      * Create a link according to the data in the *makeRelationData* structure
        and the *event*'s x,y coordinates

      * set *self._elasticLineChoiceData* to *None*.

    * If *self._selectionBoxInfo* is not *None*: This means we have finished
      drawing a selection box, so

      * deselect everything,

      * select everthing in the selection box, and

      * set *self._selectionBoxInfo* to *None*.
    """
    from sn.view.graphics.vnodes import VNode
    from sn.view.graphics.vrelations import VRelation
    self._scrolling = False
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    
    # # Handle elastic line object selection for making a Relation
    # if self._makingRelationFrom is not None:
    #   self.canvas.delete(self._makingRelationFrom.lineID)
    #   ids = self.canvas.find("closest", self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))  # find selected objects
    #   typeList:list[VObject]
    #   if isinstance(self._makingRelationFrom.node, VRelation):
    #     typeList = [r for r in self._db.values() if isinstance(r,VRelation)]
    #   elif isinstance(self._makingRelationFrom.node, VNode):
    #     typeList = [r for r in self._db.values() if isinstance(r,VNode)]
    #   else:
    #     typeList = []
    #   item = None
    #   for n in typeList:
    #     for _id in ids:
    #       tags = self.canvas.gettags(_id)
    #       if n.tag in tags:
    #         item = n  # this object is selected
    #         break
    #     else:
    #       continue  # only executed if the inner loop did NOT break
    #     break  # only executed if the inner loop DID break
    #   if item is not None:
    #     logger.debug(f"making relation from {self._makingRelationFrom.node} to {item} of type {self._makingRelationFrom.typ}.")
    #     self.makeRelation(self._makingRelationFrom.node, item, self._makingRelationFrom.typ)
    #   else:
    #     logger.debug("Relation's toNode must match the being a node/relation with the from Node.")
    #   self._makingRelationFrom = None
    #   return
      
    # Handle elastic line object selection for making a Relation
    if self._elasticLineChoiceData is not None:
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      # what's actually under the cursor (a small halo, not find("closest"),
      # which always returns *something*, however far away: dropping on empty
      # space must choose nothing)
      cx, cy = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
      ids = self.canvas.find_overlapping(cx - 2, cy - 2, cx + 2, cy + 2)
      typeList:list[VObject] = [n for n in self._db.values() \
                                if (self._elasticLineChoiceData.filter(n) \
                                    if self._elasticLineChoiceData.filter is not None \
                                    else True)] 
      item = None
      for n in typeList:
        for _id in ids:
          tags = self.canvas.gettags(_id)
          if n.tag in tags:
            item = n  # this object is selected
            break
        else:
          continue  # only executed if the inner loop did NOT break
        break  # only executed if the inner loop DID break
      self.canvas.delete(self._elasticLineChoiceData.lineID)
      if item is not None:
        self._elasticLineChoiceData.callback(self._elasticLineChoiceData.originNode, item)
      else:
        under = [n for n in self._db.values() if n is not None
                 and any(n.tag in self.canvas.gettags(_id) for _id in ids)]
        if under:
          logger.warning(f'"{under[0].name}" can\'t be chosen here.')
        elif self._elasticLineChoiceData.onEmpty is not None:
          self._elasticLineChoiceData.onEmpty(self._elasticLineChoiceData.originNode)
        else:
          logger.debug("Elastic line choice: nothing under the cursor; cancelled.")
      self._elasticLineChoiceData = None
      return
      
    # Handle a multi-selection box
    if self._selectionBoxInfo is not None:
      bb = self.canvas.coords(self._selectionBoxInfo[0])
      ids = tuple(self.canvas.find("overlapping", bb[0], bb[1], bb[2], bb[3]) if len(bb) == 4 else [])
      for s in self.selected.copy():  # unselect everything
        s.selected(False)
      for _id in ids:
        for n in self.values():  # self.nodes()+self.relations():
          if n._shape.id == _id:
            n.selected(True, _multi=True)
      self.canvas.delete(self._selectionBoxInfo[0])
      self.selectionBoxInfo = None

  def onMouseWheel(self, event):
    """
    :param event: *event.delta* contains the scroll offset.
    :type event:
    :return: None
    
    Y-axis scroll.

    Called on the two finger touchpad Y-scroll event.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Call *self.canvas.yview_scroll)*.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    self.canvas.yview_scroll(int(event.delta), 'units')

  def onShift_MouseWheel(self, event):
    """
    :param event: *event.delta* contains the scroll offset.
    :type event:
    :return: None
    
    X-axis scroll.

    Called on the two finger touchpad X-scroll event.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Call *self.canvas.xview_scroll)*.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    self.canvas.xview_scroll(int(event.delta), 'units')

  def makeRelationFrom(self, node:VObject, typ:Optional[Relation]=None):
    '''
    :param node: [VObject]
    :type node: VObject
    :param typ:
    :type typ: Optional[Relation]
    '''
    assert isinstance(node, VObject)
    
    def callback(originNode:VObject, selNode:VObject, typ):
      if selNode is not None:
        logger.debug(f"making relation from {originNode} to {selNode} of type {typ}.")
        self.makeRelation(originNode, selNode, typ)
      else:
        logger.debug("Relation's toNode must match the being a node/relation with the from Node.")
      
    
    if typ is None or (isinstance(typ, Relation) and typ.isType()):
      # lineID = self.canvas.create_line(
      #   self.viewToWindow(flattenPairs([node.centerPt(), node.centerPt()])),
      #   fill="cyan", width=3, arrow=tk.LAST)
      # self._makingRelationFrom = SNGView.makingRelationData(node, typ, lineID)
      # Dropped on empty space: a relation with no destination of its own -- it
      # inherits its type's range ("John -has-> <some phone>"). Not for isa:
      # an isa link needs both ends.
      onEmpty = None if typ is None or typ is self.model.ISA else \
        (lambda orig, typ=typ: self.makeRelation(orig, None, typ))
      self.elasticLineChoice(node, 
                             callback=lambda orig, sel, typ=typ: callback(orig, sel, typ), #type: ignore[misc]
                             arrowHeads=2, color="blue", onEmpty=onEmpty)
    else:
      if not isinstance(typ, Relation):
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument must be a model Relation; got object of class {type(typ).__name__}.')
      else:
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument "{typ.name}" must be type, not an individual;.')

  def makeRelation(self, fromNode:VObject, toNode:VObject|None, typ:Relation):
    '''
    Make an individual relation of type *typ* from *fromNode* to *toNode* --
    or, if *toNode* is None, with no destination of its own (so it inherits
    *typ*'s range: it's drawn to that, faded, or dangling if that's top).

    :param fromNode:
    :type fromNode: VObject
    :param toNode:
    :type toNode: VObject | None
    :param typ:
    :type typ: Relation
    '''
    assert isinstance(fromNode, VObject)
    assert toNode is None or isinstance(toNode, VObject)
    # Relations may connect nodes and relations in any combination (eg: a rule
    # -antecedent-> a relation) -- except isa links: a node isa a relation (or
    # vice versa) is an error.
    if toNode is not None and typ is self.model.ISA and isinstance(fromNode, VRelation) != isinstance(toNode, VRelation):
      logger.error("An isa link must be between two nodes or two relations.")
      return
    if typ and not isinstance(typ, Relation):
      logger.error(f'Relation typ {typ["label"]} must be a relation.', level='error')
      return
    try:
      # rel:GraphObject
      # if typ is self.model.ISA: #isinstance(typ, IsaIndividual):
      #   rel = IsaIndividual(self.model, src=fromNode.modelObject, dst=toNode.modelObject)
      # else:
      #   rel = Relation(self.model, parents=[typ], 
      #                  src=fromNode.modelObject, dst=toNode.modelObject, 
      #                  individual=True)
      # self.makeViewObjectForGraphObject(rel)
      with CompositeCommandMgr(self.context) as mgr: # (one undo, with any containment it lands in)
        self.context.new_relation([typ], individual=True, destination=None if toNode is None else toNode.modelObject,
                                  source=fromNode.modelObject, model=self.model)
        if toNode is not None and mgr.commands:
          self._containNewRelation(mgr, mgr.commands[-1], typ, fromNode, toNode)
    except Exception as ex:
      logger.exception("SNView.makeRelation():")
#       raise ex

  def isFiltered(self, mo:GraphObject, modes:Iterable[str]=("hide", "erase")) -> bool:
    '''
    True iff *mo* is in a category currently in one of *modes* (see *hides*).

    :param mo:
    :type mo: GraphObject
    :param modes:
    :type modes: Iterable[str]
    :returns:
    :rtype: bool
    '''
    active = [c for c, mode in self.hides.items() if mode in modes and c in self.categories.keys()]
    try:
      return bool(active) and self.categories.isCategory(mo, active)
    except Exception: # (eg: a half-built object)
      return False

  def _erasedRelation(self, rel:Relation) -> bool:
    '''
    Whether a new relation shouldn't be shown: it would bring an end in an
    erased category back into the view. (A relation that's in an erased
    category itself is shown, as anything made is: see *_exemptIfFiltered()*.)

    :param rel:
    :type rel: Relation
    :returns:
    :rtype: bool
    '''
    return any(e is not None and self.findViewObjectForGraphObject(e) is None and self.isFiltered(e, ("erase",))
               for e in (rel.localSrc, rel.localDst))

  def _exemptIfFiltered(self, vo:VObject) -> None:
    '''
    *vo* was just made (or shown explicitly): if it's in a hidden or erased
    category, show it anyway -- hiding is "soft": it applies to what was there
    when the category was hidden, and hiding the category again hides this too
    -- and say so (one message for everything made at once).

    :param vo:
    :type vo: VObject
    '''
    mo = vo.modelObject
    if mo is None or vo.categoryExempt or not self.isFiltered(mo):
      return
    vo.categoryExempt = True
    cats = [c for c, mode in self.hides.items() if c in self.categories.keys() and self.categories.isCategory(mo, [c])]
    pending = self.__dict__.setdefault("_exemptPending", {})
    if not pending and self.canvas:
      self.canvas.after_idle(self._reportExempt)
    label = vo.name or type(mo).__name__
    ends = [getattr(mo, "localSrc", None), getattr(mo, "localDst", None)]
    if all(e is not None for e in ends): # (a relation: by its ends, eg: "isa (tom → person)")
      label = f"{label} ({ends[0].name} → {ends[1].name})"
    for c in cats:
      pending.setdefault(c, []).append(label)
    vo._applyHidden()

  def _reportExempt(self) -> None:
    pending = self.__dict__.pop("_exemptPending", {})
    for c, names in pending.items():
      shown = ", ".join(dict.fromkeys(names)) # (once each, in order)
      mode = "hidden" if self.hides.get(c) == "hide" else "erased"
      menu = "hide" if mode == "hidden" else "erase"
      logger.warning(f'{shown}: in the {mode} category "{c}", but shown anyway, as it was just made (or asked for). '
                     f'To {menu} it too, {menu} "{c}" again: uncheck and re-check it in the {menu} menu.')

  def shouldHide(self, vo:VObject) -> bool:
    '''
    Whether *vo* shouldn't be drawn just now: it's in a hidden category; or
    it's a relation to or from something hidden (it would lead nowhere), or a
    containment drawn as being inside its window (see *VRelation.inWindow()*);
    or it's inside a hidden context's window.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    if mo is None:
      return False
    if self._inCollapsedWindow(vo):
      return True
    if self.isFiltered(mo, ("hide",)) and not vo.categoryExempt and not self._inShownContext(vo):
      return True
    if isinstance(vo, VRelation):
      if vo.inWindow():
        return True
      if any(isinstance(e, VObject) and e is not vo and e._isConnected() and e.isHidden() for e in (vo.src, vo.dst)):
        return True
    if self.hides: # (windows are only hidden by a category)
      for w in self.contextWindows():
        if w is not vo and w.isHidden() and w.paneAt(vo.centerPt()) is not None and w.containmentOf(mo):
          return True
    return False

  def _inCollapsedWindow(self, vo:VObject) -> bool:
    '''
    Whether *vo* is drawn inside a collapsed context window (see *VObject.setCollapsed()*), and so not shown.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    return any(w.collapsed and w is not vo and w.paneAt(vo.centerPt()) is not None and w.containmentOf(mo)
               for w in self.contextWindows())

  def _inShownContext(self, vo:VObject) -> bool:
    '''
    Whether *vo* is part of a shown context window's content (eg: an isa link
    in a rule's consequent): it's then shown whatever its category -- it's
    what the rule says, not clutter.

    :param vo:
    :type vo: VObject
    :returns:
    :rtype: bool
    '''
    mo = vo.modelObject
    return any(not w.isHidden() and not w.collapsed and w is not vo and w.containmentOf(mo) for w in self.contextWindows())

  def applyVisibility(self) -> None:
    'Bring every object into line with the current *hides* (see *VObject._applyHidden()*).'
    vos = [vo for vo in self.values() if vo is not None and vo._isConnected()]
    for vo in sorted(vos, key=lambda vo: isinstance(vo, VRelation)): # (nodes first: relations follow their ends)
      vo._applyHidden()
    self.drawInferences()

  def _visibilityMenu(self, mode:str) -> tk.Menu:
    '''
    A checkbox per category for *mode* ("hide" or "erase"): checking it sets
    that category to *mode* (so unchecks it in the other menu); unchecking it
    shows the category again.

    :param mode:
    :type mode: str
    :returns:
    :rtype: tk.Menu
    '''
    menu = tk.Menu(self.canvas)
    self._visibilityVars = getattr(self, "_visibilityVars", {}) # (keep the variables alive)
    for name in self.categories.keys():
      var = tk.BooleanVar(value=self.hides.get(name) == mode)
      self._visibilityVars[(mode, name)] = var
      menu.add_checkbutton(label=name, variable=var, onvalue=True, offvalue=False,
                           command=lambda n=name, v=var: self.context.visibility(n, mode if v.get() else "show")) #type: ignore[misc]
    return menu

  def _applyWhere(self, mo:GraphObject) -> None:
    '''
    A new object's name was typed with constraints, eg: "?p :where: alive":
    make them its "constraints" attribute. Only variables have constraints;
    for anything else, or constraints that can't be read, the name stays as
    typed (and a message says why).

    :param mo:
    :type mo: GraphObject
    '''
    name, text = splitWhere(mo.name)
    if not name.startswith("?"):
      logger.error(f'"{mo.name}": only variables (names starting with "?") have constraints.')
      return
    try:
      merged = mergeConstraints(None, text or "")
    except ConstraintError as ex:
      logger.error(f'"{mo.name}": the constraints can\'t be read ({ex}).')
      return
    mo["name"] = name
    if merged:
      mo.setAttr(CONSTRAINTS, Attribute(merged, str, VAR, CONSTRAINTS_NOTE))

  def structureChanged(self) -> None:
    '''
    Note that what's in the view, or the model, has changed: an object was
    added to or taken out of the view, or the model changed. What's worked out
    from that and remembered (see *contextWindows()*) is worked out afresh.
    '''
    self.__dict__["_structureVersion"] = self.__dict__.get("_structureVersion", 0) + 1

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
    if mo is None or vo.isHidden(): # (not what can't be seen)
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
    def area(w:VObject) -> float:
      x1, y1, x2, y2 = w.boundingBox()
      return (x2 - x1) * (y2 - y1)
    return min((w for w in self.contextWindows() if w not in exclude and not w.collapsed and w.paneAt(pt) is not None),
               key=area, default=None) # (not a collapsed one: what's dropped there couldn't be seen)

  def _paneType(self, pane:str) -> Relation:
    '''
    :param pane:
    :type pane: str
    :returns:
    :rtype: Relation
    '''
    m = self.model
    return {"contains": m.CONTAINS, "antecedent": m.ANTECEDENT, "consequent": m.CONSEQUENT,
            "definiendum": m.DEFINIENDUM, "definiens": m.DEFINIENS}[pane]

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
    along = set(draggedAlong)
    def endsIn(r:VRelation, w:VObject) -> int: # how many of relation r's ends are in w's window
      return sum(1 for e in (r.src, r.dst) if isinstance(e, VObject) and w.paneAt(e.centerPt()) is not None)
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
      for w in windows:
        if w is vo:
          continue
        rels = w.containmentOf(mo)
        if vo in along and isinstance(vo, VRelation):
          if w is target and endsIn(vo, w) < 2:
            continue
          if w is not target and rels and endsIn(vo, w) > 0:
            continue
        if w is target:
          want = self._paneType(w.paneAt(new)) #type: ignore[arg-type]
          if any(r.isa(want) for r in rels):
            continue
          others = [r for r in rels if any(r.isa(t) for t in (m.ANTECEDENT, m.CONSEQUENT, m.DEFINIENDUM, m.DEFINIENS))]
          if len(others) > 1: # in both panes: leave it be
            continue
          for r in others:    # switched panes
            self.context.remove(r)
          self.context.new_relation([want], individual=True, source=w.modelObject, destination=mo, model=self.model)
        elif rels and old is not None:
          # was it in w's window? (compare with where w was, if w moved too)
          wOld = oldCenters.get(w)
          if wOld is not None:
            wNew = w.centerPt()
            old = (old[0] + wNew[0] - wOld[0], old[1] + wNew[1] - wOld[1])
          if w.paneAt(old) is not None:
            for r in rels:
              self.context.remove(r)

  def isEventHandled(self, event:tk.Event) -> bool:
    """
    :param event: The event to test.
    :type event: tk.Event
    :returns: *True* iff *event* is the same physical event most recently
      passed to *addEventHandled()* (and not yet cleared by
      *removeEventHandled()*).
    :rtype: bool

    A canvas item's ``tag_bind`` callback and this canvas widget's own
    ``bind`` callback are dispatched independently by Tk, even for the
    exact same physical click -- returning ``"break"`` from the item's
    callback only suppresses *other item bindings*, not this canvas's own
    separate widget-level binding for the same event. This flag is how a
    contained VObject/item-level handler tells this canvas's own generic
    handler (e.g. *onRightMouse()*) "I already dealt with this one, skip
    your default behaviour."
    """
    return eventEqual(event, self._eventHandled)

  def addEventHandled(self, event:tk.Event) -> None:
    """
    Mark *event* as handled by a contained VObject/item-level callback, so
    this canvas's own separately-dispatched widget-level binding for the
    same event can detect that (via *isEventHandled()*) and skip its
    generic handling.

    :param event: The event that was just handled.
    :type event: tk.Event
    :rtype: None
    """
    self._eventHandled = event

  def removeEventHandled(self, event:tk.Event) -> None:
    """
    Clear the "handled" flag. Call this once *isEventHandled()* has been
    consulted (whether or not it returned *True*) so a later, distinct
    event isn't mistaken for an already-handled one.

    :param event: Unused (kept for symmetry with *addEventHandled()* and
      the analogous methods elsewhere, e.g. *SNView*).
    :type event: tk.Event
    :rtype: None
    """
    self._eventHandled = None

  def onRightMouse(self, event:tk.Event): # -> Optional[tk.Menu]:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :type event: tk.Event
    :return: None or the result of *self.makeMenu()*.
    :rtype:

    Called when the right mouse button is pressed (different for Mac and other OS's).

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return *None*.

    * Put up the popup menu (*self.makeMenu()*).
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    bgMenu = self.makeMenu(event)
    bgMenu.post(event.x_root, event.y_root)
    return "break"
  
  # ---- Menu handling ---------------------------------------------------------
  
  def makeMenu(self, event:tk.Event) -> tk.Menu:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
      (Only used for the location of a newly created node if that happens.)
    :type event: tk.Event
    :return: The newly created menu.
    :rtype: tk.Menu

    Create the popup menu for a *SNView* window. Does not display the menu,
    only creates it and returns it.
    """
    assert event is not None

    def makeShowMenu():
      newMenu = tk.Menu(self.canvas)
      # sort the list of individuals
      nodes = dict()
      nodeNames = []
      for i in self.model.values():
        if not(i.isIndividual() and isinstance(i, Relation)):
          nodes[i.name] = i
          nodeNames.append(i.name)
      nodeNames = sorted(nodeNames)
      # make a menu item for each
      for nn in nodeNames:
        newMenu.add_command(label=nodes[nn].name, command=lambda mo=nodes[nn]: self.makeViewObjectForGraphObject(mo)) #type: ignore[misc]
      return newMenu

    def fillModelSubmenu(menu:tk.Menu, model:Model, individual:bool, ptype:type):
      types = [v for v in model.values() if isinstance(v, ptype) and v.isType()]
      types.sort(key=lambda x: x.name) #sort by name alphabetically
      for t in types:
        if ptype is Node:
          fun = lambda t=t: self.context.new_node(t, name="", individual=individual, type=not individual)
        elif ptype is Relation:
          fun = lambda t=t: self.context.new_relation(t, name="", individual=individual, type=not individual)
        # elif ptype is Collection:
        #   fun = lambda t=t: self.context.new_collection(t, name="?", individual=individual)
        menu.add_command(label=t.name, command=fun)
  
    def makeModelSubmenu(individual:bool, ptype:type):
      newMenu:tk.Menu = tk.Menu(self.canvas)
      # process nodes in the included models
      for v in [self.model, Model.AllDBs["sn:/sn.xml"]]:
        assert isinstance(v, Model)
        m = tk.Menu(self.canvas)
        fillModelSubmenu(m, v, individual, ptype)
        newMenu.add_cascade(label=v.name, menu=m)
      # process own nodes
      #fillModelSubmenu(newMenu, self.model, individual, ptype)
      return newMenu

    bgMenu:tk.Menu = tk.Menu(self.canvas)

    # A menu command's callback runs on the main/GUI thread, where the
    # blocking builtin input() always raises RuntimeError — inputAsync()
    # returns immediately and delivers the typed line to onResult once the
    # user actually answers.
    # # "new instance" and "new subtype" for nodes menus
    modelEditMenu:tk.Menu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="model", menu=modelEditMenu)
    if self.isModelEditor():
      modelEditMenu.add_cascade(label="new instance of Node"   , menu=makeModelSubmenu(individual=True, ptype=Node))
      modelEditMenu.add_cascade(label="new subtype of Node"    , menu=makeModelSubmenu(individual=False, ptype=Node))
      modelEditMenu.add_cascade(label="new instance of Relation", menu=makeModelSubmenu(individual=True, ptype=Relation))
      modelEditMenu.add_cascade(label="new subtype of Relation", menu=makeModelSubmenu(individual=False, ptype=Relation))
      modelEditMenu.add_separator()
      # bgMenu.add_cascade(label="new instance of Collection", menu=makeModelSubmenu(individual=True, ptype=Collection))
      # bgMenu.add_cascade(label="new subtype of Collection", menu=makeModelSubmenu(individual=False, ptype=Collection))
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      modelEditMenu.add_command(label="validate", command=lambda o=self: o.context.view.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #type: ignore[misc]
    modelEditMenu.add_command(label="refresh all caches", command=lambda: [o.cache.refresh() for o in self.context.view.values()])
    
    viewMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="view", menu=viewMenu)
    viewMenu.add_command(label="show all", command=self.context.view.showAllModel)
    viewMenu.add_cascade(label="show node", menu=makeShowMenu())
    viewMenu.add_cascade(label="hide by category", menu=self._visibilityMenu("hide"))
    viewMenu.add_cascade(label="erase by category", menu=self._visibilityMenu("erase"))
    viewMenu.add_separator()
    viewMenu.add_cascade(label="Zoom", menu=self.makeZoomMenu(viewMenu))
    viewMenu.add_command(label="reset scroll region", command=lambda: self.resetScrollRegion(shrink=True))
    viewMenu.add_command(label="gather nodes", command=self.gatherNodes)
    viewMenu.add_cascade(label="animation layout", menu=self._animationLayoutMenu(viewMenu))
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      viewMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1])
    viewMenu.add_separator()
    viewMenu.add_command(label="float all relations", command=lambda: [r.floating(True) for r in self.context.view.values() if isinstance(r, VRelation) and r.modelObject is not None and r.modelObject.isIndividual()])

    reasonMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="reasoning", menu=reasonMenu)
    reasonMenu.add_command(label="clear highlights", command=self.clearHighlights, accelerator=KEY_CLEAR_HIGHLIGHTS[1])
    reasonMenu.add_command(label="reason", command=self.reason)
    reasonMenu.add_command(label="clear reasoning", command=self.clearReasoning,
                       state=tk.NORMAL if self.reasoning is not None else tk.DISABLED)
    # bgMenu.add_command(label="toggle field layout", command=self.onToggleFieldsLayout, accelerator=KEY_TOGGLE_FIELDS_LAYOUT[1])
    # bgMenu.add_command(label="show animation controls", command=self.onShowAnimationControls)
    # # from sn.view.animatedLayouts import testBones
    # # bgMenu.add_command(label="test bones", command=lambda s=self: testBones(s))
    #
    
    # "hide/enable" menu
    # hideEnableMenu = tk.Menu(self)
    # for name in self.categories.keys():
    #   hideEnableMenu.add_command(label=f'{"enable" if name in self.hiddenCategories else "hide"} {name}',
    #       command = lambda n=name: self.toggleCategory(n))
    # bgMenu.add_cascade(label="hide/enable", menu=hideEnableMenu)
    # bgMenu.add_separator()
    
    # "local layout" menu
    # localLayoutsMenu = tk.Menu(self)
    # self.suppressLocalLayoutButton = tk.BooleanVar(value=self._suppressLocalLayout)
    # self.radio = tk.StringVar(value=self.localLayoutName)
    # for name, obj in self.layoutObjects.items():
    #   if obj.isLocal():
    #     localLayoutsMenu.add_radiobutton(label=name, variable=self.radio, value=name, \
    #         command=lambda lo=obj, name=name: self.setLocalLayout(lo, name=name))
    # localLayoutsMenu.add_separator()
    # localLayoutsMenu.add_checkbutton(label="suppress autolayout", variable=self.suppressLocalLayoutButton,
    #     onvalue=True, offvalue=False,
    #     command=lambda val=not self.suppressLocalLayout(): self.suppressLocalLayout(val))
    # bgMenu.add_cascade(label="local layout", menu=localLayoutsMenu)
    
    # "global layout" menu
    # layoutsMenu = tk.Menu(self.canvas)
    # for name, obj in self.layoutObjects.items():
    #   if obj.isGlobal() and not obj.isLocal():
    #     layoutsMenu.add_command(label=name, command=obj)
    # layoutsMenu.add_separator()
    # for name, obj in self.layoutObjects.items():
    #   if obj.isGlobal() and obj.isLocal():
    #     layoutsMenu.add_command(label=name, command=obj)
    # bgMenu.add_cascade(label="global layout", menu=layoutsMenu)
    # bgMenu.add_command(label="reset scroll region", command=self.setScrollRegion)


    return bgMenu

  def makeZoomMenu(self, superMenu:tk.Menu) -> tk.Menu:
    '''
    :param superMenu:
    :type superMenu: tk.Menu
    :returns:
    :rtype: tk.Menu
    '''
    zoommenu = tk.Menu(superMenu)
    zoommenu.add_command(label="Normal Size", command=self.zoom)
    zoommenu.add_command(label="Zoom In", command=lambda: self.zoom(1.1, delta=True))
    zoommenu.add_command(label="Zoom Out", command=lambda: self.zoom(0.9, delta=True))
    zoommenu.add_separator()
    zoommenu.add_command(label="200%", command=lambda: self.zoom(2.0))
    zoommenu.add_command(label="150%", command=lambda: self.zoom(1.5))
    zoommenu.add_command(label="75%", command=lambda: self.zoom(0.75))
    zoommenu.add_command(label="50%", command=lambda: self.zoom(0.5))
    zoommenu.add_command(label="25%", command=lambda: self.zoom(0.25))
    return zoommenu

  def isModelEditor(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return True
  
  def zoom(self, scale:float=1.0, delta=False):
    """
    :param scale: the absolute scale, where 1.0 is "no scaling", unless *delta* is true, in which
            case, multiplier for the current scale (so numbers like 0.9 and 1.1 make sense).
    :type scale: float
    :param delta: True to do relative scaling, False to do absolute scaling.
    :type delta:
    """
    oldScale = self._scale
    if delta:
      self._scale *= scale
    else:
      self._scale = scale
    self.canvas.scale("all", 0, 0, self._scale / oldScale, self._scale / oldScale)
    for child_widget in self.canvas.find_withtag("text"):
      self.canvas.itemconfigure(child_widget, font=(self._fontFace, int(self._fontSize * self._scale)))
    for rec in self._inferences: # their label fonts (and label placement) too
      self._drawInference(rec)
    try:
      bb = list(self.canvas.bbox("all"))
    except:
      bb = [0, 0, 0, 0]
    bb = [0, 0, bb[2] + 800, bb[3] + 600]
    self.canvas.configure(scrollregion=bb) #type: ignore[call-overload]

  # ---- Utility ---------------------------------------------------------------

  def viewToWindow(self, *args) -> list[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :type args:
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from view to window coordinates.
    :rtype: list[float]
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0] # type: ignore[assignment]
    #assert len(args) % 2 == 0, f'args = {args}'
    ret = []
    for n in args:
      ret.append(n * self._scale)
    return ret

  def windowToView(self, *args) -> list[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :type args:
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from window to view coordinates.
    :rtype: list[float]
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0] # type: ignore[assignment]
    #assert len(args) % 2 == 0, f'args = {args}'
    ret = []
    for n in args:
      ret.append(n / self._scale)
    return ret

  def freshPaint(self):
    'Increments self._drawVersion so that graphic options can know whether to update of not.'''
    self._drawVersion += 1
    
  def repaintSoon(self) -> None:
    '''
    Repaint the whole view (see *repaint()*) once things are idle -- once, however
    many times this is called before then: eg: the moves of a whole run of the
    animation layout, recorded (or undone) as one command, each of which would
    otherwise repaint everything.
    '''
    if self.__dict__.get("_repaintPending"):
      return
    if not self.canvas:
      self.repaint()
      return
    self._repaintPending = True
    def go() -> None:
      self._repaintPending = False
      if not getattr(self, "_closed", False):
        self.repaint()
    self.canvas.after_idle(go)

  def repaint(self, event=None):
    '''
    :param event: The Tk event.
    :type event:
    '''
    self.freshPaint()
    for obj in self.context.view.values():
      if obj is not None:
        obj.draw()

  def resetScrollRegion(self, shrink:bool=False) -> None:
    '''
    Recompute the canvas's scroll region from the current extent of
    everything actually drawn on it, and apply it -- to *self.scrollRegion*
    itself (what *VObject.moveTo()*/*boundingBox()* clamp positions
    against -- see their docstrings) as well as to the canvas widget's own
    ``scrollregion`` configuration option.

    :param shrink: [default=False] Normally the region only grows (see below);
      True fits it to the drawing even if that makes it smaller -- for an
      explicit user request, when the view jumping to fit is expected.
    :type shrink: bool

    Called by *VObject.draw()* whenever a *VObject*'s bounding box no longer
    fits inside the existing region -- e.g. after it's been dragged past the
    SE edge -- so the canvas grows to keep the object reachable/visible.

    :note: This used to swallow every exception (bare ``except: pass``),
      which is exactly why the drag-past-the-edge case silently never grew
      the region: *self.canvas.bbox("all")* returns *None* when the canvas
      has nothing drawn on it yet, and ``expandRect(None, 100)`` raises
      *TypeError* -- caught and discarded here without a trace. That's now
      handled explicitly below instead of masked. It also never updated
      *self.scrollRegion* on success, so even a "successful" reset left
      *moveTo()*'s clamp still comparing against the stale old region.

    :rtype: None
    '''
    bb = self.canvas.bbox("all")
    if bb is None:  # nothing drawn yet -- nothing to size the region to
      return
    bb = tuple(expandRect(bb, 100)) #type: ignore[assignment] #mypy is fussy!
    # Only ever grow: shrinking the region can pull it out from under the
    # current view, and Tk then shifts the view to fit -- which makes the
    # whole drawing appear to jump (eg: mid-drag).
    sr = self.scrollRegion
    if shrink:
      bb = tuple(bb) #type: ignore[assignment] #mypy is fussy!
    else:
      bb = (min(bb[0], sr[0]), min(bb[1], sr[1]), max(bb[2], sr[2]), max(bb[3], sr[3]))
    if bb != tuple(sr):
      self.scrollRegion = bb
      self.canvas.configure(scrollregion=bb)

  @property
  def reasoning(self) -> Any:
    '''
    The *sn.model.reasoner.Inferences* from the last "reason" over this view's
    model -- whether run from this view's menu, another view of the same model,
    or the command line (see *sn.model.reasoner.reason()*) -- or None.

    :returns:
    :rtype: Any
    '''
    from sn.model.reasoner import reasoningFor
    return reasoningFor(self.model)

  def reason(self, engine:str="clingo") -> None:
    '''
    Run the reasoner over this view's model and print the report to this
    window's terminal. The results are kept with the model, so this and every
    other view of it show them (see *_showReasoning()*), as they do when
    "reason" is typed at the command line.

    :param engine:
    :type engine: str
    '''
    from sn.model.reasoner import reason
    try:
      result = reason(self.model, engine)
    except ImportError as ex:
      logger.error(f'The "{engine}" reasoner isn\'t available: {ex}')
      return
    print(f'Reasoning over {self.model.name}:')
    print(result.report(self.model))

  def clearReasoning(self) -> None:
    'Forget the last "reason" results for this view\'s model (in every view of it).'
    from sn.model.reasoner import clearReasoning
    clearReasoning(self.model)

  def _showReasoning(self) -> None:
    '''
    Show the model's current reasoning results (or their absence): violations
    in the objects' status reports (their error markers and "show error
    report"), and inferred and inherited relations as dashed lines.
    Called when the model reports a "reasoned" or "reasoning cleared" topic.
    '''
    self.clearInferences()
    self._refreshStatusReports()
    self.drawInferences()

  INFERENCE_COLOR = "gray45"
  INFERENCE_DASH = {"inferred": (6, 4), "inherited": (2, 3)}
  "Dash patterns: inferred relations are dashed, those inherited down the isa hierarchy dotted."

  def drawInferences(self) -> None:
    '''
    Draw the relations the last "reason" inferred (dashed) or found inherited
    down the isa hierarchy (dotted) as grey arrows with their relation type's
    name -- for those whose two ends are both shown in this view. A relation
    inferred in both directions gets one double-headed arrow. The lines follow
    their ends as they're moved or resized (see *updateInferencesFor()*), and
    never take mouse clicks.
    '''
    self.clearInferences()
    if self.reasoning is None or not self.canvas:
      return
    inherited = [(t, s, d) for t, s, d in self.reasoning.inherited]
    inheritedIds = {(id(t), id(s), id(d)) for t, s, d in inherited}
    inferred = [(t, s, d) for t, s, d in self.reasoning.inferred if (id(t), id(s), id(d)) not in inheritedIds]
    byKey:dict[tuple, dict[str, Any]] = {}
    inferred += [(self.model.ISA, x, t) for _, x, t in self.reasoning.ruleIsa] # (isa links the rules concluded)
    for kind, triples in (("inferred", inferred), ("inherited", inherited)):
      for t, s, d in triples:
        if not (isinstance(s, GraphObject) and isinstance(d, GraphObject)): # (eg: an object a rule creates)
          continue
        vs, vd = self.findViewObjectForGraphObject(s), self.findViewObjectForGraphObject(d)
        if vs is None or vd is None or vs is vd:
          continue
        reverse = byKey.get((id(t), id(vd), id(vs)))
        if reverse is not None: # the same relation both ways: one double-headed arrow
          reverse["both"] = True
          continue
        byKey[(id(t), id(vs), id(vd))] = {"type": t, "src": vs, "dst": vd, "kind": kind, "both": False,
                                          "line": None, "label": None, "patch": None}
    self._inferences = list(byKey.values())
    for rec in self._inferences:
      self._drawInference(rec)

  def _drawInference(self, rec:dict[str, Any]) -> None:
    '''
    Draw (or redraw) one inference: its label goes in a free spot near the
    middle of the straight line between the two objects (see
    *_freeLabelSpot()*), and the line is drawn as a smooth curve from the
    source's edge, through the label, to the destination's edge -- the way
    relations are drawn through their labels.

    :param rec:
    :type rec: dict[str, Any]
    '''
    from sn.view.graphics.connectors import _clipToEdgeStraight, _farPointAlong, _sub, PointType
    vs, vd = rec["src"], rec["dst"]
    hide = vs.isHidden() or vd.isHidden() # (see visibility())
    for k in ("line", "label", "patch"):
      if rec.get(k) is not None:
        self.canvas.itemconfigure(rec[k], state="hidden" if hide else "disabled")
    if hide:
      return
    cs, cd = vs.centerPt(), vd.centerPt()
    if cs == cd:
      return
    font = (self._fontFace, max(6, int(self._fontSize * 0.8 * self._scale)), "italic")
    if rec["label"] is None:
      rec["label"] = self.canvas.create_text(0, 0, text=rec["type"].name, fill=self.INFERENCE_COLOR, font=font,
                                             state="disabled", tags=["inference", "inference-label"])
    else:
      self.canvas.itemconfigure(rec["label"], font=font)

    # the label: a free spot near the middle of the straight line between the objects
    a = _clipToEdgeStraight(vs, _farPointAlong(vs, _sub(cd, cs)))
    b = _clipToEdgeStraight(vd, _farPointAlong(vd, _sub(cs, cd)))
    spot = self._freeLabelSpot(rec["label"], self.viewToWindow([a[0], a[1], b[0], b[1]]))
    self.canvas.coords(rec["label"], spot)

    # the line: through the label, clipped to each object's edge toward it
    lp = tuple(self.windowToView(spot))
    a = _clipToEdgeStraight(vs, _farPointAlong(vs, _sub(lp, cs)))
    b = _clipToEdgeStraight(vd, _farPointAlong(vd, _sub(lp, cd)))
    coords = self.viewToWindow([a[0], a[1], lp[0], lp[1], b[0], b[1]])
    lineOpts = dict(fill=self.INFERENCE_COLOR, dash=self.INFERENCE_DASH[rec["kind"]],
                    arrow=tk.BOTH if rec["both"] else tk.LAST, width=1, smooth=True)
    if rec["line"] is None:
      rec["line"] = self.canvas.create_line(coords, state="disabled", tags=["inference"], **lineOpts) #type: ignore[call-overload]
    else:
      self.canvas.coords(rec["line"], coords)
      self.canvas.itemconfigure(rec["line"], lineOpts)

    # a patch of background behind the label, so the line doesn't run through the text
    bb = self.canvas.bbox(rec["label"])
    patch = [bb[0] - 1, bb[1], bb[2] + 1, bb[3]] if bb else [0, 0, 0, 0]
    if rec.get("patch") is None:
      rec["patch"] = self.canvas.create_rectangle(patch, fill=self.canvas.cget("background"), outline="",
                                                  state="disabled", tags=["inference"])
    else:
      self.canvas.coords(rec["patch"], patch)
    self.canvas.tag_lower(rec["line"])               # the line under everything,
    self.canvas.tag_raise(rec["patch"], rec["line"]) # the patch over the line,
    self.canvas.tag_raise(rec["label"], rec["patch"]) # and the label over the patch

  def _freeLabelSpot(self, label:int, line:list[float]) -> tuple[float, float]:
    '''
    Where to centre an inference *label* on the straight *line* (window
    coords) so it doesn't sit on an object's shape or text, or on another
    inference label: the midpoint if that's free, otherwise the first free
    spot from positions further along the line and a little either side of
    it. If none is free, the midpoint.

    :param label:
    :type label: int
    :param line:
    :type line: list[float]
    :returns:
    :rtype: tuple[float, float]
    '''
    x1, y1, x2, y2 = line
    bb = self.canvas.bbox(label)
    w, h = (bb[2] - bb[0], bb[3] - bb[1]) if bb else (0, 0)
    length = max(1.0, sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2))
    nx, ny = -(y2 - y1) / length, (x2 - x1) / length # unit normal to the line
    blocking = ("vis/shape", "text", "inference-label")
    for f in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
      for side in (0, 1, -1, 2, -2):
        cx = x1 + (x2 - x1) * f + nx * side * (h + 2)
        cy = y1 + (y2 - y1) * f + ny * side * (h + 2)
        hits = self.canvas.find_overlapping(cx - w / 2 - 2, cy - h / 2 - 2, cx + w / 2 + 2, cy + h / 2 + 2)
        if not any(i != label and any(t in blocking for t in self.canvas.gettags(i)) for i in hits):
          return cx, cy
    return (x1 + x2) / 2, (y1 + y2) / 2

  def updateInferencesFor(self, vo:VObject) -> None:
    '''
    Redraw the inference lines attached to *vo* (eg: after it moved or was resized).

    :param vo:
    :type vo: VObject
    '''
    for rec in self._inferences:
      if rec["src"] is vo or rec["dst"] is vo:
        self._drawInference(rec)

  def clearInferences(self) -> None:
    if self.canvas:
      self.canvas.delete("inference")
    self._inferences = []

  def _refreshStatusReports(self) -> None:
    for vo in list(self._db.values()):
      if vo is not None:
        vo.clearStatusReport()
    self.validate(refresh=True)
    self.repaint()

  def animationLayout(self) -> Any:
    '''
    :returns: This view's animation layout (see *animatedLayouts.FieldsLayout_threaded*), made if need be.
    :rtype: FieldsLayout_threaded
    '''
    from sn.view.graphics.animatedLayouts import FieldsLayout_threaded
    layout = self.__dict__.get("_animationLayout")
    if layout is None:
      layout = self._animationLayout = FieldsLayout_threaded(self)
    return layout

  def _animationLayoutMenu(self, parent:tk.Menu) -> tk.Menu:
    '''
    The "animation layout" submenu: start/stop it, and its current: the direction
    it flows in (or none), its strength, and the relation type it lines up
    (dsts upstream of srcs: eg: "isa" flowing down gives a class diagram).

    :param parent: The menu it's a submenu of.
    :type parent: tk.Menu
    :returns: The submenu.
    :rtype: tk.Menu
    '''
    from sn.view.graphics.animatedLayouts import FLOW_DIRECTIONS
    layout = self.animationLayout()
    menu = tk.Menu(parent)
    menu.add_command(label="stop" if layout.active else "start", command=self.toggleAnimationLayout)
    menu.add_separator()
    self._flowVars = getattr(self, "_flowVars", {}) # (keep the variables alive)
    direction = tk.StringVar(value=layout.flowDirection or "none")
    self._flowVars["direction"] = direction
    dirMenu = tk.Menu(menu)
    for name in ["none", *FLOW_DIRECTIONS]:
      dirMenu.add_radiobutton(label=name, variable=direction, value=name,
                              command=lambda n=name: self.setAnimationSetting("flowDirection", None if n == "none" else n))
    menu.add_cascade(label="current direction", menu=dirMenu)
    strength = tk.DoubleVar(value=layout.flowStrength)
    self._flowVars["strength"] = strength
    strMenu = tk.Menu(menu)
    for label, value in (("weak", 3.0), ("medium", 6.0), ("strong", 10.0)):
      strMenu.add_radiobutton(label=label, variable=strength, value=value,
                              command=lambda v=value: self.setAnimationSetting("flowStrength", v))
    menu.add_cascade(label="current strength", menu=strMenu)
    relation = tk.StringVar(value=(layout.flowRelation or self.model.ISA).name)
    self._flowVars["relation"] = relation
    relMenu = tk.Menu(menu)
    types = [self.model.ISA] + sorted((r for r in self.model.values() if isinstance(r, Relation) and r.isType()
                                       and r is not self.model.ISA and not r.isSystemObject()), key=lambda r: r.name.lower())
    for t in types:
      relMenu.add_radiobutton(label=t.name, variable=relation, value=t.name,
                              command=lambda t=t: self.setAnimationSetting("flowRelation", None if t is self.model.ISA else t))
    menu.add_cascade(label="current follows", menu=relMenu)
    return menu

  def toggleAnimationLayout(self) -> None:
    '''
    Start (or, if it's running, stop) the animation layout: objects
    repel one another and relations pull them together, until things settle
    (see *animatedLayouts.FieldsLayout*). The whole run is one undoable command.
    '''
    layout = self.animationLayout()
    if layout.active:
      layout.kill()
      return
    layout(autoOff=True)

  def gatherNodes(self) -> None:
    '''
    Herd outlying objects -- eg: ones some layout bug has flung far from
    their companions -- back toward the main pack, as a single undoable
    command. See *layout.gatherShifts()* for the (per-axis) heuristic.

    Floating relations aren't moved directly: they re-centre themselves on
    their (moved) nodes.
    '''
    objs = [o for o in self.context.view.values()
            if o is not None and not o.isHidden() and not (isinstance(o, VRelation) and o.floating())]
    boxes = [o.boundingBox() for o in objs]
    moves = [(o, bb, dx, dy) for o, bb, (dx, dy) in zip(objs, boxes, gatherShifts(boxes))
             if dx or dy]
    if not moves:
      logger.info("gatherNodes(): nothing to gather.")
      return
    with CompositeCommandMgr(self.context):
      for o, bb, dx, dy in moves:
        self.context.move(o, bb[0] + dx, bb[1] + dy, _oldPos=bb, adjustPos=False)
    self.resetScrollRegion(shrink=True)
    logger.info(f"gatherNodes(): moved {len(moves)} of {len(objs)} objects.")

  def runBackgroundWork(self, fn: Callable[[], None]) -> None:
    """Launch background work (e.g. a long model computation triggered by the
    graphics editor) bound to THIS window's terminal, so its stdout/stderr/
    logging/input() output lands there regardless of what has focus by the
    time the work actually produces output.

    :param fn: The work to run.
    :type fn: Callable[[], None]
    :rtype: None
    """
    terminal = self.terminal  # set by AppPanedWidget after construction
    registry = terminal.registry

    def wrapped() -> None:
      registry.bindThreadToTerminal(terminal)
      try:
        fn()
      finally:
        registry.unbindThread()

    threading.Thread(target=wrapped, daemon=True).start()

  
        