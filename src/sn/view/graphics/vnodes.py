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
Implements VNode and all its supporting classes:

*VNode*:
   The main class in this module. A visual node that represents an *Node* (model node).
      
  .. inheritance-diagram:: VNode
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

----
"""

import tkinter as tk
from sn.model.model import IsaIndividual, GraphObject
from sn.view.graphics.vobjects import VObject
from typing import Optional, Any, override

class VNode(VObject):
  '''
  This class is more or less a dummy class under *VObject* for all nodes (including 
  T (top) (which **relation** is specialized from)) that are not **relations** so that
  nodes are issubclass()-distinct from **relations**. As such, most of it's functionality is 
  implemented in the common superclass *VObject*.  
  
  *VNode <: *VObject* :> *VRelation* :> *VIsa* 
  '''

  ### CONSTRUCTOR AND HELPERS ##########################################################

  # dummy __init__() for debugging purposes...
  # def __init__(self, canvas:PRDb, modelObject:GraphObject, 
  #              shape:Union[Any,str]="Rectangle", 
  #              x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None, 
  #              _id:Optional[int]=None):
  #   super().__init__(canvas, modelObject, shape, x, y, x1, y1, _id)
  def __init__(self, view:"SNGView", modelObject:GraphObject|str,
               shape:Any|str="Rectangle",
               x:Optional[int]=None, y:Optional[int]=None, x1:Optional[int]=None, y1:Optional[int]=None,
               **kwargs):
    super().__init__(view, modelObject, shape, x, y, x1, y1)
 
  @override
  def makeModelObjectSubtype(self, individual:bool) -> None:
    self.view.context.new_node(self.modelObject, name="", individual=individual, model=self.view.model) # type: ignore[arg-type]

#   ### PERSISTENCE ######################################################################
#
#   def serializeXML(self) -> et.Element:
#     """
#     Returns the representation of this object as an Element object.
#     Implementors should call *super().serializeXML()* **first** as this top-level method
#     will construct the Element itself.
#     """
#     elem = super().serializeXML()
#     elem.set('boundingBox', str(self.boundingBox()))
#     return elem
#
#   @classmethod
#   def getArgs(cls, elem: et.Element) -> Tuple[List[Any], Dict[str, Any]]:
#     """
#     :param elem: The *ElementTree* element from which we are unserializing.
#     :param addrServer: The address server from which we can lookup any
#       addresses by id that occur in *elem*. Note that although *addrServer*
#       may not be used here, it might be necessary for subclasses to use
#       it, so it needs to be in the argument list.
#     :return: An (\\*args, \\*\\*kwargs) tuple for the constructor of the class 
#       found in the element's name.
#     """
#     args = []
#     kwargs = dict()
#     canvas = addrServer.idLookup(elem.get('canvas'))
#     args.append(canvas)
#
#     x, y, x2, y2 = literal_eval(elem.get('boundingBox'))
#     args += [x, y, x2, y2]
#
#     model = elem.get('model')
#     model = addrServer.idLookup(model) if model!=None and model!="" else None
#
#     shape = model.attrs['vis/shape'] #elem.get('vis/shape')
#     args.append(shape)
#
#     args.append(model)
#
#
#     idStr = elem.get('id')
#     kwargs["_id"] = IDServer.getLocalID(idStr) if idStr else None
# #    kwargs["idServer"] = canvas
#
#     return args, kwargs
#
#   def unserializeXML(self, elem: et.Element):
#     """
#     :param elem: The *ElementTree* element from which we are unserializing.
#     :param addrServer: The address server from which we can lookup any
#       addresses by id that occur in *elem*. Note that although *addrServer*
#       may not be used here, it might be necessary for subclasses to use
#       it, so it needs to be in the argument list.
#
#     This object is partially constructed, but we need to restore this class's bits.
#     Implementors should call *super().unserializeXML()* at some point.
#     """
#     super().unserializeXML(elem, addrServer)

  ### ATTRIBUTES #######################################################################

  def updateFromAttrs(self, attrs:Optional[list]=None):
    def update(name):
      if name in attrs and attrsInfo[name]() != self.model.attrs[name]:
        attrsInfo[name](self.model.attrs[name])
        
    attrsInfo = {'vis/shape':self.shape, 'vis/fillColor':self.fillColor, 'vis/borderColor':self.borderColor, \
        'vis/textColor':self.textColor, "label":self.label, "type":self.typ, \
        'vis/lineColor':self.lineColor, 'vis/minSize':self.minSize, 'vis/aspectRatio':self.aspectRatio}
    #TODO: get this implemented or get rid of it.
    # if self._updatingFromAttrs: return
    # self._updatingFromAttrs = True
    # if attrs is None: attrs = list(attrsInfo.keys())    
    # for name in attrs:
    #   update(name)
    # self._updatingFromAttrs = False
    

  # def notifyAttrChanged(self, attrsObj:Attributes, name:str, value:Any):
  #   try:
  #     if name == 'vis/fillColor':
  #       self.fillColor(value)
  #     if name == 'vis/borderColor':
  #       self.borderColor(value)
  #     if name == 'vis/shape':
  #       self.shape(value)
  #     if name == 'label':
  #       self.label(value)
  #     if name == 'vis/textColor':
  #       self.textColor(value)
  #     if name == 'type':
  #       self.typ(value)
  #     if name == 'vis/lineColor':
  #       self.lineColor(value)
  #     if name == 'vis/minSize':
  #       self.minSize(value)
  #     if name == 'vis/aspectRatio':
  #       self.aspectRatio(value)
  #   except Exception as ex:
  #     self.canvas.logger.write(f'got except with "{name}": "{value}". Probably due to partially constructed VNode.', level="warning", exception=ex)
        
  ### DECORATORS #######################################################################

  # def removeDecorator(self, key=None, obj=None):
  #   """
  #   :param key: A key in the decorator list.
  #   :param obj: An actual decorator object.
  #
  #   Removes a single decorator from the decorator list, either by *key* or by *obj*\\ .
  #   If the item is not found, nothing is done.
  #   """
  #   if key!=None:
  #     if key in self.decorators:
  #       self.decorators[key].delete()
  #       self.decorators.pop(key, None)
  #       return
  #   if obj!=None:
  #     for k,v in self.decorators.items():
  #       if v == obj:
  #         v.delete()
  #         self.decorators.pop(k, None) #should have been popped already by the delete() above...
  #         return
#    assert False, f'VNode.removeDecorator(self={self}, key={key}, obj={obj}): Failed to remove decorator.'

  # def notifyDecoratorDeletion(self, decorator):
  #   self.removeDecorator(obj=decorator)

#   ### GETTERS AND SETTERS ##############################################################
#
#   def boundingBox(self, rect:List[float]=None):
#     if rect != None:
#       self._shape.boundingBox(rect)
#       self.draw()
#     return self._shape.boundingBox() 
#
#   def minSize(self, s:Optional[int]=None):
#     if s != None:
#       bb = self.boundingBox()
#       ar = self.aspectRatio()
#       self.boundingBox([bb[0], bb[1], bb[0]+s, bb[1]+(s*ar)])
#       self.model.attrs['vis/minSize'] = s
#       self._minSize = s
# #      self.draw()
#     try:
#       return self._minSize 
#     except:
#       self._minSize = self.model.attrs['vis/minSize']
#       return self._minSize
#
#   def aspectRatio(self, s:Optional[float]=None):
#     if s != None:
#       bb = self.boundingBox()
#       self.boundingBox([bb[0], bb[1], bb[2], bb[1]+((bb[2]-bb[0])*s)])
#       self.model.attrs['vis/aspectRatio'] = s
#       self._aspectRatio = s
# #       self.draw()
#     try:
#       return self._aspectRatio
#     except:
#       self._aspectRatio = self.model.attrs['vis/aspectRatio']
#       return self._aspectRatio
#
#   def fillColor(self, c=None):
#     if c != None:
#       self._shape.draw(fill=c)
#     try: # The fill color could be non-existent for a transparent color
#       return self.canvas.itemconfigure(self._shape.id, "fill")[0]
#     except:
#       return ""
#
#   def borderColor(self, c=None):
#     if c != None:
#       self._shape.draw(outline=c)
#     try: # The fill color could be non-existent for a transparent color
#       return self.canvas.itemconfigure(self._shape.id, "outline")[0]
#     except:
#       return ""
#
#   def textColor(self, c=None):
#     d = self.decorators["text"]
#     if "text" in self.decorators:
#       if d is not None:
#         if c != None:
#           d.draw(fill=c)
#     try: # The fill color could be non-existent for a transparent color
#       return self.canvas.itemconfigure(d.id, "fill")[0]
#     except:
#       return ""
#
#   def selected(self, val:Optional[bool]=None, _multi:bool=False):
#     if val is not None:
#       if val: # setting selected
#         if "selected" not in self.decorators:
#           self.decorators["selected"] = Selected(self)
#           self.decorators["selected"].draw()
#           if not _multi:
#             for s in self.canvas.selected.copy():
#               if s is not self: s.selected(False)
#           self.canvas.selected.add(self)
#       elif self.decorators is not None: # setting not selected
#         if "selected" in self.decorators:
#           self.decorators["selected"].delete()
#           assert "selected" not in self.decorators
#           self.draw()
#           self.canvas.selected.discard(self)
#     return "selected" in self.decorators if self.decorators is not None else None
#
# #        if self.selected():
# #          if (s&0x18) == 0: # the mac <cmd> key is NOT pressed
# #            for s in self.canvas.selected: 
# #              if s is not self: s.selected(False)
# #          self.canvas.selected.add(self)
# #        else:
# #          self.canvas.selected.discard(self)
#
#
#   def shape(self, c=None):
#     if c is not None and c != type(self._shape).__name__:
#       bb = self.boundingBox()
#       newShape = None
#       try:
#         newShape = self.strToShape(c, bb)
#       except Exception as ex:
#         self.canvas.logger.write(f'Shape "{c}" is not known.', level="warning", exception=ex)
#       if newShape is not None:
#         self.killBindings()
#         oldShape = self._shape
#         self._shape = newShape
#         self._shape.draw()
#         self.canvas.lift(newShape.id, oldShape.id)
#         oldShape.delete()
#         self.updateFromAttrs(['vis/fillColor', 'vis/borderColor'])
#         self.makeBindings()
#     return type(self._shape).__name__
#
#   def label(self, t=None):
#     if "text" in self.decorators:
#       d = self.decorators["text"]
#       if d is not None:
#         if t != None:
#           d.draw()
#     return self.model.attrs["label"]
#
#   def typ(self, b=None):
#     if b is not None:
#       assert isinstance(b, bool)
#       if b:
#         if "typeMarker" not in self.decorators:
#           self.decorators["typeMarker"] = TypeMarker(self)
#           self.decorators["typeMarker"].draw()
#       else:
#         if "typeMarker" in self.decorators and not self.model.system:
#           self.decorators["typeMarker"].delete()
#     return self.model.attrs["type"]
#
#   def lineColor(self, c=None):
#     return self.model.attrs['vis/lineColor']

  ### DRAWING ##########################################################################

  # def draw(self):#, rect=None):
  #   if self._shape.id is None:
  #     self._shape.draw() #self.attrs["boundingBox"])#rect)
  #     self.markerDecoratorOffset = 0
  #     for d in self.decorators.values(): # TODO: might need to concern ourselves about draw order here
  #       d.draw()
  #     self.updateFromAttrs()
  #   else:
  #     self.updateFromAttrs()
  #     self._shape.draw()
  #     self.markerDecoratorOffset = 0
  #     for k, d in self.decorators.items():
  #       d.draw()

  ### GEOMETRIC INFO/CONTROL ###########################################################
  # The "primitive" is moveTo(), so all these that actually move must call moveTo() to
  # actually do the work.

  # def moveTo(self, x, y, allowOverScrollRegionSE=True, adjustPos=True):
  #   """ 
  #   Move so that the NW corner is on (x,y), informing all the decorators and 
  #   relations
  #   """
  #   bb = self.boundingBox()
  #   print(f'VNode.moveTo({x}, {y})')
  #   if bb[0] == x and bb[1] == y: # we haven't actually moved, so do nothing.
  #     return
  #   sr = self.canvas.scrollRegion
  #   if x<sr[0]: x = sr[0]
  #   if y<sr[1]: y = sr[1]
  #   if not allowOverScrollRegionSE:
  #     if x+bb[2]-bb[0]>sr[2]: x = sr[2]-(bb[2]-bb[0])
  #     if y+bb[3]-bb[1]>sr[3]: y = sr[3]-(bb[3]-bb[1])
  #   self._shape.moveTo(x, y)
  #   self.draw()
  #   if adjustPos: self.adjustPos()
  #   for r in self.relations:
  #     r.notifyNodeMove(self)
  #
  # def moveBy(self, dx, dy, allowOverScrollRegionSE=False, adjustPos=True):
  #   bb = self.boundingBox()
  #   x = bb[0]+dx
  #   y = bb[1]+dy
  #   print(f'VNode.moveBy({dx}, {dy}), to=({x}, {y}), bb={bb}')
  #   self.moveTo(x, y, allowOverScrollRegionSE, adjustPos=adjustPos)
  #
  # def moveToCenterOn(self, x, y, adjustPos=True):
  #   bb = self.boundingBox()
  #   width = abs(bb[2]-bb[0])
  #   height = abs(bb[3]-bb[1])
  #   x = x - (width/2)
  #   y = y - (height/2)
  #   self.moveTo(x, y, adjustPos=adjustPos)

  # def centerPt(self):
  #   """Gets the center point of this shape."""
  #   r = self.boundingBox()
  #   return ((r[0]+r[2])/2, (r[1]+r[3])/2)

  # def containsPt(self, pt):
  #   return pointInPoly(pt, self._shape.points())
  #
  # def adjustPos(self, others=None):
  #
  #   layout = self.canvas.localLayout
  #   if layout is not None:
  #     for r in self.relations:
  #       layout(r)
  #     layout(self)
  #   for r in self.relations:
  #     r.draw()
  #
  # def overlaps(self, bb:list=None, others:Iterable=None, spacing:Optional[list]=None) -> List[VObject]:
  #   ""
  #   if bb is None:
  #     bb = self.boundingBox() if spacing is None else expandRect(self.boundingBox(), spacing)
  #   if others is None:
  #     others = list(self.canvas.values()) #self.canvas.nodes + self.canvas.relations
  #     others.remove(self)
  #   else:
  #     if self in others:
  #       others = others.copy()
  #       others.remove(self)
  #   ret = []
  #   for n in others:
  #     nBB = n.boundingBox() if spacing is None else expandRect(n.boundingBox(), spacing)
  #     if overlaps(bb, nBB):
  #       ret.append(n)
  #   return ret

#   ### RELATIONS ########################################################################
#
#   def addRelation(self, relation): #, direction):
#     from sn.view.graphics.vrelations import VRelation
#     if not isinstance(relation, VRelation):
#       raise TypeError("VNode.addRelation(): first argument must be of type VRelation.")
#     self.relations.append(relation) #(relation, direction))
# #     relation.model.addObserver(self) # observer the relation MODEL
#
#   def notifyRelationDeletion(self, relation):
#     """ This is the notification from removal of a relation VIEW. """ 
#     for r in self.relations:
#       if r == relation:
#         self.relations.remove(r)
#         break

  ### MENUS ############################################################################
  
  # def makeMenu(self) -> tk.Menu:
  #   m = tk.Menu(self.canvas)
  #   if app.DEBUG_MENUS:
  #     m.add_command(label=f'{self.idString} -> {self.model.idString}', state=tk.DISABLED)
  #     m.add_separator()
  #   editable = self.view.isModelEditor
  #   if editable:
  #     self.addModelEditingMenuItems(m)
  #   self.addViewMenuItems(m)
  #   m.add_separator()
  #   self.addDeletionMenuItems(m)
  #   if app.DEBUG_MENUS:
  #     m.add_separator()
  #     m.add_command(label='validate', command=self.validate)
  #   return m
    
  # def addViewMenuItems(self, menu:tk.Menu):
  #   INSTANCE = "IsaIndividual (instance)"
  #   SUBTYPE = "IsaIndividual (subtype)"
  #   # collect info about the relations
  #   types = dict()  # {name: (modelOutgoingCount, modelIncomingCount, 
  #           #         viewOutgoingCount,  viewIncomingCount,  otherIsaTypeCount)}
  #   types[INSTANCE] = (0,0,0,0)
  #   types[SUBTYPE]  = (0,0,0,0)
  #   total = (0,0)
  #   for r in self.model.relations:
  #     # get the VNode that matches the Node (if any)
  #     vRelation = None
  #     for rv in self.relations:
  #       if rv.model is r:
  #         vRelation = rv
  #         break
  #
  #     # abort if this relation (r) is in a hidden category
  #     if self.canvas.categories.isCategory(r, self.canvas.hiddenCategories): continue
  #
  #     name = r.attrs["label"]
  #     if name != "IsaIndividual":
  #       if name not in types: # add the name of the relation upon encountering a new one
  #         types[name] = (0,0,0,0)
  #       t = types[name]
  #     if r.toNode is self.model: # we're the toNode: increment incoming model and (maybe) view count 
  #       if name == "IsaIndividual":
  #         name = SUBTYPE if r.froNode.attrs['type'] else INSTANCE
  #         t = types[name]
  #       t = (t[0], t[1]+1, t[2], t[3]+(0 if vRelation is None else 1))
  #     else: # we're the froNode: increment outgoing model and (maybe) view count
  #       if name == "IsaIndividual":
  #         name = SUBTYPE if r.toNode.attrs['type'] else INSTANCE
  #         t = types[name]
  #       t = (t[0]+1, t[1], t[2]+(0 if vRelation is None else 1), t[3])
  #     types[name] = t
  #     total = (total[0]+1, total[1]+(0 if vRelation is None else 1))
  #   if types[INSTANCE] == (0,0,0,0): del types[INSTANCE]
  #   if types[SUBTYPE]  == (0,0,0,0): del types[SUBTYPE]
  #
  #   # the expand menus
  #   expMenu = tk.Menu(menu)
  #   for k,v in types.items():
  #     subMenu = tk.Menu(expMenu)
  #     if v[0] > 0:
  #       if k == INSTANCE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and vn.model is mr.froNode and not mr.toNode.attrs['type']
  #       elif k == SUBTYPE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and vn.model is mr.froNode and mr.toNode.attrs['type']
  #       else:
  #         filter = lambda vn, mr, label=k: \
  #                 mr.attrs["label"] == label and vn.model is mr.froNode
  #       subMenu.add_command(label=f'outgoing ({v[0]})', \
  #           command=lambda f=filter: self.expand(filter=f))
  #     if v[1] > 0:
  #       if k == INSTANCE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and vn.model is mr.toNode and not mr.froNode.attrs['type']
  #       elif k == SUBTYPE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and vn.model is mr.toNode and mr.froNode.attrs['type']
  #       else:
  #         filter = lambda vn, mr, label=k: \
  #                 mr.attrs["label"] == label and vn.model is mr.toNode
  #       subMenu.add_command(label=f'incoming ({v[1]})', \
  #           command=lambda f=filter: self.expand(filter=f))
  #     if v[0] > 0 and v[1] > 0:
  #       if k == INSTANCE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and not mr.froNode.attrs['type']
  #       elif k == SUBTYPE:
  #         filter = lambda vn, mr: \
  #                 mr.attrs["label"] == "IsaIndividual" and mr.froNode.attrs['type']
  #       else:
  #         filter = lambda vn, mr, label=k: \
  #                 mr.attrs["label"] == label
  #       subMenu.add_command(label=f'both ({v[0]+v[1]})', \
  #           command=lambda f=filter: self.expand(filter=f))
  #     subMenu.add_separator()
  #     for mr in self.model.relations:
  #       if k in [INSTANCE, SUBTYPE]: name = "IsaIndividual"
  #       else: name = k
  #       if mr.attrs["label"] == name:
  #         arrow = '->' if mr.froNode is self.model else '<-'
  #         other = mr.toNode if mr.froNode is self.model else mr.froNode
  #         filter = lambda vn, mr, theMr=mr: mr is theMr
  #         subMenu.add_command(label=f'{k} {arrow} {other.attrs["label"]}',
  #               command = lambda f=filter: self.expand(filter=f))
  #     expMenu.add_cascade(menu=subMenu, label=f'expand {k} relations ({v[0]+v[1]})')
  #   menu.add_command(label=f"expand all ({total[0]})", command=self.expand)
  #   menu.add_cascade(menu=expMenu, label='expand')
  #
  #   # The contract menus
  #   if total[1] > 0:
  #     conMenu = tk.Menu(menu)
  #     for k,v in types.items():
  #       subMenu = tk.Menu(conMenu)
  #       if v[2] > 0:
  #         if k == INSTANCE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and vn.model is mr.froNode and not mr.toNode.attrs['type']
  #         elif k == SUBTYPE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and vn.model is mr.froNode and mr.toNode.attrs['type']
  #         else:
  #           filter = lambda vn, mr, label=k: \
  #                   mr.attrs["label"] == label and vn.model is mr.froNode
  #         subMenu.add_command(label=f'outgoing ({v[2]})', \
  #             command=lambda f=filter: self.contract(filter=f))
  #       if v[3] > 0:
  #         if k == INSTANCE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and vn.model is mr.toNode and not mr.froNode.attrs['type']
  #         elif k == SUBTYPE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and vn.model is mr.toNode and mr.froNode.attrs['type']
  #         else:
  #           filter = lambda vn, mr, label=k: \
  #                   mr.attrs["label"] == label and vn.model is mr.toNode
  #         subMenu.add_command(label=f'incoming ({v[3]})', \
  #             command=lambda f=filter: self.contract(filter=f))
  #       if v[2] > 0 and v[3] > 0:
  #         if k == INSTANCE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and not mr.froNode.attrs['type']
  #         elif k == SUBTYPE:
  #           filter = lambda vn, mr: \
  #                   mr.attrs["label"] == "IsaIndividual" and mr.froNode.attrs['type']
  #         else:
  #           filter = lambda vn, mr, label=k: \
  #                   mr.attrs["label"] == label
  #         subMenu.add_command(label=f'both ({v[2]+v[3]})', \
  #             command=lambda f=filter: self.contract(filter=f))
  #       conMenu.add_cascade(menu=subMenu, label=f'contract {k} relations ({v[2]+v[3]})')
  #     menu.add_command(label=f"contract all ({total[1]})", command=self.contract)
  #     menu.add_cascade(menu=conMenu, label='contract')
  
  def addDeletionMenuItems(self, menu:tk.Menu):
    menu.add_command(label="remove from view", command=self.delete)
    if not self.model.system and self.view.isModelEditor:
      menu.add_command(label="delete from model", command=self.model.delete)
  
  def makeMakeRelationMenu(self, menu:tk.Menu):
    m = tk.Menu(menu)
    types = []
    for t in (t for t in self.view.model.relations if t.isType()):
        types.append(t)
    # TODO: sort menu?
    for t in types:
      m.add_command(label=t.name, 
        command=lambda t=t: self.setMakingRelation(typ=t))
    return m

  ### Event handling ###################################################################

  def setMakingRelation(self, val=True, typ=None):
    self.canvas.makeRelationFrom(self, typ=typ)
    #self.dragInfo = None

  # def onRightMouse(self, event):
  #   """Creates and displays the node specific menu at the clicked location."""
  #   self.canvas.addEventHandled(event)
  #   m = self.makeMenu()
  #   m.post(event.x_root, event.y_root)
  #   return m
  #
  # def onButton_1(self, event): #get initial location of object to be moved
  #   """
  #   The mouse clicked on this node, so begin a mouse event capture. We will
  #   decide on if it's just a node move or a selection toggle in *self.onB1_Motion()*
  #   and *self.onB1ButtonRelease()*.
  #   """
  #   self.canvas.addEventHandled(event)
  #   print(f'onButton_1() event x={event.x}, y={event.y}, selected={self.selected()}')
  #   winX = event.x - self.canvas.canvasx(0) # adjust for canvas offset
  #   winY = event.y - self.canvas.canvasy(0)
  #   self.dragInfo = (winX, winY, False) # x,y,no-drag-motion-event
  #   self.old_suppressLocalLayout = self.canvas.suppressLocalLayout()
  #   self.canvas.suppressLocalLayout(True)
  #   return 'break'
  #
  # def onB1_Motion(self, event):
  #   """
  #   The mouse is moving while being captured by this node, so if we had clicked to start
  #   accepting events, just move the node to track the event, updating *self.dragInfo*.
  #   """
  #
  #   if self.dragInfo != None:
  #     self.canvas.addEventHandled(event)
  #     winX = event.x - self.canvas.canvasx(0) # adjust for canvas offset
  #     winY = event.y - self.canvas.canvasy(0)
  #     dX = winX - self.dragInfo[0]
  #     dY = winY - self.dragInfo[1]
  #     print(f'onB1_Motion() event({event.x},{event.y}), d=({dX},{dY}), selected={self.selected()}')
  #     if self.selected():
  #       for n in self.canvas.selected:
  #         n.moveBy(dX, dY)
  #     else:
  #       self.moveBy(dX, dY)
  #     # reset the starting point for the next move
  #     self.dragInfo = (winX, winY, True) # x,y,drag-motion-event-occurred
  #     return 'break'
  #   else:
  #     print(f'non-drag onB1_Motion() event x={event.x}, y={event.y}')
  #
  #
  # def onB1_ButtonRelease(self, event): #reset data on release
  #   """
  #   Button one was released. If it was a drag, it was a move, and everything is fine except
  #   we call self.adjustPos() which may resolve overlap conflicts. If it was a click (no
  #   intervening <B1_Motion> events), toggle the selection state of the node.
  #   """
  #   if self.dragInfo != None:
  #     self.canvas.addEventHandled(event)
  #     if self.dragInfo[2]: # indicated there was a <B1_Motion> event, ie: this was a drag: wrap up a move.
  #       self.canvas.suppressLocalLayout(self.old_suppressLocalLayout)
  #       self.adjustPos()
  #     else: # this was a click, not a drag: toggle the selection state
  #       s = event.state
  #       self.selected(not self.selected(), _multi=s_CMD(s) or s_SHIFT(s)) # toggle selected
  #     self.dragInfo = None
  #     return 'break'
  #     # TODO: add updating the boundingBox.
      
  def notifyModelChanged(self, modelObj, modelOperation:str, info:Optional[any]=None):
#     if modelObj != self.model: # it must be that a IsaIndividual-ancestor of the model changed,
#       self.canvas.logger.write(f'VNode.notifyModelChanged({modelObj}[NOT self.model], "{modelOperation}", info={info}) [{self}]', level="debug")
#       self.updateFromAttrs([info[0]])
    unhandled = False
    if modelOperation == 'del': 
      if modelObj is self.model:
        self.delete()
      elif modelObj in self.relations:
        for r in self.relations:
          if r.model is modelObj:
            self.relations.remove(r)
            if isinstance(modelObj, IsaIndividual):
              self.draw()
            break
    elif modelOperation == 'mod attr':
      assert info[1] is not None
      if modelObj == self.model:
        self.notifyAttrChanged(self.model.attrs, info[0], info[1])
      self.draw()

    elif modelOperation == 'add rel':
      # the model is telling us about a added relation, but we rely on the VRelation's model to handle any added relations.
      pass
#       if not hasattr(self, "addrel123"):
#         unhandled = True
#         self.addrel123 = True
    elif modelOperation == 'del rel':
      done = False
      if modelObj is not self.model: # the model is telling us about a deleted relation, but we rely on the VRelation's model to handle any deleted relations.
        for r in self.relations:
          if r.model is modelObj:
            r.model.removeObserver(self)
            r.delete()
            done = True
            break
        if not done:
          self.canvas.logger.write(f'Got a "del rel" operation for "{modelObj}" that isn\'t one of my relations {self.relations}.', level='warning')
#       if not hasattr(self, "delrel123"):
#         unhandled = True
#         self.delrel123 = True
    else:
      raise NotImplementedError(f'VNode.notifyModelChanged(): operation "{modelOperation}" not implemented.') 
    if unhandled:
      self.canvas.logger.write(f'operation "{modelOperation}" not implemented.', level='warning') 

    
