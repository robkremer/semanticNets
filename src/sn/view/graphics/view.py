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
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.vrelations import VRelation
from random import random
from _collections_abc import Generator
from threading import Thread
from concurrent.futures._base import Future
import os
import sys
from time import monotonic_ns, sleep
import tkinter as tk
from tkinter import ttk
from tkinter.messagebox import askyesno
from collections import namedtuple
from math import sqrt
import xml.etree.ElementTree as et
from ast import literal_eval
from typing import Any, Optional, Union, Tuple, Callable, Iterable, Dict, List, \
  override
from tkinter.filedialog import asksaveasfilename
from urllib.request import urlopen
import weakref

import sn
from util.utils import bindRightMouse, flattenPairs, s_SHIFT, \
  normalizeRect, eventEqual
from util.observer import Observer, Subject
from util.utils import Categories, urlToFile, getFullClassName, urlExists, changeUrlExtension,\
  fileToUrl
from util.command import DoList, CommandWrapper
from util.persistence.pRef import PRDb, PRObject
from sn.model.model import Model
from sn.model import GraphObject
from sn.model import Node
from sn.model import Relation, IsaIndividual
import sn.view.graphics.layout as layouts
from sn import snPrefs
from itertools import chain
from sn.view.graphics.loggingPanedWindow import TGViewWindow, AppWindow, APP_WINDOW
from util.attribute import Attribute

import logging
import urllib
from types import NoneType
from sn.view.graphics.attributeEditor import applyEditAttrsBox
from urllib.error import URLError
from util.rtValuesDialog import RTValueDialog, Param
logger:sn.SNLogger = sn.getLogger(__name__)

'''
  .. inheritance-diagram:: SNView
      :parts: 3
      :private-bases:
      :top-classes: SNView

Created on Jan 1, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

-----------
'''

KEY_UNDO =                  ('<Command-KeyPress-z>'       , 'cmd+z')
KEY_REDO =                  ('<Shift-Command-KeyPress-Z>' , 'shift+cmd+Z')
KEY_REPAINT =               ('<Command-KeyPress-r>'       , 'cmd+r')
KEY_VALIDATE =              ('<Command-KeyPress-v>'       , 'cmd+v')
KEY_TOGGLE_FIELDS_LAYOUT =  ('<Command-KeyPress-f>'       , 'cmd+f')

ANIMATION_PARAMS = {
          "animationFrameTime_ms":  Param(100, 10, 5000, 
                                    'The time (in milliseconds) to wait between frame refreshes after drawing', 
                                    True),
          "animationCyclesInit":    Param(10, 1, 100, 
                                    'The number of frames to calculate before doing the first draw', 
                                    False),
          "animationCycles":        Param(1, 1, 100, 
                                    'The number of frames to calculate between drawings', 
                                    False),
          }

##########################################################################################
################################### class SNView #########################################
##########################################################################################

class SNView(PRDb, Observer):
  r"""
  The actual graph editor Canvas container (with scrollbars).  Not actually a GUI element
  itself. Quite a large class, handling the user interaction. It's
  a container for visual objects, :class:`vnodes.VNode`, :class:`vrelations.VRelation`
  and :class:`vrelations.VIsa`. All of these reference their model counterparts for
  actual semantic information (such a relations and type constraints), in addition to
  shared visual attributes (such as fillColor, bounderColor, shape, and label).
  Important member properties are:
  
    - canvas
    - vscroll
    - hscroll
    - model: a pointer to the corresponding *Model* object.
    - nodes: an iterator yielding the *VNode* objects within the *PRDb*'s list of *PRObject* objects (which are all *VObject* objects).
    - relations: similar to above, but *VRelation* objects.
  """

  makeRelationData = namedtuple('makeRelationData', 'node typ lineID')

  def __init__(self, model:Optional[Model]=None, url:Optional[str]=None, root:Optional[AppWindow]=None,
               hiddenCategories:Optional[List[str]]=None,
               **kwargs):
    '''
    :param model: [Optional[Model]] A model for which to create this new view
    :param url: [Optional[str] A URL to name this model
    :param root: An *AppWindow*.
    :param hiddenCategories:
    :param kwargs:
    
    At least one of *model* and *url* must not be *None*.
    '''
    from sn.view.graphics.vnodes import VNode
    from sn.view.graphics.vrelations import VRelation

    assert isinstance(model, (Model, NoneType))
    assert isinstance(url, (str, NoneType))
    assert model is not None or url is not None
    if root is None:
      import __main__
      root = __main__.root
    assert isinstance(root, AppWindow)
    assert isinstance(hiddenCategories, (list, NoneType))
    
    if model is not None:
      self.model = model
      url = changeUrlExtension(model.url, ".tgv") if url is None else url
    else:
      self.model = None

    self.prefsCallbacks:dict[str,int] = dict()
    'A place to store registered Prefs callbacks so we can remove them in *destroy()*.'
    
    # call the PRObject (Persistent Object) and Subject constructors
    PRDb.__init__(self, url)
    Subject.__init__(self)
    assert url in PRDb.AllDBs

    # ## TGview stuff
    self._appWindow = weakref.ref(root)
    self._fontFace = "TkMenuFont"
    self._fontSize = 12
    self._scale = 1.0
    self.isModelEditor = True
    self._suppressLocalLayout = False
    self.newNodeCoords = (0, 0)
    
    self._drawVersion:int = 0
    '''Used by draw (and sub-methods) to avoid repeating updating the view, 
    This incremented for top-level operations, and matched locally in methods
    such that methods can skip if this "global" version is not higher than their 
    local version'''
    
    self.shouldCatchNewObjects:Union[bool, Tuple[int,int], NoneType] = None
    "A flag(+) indicating the view should display any new objects when the model calls *self.update()*. The value may be 2-tuple, indicating the point at which to display it."
    
    self.localLayoutName = "find free"
    self.layoutObjects:Dict[str, layouts.LayoutHieristic] = {"find free": layouts.FindFree(self)}
    # self.layoutObjects:Dict[str, tygra.layout.LayoutHieristic] = {
    #     "ISA hierarcy (vert)": layouts.IsaHierarchy(self),
    #     "ISA hierarcy (vert, tight)": layouts.IsaHierarchyCompressed(self),
    #     "ISA hierarcy (horz)": layouts.IsaHierarchyHorizontal(self),
    #     "ISA hierarcy (horz, tight)": layouts.IsaHierarchyHorizontalCompressed(self),
    #     "find free": layouts.FindFree(self),
    #     "find free (tight)": layouts.FindFree(self, spacing=[0,0,0,0], relSpacing=[-4,-4,-4,-4]),
    #     "nudge": layouts.Nudge(self),
    #     "nudge (tight)": layouts.Nudge(self, spacing=[0,0,0,0], relSpacing=[-4,-4,-4,-4]),
    #     }
    self.setLocalLayout(self.layoutObjects[self.localLayoutName], name=self.localLayoutName)
    assert isinstance(self.localLayout, layouts.LayoutHieristic)

    self.readingPRDb = False

    self.nodes = lambda: self.makeGenerator(lambda po: isinstance(po, VNode))
    self.relations = lambda: self.makeGenerator(lambda po: isinstance(po, VRelation))
    # self.newNodeDisplaySelectionPolicy = None
    # self.setNewNodeDisplaySelectionPolicy()
    self.selected = set()  # Used by VNodes for noting selection groups
    self._scrolling = False
    self._selectionBoxInfo = None
    self._eventHandled = None
    self._makingRelationFrom = None

    # windowing stuff
    self.scrollRegion = (0, 0, 4000, 3000)

    self.doList:DoList = None # initiated by BuildSurroundingWindow(), only declared here for IDE

    self.buildSurroundingWindow(**kwargs)

    if urlExists(url):
      self._read()
    
    try:
      # from sn.view.animatedLayouts import FieldsLayout, FieldsLayout_threaded, FieldsLayout_threadPool
      # self.fieldsLayoutObj:FieldsLayout = FieldsLayout_threadPool(self)
      from sn.view.graphics.layouts.tygraToWorkerProxy import snProxy
      from sn.view.graphics.layouts.fieldsLayout import FieldsLayoutAnimationAlgorithm
      self.fieldsLayoutObj = TygraProxy(FieldsLayoutAnimationAlgorithm, [])
    except:
      logger.exception("Can't load FieldsLayout_threadPool:")
    self.animationActive = False
    self.animationFrameTime_ms = ANIMATION_PARAMS["animationFrameTime_ms"].default
    self.animationCyclesInit = ANIMATION_PARAMS["animationCyclesInit"].default
    self.animationCycles = ANIMATION_PARAMS["animationCycles"].default

    self.model.addObserver(self)

    ## Categories stuff
    self.categories = Categories[GraphObject]()
    self.categories.addCategory("system", lambda n: (n.system or n.toNode.system or n.fromNode.system) if isinstance(n, Relation) else n.system)
    self.categories.addCategory("type", lambda n: (n['type'] or n.toNode['type'] or n.fromNode['type']) \
                    if isinstance(n, Relation) else n['type'])
    self.categories.addCategory("individual node", lambda n: isinstance(n, Node) and not n['type'])
    self.categories.addCategory("individual relation", lambda n: isinstance(n, Relation) and not n['type'])
    self.categories.addCategory("higher order", lambda n: isinstance(n, Relation) \
          and (n['type'] \
            or (isinstance(n.fromNode, Relation) and n.fromNode['type']) \
            or (isinstance(n.toNode, Relation) and n.toNode['type'])))
    self.categories.addCategory("isaRelations", lambda n: isinstance(n, Relation) and n.isIsa)
    #self.hiddenCategories = set(["system", "higher order"]) if hiddenCategories is None else set(hiddenCategories)
    self.hiddenCategories = set() if hiddenCategories is None else set(hiddenCategories)
    
    # register *self.repaint()* callbacks for the appropriate keys in *tygraPrefs*.
    repaintCallback = lambda k,v,me=self: me.repaint()
    for s in ["view_showSystemTags", "view_showTypeTags", "view_showRemoteTags", "view_showRoleLabels"]:
      self.prefsCallbacks[s] = tygra.tygraPrefs.addCallback(s, repaintCallback)

  @property # A weakref property
  def appWindow(self):
    return self._appWindow()
  
  @property
  def loggingPanedWindow(self):
    return self._loggingPanedWindow() if self._loggingPanedWindow is not None else None
    
  @override
  def askSaveFile(self) -> bool:
    '''
    :return: *True* iff the file has been saved.
    
    Iff *self.dirty* is True, inquire if the file is to be saved. This is the text-only
    version. Graphic subclasses should override this method to use a dialog box.
    
    This version overrides the *Persistent* class behaviour to check that *Model* is 
    saved before saving the view for it.
    '''
    if PRDb.askSaveFile(self) and self.model.dirty:
      self.model.write()
      logger.print(f'Also saved model "{self.model.url}"')
    
  def freshPaint(self):
    self._drawVersion += 1
    
  def buildSurroundingWindow(self, **kwargs):
    '''
    Builds the *TGViewWindow* (which in turn builds the *tk.Toplevel* window), 
    and calls *self.makeFrame* to build the scrolling canvas (where the drawing
    actually takes place).
    
    Instantiates:
    
      - self.doList (as the *TGViewWindow* doList)
      - self._loggingPanedWidnow
    '''
    self.getHeaderInfo()
    
    # import __main__ as m
    # assert m.root is not None
    # root:AppWindow = m.root
    tkparent = TGViewWindow(self.appWindow, self)

    self.doList = tkparent.doList

    self._loggingPanedWindow = weakref.ref(tkparent)
    
    if tkparent is not None:
      self.makeFrame(tkparent, **kwargs)

    logger.parent.info(f'Welcome to TypedGraphs!\n  Running on python {sys.version}\n  cwd: "{os.getcwd()}"')

    
  def makeFrame(self, tkparent, **kwargs):
    '''
    Builds the scrolling frame for *self.canvas* (where the drawing actually
    takes place). Also calls *self.makeBindings()* to establish the mouse bindings of
    the canvas background.
    
    Instantiates:
      - self.frame: the outer frame which includes the scroll bars
      - self.hScroll
      - self.vScroll
      - self.canvas
    '''
    self.frame = tkparent.appFrame

    if "scrollregion" not in kwargs:
      kwargs["scrollregion"] = self.scrollRegion
    self.hScroll = ttk.Scrollbar(self.frame, orient=tk.HORIZONTAL)
    self.vScroll = ttk.Scrollbar(self.frame, orient=tk.VERTICAL)
    kwargs["yscrollcommand"] = self.vScroll.set
    kwargs["xscrollcommand"] = self.hScroll.set
    if "view_backgroundColor" not in tygra.tygraPrefs:
      tygra.tygraPrefs["view_backgroundColor"] = Attribute("view_backgroundColor", "color", "grey95")
    if "bg" not in kwargs: kwargs["bg"] = tygra.tygraPrefs.get('view_backgroundColor', storeDefault="white")

    # Call the tk.Canvas and PRDb constructors
    self.canvas = tk.Canvas(self.frame, **kwargs)

    self.hScroll['command'] = self.canvas.xview
    self.vScroll['command'] = self.canvas.yview

    self.canvas.grid(column=0, row=0, sticky=(tk.N, tk.W, tk.E, tk.S))
    self.hScroll.grid(column=0, row=1, sticky=(tk.W, tk.E))
    self.vScroll.grid(column=1, row=0, sticky=(tk.N, tk.S))
    self.frame.grid_columnconfigure(0, weight=1)
    self.frame.grid_rowconfigure(0, weight=1)

    self.makeBindings();

  @override
  def _registerPO(self, po:PRObject) -> int:
    ret = PRDb._registerPO(self, po)
    with Subject.ChangeMgr(self) as mgr:
      mgr.registerTopics([("new", po)])
    return ret

  def update(self, subject:Subject, *topics:Tuple[str, Any, ...]) -> None:
    """
    Receive update from subject.
    """
    assert subject is self.model, f'SNView.update() subject param of focus model ({self.model} @ {id(self.model)}), but got {subject} @ {id(subject)}.'
    #logger.warning("SNView.update() not implemented.")
    if subject is self.model and self.shouldCatchNewObjects is not None:
      for topic in topics:
        if topic[0] == "new":
          modelObject:GraphObject = topic[1]
          assert isinstance(modelObject, GraphObject)
          # Thie modelObject is not necessarily fully constructed to we need to defer it's drawing until it's done. 
          self.canvas.after_idle(self.makeViewObjectForGraphObject, modelObject, 
                                 self.shouldCatchNewObjects if isinstance(self.shouldCatchNewObjects, Tuple) else None) #, expand, filter)

  def doNewNodeCommand(self, parent:Node, individual:bool, atPoint:Optional[Tuple[int,int]]=None):
    """
    :param parent: [Node] The supertype of the new object to be created. If parent is a
      *Relation* a *Relation* is created, otherwise a *Node* is created.
    :param individual: [bool] iff True, creates and **individual**, otherwise creates a **type**.
    :param atPoint: [Optional[Tuple[int,int]]] If given, creates the new object at this point

    Creates a Node or Relation object in the model and displays it on this view.  
    
    :note: This method fails cleanly if *parent* is an individual or if you try to create an
      individual relation (but allows and relation type).
    """
    from sn.model.tgcommands import NewModelNodeCommand, NewModelRelationCommand
    if parent.isIndividual():
      logger.error(f'Cannot make a {"instance" if individual else "subtype"} of an individual.')
      return
    if isinstance(parent, Relation):
      if individual:
        logger.error(f'Please use a object menu to create an individual relation between objects.')
        return
      command = NewModelRelationCommand(self.model, parent=parent, individual=individual)
    else:
      command = NewModelNodeCommand(self.model, parent=parent, individual=individual)
    cmd = CommandWrapper(
              command, 
              setup=lambda pt=atPoint: self.setCatchNewObjects(atPoint=pt), 
              teardown=self.resetCatchNewObjects)
    node = self.doList.do(cmd)
    applyEditAttrsBox(self.canvas, node, title=str(node), editKey="name")
    vnode = self.findViewObjectForGraphObject(node)
    if vnode is not None:
      vnode.draw()
    
  def doNewRelationCommand(self, parent:Relation, individual:bool, frm:GraphObject, to:GraphObject, atPoint:Optional[Tuple[int,int]]=None):
    """
    :param parent: [Relation] The supertype of the new object to be created. If parent is a
      *Relation* a *Relation* is created, otherwise a *Node* is created.
    :param individual: [bool] iff True, creates and **individual**, otherwise creates a **type**.
    :param atPoint: [Optional[Tuple[int,int]]] If given, creates the new object at this point

    Creates a Node or Relation object in the model and displays it on this view.  
    
    :note: This method fails cleanly if *parent* is an individual or if you try to create an
      individual relation (but allows and relation type).
    """
    from sn.model.tgcommands import NewModelNodeCommand, NewModelRelationCommand
    if parent.isIndividual():
      logger.error(f'Cannot make a {"instance" if individual else "subtype"} of an individual.')
      return
    if isinstance(parent, Relation):
      if individual:
        logger.error(f'Please use a object menu to create an individual relation between objects.')
        return
      command = NewModelRelationCommand(self.model, parent=parent, individual=individual)
    else:
      command = NewModelNodeCommand(self.model, parent=parent, individual=individual)
    cmd = CommandWrapper(
              command, 
              setup=lambda pt=atPoint: self.setCatchNewObjects(atPoint=pt), 
              teardown=self.resetCatchNewObjects)
    node = self.doList.do(cmd)
    applyEditAttrsBox(self.canvas, node, title=str(node), editKey="name")
    vnode = self.findViewObjectForGraphObject(node)
    vnode.draw()
    
  def setCatchNewObjects(self, atPoint:Optional[Tuple[int,int]]=None):
    """
    :param atPoint: if *Tuple[int, int]*, the point at which to put the new object.
    """
    self._oldCatchNewObjects = self.shouldCatchNewObjects
    self.shouldCatchNewObjects = True if atPoint is None else atPoint
    
  def resetCatchNewObjects(self):
    self.shouldCatchNewObjects = self._oldCatchNewObjects
    
  def onEnter(self, _event):
    '''Ensures this *Canvas* has focus whenever the mouse is over it.'''
    self.canvas.focus_set()
    self.canvas.focus()

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
    # scroll using two-finger drag
    self.canvas.bind('<MouseWheel>', self.onMouseWheel)
    self.canvas.bind('<Shift-MouseWheel>', self.onShift_MouseWheel)

    # undo/redo
    self.canvas.bind(KEY_UNDO[0], lambda _x: self.doList.undo())
    self.canvas.bind(KEY_REDO[0], lambda _x: self.doList.redo())
    
    # repaint
    self.canvas.bind(KEY_REPAINT[0], self.repaint)

    # validate
    self.canvas.bind(KEY_VALIDATE[0], lambda _x: self.validate(refresh=True))
    
    # fields layout
    self.canvas.bind(KEY_TOGGLE_FIELDS_LAYOUT[0], lambda _x: self.onToggleFieldsLayout())

  def setScrollRegion(self, size:Optional[Tuple[int, int]]=None):
    if size is None:
      maxx = 0
      maxy = 0
      for n in self.values():
        bb = n.boundingBox()
        if bb[2] > maxx: maxx = bb[2]
        if bb[3] > maxy: maxy = bb[3]
      maxx += 500
      maxy += 500
      if maxx < 4000: maxx = 4000
      if maxy < 3000: maxy = 3000
      self.scrollRegion = [0, 0, int(maxx), int(maxy)]
    else:
      self.scrollRegion = [0, 0, size[0], size[1]]
    self.configure(scrollregion=self.scrollRegion)

  def incrementScrollRegion(self, by:Tuple[int, int]=(1000, 750)):
    self.scrollRegion = [0, 0, self.scrollRegion[2] + by[0], self.scrollRegion[3] + by[1]]
    self.configure(scrollregion=self.scrollRegion)

  def destroy(self):
    # try:
    #   self.container.notifyViewDeleted(self)
    # except:
    #   pass
    # for r in self.relations():
    #   try:
    #     r.delete()
    #   except:
    #     pass
    # for n in self.nodes():
    #   try:
    #     n.delete()
    #   except:
    #     pass
    # self.container = None
    PRDb.destroy(self)
    self.model = None
    self.canvas = None
    #remove all the registered callbacks for this view
    for key,ID in self.prefsCallbacks.items():
      tygra.tygraPrefs.removeCallback(key, ID)
      
      
 
  # @override
  # def askSaveFile(self):
  #   '''
  #   Iff *self.dirty* is True, inquire if the file is to be saved.
  #   '''
  #   if self.url is not None:
  #     fn = urlToFile(self.url)
  #     ans = askyesno(self.url, f'View {self.name} has been modified. Do you want to save changes?', parent=self.loggingPanedWindow)
  #     if ans:
  #       print(f'{fn} saved.')
  #       self.write()
  #     else:
  #       print(f'{fn} changed NOT saved.')
  #   else:
  #     self.saveFile(askForFileName=True)
    
  ### Persistence ######################################################################

  @override
  def _url_setter(self, url:str):
    super()._url_setter(url)
    self.loggingPanedWindow.setWindowTitle()
    
  def saveFile(self, askForFileName=False):
    if self.url is None:
      askForFileName = True
    if askForFileName:
      ext = ".tgv"
      filename:str = None if self.url is None else urlToFile(self.url)
      if filename is None:
        dirname = None
      else:
        dirname = os.path.dirname(filename)
        filename = os.path.basename(filename)
        fileSplit = filename.split(".")
        if len(fileSplit) > 1:
          ext = "."+fileSplit[-1]
          filename = ".".join(fileSplit[0:-1])
      f = asksaveasfilename(
              parent=self.canvas.winfo_toplevel(),
              title="Save Tygra view",
              defaultextension=ext, 
              initialdir=dirname,
              initialfile=filename,
              filetypes=[("tygra view files", ".tgv"), ("xml files", ".xml")])
      if f is None or f=="":  # asksaveasfile return `None` if dialog closed with "cancel".
        return
      url = fileToUrl(f)
      if self.url != url:
        self.url = url
    self.write(forceWrite=True)

  def serializeXML(self) -> et.Element:
    """
    Returns the representation of this object as an Element object.
    Implementors should call *super().serializeXML()* **first** as this top-level method
    will construct the Element itself.
    """
    elem = PRDb.serializeXML(self)  # selective "super()"
    elem.set("model", self.model.idString)
    elem.set("modelEditor", str(self.isModelEditor))
    elem.set("hiddenCategories", str(list(self.hiddenCategories)))
    elem.set("geometry", self.canvas.winfo_toplevel().geometry())

    # # save nodes
    # nodes = et.Element("nodes")
    # elem.append(nodes)
    # for n in self.nodes():
    #   x = n.serializeXML()
    #   nodes.append(x)
    #
    # # save relations
    # rels = et.Element("relations")
    # elem.append(rels)
    # for r in self.relations():
    #   x = r.serializeXML()
    #   rels.append(x)
    
    return elem

  @classmethod
  def getArgs(cls, elem: et.Element) -> Tuple[List[Any], Dict[str, Any]]:
    r"""
    :param elem: The *ElementTree* element from which we are unserializing.
    :param addrServer: The address server from which we can lookup any
      addresses by id that occur in *elem*. Note that although *addrServer*
      may not be used here, it might be necessary for subclasses to use
      it, so it needs to be in the argument list.
    :return: An (\*args, \*\*kwargs) tuple for the constructor of the class
      found in the element's name.
    """
    args = []
    kwargs = dict()
    args.append(None)  # TODO: should we be passing a Window here?

    modelID = elem.get("model")
    self.model = Model.getStore(modelID)
    
    modelEditor = elem.get("modelEditor")
    self.isModelEditor = modelEditor == True
    assert isinstance(self.isModelEditor, bool)
    
    hiddenCategories = elem.get("hiddenCategories")
    if hiddenCategories is not None:
      kwargs["hiddenCategories"] = literal_eval(hiddenCategories)

    geometry = elem.get("geometry")
    if geometry is not None:
      kwargs["windowGeometry"] = geometry

    return args, kwargs

  def unserializeXML(self, elem: et.Element):
    """
    :param elem: The *ElementTree* element from which we are unserializing.
    :param addrServer: The address server from which we can lookup any
      addresses by id that occur in *elem*. Note that although *addrServer*
      may not be used here, it might be necessary for subclasses to use
      it, so it needs to be in the argument list.

    This object is partially constructed, but we need to restore this class's bits.
    Implementors should call *super().unserializeXML()* at some point.
    """
    self.readingPRDb = True
    try:
      # self.model = Model.getStore(elem.get("model"))
      # self.isModelEditor = bool(elem.get("modelEditor"))
      # self.hiddenCategories = literal_eval(elem.get("hiddenCategories"))
      # self.geometry = elem.get("geometry")
      self.getHeaderInfo(elem)
      PRDb.unserializeXML(self, elem)      
      for o in self.values():
        try:
          o._post__init__()
        except Exception:
          logger.exception(f'{self.__class__.__name__}.unserializeXML() calling {o}._post_init__():')
    except Exception:
      logger.exception(f'{self.__class__.__name__}.unserializeXML():')
    finally:
      self.readingPRDb = False
      self.dirty = False
      self.repaint()

  def validate(self, refresh:bool=False) -> int:
    errCount = 0
    for n in self._objects.values():
      errCount += len(n.validate())
    if errCount == 0:
      logger.info("All nodes and relations passed validation.")
    else:
      logger.warning(f"Found {errCount} validation faults.")
    if refresh:
      self.freshPaint()
      self.repaint()
    return errCount

  def getHeaderInfo(self, elem:Optional[et.Element]=None):
    '''
    Fill in the following self.* properties, either from *elem* (if *elem* is not *None*),
      or as defaults (if the respective property is not instantiated):
    
      - self.isModelEditor
      - self.hiddenCategories
      - self.geometry
    '''
    if elem is None:
      try:
        with urlopen(self.url) as f: # could raise urllib.error.URLError
          tree = et.ElementTree(file=f)
          elem = tree.getroot()#("PRDb")#self.__class__.__name__)
          assert elem.tag == getFullClassName(self.__class__)
      except urllib.error.URLError:
        #if self.url is None or not urlExists(self.url):
        if not hasattr(self, "isModelEditor")   : self.isModelEditor    = True
        if not hasattr(self, "hiddenCategories"): self.hiddenCategories = []
        if not hasattr(self, "geometry")        : self.geometry         = "600x800"
        return
    modelURL = elem.get("model")
    try:
      self.model = Model.getStore(modelURL)
    except Exception as ex:
      raise URLError(f'SNView.getHeaderInfo(): Unexpected exception opening "{modelURL}": {ex.__class__.__name__}: {str(ex)}')
    self.isModelEditor = bool(elem.get("modelEditor"))
    self.hiddenCategories = literal_eval(elem.get("hiddenCategories"))
    self.geometry = elem.get("geometry")

  ### Event handling ###################################################################

  def onRightMouse(self, event:tk.Event) -> Optional[tk.Menu]:
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
    return bgMenu

  def onMotion(self, event:tk.Event) -> None:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None

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
    self._selectionBoxInfo = [
        self.canvas.create_rectangle(self.viewToWindow(self.canvas.canvasx(event.x), self.canvas.canvasy(event.y), self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)), fill="", width=3, outline="blue", dash=(1,6)), 
        event.x, 
        event.y, 
        False]

  def onB1_Motion(self, event):
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None

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
      if isinstance(self._makingRelationFrom.node, VRelation):
        typeList = self.relations()
      elif isinstance(self._makingRelationFrom.node, VNode):
        typeList = self.nodes()
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
        logger.debug(f"making relation from {self._makingRelationFrom.node} to {item} of type {self._makingRelationFrom.typ}.", level="debug")
        self.makeRelation(self._makingRelationFrom.node, item, self._makingRelationFrom.typ)
      else:
        logger.debug("Relation's toNode must match the being a node/relation with the from Node", level='error')
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

    Called on the two finger touchpad X-scroll event.

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return.

    * Call *self.canvas.xview_scroll)*.
    """
    if self.isEventHandled(event):
      self.removeEventHandled(event)
      return None
    self.canvas.xview_scroll(int(event.delta), 'units')

  def onToggleFieldsLayout(self):
    if not self.animationActive:
      self.animationActive = True
      logger.info("Animation on")
      self.fieldsLayoutObj.nextFrame(graph=list(self._objects.values()), activeNodes=[], cycles=10, 
                                     callback=lambda future, slf=self : slf.after(slf.fieldsListener, future))
    else:
      self.animationActive = False
      
  def fieldsListener(self, future:Future):
    '''
    This is the callback for a call to the animation's *nextFrame* method. It performs
    the moves listed in the result of the call (but carefully, as it only performs
    N moves before yielding to the mainloop using *after_idle()*). Then, when
    it's completed that, it requeues itself back into the mainloop (unless 
    *self.animationActive* has become *False*, in which case, it exists).
    '''
    def doMoves(moves:List[Tuple[int, Tuple[float, float]]]):
      '''
      Performs the actual moves from an animation calculation, but doesn't do more
      than N at a time before releasing the mainloop using *after_idle()* to requeue
      itself.  When it's done it waits 500ms to start a new animation if the 
      *self.animationActive* is still *True*.
      '''
      i = max = 5 # set the number of iterations before yielding to the mainloop
      for k,v in moves:
        obj:VObject = self._objects[k] 
        obj.moveToCenterOn(v[0], v[1], adjustPos=False)
        i -= 1
        if i == 0: # requeue the remaining moves and exit
          self.after(lambda slf=self, moves=moves[max:]: doMoves(moves))
          return
      if self.animationActive: # if still active, call nextFrame() in animation process with this method as the callback
        self.after(lambda slf=self: slf.fieldsLayoutObj.nextFrame(activeNodes=[], cycles=1, 
                                    callback=lambda future, slf=self : slf.after(slf.fieldsListener, future)),
                   wait=self.animationFrameTime_ms)
      else: # if animation is signaled to abort, exit
        logger.info("Animation off")
      
    moves = future.result(timeout=1.0) # shouldn't timeout
    moves = [(k, v) for k,v in moves.items()] #change moves into a list of tuplels
    doMoves(moves)

      
  def onShowAnimationControls(self):
    '''
    Ask the animation for it's parameters and constraints, create params control
    dialog, and run it, passing changed parameters to (and from) the remote process.
    '''
    from sn.view.graphics.layouts.fieldsLayout import FIELD_LAYOUT_PARAMS

    def receiveParams(future:Future):
      '''
      This is the callback from asking the animation for the values of its parameters.
      Create an animation control dialog and populate it from *FIELD_LAYOUT_PARAMS
      and the received result.
      '''
      self.animationControls = RTValueDialog(self._loggingPanedWindow()._tkTop(), title=self._loggingPanedWindow()._tkTop().title())
      params:dict[str,Any] = future.result(timeout=2) # will wait on the result
      for k,v in FIELD_LAYOUT_PARAMS.items():
        self.animationControls.appendSlider(k, v.type, params[k] if k in params else v.default, v.default, v.min, v.max, 
                       lambda n, v: self.after(sliderChanged, n, v), 
                       v.help, v.log)
      params = {"animationFrameTime_ms": self.animationFrameTime_ms, "animationCycles": self.animationCycles, "animationCyclesInit": self.animationCyclesInit}
      for k,v in ANIMATION_PARAMS.items():
        assert hasattr(self, k)
        val = getattr(self, k)
        self.animationControls.appendSlider(k, v.type, val, v.default, v.min, v.max, 
                       lambda n, v: self.after(sliderChanged, n, v), 
                       v.help, v.log)
      self.animationControls.show()
  
    def sliderChanged(name:str, value:Any):
      '''
      Callback for a slider change. 
      '''
      print("sliderChanged")
      if name in ANIMATION_PARAMS:
        setattr(self, name, value)
        return
      try:
        future:Future = self.fieldsLayoutObj.updateSettings(**{name: value})
        future.add_done_callback(lambda future, name=name, oldValue=value: self.after(AnimationParamVerified, future, name, oldValue))
      except:
        logger.exception("sliderChanged():")
      
    def AnimationParamVerified(future:Future, name, oldValue):
      '''
      The callback from the remote process verifying a change to a parameter. If the 
      parameter hadn't changed as expected, update the animation controls dialog.
      '''
      print("AnimationParamVerified")
      result:dict = future.result(timeout=2)
      if result[name] != oldValue:
        self.animationControls[name] = result[name]
      
    future:Future = self.fieldsLayoutObj.updateSettings() # ask for the values of params
    future.add_done_callback(lambda future, slf=self: slf.after(receiveParams, future))

  def after(self, f:Callable, *args, wait:Optional[float]=None):
    if wait is None or wait==0.0:
      self.canvas.winfo_toplevel().after_idle(f, *args)
    else:
      self.canvas.winfo_toplevel().after(wait, f, *args)
     
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

  def defaultNewNodeDisplaySelectionPolicy(self, mObj:GraphObject) -> bool:
    """
    :param mObj: A MObject to test for displaying
    :return: True iff *mObj* is not in *self.hiddenCategories* and it's
      a relation whose to- and from- nodes are displayed.
    """
    if self.categories.isCategory(mObj, self.hiddenCategories):
      return False
    if isinstance(mObj, Relation):
      displayedModels = {n.model for n in self.values()}
      if mObj.toNode in displayedModels and mObj.fromNode in displayedModels:
        return True
    return False

  def setNewNodeDisplaySelectionPolicy(self, func:Optional[Callable[[GraphObject], bool]]=None):
    """
    Changes the policy on displaying newly created model objects are selected for display.
    By default (argument is *None*), the policy is
    *self.defaultNewNodeDisplaySelectionPolicy()*.
    :return: The previous policy function
    """
    oldPolicy = self.newNodeDisplaySelectionPolicy
    if func is None:
#      self.newNodeDisplaySelectionPolicy = lambda mObj: not self.categories.isCategory(mObj, self.hiddenCategories)
      self.newNodeDisplaySelectionPolicy = self.defaultNewNodeDisplaySelectionPolicy
    else:
      self.newNodeDisplaySelectionPolicy = func
    return oldPolicy

  def notifyModelChanged(self, modelObj, modelOperation:str):
    """Handles modelOperations: "add node", "add rel", "del node", "del rel"""
    if modelOperation in ["add node", "add rel"]:
      if self.newNodeDisplaySelectionPolicy(modelObj):
        vObject = self.findViewObjectForGraphObject(modelObj)
        if vObject is None:
          self.makeViewObjectForGraphObject(modelObj)
    elif modelOperation == "del node" or modelOperation == "del rel":
      vObject = self.findViewObjectForGraphObject(modelObj)
      if vObject is not None:
        vObject.delete()
    else:
      raise TypeError(f'SNView.notifyModelChanged({modelObj}, "{modelOperation}"): Unknown model operation "{modelOperation}".')

  ### Utility ##########################################################################

  def viewToWindow(self, *args) -> List[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from view to window coordinates.
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0]
    #assert len(args) % 2 == 0, f'args = {args}'
    ret = []
    for n in args:
      ret.append(n * self._scale)
    return ret

  def windowToView(self, *args) -> List[float]:
    """
    :param args: Either a single list argument or multiple float parameters. In either case there
          must be an even number of items, taken as x,y pairs. Since scaling is x:y equal, this "even"
          limitation is relaxed here.
    :return: A list converted coordinates where the evens are x coordinates and the odds are y coordinates
          converted from window to view coordinates.
    """
    if len(args) == 1 and isinstance(args[0], Iterable):
      args = args[0]
    #assert len(args) % 2 == 0, f'args = {args}'
    ret = []
    for n in args:
      ret.append(n / self._scale)
    return ret

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
    bgMenu = tk.Menu(self.canvas)

    # "new instance" and "new subtype" for nodes menus
    if self.isModelEditor:
      def fillMenu(menu:tk.Menu, model:Model, individual:bool, makeRelations:bool):
        types = []
        for t in (t for t in (model.relations if makeRelations else model.nodes) if t.isType()):
          types.append(t)
        types.sort(key=lambda x: x.name) #sort by name alphabetically
        for t in types:
          menu.add_command(label=t.name, \
            command=lambda x=x, y=y, t=t: self.doNewNodeCommand(parent=t, individual=individual, atPoint=(x,y)))
        
      def makeSubmenu(individual:bool, makeRelations:bool):
        newMenu = tk.Menu(self.canvas)
        # process nodes in the included models
        for k,v in self.model.includes.items():
          m = tk.Menu(self.canvas)
          fillMenu(m, Model.getStore(v), individual, makeRelations)
          newMenu.add_cascade(label=k, menu=m)
        # process own nodes
        fillMenu(newMenu, self.model, individual, makeRelations)
        return newMenu
        
      bgMenu.add_cascade(label="new instance of Node"   , menu=makeSubmenu(individual=True, makeRelations=False))
      bgMenu.add_cascade(label="new subtype of Node"    , menu=makeSubmenu(individual=False, makeRelations=False))
      bgMenu.add_cascade(label="new subtype of Relation", menu=makeSubmenu(individual=False, makeRelations=True))
      bgMenu.add_separator()

    bgMenu.add_command(label="validate", command=lambda o=self: o.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #utils.CHAR_CMD
    bgMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1]) #utils.CHAR_CMD
    bgMenu.add_command(label="show all", command=self.showAllModel)
    bgMenu.add_command(label="toggle field layout", command=self.onToggleFieldsLayout, accelerator=KEY_TOGGLE_FIELDS_LAYOUT[1])
    bgMenu.add_command(label="show animation controls", command=self.onShowAnimationControls)
    # from sn.view.animatedLayouts import testBones
    # bgMenu.add_command(label="test bones", command=lambda s=self: testBones(s))
    
    def makeShowMenu():
      newMenu = tk.Menu(self.canvas)
      # sort the list of individuals
      nodes = dict()
      nodeNames = []
      for i in self.model.nodes:
        if i.isIndividual():
          nodes[i.name] = i
          nodeNames.append(i.name)
      nodeNames = sorted(nodeNames)
      # make a menu item for each
      for i in nodeNames:
        newMenu.add_command(label=nodes[i].name, command=lambda mo=nodes[i]: self.makeViewObjectForGraphObject(mo))
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

    # if app.DEBUG_MENUS:
    #   bgMenu.add_separator()
    #   bgMenu.add_command(label="validate", command=self.validate)

    return bgMenu

  def toggleCategory(self, name:str):
    if name in self.hiddenCategories:
      self.hiddenCategories.remove(name)
    else:
      self.hiddenCategories.add(name)
      # nodes should be deleted ahead and separately from relations and deleting nodes might automattically delete relations
      for n in [x for x in self.nodes() if self.categories.isCategory(x.model, self.hiddenCategories)]:
        n.delete()
      for n in [x for x in self.relations() if self.categories.isCategory(x.model, self.hiddenCategories) and x.model['type']]:
        n.delete()
      for n in [x for x in self.relations() if self.categories.isCategory(x.model, self.hiddenCategories)]:
        n.delete()

  # def queueNewNode(self, x, y, t):
  #   self.newNodeCoords = (x, y)
  #   mNode = Node(self.model, t, idServer=self.model)
  #   mNode.attrs.edit(self, title=f'New subtype of {t.idString} "{t["label"]}"')

  def isEventHandled(self, event):
    return eventEqual(event, self._eventHandled)

  def addEventHandled(self, event):
    self._eventHandled = event

  def removeEventHandled(self, event):
    self._eventHandled = None

  @property
  def localLayout(self):
    return self.doNothing if self._suppressLocalLayout else self._localLayout

  def setLocalLayout(self, layout, name=None):
    if layout is not None:
      assert isinstance(layout, layouts.LayoutHieristic)
      self._localLayout = layout
      self.localLayoutName = "" if name is None else name
    return self.localLayout

  def doNothing(self, *args, **kwargs):
    logger.log(logging.DEBUG, "SNView.doNothing() called.")

  def suppressLocalLayout(self, suppress:str|bool|None=None):
    if suppress is not None:
      if isinstance(suppress, str):
        self._suppressLocalLayout = suppress.lower() in ['true', 't', 'yes', 'y', 'on']
      else:
        assert isinstance(suppress, bool)
        self._suppressLocalLayout = suppress
    return self._suppressLocalLayout

  ### Operations #######################################################################

  def makeViewObjectForGraphObject(self, mObject:GraphObject,
                                   atPoint:Optional[Tuple[float, float]]=None,
                                   expand:int=0,
                                   filter:Optional[Callable[[Any, Relation], bool]]=lambda vn, mr: True) \
                                   ->PRObject: #->VObject
    '''
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
    from sn.view.graphics.vrelations import VRelation, VIsa
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vnodes import VNode
    # make certain we don't make a duplicate    #createdVObjects:set[VObject] = set()
    ret = self.findViewObjectForGraphObject(mObject)
    if ret is None:
      if isinstance(mObject, IsaIndividual):
        ret = VIsa(self, modelObject=mObject)
      elif isinstance(mObject, Relation):
        ret = VRelation(self, modelObject=mObject)
      elif isinstance(mObject, Node):
        sizex = mObject.get('vis/minSize', tygraPrefs.get("view_NodeMinSize", storeDefault=30))
        sizey = int(sizex / mObject.get('vis/aspectRatio', tygraPrefs.get("view_NodeAspectRatio", storeDefault=1.5)))
        if atPoint is None:
          try:
            mParent = mObject.getParents().__next__()
            vParent = self.findViewObjectForGraphObject(mParent)
          except StopIteration: # no parent
            vParent = None
          if vParent is None:
            x, y = self.newNodeCoords
          else:
            bb = vParent.boundingBox()
            x = bb[0]
            y = bb[1] + 120
        else:
          x, y = atPoint
        ret = VNode(self, mObject, x=x, y=y, x1=x + sizex, y1=y + sizey)
      else:
        raise AttributeError(f'SNView.makeViewObjectforGraphObject(): unexpected model object type: {mObject.__class__.__name__}.')

    assert isinstance(ret, VObject), f'SNView.makeViewObjectForGraphObject(): Unexpected return type "{ret.__class__.__name__}".'
    if expand > 0:
      ret.expand(filter=filter, expand=expand - 1)
    return ret

  def repaint(self, event=None):
    self.freshPaint()
    for obj in self.values():
      if not obj.isHidden():
        obj.draw()

  def findViewObjectForGraphObject(self, mObject:GraphObject) -> Optional[PRObject]: #-> Optional[VObject] 
    '''
    :param mObject: A model object.
    :return: A *VObject* currently in the display representing *mObject*, or *None* if there is not such object.
    '''
    if not isinstance(mObject, GraphObject):
      raise AttributeError(f'Expected a param of type GraphObject, but got type {mObject.__class__.__name__}')
    for obj in self.values():
      if obj.modelObject is mObject:  # already displayed?
        # TODO: remove this expensive assertion
        assert obj in list(self.nodes()) or obj in list(self.relations()), f'obj.__class__ = {obj.__class__.__name__}, len(self.relations) = {len(list(self.relations))}, len(self.nodes()) = {len(list(self.nodes()))}'
        return obj
    return None

  def _defaultPopulate(self):
    n = 0
    for obj in self.model._objects.values():
      self.makeViewObjectForGraphObject(obj)
      n += 1
    if n==0: # if this is brand new and has nothing, display the included models' objects.
      for incURL in self.model.includes.values():
        try:
          incModel:Model = PRDb.getStore(incURL)
          for obj in incModel._objects.values():
            self.makeViewObjectForGraphObject(obj)
        except Exception as ex:
          logger.exception(f'AppWindow.onNewModel(): Failed to open included model "{incURL}": {ex}')
    
  def showAllModel(self):
    x = 10
    y = 10
    sizex = self.model.top['vis/minSize']
    sizey = int(sizex * self.model.top['vis/aspectRatio'])
    grid = (sizex * 2, sizey * 2)
    numNodes = len(list(self.model.nodes)) - len(list(self.nodes()))
    gridCount = int(sqrt(numNodes)) if numNodes>0 else 0
    blockSize = gridCount * grid[1] + y
    for mnode in self.model.nodes:
      if self.categories.isCategory(mnode, self.hiddenCategories):
        continue
      vObj = self.findViewObjectForGraphObject(mnode)
      if vObj is None and not self.categories.isCategory(mnode, self.hiddenCategories):
        n = self.makeViewObjectForGraphObject(mnode, atPoint=(x, y))
        if y < blockSize:
          y += grid[1]
        else:
          x += grid[0]
          y = 10
        self.localLayout(n)
    for mrel in self.model.relations:
      if self.categories.isCategory(mrel, self.hiddenCategories) or \
          all(map(lambda obj: self.categories.isCategory(obj, self.hiddenCategories), 
                  map(lambda role: role["filler"], list(chain(mrel.roles.values()))))):
        continue  
      vObj = self.findViewObjectForGraphObject(mrel)
      if vObj is None:
        try:
          r = self.makeViewObjectForGraphObject(mrel)
          self.localLayout(r)
        except Exception as ex:
          logger.write(f'Could not instantiate VObject for {type(mrel).__name__} {mrel.idString} "{mrel["label"]}": {type(ex).__name__}("{ex}")', level='warning', exception=ex)

  def makeRelationFrom(self, node:PRObject, typ:Optional[Relation]=None):
    '''
    :param node: [VObject]
    '''
    from sn.view.graphics.vobjects import VObject
    assert isinstance(node, VObject)
    if typ is None or (isinstance(typ, Relation) and typ.isType()):
      lineID = self.canvas.create_line(
        self.viewToWindow(flattenPairs([node.centerPt(), node.centerPt()])),
        fill="cyan", width=3, arrow=tk.LAST)
      self._makingRelationFrom = SNView.makeRelationData(node, typ, lineID)
    else:
      if not isinstance(typ, Relation):
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument must be a model Relation; got object of class {type(typ).__name__}.')
      else:
        raise TypeError(f'SNView.makeRelationFrom(): "typ" argument "{typ.name}" must be type, not an individual;.')

  def makeRelation(self, fromNode:PRObject, toNode:PRObject, typ:Relation):
    from sn.view.graphics.vobjects import VObject
    from sn.view.graphics.vrelations import VRelation
    assert isinstance(fromNode, VObject)
    assert isinstance(toNode, VObject)
    if      isinstance(fromNode, VRelation) and not isinstance(toNode, VRelation) or \
      not isinstance(fromNode, VRelation) and     isinstance(toNode, VRelation):
      logger.error("Relations must be either between nodes or between relations only.", level='error')
      return
    if typ and not isinstance(typ, Relation):
      logger.error(f'Relation typ {typ["label"]} must be a relation.', level='error')
      return
    try:
      if typ is self.model.isaType: #isinstance(typ, IsaIndividual):
        rel = IsaIndividual(self.model, src=fromNode.modelObject, dst=toNode.modelObject)
      else:
        rel = Relation(self.model, 
                       fillers=[("src", fromNode.modelObject), ("dst", toNode.modelObject)], 
                       parent=typ, qualifiers=INDIVIDUAL)
      self.makeViewObjectForGraphObject(rel)
    except Exception as ex:
      logger.exception("SNView.makeRelation():")
#       raise ex

#   def __repr__(self):
#     return f'<{type(self).__name__}, id={self.idString}, container={repr(self.container)}>'
#
#   def moveto(self, tag, x, y):
#     print(f'TGView.moveto(): x={x}, y={y}')
#     super().moveto(tag, x, y)

  def intersectTag(self, ids:Iterable[int], tag:str, exclude:Union[list[int], int]=[]) -> list[int]:
    '''
    :param ids: [Iterable[int]] An *Iterable* of *ints* representing *Canvas* ids.
    :param tag: [str] A *str* *Canvas* tag.
    :param exclude: [list[int] or int, default=[]] A list of *int* representing *Canvas* ids.
    :return: A list of all ids in *ids* that have tag *tag* that are not in *exclude*.
    '''
    if isinstance(exclude, int): exclude = [exclude]
    ret = []
    for id in ids:
      if tag in self.canvas.gettags(id) and id not in exclude:
        ret.append(tag)
    return ret


      