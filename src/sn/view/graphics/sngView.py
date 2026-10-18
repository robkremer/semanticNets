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
from sn.model import names
from sn.model.constraints import WHERE, CONSTRAINTS, CONSTRAINTS_NOTE, splitWhere, mergeConstraints, ConstraintError
from util.attribute import Attribute, VAR
from sn.model.model import Model, Node, Relation, Collection, IsaIndividual, SN_URL,\
  GraphObject

from contextlib import contextmanager
from functools import partial
from typing import cast, override, Any, Iterable, Iterator, Callable, Optional
from util.utils import bindRightMouse, fixURL, urlExists, expandRect,\
  flattenPairs, s_SHIFT, s_CMD, s_ALT, normalizeRect
from sn.view.graphics.utils import eventEqual, addToMenuBar, addCheckToMenuBar, removeFromMenuBar
from util.persistence.pRef import PRDb
from util.observer import Subject, Observer
from util.attributeEditor import applyEditAttrsBox
from sn.view.textUserInterface import SNTerminalWidget
from util.command import Command
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from sn.view.graphics.layout import FindFree, Direction, freeSpotIn, clearOf, LayoutHeuristic, finishTween, relationTypes, relationNamed, nodeTypes, nodeNamed
import sn.view.graphics.treeLayout # (registers the tree layout: see layout.LAYOUTS)
import sn.view.graphics.balloonLayout # (registers the balloon, radial and hub layouts)
from sn.view.graphics.decorators import NOMINAL_ASPECT
from util.commandParser import CompositeCommandMgr
from util.utils import Categories
from math import sqrt
from util.persistence.serialize import InstantiationInfo, PropertyInfo,\
  ParamInfo, Serializable, SerializableType
from util.persistence.serialize import DEFAULT_STRATEGY
from sn.view.graphics.guiApp import Application, AppWindow
from sn.view.graphics.directoryWindow import noteSaved
from sn.view.graphics.viewCommands import ViewDoList, _ContainCreated, keptWith # (ViewDoList, keptWith: imported from here elsewhere too)
from sn.view.graphics.sngContext import SNGContext
from sn.view.graphics.viewBase import ViewBase
from sn.view.graphics.viewLayouts import LayoutsMixin
from sn.view.graphics.viewReasoning import ReasoningMixin
from sn.view.graphics.viewViewport import ViewportMixin
import os
import threading
from pathlib import Path
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

KEY_UNDO =                  ('<Command-KeyPress-z>'       , 'cmd+z')
KEY_REDO =                  ('<Shift-Command-KeyPress-Z>' , 'shift+cmd+Z')
KEY_REPAINT =               ('<Command-KeyPress-r>'       , 'cmd+r')
KEY_CUT =                   ('<Command-KeyPress-x>'       , 'Command-X')
KEY_COPY =                  ('<Command-KeyPress-c>'       , 'Command-C')
KEY_PASTE =                 ('<Command-KeyPress-v>'       , 'Command-V')
KEY_COPY_IMAGE =            ('<Shift-Command-KeyPress-C>' , 'Shift-Command-C')
KEY_SELECT_ALL =            ('<Command-KeyPress-a>'       , 'Command-A')
KEY_ERASE =                 ('<KeyPress-BackSpace>', '<KeyPress-Delete>')
"Erase what's selected from the view: the Mac's delete key (BackSpace), or forward delete."
KEY_REMOVE =                ('<Shift-KeyPress-BackSpace>', '<Shift-KeyPress-Delete>')
"Remove what's selected from the model (after asking)."
KEY_CLEAR_HIGHLIGHTS =      ('<Escape>'                   , 'esc')
KEY_VALIDATE =              ('<Command-KeyPress-v>'       , 'cmd+v')
KEY_TOGGLE_FIELDS_LAYOUT =  ('<Command-KeyPress-f>'       , 'cmd+f') # (not bound: see KEY_FIND)
KEY_FIND =                  ('<Command-KeyPress-f>'       , 'Command-F')
KEY_ZOOM_IN =               ('<Command-KeyPress-equal>'   , 'Command-+') # (also <Command-KeyPress-plus>: shifted, on most keyboards)
KEY_ZOOM_OUT =              ('<Command-KeyPress-minus>'   , 'Command--')
KEY_ZOOM_NORMAL =           ('<Command-KeyPress-0>'       , 'Command-0')
KEY_ZOOM_FIT =              ('<Command-KeyPress-9>'       , 'Command-9')

RELATION_CATEGORY = "relations: "
"How a relation type's category (for hiding or erasing its relations) is named: see *SNGView.relationCategory()*."
NODE_CATEGORY = "nodes: "
"How a node type's category (for hiding or erasing its individuals) is named: see *SNGView.nodeCategory()*."


class SNGView(ViewportMixin, ReasoningMixin, LayoutsMixin, ViewBase, AbstractGraph["VObject", "VRelation"], Observer, Dirtyable):
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

  def doSaveModel(self) -> None:
    '''
    Save this view's model: the target of the "File | Save model" menu item
    (added/removed like "Save view": see *onWindowFocusIn()*). Not a model
    that's write-locked (eg: the system model).

    :rtype: None
    '''
    model = self.model
    if model is None:
      return
    if model.writeLocked():
      logger.warning(f'"{model.url}" is write-locked: not saved.')
      return
    model.save()
    logger.info(f'Saved "{model.url}".')
    noteSaved(model.url)

  def _saveCopy(self, what:str, db:Any, extension:str, filetypes:list[tuple[str, str]]) -> None:
    '''
    Ask for a file, and save a copy of *db* (this view, or its model) there.
    This window stays on the original -- not as a Mac "Save As" does -- so say
    so, in the log, and flash the terminal pane to draw attention to it.

    :param what: "view" or "model", for the messages.
    :type what: str
    :param db: The view or model.
    :type db: SNGView | Model
    :param extension: Its files' extension, eg: ".snv".
    :type extension: str
    :param filetypes: For the file dialog.
    :type filetypes: list[tuple[str, str]]
    '''
    from tkinter import filedialog, messagebox
    current = fixURL(db.url)[0]
    path = current[len("file://"):] if current.startswith("file://") else ""
    filename = filedialog.asksaveasfilename(parent=self.window, title=f"Save a copy of the {what} as",
                                            defaultextension=extension, filetypes=filetypes,
                                            initialdir=os.path.dirname(path) or None,
                                            initialfile=f"{os.path.splitext(os.path.basename(path))[0]} copy{extension}" if path else "")
    if not filename:
      return
    copyURL = fixURL(filename, extension, replaceExt=None, mode="w")[0]
    if copyURL == current: # (its own file: just save it)
      db.save(overwrite=True)
      logger.info(f'Saved "{current}".')
      noteSaved(current)
      return
    try:
      db.save(saveas=filename, overwrite=True) # (the dialog has asked about replacing an existing file)
    except Exception as ex:
      messagebox.showerror("Save a copy", f"The {what} couldn't be saved as\n{filename}:\n\n{ex}", parent=self.window)
      return
    logger.warning(f'Saved a copy of the {what} as "{filename}". This window is still on the original, '
                   f'"{current}", and further changes go there.')
    noteSaved(copyURL)
    self.terminal.flash()

  def doSaveViewAs(self) -> None:
    '''
    Save a copy of this view in another file: the target of "File | Save view
    as..." (see *_saveCopy()*). This window stays on this view.

    :rtype: None
    '''
    self._saveCopy("view", self, ".snv", [("View files", "*.snv"), ("All files", "*.*")])

  def doSaveModelAs(self) -> None:
    '''
    Save a copy of this view's model in another file: the target of "File |
    Save model as..." (see *_saveCopy()*). This window stays on the model.

    :rtype: None
    '''
    if self.model is not None:
      self._saveCopy("model", self.model, ".snm", [("Model files", "*.snm"), ("All files", "*.*")])

  @staticmethod
  def _afterFileMenu() -> int:
    '''
    :returns: The menu bar position just after "File" (where "Edit" goes).
    :rtype: int
    '''
    try:
      bar = tk._default_root.nametowidget(tk._default_root["menu"]) # type: ignore[attr-defined,union-attr]
      return int(bar.index("File")) + 1
    except Exception:
      return 1

  def doReplaceSuperModel(self) -> None:
    '''
    "Edit | Replace super-model...": put another model in place of one of this
    view's model's super-models -- or of a model its objects refer to that
    isn't one (see *Model.unlistedModels()*) -- eg: an ontology's copy on the
    web in place of the local one (see *Model.replaceSuperModel()*); and show
    the same objects of the new one in its open views.

    :rtype: None
    '''
    from tkinter import messagebox
    from sn.view.graphics.replaceModelDialog import ReplaceModelDialog
    model = self.model
    if not self.isModelEditor():
      messagebox.showinfo("Replace super-model", self.lockedReason(), parent=self.window)
      return
    answer = ReplaceModelDialog(self.window, model).show()
    if answer is None:
      return
    old, where = answer
    try:
      new = Model.getDB(PRDb.absoluteURL(where, base=model.url))
      count = model.replaceSuperModel(old, new)
    except Exception as ex:
      messagebox.showerror("Replace super-model", f'Nothing was changed:\n\n{ex}', parent=self.window)
      return
    shown = 0
    for window in list(Application.current.windows.values()) if Application.current else [self.window]:
      view = getattr(window, "view", None)
      if view is not None and view.model is model:
        shown += view.modelObjectsReplaced(old, new)
    logger.warning(f'{model.name}: "{new.url}" is in place of "{old.url}": {count} reference{"" if count == 1 else "s"} '
                   f'changed, and {shown} object{"" if shown == 1 else "s"} in open views. Save the model (and the views) '
                   f'to keep it; its other views take it into account when they\'re opened.')
    self.terminal.flash()

  def doModelPreferences(self) -> None:
    '''
    "Edit | Model preferences...": edit this view's model's preferences (see
    *sn.model.modelPrefs*) -- just their values (their notes are their names'
    tooltips). Its super-models are shown as its *superDBs* are (see
    *Model.superModelPaths()*), "Add file..." choosing a model file, "Add URL..."
    taking its URL (eg: on the web: see *askModelURL()*), and set from
    the edited list (see *Model.setSuperModels()*): if that can't be done,
    nothing is changed, and the reasons are shown.

    :rtype: None
    '''
    from tkinter import filedialog, messagebox
    from util.attributeEditor import editAttrsBox
    from util.persistence.pRef import PRDb
    from sn.model.modelPrefs import SUPER_MODELS
    model = self.model
    if model is None or not hasattr(model, "prefs"):
      return
    if not self.isModelEditor():
      messagebox.showinfo("Model preferences", self.lockedReason(), parent=self.window)
      return
    modelFile = model.url[len("file://"):] if model.url.startswith("file://") else ""
    def chooseModel(parent:tk.Misc) -> str|None:
      path = filedialog.askopenfilename(parent=parent, title="Choose a model this one builds on",
                                        filetypes=[("Model files", "*.snm"), ("All files", "*.*")],
                                        initialdir=os.path.dirname(modelFile) or None)
      return PRDb.relativeURL(Path(path).as_uri(), base=model.url) if path else None
    def chooseModelURL(parent:tk.Misc) -> str|None:
      from sn.view.graphics.directoryWindow import askModelURL
      url = askModelURL(parent, "A model this one builds on", kinds=("model",),
                        prompt="The URL of a model this one builds on (eg: an ontology on the web):")
      return PRDb.relativeURL(url, base=model.url) if url else None
    updates = editAttrsBox(self.window, model.prefs, title=f"Preferences of {model.name}",
                           displayValues={SUPER_MODELS: model.superModelPaths()},
                           hideColumns=("type", "qualifiers", "note"),
                           listItemMakers={SUPER_MODELS: {"Add file...": chooseModel, "Add URL...": chooseModelURL}})
    if not updates:
      return
    for key, attr in updates.items():
      if key == SUPER_MODELS:
        if attr is None:
          continue
        try:
          model.setSuperModels(list(attr.value or [])) # type: ignore[arg-type]
          logger.info(f'{model.name}: super-models now {["sn"] + model.superModelPaths()}.')
        except ValueError as ex:
          messagebox.showerror("Model preferences", f"The super-models weren't changed:\n\n{ex}", parent=self.window)
      else:
        try:
          if attr is None:
            del model.prefs[key]
          else:
            model.prefs.setAttr(key, attr)
          model.setDirty()
        except Exception as ex:
          logger.exception(f'{model.name}: preference "{key}" couldn\'t be set.')
          messagebox.showerror("Model preferences", f'"{key}" couldn\'t be set:\n\n{ex}', parent=self.window)

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
    addToMenuBar("File|Save view as...", self.doSaveViewAs)
    addToMenuBar("File|Save model", self.doSaveModel)
    addToMenuBar("File|Save model as...", self.doSaveModelAs)
    addToMenuBar("File|Close model", self.doCloseModel, separatorBefore=True) # (after the saves)
    addToMenuBar("File|Open super model", menu=self._superModelsMenu())
    addToMenuBar("Edit|Cut", lambda: self._editAction("cut"), accelerator=KEY_CUT[1], cascadePositions={"Edit": self._afterFileMenu()})
    addToMenuBar("Edit|Copy", lambda: self._editAction("copy"), accelerator=KEY_COPY[1])
    addToMenuBar("Edit|Paste", lambda: self._editAction("paste"), accelerator=KEY_PASTE[1])
    addToMenuBar("Edit|Copy as picture", lambda: self._editAction("copy image"), accelerator=KEY_COPY_IMAGE[1])
    addToMenuBar("Edit|Select All", lambda: self._editAction("select all"), accelerator=KEY_SELECT_ALL[1])
    addToMenuBar("Edit|Find...", self.openSearchDialog, accelerator=KEY_FIND[1], separatorBefore=True)
    addToMenuBar("Edit|Model preferences...", self.doModelPreferences, separatorBefore=True)
    addToMenuBar("Edit|Replace super-model...", self.doReplaceSuperModel)
    self._editLockedVar().set(not self.isModelEditor()) # (the model may have been write-locked since)
    addCheckToMenuBar("Edit|Lock view", self._editLockedVar(), self._onLockViewItem, separatorBefore=True)
    addCheckToMenuBar("View|Layout panel", self._layoutPanelShown(), self._onLayoutPanelItem,
                      cascadePositions={"View": self._afterFileMenu() + 1}) # (after "Edit", made just above)
    addCheckToMenuBar("View|Reasoning toolbar", self._reasoningToolbarShown(),
                      lambda: self.showReasoningToolbar(self._reasoningToolbarShown().get()))
    addToMenuBar("View|Zoom In", self.zoomIn, accelerator=KEY_ZOOM_IN[1], separatorBefore=True)
    addToMenuBar("View|Zoom Out", self.zoomOut, accelerator=KEY_ZOOM_OUT[1])
    addToMenuBar("View|Normal Size", lambda: self.zoomAbout(1.0), accelerator=KEY_ZOOM_NORMAL[1])
    addToMenuBar("View|Zoom to Fit", self.zoomToFit, accelerator=KEY_ZOOM_FIT[1])
    bar = self.__dict__.get("_reasoningToolbar")
    if bar is not None:
      bar.refreshLock()

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
    removeFromMenuBar("File|Save view as...")
    removeFromMenuBar("File|Save model")
    removeFromMenuBar("File|Save model as...")
    removeFromMenuBar("Edit|Cut")
    removeFromMenuBar("Edit|Copy")
    removeFromMenuBar("Edit|Paste")
    removeFromMenuBar("Edit|Copy as picture")
    removeFromMenuBar("Edit|Select All")
    removeFromMenuBar("Edit|Find...")
    removeFromMenuBar("Edit|Model preferences...")
    removeFromMenuBar("Edit|Replace super-model...")
    removeFromMenuBar("Edit|Lock view")
    removeFromMenuBar("File|Close model")
    removeFromMenuBar("File|Open super model")
    removeFromMenuBar("View|Layout panel")
    removeFromMenuBar("View|Reasoning toolbar")
    for item in ("Zoom In", "Zoom Out", "Normal Size", "Zoom to Fit"):
      removeFromMenuBar("View|" + item)

  SN_VIEW = "sn.snv"
  '''
  The file name of the system model's (sn's) view, in the sn.model package's
  folder: sn has no file of its own, so it's taken to be there -- with the base
  rules (see *superModelView()*).
  '''

  def _superModelsMenu(self) -> tk.Menu:
    '''
    :returns: The "File | Open super model" cascade: an item for each of this
      view's model's super-models (see *superModelView()*), nearest first.
    :rtype: tk.Menu
    '''
    from sn.view.graphics.utils import _getMenuBar, getSubMenu
    from sn.model.reasoner import baseRulesSource
    old = self.__dict__.get("_superMenu")
    parent = getSubMenu(_getMenuBar(), "File") # type: ignore[arg-type]
    menu = self._superMenu = tk.Menu(parent, tearoff=0)
    supers = self.model.allSuperDBs()
    for db in supers:
      if not isinstance(db, Model):
        continue
      if db is self.model.TOP.model:
        label = "sn (the system model)"
      elif baseRulesSource(db) is not None:
        label = f"{os.path.splitext(db.name)[0]} (base rules)"
      else:
        label = PRDb.relativeURL(db.url, base=self.model.url)
      menu.add_command(label=label, command=lambda db=db: self.openSuperModel(db)) # type: ignore[misc]
    if not supers:
      menu.add_command(label="(none)", state=tk.DISABLED)
    if old is not None:
      self.canvas.after_idle(old.destroy) # (once it's no longer in the menu bar)
    return menu

  def superModelView(self, model:Model) -> tuple[str, str]:
    '''
    Where a super-model's view goes: next to its file, with the same name and
    ".snv" -- for the base rules, next to the file they come from (see
    *sn.model.reasoner.baseRulesSource()*), not the copy they're read from; for
    the system model (sn), which has no file, in the sn.model package's folder
    (see *SN_VIEW*).

    :param model: A super-model.
    :type model: Model
    :returns: (the URL of the model's file -- or "" for sn, which has none --
      and the URL of its view).
    :rtype: tuple[str, str]
    '''
    import importlib.resources
    from pathlib import Path
    from sn.model.reasoner import baseRulesSource
    if model is self.model.TOP.model:
      return "", Path(str(importlib.resources.files("sn.model").joinpath(self.SN_VIEW))).as_uri()
    src = baseRulesSource(model) or model.url
    return src, fixURL(src, ".snv", replaceExt=True, mode="w")[0]

  def openSuperModel(self, model:Model) -> None:
    '''
    Open a window on one of this view's model's super-models (see
    *superModelView()*): its view, if it has one, or else a new one -- for the
    base rules, of the file they come from (read-only).

    :param model: The super-model.
    :type model: Model
    '''
    app = self.window._root() # type: ignore[attr-defined]
    src, viewURL = self.superModelView(model)
    if src and src != model.url and not urlExists(viewURL): # (the base rules: a view of the file they come from)
      model = Model(src)
    app.openViewOn(model, viewURL) #type: ignore[attr-defined]


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
  
  def addNewObjectMenus(self, menu:tk.Menu, at:tuple[float, float], into:tuple[VObject, str]|None=None) -> None:
    '''
    Add the "new instance of Node", "new subtype of Node", "new instance of
    Relation" and "new subtype of Relation" cascades to *menu*: each with a
    submenu per model (this view's, its super-models, then sn) of its types.
    What's made is put at *at* (see *_newObjectLocation()*) -- and, with
    *into*, contained in that context window's pane (one undo for both): eg:
    the menu on a rule's window, to edit it in place.

    :param menu:
    :type menu: tk.Menu
    :param at: Where the menu was asked for (view coords).
    :type at: tuple[float, float]
    :param into: (a context window, the name of one of its panes: see *VObject.panes()*), or None.
    :type into: tuple[VObject, str] | None
    '''
    self._newAt = None
    def make(t:GraphObject, individual:bool, ptype:type) -> None:
      if ptype is Node: # (put where the menu was asked for: see _newObjectLocation())
        self._newAt = (int(at[0]), int(at[1]), t)
      new = self.context.new_node if ptype is Node else self.context.new_relation
      if into is None:
        new(t, name="", individual=individual, type=not individual) # type: ignore[arg-type]
        return
      win, pane = into
      with CompositeCommandMgr(self.context) as mgr:
        new(t, name="", individual=individual, type=not individual) # type: ignore[arg-type]
        if mgr.commands and win.modelObject is not None:
          mgr._addCommand(_ContainCreated(self.model, self._paneType(pane), win.modelObject, mgr.commands[-1]))
    def typesMenu(individual:bool, ptype:type) -> tk.Menu:
      ret = tk.Menu(self.canvas)
      # this model's types, then its super-models' (nearest first), then sn's
      implicit = self.model.implicitSuperDBs()
      supers = [db for db in self.model.allSuperDBs() if isinstance(db, Model) and not any(db is i for i in implicit)]
      for v in [self.model, *supers, Model.AllDBs[SN_URL]]:
        assert isinstance(v, Model)
        m = tk.Menu(self.canvas)
        for t in sorted((o for o in v.values() if isinstance(o, ptype) and o.isType()), key=lambda o: o.name):
          m.add_command(label=t.name, command=lambda t=t: make(t, individual, ptype)) #type: ignore[misc]
        ret.add_cascade(label=v.name, menu=m)
      return ret
    menu.add_cascade(label="new instance of Node", menu=typesMenu(True, Node))
    menu.add_cascade(label="new subtype of Node", menu=typesMenu(False, Node))
    menu.add_cascade(label="new instance of Relation", menu=typesMenu(True, Relation))
    menu.add_cascade(label="new subtype of Relation", menu=typesMenu(False, Relation))

  _newAt:tuple[int, int, GraphObject]|None = None
  '''
  Where the background menu that's making a node was asked for (view coords),
  and the type it's making one of, until it's made (see *makeMenu()*, *_newObjectLocation()*).
  '''

  def _placeNew(self, vo:VObject, under:VObject|None) -> None:
    '''
    Move a newly made view object to the nearest free place (see *FindFree*):
    below *under* (its supertype), if that's given -- or wherever the view's
    dynamic layout puts it -- and then let that layout adjust the rest (see
    *ViewDoList.adjustAgain()*).

    :param vo:
    :type vo: VObject
    :param under:
    :type under: VObject | None
    '''
    if not vo._isConnected() or vo.isHidden():
      return
    if vo._shape is None or vo._shape.id is None: # (not drawn yet: it'd be invisible to the search)
      self.freshPaint()
      vo.draw()
    if under is not None and not under._isConnected():
      under = None
    c = self.canvas
    seen = list(self.windowToView(c.canvasx(0), c.canvasy(0), c.canvasx(c.winfo_width()), c.canvasy(c.winfo_height())))
    cx, cy = vo.centerPt()
    within = seen if c.winfo_width() > 1 and seen[0] <= cx <= seen[2] and seen[1] <= cy <= seen[3] else None # (on screen: kept there)
    self.localLayout(vo, referenceNode=under, direction=Direction.SUB if under is not None else Direction.NEAREST, within=within)
    if isinstance(self.context.doList, ViewDoList): # (the layout keeps it arranged with the rest, now it's here)
      self.context.doList.adjustAgain()

  # ---- Cut, copy and paste ---------------------------------------------------

  def _selectedModelObjects(self, orAll:bool=False) -> list[GraphObject]:
    '''
    :param orAll: If nothing's selected, everything shown instead (as "select
      all" would select: see *selectAll()*).
    :type orAll: bool
    :returns: The model objects of what's selected, in the order they're drawn
      (top to bottom, left to right).
    :rtype: list[GraphObject]
    '''
    chosen = self.selected if self.selected or not orAll else self._shownObjects()
    vos = sorted((vo for vo in chosen if vo._isConnected() and vo.modelObject is not None),
                 key=lambda vo: (vo.boundingBox()[1], vo.boundingBox()[0]))
    return [vo.modelObject for vo in vos] #type: ignore[misc]

  def _shownObjects(self) -> list[VObject]:
    ":returns: What's shown: what *selectAll()* selects (not what's hidden)."
    return [vo for vo in self.values() if vo is not None and vo._isConnected() and not vo.isHidden()]

  def _geometryOf(self, objects:Iterable[GraphObject]) -> dict[int, dict[str, Any]]:
    '''
    :param objects: Model objects.
    :type objects: Iterable[GraphObject]
    :returns: How this view shows each of *objects* that it shows (by *id()*
      of the object): what *showPasted()* needs to show a copy of it the same
      way (see *copying.Clip.geometry*).
    :rtype: dict[int, dict[str, Any]]
    '''
    ret:dict[int, dict[str, Any]] = {}
    for mo in objects:
      vo = self.findViewObjectForGraphObject(mo)
      if vo is None or not vo._isConnected():
        continue
      g:dict[str, Any] = {"bb": [int(v) for v in vo.boundingBox()], "userSized": vo.userSized,
                          "filtered": self.isFiltered(mo) and not vo.categoryExempt} # (hidden by its category: so is the copy)
      if isinstance(vo, VRelation):
        g["floating"] = vo.floating()
      if getattr(vo, "collapsed", False):
        g["collapsed"], g["expandedHeight"] = True, getattr(vo, "expandedHeight", None)
      ret[id(mo)] = g
    return ret

  def doCopy(self, cut:bool=False) -> None:
    '''
    Copy what's selected -- or, if nothing is, everything shown -- to the
    clipboard (see *ModelContext.copy()*), with how this view shows it, so a
    paste shows the copies the same way (see *showPasted()*). With *cut*,
    remove it from the model too (undoably) -- only what's selected: not
    everything, just because nothing is.

    :param cut:
    :type cut: bool
    '''
    from sn.model import copying
    objs = self._selectedModelObjects(orAll=not cut)
    if not objs:
      logger.warning("Nothing is selected to cut." if cut else "There's nothing to copy.")
      return
    geometry = self._geometryOf(copying.closure(objs)) # (now: once it's cut, it's not shown)
    try:
      msg = self.context.cut(objs) if cut else self.context.copy(objs)
    except Exception as ex:
      logger.error(f"Can't {'cut' if cut else 'copy'}: {ex}")
      return
    clip = copying.clipboard
    if clip is not None:
      clip.geometry = {i: geometry[id(e.original)] for i, e in enumerate(clip.entries) if id(e.original) in geometry}
      clip.viewURL = self.url
    if msg:
      print(msg)

  def doPaste(self, at:tuple[float, float]|None=None) -> None:
    '''
    Paste what was last cut or copied (see *ModelContext.paste()*), and show
    it (see *showPasted()*).

    :param at: Where to put it (view coords: the top left of what's pasted), or
      None to put it where it was (or beside it, if that's taken).
    :type at: tuple[float, float] | None
    '''
    try:
      if at is None:
        self.context.paste()
      else:
        self.context.paste(x=int(at[0]), y=int(at[1]))
    except Exception as ex:
      logger.error(f"Can't paste: {ex}")

  def _editAction(self, action:str) -> None:
    '''
    "Edit | Cut", "Copy", "Paste" or "Select All" in the menu bar: for the
    terminal's text, if that has the keyboard focus, else for the canvas.
    ("Copy as picture" is always the canvas's: see *doCopyImage()*.)

    :param action: "cut", "copy", "paste", "select all" or "copy image".
    :type action: str
    '''
    w = self.canvas.focus_get()
    if action == "copy image":
      self.doCopyImage()
    elif isinstance(w, (tk.Text, tk.Entry)):
      w.event_generate("<<SelectAll>>" if action == "select all" else f"<<{action.capitalize()}>>")
    elif action == "select all":
      self.selectAll()
    elif action == "paste":
      self.doPaste()
    else:
      self.doCopy(cut=action == "cut")

  def selectAll(self) -> None:
    '''
    Select everything that's shown: not what's hidden (eg: a hidden category,
    or what's in a collapsed window).
    '''
    for vo in self._shownObjects():
      if not vo.selected():
        vo.selected(True, _multi=True)

  def onEditKey(self, event:tk.Event, action:str) -> str:
    '''
    Cmd-X, Cmd-C, Cmd-V or Cmd-A on the canvas (see *_editAction()*).

    :param event:
    :type event: tk.Event
    :param action: "cut", "copy", "paste", "select all" or "copy image".
    :type action: str
    :returns: "break": it's been dealt with.
    :rtype: str
    '''
    self._editAction(action)
    self.addEventHandled(event)
    return "break"

  def pictureObjects(self) -> list[VObject]:
    '''
    :returns: What a picture of the selection shows (see *doCopyImage()*):
      what's selected, what's in any selected context windows (at any depth),
      and the relations between any of those -- as far as they're shown; or,
      if nothing's selected, everything shown.
    :rtype: list[VObject]
    '''
    if not self.selected:
      return self._shownObjects()
    ret:list[VObject] = []
    def add(vo:VObject) -> None:
      if vo in ret or not vo._isConnected() or vo.isHidden():
        return
      ret.append(vo)
      for c in vo.carriedContents():
        add(c)
    for vo in self.selected:
      add(vo)
    more = True
    while more: # (relations between them -- and between those)
      more = False
      for vo in self.values():
        if isinstance(vo, VRelation) and vo not in ret and vo.src in ret and vo.dst in ret and vo._isConnected() and not vo.isHidden():
          ret.append(vo)
          more = True
    return ret

  def doCopyImage(self) -> None:
    '''
    Put a picture of what's selected -- or, if nothing is, of everything
    shown -- (see *pictureObjects()*), as it's drawn (but without the
    selection's handles), on the system clipboard, as a PNG: to paste into
    another program (see *imageExport*).
    '''
    from sn.view.graphics.imageExport import copyImage
    vos = self.pictureObjects()
    if not vos:
      logger.warning("There's nothing to copy as a picture.")
      return
    selected = list(self.selected)
    for vo in selected:
      vo.selected(False)
    try:
      self.canvas.update_idletasks()
      tags = {vo.tag for vo in vos}
      items = [i for i in self.canvas.find_all() if tags.intersection(self.canvas.gettags(i))]
      w, h = copyImage(self.canvas, items)
      print(f"Copied a picture of {len(vos)} object{'' if len(vos) == 1 else 's'} ({w}\u00d7{h}), to paste into another program.")
    except Exception as ex:
      logger.error(f"Can't copy a picture: {ex}")
    finally:
      for vo in selected:
        if vo._isConnected():
          vo.selected(True, _multi=True)

  def onDeleteKey(self, event:tk.Event, fromModel:bool) -> str:
    '''
    Delete: erase what's selected from the view (see *doErase()*); Shift-Delete:
    remove it from the model (see *doRemove()*), after asking.

    :param event:
    :type event: tk.Event
    :param fromModel:
    :type fromModel: bool
    :returns: "break"
    :rtype: str
    '''
    vos = [vo for vo in self.selected if vo._isConnected()]
    if not vos:
      return "break"
    if fromModel:
      self.doRemove(vos, confirm=True)
    else:
      self.doErase(vos)
    return "break"

  def doErase(self, vos:list[VObject]) -> None:
    '''
    Erase *vos* from this view (the model keeps their objects): one undo.

    :param vos:
    :type vos: list[VObject]
    '''
    vos = [vo for vo in vos if vo._isConnected()]
    if not vos:
      return
    try:
      self.context.erase(vos[0], others=vos[1:])
    except Exception as ex:
      logger.error(f"Can't erase: {ex}")

  def doEraseOthers(self, keep:list[VObject]) -> None:
    '''
    Erase everything but *keep* from this view (the model keeps their
    objects): one undo. Also kept are what *keep* needs to make sense (see
    *keptWith()*): the relations among the kept objects, the ends of the kept
    relations, and the context windows the kept objects are in. For working
    on a small part of a big view.

    :param keep:
    :type keep: list[VObject]
    '''
    from sn.view.graphics.vrelations import VRelation
    keep = [vo for vo in keep if vo._isConnected()]
    if not keep:
      return
    everything = [vo for vo in self.values() if vo is not None and vo._isConnected()]
    kept = {id(vo) for vo in keptWith(keep, everything,
                                      lambda vo: (vo.src, vo.dst) if isinstance(vo, VRelation) else None,
                                      lambda vo: vo.windowContents())}
    for vo in [vo for vo in self.selected if id(vo) not in kept]: # (out of the selection: else erasing one erases them all)
      vo.selected(False)
    # (the relations first: erasing a node takes its relations with it, so they'd be undone with it rather than on their own)
    self.doErase([vo for vo in everything if id(vo) not in kept and isinstance(vo, VRelation)] +
                 [vo for vo in everything if id(vo) not in kept and not isinstance(vo, VRelation)])

  def doRemove(self, vos:list[VObject], confirm:bool=False) -> None:
    '''
    Remove the model objects of *vos* from the model -- and so from every view
    of it: one undo. What can't be removed here is left, with a message: what
    the reasoner inferred (mark it asserted first), and what's in another
    model, or a write-locked one, or is a system object.

    :param vos:
    :type vos: list[VObject]
    :param confirm: Ask first (eg: for a key press, which is easily made by mistake).
    :type confirm: bool
    '''
    from tkinter import messagebox
    if not self.isModelEditor():
      logger.warning(f"Nothing's removed. {self.lockedReason()}")
      return
    mos:list[GraphObject] = []
    skipped:list[str] = []
    for vo in vos:
      mo = vo.modelObject
      if mo is None or any(mo is m for m in mos):
        continue
      if vo.isInferred() or mo.model is not self.model or mo.model.writeLocked() or vo._systemLocked():
        skipped.append(mo.name or type(mo).__name__)
      else:
        mos.append(mo)
    if skipped:
      logger.warning(f'Not removed (inferred, system, or in another model): {", ".join(skipped)}.')
    if not mos:
      return
    if confirm:
      what = f'"{mos[0].name}"' if len(mos) == 1 and mos[0].name else f"{len(mos)} objects"
      if not messagebox.askokcancel("Remove from model",
                                    f'Remove {what} from the model "{self.model.name}" -- and so from every view of it?\n\n(Undo puts {"it" if len(mos) == 1 else "them"} back.)',
                                    parent=self.canvas.winfo_toplevel()):
        return
    try:
      with CompositeCommandMgr(self.context):
        for mo in mos:
          self.context.remove(mo)
    except Exception as ex:
      logger.error(f"Can't remove: {ex}")

  PASTE_GAP = 40
  "The space (view units) left between pasted objects and what's beside them (see *_pasteOffset()*)."

  def _pasteOffset(self, boxes:list[list[int]], at:tuple[int, int]|None) -> tuple[int, int]:
    '''
    :param boxes: Where the pasted objects were (their bounding boxes).
    :type boxes: list[list[int]]
    :param at: Where the top left of them all is to go, or None.
    :type at: tuple[int, int] | None
    :returns: How far to move them from where they were: to *at*; else not at
      all, if nothing's there now (eg: they were cut, or copied from another
      view); else the least distance to the right or down to where nothing is.
    :rtype: tuple[int, int]
    '''
    if not boxes:
      return 0, 0
    x1, y1 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x2, y2 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    if at is not None:
      return int(at[0] - x1), int(at[1] - y1)
    others = [vo.boundingBox() for vo in self.values() if vo is not None and vo._isConnected() and not vo.isHidden()]
    def free(dx:int, dy:int) -> bool: # (with room around it -- except where it was: what's near that was near it)
      g = self.PASTE_GAP // 2 if (dx, dy) != (0, 0) else 0
      return not any(b[0] < x2 + dx + g and x1 + dx - g < b[2] and b[1] < y2 + dy + g and y1 + dy - g < b[3] for b in others)
    w, h = int(x2 - x1) + self.PASTE_GAP, int(y2 - y1) + self.PASTE_GAP
    for k in range(50):
      for d in ((0, 0),) if k == 0 else ((k * w, 0), (0, k * h)):
        if free(*d):
          return d
    return w, 0

  def showPasted(self, clip:Any, made:list[GraphObject], at:tuple[int, int]|None=None) -> None:
    '''
    Show the objects just pasted (by *SNGContext.paste()*) as the view they were
    copied from showed them (see *copying.Clip.geometry*): the same sizes and
    layout -- a pasted rule's window with its contents in place -- moved
    together (see *_pasteOffset()*). What wasn't shown there (eg: an erased isa
    link) is shown, or not, as any new object is (see *update()*), but without
    asking for its name. Then what was asked to be copied is selected, so it
    can be dragged away at once.

    :param clip: What was pasted (a *copying.Clip*).
    :type clip: copying.Clip
    :param made: The new objects, by entry of *clip* (see *copying.pasteInto()*).
    :type made: list[GraphObject]
    :param at: Where to put the top left of them all (view coords), or None.
    :type at: tuple[int, int] | None
    '''
    from sn.view.graphics.vnodes import VNode
    pending = self.__dict__.setdefault("_pasting", {}) # (for update(): see there)
    for mo in made:
      pending[id(mo)] = mo
    dx, dy = self._pasteOffset([g["bb"] for g in clip.geometry.values()], at)
    shown:dict[int, VObject] = {}
    for i in sorted(range(len(made)), key=lambda i: clip.entries[i].kind != "node"): # (nodes first: they're relations' ends)
      mo, g = made[i], clip.geometry.get(i)
      if g is None:
        continue
      x1, y1, x2, y2 = g["bb"][0] + dx, g["bb"][1] + dy, g["bb"][2] + dx, g["bb"][3] + dy
      vo = self.findViewObjectForGraphObject(mo)
      if vo is None and isinstance(mo, Relation):
        vo = VRelation(self, mo, x=x1, y=y1, x1=x2, y1=y2, floating=g.get("floating"))
      elif vo is None:
        vo = VNode(self, mo, x=x1, y=y1, x1=x2, y1=y2)
      else: # (made already: an end of a relation shown before it)
        vo.boundingBox([x1, y1, x2, y2])
        if isinstance(vo, VRelation) and "floating" in g:
          vo._floatingAnchor = g["floating"]
      vo.userSized = g.get("userSized", False)
      if g.get("collapsed"):
        vo.collapsed, vo.expandedHeight = True, g.get("expandedHeight")
      if not g.get("filtered"):
        self._exemptIfFiltered(vo)
      shown[i] = vo
    def select() -> None:
      for s in self.selected.copy():
        s.selected(False)
      boxes = []
      for i in clip.selected:
        vo = shown.get(i)
        if vo is not None and vo._isConnected() and not vo.isHidden():
          vo.selected(True, _multi=True)
          boxes.append(vo.boundingBox())
      if boxes:
        self.scrollToShow([min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)])
    if self.canvas:
      self.canvas.after_idle(select)

  def scrollToShow(self, box:list[float], margin:int=20) -> None:
    '''
    Scroll the canvas, if need be, so that *box* is in sight -- the least it
    takes (as much of it as fits, from its top left).

    :param box: A rectangle, in view coords.
    :type box: list[float]
    :param margin: Room to leave around it (canvas pixels).
    :type margin: int
    '''
    c = self.canvas
    self.resetScrollRegion()
    x1, y1, x2, y2 = self.viewToWindow(*box)
    left, top = c.canvasx(0), c.canvasy(0)
    right, bottom = left + c.winfo_width(), top + c.winfo_height()
    sr = self.scrollRegion
    def start(lo:float, hi:float, a:float, b:float, size:float) -> float|None: # (where the visible lo..hi should start, to show a..b)
      if lo <= a and b <= hi:
        return None
      return a - margin if a < lo or b - a + 2 * margin > size else b + margin - size
    if (x := start(left, right, x1, x2, right - left)) is not None:
      c.xview_moveto(max(0.0, (x - sr[0]) / max(1, sr[2] - sr[0])))
    if (y := start(top, bottom, y1, y2, bottom - top)) is not None:
      c.yview_moveto(max(0.0, (y - sr[1]) / max(1, sr[3] - sr[1])))

  def findAGoodLocation(self, mObject:GraphObject) -> tuple[int,int]:
    '''
    :param mObject:
    :type mObject: GraphObject
    :returns: Where to start looking for a place for a new view object for
      *mObject* (see *_newObjectLocation()*).
    :rtype: tuple[int, int]
    '''
    x, y, _ = self._newObjectLocation(mObject)
    return x, y

  def _newObjectLocation(self, mObject:GraphObject) -> tuple[int, int, "VObject|None"]:
    '''
    Where to start looking for a place for a new view object for *mObject*
    (the nearest free place to it is used: see *makeViewObjectForGraphObject()*):
    where the background menu making it was asked for, if it was; else just
    below its (first) supertype, if that's shown; else at the cursor.

    :param mObject:
    :type mObject: GraphObject
    :returns: (x, y, and the supertype's view object, if it's below that).
    :rtype: tuple[int, int, VObject | None]
    '''
    if self._newAt is not None and mObject.isa(self._newAt[2]): # (once: see makeMenu())
      x, y, _ = self._newAt
      self._newAt = None
      return x, y, None
    mParents = mObject.getParents()
    mParent = mParents[0] if len(mParents) > 0 else None
    vParent = self.findViewObjectForGraphObject(mParent) if mParent is not None else None
    if vParent is None or vParent.isHidden() or vParent.isContextWindow():
      x, y = self.cursorViewPoint()
      return x, y, None
    bb = vParent.boundingBox()
    return int(bb[0]), int(bb[3] + self.NEW_BELOW_GAP), vParent

  NEW_BELOW_GAP = 40
  "How far below its supertype (view units) a new object is put (see *_newObjectLocation()*)."

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
        rel = cast(Relation, r.modelObject)
        for end in ("src", "dst"):
          own = rel.localSrc if end == "src" else rel.localDst
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
    def nextPoint() -> tuple[int, int]:
      nonlocal x, y
      p = (x, y)
      if y < blockSize:
        y += grid[1]
      else:
        x += grid[0]
        y = 10
      return p
    # what's made along the way (eg: a relation's end from a super-model) goes on the grid too: not to the
    # nearest free place (see _placeNew()), a search that's very slow in a crowded big view
    self.__dict__["_nextGridPoint"] = nextPoint
    try:
      for mnode in self.model.values():
        if self.isFiltered(mnode):
          continue
        vObj = self.findViewObjectForGraphObject(mnode)
        if vObj is None:
          n = self.makeViewObjectForGraphObject(mnode, atPoint=nextPoint())
          self.localLayout(n)
    finally:
      del self.__dict__["_nextGridPoint"]

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

  def search(self, pattern:str, wholeWord:bool=False, matchCase:bool=False, regex:bool=False,
             wholeModel:bool=False, superModels:bool=False,
             confirm:Callable[[int], bool]|None=None) -> tuple[list[VObject], int]:
    '''
    Highlight the nodes and relations in the view whose names match *pattern*
    (see *sn.model.model.nameMatcher()*) -- not isa links, nor those not drawn
    just now (see *VObject.isHidden()*) -- replacing any earlier highlights,
    and scroll to show them. With *wholeModel*, those in the model (and, with
    *superModels*, its super-models) that aren't in the view are shown first
    (one undoable command: see *represent()*), even if they're in a hidden or
    erased category; and so are any of those in the view in such a category.

    :param pattern: What to look for in names.
    :type pattern: str
    :param wholeWord: See *nameMatcher()*.
    :type wholeWord: bool
    :param matchCase: See *nameMatcher()*.
    :type matchCase: bool
    :param regex: See *nameMatcher()*.
    :type regex: bool
    :param wholeModel: Look in the model too, and show what's found.
    :type wholeModel: bool
    :param superModels: With *wholeModel*: in its super-models too.
    :type superModels: bool
    :param confirm: With *wholeModel*: asked, with how many objects would be
      shown, whether to show them (eg: there are a lot); None: they are.
    :type confirm: Callable[[int], bool] | None
    :returns: The view objects highlighted, and how many were shown.
    :rtype: tuple[list[VObject], int]
    :raises re.error: If *regex* and *pattern* isn't a good regular expression.
    '''
    from sn.model.model import nameMatcher
    matches = nameMatcher(pattern, wholeWord=wholeWord, matchCase=matchCase, regex=regex)
    found:list[GraphObject] = []
    brought = 0
    if wholeModel:
      found = self.model.search(pattern, wholeWord=wholeWord, matchCase=matchCase, regex=regex, superModels=superModels)
      shown = self._shownModelObjects()
      missing = sorted((o for o in found if id(o) not in shown), key=lambda o: isinstance(o, Relation)) # (nodes first)
      if missing and (confirm is None or confirm(len(missing))):
        self.context.represent(missing)
        brought = len(missing)
    self.clearHighlights()
    ret:list[VObject] = []
    for vo in list(self.values()):
      mo = vo.modelObject if vo is not None else None
      if mo is None or isinstance(mo, IsaIndividual) or not vo._isConnected() or not matches(str(mo.name)):
        continue
      if wholeModel and vo.isHidden():
        self._exemptIfFiltered(vo)
      if not vo.isHidden():
        vo.highlight(True)
        ret.append(vo)
    if ret and self.canvas:
      def show() -> None: # (once anything just shown is placed: see makeViewObjectForGraphObject())
        boxes = [vo.boundingBox() for vo in ret if vo._isConnected()]
        if boxes:
          self.scrollToShow([min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)])
      self.canvas.after_idle(show)
    return ret, brought

  def openSearchDialog(self) -> None:
    '''
    "Edit | Find...": open this view's search dialog (see
    *sn.view.graphics.searchDialog.SearchDialog*), or bring it to the front.
    '''
    from sn.view.graphics.searchDialog import SearchDialog
    d = self.__dict__.get("_searchDialog")
    if d is not None and d.winfo_exists():
      d.bringToFront()
    else:
      self.__dict__["_searchDialog"] = SearchDialog(self)

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
    for end in (fromNode, toNode): # (the reasoner's: see GraphObject.inferred)
      if end is not None and end.isInferred():
        logger.error(f'"{end.name}" is inferred: mark it as asserted to relate it.')
        return
    try:
      with CompositeCommandMgr(self.context) as mgr: # (one undo, with any containment it lands in)
        self.context.new_relation([typ], individual=True, destination=None if toNode is None else toNode.modelObject,
                                  source=fromNode.modelObject, model=self.model)
        if toNode is not None and mgr.commands:
          self._containNewRelation(mgr, mgr.commands[-1], typ, fromNode, toNode)
    except Exception:
      logger.exception("SNView.makeRelation():")

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
    src, dst = getattr(mo, "localSrc", None), getattr(mo, "localDst", None)
    if src is not None and dst is not None: # (a relation: by its ends, eg: "isa (tom → person)")
      label = f"{label} ({src.name} → {dst.name})"
    for c in cats:
      pending.setdefault(c, []).append(label)
    vo._applyHidden()

  def _reportExempt(self) -> None:
    pending = self.__dict__.pop("_exemptPending", {})
    for c, labels in pending.items():
      shown = ", ".join(dict.fromkeys(labels)) # (once each, in order)
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

  def _visibilityMenu(self, mode:str) -> tk.Menu:
    '''
    A checkbox per category for *mode* ("hide" or "erase"): checking it sets
    that category to *mode* (so unchecks it in the other menu); unchecking it
    shows the category again. The relation and node types' categories (see
    *relationCategory()*, *nodeCategory()*) are listed only while they're
    hidden or erased; "relation types..." and "node types..." choose them (see
    *chooseRelationCategories()*, *chooseNodeCategories()*).

    :param mode:
    :type mode: str
    :returns:
    :rtype: tk.Menu
    '''
    menu = tk.Menu(self.canvas)
    self._visibilityVars = getattr(self, "_visibilityVars", {}) # (keep the variables alive)
    for name in self.categories.keys():
      if name.startswith((RELATION_CATEGORY, NODE_CATEGORY)) and name not in self.hides:
        continue
      var = tk.BooleanVar(value=self.hides.get(name) == mode)
      self._visibilityVars[(mode, name)] = var
      menu.add_checkbutton(label=name, variable=var, onvalue=True, offvalue=False,
                           command=lambda n=name, v=var: self.context.visibility(n, mode if v.get() else "show")) #type: ignore[misc]
    menu.add_separator()
    menu.add_command(label="relation types...", command=lambda: self.chooseRelationCategories(mode))
    menu.add_command(label="node types...", command=lambda: self.chooseNodeCategories(mode))
    return menu

  def relationCategory(self, typ:Relation|str) -> str:
    '''
    The category of the relations of a relation type, and of its subtypes
    (not the type itself, nor isa links: see the "isa individuals" category),
    for hiding or erasing (see *visibility()*): made the first time it's
    asked for.

    :param typ: The relation type, or its name.
    :type typ: Relation | str
    :returns: The category's name: *RELATION_CATEGORY* and the type's: eg: "relations: imports".
    :rtype: str
    '''
    name = str(typ if isinstance(typ, str) else typ.name)
    category = RELATION_CATEGORY + name
    if category not in self.categories.keys():
      found:dict[str, Relation|None] = {}
      def test(mo:GraphObject) -> bool:
        if "t" not in found: # (looked up when first needed: eg: a view read before its model's super-models)
          found["t"] = typ if isinstance(typ, Relation) else relationNamed(self.model, name)
        t = found["t"]
        return t is not None and isinstance(mo, Relation) and not isinstance(mo, IsaIndividual) \
               and mo.isIndividual() and mo.isa(t)
      self.categories.addCategory(category, test)
    return category

  def nodeCategory(self, typ:Node|str) -> str:
    '''
    The category of the individuals of a node type, and of its subtypes (not
    the types themselves: see the "types" category; nor relations), for
    hiding or erasing (see *visibility()*): made the first time it's asked
    for.

    :param typ: The node type, or its name.
    :type typ: Node | str
    :returns: The category's name: *NODE_CATEGORY* and the type's: eg: "nodes: person".
    :rtype: str
    '''
    name = str(typ if isinstance(typ, str) else typ.name)
    category = NODE_CATEGORY + name
    if category not in self.categories.keys():
      found:dict[str, Node|None] = {}
      def test(mo:GraphObject) -> bool:
        if "t" not in found: # (looked up when first needed: eg: a view read before its model's super-models)
          found["t"] = typ if isinstance(typ, Node) else nodeNamed(self.model, name)
        t = found["t"]
        return t is not None and isinstance(mo, Node) and not isinstance(mo, Relation) \
               and mo.isIndividual() and mo.isa(t)
      self.categories.addCategory(category, test)
    return category

  def _setHides(self, text:str) -> None:
    '''
    Put back the hidden and erased categories saved with the view (see
    *hides*), making those of relation and node types (see
    *relationCategory()*, *nodeCategory()*).

    :param text: What was saved: eg: "types=hide,relations: imports=erase".
    :type text: str
    '''
    self.hides = dict(kv.split("=", 1) for kv in text.split(",") if "=" in kv)
    for category in self.hides:
      if category.startswith(RELATION_CATEGORY):
        self.relationCategory(category[len(RELATION_CATEGORY):])
      elif category.startswith(NODE_CATEGORY):
        self.nodeCategory(category[len(NODE_CATEGORY):])

  def _shownModelObjects(self) -> set[int]:
    ":returns: The ids of the model objects shown in the view (not erased: hidden ones too)."
    return {id(vo.modelObject) for vo in self.values() if vo is not None and vo._isConnected() and vo.modelObject is not None}

  def showRelationsOfTypes(self) -> None:
    '''
    "show" > "relations...": choose relation types in a dialog, and show
    their relations (and their subtypes') between the nodes in the view --
    and, if asked, with the nodes at their other ends too. Shown even if
    they're in a hidden or erased category (they were asked for by type: see
    *_exemptIfFiltered()*). One undoable command (see *represent()*).
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    ENDS = "and the nodes at their other ends (if those aren't shown)"
    types = [t for t in relationTypes(self.model) if t is not self.model.ISA]
    d = TypesDialog(self.canvas, "Show relations", types, set(), options=[(ENDS, False)], # type: ignore[arg-type]
                    note="Show the relations of these types (and their subtypes) between what's shown. (Isa links: "
                         "the \"isa individuals\" category.)")
    chosen = d.show()
    if not chosen:
      return
    chosenTypes = [t for t in types if id(t) in chosen]
    shown = self._shownModelObjects()
    nodes:list[GraphObject] = []
    rels:list[GraphObject] = []
    for r in self.model.values():
      if not isinstance(r, Relation) or isinstance(r, IsaIndividual) or not r.isIndividual() or id(r) in shown \
         or not r._isConnected() or not any(r.isa(t) for t in chosenTypes):
        continue
      ends = [e for e in (r.src, r.dst) if e is not None]
      missing = [e for e in ends if id(e) not in shown]
      if missing and not d.options[ENDS]:
        continue
      for e in missing:
        if e not in nodes:
          nodes.append(e)
      rels.append(r)
    self._showObjects(nodes + rels, "relations of those types")

  def showNodesOfTypes(self) -> None:
    '''
    "show" > "nodes...": choose node types in a dialog, and show their
    individuals (and their subtypes') -- and, if asked (the default), their
    relations to what's shown, and to each other (not those in a hidden or
    erased category). The nodes are shown even if they're in a hidden or
    erased category (they were asked for by type: see *_exemptIfFiltered()*).
    One undoable command (see *represent()*).
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    RELATIONS = "and their relations to what's shown"
    types = nodeTypes(self.model)
    d = TypesDialog(self.canvas, "Show nodes", types, set(), options=[(RELATIONS, True)], # type: ignore[arg-type]
                    note="Show the individuals of these types (and their subtypes).")
    chosen = d.show()
    if not chosen:
      return
    chosenTypes = [t for t in types if id(t) in chosen]
    shown = self._shownModelObjects()
    nodes:list[GraphObject] = [n for n in self.model.values() if isinstance(n, Node) and not isinstance(n, Relation)
                               and n.isIndividual() and n._isConnected() and id(n) not in shown and any(n.isa(t) for t in chosenTypes)]
    rels:list[GraphObject] = []
    if d.options[RELATIONS] and nodes:
      ends = shown | {id(n) for n in nodes}
      new = {id(n) for n in nodes}
      for r in self.model.values():
        if isinstance(r, Relation) and not isinstance(r, IsaIndividual) and r.isIndividual() and r._isConnected() \
           and id(r) not in shown and r.src is not None and r.dst is not None \
           and id(r.src) in ends and id(r.dst) in ends and (id(r.src) in new or id(r.dst) in new) and not self.isFiltered(r):
          rels.append(r)
    self._showObjects(nodes + rels, "nodes of those types")

  def _showObjects(self, objects:list[GraphObject], what:str) -> None:
    '''
    Show *objects* in the view, as one undoable command (see *represent()*) --
    or, if there are none, say so.

    :param objects: Model objects: nodes before relations.
    :type objects: list[GraphObject]
    :param what: What they are, for the message if there are none: eg: "relations of those types".
    :type what: str
    '''
    if not objects:
      from tkinter import messagebox
      messagebox.showinfo("Show", f"There are no {what} to show: they're all shown already.", parent=self.window)
      return
    self.context.represent(objects)

  def chooseRelationCategories(self, mode:str) -> None:
    '''
    "relation types...": choose, in a dialog, the relation types whose
    relations (and their subtypes') to hide or erase (*mode*); those
    unchecked that were are shown again. Done as one undoable command.

    :param mode: "hide" or "erase".
    :type mode: str
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    types = [t for t in relationTypes(self.model) if t is not self.model.ISA]
    checked = {id(t) for t in types if self.hides.get(RELATION_CATEGORY + str(t.name)) == mode}
    verb = "Hide" if mode == "hide" else "Erase"
    chosen = TypesDialog(self.canvas, f"{verb} relations", types, checked, # type: ignore[arg-type]
                                 note=f"{verb} the relations of these types (and their subtypes). "
                                      f"(Isa links: the \"isa individuals\" category.)").show()
    if chosen is None:
      return
    changes = [(self.relationCategory(t), mode if id(t) in chosen else "show") for t in types
               if (id(t) in chosen) != (id(t) in checked)]
    if not changes:
      return
    with CompositeCommandMgr(self.context):
      for category, m in changes:
        self.context.visibility(category, m)

  def chooseNodeCategories(self, mode:str) -> None:
    '''
    "node types...": choose, in a dialog, the node types whose individuals
    (and their subtypes') to hide or erase (*mode*) -- and with them, their
    relations; those unchecked that were are shown again. Done as one
    undoable command.

    :param mode: "hide" or "erase".
    :type mode: str
    '''
    from sn.view.graphics.visibilityDialog import TypesDialog
    types = nodeTypes(self.model)
    checked = {id(t) for t in types if self.hides.get(NODE_CATEGORY + str(t.name)) == mode}
    verb = "Hide" if mode == "hide" else "Erase"
    chosen = TypesDialog(self.canvas, f"{verb} nodes", types, checked, # type: ignore[arg-type]
                                 note=f"{verb} the individuals of these types (and their subtypes), and their relations. "
                                      f"(The types themselves: the \"types\" category.)").show()
    if chosen is None:
      return
    changes = [(self.nodeCategory(t), mode if id(t) in chosen else "show") for t in types
               if (id(t) in chosen) != (id(t) in checked)]
    if not changes:
      return
    with CompositeCommandMgr(self.context):
      for category, m in changes:
        self.context.visibility(category, m)

  def _askName(self, mo:GraphObject) -> None:
    '''
    Ask for a new object's name (and anything else about it), in the
    attribute editor -- unless it's gone (eg: undone).

    :param mo:
    :type mo: GraphObject
    '''
    if getattr(self, "_closed", False) or not mo._isConnected():
      return
    applyEditAttrsBox(self.canvas, mo, title=mo.name, editKey="name")
    # a variable's name may be typed with constraints: "?p :where: alive" (see sn.model.constraints)
    if WHERE in mo.name:
      self._applyWhere(mo)

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
    if not names.isVariableName(name):
      logger.error(f'"{mo.name}": only variables have constraints ({names.grammar.describe()}).')
      return
    try:
      merged = mergeConstraints(None, text or "")
    except ConstraintError as ex:
      logger.error(f'"{mo.name}": the constraints can\'t be read ({ex}).')
      return
    mo["name"] = name
    if merged:
      mo.setAttr(CONSTRAINTS, Attribute(merged, str, VAR, CONSTRAINTS_NOTE))

  @contextmanager
  def batchedItemStates(self) -> Iterator[None]:
    '''
    Within it, objects' hiding and showing their canvas items (see
    *VObject._hideItems()*, *VObject._showItems()*) is put off, and done at
    the end in one pass over the canvas -- instead of a search of the whole
    canvas for each object's items, which is slow for many objects in a big
    view (eg: *doEraseOthers()*). Nested, only the outermost does it.
    '''
    if self.__dict__.get("_pendingItemStates") is not None:
      yield
      return
    self.__dict__["_pendingItemStates"] = {}
    try:
      yield
    finally:
      pending:dict[int, tuple[VObject, bool]] = self.__dict__.pop("_pendingItemStates")
      if pending:
        byTag = {vo.tag: (vo, hide) for vo, hide in pending.values()}
        c = self.canvas
        for i in c.find_all():
          for t in c.gettags(i):
            if t in byTag:
              vo, hide = byTag[t]
              vo._hideItem(i) if hide else vo._showItem(i)
        for vo, hide in byTag.values():
          if not hide:
            vo.__dict__["_itemsHidden"] = False

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

  BOTH_PANES = "both"
  "The pseudo-pane (see *containmentHomes()*) of something a rule or definition uses on both sides: astride the divider."

  def containmentHomes(self, among:Iterable[VObject]|None=None, window:VObject|None=None) -> dict[VObject, tuple[VObject, str]]:
    '''
    Where each contained object belongs: the context window, and its pane
    (see *VObject.panes()*), that it should sit in -- what layouts keep it in
    (see *homeRect()*).

    What a context contains directly -- nodes, relation types, and relations
    (their labels) -- belongs in it. So do the variables a contained relation
    uses but the context doesn't contain itself: its ends (eg: the base rules'
    !a and !b) and its type (?r). An object contained by (or used in) more than
    one context (eg: by a rule and by another window on the rule) belongs in
    the innermost one whose pane it's in, or, if it's in none, the smallest
    (the innermost, if they're nested). A window belongs only in a bigger
    window (so nesting can't go round in circles).

    In a rule or definition, the pane is the one its containment says
    (antecedent, consequent, definiendum, definiens) -- the one it's in, if
    it's in both -- or, for a plain "contains", the one it's in (or nearer). A
    variable used on both sides belongs astride the divider (*BOTH_PANES*).

    And a relation the context doesn't contain, whose two ends both belong in
    the same window, belongs there too (eg: a pattern relation's isa link to
    its type variable, !a -^r-> !b to ^r): in its ends' pane -- or, if they're
    in different ones, the one that isn't astride the divider, or astride it
    if neither is.

    :param among: Just these view objects (default: all of them).
    :type among: Iterable[VObject] | None
    :param window: Just what this window contains (and its contents use), as
      if it were the only one (default: all the windows).
    :type window: VObject | None
    :returns: Each contained view object: (its window, the pane's name).
    :rtype: dict[VObject, tuple[VObject, str]]
    '''
    m = self.model
    byObj:dict[int, dict[VObject, list[Relation]]] = {} # id(contained model object) -> {window: its containments of it}
    uses:dict[int, dict[VObject, set[str|None]]] = {}   # id(variable) -> {window: the panes of the contained relations using it}
    for w in (self.contextWindows() if window is None else [window]):
      mo = w.modelObject
      if mo is None:
        continue
      panes = w.panes()
      for r, _ in mo._getOutgoing(lambda r: r.isIndividual() and r.isa(m.CONTAINS)):
        d = r.localDst
        if d is None or d is mo:
          continue
        byObj.setdefault(id(d), {}).setdefault(w, []).append(r)
        if isinstance(d, Relation) and d.isIndividual():
          pane = "contains" if "contains" in panes else next((p for p in panes if r.isa(self._paneType(p))), None)
          for e in (d.localSrc, d.localDst, *d.getParents()):
            if e is not None and e is not mo and e.isVariable():
              uses.setdefault(id(e), {}).setdefault(w, set()).add(pane)
    if not byObj:
      return {}
    def area(w:VObject) -> float:
      x1, y1, x2, y2 = w.fullBoundingBox()
      return (x2 - x1) * (y2 - y1)
    memo:dict[int, tuple[VObject, str]|None] = {}
    def home(vo:VObject) -> tuple[VObject, str]|None: # (remembered: a relation's ends are asked for again and again)
      if id(vo) not in memo:
        memo[id(vo)] = None # (so a relation between relations can't go round in circles)
        memo[id(vo)] = homeOf(vo)
      return memo[id(vo)]
    def between(vo:VRelation) -> tuple[VObject, str]|None: # (a relation whose ends belong in the same window)
      if vo.modelObject.isa(m.CONTAINS) or not all(isinstance(e, VObject) and e._isConnected() for e in (vo.src, vo.dst)): # type: ignore[union-attr]
        return None
      hs, hd = home(vo.src), home(vo.dst) #type: ignore[arg-type]
      if hs is None or hd is None or hs[0] is not hd[0]:
        return None
      panes = {hs[1], hd[1]}
      if len(panes) > 1:
        panes.discard(self.BOTH_PANES)
      return hs[0], panes.pop() if len(panes) == 1 else self.BOTH_PANES
    def homeOf(vo:VObject) -> tuple[VObject, str]|None:
      mo = vo.modelObject if vo is not None else None
      if mo is None or not vo._isConnected():
        return None
      direct = id(mo) in byObj
      if not direct and (id(mo) not in uses or (isinstance(vo, VRelation) and mo.isIndividual())):
        return between(vo) if isinstance(vo, VRelation) else None
      cands:dict = byObj[id(mo)] if direct else uses[id(mo)]
      if not isinstance(vo, VRelation) and vo.isContextWindow():
        cands = {w: rs for w, rs in cands.items() if w is not vo and area(w) > area(vo)}
      if not cands:
        return None
      center = vo.centerPt()
      inside = [w for w in cands if w.paneAt(center) is not None]
      w = min(inside or cands, key=area)
      panes = w.panes()
      if "contains" in panes:
        return w, "contains"
      if not direct: # (used, not contained: on the side it's used on, or astride the divider)
        used = cands[w]
        return w, next(iter(used)) if len(used) == 1 and None not in used else self.BOTH_PANES
      here = w.paneAt(center)
      said = [p for p in panes if any(r.isa(self._paneType(p)) for r in cands[w])]
      if said:
        return w, here if here in said else said[0]
      if here is not None:
        return w, here
      return w, min(panes, key=lambda p: abs((panes[p][0] + panes[p][2]) / 2 - center[0])) # (the nearer pane)
    ret:dict[VObject, tuple[VObject, str]] = {}
    for vo in (self.values() if among is None else among):
      if vo is not None and (h := home(vo)) is not None:
        ret[vo] = h
    return ret

  def homeRect(self, w:VObject, pane:str) -> list[float]:
    '''
    The area (view coords) of window *w* that what belongs in its *pane* (see
    *containmentHomes()*) is kept in: the pane; or, for *BOTH_PANES*, a band
    astride the divider, a third of the window wide.

    :param w: A context window.
    :type w: VObject
    :param pane: One of its panes' names, or *BOTH_PANES*.
    :type pane: str
    :returns: [x1, y1, x2, y2].
    :rtype: list[float]
    '''
    panes = w.panes()
    if pane != self.BOTH_PANES:
      return panes[pane]
    left, right = panes.values()
    half = (right[2] - left[0]) / 6
    return [left[2] - half, left[1], left[2] + half, left[3]]

  BUMP_GAP = 12.0
  "How far outside a window (view units) something that doesn't belong in it is put (see *bumpIntruders()*)."

  def windowChain(self, vo:VObject, homes:dict[VObject, tuple[VObject, str]]) -> list[VObject]:
    '''
    :param vo:
    :type vo: VObject
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :returns: The window *vo* belongs in, the window that one's in, and so on out.
    :rtype: list[VObject]
    '''
    ret:list[VObject] = []
    w = homes.get(vo, (None, ""))[0]
    while w is not None and w is not vo and w not in ret:
      ret.append(w)
      w = homes.get(w, (None, ""))[0]
    return ret

  def belongsIn(self, vo:VObject, w:VObject, homes:dict[VObject, tuple[VObject, str]]) -> bool:
    '''
    Whether *vo* may be in context window *w*: it's *w*; *w* contains it (or
    its contents use it), directly or by way of a window in *w*; it's a window
    that *w* is in; or it's a relation to or from *w*, or *w*'s containment of
    something (drawn as being inside it).

    :param vo:
    :type vo: VObject
    :param w:
    :type w: VObject
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :rtype: bool
    '''
    if vo is w or w in self.windowChain(vo, homes) or vo in self.windowChain(w, homes):
      return True
    if isinstance(vo, VRelation) and (w in (vo.src, vo.dst) or vo.inWindow()):
      return True
    mo = vo.modelObject
    return mo is not None and bool(w.containmentOf(mo))

  def _visibleWindows(self) -> list[VObject]:
    '''
    :returns: The context windows that are drawn.
    :rtype: list[VObject]
    '''
    return [w for w in self.contextWindows() if not w.isHidden()]

  def awayFromWindows(self, vo:VObject, box:list[float], homes:dict[VObject, tuple[VObject, str]],
                      obstacles:list[list[float]]=[], gap:float|None=None) -> tuple[float, float]|None:
    '''
    How far to move *vo*, were its box *box*, to be clear of every context
    window it doesn't belong in (see *belongsIn()*) -- the least move, keeping
    it in its own pane if it's in it now (see *containmentHomes()*), and off
    *obstacles* if it can be (see *layout.clearOf()*).

    :param vo:
    :type vo: VObject
    :param box: Its box, there.
    :type box: list[float]
    :param homes: As from *containmentHomes()* (for *vo* and the windows, at least).
    :type homes: dict[VObject, tuple[VObject, str]]
    :param obstacles: Boxes not to land on.
    :type obstacles: list[list[float]]
    :param gap: The clearance (default: *BUMP_GAP*).
    :type gap: float | None
    :returns: (dx, dy) -- (0, 0) if it's clear already -- or None if there's no place.
    :rtype: tuple[float, float] | None
    '''
    windows = self._visibleWindows()
    keepOut = [list(w.boundingBox()) for w in windows if w is not vo and not self.belongsIn(vo, w, homes)]
    if not keepOut:
      return 0.0, 0.0
    within = None
    if (home := homes.get(vo)) is not None:
      r = self.homeRect(*home)
      cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
      if r[0] <= cx <= r[2] and r[1] <= cy <= r[3] and box[2] - box[0] <= r[2] - r[0] and box[3] - box[1] <= r[3] - r[1]:
        within = r # (it's in its pane: it stays in it)
    return clearOf(box, keepOut, obstacles, within=within, gap=self.BUMP_GAP if gap is None else gap)

  def _intrudes(self, vo:VObject, w:VObject, homes:dict[VObject, tuple[VObject, str]]) -> bool:
    '''
    :returns: Whether *vo* overlaps window *w* without belonging in it (see
      *belongsIn()*). Of two windows overlapping, neither in the other, the
      smaller is the one that\'s in the way.
    :rtype: bool
    '''
    if vo is w or self.belongsIn(vo, w, homes):
      return False
    a, b = vo.boundingBox(), w.boundingBox()
    if not (a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]):
      return False
    if not isinstance(vo, VRelation) and vo.isContextWindow():
      area = lambda r: (r[2] - r[0]) * (r[3] - r[1])
      return (area(a), vo._id) < (area(b), w._id) # (the smaller yields)
    return True

  def bumpIntruders(self) -> list[tuple[VObject, list[int], list[int]]]:
    '''
    Push everything drawn in a context window it doesn't belong in (see
    *belongsIn()*: eg: something a window was dropped on, or uncovered by
    expanding it, or whose containment was removed) out of it -- each the
    least it takes (see *awayFromWindows()*), onto a free place if there's one
    near. Windows go first (carrying their contents), then nodes, then
    relations' labels; a floating label is put back between its ends (see
    *VRelation.reposition()*), which keeps it out of windows itself. Done
    after every command (see *ViewDoList*), not in the middle of a drag.

    :returns: (object, its box before, after) for each one moved, in order.
    :rtype: list[tuple[VObject, list[int], list[int]]]
    '''
    windows = self._visibleWindows()
    if not windows:
      return []
    homes = self.containmentHomes()
    objs = [o for o in self.values() if o is not None and o._isConnected() and not o.isHidden()]
    isWindow = lambda o: not isinstance(o, VRelation) and o.isContextWindow()
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    rank = lambda o: 0 if isWindow(o) else 2 if isinstance(o, VRelation) else 1
    moves:list[tuple[VObject, list[int], list[int]]] = []
    for vo in sorted(objs, key=rank):
      if not any(self._intrudes(vo, w, homes) for w in windows):
        continue
      old = list(vo.boundingBox())
      if floats(vo):
        cast(VRelation, vo).reposition(adjustPos=False) # (back between its ends -- out of the window: see VRelation.placedLabel())
      else:
        carried = set(vo.carriedContents()) if isWindow(vo) else set()
        near = expandRect(old, 400)
        obstacles = [list(o.boundingBox()) for o in objs if o is not vo and o not in carried and not isWindow(o) and not floats(o)
                     and (b := o.boundingBox())[0] < near[2] and near[0] < b[2] and b[1] < near[3] and near[1] < b[3]]
        d = self.awayFromWindows(vo, old, homes, obstacles)
        if d is None or d == (0.0, 0.0):
          continue
        vo.moveTo(old[0] + d[0], old[1] + d[1], adjustPos=False)
      new = list(vo.boundingBox())
      if new != old:
        moves.append((vo, old, new))
        if isWindow(vo):
          homes = self.containmentHomes() # (what's where has changed)
    if moves:
      logger.info(f"moved {len(moves)} object{'' if len(moves) == 1 else 's'} out of windows {'it doesn' if len(moves) == 1 else 'they don'}'t belong in.")
    return moves

  def restackWindows(self) -> None:
    '''
    Put the context windows beneath everything else, each above the window
    it's on (see *containmentHomes()*): a window inside another is drawn on
    top of it, whichever was drawn last.
    '''
    windows = self.contextWindows()
    if not windows or self.canvas is None:
      return
    homes = {vo: w for vo, (w, _) in self.containmentHomes(windows).items()} if len(windows) > 1 else {}
    def depth(w:VObject) -> int:
      d = 0
      while (w := homes.get(w)) is not None and d < len(windows): #type: ignore[assignment]
        d += 1
      return d
    for w in sorted(windows, key=depth, reverse=True): # (the innermost lowered first: the outermost ends up at the bottom)
      self.canvas.tag_lower(w.tag)
    # the shadows and highlights on a window go just in front of it (see placeBehind()): the outermost first, so the innermost wins
    c = self.canvas
    for w in sorted(windows, key=depth):
      frame = w._shape.id if w._shape is not None else None
      bb = c.bbox(frame) if frame is not None else None
      if bb:
        for item in c.find_overlapping(*bb):
          tags = c.gettags(item)
          if ("shadow" in tags or "highlight" in tags) and w.tag not in tags:
            c.tag_raise(item, frame)

  def placeBehind(self, item:int, ownerTag:str) -> None:
    '''
    Stack something drawn behind a view object -- a type's shadow, or a
    highlight's glow (canvas *item*: see *decorators.ShadowDecorator*,
    *decorators.Highlight*) -- behind everything, but just in front of the
    topmost context window it's on (other than its owner's, tagged
    *ownerTag*), so the window doesn't hide it (windows are beneath
    everything: see *restackWindows()*). One spatial query
    (find_overlapping()) each.

    :param item:
    :type item: int
    :param ownerTag: The tag of the view object it's the shadow of.
    :type ownerTag: str
    '''
    c = self.canvas
    bb = c.bbox(item)
    frames = [i for i in c.find_overlapping(*bb) if "context-frame" in (tags := c.gettags(i)) and ownerTag not in tags] if bb else []
    if frames:
      c.tag_raise(item, frames[-1]) # (find_overlapping() gives them bottom to top)
    else:
      c.tag_lower(item)

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
    if mo is None or vo.isHidden() or vo.isInferred(): # (not what can't be seen, or the reasoner's: see GraphObject.inferred)
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
            "definiendum": m.DEFINIENDUM, "definiens": m.DEFINIENS, "condition": m.CONDITION, "required": m.REQUIRED}[pane]

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
    if not self.isModelEditor(): # (containment's in the model: a locked view just moves things)
      return
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
          others = [r for r in rels if any(r.isa(t) for t in (m.ANTECEDENT, m.CONSEQUENT, m.DEFINIENDUM, m.DEFINIENS, m.CONDITION, m.REQUIRED))]
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


  def isModelEditor(self) -> bool:
    '''
    :returns: Whether the model can be changed in this view: it isn't locked
      (see *setEditLocked()*), and the model isn't write-locked. Either way,
      the view itself can be (eg: moving things, or erasing them from view).
    :rtype: bool
    '''
    return not self.__dict__.get("_editLocked", False) and not self.model.writeLocked()

  def lockedReason(self) -> str:
    '''
    :returns: Why the model can't be changed in this view (see
      *isModelEditor()*), for a message.
    :rtype: str
    '''
    if self.model.writeLocked():
      return f'"{self.model.name}" is write-locked: it can\'t be changed here.'
    return "This view is locked: it can't change the model. Click the pencil (bottom right) to unlock it."

  def editLocked(self) -> bool:
    '''
    :returns: Whether the user's locked this view, so it can't change the
      model (see *setEditLocked()*).
    :rtype: bool
    '''
    return self.__dict__.get("_editLocked", False)

  def _editLockedVar(self) -> tk.BooleanVar:
    '''
    :returns: Whether the model can't be changed in this view (see
      *isModelEditor()*) -- what "Edit | Lock view" shows (and sets: see
      *_onLockViewItem()*).
    :rtype: tk.BooleanVar
    '''
    var = self.__dict__.get("_editLockedVarObj")
    if var is None:
      var = self._editLockedVarObj = tk.BooleanVar(self.canvas, value=not self.isModelEditor())
    return var

  def _onLockViewItem(self) -> None:
    '''
    "Edit | Lock view" was chosen: lock or unlock the view, as the pencil in
    the reasoning toolbar does (see *setEditLocked()*) -- not a write-locked
    model's.
    '''
    if not self.setEditLocked(self._editLockedVar().get()):
      self.window.bell()

  def setEditLocked(self, locked:bool=True) -> bool:
    '''
    Lock this view, so it can't change the model (see *isModelEditor()*) --
    only how it's shown -- or unlock it. Not other views of the model. It's
    saved with the view. A write-locked model's view can't be unlocked.

    :param locked:
    :type locked: bool
    :returns: Whether it's done (unlocking a write-locked model's view isn't).
    :rtype: bool
    '''
    if not locked and self.model.writeLocked():
      logger.warning(self.lockedReason())
      self._editLockedVar().set(True)
      return False
    if locked != self.editLocked():
      self._editLocked = locked
      self.setDirty() # (saved with the view)
    self._editLockedVar().set(not self.isModelEditor())
    bar = self.__dict__.get("_reasoningToolbar")
    if bar is not None:
      bar.refreshLock()
    return True
  


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


  def gatherIntoWindow(self, w:VObject) -> None:
    '''
    Move what context window *w* contains (and the variables its contents
    use) into it, each into its pane (see *containmentHomes()*), at a free
    spot -- as near as can be to where it was, if that's just outside its
    pane; otherwise set out in rows from the pane's top left, far enough
    apart for the labels of the relations between them -- as one undoable
    command. What's already in its pane stays put, and so does what sits in
    another window that also contains it. If there's no room, the window
    grows downward. A collapsed window is expanded first. Floating relations
    (their labels) aren't moved: they follow their ends.

    :param w: A context window (see *VObject.isContextWindow()*).
    :type w: VObject
    '''
    if not w.isContextWindow():
      return
    floats = lambda o: isinstance(o, VRelation) and o.floating()
    margin = 10.0
    near = 100.0 # (how far out of its pane something can be and still be just nudged in; otherwise it's set out in rows)
    topMargin = 22.0 if len(w.panes()) > 1 else margin # (room for the pane labels)
    allHomes = self.containmentHomes()
    def elsewhere(vo:VObject) -> bool: # (in another window that has it)
      other = allHomes.get(vo, (None, None))[0]
      return other is not None and other is not w and other.paneAt(vo.centerPt()) is not None
    homes = {vo: pane for vo, (_, pane) in self.containmentHomes(window=w).items()
             if not floats(vo) and not elsewhere(vo)}
    def inside(box:list[float], rect:list[float]) -> bool:
      return rect[0] <= box[0] and rect[1] <= box[1] and box[2] <= rect[2] and box[3] <= rect[3]
    toMove = sorted((vo for vo, pane in homes.items() if not inside(vo.boundingBox(), self.homeRect(w, pane))),
                    key=lambda vo: (vo.boundingBox()[1], vo.boundingBox()[0]))
    if not toMove:
      logger.info(f'"{w.name}": nothing to gather.')
      return
    # Plan it all first (the commands only run when the composite ends): where each goes, and how
    # big the window must be.
    moving = set(toMove)
    labels = [o.boundingBox() for o in self.values() if o is not None and floats(o) and (o.src in moving or o.dst in moving)] # type: ignore[attr-defined]
    gap = (max([margin, *((b[2] - b[0]) + 2 * margin for b in labels)]), # (room between things for the labels between them)
           max([margin, *((b[3] - b[1]) + 2 * margin for b in labels)]))
    W = list(w.fullBoundingBox()) # (as expanded, if it's collapsed)
    def rectIn(pane:str, bb:list[float]) -> list[float]: # (the pane's rect if the window were *bb*: see VObject.panes())
      r, sx = self.homeRect(w, pane), (bb[2] - bb[0]) / (W[2] - W[0])
      return [bb[0] + (r[0] - W[0]) * sx, r[1], bb[0] + (r[2] - W[0]) * sx, r[3] + bb[3] - W[3]]
    obstacles = []
    for o in self.values():
      if o is None or o is w or o in moving or not o._isConnected() or o.isHidden():
        continue
      if floats(o) and any(e in moving for e in (o.src, o.dst)): # type: ignore[attr-defined]
        continue # (it'll follow its ends)
      b = list(o.boundingBox())
      if not isinstance(o, VRelation) and o.isContextWindow() and b[0] <= W[0] and b[1] <= W[1] and W[2] <= b[2] and W[3] <= b[3]:
        continue # (a window w is in)
      obstacles.append(b)
    bb, moves = list(W), []
    for vo in toMove:
      box = list(vo.boundingBox())
      while True:
        rect = rectIn(homes[vo], bb)
        inRect = [o for o in obstacles if o[0] < rect[2] and rect[0] < o[2] and o[1] < rect[3] and rect[1] < o[3]]
        out = max(rect[0] - box[0], box[2] - rect[2], rect[1] - box[1], box[3] - rect[3])
        if (d := freeSpotIn(box, rect, inRect, margin=margin, topMargin=topMargin, gap=gap, rows=out > near)) is not None:
          break
        # No room: grow down by its height -- and wider, if it's too wide for its pane (the panes
        # share the width).
        short = (box[2] - box[0]) + 2 * margin - (rect[2] - rect[0])
        bb[2] += short * (bb[2] - bb[0]) / (rect[2] - rect[0]) if short > 0 else 0
        bb[3] += (box[3] - box[1]) + gap[1] + margin
      placed = [box[0] + d[0], box[1] + d[1], box[2] + d[0], box[3] + d[1]]
      obstacles.append(placed)
      moves.append((vo, box, placed))
    with CompositeCommandMgr(self.context):
      if w.collapsed:
        self.context.collapse(w, False)
      if bb != W:
        self.context.resize(w, bb[0], bb[1], bb[2], bb[3])
      for vo, box, placed in moves:
        self.context.move(vo, placed[0], placed[1], _oldPos=box, adjustPos=False)
    self.resetScrollRegion(shrink=True)
    logger.info(f'"{w.name}": gathered {len(toMove)} object{"" if len(toMove) == 1 else "s"}.')

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

  
        