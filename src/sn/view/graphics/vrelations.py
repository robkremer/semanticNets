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
"""
vrelations.py

Implements VRelation and VIsa classes.

  .. inheritance-diagram:: VRelation VIsa
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

.. codeauthor:: Rob Kremer <robkremer@me.com>

---------------
"""

import tkinter as tk
import xml.etree.ElementTree as et
from ast import literal_eval
from typing import Any, Optional, Union, Tuple, List, Dict, Iterable, \
  override
from types import NoneType

from dataclasses import dataclass
import weakref

import sn
from sn import snPrefs
from util.utils import flattenPairs, midpoint
from util.attribute import AttributedObject
from util.persistence.pRef import PRDb, PReference
from util.persistence.serialize import InstantiationInfo, ParamInfo,\
  PropertyInfo
from util.attributeEditor import applyEditAttrsBox # @UnresolvedImport
from util.abstractGraph import AGRelation
from sn.model.model import GraphObject, Relation, IsaIndividual
from sn.view.graphics.vobjects import VObject
from sn.view.graphics.connectors import drawSmoothConnector, ConnectorIDs,\
  drawStraightConnector, ConnectorTerminators
#TODO: remove the "#@" when attributeEditor get fixed up.

import logging
logger:sn.SNLogger = sn.getLogger(__name__)
  
ROLE_VATTRIBUTES = {'vis/lineColor': 'black',
                    'vis/fillColor': '',
                    'vis/lineWidth': 1,
                    'nearEndShape': '',
                    'farEndShape': '',
                    }

    
class VRelation(VObject, AGRelation):
  '''
  Implements the visual representation of model *Relation*. The roles are taken
  for the *Relation* object exclusively.  
  
  Adds to self.cache (from VObject):
  
    - '._roles': List of role names
    - '._<rolename>__filler': List of fillers for each role name 
  '''

  granularity = 1  # the accuracy to which we should calculate endpoints
  
  ### CONSTRUCTOR AND HELPERS ##########################################################

  def __init__(self, view:SNGView, # type: ignore[name-defined] # @UndefinedVariable
        modelObject:Relation|str, 
        typ:Relation|None=None,
        shape:Union[Any, str]="Oval",
        x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None,
        floating:Optional[bool]=None,
        _bb:Optional[list]=None):
    """  
    :param canvas: [Required] The TGView object for this object.
    :param modelObject: [Required if creating a view object only (*_id* is *None*)]
      The *Relation* object to server as the modelObject for this view object.
    :param typ: [Required if creating a modelObject object (*_id* is *None* and 
      *modelObject* is *None*)] A *Relation* used to create an ISA parent relation from
      the new *Relation*. 
    :param shape: [Union[tygra.view.shapes.Shape, str], default=...shapes.Rectangle] The basic shape of this object.
    :param x: The upper left corner x coordinate
    :param y: The upper left corner y coordinate
    :param x1: The lower right corner x coordinate
    :param y1: The lower right corner y coordinate
    :param floating: [Default True] weather or not the relation should be floating.
      Normally ONLY used when unserializing.
    
    This class has to take special measures to avoid an address fault because Relations
    may reference other relations, so there is no way to ensure that toNode and fromNode
    idString-to-addresses have already be registered.  To get around that, if there had
    been an address fault in *self.getArgs()*, it will have put the str isString in place
    of the pointer.  The pointer(s) will be properly instantiated (etc) on a second 
    pass when the owner container calls the *self._post__init__()* method.
    """
    if isinstance(modelObject, str):
      try:
        obj = PReference[GraphObject](modelObject)(relativeTo=view.model)
      except KeyError:
        obj = None
      modelObject = obj # type: ignore[assignment]
    assert isinstance(modelObject, (Relation,NoneType)), \
          f"Bad modelObject param in VRelation.__init__(): type {modelObject.__class__.__name__}"
   
    if typ is not None:
      if not isinstance(typ, Relation):
        raise TypeError(f'VRelation._init_(): "typ" argument a subtyp of Relation object; got object of class {typ(typ).__name__}.')

    # self.init = {"typ": typ, "_bb": _bb}  # pass these parameters to self for _post__init__()      

    # *VRelation* inherits from both *VObject* and *AGRelation*, which both
    # in turn share *AGObject* as a common ancestor -- the same diamond shape
    # as *sn.model.model.Relation* (see its __init__ for the full
    # explanation). A single cooperative super().__init__() call, instead of
    # the old separate VObject.__init__()/AGRelation.__init__() calls, lets
    # the MRO run AGObject.__init__() (and hence PRObject.__init__(), which
    # registers this object with *view*) exactly once instead of once per
    # inheritance path.
    super().__init__(view, x=x, y=y, x1=x1, y1=y1, shape=shape, modelObject=modelObject, src=None, dst=None)
    assert isinstance(self.modelObject, (Relation,NoneType))
 
    # Done by AbstractGraph
    # if not self.view.reading: # can't do an expansion while things aren't settled yet...
    #   self._connect()
          
    self._floatingAnchor = True if floating is None else floating
    # self._redrawExecuting = False
    
    self.canvas.after(0, lambda slf=self: slf.reposition(aggressive=True)) #type: ignore[misc]
    # self.canvas.freshPaint()
    # self.draw()
    self.connectInfo:ConnectorIDs|None = None
          
  # def _post__init__(self):
  #   """
  #   If one or more of the terminal nodes' models had been deleted in the model, then
  #   we will fail to get the address of the terminal nodes, in which case, we will throw
  #   a KeyError exception.
  #   """
  #   if self.modelObject is not self.modelObject.container.relation:
  #     self._connectRoles()
  #   super()._post__init__()
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    sup = VObject.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=sup.conArgs,
            conKWArgs=sup.conKWArgs+[ParamInfo("floating", bool, lambda slf: slf._floatingAnchor)], #type: ignore[attr-defined]
            postconSetters=sup.postconSetters,
            finalSetters=sup.finalSetters)

  @override
  def makeModelObjectSubtype(self, individual:bool) -> None:
    self.view.context.new_relation(self.modelObject, name="", individual=individual, type=not individual, model=self.view.model) # type: ignore[arg-type]

  def connect(self, source:VObject|None=None, destination:VObject|None=None):
    '''
    Determine the connecting objects from self.modelObject, and invoke the super version
    with from that.
    '''
    if self.view.reading or self.modelObject is None:
      return
    assert isinstance(self.modelObject, Relation)
    if source is None and self.modelObject.src is not None:
      source = self.view.makeViewObjectForGraphObject(self.modelObject.src)
      if self in source._outgoing:
        raise RuntimeError(f'Reinserting self ({self}) into {source}.')
    if destination is None and self.modelObject.dst is not None:
      destination = self.view.makeViewObjectForGraphObject(self.modelObject.dst)
      if self in destination._incoming:
        raise RuntimeError(f'Reinserting self ({self}) into {destination}.')
    super().connect(source, destination)
   
    
  # def _connectRoles(self):
  #   '''
  #   Establishes all the connectors for the VRelation, both in the view and in the
  #   cache, based on it's referent *Relation* in the model by:
  #
  #     - makes sure every connected VOjbect is in the view
  #     - adds *self* to the relations of those VObjects
  #     - instantiates self.cache._roles to the list of roles in the model object
  #     - instantiates all self.cache._<roleName>__filler to the list of fillers for each role name
  #   '''
  #   # roles = []
  #   # for roleName, roleObj in self.modelObject.roles.items():
  #   #   roleFillers = roleObj['filler']
  #   #   roles.append(roleName)
  #   #   nodes = []
  #   #   for roleFiller in roleFillers:
  #   #     mObj = roleFiller()  # PReference -> ModelBbject
  #   #     node = self.canvas.makeViewObjectForGraphObject(mObj)
  #   #     # nodes.append(weakref.ref(node))
  #   #     nodes.append(node)
  #   #     node.addRelation(self)
  #   #   setattr(self.cache, f'_{roleName}__filler', nodes)
  #   snode = self.view.makeViewObjectForGraphObject(self.modelObject.src)
  #   self.src = snode
  #   snode.dst = self
  #
  #   # setattr(self.cache, '_roles', roles)
    
  # def register(self):
  #   self.canvas.relations.append(self)

  # def makeDecorators(self):
  #   from sn.view.decorators import Text, TypeMarker
  #   self.decorators["text"] = Text(self, text=self.modelObject.name, fill="blue")
  #   if self.modelObject.get("type") or self.modelObject.isSystemObject():
  #     self.decorators["typeMarker"] = TypeMarker(self)

  ### DESTRUCTOR ########################################################################

  def _delete(self):
    """ Low-level delete that doesn't take care of notifications."""
    # for roleinfoList in self.roles.values():
    #   for r in roleinfoList:
    #     r.eraseView(self.canvas.canvas)
    if self.connectInfo:
      self.connectInfo.deleteAll(self.canvas)
    super().delete()

  def delete(self):
    """
    Removes this Relation:
      remove it from the display
      removing it from canvas's list
      notify the relevant nodes
    """
    for node in (self.src, self.dst):
      try:
        if node is not None:
          node.notifyRelationDeletion(self)
      except:
        pass
    self._delete()
    
  def _getConnectedVObjects(self) -> List[VObject]:
    ret = []
    roles = self.cache._roles if hasattr(self.cache, "_roles") else []
    for roleName in roles:
      for obj in getattr(self.cache, f'_{roleName}__filler'):
        ret.append(obj)
    return ret
    
  def validate(self) -> list[str]:
    """
    :return: The list of errors or inconsistencies in this *VNode*. 
    
    Validate the VNode, print any violations to *self.tgmodel.logger*
    and return the number of violations.
    
    .. note:: Validation can only take place AFTER the
       GraphObject is fully constructed with all its ISA relations.
       
    This method checks:
    
    - There exists a model object (*self.model* is not *None*\\ ).
    - The model is valid (calls *self.modelObject.validate()*\\ ).
    """
    self.errors = super().validate()
    
    # for roleName in (self.cache._roles if hasattr(self.cache, "_roles") else []):
    #   fillers = getattr(self.cache, f'_{roleName}__filler')
    #   for filler in fillers:
    #     if isinstance(filler, PReference):
    #       filler = filler()
    #
    #     if not isinstance(filler, VObject):
    #       self.errors.append(f'{roleName}.filler containers item of type {filler.__class__.__name__}; should be a subtype of VObject.')
    #     else:
    #       if self.modelObject is not None and not isinstance(self.modelObject, Relation):
    #         self.errors.append(f'self.modelObejct is of type "{self.modelObject.__class__.__name__}", but it should be of type Relation.') 
    #       elif filler.modelObject not in map(lambda x: x(), self.modelObject[_toFillerAttrName(roleName)]):
    #         self.errors.append(f'the filler "{str(filler.modelObject)}" at {id(filler.modelObject)} of role "{roleName}" does not occur in the corresponding model object ({str(self.modelObject[_toFillerAttrName(roleName)])} ({str(list(map(lambda x: id(x()), self.modelObject[_toFillerAttrName(roleName)])))})).') 
          
    # if errCount == 0:
    #   if 'error' in self.decorators:
    #     self.removeDecorator('error')
    #     self.draw()
    # elif 'error' not in self.decorators:
    #   self.decorators['error'] = ErrorMarker(self)
    #   self.draw()
    return self.errors
  
  # ### ATTRIBUTES #######################################################################
  #
  # def notifyAttrChanged(self, attrsObj:AttributedObject, name:str, value:Any):
  #   super().notifyAttrChanged(attrsObj, name, value)

  ### DECORATORS #######################################################################

  ### GETTERS AND SETTERS ##############################################################
  
  def floating(self, value:Optional[bool]=None):
    # if self.modelObject['type']: return False # type relations never float
    if value != None:
      oldVal = self._floatingAnchor
      self._floatingAnchor = value
      if oldVal != self._floatingAnchor:
        self.reposition()
    return self._floatingAnchor

  ### DRAWING ##########################################################################

  @dataclass
  class RoleInfo:
    vobject:weakref.ref  # VObject
    nearPt:Optional[Tuple[int, int]] = None
    farPt:Optional[Tuple[int, int]] = None
    lineID:Optional[int] = None
    nearShapeID:Optional[int] = None
    farShapeID:Optional[int] = None
    labelID:Optional[int] = None
    mark:bool = False
    
    def eraseView(self, canvas):
      if self.lineID is not None: 
        canvas.delete(self.lineID)
        self.lineID = None
      if self.nearShapeID is not None: 
        canvas.delete(self.nearShapeID)
        self.nearShapeID = None
      if self.farShapeID  is not None: 
        canvas.delete(self.farShapeID)
        self.farShapeID = None
      if self.labelID  is not None: 
        canvas.delete(self.labelID)
        self.labelID = None    
    
  # def updateRoleRelatedVObjects(self) -> dict[str, list[RoleInfo]]:
  #   '''
  #   :return: *self.roles*, which is a dict of <rolename> to a list of RoleInfo, which is a VObject with its
  #       near- and far- connection points, etc
  #
  #   Collects the info from the model object and updates *self.roles*, adding any
  #   new roles or objects connected with roles, updates the position of any
  #   existing ones, and removeing any deleted roles or objects connected.
  #   '''
  #   for rilist in self.roles.values():
  #     for ri in rilist:
  #       ri.mark = False
  #   showInheritedRoles = snPrefs.get("gui/showInheritedRoles", storeDefault=False)
  #   #for k, v in   self.modelObject.items() if showInheritedRoles else self.modelObject._attrs.items():
  #   for k, v in   self.modelObject.items() if showInheritedRoles else self.modelObject.get.items():
  #     if k.endswith(".filler"):  # iterating the rolenames
  #       if not showInheritedRoles:
  #         v = v.value
  #
  #       roleName = k[1:-7]
  #
  #       # add the roleName to self.roles if it isn't already there
  #       if roleName not in self.roles:
  #         self.roles[roleName] = []
  #
  #       # get all the referenced VObjects
  #       vObjs = []
  #       for ref in v:
  #         vObjs.append(self.canvas.makeViewObjectForGraphObject(ref()))
  #
  #       # mark the objects in self.roles so we don't delete it
  #       for o in vObjs:
  #         role = [r for r in self.roles[roleName] if r.vobject() is o]
  #         if len(role) == 0:  # add the object to the role if necessary
  #           role = VRelation.RoleInfo(weakref.ref(o))
  #           self.roles[roleName].append(role)
  #         else:
  #           assert len(role) == 1
  #           role = role[0]
  #         role.mark = True
  #
  #       # delete any outdated items from self.roles (removing the graphics from the canvas) 
  #       for r in self.roles[roleName]:
  #         if r.mark:
  #           r.mark = False
  #         else:  # delete from this role's list
  #           r.eraseView(self.canvas.canvas)
  #           self.roles[roleName].remove(r)
  #
  #   self._findPoints(self.roles)
  #   return self.roles
  #
  # def _findPoints(self, roles:dict[str, list[RoleInfo]]):
  #   '''
  #   :param roles: a dict of list of RoleInfo to fill out the RoleInfo points information
  #     based on the each RoleInfo's vobject.
  #   :return: The parameter with the points info filled out.
  #
  #   The points info that this method fills out accounts for multiple roles that 
  #   refer to the same *VObject* by shifting the endponts, by 4 in the x or y 
  #   direction to avoid overdrawing lines.
  #   '''
  #   objCounts:dict[int, int] = dict()  # dict[id:count] count the objects we are drawing to so that we can avoid drawing lines over one another
  #   for infoList in roles.values():
  #     for info in infoList:  # count this object so that we can avoid drawing lines over one another
  #       if info.vobject() is None:  # TODO: Need to delete this component...
  #         pass
  #       if id(info.vobject()) in objCounts:
  #         objCounts[id(info.vobject())] += 1
  #       else:
  #         objCounts[id(info.vobject())] = 1 
  #
  #       info.nearPt, info.farPt = self.findEndPoints(self, info.vobject())
  #
  #       count = objCounts[id(info.vobject())]
  #       if count > 0:
  #         if abs(info.nearPt[0] - info.farPt[0]) > abs(info.nearPt[1] - info.farPt[1]): 
  #           info.nearPt = (info.nearPt[0]        , info.nearPt[1] + 4 * count)
  #           info.farPt = (info.farPt [0]        , info.farPt [1] + 4 * count)
  #         else:
  #           info.nearPt = (info.nearPt[0] + 4 * count, info.nearPt[1])
  #           info.farPt = (info.farPt [0] + 4 * count, info.farPt [1])
  
  def parseEndShape(self, shape:str) -> Optional[Tuple[str, list]]:
    '''
    :param shape: A shape string of the form **{** circle(<diameter>) **|** arrow(<len>,<hypotenuse>,<close>) **}**.
    :return: *None* or (str, list[int]), where if str is "circle", list is len 1, or if str is "arrow" list is len 3. 
    '''
    if shape is None or shape == "":
      return None
    sep = len(shape)
    for i, c in enumerate(shape):
      if not (c.isalpha() or c == ' '): 
        sep = i
        break
    shapeName = (shape[:sep]).strip().lower() 
    if shapeName not in ['arrow', 'circle']:
      logger.warning(f'VRelation.drawEndShape(): Unknown shape name: "{shape}"; assuming no end shape.')
      return None
    try:
      args = literal_eval(shape[sep:])
      if not isinstance(args, Iterable):
        args = [args]
      for a in args:
        assert isinstance(a, (int, float))
    except:
      logger.warning(f'VRelation.drawEndShape(): Malformed end shape arguments: "{shape}"; using defaults.')
      args = []
    return shapeName, args

  # def drawEndShape(self, shape:str, line:list, ID:int , lineColor:str, fillColor:str) -> Optional[int]:
  #   '''
  #   :return: the ID of the drawn shape (if any)
  #   '''
  #   shape = self.parseEndShape(shape)
  #   if shape is None:
  #     if ID is not None:  # need to delete the old end shape
  #       self.canvas.canvas.delete(ID)
  #     return None
  #   shapeName, args = shape
  #
  #   if shapeName == "circle":
  #     if ID is not None and self.canvas.canvas.type(ID) != "oval":  # need to delete the old none-oval and draw a new oval
  #       self.canvas.canvas.delete(ID)
  #       ID = None
  #
  #     # fill in defaults
  #     diam = 5 if len(args) == 0 else args[0]
  #     radius = diam / 2.0
  #
  #     if ID is None:  # new circle
  #       ID = self.canvas.canvas.create_oval(
  #           self.view.viewToWindow([line[2] - radius, line[3] - radius, line[2] + radius, line[3] + radius]),
  #           fill=fillColor, outline=lineColor, tags=[self.tag])
  #     else:  # repaint existing circle
  #       self.canvas.canvas.coords(ID,
  #           self.view.viewToWindow([line[2] - radius, line[3] - radius, line[2] + radius, line[3] + radius]))
  #       self.canvas.canvas.itemconfigure(ID, fill=fillColor, outline=lineColor)
  #
  #     # TODO: fill this in
  #
  #   elif shapeName == "arrow":
  #     if ID is not None and self.canvas.canvas.type(ID) != "line":  # need to delete the old none-oval and draw a new oval
  #       self.canvas.canvas.delete(ID)
  #       ID = None
  #
  #     # fill in defaults
  #     # defArgs = [8, 10, 3]
  #     n = len(args)
  #     if n == 0:
  #       args = [8, 10, 3]
  #     elif n == 1:
  #       args = [args[0], args[0] * 1.25, args[0] * 0.375]
  #     elif n == 2:
  #       args = [args[0], args[1], args[0] * 0.375]
  #     elif n > 3:
  #       args = args[:3]
  #
  #     if ID is None:  # new line
  #       ID = self.canvas.canvas.create_line(
  #           self.view.viewToWindow(line),
  #           fill=lineColor, tags=[self.tag], arrow=tk.LAST, arrowshape=tuple(self.view.viewToWindow(args)))
  #     else:  # repaint existing line
  #       self.canvas.canvas.coords(ID,
  #           self.view.viewToWindow(line))
  #       self.canvas.canvas.itemconfigure(ID, fill=lineColor, arrow=tk.LAST, arrowshape=tuple(self.view.viewToWindow(args)))
  #
  #   return ID
    
  def draw(self, fast=False, **kwargs):
    if self._drawVersion >= self.view._drawVersion: 
      return
    super().draw(fast=fast, **kwargs)
    if self.modelObject is None:
      return
    # self.reposition(suppressDraw=True)
    if self.modelObject.isSystemObject() and self.modelObject.name == "relation":
      return
    # self.updateRoleRelatedVObjects()
    # for role, infoList in self.roles.items():
    #   if not fast:
    #     color = self.modelObject.get(f"{role}.lineColor"   , "black")
    #     width = self.modelObject.get(f"{role}.lineWidth"   , 1)
    #     kwargs = {"fill": color, "width": width}
    #   else:
    #     kwargs = dict()
    #   for info in infoList:  # count this object so that we can avoid drawing lines over one another
    #     # draw lines
    #     if info.lineID is None:  # new line
    #       info.lineID = self.canvas.canvas.create_line(
    #           self.view.viewToWindow(flattenPairs([info.nearPt, info.farPt])),
    #           tags=[self.tag], **kwargs)
    #     else:  # repaint existing line
    #       self.canvas.canvas.coords(info.lineID,
    #           self.view.viewToWindow(flattenPairs([info.nearPt, info.farPt])))
    #       self.canvas.canvas.itemconfigure(info.lineID, **kwargs)
    #
    #     # draw role labels
    #     if snPrefs.get("gui/showRoleLabels", storeDefault=False):
    #       anchor:str = ("n" if info.nearPt[1] < info.farPt[1] else "s") + \
    #                    ("w" if info.nearPt[0] < info.farPt[0] else "e")
    #       if info.labelID is None:
    #         info.labelID = self.canvas.canvas.create_text(info.nearPt[0], info.nearPt[1], text=role,
    #             fill="gray50", font=('Helvetica', 10, 'italic'), tags=[self.tag],
    #             anchor=anchor)
    #         assert info.labelID is not None
    #       else:
    #         self.canvas.canvas.coords(info.labelID,
    #             self.view.viewToWindow(info.nearPt[0], info.nearPt[1]))
    #         self.canvas.canvas.itemconfigure(info.labelID,
    #             anchor=anchor)
    #     else:
    #       if info.labelID is not None:
    #         self.canvas.canvas.delete(info.labelID)
    #         info.labelID = None
    #
    #     # draw end shapes (arrowheads)
    #     if not fast:  # if we're fast don't bother with the end shapes
    #       fillColor = self.modelObject.get(f"{role}.fillColor"   , "")
    #       nearEndShape = self.modelObject.get(f"{role}.nearEndShape", "")
    #       farEndShape = self.modelObject.get(f"{role}.farEndShape" , "")
    #       info.nearShapeID = self.drawEndShape(nearEndShape, [info.farPt[0], info.farPt[1], info.nearPt[0], info.nearPt[1]],
    #                                            info.nearShapeID, color, fillColor)
    #       info.farShapeID = self.drawEndShape(farEndShape, [info.nearPt[0], info.nearPt[1], info.farPt[0], info.farPt[1]],
    #                                            info.farShapeID, color, fillColor)
    # if self.view.reading: # need to wait until after all are displayed before expanding
    #   return
    terminators = ConnectorTerminators(self.cache['vis/terminator1'], self.cache['vis/terminator2'], self.cache['vis/terminator3'], self.cache['vis/terminator4'])
    lineType = self.cache['vis/lineType']
    if lineType == "straight":
      self.connectInfo = drawStraightConnector(self.src, self, self.dst, 
            terminators, self.connectInfo, 
            lineColor=self.cache['vis/lineColor'], 
            fillColor=self.cache['vis/lineFillColor'], 
            width=self.cache['vis/lineWidth'],
            tags=[self.tag])
    else:
      self.connectInfo = drawSmoothConnector(self.src, self, self.dst, 
            terminators, self.connectInfo, 
            lineColor=self.cache['vis/lineColor'], 
            fillColor=self.cache['vis/lineFillColor'], 
            width=self.cache['vis/lineWidth'],
            tags=[self.tag])
          
  # def drawUnfilledRoles(self):
  #   for role, infoList in self.roles.items():
  #     relation:Relation = self.modelObject
  #     if len(infoList) < relation.roles[role].card[1]:
  #       # draw in the "dangling" role as a clickable object
  #       self.unfilledRoles[role] = (self.canvas.canvas.create_text(info.nearPt[0], info.nearPt[1], text=role,
  #               fill="gray50", font=('Helvetica', 10, 'italic'), tags=[self.tag],
  #               anchor=anchor))

  ### GEOMETRIC INFO/CONTROL ###########################################################

  def reposition(self, aggressive:bool=False, suppressDraw:bool=False, adjustPos:bool=True):
    '''
    :param adjustPos: [default=True] When *True* (the normal case, e.g. called
      once at the end of a drag), a relation that isn't centred between its
      *src*/*dst* also gets a full *self.adjustPos()* call, which may invoke
      the local layout heuristic (FindFree) to resolve overlaps. When *False*
      (passed down from a live drag via *notifyNodeMove()*), the relation
      still repositions/redraws to track its connected nodes' current
      positions, but skips that extra layout-heuristic call, so a relation
      doesn't jump to a FindFree-computed spot on every single mouse-motion
      tick while something it's connected to is being dragged.
    '''
    # connectedObjects = self._getConnectedVObjects()
    # if self.floating() and len(connectedObjects) > 1 and self.modelObject.isIndividual():
    #   if len(set(connectedObjects)) <= 1:  # if all the objects are the same
    #     c = connectedObjects[0].centerPt()
    #     ctr = (c[0] + self.view.model._top.get('vis/minSize', 20) * 1.5, c[1])
    #   else:
    #     ctr = midpoint(*map(lambda obj: obj.centerPt(), connectedObjects))
    #   self.moveToCenterOn(ctr[0], ctr[1])
    # else:
    #   self.adjustPos(aggressive=aggressive)
    if not self.floating():
      if not suppressDraw:
        self.draw()
      return
    if self.src is not None and self.dst is not None:
      self.moveToCenterOn(*midpoint(self.src.centerPt(), self.dst.centerPt()), adjustPos=adjustPos)
    elif self.src is None and self.dst is None:
      if adjustPos:
        self.adjustPos(aggressive=aggressive)
    elif self.dst is None:
      ctrPt = self.src.centerPt() # type: ignore[union-attr]
      self.moveToCenterOn(ctrPt[0]+70, ctrPt[1], adjustPos=adjustPos)
    elif self.src is None:
      ctrPt = self.dst.centerPt()
      self.moveToCenterOn(ctrPt[0]-70, ctrPt[1], adjustPos=adjustPos)

    if not suppressDraw:
      self.draw()

  def findEndPoints(self, frm:VObject, to:VObject):
    return (self.findIntersection(to.centerPt(), frm), self.findIntersection(frm.centerPt(), to))

  def findIntersection(self, p1, node):
    """p2 is the center of node"""
    p2 = node.centerPt()
    while not self.arePtsClose(p1, p2):
      pc = midpoint(p1, p2)
      if node.containsPt(pc):
        p2 = pc
      else:
        p1 = pc
    return p1
    
  def arePtsClose(self, p1, p2):
    """ Return True iff the two points are close to one another. """
    return abs(p1[0] - p2[0]) < VRelation.granularity and abs(p1[1] - p2[1]) < VRelation.granularity

  ### NODES THIS RELATION CONNECTS TO #################################################

  def notifyNodeMove(self, node, adjustPos:bool=True):  # , direction):
    self.reposition(adjustPos=adjustPos)
    
  def notifyNodeDeletion(self, node):
    '''
    Recieve notice that *node* is deleting, so we delete the whole relation, being
    careful not to renotify *node*
    '''
    for n in self._getConnectedVObjects():
      if n is not node:
        n.notifyRelationDeletion(self) 
    self._delete()
    
  def _removeSelfFromConnectedNodes(self):
    '''
    Removes the reference to *self* from all objects this relation connects.
    Useful when making this relation hidden.
    
    :note: This should be used with caution as the system depends on exactly
      one entry in the *VObject.relations list* for each connecting role.
    '''
    for n in self._getConnectedVObjects():
      n.relations.remove(self)
      n.cache.refresh()
      
  def _addSelfToConnectedNodes(self):
    '''
    Appends a reference to *self* to all objects this relation connects.
    Useful when making this relation hidden.
    
    :note: This should be used with caution as the system depends on exactly
      one entry in the *VObject.relations list* for each connecting role.
    '''
    for n in self._getConnectedVObjects():
      n.relations.append(self)
      n.cache.refresh()
  
  @override
  def setHidden(self, hide:bool=True):
    '''
    '''
    if hide == self._hidden:
      return
    super().setHidden(hide)
    if hide:
      self._removeSelfFromConnectedNodes()
    else:
      self._addSelfToConnectedNodes()

  ### MENUS ############################################################################

  def addViewMenuItems(self, menu:tk.Menu):
    if self.modelObject is not None and self.modelObject.isIndividual():
      self._menuFloating = tk.BooleanVar()
      self._menuFloating.set(self.floating())
      menu.add_checkbutton(label="floating", onvalue=1, offvalue=0, variable=self._menuFloating, command=self._toggleFloatingAnchor)

    super().addViewMenuItems(menu)
  
  @override
  def addModelEditingMenuItems(self, menu:tk.Menu):
    super().addModelEditingMenuItems(menu)
    # Never offered for system relations (those in the always-in-memory sn model).
    if self.modelObject is None or self.modelObject.isSystemObject():
      return
    state = tk.NORMAL if self._endpointsEditable() else tk.DISABLED
    menu.add_command(label="reset src", state=state, command=lambda: self.chooseNewEndpoint("src"))
    menu.add_command(label="reset dst", state=state, command=lambda: self.chooseNewEndpoint("dst"))

  TERMINAL_HIT_RADIUS = 10
  "How close (in screen pixels, on each axis) a click must be to a terminal to grab it."

  def _endpointsEditable(self) -> bool:
    '''
    :returns: True iff the user may change this relation's src/dst here: not
      a system relation, and in an editor view of the relation's own model.
    '''
    mo = self.modelObject
    return mo is not None and not mo.isSystemObject() \
           and self.view.isModelEditor() and self.view.model is mo.model

  def _terminalAt(self, x:float, y:float) -> str|None:
    '''
    :param x: Canvas (window) coordinates, eg: from *canvasx(event.x)*.
    :param y: See *x*.
    :returns: "src" or "dst" if (x, y) is within *TERMINAL_HIT_RADIUS* of that
      end of the drawn connector, otherwise None.
    '''
    info = getattr(self, "connectInfo", None)
    if info is None:
      return None
    ends:list[tuple[str, float, float]] = []
    if info.sourceLineID is not None:
      c = self.view.canvas.coords(info.sourceLineID)   # drawn from the src end...
      if len(c) >= 2:
        ends.append(("src", c[0], c[1]))
    if info.destLineID is not None:
      c = self.view.canvas.coords(info.destLineID)     # ...and to the dst end
      if len(c) >= 2:
        ends.append(("dst", c[-2], c[-1]))
    r = self.TERMINAL_HIT_RADIUS
    for end, ex, ey in ends:
      if abs(x - ex) <= r and abs(y - ey) <= r:
        return end
    return None

  def grabTerminal(self, event) -> bool:
    '''
    If *event* (a button-1 press) is near either terminal, start choosing a new
    src/dst there (the same elastic line as the "reset src"/"reset dst" menu
    items), to be completed where the drag is released -- see
    *SNGView.onB1_ButtonRelease()*.

    :returns: True iff it did (so the caller shouldn't start its own drag).
    '''
    if not self._endpointsEditable():
      return False
    end = self._terminalAt(self.view.canvas.canvasx(event.x), self.view.canvas.canvasy(event.y))
    if end is None:
      return False
    self.view.addEventHandled(event)
    self.dragInfo = None
    self.chooseNewEndpoint(end)
    return True

  @override
  def onButton_1(self, event):
    '''
    A press near either terminal grabs it (see *grabTerminal()*); anywhere
    else it's the usual drag (moving and anchoring the label).
    '''
    if self.grabTerminal(event):
      return 'break'
    return super().onButton_1(event)

  def chooseNewEndpoint(self, end:str) -> None:
    '''
    Let the user pick a new *end* ("src" or "dst") for this relation with an
    elastic line, then change it in the model (as one undoable command).

    Only objects of the same kind as the other end are offered: relations
    connect either two nodes or two relations. For an isa link, the new
    parent (dst) must also be a type, since individuals can't have children.
    '''
    assert end in ("src", "dst")
    other = self.dst if end == "src" else self.src
    isaParent = end == "dst" and isinstance(self.modelObject, IsaIndividual)
    def acceptable(n:VObject) -> bool:
      return n is not self \
             and (other is None or isinstance(n, VRelation) == isinstance(other, VRelation)) \
             and not (isaParent and (n.modelObject is None or n.modelObject.isIndividual()))
    def chosen(_origin:VObject, sel:VObject) -> None:
      if end == "src":
        self.view.context.reconnect(self.modelObject, source=sel.modelObject)
      else:
        self.view.context.reconnect(self.modelObject, destination=sel.modelObject)
    color = self.cache['vis/lineColor'] or "green"
    self.view.elasticLineChoice(self, chosen, filter=acceptable,
                                arrowHeads=1 if end == "src" else 2, color=color)

  @override
  def update(self, subject, *topics:tuple[str, tuple[Any, ...]]) -> None:
    '''
    Follow changes to the model relation's endpoints ("mod src"/"mod dst"
    topics -- see *Relation._endpointChanged()*); anything else is handled
    by *VObject.update()*.
    '''
    rest = []
    for topic in topics:
      if topic[0] in ("mod src", "mod dst"):
        _old, new = topic[1]
        vo = None if new is None else self.view.makeViewObjectForGraphObject(new)
        if topic[0] == "mod src":
          self.src = vo  # AGRelation's setter moves us between the nodes' relation lists
        else:
          self.dst = vo
        self.view.freshPaint()
        self.reposition()
      else:
        rest.append(topic)
    if rest:
      super().update(subject, *rest)

  def _toggleFloatingAnchor(self, event=None):
    self.floating(self._menuFloating.get())
    if self.floating():
      self.draw()
      
  # def addModelEditingMenuItems(self, menu:tk.Menu):
  #   disabled = self.modelObject.isSystemObject() or not self.view.isModelEditor
  #   menu.add_command(label=f"{'show' if disabled else 'edit'} attributes", \
  #     command=lambda disabled=disabled: self.onEditAttributes(disabled=disabled))    #menu.add_cascade(menu=self.makeMakeRelationMenu(menu), label='make relation')
  #   if self.modelObject.isType():
  #     menu.add_command(label='make instance', command=lambda: self._doNewNodeCommand(individual=True))
  #     menu.add_command(label='make subtype', command=lambda: self._doNewNodeCommand(individual=False))
  #   menu.add_separator()
    
  # @override
  # def _doNewNodeCommand(self, individual:bool):
  #   from util.command import CommandWrapper
  #   cmd = CommandWrapper(
  #             NewModelRelationCommand(self.view.model, parent=self.modelObject, individual=individual),
  #             setup=self._setCatchNewObjects,
  #             teardown=self._resetCatchNewObjects)
  #   node = self.canvas.doList.do(cmd)
  #   applyEditAttrsBox(self.canvas.canvas, node, title=str(node), editKey="name")
  #   vnode = self.canvas.findViewObjectForGraphObject(node)
  #   vnode.draw()

  ### Event handling ###################################################################

  @override
  def onEnter(self, event):
    self.canvas.configure(cursor="sb_h_double_arrow")
    
  def onB1_ButtonRelease(self, event):
    if self.dragInfo is not None and self.dragInfo[4]:
      self.floating(False)
    super().onB1_ButtonRelease(event)

  ### Debugging support ################################################################
  
# class VIsa(VRelation):
#
#   def __init__(self, tgview,
#       modelObject=None, typ:Relation=None,
#       shape:Union[Any, str]="Oval",
#       x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None,
#       _bb:Optional[list]=None,
#       floating:Optional[bool]=None):
#     super().__init__(tgview, modelObject=modelObject, typ=typ, shape=shape, _bb=_bb, floating=floating, x=x, y=y, x1=x1, y1=y1)
#
#   # def _post__init__(self):
#   #   super()._post__init__()
#
#   def addModelEditingMenuItems(self, menu:tk.Menu):
#     pass  # we don't want to allow user editing of attributes or relations on isa's.

