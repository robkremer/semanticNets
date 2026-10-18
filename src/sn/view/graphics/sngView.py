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
from sn.model.model import Model, Node, Relation, Collection, IsaIndividual, GraphObject

from functools import partial
from typing import cast, override, Any, Iterable, Callable, Optional
from util.utils import bindRightMouse, fixURL, flattenPairs, s_SHIFT, s_CMD, s_ALT, normalizeRect
from sn.view.graphics.utils import eventEqual
from util.persistence.pRef import PRDb
from util.observer import Subject, Observer
from sn.view.textUserInterface import SNTerminalWidget
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import FindFree, LayoutHeuristic, finishTween
import sn.view.graphics.treeLayout # (registers the tree layout: see layout.LAYOUTS)
import sn.view.graphics.balloonLayout # (registers the balloon, radial and hub layouts)
from sn.view.graphics.decorators import NOMINAL_ASPECT
from util.utils import Categories
from util.persistence.serialize import InstantiationInfo, PropertyInfo,\
  ParamInfo, Serializable, SerializableType
from util.persistence.serialize import DEFAULT_STRATEGY
from sn.view.graphics.guiApp import AppWindow
from sn.view.graphics.directoryWindow import noteSaved
from sn.view.graphics.sngContext import SNGContext
from sn.view.graphics.viewBase import ViewBase, KEY_UNDO, KEY_REDO, KEY_REPAINT, KEY_CUT, KEY_COPY, KEY_PASTE, KEY_COPY_IMAGE, KEY_SELECT_ALL, KEY_ERASE, KEY_REMOVE, KEY_CLEAR_HIGHLIGHTS, KEY_VALIDATE, KEY_FIND, KEY_ZOOM_IN, KEY_ZOOM_OUT, KEY_ZOOM_NORMAL, KEY_ZOOM_FIT
from sn.view.graphics.viewViewport import ViewportMixin
from sn.view.graphics.viewReasoning import ReasoningMixin
from sn.view.graphics.viewLayouts import LayoutsMixin
from sn.view.graphics.viewFiles import FilesMixin
from sn.view.graphics.viewVisibility import VisibilityMixin
from sn.view.graphics.viewContainment import ContainmentMixin
from sn.view.graphics.viewEditing import EditingMixin
import threading
from util.abstractGraph import AbstractGraph
from util.dirtyable import Dirtyable
from collections import namedtuple

logger:sn.SNLogger = sn.getLogger(__name__)

'''
The Canvas that handles Semantic Nets visual graphics representing objects in
one of more models (but having a single default model).

Created on Aug 21, 2026

@author: robkremer
'''
import tkinter as tk


class SNGView(ViewportMixin, ReasoningMixin, LayoutsMixin, FilesMixin, VisibilityMixin, ContainmentMixin, EditingMixin, ViewBase, AbstractGraph["VObject", "VRelation"], Observer, Dirtyable):
  '''
  The persistent container of VObjects.
  '''

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
    if _reading: # (its objects' first drawings are put off till it's all read: see _drawAllAfterRead() -- even if
      self.__dict__["_firstDrawsDeferred"] = True # the event loop's run meanwhile, eg: to show progress)
          
    self.model:Model = model

    # global way to get the tk application-root window
    self.root = tk._default_root # type: ignore[attr-defined] # @UndefinedVariable 
    
    self.window = AppWindow(self.root, self.url, geometry) # (self.url: where it is -- eg: a copied file's, not the URL stored in it)
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
    # the reasoning toolbar: shown unless the view was saved with it hidden (see showReasoningToolbar())
    self.canvas.after_idle(lambda: self.showReasoningToolbar(self.__dict__.pop("_pendingReasoningToolbar", "1") != "0", changed=False))
    self.canvas.after_idle(self.layoutSplit) # (the strip at the right that opens the layout panel: see showLayoutPanel())
    self._closed:bool = False
    "Set when the view's window is closed (see *detachFromModel()*): it then ignores the model's updates."
    
    self.selected:set[VObject] = set()
    'The set of currently selected VObjects.'
    self._suppressLocalLayout = False
    'Temporarily suppress automatic layout. Necessary during drag operations, etc.'
    self.localLayout:LayoutHeuristic = FindFree(self)
    '''The view's dynamic layout (see *layout*: one of *layout.layoutsFor(DYNAMIC)*): it
    places what's made or dropped, and adjusts things after each command (see
    *ViewDoList*). Set it with *setDynamicLayout()*; it's saved with the view.'''

    self._eventHandled:Optional[tk.Event] = None
    "Set by a contained VObject/item-level handler (via addEventHandled()) to mark that it already handled a mouse event, so this canvas's own (separately-dispatched) widget-level binding for the same event -- e.g. onRightMouse() -- can skip its generic handling. See isEventHandled()/addEventHandled()/removeEventHandled()."

    self._deletedGraphObjectsCache:dict[tuple[int,int],VObject] = dict[tuple[int,int],VObject]()
    """Used by update to store deleted VObjects matching deleted GraphObjects in case they are restored:
    by (the id of) the model and the model object's id in it -- every model numbers its objects from 256,
    and a view shows its model's super-models' objects too."""
    
    self._drawVersion:int = 0
    self.scrollRegion:tuple = (0, 0, 4000, 3000)

    self.makeBindings()
     
    # self._makingRelationFrom:SNGView.makingRelationData|None = None
    self._elasticLineChoiceData:SNGView.ElasticLineChoiceData|None = None
    self._selectionBoxInfo:list[Any]|None = None
    self._cursorBeforeTerminal:str = "arrow"
    "The cursor to restore when the pointer moves off a relation terminal (see *_updateTerminalCursor()*)."
    self._scrolling:bool = False
    self._panned:bool = False
    "Whether the pointer's moved since a drag-scroll's press (see *onButton_1()*)."
    self._panClicked:VObject|None = None
    "The object a Cmd-press landed on: a Cmd-click with no drag toggles its selection."
    self._cursorBeforePan:str = "arrow"
    "The cursor to restore when a drag-scroll ends."
    self._dragZoom:tuple[int, float, list[float], int, int]|None = None
    "An Option-drag zooming: where it was pressed (window y), the zoom then, and the point (view units) kept under the pointer, at window x, y (see *onButton_1()*)."

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
    self.categories.addCategory("constraints",     lambda mo: mo.isIndividual() and mo.isa(m.CONSTRAINT))
    self.categories.addCategory("inferred objects", lambda mo: getattr(mo, "inferred", False)) # (what "reason" put in the model: see GraphObject.inferred)
    self.hides:dict[str, str] = {}
    "The categories currently hidden or erased: category name -> \"hide\" or \"erase\". Saved with the view."
    

  @override
  def _wasRead(self, url:str) -> None:
    '''
    Once it's read: say which of its objects' model objects couldn't be found
    (if any: eg, deleted from an ontology it uses). They're shown as missing
    (see *VObject.validate()*: their status reports say why, and offer to
    erase them).

    :param url:
    :type url: str
    '''
    super()._wasRead(url)
    unresolved = self.__dict__.pop("_unresolved", [])
    if unresolved:
      shown = unresolved[:Model.UNRESOLVED_SHOWN]
      more = f"\n  ... and {len(unresolved) - len(shown)} more" if len(unresolved) > len(shown) else ""
      logger.warning(f'"{url}": {len(unresolved)} of its objects\' model objects couldn\'t be found (they\'re shown as '
                     f'missing):\n  ' + "\n  ".join(f"{ref}: {why}" for ref, why in shown) + more)

  def modelObjectsReplaced(self, old:Model, new:Model) -> int:
    '''
    Its model has put *new* in *old*'s place (see *Model.replaceSuperModel()*):
    its objects showing objects of *old* show the same objects of *new*.

    :param old:
    :type old: Model
    :param new:
    :type new: Model
    :returns: How many of its objects were changed.
    :rtype: int
    '''
    count = 0
    for vo in list(self._db.values()):
      mo = getattr(vo, "_modelObject", None)
      if mo is None or mo.db is not old:
        continue
      target = new._db.get(mo._id)
      if not isinstance(target, GraphObject):
        continue
      mo.detach(vo)
      vo._modelObject = target
      target.attach(vo)
      vo.cache.clear() # (its look, from its model object: got afresh -- see Cache)
      vo.cache["name"] = target.name
      count += 1
    if count:
      self.__dict__.pop("_byModelObject", None) # (see viewObjectsFor())
      self._observeModel(new)
      self.setDirty()
      self.repaint()
    return count

  @override
  def serializationHeader(self) -> dict[str, Any]:
    '''
    :returns: What's in the head of its file (see *PRDb.serializationHeader()*;
      its model's URL is there too: see *getInstantiationInfo()*), and the
      version of the structures it's saved in (see *sn.SCHEMA_VERSION*).
    :rtype: dict[str, Any]
    '''
    return {**super().serializationHeader(), "schema": sn.SCHEMA, "schemaVersion": sn.SCHEMA_VERSION}

  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    def finalize(slf:Serializable, _:SerializableType):
      assert isinstance(slf, SNGView), f'Expected SNGView for param 1, got {type(slf)}.'
      for rel in list(slf.values()):
        if isinstance(rel, VRelation):
          rel.connect()
      # (a full repaint first: it fits the objects to their text, as any later one would -- by
      # a pixel or so, if the file was saved with other font metrics -- so that isn't a change.
      # It's the objects' first drawing too: theirs, queued as they were made, are put off till then.)
      slf.__dict__["_firstDrawsDeferred"] = True
      slf.canvas.after_idle(lambda slf=slf: [slf.applyVisibility(), slf._restoreAnimationState(), slf._restoreLayoutState(), slf._restoreLayoutPanel(), slf._drawAllAfterRead(), slf.canvas.after_idle(slf._pinRelationTypes), slf.resetScrollRegion(), slf._restoreViewport(), slf.setDirty(False)]) # type: ignore[misc]
    ret:InstantiationInfo = super().getInstantiationInfo()
    # (its model's URL relative to the view's file if they're side by side -- see PRDb.relativeURL() -- so
    # a view and model copied together stay together; a relative URL is resolved against the view's file on reading)
    def readModel(m:Any) -> Model: # (one already in memory -- eg: the system model, sn, which has no file -- as is)
      db = PRDb.AllDBs.get(PRDb.resolveURL(str(m))) # (by what it stands for: eg, old views name sn "sn:/sn.xml" -- see PRDb.aliases)
      return db if isinstance(db, Model) else Model(cast(str, m))
    ret.conArgs.append(ParamInfo("model", str, getter=lambda slf: PRDb.relativeURL(cast(SNGView,slf).model.url),
                                 setter=readModel, inHead=True))
    ret.conKWArgs.append(ParamInfo("geometry", str, getter=lambda slf: cast(SNGView,slf).window.geometry()))
    ret.postconSetters.append(PropertyInfo("hides", str,
        lambda slf: ",".join(f"{k}={v}" for k, v in cast(SNGView, slf).hides.items()),
        lambda slf, v: cast(SNGView, slf)._setHides(str(v)),
        optional=True)) # optional: views saved before it existed still load
    ret.postconSetters.append(PropertyInfo("reasoningToolbar", str,
        lambda slf: "1" if cast(SNGView, slf)._reasoningToolbarShown().get() else "0",
        lambda slf, v: setattr(slf, "_pendingReasoningToolbar", str(v)), # (applied once the view is built: see __init__())
        optional=True)) # optional: views saved before it existed still load (and show it)
    ret.postconSetters.append(PropertyInfo("animation", str,
        lambda slf: cast(SNGView, slf)._animationState(),
        lambda slf, v: setattr(slf, "_pendingAnimation", str(v)), # (applied once the view is built: see _restoreAnimationState())
        optional=True))
    ret.postconSetters.append(PropertyInfo("layoutPanel", str,
        lambda slf: cast(SNGView, slf)._layoutPanelState(),
        lambda slf, v: setattr(slf, "_pendingLayoutPanel", str(v)), # (applied once the view is built: see _restoreLayoutPanel())
        optional=True)) # optional: views saved before it existed still load (with the animation toolbar's "toolbar=1" for it)
    ret.postconSetters.append(PropertyInfo("layout", str,
        lambda slf: cast(SNGView, slf).localLayout.state() if cast(SNGView, slf).localLayout is not None else "",
        lambda slf, v: setattr(slf, "_pendingLayout", str(v)), # (applied once the view is built: see _restoreLayoutState())
        optional=True)) # optional: views saved before it existed still load (with "avoid overlaps")
    ret.postconSetters.append(PropertyInfo("viewport", str,
        lambda slf: cast(SNGView, slf)._viewportState(),
        lambda slf, v: setattr(slf, "_pendingViewport", str(v)), # (applied once the view is built: see _restoreViewport())
        optional=True)) # optional: views saved before it existed still load (at zoom 1, scrolled to the top left)
    ret.postconSetters.append(PropertyInfo("editLocked", str,
        lambda slf: "1" if cast(SNGView, slf).editLocked() else "0",
        lambda slf, v: setattr(slf, "_editLocked", str(v) == "1"),
        optional=True)) # optional: views saved before it existed still load (unlocked)
    ret.postconSetters.append(PropertyInfo("layoutParameters", str,
        lambda slf: cast(SNGView, slf)._layoutParametersState(),
        lambda slf, v: cast(SNGView, slf)._restoreLayoutParameters(str(v)), # (by name: relations are looked up when used)
        optional=True)) # optional: views saved before it existed still load
    for p in ret.postconSetters: # (inferred objects aren't saved: see VObject.isInferred())
      if p.name == "_db":
        def assertedObjects(slf:Serializable) -> SerializableType:
          from util.persistence.serialize import strdict
          ret:strdict[Any] = strdict()
          for k, v in cast(SNGView, slf)._db.items():
            if not (isinstance(v, VObject) and v.isInferred()):
              ret[str(k)] = v
          return ret
        p.getter = assertedObjects
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
    finishTween(self) # (a layout's smooth move under way: saved where it's going)
    super().save(saveas=saveas, overwrite=overwrite, format=format)
    if saveas is None: # (saving a copy elsewhere doesn't save this: see PRDb.save())
      self.setDirty(False)
      noteSaved(self.url)


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
    index = self.__dict__.get("_byModelObject") if self.__dict__.get("_byModelObjectOf") is self._db else None
    replacing = _id is not None and self._db.get(_id) is not None
    ret = super()._register(value, _id)
    if index is not None:
      if replacing: # (not expected: start the index afresh)
        del self.__dict__["_byModelObject"]
      elif value.modelObject is not None:
        for key in self._indexKeys(value.modelObject):
          index.setdefault(key, []).append(value)
    if value.modelObject is not None:
      self._observeModel(value.modelObject.db)
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
    obj = self._db.get(_id)
    super()._unregister(_id)
    index = self.__dict__.get("_byModelObject") if self.__dict__.get("_byModelObjectOf") is self._db else None
    if index is not None and obj is not None and obj.modelObject is not None:
      for key in self._indexKeys(obj.modelObject):
        objs = index.get(key, [])
        for i, o in enumerate(objs):
          if o is obj:
            del objs[i]
            break
    self.setDirty()
    
  def detachFromModel(self) -> None:
    '''
    The view's window is closing: stop observing the model, and stop each of
    the view's objects observing its model object -- the model stays in memory
    (it may have other views), and its changes mustn't reach a window that's
    gone; and stop observing the other models whose objects it shows (see
    *_observeModel()*). Notifications already on their way are ignored (see
    *_closed*).
    '''
    self._closed = True
    self.model.detach(self)
    for model in self.__dict__.pop("_otherModels", {}).values():
      model.detach(self)
    for vo in list(self._db.values()):
      if vo is None:
        continue
      try:
        mo = vo.modelObject
      except Exception: # (eg: its model object has been deleted)
        continue
      if mo is not None:
        mo.detach(vo)

  def _observeModel(self, model:Any) -> None:
    '''
    Hear about *model*'s objects being deleted, and put back (eg: by an undo
    in another window), if it isn't the view's own model (always heard from):
    eg, it's a super-model of that, and one of its objects is shown here (see
    *_register()*). Kept up till the window closes (see *detachFromModel()*):
    an object may be put back after its box here has gone.

    :param model: The model of an object shown in the view.
    :type model: Any
    '''
    if not isinstance(model, Model) or model is self.model or self.__dict__.get("_closed"):
      return
    observed:dict[int, Model] = self.__dict__.setdefault("_otherModels", {})
    if id(model) not in observed:
      observed[id(model)] = model
      model.addObserver(self)

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
    own = subject is self.model
    if not own: # (a model whose objects it shows: see _observeModel() -- only what's deleted from it, and put back, matters here)
      topics = tuple(t for t in topics if t[0] in ("new", "del"))
      if not topics:
        return
    self.structureChanged() # (eg: an object retyped: maybe now a context window)
    logger.debug(f'SNGView.update({subject.name}, {len(topics)} topics)')
    for t in topics:
      topicName:str = t[0]
      topicData:tuple[Any, ...] = t[1]
      match t:
      #  if topicName == 'add GraphObject':
        # case ['add GraphObject', topicData]:
        case ['new', topicData]:
          modelID = topicData[0]
          
          # if this is one we've seen before, just restore it (unless that was done already: an
          # object's relations come back with it -- eg: when a paste or a cut is redone)
          vObject:VObject|None = self._deletedGraphObjectsCache.get((id(subject), modelID))
          if vObject is not None:
            if not vObject._isConnected():
              vObject._reconnect()
            continue
          if not own: # (an object added to another model isn't shown here till it's asked for)
            continue
          
          modelObj = topicData[1]
          if getattr(modelObj, "inferred", False): # (what "reason" concluded: shown when it's done -- see _showInferred())
            continue
          pasted = self.__dict__.get("_pasting", {}).pop(id(modelObj), None) is not None # (see showPasted())
          if (modelObj.isType() or isinstance(modelObj, Node)) and self.canvas and not pasted:
            # (now: asked later -- after_idle -- the editor came up blank, or unseen, when the
            # object was made from a pop-up menu, and took all the input: the app seemed to hang)
            self._askName(modelObj)
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
          if newObj is not None and not pasted: # (made just now, in a hidden category: shown anyway -- see _exemptIfFiltered())
            self._exemptIfFiltered(newObj)
  
        # elif topicName == 'del GraphObject':
        case ["reasoned", data]:
          self._showReasoning(showInferred=not (len(data) > 1 and data[1])) # (not if it was reasoned silently)
        case ["reasoning cleared", _]: # (nothing's inferred -- or, if this is heard late, what's inferred now is a later reason's, which says itself whether to show it)
          self._showReasoning(showInferred=False)

        case ["del", topicData]:
          modelID = topicData[0]
          found = self._viewObjectsForID(subject, modelID)
          obj:VObject|None = found[0] if found else None
          if obj is not None:
            dirty = self.isDirty()
            obj._disconnect()
            self._deletedGraphObjectsCache[(id(subject), modelID)] = obj
            if obj.isInferred() and not dirty: # (no longer inferred: not a change to the view -- see _showInferred())
              self.setDirty(False)
          
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
        under:VObject|None = None
        nextGridPoint = self.__dict__.get("_nextGridPoint")
        if atPoint is None and nextGridPoint is not None: # (within showAllModel())
          atPoint = nextGridPoint()
        if atPoint is None:
          x, y, under = self._newObjectLocation(mObject)
        else:
          x, y = int(atPoint[0]), int(atPoint[1])
        ret = VNode(self, mObject, x=x, y=y, x1=int(x + sizex), y1=int(y + sizey))
        if atPoint is None and self.canvas and getattr(self, "localLayout", None) is not None and not self.reading:
          # not on top of anything: the nearest free place (below its supertype, if it's there) -- once
          # it's drawn, and so are any others just made (eg: by the same command), so it avoids them too
          self.canvas.after_idle(lambda vo=ret, under=under: self._placeNew(vo, under)) #type: ignore[misc]
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
  


  # ---- Cut, copy and paste ---------------------------------------------------


  def findViewObjectForGraphObject(self, mObject:GraphObject|Callable[[VObject],bool]) -> VObject|None:
    '''
    :param mObject: A model object or a boolean function taking a VObject
    :type mObject: GraphObject|Callable[[VObject],bool]
    :return: A *VObject* currently in the display representing *mObject*, or *None* if there is not such object.
    :rtype: VObject | None
    '''
    if isinstance(mObject, GraphObject):
      found = self.viewObjectsFor(mObject)
      return found[0] if found else None
    else:
      for obj in self.values():
        if obj is not None and mObject(obj):  # already displayed?
          return obj
    return None

  def viewObjectsFor(self, mObject:GraphObject) -> list[VObject]:
    '''
    :param mObject: A model object.
    :type mObject: GraphObject
    :returns: The view objects in the display representing *mObject* (normally
      at most one), in the view's order. Looked up in an index, made when first
      needed and kept up to date as objects come and go (see *_register()*,
      *_unregister()*).
    :rtype: list[VObject]
    '''
    index = self._viewObjectIndex()
    return [o for o in index.get(id(mObject), ()) if o.modelObject is mObject]

  def _viewObjectsForID(self, model:Model, modelID:int) -> list[VObject]:
    '''
    :param model: A model.
    :type model: Model
    :param modelID: The id of one of its objects.
    :type modelID: int
    :returns: The view objects in the display representing that object -- all
      a model says of an object it's deleted (see *update()*) is its id: the
      id alone isn't enough, as every model numbers its objects from 256, and
      a view shows its model's super-models' objects too.
    :rtype: list[VObject]
    '''
    return [o for o in self._viewObjectIndex().get((id(model), modelID), ())
            if o.modelObject is not None and o.modelObject.db is model and o.modelObject.id == modelID]

  @staticmethod
  def _indexKeys(mo:GraphObject) -> tuple[int, tuple[int, int]]:
    '''
    :param mo: A model object.
    :type mo: GraphObject
    :returns: What a view object representing *mo* is indexed by (see
      *_viewObjectIndex()*): (the id of) *mo*; and (the id of) its model and
      its id in that.
    :rtype: tuple[int, tuple[int, int]]
    '''
    return id(mo), (id(mo.db), mo.id)

  def _viewObjectIndex(self) -> dict[int|tuple[int, int], list[VObject]]:
    '''
    :returns: The view's objects by (the id of) their model objects (see
      *viewObjectsFor()*), and by (the id of) their model objects' models and
      their ids in them (see *_viewObjectsForID()*).
    :rtype: dict[int|tuple[int, int], list[VObject]]
    '''
    index = self.__dict__.get("_byModelObject")
    if index is None or self.__dict__.get("_byModelObjectOf") is not self._db: # (reading replaces the dict: see PRDb)
      index = {}
      for obj in self.values():
        if obj is not None and obj.modelObject is not None:
          for key in self._indexKeys(obj.modelObject):
            index.setdefault(key, []).append(obj)
      self.__dict__["_byModelObject"] = index
      self.__dict__["_byModelObjectOf"] = self._db
    return index

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
    
    # cut, copy and paste
    self.canvas.bind(KEY_CUT[0], lambda e: self.onEditKey(e, "cut"))
    self.canvas.bind(KEY_COPY[0], lambda e: self.onEditKey(e, "copy"))
    self.canvas.bind(KEY_PASTE[0], lambda e: self.onEditKey(e, "paste"))
    self.canvas.bind(KEY_COPY_IMAGE[0], lambda e: self.onEditKey(e, "copy image"))
    self.canvas.bind(KEY_SELECT_ALL[0], lambda e: self.onEditKey(e, "select all"))
    for key in KEY_ERASE:
      self.canvas.bind(key, lambda e: self.onDeleteKey(e, fromModel=False))
    for key in KEY_REMOVE:
      self.canvas.bind(key, lambda e: self.onDeleteKey(e, fromModel=True))

    # repaint
    self.canvas.bind(KEY_REPAINT[0], self.repaint)
    for key, action in ((KEY_ZOOM_IN[0], self.zoomIn), ("<Command-KeyPress-plus>", self.zoomIn), (KEY_ZOOM_OUT[0], self.zoomOut),
                        (KEY_ZOOM_NORMAL[0], lambda: self.zoomAbout(1.0)), (KEY_ZOOM_FIT[0], self.zoomToFit)):
      self.canvas.bind(key, lambda _e, a=action: a()) # type: ignore[misc]

    # abandon an elastic-line choice (or, if there's none, clear the highlights)
    self.canvas.bind(KEY_CLEAR_HIGHLIGHTS[0], self.cancelElasticLine)

    # find objects by name
    self.canvas.bind(KEY_FIND[0], lambda _e: self.openSearchDialog())

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
    
    If the SHIFT or COMMAND key is pressed: start a drag-scroll (panning the
    view -- with COMMAND, over objects too: they leave the press to the
    canvas, see *VObject.onButton_1()*). If the OPTION key is: start a
    drag-zoom (over objects too), up to zoom in, down to zoom out, about
    where it was pressed (see *ZOOM_DRAG*). Otherwise, unselect 
    everything and prepare for a possible selection box animation (if we get a 
    move event).

    Called on the *<Button-1>* event (when the mouse button 1 is pressed).

    * If *self._makeRelationFrom* is not *None*, return.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * If the shift or command key is pressed start a scroll action and return.

    * If the option key is pressed start a zoom action and return.

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
    if not (s_SHIFT(event.state) or s_CMD(event.state) or s_ALT(event.state)) and self.grabTerminalNear(event):
      self.removeEventHandled(event)
      return None

    # option-Button1 down: zoom
    if s_ALT(event.state):
      self._panClicked = None
      self._cursorBeforePan = str(self.canvas.cget("cursor")) or "arrow"
      self.canvas.configure(cursor="sb_v_double_arrow")
      at = self.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))
      self._dragZoom = (event.y, self._scale, at, event.x, event.y)
      return

    # shift- or cmd-Button1 down: scroll (pan the view)
    if s_SHIFT(event.state) or s_CMD(event.state):
      self._scrolling = True
      self._panned = False
      if not s_CMD(event.state): self._panClicked = None # (a Shift-click toggles nothing)
      self._cursorBeforePan = str(self.canvas.cget("cursor")) or "arrow"
      self.canvas.configure(cursor="fleur")
      self.canvas.scan_mark(event.x, event.y)
      return

    # plain Button1 down: multi-select box
    for s in self.selected.copy():  # unselect everything
      s.selected(False)
    # 0:rect, 1:canvas-x, 2:canvas-y, 3:activated
    # (canvasx()/canvasy() already give canvas coordinates -- scrolled and zoomed,
    # like the drawn items -- so no viewToWindow() here: that zoomed it twice)
    x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
    self._selectionBoxInfo = [
        self.canvas.create_rectangle(x, y, x, y, fill="", width=3, outline="blue", dash=(1,6)),
        x,
        y,
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

      # continue zooming: by ZOOM_DRAG for each 100 pixels up, keeping the
      # pressed-on point under where it was pressed
      if self._dragZoom is not None:
        y0, scale0, at, wx, wy = self._dragZoom
        scale = min(self.MAX_ZOOM, max(self.MIN_ZOOM, scale0 * self.ZOOM_DRAG ** ((y0 - event.y) / 100)))
        if abs(scale - self._scale) > 1e-6:
          self.zoom(scale)
          self.resetScrollRegion()
          self._scrollToPut(at, wx, wy)
        return

      # continue scrolling
      if self._scrolling:
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        self._panned = True
        return
  
      # adjust selection box
      if self._selectionBoxInfo is not None:
        self._selectionBoxInfo[3] = True # activated
        bb = normalizeRect([self._selectionBoxInfo[1], self._selectionBoxInfo[2], self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)])
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
    if self._dragZoom is not None: # a drag-zoom's done
      self._dragZoom = None
      self.canvas.configure(cursor=self._cursorBeforePan)
      self.removeEventHandled(event)
      return None
    if self._scrolling: # a drag-scroll's done; a Cmd-click that never moved toggles what it was on
      self._scrolling = False
      self.canvas.configure(cursor=self._cursorBeforePan)
      clicked, self._panClicked = self._panClicked, None
      if not self._panned and clicked is not None:
        clicked.selected(not clicked.selected(), _multi=True)
      self.removeEventHandled(event)
      return None
    self._panClicked = None
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    
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
      # the topmost one: eg: an object in a context window, not the window
      # (find_overlapping() gives the items bottom to top)
      byTag = {n.tag: n for n in typeList if n is not None}
      item = next((byTag[tag] for _id in reversed(ids) for tag in self.canvas.gettags(_id) if tag in byTag), None)
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
          if n is not None and n._shape.id == _id:
            n.selected(True, _multi=True)
      self.canvas.delete(self._selectionBoxInfo[0])
      self._selectionBoxInfo = None

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


  def structureChanged(self) -> None:
    '''
    Note that what's in the view, or the model, has changed: an object was
    added to or taken out of the view, or the model changed. What's worked out
    from that and remembered (see *contextWindows()*) is worked out afresh.
    '''
    self.__dict__["_structureVersion"] = self.__dict__.get("_structureVersion", 0) + 1


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
    clickAt = self.windowToView(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

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

    bgMenu:tk.Menu = tk.Menu(self.canvas)

    # A menu command's callback runs on the main/GUI thread, where the
    # blocking builtin input() always raises RuntimeError — inputAsync()
    # returns immediately and delivers the typed line to onResult once the
    # user actually answers.
    # # "new instance" and "new subtype" for nodes menus
    modelEditMenu:tk.Menu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="model", menu=modelEditMenu)
    if self.isModelEditor():
      self.addNewObjectMenus(modelEditMenu, (clickAt[0], clickAt[1]))
      modelEditMenu.add_separator()
      from sn.model import copying
      modelEditMenu.add_command(label="paste here", command=lambda: self.doPaste(at=(clickAt[0], clickAt[1])),
                                state=tk.NORMAL if copying.clipboard is not None else tk.DISABLED)
      modelEditMenu.add_separator()
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      modelEditMenu.add_command(label="validate", command=lambda o=self: o.context.view.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #type: ignore[misc]
    modelEditMenu.add_command(label="refresh all caches", command=self.refreshAllCaches)
    
    viewMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="view", menu=viewMenu)
    showMenu = tk.Menu(viewMenu)
    showMenu.add_command(label="all", command=self.context.view.showAllModel)
    showMenu.add_command(label="relations...", command=self.showRelationsOfTypes)
    showMenu.add_command(label="nodes...", command=self.showNodesOfTypes)
    showMenu.add_cascade(label="node", menu=makeShowMenu())
    viewMenu.add_cascade(label="show", menu=showMenu)
    viewMenu.add_cascade(label="hide by category", menu=self._visibilityMenu("hide"))
    viewMenu.add_cascade(label="erase by category", menu=self._visibilityMenu("erase"))
    viewMenu.add_separator()
    viewMenu.add_cascade(label="Zoom", menu=self.makeZoomMenu(viewMenu))
    viewMenu.add_command(label="reset scroll region", command=lambda: self.resetScrollRegion(shrink=True))
    viewMenu.add_cascade(label="layout", menu=self._layoutMenu(viewMenu))
    if snPrefs.get("gui/debugMenus", storeDefault=False, storeType=bool):
      viewMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1])
    viewMenu.add_separator()
    viewMenu.add_command(label="float all relations", command=lambda: [r.floating(True) for r in self.context.view.values() if isinstance(r, VRelation)]) # (not relation types: they never float)

    reasonMenu = tk.Menu(self.canvas)
    bgMenu.add_cascade(label="reasoning", menu=reasonMenu)
    reasonMenu.add_command(label="clear highlights", command=self.clearHighlights, accelerator=KEY_CLEAR_HIGHLIGHTS[1])
    viewMenu.add_command(label="find...", command=self.openSearchDialog, accelerator=KEY_FIND[1])
    reasonMenu.add_command(label="reason", command=self.reason)
    reasonMenu.add_command(label="reason silently", command=self.reasonSilently)
    reasonMenu.add_command(label="clear reasoning", command=self.clearReasoning,
                       state=tk.NORMAL if self.reasoning is not None else tk.DISABLED)

    return bgMenu

  def makeZoomMenu(self, superMenu:tk.Menu) -> tk.Menu:
    '''
    The "Zoom" submenu: normal size, zoom in and out (about the middle of the
    window: see *zoomAbout()*), zoom to fit (see *zoomToFit()*), and some
    sizes; with their keys.

    :param superMenu:
    :type superMenu: tk.Menu
    :returns:
    :rtype: tk.Menu
    '''
    zoommenu = tk.Menu(superMenu)
    zoommenu.add_command(label="Normal Size", command=lambda: self.zoomAbout(1.0), accelerator=KEY_ZOOM_NORMAL[1])
    zoommenu.add_command(label="Zoom In", command=self.zoomIn, accelerator=KEY_ZOOM_IN[1])
    zoommenu.add_command(label="Zoom Out", command=self.zoomOut, accelerator=KEY_ZOOM_OUT[1])
    zoommenu.add_command(label="Zoom to Fit", command=self.zoomToFit, accelerator=KEY_ZOOM_FIT[1])
    zoommenu.add_separator()
    for percent in (200, 150, 75, 50, 25):
      zoommenu.add_command(label=f"{percent}%", command=partial(self.zoomAbout, percent / 100))
    return zoommenu


  ZOOM_DRAG = 2.0
  "How much an Option-drag zooms in for each 100 pixels up (and out, down)."


  


  # ---- Utility ---------------------------------------------------------------


    


  @override
  def isDirty(self) -> bool:
    '''
    True iff it, or one of its objects, has changed since it was saved --
    not counting inferred objects (see *GraphObject.inferred*): they aren't saved.

    :returns:
    :rtype: bool
    '''
    if Dirtyable.isDirty(self):
      return True
    for obj in self._db.values():
      if obj is not None and not (isinstance(obj, VObject) and obj.isInferred()) and obj.isDirty():
        Dirtyable.setDirty(self, True)
        return True
    return False


  # ---- layouts (see layout) ---------------------------------------------------------


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

  
        