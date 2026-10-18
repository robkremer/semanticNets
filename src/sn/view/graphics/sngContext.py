'''
The context of a graphical view (*SNGContext*): the commands a view adds to
its model's (see *sn.controller.modelInterface.ModelContext*) -- moving,
resizing, collapsing, showing (representing), erasing, pasting, hiding and
expanding its objects -- each an undoable command (its own class, inside the
context, implements it). Every view (*sn.view.graphics.sngView.SNGView*) has one.

Created on Oct 18, 2026 (from sngView.py)

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
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
from typing import Any, Callable, override, TYPE_CHECKING
from util.command import Command
from util.persistence.pRef import PReference
from sn.model.model import Model, Relation, GraphObject
from sn.controller.modelInterface import ModelContext
from sn.view.textUserInterface import UIContext
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.viewCommands import ViewDoList
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView # (sngView imports this module: the view is imported where it's needed at run time)

class SNGContext(UIContext):
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
    self.doList = self.parser.doList = ViewDoList(view) # (bumps what's left in a window it doesn't belong in)
    
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
    
  def move(self, obj:"VObject", x:int|float, y:int|float, _oldPos:list[int]|None=None, adjustPos:bool=True, _carry:bool=True, #type: ignore[name-defined]
           _wasFloating:bool|None=None, _drag:bool=False):
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
    :param _carry:
    :type _carry: bool
    :param _wasFloating:
    :type _wasFloating: bool | None
    :param _drag:
    :type _drag: bool
    '''
    print ("dummy graphic command")

  class _Move(Command):
    def __init__(self, obj:"VObject", x:int|float, y:int|float, _oldPos:list[int]|None=None, adjustPos:bool=True, _carry:bool=True, #type: ignore[name-defined]
                 _wasFloating:bool|None=None, _drag:bool=False):
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
      :param _carry: [default=True] Passed to *obj.moveTo()*: whether a context
        window carries what's inside it along. A move that's one of many (eg: a
        layout's) whose contents are moved by their own commands passes False:
        otherwise redoing or undoing it would move them twice.
      :type _carry: bool
      :param _wasFloating: [Optional] For a relation's label placed by a layout:
        whether it floated (between its ends) before -- the move pins it (it
        no longer floats), and undoing it puts that back.
      :type _wasFloating: bool | None
      :param _drag: [default=False] Whether it's the user dropping something they
        dragged (see *VObject.onB1_ButtonRelease()*), not a program moving it:
        eg: a tree layout pins a dragged node where it's dropped (see
        *treeLayout.TreeLayout.adjust()*).
      :type _drag: bool
      '''
      super().__init__("move")
      self.drag:bool = _drag
      self.obj:VObject = obj
      self.oldPos:list[int]|None = list(_oldPos) if _oldPos is not None else None
      self.x, self.y = x, y
      self.adjustPos = adjustPos
      self.carry = _carry
      self.pin = _wasFloating is not None
      if isinstance(self.obj, VRelation):
        self.floating:bool = self.obj.floating() if _wasFloating is None else _wasFloating

    @override
    def do(self) -> None:
      super().do()
      if self.oldPos is None:
        self.oldPos = self.obj.boundingBox()
      if self.pin and isinstance(self.obj, VRelation):
        self.obj._floatingAnchor = False # (directly: not recentred between its ends first)
      self.obj.moveTo(self.x, self.y, adjustPos=self.adjustPos, carry=self.carry)
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
      self.obj.moveTo(self.oldPos[0], self.oldPos[1], adjustPos=False, carry=self.carry)
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
      from sn.view.graphics.sngView import SNGView # (a circular import, made here: see the module's imports)
      assert isinstance(self.view, SNGView), f'Expected SNGView, got {type(self.view)}.'
      self.modelObjects:list[GraphObject] = []
      assert isinstance(self.modelObjects, list), f'Expected list, got {type(self.modelObjects)}.'
      n:GraphObject|str
      for n in objects: # convert from str to GraphObject if necessary
        temp:Any = PReference.eval(n) if type(n) is str else n
        assert isinstance(temp, GraphObject)
        self.modelObjects.append(temp)
      self.vobjects:list[VObject] = []
  
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
      return f'{super().__str__()} {" ".join([mo.name for mo in self.modelObjects])} --view {self.view}'


  # This is just a signature -- the behaviour is in class _New_node.
  def erase(self, object:VObject, others:list[VObject]|None=None): # pylint: disable=redefined-builtin
    '''
    Delete a *GraphObject*.
    
    :param object: The *VObject* to delete from the view.
    :type object: VObject
    :param others: More to delete with it, in the same command (see *SNGView.doErase()*).
    :type others: list[VObject] | None
    '''
    pass
    
  class _Erase(Command):
    def __init__(self, object:VObject, others:list[VObject]|None=None): # pylint: disable=redefined-builtin
      '''
      Delete a object from it's model.
      
      :param object: The object to delete from the view.
      :type object: VObject
      :param others: More to delete with it -- else, if *object* is selected,
        the rest of the selection.
      :type others: list[VObject] | None
      '''
      # param checking...
      super().__init__("remove")
      if others is not None:
        self.objects:list[VObject] = [object] + [o for o in others if o is not object]
      else:
        self.objects = list(object.view.selected) if object.selected() else [object]
    
    @override
    def do(self):
      super().do()
      self.erased:list[VObject] = [] # (not those taken out with another: eg: a node's relations -- it puts them back)
      with self.objects[0].view.batchedItemStates():
        for obj in self.objects:
          if obj._isConnected():
            obj._disconnect()
            self.erased.append(obj)
  
    @override
    def undo(self):
      super().undo()
      with self.objects[0].view.batchedItemStates():
        for obj in reversed(self.erased): # (the ends of relations before the relations)
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


  @override
  def paste(self, /, model:Model|None=None, x:int|None=None, y:int|None=None):
    '''
    Make new objects in the model -- with new ids -- copying what was last cut
    or copied (see *ModelContext.paste()*), and show them in this view as the
    originals were shown (see *SNGView.showPasted()*): where they were, or
    beside them if that's taken -- or with their top left at (*x*, *y*).

    :param model: The Model to paste into. Default: the current model.
    :type model: Model
    :param x: Where to put them (view coords), with *y*.
    :type x: int | None
    :param y:
    :type y: int | None
    '''
    pass

  class _Paste(ModelContext._Paste):
    def __init__(self, /, model:Model|None=None, x:int|None=None, y:int|None=None, view:SNGView|None=None):
      '''
      Make new objects in the model, copying what was last cut or copied, and
      show them as the originals were shown.

      :param model:
      :type model: Model | None
      :param x:
      :type x: int | None
      :param y:
      :type y: int | None
      :param view:
      :type view: SNGView | None
      '''
      super().__init__(model=model)
      self.view:SNGView|None = view
      self.at:tuple[int, int]|None = None if x is None or y is None else (int(x), int(y))

    @override
    def do(self) -> list[GraphObject]:
      first = self.made is None
      ret = super().do()
      if first and self.view is not None and self.model is self.view.model: # (not if it's pasted into another model)
        self.view.showPasted(self.clip, ret, self.at)
      return ret

    @override
    def delete(self):
      super().delete()
      self.view = None

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
        mo = vo.modelObject
        if not vo._isConnected() and (mo is None or mo._isConnected()): # (not an inferred object a later "reason" took out of the model)
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

  def expand(self, object:VObject, *, levels:int=0, _filter:Callable[[Any, Relation], bool]=lambda _vn, _mr: True):
    '''
    This is a dummy graphic command (the command is *_Expand*).

    :param object:
    :type object: VObject
    :param levels:
    :type levels: int
    :param _filter:
    :type _filter: Callable[[Any, Relation], bool]
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
      self.exempted:list[VObject] = []
      "What was shown though in a hidden category (see *VObject.expand()*): hidden again by an undo."
      self.originalDo:bool = True
            
    @override
    def do(self) -> None:
      Command.do(self)
      if self.originalDo:
        self.originalDo = False
        self.createdObjects = []
        view:SNGView =self.obj.view
        detachCode = view.attachCallback(lambda com, tup: self.createdObjects.append(tup[1]) if com=='new' else 0) # (tup is (id, VObject))
        self.obj.expand(filter=self.filter, expand=self.levels, _exempted=self.exempted)
        view.detachCallback(detachCode)
      else: # redo: nodes first (see _Represent.do())
        for obj in sorted(self.createdObjects, key=lambda vo: isinstance(vo, VRelation)):
          if not obj._isConnected():
            obj._reconnect()
        for obj in self.exempted:
          if obj._isConnected() and not obj.categoryExempt:
            obj.categoryExempt = True
            obj._applyHidden()
  
    @override
    def undo(self):
      Command.undo(self)
      for obj in reversed(self.createdObjects):
        if obj._isConnected():
          obj._disconnect()
      for obj in self.exempted: # (in a hidden category again)
        if obj._isConnected() and obj.categoryExempt:
          obj.categoryExempt = False
          obj._applyHidden()
        
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
