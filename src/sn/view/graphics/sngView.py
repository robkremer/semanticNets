'''
The graphical view (*SNGView*): a window's canvas of view objects (see
*sn.view.graphics.vobjects*) showing the objects of one model (and of the
models it builds on), saved as a ``.snv`` file. This module is the view as a
database -- making it, saving and reading it, observing its model, finding
the view objects of a model object; what else it does is in its parts, the
mixins it inherits (see *viewBase*):

  - *viewViewport.ViewportMixin*: zooming, scrolling, painting;
  - *viewReasoning.ReasoningMixin*: showing reasoning;
  - *viewLayouts.LayoutsMixin*: layouts, and the layout panel;
  - *viewFiles.FilesMixin*: files, window menus, locking;
  - *viewVisibility.VisibilityMixin*: hidden and erased categories;
  - *viewContainment.ContainmentMixin*: context windows;
  - *viewEditing.EditingMixin*: new objects, cut, copy and paste, erasing;
  - *viewInput.InputMixin*: the mouse, keys and menus.

Its commands are in *sngContext.SNGContext*, its undo list in
*viewCommands.ViewDoList*.

Created on Aug 21, 2026

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
from sn import snPrefs
import sn
from sn.model.model import Model, Node, Relation, Collection, IsaIndividual, GraphObject

from typing import cast, override, Any, Iterable, Callable, Optional
from util.utils import fixURL
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
from sn.view.graphics.viewBase import ViewBase
from sn.view.graphics.viewViewport import ViewportMixin
from sn.view.graphics.viewReasoning import ReasoningMixin
from sn.view.graphics.viewLayouts import LayoutsMixin
from sn.view.graphics.viewFiles import FilesMixin
from sn.view.graphics.viewVisibility import VisibilityMixin
from sn.view.graphics.viewContainment import ContainmentMixin
from sn.view.graphics.viewEditing import EditingMixin
from sn.view.graphics.viewInput import InputMixin
import threading
from util.abstractGraph import AbstractGraph
from util.dirtyable import Dirtyable

logger:sn.SNLogger = sn.getLogger(__name__)

import tkinter as tk


class SNGView(ViewportMixin, ReasoningMixin, LayoutsMixin, FilesMixin, VisibilityMixin, ContainmentMixin, EditingMixin, InputMixin, ViewBase, AbstractGraph["VObject", "VRelation"], Observer, Dirtyable):
  '''
  The persistent container of VObjects.
  '''


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

  BATCHED_UPDATE_BOXES = 50
  "A notification that takes out, or puts back, at least this many of a view's boxes has their items hidden or shown in one pass over the canvas (see *update()*, *batchedItemStates()*). Measured: the pass takes as long as finding about 50 boxes' items one by one on a canvas of 50,000 items, about 125 on one of 17,000, and more on smaller ones -- where both are quick."

  def _changesManyBoxes(self, subject:Model, topics:tuple[tuple[str, tuple[Any, ...]], ...]) -> bool:
    '''
    :param subject: The model notifying (see *update()*).
    :type subject: Model
    :param topics: What it says.
    :type topics: tuple[tuple[str, tuple[Any, ...]], ...]
    :returns: Whether at least *BATCHED_UPDATE_BOXES* of *topics* take one of
      this view's boxes out ("del"), or put one back ("new"). Not just how
      many "del"s and "new"s there are: they may be of objects it doesn't
      show (eg: reasoning cleared, or a super-model's objects removed in
      another window), and then the pass over the canvas would be wasted.
    :rtype: bool
    '''
    n = 0
    for t in topics:
      if t[0] == "del":
        n += bool(self._viewObjectsForID(subject, t[1][0]))
      elif t[0] == "new":
        vo = self._deletedGraphObjectsCache.get((id(subject), t[1][0]))
        n += vo is not None and not vo._isConnected()
      if n >= self.BATCHED_UPDATE_BOXES:
        return True
    return False

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
    if self.__dict__.get("_pendingItemStates") is None and self._changesManyBoxes(subject, topics):
      with self.batchedItemStates(): # (and the same again within it, to do the topics)
        self.update(subject, *topics)
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


    
    


  def structureChanged(self) -> None:
    '''
    Note that what's in the view, or the model, has changed: an object was
    added to or taken out of the view, or the model changed. What's worked out
    from that and remembered (see *contextWindows()*) is worked out afresh.
    '''
    self.__dict__["_structureVersion"] = self.__dict__.get("_structureVersion", 0) + 1


  
  


  


    


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

  
        