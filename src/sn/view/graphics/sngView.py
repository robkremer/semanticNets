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
from sn.model.model import Model, Node, Relation, Collection, IsaIndividual,\
  GraphObject, GORef
from sn.controller.modelInterface import ModelContext

from typing import cast, override, Any, Iterable, Callable, Optional
from util.utils import bindRightMouse, fixURL, isValidURL, urlExists, expandRect,\
  flattenPairs, s_SHIFT, normalizeRect
from sn.view.graphics.utils import eventEqual, addToMenuBar, removeFromMenuBar
from util.terminal import inputAsync
from util.persistence.pRef import PRDb, PReference
from util.observer import Subject, Observer
from util.attributeEditor import applyEditAttrsBox
from sn.view.textUserInterface import UIContext, SNTerminalWidget
from util.command import Command
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import FindFree
from math import sqrt
from util.persistence.serialize import InstantiationInfo, PropertyInfo,\
  ParamInfo, Serializable, SerializableType
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
KEY_VALIDATE =              ('<Command-KeyPress-v>'       , 'cmd+v')
KEY_TOGGLE_FIELDS_LAYOUT =  ('<Command-KeyPress-f>'       , 'cmd+f')

class SNGContext(UIContext):
  #from sn.view.graphics.vobjects import VObject
  @override
  def __init__(self, model:Model, view:SNGView):
    super().__init__(model)
    self.view:SNGView = view
    self.defaults["view"] = view
    
  @override
  def _defineDecoders(self):
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
    self.view = view
    self.defaults["view"] = self.view
    
  def move(self, obj:"VObject", x:int|float, y:int|float): #type: ignore[name-defined]
    '''
    This is a dummy graphic command.
    '''
    print ("dummy graphic command")
    
  class _Move(Command):
    def __init__(self, obj:"VObject", x:int|float, y:int|float, oldPos:list[int]|None=None): #type: ignore[name-defined]
      '''
      :param oldPos: [Optional] The object's true position *before the drag
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
      :type oldPos: Optional[list[int]]
      '''
      super().__init__("move")
      self.obj:VObject = obj
      self.oldPos:list[int]|None = list(oldPos) if oldPos is not None else None
      self.x, self.y = x, y
      if isinstance(self.obj, VRelation):
        self.floating:bool = self.obj.floating()

    @override
    def do(self) -> None:
      super().do()
      if self.oldPos is None:
        self.oldPos = self.obj.boundingBox()
      self.obj.moveTo(self.x, self.y)
      self.obj.view.freshPaint()
      self.obj.view.repaint()
  
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
      self.obj.view.freshPaint()
      self.obj.view.repaint()
      
    @override
    def delete(self):
      super().delete()
      self.obj = None #type: ignore[assignment]
      
    @override
    def __str__(self):
      return f'{super().__str__()} {self.obj.name} {self.x} {self.y}'

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
        if verb == 'new':
          self.vobjects.append(tup[0])
      super().do()
      view = self.view
      if len(self.vobjects) == 0: # first call
        # setup a callback to place an newly created VObjects in self.vobjects
        detachCode = view.attachCallback(callback)
        for mo in self.modelObjects:
          self.view.makeViewObjectForGraphObject(mo) # seems odd, but the callback should add this to self.vobjects
        view.detachCallback(detachCode) # kill the callback
      else: # subsequent call
        n:VObject
        for n in self.vobjects:
          n._reconnect()
  
    @override
    def undo(self):
      super().undo()
      for vo in self.vobjects:
        vo._disconnect()
  
    @override
    def delete(self):
      super().delete()
      self.modelObjects = None # type: ignore[assignment]
      self.view = None # type: ignore[assignment]
      self.vobjects = None # type: ignore[assignment]
  
    @override
    def __str__(self):
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
      return f'{super().__str__()} {self.objects[0].getPRef().tostring()}'


  def expand(self, object:GraphObject):
    '''
    This is a dummy graphic command.
    '''
    print ("dummy graphic command")
    
  class _Expand(Command):
    def __init__(self, object:VObject, *, levels:int=0, _filter:Callable[[Any, Relation], bool]=lambda _vn, _mr: True):
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
        detachCode = view.attachCallback(lambda com, tup: self.createdObjects.append(tup[0]) if com=='new' else 0)
        self.obj.expand(filter=self.filter, expand=self.levels)
        print(f'ExpandCommand.do() created {len(self.createdObjects)} VObjects')
        view.detachCallback(detachCode)
      else:
        for obj in self.createdObjects:
          #obj.setHidden(False)
          obj._disconnect()
  
    @override
    def undo(self):
      Command.undo(self)
      for obj in self.createdObjects:
        #obj.setHidden()
        obj._reconnect()
        
    @override
    def delete(self):
      for obj in self.createdObjects:
        obj.delete()
      self.createdObjects = None #type: ignore[assignment]
  
    @override
    def __str__(self):
      return Command.__str__(self)

    

class SNGView(AbstractGraph["VObject", "VRelation"], Observer, Dirtyable):
  '''
  The persistent container of VObjects.
  '''

  makingRelationData = namedtuple('makeRelationData', 'node typ lineID')

  def __new__(cls, url:str, model:Model, *, mode="w", geometry:str="300x400+20+20", _reading:bool=False):
    if url is None:
      url = fixURL(model.url, extension=".snv", replaceExt=True, mode="w")[0]
    return PRDb.__new__(cls, url, mode=mode, memoryResident=False, _reading=_reading)

  def __init__(self, url:str, model:Model, *, mode="w", geometry:str="300x400+20+20", _reading:bool=False):
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
    
    # self.context._setView(self) # make this view the view of the context. #TODO: hackey ...
    self.selected:set[VObject] = set()
    'The set of currently selected VObjects.'
    self._suppressLocalLayout = False
    'Temporarily suppress automatic layout. Necessary during drag operations, etc.'
    self.localLayout = FindFree(self)

    self._eventHandled:Optional[tk.Event] = None
    "Set by a contained VObject/item-level handler (via addEventHandled()) to mark that it already handled a mouse event, so this canvas's own (separately-dispatched) widget-level binding for the same event -- e.g. onRightMouse() -- can skip its generic handling. See isEventHandled()/addEventHandled()/removeEventHandled()."

    self._drawVersion:int = 0
    self.scrollRegion:tuple = (0, 0, 4000, 3000)

    self.makeBindings()
     
    self._makingRelationFrom:SNGView.makingRelationData|None = None
    self._scrolling:bool = False
    

  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    def finalize(slf:Serializable, _:SerializableType):
      assert isinstance(slf, SNGView), f'Expected SNGView for param 1, got {type(slf)}.'
      slf.setDirty(False)
      for rel in list(slf.values()):
        if isinstance(rel, VRelation):
          rel.connect()
      slf.canvas.after_idle(slf.resetScrollRegion)
    ret:InstantiationInfo = super().getInstantiationInfo()
    # ret.class_ = cls
    ret.conArgs.append(ParamInfo("model", str, getter=lambda slf: cast(SNGView,slf).model.url, setter=lambda m: Model(cast(str,m))))
    ret.conKWArgs.append(ParamInfo("geometry", str, getter=lambda slf: cast(SNGView,slf).window.geometry()))
    ret.finalSetters.append(PropertyInfo("_", bool, setter=finalize))
    return ret

  
  @override
  def save(self, saveas:Optional[str]=None, overwrite=False, format:str="XML") -> None:
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

  @override
  def _register(self, value: VObject, _id:Optional[int]=None) -> int: # type: ignore[override]
    '''
    Overrides the 
    :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
    to restrict contained objects to :py:class:`GraphObject` subtypes. 
    *This violates subsumption rules, but that's what we want here!* 
    
    Also sets the dirty bit and notifies any observers ("add GraphObject" (GraphObject))
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
    '''
    super()._unregister(_id)
    self.setDirty()
    
  @override
  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]])->None:
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vnodes import VNode
    from sn.view.graphics.vrelations import VRelation #, VIsa
    assert isinstance(subject, Model), f'Expected Model, got {type(subject)}.'
    logger.info(f'SNGView.update({subject.name}, {len(topics)} topics):')
    for t in topics:
      topicName:str = t[0]
      topicData:tuple[Any, ...] = t[1]
      if topicName == 'add GraphObject':
        modelID = topicData[0]
        modelObj = topicData[1]
        logger.info(f'  Creating V{modelObj.__class__.__name__} for model object {modelObj}:{modelObj.__class__.__name__}')
        if (modelObj.isType() or isinstance(modelObj, Node)) and self.canvas: 
          applyEditAttrsBox(self.canvas, modelObj, title=modelObj.name, editKey="name")
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
          newObj = self.findViewObjectForGraphObject(modelObj) or VNode(self, modelObj)
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
          newObj = self.findViewObjectForGraphObject(modelObj) or VRelation(self, modelObj)
        # elif typ is IsaIndividual:
        #   newObj = VIsa(self, modelObj)
        else:
          logger.error(f"VObject subtype not implemented for model type {typ.__name__}.")

      elif topicName == 'del GraphObject':
        modelID == topicData[0]
        
        
      else:
        logger.warning(f'  Unsupported topic "{topicName}": {topicData}')

  def suppressLocalLayout(self, suppress:str|bool|None=None):
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
    :param tag: [str] A *str* *Canvas* tag.
    :param exclude: [list[int] or int, default=[]] A list of *int* representing *Canvas* ids.
    :return: A list of all ids in *ids* that have tag *tag* that are not in *exclude*.

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
    :param atPoint: [Optional, 2-Tuple[float]] The point where the new object
        should be displayed if it has to be created.
    :param expand: [Optional[int], default=None] The number of hops to expand.
    :param filter: Optional[Callable[[Self, Relation], bool]] A function *selfxRelation->bool*
        where that relation will only be expanded if the function returns *True*
    :return: If there is a *VObject* currently in the display representing *mObject* then
        that is returned, otherwise an attempt is make to create such an object referencing
        *mObject* and that is returned.
    '''
    from sn.view.graphics.vrelations import VRelation
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vnodes import VNode
    # make certain we don't make a duplicate    #createdVObjects:set[VObject] = set()
    ret = self.findViewObjectForGraphObject(mObject)
    if ret is None:
      if isinstance(mObject, Relation):
        ret = VRelation(self, modelObject=mObject)
      elif isinstance(mObject, (Node,GraphObject)):
        minSize = mObject.get('vis/minSize', snPrefs.get("gui/NodeMinSize", storeDefault=30))
        assert isinstance(minSize, (float,int))
        sizex = float(minSize)
        aspectRatio = mObject.get('vis/aspectRatio', snPrefs.get("gui/NodeAspectRatio", storeDefault=1.5))
        assert isinstance(aspectRatio, (float,int))
        sizey = int(sizex / aspectRatio)
        if atPoint is None:
          # try:
          #   mParent = mObject.getParents().__next__()
          #   vParent = self.findViewObjectForGraphObject(mParent)
          # except StopIteration: # no parent
          #   vParent = None
          # if vParent is None:
          #   x, y = self.newNodeCoords
          # else:
          #  bb = vParent.boundingBox()
          #  x = bb[0]
          #  y = bb[1] + 120
          #TODO: Do some reasonable placement.
          x, y = 0, 0
        else:
          x, y = int(atPoint[0]), int(atPoint[1])
        ret = VNode(self, mObject, x=x, y=y, x1=int(x + sizex), y1=int(y + sizey))
      else:
        raise AttributeError(f'SNView.makeViewObjectforGraphObject(): unexpected model object type: {mObject.__class__.__name__}.')

    assert isinstance(ret, VObject), f'SNView.makeViewObjectForGraphObject(): Unexpected return type "{ret.__class__.__name__}".'
    if expand > 0:
      ret.expand(filter=filter, expand=expand - 1)
    return ret

  def findViewObjectForGraphObject(self, mObject:GraphObject|Callable[[VObject],bool]) -> VObject|None:
    '''
    :param mObject: A model object.
    :return: A *VObject* currently in the display representing *mObject*, or *None* if there is not such object.
    '''
    if not isinstance(mObject, GraphObject):
      raise AttributeError(f'Expected a param of type GraphObject, but got type {mObject.__class__.__name__}')
    for obj in self.values():
      if obj.modelObject is mObject:  # already displayed?
        return obj
    return None

  def validate(self, refresh:bool=False) -> int:
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
        logger.error(f'Found {len(count)+1} visual objects representing model object {vobj.modelObject.name}#{vobj.modelObject.id}: {[o.id for o in [vobj]+count]}.' )
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
      vObj = self.findViewObjectForGraphObject(mnode)
      if vObj is None:# and not self.categories.isCategory(mnode, self.hiddenCategories):
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
    self.context.undo()
    self.addEventHandled(event)
    
  def onRedo(self, event:tk.Event):
    self.context.redo()
    self.addEventHandled(event)
    
  def onMotion(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None
    
    If there's a _makingRelationFrom going on (elastic line), then continue the
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
    if self._makingRelationFrom is not None:
      self.canvas.coords(self._makingRelationFrom.lineID,
            flattenPairs([self.viewToWindow(self._makingRelationFrom.node.centerPt()),
                      (self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))]))
      return

  def onButton_1(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
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
    if self._makingRelationFrom is not None: return

    # check of a widget has handled the event
    if self.isEventHandled(event):
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
    self._selectionBoxInfo:list[Any] = [
        self.canvas.create_rectangle(rect, fill="", width=3, outline="blue", dash=(1,6)), 
        rect[0], #event.x, 
        rect[1], #event.y, 
        False]

  def onB1_Motion(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
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

  def onB1_ButtonRelease(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None
    
    Depending on the context, finish creating a Relation or create a selection
    set from the selection box that just finished.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Set *self._scrolling* to *None*.

    * If *self._makingRelaionFrom* is not *None*:

      * Create a link according to the data in the *makeRelationData* structure
        and the *event*'s x,y coordinates

      * set *self._makingRelationFrom* to *None*.

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
    
    # Handle elastic line object selection for making a Relation
    if self._makingRelationFrom is not None:
      self.canvas.delete(self._makingRelationFrom.lineID)
      ids = self.canvas.find("closest", self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))  # find selected objects
#     logger.write(f"graphs making relation for {ids}", level='info')
      typeList:list[VObject]
      if isinstance(self._makingRelationFrom.node, VRelation):
        typeList = [r for r in self._db.values() if isinstance(r,VRelation)]
      elif isinstance(self._makingRelationFrom.node, VNode):
        typeList = [r for r in self._db.values() if isinstance(r,VNode)]
      else:
        typeList = []
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
      if item is not None:
        logger.debug(f"making relation from {self._makingRelationFrom.node} to {item} of type {self._makingRelationFrom.typ}.")
        self.makeRelation(self._makingRelationFrom.node, item, self._makingRelationFrom.typ)
      else:
        logger.debug("Relation's toNode must match the being a node/relation with the from Node.")
      self._makingRelationFrom = None
      return
      
    # Handle a multi-selection box
    if self._selectionBoxInfo is not None:
      bb = self.canvas.coords(self._selectionBoxInfo[0])
      ids = self.canvas.find("overlapping", bb[0], bb[1], bb[2], bb[3]) if len(bb) == 4 else []
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
    '''
    from sn.view.graphics.vobjects import VObject
    assert isinstance(node, VObject)
    if typ is None or (isinstance(typ, Relation) and typ.isType()):
      lineID = self.canvas.create_line(
        self.viewToWindow(flattenPairs([node.centerPt(), node.centerPt()])),
        fill="cyan", width=3, arrow=tk.LAST)
      self._makingRelationFrom = SNGView.makingRelationData(node, typ, lineID)
    else:
      if not isinstance(typ, Relation):
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument must be a model Relation; got object of class {type(typ).__name__}.')
      else:
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument "{typ.name}" must be type, not an individual;.')

  def makeRelation(self, fromNode:VObject, toNode:VObject, typ:Relation):
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vrelations import VRelation
    assert isinstance(fromNode, VObject)
    assert isinstance(toNode, VObject)
    if      isinstance(fromNode, VRelation) and not isinstance(toNode, VRelation) or \
        not isinstance(fromNode, VRelation) and     isinstance(toNode, VRelation):
      logger.error("Relations must be either between nodes or between relations only.")
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
      self.context.new_relation([typ], individual=True, destination=toNode.modelObject, source=fromNode.modelObject, model=self.model)
    except Exception as ex:
      logger.exception("SNView.makeRelation():")
#       raise ex

  def isEventHandled(self, event:tk.Event) -> bool:
    """
    :param event: The event to test.
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
    :rtype: None
    """
    self._eventHandled = None

  def onRightMouse(self, event:tk.Event): # -> Optional[tk.Menu]:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None or the result of *self.makeMenu()*.

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
    :return: The newly created menu.

    Create the popup menu for a *SNView* window. Does not display the menu,
    only creates it and returns it.
    """
    assert event is not None
    x = event.x
    y = event.y
    bgMenu:tk.Menu = tk.Menu(self.canvas)

    # A menu command's callback runs on the main/GUI thread, where the
    # blocking builtin input() always raises RuntimeError — inputAsync()
    # returns immediately and delivers the typed line to onResult once the
    # user actually answers.
    # # "new instance" and "new subtype" for nodes menus
    if self.isModelEditor():
      def fillMenu(menu:tk.Menu, model:Model, individual:bool, ptype:type):
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
    
      def makeSubmenu(individual:bool, ptype:type):
        newMenu:tk.Menu = tk.Menu(self.canvas)
        # process nodes in the included models
        for v in [self.model, Model.AllDBs["sn:/sn.xml"]]:
          assert isinstance(v, Model)
          m = tk.Menu(self.canvas)
          fillMenu(m, v, individual, ptype)
          newMenu.add_cascade(label=v.name, menu=m)
        # process own nodes
        #fillMenu(newMenu, self.model, individual, ptype)
        return newMenu
    
      modelEditMenu:tk.Menu = tk.Menu(self.canvas)
      modelEditMenu.add_cascade(label="new instance of Node"   , menu=makeSubmenu(individual=True, ptype=Node))
      modelEditMenu.add_cascade(label="new subtype of Node"    , menu=makeSubmenu(individual=False, ptype=Node))
      modelEditMenu.add_cascade(label="new instance of Relation", menu=makeSubmenu(individual=True, ptype=Relation))
      modelEditMenu.add_cascade(label="new subtype of Relation", menu=makeSubmenu(individual=False, ptype=Relation))
      # bgMenu.add_cascade(label="new instance of Collection", menu=makeSubmenu(individual=True, ptype=Collection))
      # bgMenu.add_cascade(label="new subtype of Collection", menu=makeSubmenu(individual=False, ptype=Collection))
      bgMenu.add_cascade(label="edit model", menu=modelEditMenu)
      bgMenu.add_separator()
      bgMenu.add_separator()
    
    bgMenu.add_command(label="float all", command=lambda: [r.floating(True) for r in self.context.view.values() if isinstance(r, VRelation) and r.modelObject.isIndividual()])
    bgMenu.add_command(label="refresh all", command=lambda: [o.cache.refresh() for o in self.context.view.values()])
    bgMenu.add_command(label="show all", command=self.context.view.showAllModel)
    bgMenu.add_command(label="reset scroll region", command=self.resetScrollRegion)
    # bgMenu.add_command(label="toggle field layout", command=self.onToggleFieldsLayout, accelerator=KEY_TOGGLE_FIELDS_LAYOUT[1])
    # bgMenu.add_command(label="show animation controls", command=self.onShowAnimationControls)
    # # from sn.view.animatedLayouts import testBones
    # # bgMenu.add_command(label="test bones", command=lambda s=self: testBones(s))
    #
    def makeShowMenu():
      newMenu = tk.Menu(self.canvas)
      # sort the list of individuals
      nodes = dict()
      nodeNames = []
      for i in self.model.values():
        #if i.isIndividual():
          nodes[i.name] = i
          nodeNames.append(i.name)
      nodeNames = sorted(nodeNames)
      # make a menu item for each
      for nn in nodeNames:
        newMenu.add_command(label=nodes[nn].name, command=lambda mo=nodes[nn]: self.makeViewObjectForGraphObject(mo))
      return newMenu
    bgMenu.add_cascade(label="show", menu=makeShowMenu())
    
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

    zoommenu = tk.Menu(bgMenu)
    zoommenu.add_command(label="Normal Size", command=self.zoom)
    zoommenu.add_command(label="Zoom In", command=lambda: self.zoom(1.1, delta=True))
    zoommenu.add_command(label="Zoom Out", command=lambda: self.zoom(0.9, delta=True))
    zoommenu.add_separator()
    zoommenu.add_command(label="200%", command=lambda: self.zoom(2.0))
    zoommenu.add_command(label="150%", command=lambda: self.zoom(1.5))
    zoommenu.add_command(label="75%", command=lambda: self.zoom(0.75))
    zoommenu.add_command(label="50%", command=lambda: self.zoom(0.5))
    zoommenu.add_command(label="25%", command=lambda: self.zoom(0.25))
    bgMenu.add_cascade(label="Zoom", menu=zoommenu)

    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      bgMenu.add_separator()
      bgMenu.add_command(label="validate", command=lambda o=self: o.context.view.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #type: ignore[misc]
      bgMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1])

    return bgMenu

  def isModelEditor(self) -> bool:
    return True
  
  def zoom(self, scale:float=1.0, delta=False):
    """
    :param scale: the absolute scale, where 1.0 is "no scaling", unless *delta* is true, in which
            case, multiplier for the current scale (so numbers like 0.9 and 1.1 make sense).
    :param delta: True to do relative scaling, False to do absolute scaling.
    """
    oldScale = self._scale
    if delta:
      self._scale *= scale
    else:
      self._scale = scale
    self.canvas.scale("all", 0, 0, self._scale / oldScale, self._scale / oldScale)
    for child_widget in self.canvas.find_withtag("text"):
      self.canvas.itemconfigure(child_widget, font=(self._fontFace, int(self._fontSize * self._scale)))
    try:
      bb = list(self.canvas.bbox("all"))
    except:
      bb = [0, 0, 0, 0]
    bb = [0, 0, bb[2] + 800, bb[3] + 600]
    self.canvas.configure(scrollregion=bb)

  # ---- Utility ---------------------------------------------------------------

  def viewToWindow(self, *args) -> list[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from view to window coordinates.
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
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from window to view coordinates.
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
    
  def repaint(self, event=None):
    self.freshPaint()
    for obj in self.context.view.values():
#      if not obj.isHidden():
        obj.draw()

  def resetScrollRegion(self) -> None:
    '''
    Recompute the canvas's scroll region from the current extent of
    everything actually drawn on it, and apply it -- to *self.scrollRegion*
    itself (what *VObject.moveTo()*/*boundingBox()* clamp positions
    against -- see their docstrings) as well as to the canvas widget's own
    ``scrollregion`` configuration option.

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
    bb = tuple(expandRect(bb, 100))
    self.scrollRegion = bb
    self.canvas.configure(scrollregion=bb)

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

  
        