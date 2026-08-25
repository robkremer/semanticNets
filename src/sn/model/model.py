'''
.. inheritance-diagram:: Model GraphObject Node Relation IsaIndividual
    :parts: 1
    :private-bases:
    :top-classes: object


Created on Apr 21, 2026

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
from util.persistence.pRef import PRObject, PRDb, PReference, PRDbContainer
from util.persistence.serialize import InstantiationInfo, ParamInfo, PropertyInfo,\
  SerializableType
from util.utils import removeDuplicates, delOne
from typing import override, cast, Generator, Callable, Optional,\
  Iterable, overload, Iterator
from util.attribute import AttributedObject, Attribute, VAR, TYPENAME,\
  UNRESTRICTED, VAR_DEFAULTED, NOVALUE
from util.validatedList import ValidatedList
#from docutils.nodes import description
import logging
from util.observer import Subject
import sn

logger:sn.SNLogger = sn.getLogger(__name__)

RIGHT_ARROW = "\u279C"
UP_ARROW = "\u2B06" #"\u2B06"

RIGHT_POINTING_DOUBLE_ANGLE_QUOTATION_MARK = '\u00BB'
SINGLE_RIGHT_POINTING_ANGLE_QUOTATION_MARK = '\u203A'
SINGLE_LEFT_POINTING_ANGLE_QUOTATION_MARK = '\u2039'
EN_DASH = '\u2013'
ANTICLOCKWISE_GAPPED_CIRCLE_ARROW = '\u27F2'

REL_PLANE = EN_DASH + SINGLE_RIGHT_POINTING_ANGLE_QUOTATION_MARK
REL_TRANSITIVE = RIGHT_POINTING_DOUBLE_ANGLE_QUOTATION_MARK
REL_SYMMETRIC = SINGLE_LEFT_POINTING_ANGLE_QUOTATION_MARK
REL_REFLEXIVE = ANTICLOCKWISE_GAPPED_CIRCLE_ARROW

def makeRelationArrow(rel:Relation) -> str:
  t = rel.isTransitive()
  s = rel.isSymmetric()
  r = rel.isReflexive()
  if t and s and r:
    return "==" 
  ret = REL_PLANE
  if t:
    ret = ret[:-1] + REL_TRANSITIVE
  if s:
    ret = REL_SYMMETRIC + ret
  if r:
    ret = REL_REFLEXIVE + ret
  return ret

GORef = PReference["GraphObject"]

class GraphObject(AttributedObject, PRObject):
  '''
  .. Note::
  
    *GraphObject* is a **subclass** but not strictly a **subtype** of *PRObject* as 
    its container object pointer (*Model*) is subtype of the its parent's pointer
    (*PRDb*).
  '''
  
  def __init__(self, db:Model, parents:Iterable[GraphObject]=[], individual:bool=False, name:Optional[str]=None):
    '''
    :param db: The Model in which to create the object
    :type db: Model
    :param parents: The direct parents of the object from which they will inherit attributes.
    :type parents: GraphObject
    :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to True.
    :type individual: bool
    :param name: The given name of the object. It need not be unique in the model, but that
      may lead to ambiguities in searching for it my name, so uniqueness would be good...
      If the name is not given, it will inherit it's name from the first parent.
    :type name: Optional[str]
    '''
    assert isinstance(db, Model)
    AttributedObject.__init__(self)
    PRObject.__init__(self, db)

    outgoingCheck = lambda r, slf=self: isinstance(r, Relation) and r.src is slf and not slf is None and not slf.model.writeLocked()
    self._outgoing:ValidatedList[Relation] = ValidatedList(outgoingCheck)
    "Should only be assigned by *Relation* objects where self is at the src end and not write-locked."
    
    incomingCheck = lambda r, slf=self: isinstance(r, Relation) and r.dst is slf
    self._incoming:ValidatedList[Relation] = ValidatedList(incomingCheck)
    "Should only be assigned by *Relation* objects where self is at the dst end."
    
    self._individual = individual
    self._parentsCache:list[GraphObject]|None = []
    if parents is not None: # Will be None when reading in from persistent store
      for p in parents:
        IsaIndividual(db, self, p)
    if name is not None:
      try:
        self["name"] = name
      except Exception as ex:
        logger.warning(f'Cannot update name field ({ex.__class__.__name__}): {ex}')
      
    self.inferred:bool = False
    "Used to mark objects are inferred by the system so they may later be retracted."
    self._statusReport:list[tuple[str, str]] = []

  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.
    '''
    atObject = AttributedObject.getInstantiationInfo()
    prObject = PRObject.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(GraphObject, slf).db)],
            conKWArgs=[ParamInfo("individual", bool, lambda slf: cast(GraphObject,slf)._individual)],
            postconSetters=atObject.postconSetters + prObject.postconSetters +
              [PropertyInfo("inferred", bool)],
            finalSetters=atObject.finalSetters + prObject.finalSetters
            )

  @property
  def model(self) -> Model:
    'Simple aliasing for *self.db*.'
    return self.db
  
# These aren't actually needed because _incoming and _outgoing are really caches for relation connections 
  # @override
  # def setDirty(self, value:bool=True) -> None:
  #   '''
  #   An object is dirty if it has been modified and should probably be
  #   saved on exit.  This should be called from all methods that modify
  #   the state of this object.
  #
  #   If *value* is False, resets all the contained *Attributes* to False.
  #
  #   :param value: (default True) The value to set *dirty* to.
  #   :type value: bool
  #   '''
  #   assert type(value) is bool
  #   super().setDirty(value)
  #   if not value:
  #     self._incoming.setDirty(False)
  #     self._outgoing.setDirty(False)
  #
  # @override
  # def isDirty(self) -> bool:
  #   '''
  #   Returns True iff the object (or an of it's contained *Attributes*) have 
  #   been modified and should probably be saved on exit. 
  #   '''
  #   if super().isDirty() or self._incoming.isDirty() or self._outgoing.isDirty():
  #     return True
  #   return False
  
  def _getOutgoing(self, 
                   filtr:Callable[[Relation], bool]=lambda _: True, 
                   localOnly:bool=False) -> Generator[tuple[Relation, GraphObject|None]]:
    '''
    This method should be used to access all outgoing relations.  It will automatically
    include any symmetric relations.
    
    :param filtr: If provided, this function will be called with the *Relation*
      as an argument.  If it returns true, the relation will be returned in the
      return value, otherwise it won't. By default, ALL relations are returned.
    :type filtr: Callable[[Relation], bool]
    :param localOnly: if *localOnly* is True, the GraphObject (second) elements 
      in the returned pairs will be None if this Relation only inherits a value.
      If *localOnly* is False, the second elements will be the inherited value
      (if there's no local). By default, *localOnly* is False.
    :type localOnly: bool
    '''
    for rel in self._outgoing:
      if filtr(rel):
        yield rel, rel._dst if localOnly else rel.dst
    for rel in self._incoming:
      if rel.isSymmetric() and filtr(rel):
        yield rel, rel._src if localOnly else rel.src

  def _getIncoming(self, filtr:Callable[[Relation], bool]=lambda _: True, 
                   localOnly:bool=False) -> Generator[tuple[Relation, GraphObject|None]]:
    '''
    This method should be used to access all incoming relations.  It will automatically
    include any symmetric relations.
    '''
    for rel in self._incoming:
      if filtr(rel):
        yield rel, rel._src if localOnly else rel.src
    for rel in self._outgoing:
      if rel.isSymmetric() and filtr(rel):
        yield rel, rel._dst if localOnly else rel.dst
        
  def _addToStatusReport(self, cond:bool, msg:str, severity:str='E') -> None:
    '''
    Conditionally logs an line in the status report for the object.
    
    :param cond: A conditional expression that if False will cause an entry in
      the status report.
    :type cond: bool:
    :param msg: A message to print in the status report if *cond* is False.
    :type msg: str
    :param severity: A one-character severity code: F (fatal), E (error), 
      W (warning), I (informational)
    :type severity: str
    :returns: None
    '''
    if not cond:
      self._statusReport.append((severity, msg))
    
  def validate(self) -> list[str]:
    #ret:list[str] = []
    self._statusReport = []
        
    #check that Python types correspond to SN types.
    if type(self) is GraphObject:
      self._addToStatusReport(self.id == 1, 
            'The only GraphObject should be top', 'E')
    elif type(self) is Node:
      # can't use .isa() for this as getParents() will create an isa to NODE.
      self._addToStatusReport(self is self.model.NODE or self.model.NODE in self.getSupers(), 
            'All Node objects should be explicit isa-children of "node"', 'W')
      self._addToStatusReport(not self.isa(self.model.RELATION),
            'Node object isa relation')
    elif type(self) is Relation:
      self._addToStatusReport(self is self.model.RELATION or self.model.RELATION in self.getSupers(),
            'All Relation objects should be explicit isa-children of "relation".', 'W')
      self._addToStatusReport(not self.isa(self.model.NODE),
            'Relation object isa node')
    elif type(self) is Collection:
      self._addToStatusReport(self is self.model.COLLECTION or self.model.COLLECTION in self.getSupers(),
            'All Collection objects should be explicit isa-children of "collection".', 'W')
      self._addToStatusReport(not self.isa(self.model.RELATION),
            'Collection object isa relation')
    elif type(self) is IsaIndividual:
      pass
    else:
      self._addToStatusReport(False,
            f'Unexpected type {self.__class__.__name__}')
    return self.statusReport()
  
  def statusReport(self) -> list[str]:
    ret:list[str] = []
    for sev, text in self._statusReport:
      ret.append(f'{sev}: {text}')
    return ret
  
  def status(self) -> str:
    stats:list[tuple[str,str]] = self._statusReport
    priority = 'IWEF'
    pos:int = -1
    if not stats:
      return ''
    for s,_ in stats:
      p = priority.find(s) 
      if p > pos:
        pos = p
    assert pos>=0
    return priority[pos]
  
  _STATUS:dict[str,int] = {
    '':0,
    'E':-1,
    'F':-2,
    'I':1,
    'W':2
    }
  
  def statsInt(self):
    return self._STATUS[self.status()]    
    
  def _isConnected(self):
    return self.id in self.db

  def _disconnect(self) -> None:
    '''
    Disconnect this object from it's *Model* by:
    
      - unregistering it with the *Model*
      - unregistering (from other objects) the far ends of the relations, but keeping the close 
        ends intact so that they may be later restored if necessary
      - unregistering all the above relations with the *Model*
      
    .. Note::

      User this method when deleting an object with the potential to undo the 
      deletion.  Keep a pointer to the object and undo the deletion by calling
      its _reconnect() method.
    '''
    #TODO: This is a potential problem for chains of transitive relations.
    assert self._isConnected()
    
    children = self.getChildren()
    
    # unregister from the model
    self.db._unregister(self._id)

    # disconnect from related-to objects
    for r,_ in self._getIncoming():
      r._disconnect(keep=self)
    for r,_ in self._getOutgoing():
      r._disconnect(keep=self)
      
    for child in children: #TODO: could be more efficient by just fixing the parentCache's.
      child.retract()
    
  def _reconnect(self):
    '''
    Reconnect this disconnected object to it's *Model* by:
    
      - reregistering it to the *Model*
      - reregistering (to other objects) the far ends of the relations 
      - reregistering all the above relations with the *Model*
      
    .. Note::
    
      This method should only be used to undo a _disconnect() operation.
      
    '''
    assert not self._isConnected()
    
    # unregister from the model
    self.db._register(self, self._id)

    # disconnect from related-to objects
    for r,_ in self._getIncoming():
      r._reconnect(kept=self)
    for r,_ in self._getOutgoing():
      r._reconnect(kept=self)

    for child in self.getChildren(): #TODO: could be more efficient by just fixing the parentCache's.
      child.retract()
      
  def retract(self):
    '''
    Resets the parent cache of this object and all isa-decendents of this object.
    '''
    self._parentsCache = None
    for child in self.getChildren():
      child.retract()

  #def getSupers(self)->list[GraphObject]: #xtype: ignore[override]
  @override
  def getSupers[GraphObject](self, asTree:bool=False, rmDups:bool=True) -> list:
    '''
    :returns: A list of all super types to this object in mro order.
    :rtype: list[GraphObject]
    '''
    ret:list = []
    for parent in self.getParents(): #gather ancestors in mro order
      if parent not in ret: #TODO: this test will likely fail in the the "asTree" case...
        ret.append(parent)
        if asTree:
          ret.append(parent.getSupers(asTree=asTree, rmDups=rmDups))
        else:
          ret += parent.getSupers(asTree=asTree, rmDups=rmDups)
    if rmDups:
      ret = removeDuplicates(ret, asTree=asTree)
    return ret
  
  @overload
  def isa(self, typ:GraphObject) -> bool: ...
  @overload
  def isa(self, typ:None=None, asTree:bool=False, rmDups:bool=True) -> list: ...
  def isa(self, typ:GraphObject|None=None, asTree:bool=False, rmDups:bool=True) -> list|bool:
    '''
    If *typ* is not specified returns a list if isa-ancestors to this object; if *typ*
    is specified returns True iff *typ* is an isa-ancestor of this object.
    '''
    if asTree and typ is None:
      ret:list = [self]
      ret.append(self.getSupers(asTree=asTree, rmDups=rmDups))
      return ret
    ret = [self]+self.getSupers(asTree=asTree, rmDups=rmDups)
    return ret if typ is None else typ in ret
    
  def getParents(self)->list[GraphObject]:
    '''
    Return the immediate parents of this object. As a side effect, it cleans
    up any inferred isa relations that are superseded by explicit relations.
    
    :returns: The immediate parents of this object by iterating the *IsaIndividuals*
      in *self._getOutgoing()*.
    :rtype: list[GraphObject]
    '''
    # dispose of an inferred parents that can be dropped
    #TODO: This could be very computationally expensive...
    # more:bool = True
    # rel:Relation
    # other:GraphObject
    # while more:
    #   more = False
    #   relsAndParents = list(self._getOutgoing(lambda r: isinstance(r, IsaIndividual)))
    #   for rel,parent in relsAndParents:
    #     if rel.inferred:
    #       if parent in treeFlatten([p.getSupers() for r,p in relsAndParents if not r.inferred and p is not None]):
    #         rel._disconnect(keep=None)
    #         more = True
    #         break
    
    if self._parentsCache is not None and self.model._allowParentsCaching:
      return self._parentsCache
    
    ret = [other for _rel,other in self._getOutgoing(lambda r: isinstance(r, IsaIndividual)) if other is not None] 
    if ret == [] and type(self) is not GraphObject:
      raise LookupError("No parent found.")
    if self in ret:
      logger.error(f'{self.model.url}#{self._id} has itself as parent. {[go._id for go in ret]}')
      raise RecursionError(f'{self.model.url}#{self._id} has itself as parent. {[go._id for go in ret]}')
      ret.remove(self)

    self._parentsCache = ret
    return ret   

  def getDescendants(self, model:Model|None=None, asTree:bool=False, rmDups:bool=True)->list:
    '''
    :param model: If this is given, the descendents are limited to those in the 
      model. This is necessary for things like the ISA type which may be stored
      in a super-model and could otherwise return every isa individual in all 
      the models. ISA will return [] if *model* is not given. By default, the 
      descendants are limited to the model of *self*.
    :type model: Model
    :returns: A list of all decendents to this object.
    :rtype: list[GraphObject]
    '''
    if model is None:
      model = self.model
    if self.name == "isa" and self.isType() and model is not None:
      return [r for r in model.values() if isinstance(r, IsaIndividual)]
    ret:list = []
    for child in self.getChildren(): 
      ret.append(child)
      if asTree:
        ret.append(child.getDescendants(asTree=asTree, rmDups=rmDups))
      else:
        ret += child.getDescendants(asTree=asTree, rmDups=rmDups)
    if rmDups:
      ret = removeDuplicates(ret, asTree=asTree)
    return ret
    

  def getChildren(self)->list[GraphObject]:
    '''
    :returns: The immediate isa-children of this object by iterating the *IsaIndividuals*
    in *self._getIncoming()*.
    :rtype: list[GraphObject]
    '''
    if self.isIndividual():
      return []
    return [other for _rel,other in self._getIncoming(lambda r: isinstance(r, IsaIndividual)) if other is not None]    

  @overload
  def getRelatedTo(self, *, _seen:set[int]|None=None)                         -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def getRelatedTo(self, rel:Relation|None=None, *, _seen:set[int]|None=None) -> list[GraphObject]: ...
  def getRelatedTo(self, rel:Relation|None=None, *, _seen:set[int]|None=None) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    # def isSeen(obj):
    #   if obj in seen:
    #     return True
    #   seen.append(obj)
    seen:set[int] = set() if _seen is None else _seen
    if self.id in seen:
      return []
    else:
      seen.add(self.id)
    ret:list[tuple[Relation,GraphObject]] = []
    r: Relation
    filtr:Callable[[Relation], bool] = (lambda r: True) if rel is None else (cast(Callable[[Relation], bool], lambda r, typ=rel: r.isa(typ)))
    for r,other in self._getOutgoing(filtr):
      if other is not None:
        ret.append((r, other))
        #seen.add(other.id)
        if r.isTransitive() and other is not self:
          # add in any transitives, filtering out anything we already refer to
          ret += [ret2 for ret2 in other.getRelatedTo(_seen=seen) if filtr(r)]
        if r.isReflexive() and other is not self and self not in seen:
          ret.append((r, self))
    if len(ret) == 0:
      return []
      
    if rel is not None: # and not _returnPairs:
      ret2:list[GraphObject] = list(list(zip(*ret))[1]) # return only the objects
      if rel.isIrreflexive():
        return [x for x in ret2 if x is not self]
      return ret2
    
    return [(r,o) for r,o in ret if not(r.isIrreflexive() and o is self)] # return the rel/object pairs

  @overload
  def isRelatedTo(self) -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def isRelatedTo(self, rel:Relation) -> list[GraphObject]: ...
  @overload
  def isRelatedTo(self, rel:Relation, obj:GraphObject) -> bool: ...
  def isRelatedTo(self, rel:Relation|None=None, obj:GraphObject|None=None) -> bool|list[GraphObject]|list[tuple[Relation,GraphObject]]:
    if obj is None:
      return self.getRelatedTo(rel)
    else:
      return obj in self.getRelatedTo(rel, _seen=set())
    
  @overload
  def getRelatedFrom(self)                         -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def getRelatedFrom(self, rel:Relation|None=None) -> list[GraphObject]: ...
  def getRelatedFrom(self, rel:Relation|None=None) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    # if rel is not None:
    #   return [other for _rel,other in self._getIncoming(lambda r, typ=rel: r.isa(typ)) if other is not None] #type: ignore[misc]
    # else:
    #   return [(rel,other) for rel,other in self._getIncoming() if other is not None]    
    ret:list[tuple[Relation,GraphObject]] = []
    r: Relation
    filtr:Callable[[Relation], bool] = (lambda r: True) if rel is None else (cast(Callable[[Relation], bool], lambda r, typ=rel: r.isa(typ)))
    for r,other in self._getIncoming(filtr):
      if other is not None:
        ret.append((r, other))
        seen = [] if ret == [] else list(list(zip(*ret))[1])
        if r.isTransitive() and other is not self:
          # add in any transitives, filtering out anything we already refer to
          ret += [ret2 for ret2 in other.getRelatedFrom() if ret2[1] not in seen and filtr(r)]
        # if r.isReflexive() and other is not self and self not in seen:
        #   ret.append((r, self))
        # if r.isSymmetric():
        #   pass
    if rel is not None: # and not _returnPairs:
      return list(list(zip(*ret))[1]) # return only the objects
    return ret # return the rel/object pairs


  @overload
  def isRelatedFrom(self) -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def isRelatedFrom(self, rel:Relation) -> list[GraphObject]: ...
  @overload
  def isRelatedFrom(self, rel:Relation, obj:GraphObject) -> bool: ...
  def isRelatedFrom(self, rel:Relation|None=None, obj:GraphObject|None=None) -> bool|list[GraphObject]|list[tuple[Relation,GraphObject]]:
    if obj is None:
      return self.getRelatedFrom(rel)
    else:
      return obj in self.getRelatedFrom(rel)
    
  @override
  def isIndividual(self)->bool:
    return self._individual

  @property
  @override
  def name(self)->str:
    try:
      ret = self["name"]
    except:
      ret = "?"
    if ret is NOVALUE:
      ret = "<name not set>"
    assert isinstance(ret, str)
    return ret
  
  @property
  def db(self) -> Model:
    return cast(Model, super().db) # this is a purposeful violation of the subsumption principle
  
  @override
  def __repr__(self):
    return self.torepr()
  
  @override
  def torepr(self, relativeTo:Model|None=None):
    return f'{self.tostring(relativeTo)} @ {self.getPRef().tostring(relativeTo)}'
  
  @override
  def __str__(self) -> str:
    return self.tostring()
  
  @override
  def tostring(self, relativeTo:Model|None=None) -> str:
    name = self.getLocal("name", None)
    if name is None:
      name = f'{UP_ARROW}"{self.get("name")}"'
    else:
      name = f'"{self.get("name")}"'
    return f'{self.__class__.__name__}({name}, {self.getPRef().tostring(relativeTo)}, <{"individual" if self.isIndividual() else "type"}{", <inferred>" if self.inferred else ""}>)'
  
  @override
  def __eq__(self, other:object):
    return PRObject.__eq__(self, object)
  
  @override
  def __hash__(self): #type: ignore[override]
    return PRObject.__hash__(self)
  
  @override
  def __delitem__(self, key:str)->None:
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    super().__delitem__(key)
  
  @override
  def __setitem__(self, key:str, value:SerializableType)->None:
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    super().__setitem__(key, value)
  
  @override
  def setAttr(self, key:str, attr:Attribute) -> None:
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    super().setAttr(key, attr)
    
    
class Model(PRDb[GraphObject], Subject):
  '''
  .. Note::
  
    *Model* is a **subclass** but not strictly a **subtype** of *PRDb* as it restricts
    its member objects to be subtypes of :py:class:`GraphOBject`.
    
  .. Note::
  
    To open an existing Model use :py:meth:`Model.getDB`, which will fail if
    the *Model* isn't in memory and can't be read from a file. To create a **new**
    *Model* use it's Construction (*Model(<url>)*).
    
  '''

  @override
  @classmethod
  def _initCache(cls):
    '''
    Re-initializes the Model cache. 
    
    .. Warning::
    
       This should only be used for testing purposes (eg: unit testing) as it wipes
       the DB cache and could cause bad pointers in any interface applications.
    
    .. Note::
    
      Creates a brand new base Model.
    '''
    PRDb._initCache()
    from sn.model import TopModel
    model = TopModel("sn:///sn", mode="", _reading=False) # creates a model in memory cache
    model._writeLocked = True
    
  def __init__(self, url:str, mode:str="w", _reading:bool=False):
    '''
    Constructor
    '''
    PRDb.__init__(self, url, mode=mode, _reading=_reading)
    Subject.__init__(self)
    
    self._allowParentsCaching:bool = False

    sn:Model = cast(Model, GORef.eval("$sn"))
    if sn not in self.superDBs:
      self.superDBs.append(sn) #type: ignore[arg-type]
    
    self.TOP:GraphObject = GORef.eval("$sn#top") #type: ignore[assignment]
    self.RELATION:Relation = GORef.eval("$sn#relation") #type: ignore[assignment]
    self.ISA:Relation = GORef.eval("$sn#3") #type: ignore[assignment]
    self.NODE:Node = GORef.eval("$sn#node") #type: ignore[assignment]
    self.REFLEXIVE:Relation = GORef.eval("$sn#reflexive") #type: ignore[assignment]
    self.IRREFLEXIVE:Relation = GORef.eval("$sn#irreflexive") #type: ignore[assignment]
    self.SYMMETRIC:Relation = GORef.eval("$sn#symmetric") #type: ignore[assignment]
    self.TRANSITIVE:Relation = GORef.eval("$sn#transitive") #type: ignore[assignment] 
    self.EQUALITY:Relation = GORef.eval("$sn#equality") #type: ignore[assignment]
    self.COLLECTION:Collection = GORef.eval("$sn#collection") #type: ignore[assignment]

    if hasattr(self, "_initialized") or _reading: # This means the __new__ method has returned an existing object, so don't truck over it!
      return

    self.nextID:int = 256
    self._dirty = False
    
  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    ret:InstantiationInfo = super().getInstantiationInfo()
    ret.class_ = cls
    ret.finalSetters.append(PropertyInfo("_", bool, setter=lambda slf,_t:cast(Model,slf).setDirty(False)))
    return ret

  @override
  @classmethod
  def getDB(cls, url:str, mode="w") -> Model:
    '''
    Override of the super() version to specificatlly return a Model.
    '''
    if url in ("sn","$sn"):
      url = "sn:/sn.xml"
      mode = ""
    ret = super().getDB(url, mode=mode)
    if not isinstance(ret, Model):
      raise TypeError(f'Database "{url}" is of type {ret.__class__.__name__}; expected type Model."')
    return ret
      
  @override
  def _register(self, value: GraphObject, _id:Optional[int]=None) -> int: # type: ignore[override]
    '''
    Overrides the 
    :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
    to restrict contained objects to :py:class:`GraphObject` subtypes. 
    *This violates subsumption rules, but that's what we want here!* 
    
    Also sets the dirty bit and notifies any observers ("add GraphObject" (GraphObject))
    '''
    assert isinstance(value, GraphObject), \
        f'Models are restricted to containing only GraphObject subtypes; got a {value.__class__.__name__} type.'
    self.setDirty()
    ret = super()._register(value, _id)
    with Subject.ChangeMgr(self, later=True) as cm:
      cm.registerTopics(("add GraphObject", (ret, value)))
    return ret
    
  def _unregister(self, _id:int) -> None:
    '''
    Overrides the 
    :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
    to also set the dirty bit and notify any observers () 
    '''
    super()._unregister(_id)
    self.setDirty()
    self.notify(("del GraphObject", (_id,)))
    
  def setDirty(self, value:bool=True) -> bool:
    '''
    An object is dirty if it has been modified and should probably be
    saved on exit.  This should be called from all methods that modify
    the state of this object.
    
    If *value* is False, resets all the contained *Attributes* to False.
    
    :param value: (default True) The value to set *dirty* to.
    :type value: bool
    '''
    assert type(value) is bool
    if not value:
      obj:GraphObject
      for obj in self._db.values():
        if obj.isDirty():
          obj.setDirty(False)
    self._dirty = value
    return self._dirty
    
  def isDirty(self) -> bool:
    '''
    Returns True iff the object (or an of it's contained *Attributes*) have 
    been modified and should probably be saved on exit. 
    '''
    if self._dirty:
      return True
    obj:GraphObject
    for obj in self._db.values():
      if obj.isDirty():
        self._dirty = True
        return True
    return False
  
  @override
  def save(self, saveas:Optional[str]=None, overwrite=False, format:str="XML") -> None:
    super().save(saveas=saveas, overwrite=overwrite, format=format)
    self.setDirty(False)

  def validate(self) -> list[tuple[GraphObject,list[str]]]:
    ret:list[tuple[GraphObject,list[str]]] = []
    go:GraphObject
    for go in self.values():
      res = go.validate()
      if res:
        ret.append((go, res))
    return ret
  
  @override
  def _makeDBContainer(self) -> AllModelCollection:
    return AllModelCollection(self)


# class TopModel(Model):
#   def __init__(self, url:str, mode:str="", _reading:bool=False):
#     Subject.__init__(self)
#     PRDb.__init__(self, url, mode="")
#     self._allowParentsCaching:bool = False
#     self.TOP:GraphObject = GraphObject(self, [])
#     # these re-assignments from a ValidationList to a list are necessary in 
#     # these top types as they will violate the ValidationList constraints. 
#     self.TOP._outgoing.checking(False) 
#     self.TOP._incoming.checking(False)
#     self.RELATION:Relation = Relation(self, [], self.TOP, self.TOP)
#     self.RELATION._outgoing.checking(False)
#     self.RELATION._incoming.checking(False)
#     self.ISA:Relation = Relation(self, [], self.TOP, self.TOP)
#     self.ISA._outgoing.checking(False)
#     self.ISA._incoming.checking(False)
#     IsaIndividual(self, self.RELATION, self.TOP) # can't do this until after ISA exists
#     isaisa:IsaIndividual = IsaIndividual(self, self.ISA, self.RELATION)
#
#     # now that we have the isa defined, fix up the name attribute (as it involves inheritance) 
#     self.TOP.setAttr("name", Attribute("top", str, VAR_DEFAULTED))
#     if self.TOP._id != 1:
#       raise Exception("TopModel.__init__() called twice.")
#     self.RELATION.setAttr("name", Attribute("relation", None, TYPENAME)) # can't do this until AFTER ISA exists.
#     self.ISA["name"] = "isa"
#     self.NODE:Node = Node(self, [self.TOP])
#     self.NODE.setAttr("name", Attribute("node", None, VAR)) # can't do this until AFTER ISA exists.
#
#     # add it the basic relation types
#     self.REFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="reflexive")
#     self.REFLEXIVE["reflexive"] = True
#     self.IRREFLEXIVE:Relation = Relation(self, [self.RELATION], individual=False, name="irreflexive")
#     self.IRREFLEXIVE["irreflexive"] = True
#     self.SYMMETRIC:Relation = Relation(self, [self.RELATION], individual=False, name="symmetric") 
#     self.SYMMETRIC["symmetric"] = True
#     self.TRANSITIVE:Relation = Relation(self, [self.RELATION], individual=False, name="transitive") 
#     self.TRANSITIVE["transitive"] = True
#
#     # fix up the ISA relation type so it inherits from REFLEXIVE and TRANSITIVE
#     assert isinstance(isaisa, IsaIndividual)
#     isaisa.connect(destination=self.REFLEXIVE)
#     IsaIndividual(self, self.ISA, self.TRANSITIVE)
#
#     self.EQUALITY:Relation = Relation(self, [self.REFLEXIVE, self.SYMMETRIC, self.TRANSITIVE], name="equality")
#
#     # add in a base context node
#     self.COLLECTION:Collection = Collection(self, [self.NODE], [], individual=False, name="collection")
#
#     self[0] # causes the "all model" collection to be instantiated.
#     self._allowParentsCaching = True




  
          
class Node(GraphObject):
  
  def getParents(self)->list[GraphObject]:
    '''
    :returns: The immediate parents of this object by iterating the *IsaIndividuals*
      in *self._getOutgoing()*. If no parent is explictly found a inferred 
      *isaIndividual* is created to *model.NODE* and the *model.NODE* object
      is returned.
    :rtype: list[GraphObject]
    '''
    try:
      return super().getParents()
    except LookupError:
      if self is self.model.NODE:
        return [self.model.TOP]
      # isa = IsaIndividual(self.model, self, self.model.NODE)
      # isa.inferred = True
      return [self.model.NODE]
    
    
class Collection(Node):
  
  def __init__(self, db:Model, parents:Iterable[GraphObject]=[], members:Iterable[GraphObject]=[], individual:bool=False, name:Optional[str]=None):
    super().__init__(db, parents, individual=individual, name=name)
    self.members:list[GraphObject] = list(members)
    
  def addMember(self, member:GraphObject):
    if member not in self.members:
      self.members.append(member)
      self.setDirty()
      
  def removeMember(self, member:GraphObject):
    self.members.remove(member)
    self.setDirty()
    
  def getMembers(self) -> Iterator[GraphObject]:
    for member in self.members:
      yield member

  def isMember(self, obj:GraphObject) -> bool:
    return obj in self.members
  
  def countMembers(self) -> int:
    return len(self.members)

  def getParents(self)->list[GraphObject]:
    '''
    :returns: The immediate parents of this object by iterating the *IsaIndividuals*
      in *self._getOutgoing()*. If no parent is explictly found a inferred 
      *isaIndividual* is created to *model.NODE* and the *model.NODE* object
      is returned.
    :rtype: list[GraphObject]
    '''
    try:
      return super().getParents()
    except LookupError:
      if self is self.model.COLLECTION:
        return [self.model.NODE]
      # isa = IsaIndividual(self.model, self, self.model.COLLECTION)
      # isa.inferred = True
      return [self.model.COLLECTION]
    
  @override
  def tostring(self, relativeTo:Model | None=None) -> str:
    return f'{super().tostring(relativeTo)[:-1]}, {self.countMembers()} members)'
  
  @override
  def torepr(self, relativeTo:Model | None=None) -> str:
    ret = self.tostring(relativeTo)+":"
    for m in self.getMembers():
      ret += (f'\n    {m.tostring(relativeTo)}')
    return ret
    
class AllModelCollection(Collection, PRDbContainer):
  def __init__(self, model:Model):
    Collection.__init__(self, model, [Model.getDB("$sn").COLLECTION], individual=True, name=model.name)
    PRDbContainer.__init__(self, model)
  
  @override
  def addMember(self, member:GraphObject):
    raise PermissionError("Cannot add members to an AllModelCollection. To add an object, add it to the Model.")
      
  @override
  def removeMember(self, member:GraphObject):
    raise PermissionError("Cannot remove members to an AllModelCollection. To remove an object, remove it from the Model.")
    
  @override
  def getMembers(self) -> Iterator[GraphObject]:
    for member in list(self.db.values()):
      yield member

  @override
  def isMember(self, obj:GraphObject) -> bool:
    return obj in self.db._db
  
  @override
  def countMembers(self) -> int:
    return len(self.db._db)
    
    
  
class Relation(GraphObject):
  def __init__(self, db:Model, 
               parents:Iterable[GraphObject]=[], 
               src:GraphObject|None=None, 
               dst:GraphObject|None=None, 
               individual:bool=False, 
               name:Optional[str]=None):
    if not db.reading:
      for p in parents:
        assert not hasattr(db, "RELATION") or isinstance(p, Relation)
    super().__init__(db, parents, individual=individual, name=name)
    
    self._symmetric:bool|None = None
    self._reflexive:bool|None = None
    self._irreflexive:bool|None = None
    self._transitive:bool|None = None

    self._dst:GraphObject|None = None
    self._src:GraphObject|None = None
    if db.reading:
      self._dst = dst
      self._src = src
    else:
      self.connect(source=src, destination=dst)
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.
    '''
    ret = GraphObject.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(Relation, slf).db)],
            conKWArgs=[ParamInfo("individual", bool, lambda slf: cast(Relation, slf)._individual)],
            postconSetters=ret.postconSetters,
            finalSetters=ret.finalSetters+
                          [PropertyInfo("src", str, 
                                        lambda slf: GORef.formatForURL(slf._src, slf.db), #type: ignore[attr-defined]
                                        lambda slf, source: slf.connect(source=GORef.eval(source, slf.db)) if source is not None and source!="None" else None), #type: ignore[attr-defined, arg-type]
                           PropertyInfo("dst", str, 
                                        lambda slf: GORef.formatForURL(slf._dst, slf.db), #type: ignore[attr-defined]
                                        lambda slf, dest  : slf.connect(destination=GORef.eval(dest, slf.db)) if dest is not None and dest!="None" else None)] #type: ignore[attr-defined, arg-type]
                          # [PropertyInfo("src_", GraphObject, lambda slf: PReference(slf._src), lambda slf, source: slf.connect(source=source)),
                          #  PropertyInfo("dst_", GraphObject, lambda slf: slf.dst, lambda slf, dest  : slf.connect(destination=dest))]
            )
    # return InstantiationInfo(
    #         cls, 
    #         conArgs=[ParamInfo("db", Model, lambda slf: cast(GraphObject, slf).db)],
    #         conKWArgs=[ParamInfo("individual", bool, lambda slf: cast(GraphObject,slf)._individual)],
    #         postconSetters=atObject.postconSetters + prObject.postconSetters,
    #         finalSetters=atObject.finalSetters + prObject.finalSetters
    #         )

  @property
  def dst(self, localOnly:bool=False) -> GraphObject|None: #GraphObject|None:
    '''
    :return: The **calculated* destination of this relation; ie: if this relation
      does not have a specific destination, look it up in the ISA hierarchy.
    '''
    if localOnly or self._dst is not None:
      return self._dst
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        assert isinstance(obj, Relation)
        if obj._dst is not None:
          return obj._dst
    return None
  
  @dst.setter
  def dst(self, obj:GraphObject):
    # if self._legalDst(obj):
    #   self._dst = obj
    self.connect(destination=obj)
    assert self._dst is obj
    self.setDirty()
    
  @property
  def src(self, localOnly:bool=False) -> GraphObject|None: #GraphObject|None:
    '''
    :return: The **calculated* source of this relation; ie: if this relation
      does not have a specific source, look it up in the ISA hierarchy.
    '''
    if localOnly or self._src is not None:
      return self._src
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        assert isinstance(obj, Relation)
        if obj._src is not None:
          return obj._src
    return None
  
  @src.setter
  def src(self, obj:GraphObject):
    # if self._legalSrc(obj):
    #   self._src = obj
    self.connect(source=obj)
    assert self._src is obj
    self.setDirty()
      
  def retract(self):
    '''
    Retract the inferences about this object.  In this case,
    retract settings for isSymmetric(), isReflexive(), isTransitive(). They 
    will automatically be recalculated next time they are used.
    '''
    self._symmetric = None
    self._reflexive = None
    self._transitive = None
    
  def _legalDst(self, obj:GraphObject) -> bool:
    #TODO: need to fill out _legalDst
    return True
    
  def _legalSrc(self, obj:GraphObject) -> bool:
    #TODO: need to fill out _legalSrc
    return True
  
  @override
  def validate(self) -> list[str]:
    if self._src is not None:
      self._addToStatusReport(self in self._src._outgoing, f'src end is not registered with src object, {self._src}', 'E')
    if self._dst is not None:
      self._addToStatusReport(self in self._dst._incoming, f'dst end is not registered with dst object, {self._dst}', 'E')
    return self.statusReport()
    
  def isReflexive(self):
    if self._reflexive is None:
      self._reflexive = bool(self.get("reflexive", False))
    return self._reflexive
  
  def isIrreflexive(self):
    if self._irreflexive is None:
      self._irreflexive = bool(self.get("irreflexive", False))
    return self._irreflexive
  
  def isSymmetric(self):
    if self._symmetric is None:
      try: # fails during in itialization
        self._symmetric = bool(self.get("symmetric", False))
      except:
        self._symmetric = False
    return self._symmetric
  
  def isTransitive(self):
    if self._transitive is None:
      self._transitive = bool(self.get("transitive", False))
    return self._transitive
    
  def getParents(self)->list[GraphObject]:
    '''
    :returns: The immediate parents of this object by iterating the *IsaIndividuals*
      in *self._getOutgoing()*. If no parent is explictly found a inferred 
      *isaIndividual* is created to *model.RELATION* and the *model.RELATION* 
      object is returned.
    :rtype: list[GraphObject]
    '''
    try:
      return super().getParents()
    except LookupError:
      if self is self.model.RELATION:
        return [self.model.TOP]
      try: # this will fail during initialization, so ignore it in that case...
        # isa = IsaIndividual(self.model, self, self.model.RELATION)
        # isa.inferred = True
        return [self.model.RELATION]
      except AttributeError:
        return []

  @override
  def tostring(self, relativeTo:Model|None=None) -> str:
    def makeStr(o:GraphObject|None, inherited:bool) -> str:
      if o is None:
        return 'None'
      return f'{UP_ARROW if inherited else ""}{o.getPRef().tostring(self.db if relativeTo is None else relativeTo)}'
    ret = super().tostring(relativeTo=relativeTo)
    # return f'{ret[:-1]}, {makeStr(self.src, self._src is None)} {RIGHT_ARROW} {makeStr(self.dst, self._src is None)}{ret[-1]}'
    return f'{ret[:-1]}, {makeStr(self.src, self._src is None)} {makeRelationArrow(self)} {makeStr(self.dst, self._dst is None)}{ret[-1]}'
    #return f'{ret[:-1]}, {UP_ARROW if self._src is None else self._src._id} {"makeRelationArrow(self)"} {UP_ARROW if self._dst is None else self._dst._id}{ret[-1]}'
  
  def __hash__(self): #type: ignore[override]
    return super().__hash__()
  
  def connect(self, source:Optional[GraphObject]=None, destination:Optional[GraphObject]=None):
    '''
    Connects or re-assigns the *src* and/or *dst* links by removing any existing
    links and setting the pointers in both this *Relation* and the target
    *GraphObjects*.
    
    .. Note::
    
      Use this method during Relation construction or when modifying the source 
      and/or destination of the Relation. This method ONLY applies to *Relations*.
      (contrast :py:method:`GraphObject._disconnect` and 
      :py:method:`GraphObject._reconnect`) 
    
    :param source: The :py:class:`GraphObject` for the *src* link.
    :type source: GraphObject
    :param destination: The :py:class:`GraphObject` for the *dst* link.
    :type destination: GraphObject
    '''
    if source is not None:
      if self._src is not source: # don't do anything if it's already done.
        if self._src is not None:
          delOne(self._src._outgoing, self)
        self._src = source
        source._outgoing.append(self)
        assert self in source._outgoing
        self.setDirty()
    if destination is not None:
      if self._dst is not destination: # don't do anything if it's already done.
        if self._dst is not None:
          delOne(self._dst._incoming, self)
        self._dst = destination
        destination._incoming.append(self)
        assert self in destination._incoming
        self.setDirty()
    
  @override
  def _reconnect(self, kept:GraphObject|None=None):
    if self._src is not None and self._src is not kept:
      self._src._outgoing.append(self) 
    if self._dst is not None and self._dst is not kept:
      self._dst._incoming.append(self)
    super()._reconnect()
    self.setDirty()
   
  @override
  def _disconnect(self, keep:GraphObject|None=None) -> None: #type: ignore[override]
    '''
    Disconnects this relation from it's src and dst by removing the pointers
    from the src and dst objects. The pointers **to** these object (in this
    relation) are kept intact. This relation is also removed from it's
    containing *Model* object (it is removed from the Model's list, but
    it's *db* pointer remains intact.
    
    This is typically useful for undo operations where, for example, a delete
    operation on an object can be undone by disconnecting the object, saving
    it, and if it on deletion and then re-connecting it if the delete is undone.
    
    :param source: [default: *False*] Iff True the *src* side is disconnected.
    :type source: bool  
    :param destination: [default: *False*] Iff True the *dst* side is disconnected.
    :type destination: bool  
    '''
    if self._src is not None and self._src is not keep:
      delOne(self._src._outgoing, self) 
    if self._dst is not None and self._dst is not keep:
      delOne(self._dst._incoming, self) 
    super()._disconnect()
    self.setDirty()
    
class IsaIndividual(Relation):
  def __init__(self, db:Model, src:GraphObject|None=None, dst:GraphObject|None=None):
    if not db.reading:
      if src is None or dst is None:
        raise ValueError("IsaIndividual.__init__(): ISA relations require both a source and destination.")
    super().__init__(db, [], src, dst, individual=True)
    
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.
    '''
    sup = Relation.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(Relation, slf).db)], # no conKWargs
            postconSetters=sup.postconSetters,
            finalSetters=sup.finalSetters
            )

  @override
  def getSupers[GraphObject](self, asTree:bool=False, rmDups:bool=True) -> list:
    if asTree:
      return [self.db.ISA, [self.db.RELATION, [self.db.TOP]]]
    else:
      return [self.db.ISA, self.db.RELATION, self.db.TOP]
  
  @override
  def getParents(self)->list[GraphObject]:
    return [self.db.ISA]  
  
  # @override
  # def isa(self, typ:GraphObject|None=None, asTree:bool=False, rmDups:bool=True) -> list|bool:
  #   if asTree and typ is None:
  #     if rmDups:
  #       return [self, 
  #               [self.model.ISA, 
  #                [self.model.REFLEXIVE, 
  #                 [self.model.RELATION, self.model.TOP], 
  #                 self.model.TRANSITIVE]]]
  #     else:
  #       return [self, 
  #               [self.model.ISA, 
  #                [self.model.REFLEXIVE, 
  #                 [self.model.RELATION, self.model.TOP], 
  #                 self.model.TRANSITIVE,
  #                 [self.model.RELATION, self.model.TOP]]]]
  #   else:
  #     if rmDups:
  #       return [self, self.model.ISA, self.model.REFLEXIVE, self.model.RELATION, self.model.TOP, self.model.TRANSITIVE]
  #     else:
  #       return [self, self.model.ISA, self.model.REFLEXIVE, self.model.RELATION, self.model.TOP, self.model.TRANSITIVE, self.model.RELATION, self.model.TOP]
  #
  #

  
  @override
  def connect(self, source:Optional[GraphObject]=None, destination:Optional[GraphObject]=None):
    retract = source      is not None and source      is not self._src or \
              destination is not None and destination is not self._dst  
    super().connect(source, destination)
    if retract: #TODO: could be a lot more efficient by just fixing the parentCache's.
      self.retract()
    self.setDirty()
    
    
