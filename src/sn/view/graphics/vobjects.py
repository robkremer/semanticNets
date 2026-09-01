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
from util.attribute import Restriction
from util.persistence.serialize import InstantiationInfo, ParamInfo,\
  PropertyInfo
from sn.model.model import UP_ARROW
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

import weakref
from typing import Any, Optional, Union, Tuple, Iterable, Callable, override,\
  cast
import xml.etree.ElementTree as et
from ast import literal_eval
import tkinter as tk

import sn
from util.persistence.pRef import PRObject, PRDb, PReference #, DeletedObjectError
from util.observer import Observer, Subject
from util.utils import tag_bindRightMouse, tag_unbindRightMouse, s_CMD, s_SHIFT,\
  expandRect, overlaps, pointInPoly
from util.tooltip import CreateToolTip
from util.command import CommandWrapper
from sn.model import GraphObject
from sn.model import Relation
#from sn.model.tgcommands import RmGraphObjectCommand
from sn.view.graphics.decorators import WrappingText, Selected, MarkerContainer,\
  Decorator
from util.attributeEditor import getEditedAttrsCommandObj, applyEditAttrsBox,\
  editAttrsBox
from sn.view.graphics.snCanvas import SNGView
from sn import snPrefs

import logging
logger:sn.SNLogger = sn.getLogger(__name__)

VATTRIBUTES =     { 'vis/shape'          : 'Rectangle', 
                    'vis/minSize'        : 30, 
                    'vis/maxSize'        : 1000, 
                    'vis/aspectRatio'    : 0.5, 
                    'vis/fillColor'      : 'white', 
                    'vis/borderColor'    : 'black',
                    'borderWidth'    : 1, 
                    'vis/borderSmooth'   : False, 
                    'vis/textColor'      : 'black', 
                    'vis/textModifiesBB' : False,
                    'vis/terminator1'    : "",
                    'vis/terminator2'    : "",
                    'vis/terminator3'    : "",
                    'vis/terminator4'    : "arrow",
                    'vis/lineColor'      : "black",
                    'vis/lineFillColor'  : "black",
                    'vis/lineType'       : "smooth",
                    'vis/lineWidth'      : 1,
                    }
                    
class Cache:
  '''
  An empty class to stuff cached attributes in. This includes all the visual attributes included
  in *VATTRIBUTES*, plus:
  
    - *_roles* : (*VRelation* only) A list of *str* names of the roles. 
    - *_<rolename>__filler*: (VRelation* only) List of fillers for each role name 
  '''
  
  def __init__(self, owner):
    '''
    ;param owner: [VObject]
    '''
    assert isinstance(owner, VObject)
    self._owner:weakref.ref = weakref.ref(owner)
    
  def refresh(self, attr:Optional[str]=None, verbose:bool=False):
    '''
    :param attr: [default=None] The name of the attribute to refresh; if *attr*
        is not already in the cache, it will be added.
        If None, refresh ALL attributes from *VATTRIBUTES* that are already in the cache.
    :param verbose: [default=False] If True, write out all the attributes from 
        *VATTRIBUTES* that are in the cache AFTER the update has occurred.
        
    Update *attr* from the model object.
    '''
    if self._owner() is None: return
    
    def refreshAttr(attr:str):
      setattr(self, attr, self._owner().modelObject[attr])
      
    if attr is None:
      for a in VATTRIBUTES:
        if hasattr(self, a):
          refreshAttr(a)
    else:
      refreshAttr(attr)
    if verbose:
      buf = ""
      for a in VATTRIBUTES:
        if hasattr(self, a):
          buf += f'{a}: {getattr(self, a)}\n'
      logger.info(buf)
      
  def __getitem__(self, key:str) -> Any:
    if not hasattr(self, key):
      self.refresh(key)
    return getattr(self, key, VATTRIBUTES.get(key, None))
      
  def __setitem__(self, key:str, val:Any) -> None:
    setattr(self, key, val)
    
  def __contains__(self, key:str):
    return key in VATTRIBUTES
      

class VObject(PRObject, Observer):
  '''
  An object that visually represents some object in a tygra *Model* that resides
  in a particular *SNCanvas* (which may include VObjects representing objects in
  several different tygra *Model* objects).
  
  The "size" and location of *VObject* considered to be that of the *self._shape*
  object, which in turn is controlled by the *self.boundingBox()* method. Note
  that decorators may be drawn outside of this bounding box.
  '''

  def __init__(self, view:SNGView, modelObject:GraphObject|str, 
               shape:Union[Any,str]="Rectangle", 
               x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None):
    '''
    :param view: The SNGView object that "owners" this VObject.
    :type view: SNGView
    :param modelObject: The object in the model that this object represents.
    :param shape: [Union[tygra.view.shapes.Shape, str], default=...shapes.Rectangle] The basic shape of this object.
    :param x: The upper left corner x coordinate
    :param y: The upper left corner y coordinate
    :param x1: The lower right corner x coordinate
    :param y1: The lower right corner y coordinate
    '''
    from sn.view.graphics.shapes import Shape
    from sn.view.graphics.vrelations import VRelation
    from sn.view.graphics.snCanvas import SNCanvas
    
    #check parameters
    assert isinstance(view, SNGView)
    if isinstance(modelObject, str):
      obj = PReference[GraphObject](modelObject)()
      assert isinstance(obj, GraphObject)
      modelObject = obj
    assert isinstance(modelObject, GraphObject)
    assert isinstance(shape, (Shape,str)), f'Expected Shape or str, but got "{shape.__class__.__name__}"'

    # set up the reference model object and it's cached details
    
    self._modelObject:GraphObject = modelObject if isinstance(modelObject, GraphObject) else PReference(modelObject)
    m = self.modelObject
    # these act as a cache, as it's relatively expensive to look up these values in the model object.
    self.cache:Cache = Cache(self)
    setattr(self.cache, 'name', m.name)
    for attrName, default in VATTRIBUTES.items():
      setattr(self.cache, attrName, m.get(attrName, default))

    if x  is None: x  = 0
    if y  is None: y  = 0
    if x1 is None: x1 = self.cache["vis/minSize"]
    if y1 is None: y1 = self.cache["vis/minSize"]/self.cache["vis/aspectRatio"]
    assert isinstance(x , (int, float)) and not isinstance(x , bool)
    assert isinstance(y , (int, float)) and not isinstance(y , bool)
    assert isinstance(x1, (int, float)) and not isinstance(x1, bool)
    assert isinstance(y1, (int, float)) and not isinstance(y1, bool)
      
    self._drawVersion:int = -1
    self._boundingBox = [x, y, x1, y1]
          
    #call super constructors
    PRObject.__init__(self, view)
    assert self._id is not None
    Observer.__init__(self)
    
    self.view:SNGView = view
    self.canvas:SNCanvas = view.canvas
    self._updatingFromAttrs = False
    self.tooltip = None
    self.markerDecoratorOffset=0
    self.dragInfo = None
    self._deleted = False
    self._hidden = False

    if isinstance(shape, str):
      try:
        shape = self.strToShape(shape)
      except Exception as ex:
        logger.warning(f'Unknown shape "{shape}" in {self.__class__.__name__} constructor for object {self}. Using "RoundedRectangle" (exception="{ex}"')
        shape = self.strToShape("RoundedRectangle")
    assert isinstance(shape, Shape)
    self._shape = shape
    self.tag = "ID"+str(self._id)
    
    self.relations:list[VRelation] = []
    'CAUTION: This list of referenced relations MUST have exactly a one-to-one relation with every connecting role of every connecting relation.'
    
    self.errors:list = []
    
    self.decorators:dict[str, Decorator] = dict()
    self.makeDecorators()
    
    self.modelObject.addObserver(self)
    # if _id is None: # being created by the user (not reading from persistent store)
    #   self._post__init__()
    
    self.canvas.after(0, lambda slf=self: [ \
                                  slf.canvas.freshPaint(), \
                                  slf.draw(), \
                                  slf.makeBindings()]) 
    
  # def _post__init__(self):
  #   self.canvas.freshPaint()
  #   self.draw()
  #   self.makeBindings()
  #   #self.adjustPos()
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("view", SNGView, lambda slf: cast(VObject, slf).view),
                     ParamInfo("modelObject", str, lambda slf: slf.modelObject.getPRef().tostring(slf.view.model))], #type: ignore[attr-defined]
            conKWArgs=[ParamInfo("x", int, lambda slf: slf.boundingBox()[0]), #type: ignore[attr-defined]
                       ParamInfo("y", int, lambda slf: slf.boundingBox()[1]), #type: ignore[attr-defined]
                       ParamInfo("x1", int, lambda slf: slf.boundingBox()[21]), #type: ignore[attr-defined]
                       ParamInfo("y1", int, lambda slf: slf.boundingBox()[3])], #type: ignore[attr-defined]
            postconSetters=[],
            finalSetters=[]
            )

  @property
  @override
  def name(self)->str:
    n = self.modelObject["name"]
    assert n is None or type(n) is str
    return "" if n is None else n
    
  @property
  def modelObject(self) -> GraphObject:
    '''
    :returns: The corresponding model object.
    :rtype: GraphObject
    :raises ReferenceError: if there is not corresponding model object (deleted?)
    :
    '''
    try:
      ret:GraphObject|None = self._modelObject
      assert isinstance(ret, GraphObject)
    except:
      logger.exception("Can't access model object.")
      ret = None
    if ret is None:
      raise ReferenceError("model object not found.")
    return ret
        
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

    
  def update(self, subject:Subject, *topics:tuple[str, tuple[Any, ...]]) -> None:
      """
      Receive update from subject.
      """
      rm = False # flag for checking if "rm" is one of the topics
      try: # if this is a deletion, the object will fail validation on access
        assert subject is self.modelObject
      # except DeletedObjectError as ex:
      #   #assert subject is self._modelObject() #access without the checks
      #   #subject = subject()
      #   rm = True
      #   rmEx = ex
      except Exception as ex:
        logger.exception(f'VObject.update({topics}): Failed to access subject: ')
        return
      #logger.info(f"VObject.update({subject}, {topics}): executing.")
      vChanged = False
      for topic in topics:
        topicName = topic[0]
        if topicName == "new attribute" or topicName == "mod attribute": # no point in changing an object we're removing!
          attname:str = topic[1][0]
          #attval = topic[2]
          if attname in VATTRIBUTES:
            self.cache.refresh(attname)
            vChanged = True
          else:
            logger.warning(f'{self.name}: Don\'t know what to do with update({self.modelObject.name}, {topic})')
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
        self.canvas.freshPaint()
        self.draw() 

  # ---- PERSISTENCE -----------------------------------------------------------

  @override
  @classmethod
  def getArgs(cls, elem:et.Element) -> Tuple[list[Any], dict[str, Any]]:
    container = elem.get("_container")
    ID = int(elem.get("id"))
    shape = elem.get('vis/shape')
    bb = literal_eval(elem.get('bb'))
    modelObject = PReference(elem.get("modelObject"), container.model)
    return [container], \
           {"modelObject":modelObject, 
            'vis/shape':shape, "x":bb[0] , "y":bb[1] , "x1":bb[2] , "y1":bb[3] ,
            "_id":ID}
  
  def serializeXML(self) -> et.Element:
    """
    Returns the representation of this object as an Element object.
    Implementors should call *super().serializeXML()* **first** as this top-level method
    will construct the Element itself.
    """
    elem:et.Element = PRObject.serializeXML(self)
    elem.set('modelObject', self._modelObject.getRelativeStringRefInContext(self.view.model))
    elem.set('vis/shape', self._shape.__class__.__name__)
    bb = self.boundingBox()
    elem.set('bb', f'[{int(bb[0])}, {int(bb[1])}, {int(bb[2])}, {int(bb[3])}]')
    return elem

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
    super().unserializeXML(elem)
    
  def validate(self) -> list[str]:
    '''
    Populates (or clears) the *self.errors* list.
    '''
    self.errors = []
    if self.modelObject is None:
      msg = "Model is missing"
      self.errors.append(msg)
    else:
      model:GraphObject = self.modelObject
      self.errors += model.validate()
    return self.errors
    

  ### GETTERS AND SETTERS ##############################################################

  def boundingBox(self, rect:list[int]=None, fast=False) -> list:
    '''
    Returns or sets the bounding box for the *VObject* in [minX, minY, maxX, maxY]
    form.  Checks *rect* for sanity and shifts it to be within *self.canvas.scrollRegion*.
    
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
      if rect[0] < 0: # make sure it's to the right of origin
        rect[2] = rect[2]-rect[0]
        rect[0] = 0 
      if rect[1] < 0: # make sure it's below origin
        rect[3] = rect[3]-rect[1]
        rect[1] = 0 
      if rect[2] > self.canvas.scrollRegion[2]:
        rect[0] = rect[2] - rect[0]
        rect[2] = self.canvas.scrollRegion[2]
      if rect[3] > self.canvas.scrollRegion[3]:
        rect[1] = rect[3] - rect[1]
        rect[3] = self.canvas.scrollRegion[3]
      self._boundingBox = rect.copy()
    
      if not fast:
        bb = self._boundingBox
        minX = self.cache['vis/minSize']
        if bb[2]-bb[0] < minX:
          bb[2] = bb[0]+minX
        aspectRatio = self.cache['vis/aspectRatio'] # could aspaectRation be 0???
        minY = (bb[2]-bb[0]) * aspectRatio
        if bb[3]-bb[1] < minY:
          bb[3] = bb[1]+minY
          
        maxX = self.cache["vis/maxSize"]
        if bb[2]-bb[0] > maxX:
          bb[2] = bb[0]+maxX
        maxY = (bb[2]-bb[0]) * aspectRatio
        if bb[3]-bb[1] > maxY:
          bb[3] = bb[1]+maxY
      
      # self.canvas.freshPaint()
      # self.draw()
      self.dirty()

    return self._boundingBox

    
  def selected(self, val:Optional[bool]=None, _multi:bool=False):
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

  def shape(self, c:str=None):
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
      self.dirty()
    return type(self._shape).__name__ if self._shape is not None else None
  
  ## BINDINGS ####################################################################
  
  def makeBindings(self):
    bindObj = self.tag #bindObj
    tag_bindRightMouse(self.canvas, bindObj, self.onRightMouse)
    self.canvas.tag_bind(bindObj, "<Button-1>", self.onButton_1)
    self.canvas.tag_bind(bindObj, "<B1-Motion>", self.onB1_Motion)
    self.canvas.tag_bind(bindObj, "<B1-ButtonRelease>", self.onB1_ButtonRelease)
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
    if self.tooltip is not None:
      self.tooltip.delete()
      
  def onRightMouse(self, event):
    """Creates and displays the node specific menu at the clicked location."""
    self.canvas.addEventHandled(event)
    m = self.makeMenu()
    m.post(event.x_root, event.y_root)
    return 'break'

  def onButton_1(self, event): #get initial location of object to be moved
    """
    The mouse clicked on this node, so begin a mouse event capture. We will
    decide on if it's just a node move or a selection toggle in *self.onB1_Motion()*
    and *self.onB1ButtonRelease()*.
    """
    self.canvas.addEventHandled(event)
    #print(f'onButton_1() event x={event.x}, y={event.y}, selected={self.selected()}')
    winX = event.x - self.canvas.canvasx(0) # adjust for canvas offset
    winY = event.y - self.canvas.canvasy(0)
    r = self.boundingBox()
    self.dragInfo = (r[0], r[1], winX, winY, False) # x,y,no-drag-motion-event
    self.old_suppressLocalLayout = self.view.suppressLocalLayout()
    self.view.suppressLocalLayout(True)
    return 'break'

  def onB1_Motion(self, event):
    """
    The mouse is moving while being captured by this node, so if we had clicked to start
    accepting events, just move the node to track the event, updating *self.dragInfo*.
    """
    
    if self.dragInfo != None:
      self.canvas.addEventHandled(event)
      winX = event.x - self.canvas.canvasx(0) # adjust for canvas offset
      winY = event.y - self.canvas.canvasy(0)
      dX = winX - self.dragInfo[2]
      dY = winY - self.dragInfo[3]
      #print(f'onB1_Motion() event({event.x},{event.y}), d=({dX},{dY}), selected={self.selected()}')
      self.canvas.freshPaint()
      if self.selected():
        for n in self.view.selected:
          n.moveBy(dX, dY, adjustPos=False, fast=False)
      else:
        self.moveBy(dX, dY, adjustPos=False, fast=False)
      # reset the starting point for the next move
      self.dragInfo = (self.dragInfo[0], self.dragInfo[1], winX, winY, True) # x,y,drag-motion-event-occurred
      return 'break'
    #else:
      #print(f'non-drag onB1_Motion() event x={event.x}, y={event.y}')


  def onB1_ButtonRelease(self, event): #reset data on release
    """
    Button one was released. If it was a drag, it was a move, and everything is fine except
    we call self.adjustPos() which may resolve overlap conflicts. If it was a click (no
    intervening <B1_Motion> events), toggle the selection state of the node.
    """
    #from sn.view.vcommands import MoveCommand
    if self.dragInfo != None:
      self.canvas.addEventHandled(event)
      if self.dragInfo[4]: # indicated there was a <B1_Motion> event, ie: this was a drag: wrap up a move.
        # self.view.suppressLocalLayout(self.old_suppressLocalLayout)
        # if False: #self.canvas.fieldsLayoutObj.active:
        #   bb = self.boundingBox()
        #   x, y, _, _ = bb 
        #   if self.overlaps(bb, spacing=[20,10]):
        #     self.canvas.fieldsLayoutObj(self)
        # else:
        #   x, y = self.adjustPos()
        # #record a move command
        # self.canvas.doList.do(MoveCommand(self, (x, y), (self.dragInfo[0], self.dragInfo[1]), suppressFirst=False))
        bb = self.boundingBox()
        self.canvas.context.move(self, bb[0], bb[1])
      else: # this was a click, not a drag: toggle the selection state
        s = event.state
        self.selected(not self.selected(), _multi=s_CMD(s) or s_SHIFT(s)) # toggle selected
      self.dragInfo = None
      return 'break'
      # TODO: add updating the boundingBox.

  ## MENUS ####################################################################
  
  def makeMenu(self) -> tk.Menu:
    m = tk.Menu(self.canvas)
    if True: #app.DEBUG_MENUS:
      m.add_command(label=f'#{self._id} -> {self.modelObject.name}', state=tk.DISABLED)
      m.add_separator()
    editable = self.canvas.isModelEditor()
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
    if snPrefs.get("debug", False):
      m.add_separator()
      m.add_command(label="validate", command=lambda o=self: \
                                                (n := len(o.validate()), \
                                                 logger.info(f'"{o.modelObject.name}": No errors detected.') if n==0 else logger.warning(f'"{o.modelObject.name}": detected {n} errors.'), \
                                                 o.canvas.freshPaint(), 
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

  def addModelEditingMenuItems(self, menu:tk.Menu):
    disabled = (self.modelObject.isSystemObject() \
                and not snPrefs.get("view_allowEditingSystemObjects", storeDefault=False)) \
               or not self.canvas.isModelEditor() \
               or self.modelObject.isIndividual() and isinstance(self.modelObject, Relation)
    remote = self.view.model != self.modelObject.model
    menu.add_command(label=f"{'show' if disabled else 'edit'} attributes", \
                     command=lambda disabled=disabled: self.onEditAttributes(disabled=disabled or remote))    
    if self.modelObject.isType():
      menu.add_command(label='make new instance', command=lambda: self.canvas.doNewNodeCommand(parent=self.modelObject, individual=True))
      menu.add_command(label='make new subtype', command=lambda: self.canvas.doNewNodeCommand(parent=self.modelObject, individual=False))
      menu.add_separator()
    if not disabled:
      relTypesMenu = tk.Menu()
      for r in [r for r in self.view.model.values() if isinstance(r, Relation) and r.isType()]:
          relTypesMenu.add_command(label=r.name, command=lambda r=r: self.canvas.makeRelationFrom(self, r))
      menu.add_cascade(label="make relation to...", menu=relTypesMenu)
      menu.add_command(label="delete from model", state=tk.DISABLED if remote else tk.NORMAL, 
                       command=lambda: self.canvas.doList.do(
                         CommandWrapper(RmGraphObjectCommand(self.view.model, self.modelObject),
                                        setup=self.canvas.setCatchNewObjects, 
                                        teardown=self.canvas.resetCatchNewObjects)))
      menu.add_separator()
    
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
    expMenu = tk.Menu()
    expMenu.add_command(label="expand all, 1 level" , command=lambda: self.canvas.doList.do(ExpandCommand(self)))
    expMenu.add_command(label="expand all, 2 levels", command=lambda: self.canvas.doList.do(ExpandCommand(self, levels=1)))
    expMenu.add_command(label="expand all, 3 levels", command=lambda: self.canvas.doList.do(ExpandCommand(self, levels=2)))
    expMenu.add_command(label="expand all, 4 levels", command=lambda: self.canvas.doList.do(ExpandCommand(self, levels=3)))
    menu.add_cascade(menu=expMenu, label="expand")
    menu.add_command(label="remove from view", 
                     command=lambda: self.canvas.doList.do(RemoveFromViewCommand(self)),
                     state="normal" if self.isHidable() else "disabled")
         
  @override
  def dirty(self):
    self.canvas.dirty = True
    
  def onEditAttributes(self, disabled:bool=False):
    if disabled:
      editAttrsBox(self.canvas, self.modelObject, title=str(self.modelObject), disabled=True)
    else:
      applyEditAttrsBox(self.canvas, self.modelObject, title=str(self.modelObject)) #f'{self.modelObject.idString}: "{self.modelObject.name}"')

  def tooltipFunc(self) -> str:
    tip = ""
    line = "\u2594"*18
    try:
      tip = self.modelObject.name
      if snPrefs.get("debug", storeDefault=False):
        tip += f' ({self._id})'
      note = self.modelObject.get("note", None)
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
  
  def makeDecorators(self):
    self.decorators["text"] = WrappingText(self)
    self.decorators["markers"] = MarkerContainer(self)
    # try:
    #   if self.modelObject.isType() or self.modelObject.isSystemObject:
    #     self.decorators["typeMarker"] = TypeMarker(self)
    # except Exception as ex:
    #   self.canvas.logger.write(f"failed to make 'typeMarker': {type(ex).__name__}: {ex}.", level="warning", exception=ex)

  def strToShape(self, name):
    from sn.view.graphics.shapes import Shape
    cls = Shape.getShapeClass(name)
    if cls is not None:
      return cls(self)
    raise TypeError("VNode.strToShape(): Do not know shape class '"+name+"'.")

  def notifyDecoratorDeletion(self, decorator):
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

  ### DRAWING ##################################################################
  
  def draw(self, fast=False, **kwargs):#, rect=None):
    if self._drawVersion >= self.canvas._drawVersion: return
    else: self._drawVersion = self.canvas._drawVersion
    self._shape.draw(fast=fast, **kwargs) #self["boundingBox"])#rect)
    self.markerDecoratorOffset=0
    for d in self.decorators.values(): # TODO: might need to concern ourselves about draw order here
      d.draw(fast=fast)

  def moveTo(self, x, y, allowOverScrollRegionSE=False, adjustPos=True, fast=False):
    """ 
    Move so that the NW corner is on (x,y), informing all the decorators and 
    relations
    """
    bb = self.boundingBox(fast=fast)
    if bb[0] == x and bb[1] == y: # we haven't actually moved, so do nothing.
      return
    sr = self.canvas.scrollRegion
    if x<sr[0]: x = sr[0]
    if y<sr[1]: y = sr[1]
    if not allowOverScrollRegionSE:
      if x+bb[2]-bb[0]>sr[2]: x = sr[2]-(bb[2]-bb[0])
      if y+bb[3]-bb[1]>sr[3]: y = sr[3]-(bb[3]-bb[1])
    self.boundingBox([x, y, x+bb[2]-bb[0], y+bb[3]-bb[1]])
    if adjustPos:
      #The traditional way 
      self.adjustPos(fast=fast)
      
      # use the field animation layout
      # if hasattr(self.canvas, "fieldsLayoutObj") and self.canvas.fieldsLayoutObj is not None and self.overlaps(spacing=[20, 10]):
      #   self.canvas.fieldsLayoutObj.nextFrame(activeNodes=[self])
      
    self.canvas.freshPaint()
    self.draw()
    self.dirty()
    if not fast:
      for r in self.relations:
        r.notifyNodeMove(self)
    
      
  def moveBy(self, dx, dy, allowOverScrollRegionSE=False, adjustPos=True, fast=False):
    bb = self.boundingBox(fast=fast)
    x = bb[0]+dx
    y = bb[1]+dy
    self.moveTo(x, y, allowOverScrollRegionSE, adjustPos=adjustPos, fast=fast)
    
  def moveToCenterOn(self, x, y, adjustPos=True, fast=False):
    bb = self.boundingBox(fast=fast)
    width = abs(bb[2]-bb[0])
    height = abs(bb[3]-bb[1])
    x = int(x - (width/2))
    y = int(y - (height/2))
    self.moveTo(x, y, adjustPos=adjustPos, fast=fast)

  def centerPt(self):
    """Gets the center point of this shape."""
    r = self.boundingBox()
    return (int((r[0]+r[2])/2), int((r[1]+r[3])/2))

  def containsPt(self, pt):
    return pointInPoly(pt, self._shape.points())
    
  def adjustPos(self, aggressive:bool=False, fast=False) -> (int, int):
    if fast:
      bb = self.boundingBox(fast=fast)
      return bb[0], bb[1]
    
    # use a regular layout  
    layout = self.view.localLayout
    if layout is not None:
      for r in self.relations:
        layout(r, aggressive=aggressive)
      layout(self, aggressive=aggressive)
    r = self.boundingBox(fast=fast)
    
    return r[0], r[1]
    
  def overlaps(self, bb:list=None, others:Iterable=None, spacing:Optional[list]=None) -> list: #list[VObject]:
    ""
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
             filter:Optional[Callable[[Any, Relation], bool]]=lambda _vn, _mr: True, 
             expand=0):
    """
    :param filter: Optional[Callable[[Self, Relation], bool]] A function *selfxRelation->bool*
        where that relation will only be expanded if the function returns *True* 
    :param expand: [Optional[int], default=None] The number of hops to expand.
    :return: A set of all the VObjects created during the expansion.
    """
    # Iterate all the relations connected to this, collecting all the undisplayed ones in *rels*
    # and also recurse on any displayed ones if *expand* > 0
    rels:list[Relation] = []
    for mRelr in self.modelObject.referencers:
      mRel = mRelr()
      if not self.canvas.categories.isCategory(mRel, self.canvas.hiddenCategories):
        if filter(self, mRel):
          vRel = self.canvas.findViewObjectForGraphObject(mRel)
          if vRel is None:
            rels.append(mRel)
          elif expand > 0:
            vRel.expand(filter=filter, expand=expand-1)
            
    # *rels* contains the unexpanded model *Relations*, so create a VRelations for
    # each of them.
    if len(rels) > 0:
      bb = self.boundingBox()
      x = bb[2] + 50
      y = len(rels) * 25
      for r in rels:
        self.canvas.makeViewObjectForGraphObject(r, atPoint=[x,y], expand=expand, filter=filter)
        y += 50

  ### RELATIONS ########################################################################

  def addRelation(self, relation): #, direction):
    from sn.view.graphics.vrelations import VRelation
    if not isinstance(relation, VRelation):
      raise TypeError("VNode.addRelation(): first argument must be of type VRelation.")
    self.relations.append(relation) #(relation, direction))
#     relation.model.addObserver(self) # observer the relation MODEL

  def notifyRelationDeletion(self, relation):
    """ This is the notification from removal of a relation VIEW. """ 
    for r in self.relations:
      if r == relation:
        self.relations.remove(r)
        break
        
  def setHidden(self, hide:bool=True):
    '''
    "Unhooks" ("rehooks") from the view's list of objects and sets the graphics objects to
    state="hidden" ("normal"). Note that Nodes' .relations and Relations' arcs are not
    updated.  
    '''
    if hide == self._hidden:
      return
    if hide:
      if not self.isHidable():
        logger.error("Cannot hid an object that has any non-individual relations.")
      PRDb.remove(self.view, self._id) # both PRDb and SNCanvas have __setitem__()
      self.canvas.itemconfigure(self.tag, state="hidden")
    else:
      PRDb.__setitem__(self.view, self._id, self) # both PRDb and SNCanvas have __setitem__()
      self.canvas.itemconfigure(self.tag, state="normal")
    self.dirty()
    
  def isHidden(self):
    return self._hidden
    
  def isHidable(self) -> bool:
    '''
    An object is "hidable" only if ALL it's relations are instances.
    '''
    for r in self.relations:
      if r.modelObject.isType() and not r.isHidden():
        return False 
    return True

  ### Debugging support ################################################################
  
  @override
  def __str__(self) -> str:
    return self.tostring()
  
  @override
  def tostring(self, relativeTo:SNGView|None=None) -> str:
    name = self.modelObject.getLocal("name", None)
    if name is None:
      name = f'{UP_ARROW}"{self.modelObject.get("name")}"'
    return f'{self.__class__.__name__}({name}, {self.getPRef().tostring(relativeTo)}, {self.modelObject.tostring(self.view.model)})'
  
  def __repr__(self):
    return self.__str__()
  
  # def __hash__(self):
  #   return hash(self.idString)
    

