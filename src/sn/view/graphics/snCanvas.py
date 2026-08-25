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
import sn
from sn.model.model import Model, Node, Relation, Collection
from sn.controller.modelInterface import ModelContext
from sn.view.graphics.guiApp2 import SNGViewFrame

from typing import cast, override, Any
from util.utils import bindRightMouse, fixURL
from util.terminal import inputAsync
from util.persistence.pRef import PRDb
from util.observer import Subject, Observer
from util.attributeEditor import applyEditAttrsBox
#from sn.view.graphics.vobjects import VObject

logger:sn.SNLogger = sn.getLogger(__name__)

'''
The Canvas that handles Semantic Nets visual graphics representing objects in
one of more models (but having a single default model).

Created on Aug 21, 2026

@author: robkremer
'''
import tkinter as tk

class SNGContext(ModelContext):
  @override
  def __init__(self, model:Model):
    super().__init__(model)
    self.view:SNGView = None
    

class SNGView(PRDb["VObject"], Observer):
  '''
  The persistent container of VObjects.
  '''
  def __new__(cls, url:str|None, canvas:SNCanvas, model:Model, mode="w", _reading:bool=False):
    if url is None:
      url = fixURL(model.url, extension=".snv", replaceExt=True, mode="w")[0]
    return PRDb.__new__(cls, url, mode=mode, _reading=_reading)

  def __init__(self, url:str|None, canvas:SNCanvas, model:Model, mode="w", _reading:bool=False):
    if url is None:
      url = fixURL(model.url, extension=".snv", replaceExt=True, mode="w")[0]
    PRDb.__init__(self, url)
    self.canvas:SNCanvas = canvas
    self.model:Model = model
    model.addObserver(self)

  @override
  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]])->None:
    logger.info(f'SNGView.update({subject.name}, {len(topics)} topics):')
    for t in topics:
      topicName:str = t[0]
      topicData:tuple[Any, ...] = t[1]
      if topicName == 'add GraphObject':
        modelID = topicData[0]
        modelObj = topicData[1]
        logger.info(f'  Creating V{modelObj.__class__.__name__} for model object {modelID}:{modelObj.__class__.__name__}')
        applyEditAttrsBox(self.canvas, modelObj, title=modelObj.name, editKey="name")
      else:
        logger.warning(f'  Unsupported topic "{topicName}": {topicData}')


class SNCanvas(tk.Canvas):
  '''
  classdocs
  '''

  def __init__(self, master:SNGViewFrame, **kwargs):
    '''
    Constructor
    '''
    #assert isinstance(master, SNGViewFrame), f'Expected SNGViewFrame, got {type(master)}'
    tk.Canvas.__init__(self, master, kwargs)
    self.create_text(10, 10, text=f'Model: {self.model}')
    #self.after(30, print, "hello from the graphics display")
    
    self._scale:float = 1.0
    self._fontFace:str = "Arial"
    self._fontSize:float = 10.0
    
    self.makeBindings()
    
  @property
  def model(self) -> Model:
    return cast(SNGViewFrame, self.master).model
    
  @property
  def context(self) -> ModelContext:
    return cast(SNGViewFrame, self.master).context
    
  # ---- Event handling --------------------------------------------------------

  def makeBindings(self):
    '''
    Create the bindings for the *Canvas* object.
    '''
    # self.canvas.bind("<Enter>", self.onEnter)
    #
    # # For making relations
    # self.canvas.bind("<B1-ButtonRelease>", self.onB1_ButtonRelease)
    # self.canvas.bind("<Motion>", self.onMotion)

    # for popup menu
    bindRightMouse(self, self.onRightMouse)  # lambda e: self.backgroundMenu(e).post(e.x_root, e.y_root))

    # # scroll using mouse click-and-drag
    # self.canvas.bind("<Button-1>", self.onButton_1)
    # self.canvas.bind("<B1-Motion>", self.onB1_Motion)
    # # scroll using two-finger drag
    # self.canvas.bind('<MouseWheel>', self.onMouseWheel)
    # self.canvas.bind('<Shift-MouseWheel>', self.onShift_MouseWheel)
    #
    # # undo/redo
    # self.canvas.bind(KEY_UNDO[0], lambda _x: self.doList.undo())
    # self.canvas.bind(KEY_REDO[0], lambda _x: self.doList.redo())
    #
    # # repaint
    # self.canvas.bind(KEY_REPAINT[0], self.repaint)
    #
    # # validate
    # self.canvas.bind(KEY_VALIDATE[0], lambda _x: self.validate(refresh=True))
    #
    # # fields layout
    # self.canvas.bind(KEY_TOGGLE_FIELDS_LAYOUT[0], lambda _x: self.onToggleFieldsLayout())

  def onRightMouse(self, event:tk.Event): # -> Optional[tk.Menu]:
    """
    :param event: *event.x* and *event.y* contain the x,y coordinate of the click.
    :return: None or the result of *self.makeMenu()*.

    Called when the right mouse button is pressed (different for Mac and other OS's).

    * Check if the event has been handled by a contained widget. If it has been,
      call *self.removeEventHandled()* and return *None*.

    * Put up the popup menu (*self.makeMenu()*).
    """
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
    bgMenu = tk.Menu(self)

    # A menu command's callback runs on the main/GUI thread, where the
    # blocking builtin input() always raises RuntimeError — inputAsync()
    # returns immediately and delivers the typed line to onResult once the
    # user actually answers.
    bgMenu.add_command(label="input", command=lambda: inputAsync("What? ", onResult=print))
    # # "new instance" and "new subtype" for nodes menus
    if self.isModelEditor():
      def fillMenu(menu:tk.Menu, model:Model, individual:bool, ptype:type):
        # types = []
        types = [v for v in model.values() if isinstance(v, ptype) and v.isType()]
        # for t in (t for t in (model.relations if makeRelations else model.nodes) if t.isType()):
        #   types.append(t)
        types.sort(key=lambda x: x.name) #sort by name alphabetically
        for t in types:
          if ptype is Node:
            fun = lambda t=t: self.context.new_node(t, name="?", individual=individual)
          elif ptype is Relation:
            fun = lambda t=t: self.context.new_relation(t, name="?", individual=individual)
          # elif ptype is Collection:
          #   fun = lambda t=t: self.context.new_collection(t, name="?", individual=individual)
          menu.add_command(label=t.name, command=fun)
    
      def makeSubmenu(individual:bool, ptype:type):
        newMenu = tk.Menu(self)
        # process nodes in the included models
        for v in [self.model, Model.AllDBs["sn:/sn.xml"]]:
          m = tk.Menu(self)
          fillMenu(m, v, individual, ptype)
          newMenu.add_cascade(label=v.name, menu=m)
        # process own nodes
        #fillMenu(newMenu, self.model, individual, ptype)
        return newMenu
    
      bgMenu.add_cascade(label="new instance of Node"   , menu=makeSubmenu(individual=True, ptype=Node))
      bgMenu.add_cascade(label="new subtype of Node"    , menu=makeSubmenu(individual=False, ptype=Node))
      bgMenu.add_cascade(label="new instance of Relation", menu=makeSubmenu(individual=True, ptype=Relation))
      bgMenu.add_cascade(label="new subtype of Relation", menu=makeSubmenu(individual=False, ptype=Relation))
      # bgMenu.add_cascade(label="new instance of Collection", menu=makeSubmenu(individual=True, ptype=Collection))
      # bgMenu.add_cascade(label="new subtype of Collection", menu=makeSubmenu(individual=False, ptype=Collection))
      bgMenu.add_separator()
    
    # bgMenu.add_command(label="validate", command=lambda o=self: o.validate(refresh=True), accelerator=KEY_VALIDATE[1]) #utils.CHAR_CMD
    # bgMenu.add_command(label="repaint", command=self.repaint, accelerator=KEY_REPAINT[1]) #utils.CHAR_CMD
    # bgMenu.add_command(label="show all", command=self.showAllModel)
    # bgMenu.add_command(label="toggle field layout", command=self.onToggleFieldsLayout, accelerator=KEY_TOGGLE_FIELDS_LAYOUT[1])
    # bgMenu.add_command(label="show animation controls", command=self.onShowAnimationControls)
    # # from sn.view.animatedLayouts import testBones
    # # bgMenu.add_command(label="test bones", command=lambda s=self: testBones(s))
    #
    # def makeShowMenu():
    #   newMenu = tk.Menu(self.canvas)
    #   # sort the list of individuals
    #   nodes = dict()
    #   nodeNames = []
    #   for i in self.model.nodes:
    #     if i.isIndividual():
    #       nodes[i.name] = i
    #       nodeNames.append(i.name)
    #   nodeNames = sorted(nodeNames)
    #   # make a menu item for each
    #   for i in nodeNames:
    #     newMenu.add_command(label=nodes[i].name, command=lambda mo=nodes[i]: self.makeViewObjectForGraphObject(mo))
    #   return newMenu
    # bgMenu.add_cascade(label="show", menu=makeShowMenu())
    #
    # # "hide/enable" menu
    # # hideEnableMenu = tk.Menu(self)
    # # for name in self.categories.keys():
    # #   hideEnableMenu.add_command(label=f'{"enable" if name in self.hiddenCategories else "hide"} {name}',
    # #       command = lambda n=name: self.toggleCategory(n))
    # # bgMenu.add_cascade(label="hide/enable", menu=hideEnableMenu)
    # # bgMenu.add_separator()
    #
    # # "local layout" menu
    # # localLayoutsMenu = tk.Menu(self)
    # # self.suppressLocalLayoutButton = tk.BooleanVar(value=self._suppressLocalLayout)
    # # self.radio = tk.StringVar(value=self.localLayoutName)
    # # for name, obj in self.layoutObjects.items():
    # #   if obj.isLocal():
    # #     localLayoutsMenu.add_radiobutton(label=name, variable=self.radio, value=name, \
    # #         command=lambda lo=obj, name=name: self.setLocalLayout(lo, name=name))
    # # localLayoutsMenu.add_separator()
    # # localLayoutsMenu.add_checkbutton(label="suppress autolayout", variable=self.suppressLocalLayoutButton,
    # #     onvalue=True, offvalue=False,
    # #     command=lambda val=not self.suppressLocalLayout(): self.suppressLocalLayout(val))
    # # bgMenu.add_cascade(label="local layout", menu=localLayoutsMenu)
    #
    # # "global layout" menu
    # # layoutsMenu = tk.Menu(self.canvas)
    # # for name, obj in self.layoutObjects.items():
    # #   if obj.isGlobal() and not obj.isLocal():
    # #     layoutsMenu.add_command(label=name, command=obj)
    # # layoutsMenu.add_separator()
    # # for name, obj in self.layoutObjects.items():
    # #   if obj.isGlobal() and obj.isLocal():
    # #     layoutsMenu.add_command(label=name, command=obj)
    # # bgMenu.add_cascade(label="global layout", menu=layoutsMenu)
    # # bgMenu.add_command(label="reset scroll region", command=self.setScrollRegion)

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
    self.scale("all", 0, 0, self._scale / oldScale, self._scale / oldScale)
    for child_widget in self.find_withtag("text"):
      self.itemconfigure(child_widget, font=(self._fontFace, int(self._fontSize * self._scale)))
    try:
      bb = list(self.bbox("all"))
    except:
      bb = [0, 0, 0, 0]
    bb = [0, 0, bb[2] + 800, bb[3] + 600]
    self.configure(scrollregion=bb)

  
        