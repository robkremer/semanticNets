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
from util.persistence.serialize import DEFAULT_STRATEGY
from util.utils import removeDuplicates, delOne
from typing import override, cast, Generator, Callable, Optional,\
  Iterable, overload, Iterator, Any
from util.attribute import AttributedObject, Attribute, VAR, TYPENAME,\
  UNRESTRICTED, VAR_DEFAULTED, NOVALUE
from util.validatedList import ValidatedList
#from docutils.nodes import description
import logging
from util.observer import Subject
import sn
from util.dirtyable import Dirtyable
from util.abstractGraph import AGRelation, AbstractGraph, AGObject
from util.errorReportingObject import ErrorReportingObject
from sn.model.snAttribute import SNAttributedObject

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
  '''
  :param rel:
  :type rel: Relation
  :returns:
  :rtype: str
  '''
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

class GraphObject(AGObject["Model", "Relation"], SNAttributedObject, ErrorReportingObject):
  '''
  .. Note::
  
    *GraphObject* is a **subclass** but not strictly a **subtype** of *PRObject* as 
    its container object pointer (*Model*) is subtype of the its parent's pointer
    (*PRDb*).
  '''
  
  def __init__(self, db:Model, parents:Iterable[GraphObject]=[], individual:bool=False, name:Optional[str]=None, **kwargs):
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
    :param kwargs: Passed on to *super().__init__()*. *GraphObject* is normally
      combined with *AGRelation* via multiple inheritance (see *Relation*),
      and the two share *AGObject* as a common ancestor -- calling *super()*
      cooperatively here (instead of naming *AGObject* and *AttributedObject*
      directly, as this used to) ensures that shared ancestor's *__init__*
      -- which registers this object with *db* -- runs exactly once no
      matter which subclass is being constructed, rather than once per
      inheritance path. *kwargs* is how *AGRelation*'s own *src*/*dst*
      constructor arguments -- which *GraphObject* has no use for itself --
      get carried through to it along that same chain.
    :type kwargs: Any
    '''
    assert isinstance(db, Model)

    self._parentsCache:list[GraphObject]|None = []

    # incomingCheck = lambda r, slf=self: isinstance(r, Relation) and r.dst is slf
    # self._incoming:ValidatedList[Relation] = ValidatedList(incomingCheck)
    # "Should only be assigned by *Relation* objects where self is at the dst end."
    #
    # outgoingCheck = lambda r, slf=self: isinstance(r, Relation) and r.src is slf and not slf is None and not slf.model.writeLocked()
    # self._outgoing:ValidatedList[Relation] = ValidatedList(outgoingCheck)
    # "Should only be assigned by *Relation* objects where self is at the src end and not write-locked."
    
    self._individual = individual

    super().__init__(db=db, **kwargs)

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
    # self._statusReport:list[tuple[str, str, dict[str,Callable[[],None]]]] = []

  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.

    :returns:
    :rtype: InstantiationInfo
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
    '''
    Simple aliasing for *self.db*.

    :returns:
    :rtype: Model
    '''
    return self.db
  
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
    :returns:
    :rtype: Generator[tuple[Relation, GraphObject | None]]
    '''
    for rel in self._outgoing:
      if filtr(rel):
        yield rel, rel.localDst if localOnly else rel.dst
    for rel in self._incoming:
      if filtr(rel) and rel.isSymmetric():
        yield rel, rel.localSrc if localOnly else rel.src

  def _getIncoming(self, filtr:Callable[[Relation], bool]=lambda _: True, 
                   localOnly:bool=False) -> Generator[tuple[Relation, GraphObject|None]]:
    '''
    This method should be used to access all incoming relations.  It will automatically
    include any symmetric relations.

    :param filtr:
    :type filtr: Callable[[Relation], bool]
    :param localOnly:
    :type localOnly: bool
    :returns:
    :rtype: Generator[tuple[Relation, GraphObject | None]]
    '''
    for rel in self._incoming:
      if filtr(rel):
        yield rel, rel.localSrc if localOnly else rel.src
    for rel in self._outgoing:
      if filtr(rel) and rel.isSymmetric():
        yield rel, rel.localDst if localOnly else rel.dst
        
  # def assertToStatusReport(self, cond:bool, msg:str, severity:str='E', actions:dict[str,Callable[[],None]]=dict()) -> None:
  #   '''
  #   Conditionally logs an line in the status report for the object.
  #
  #   :param cond: A conditional expression that if False will cause an entry in
  #     the status report.
  #   :type cond: bool:
  #   :param msg: A message to print in the status report if *cond* is False.
  #   :type msg: str
  #   :param severity: A one-character severity code: F (fatal), E (error), 
  #     W (warning), I (informational)
  #   :type severity: str
  #   :param actions: A dict of str:Callable indicating actions such as fix:<function>,
  #     or "delete:<function>" for use in a ActionDialog later.
  #   :type actions: dict[str:Callable[[],None]]
  #   :returns: None
  #   '''
  #   if not cond:
  #     self._statusReport.append((severity, msg, actions))
    
  def validate(self) -> list[str]:
    #ret:list[str] = []
        
    #check that Python types correspond to SN types.
    '''
    :returns:
    :rtype: list[str]
    '''
    if type(self) is GraphObject:
      self.assertToStatusReport(self.id == 1, 
            'The only GraphObject should be top', 'E')
    elif type(self) is Node:
      # can't use .isa() for this as getParents() will create an isa to NODE.
      self.assertToStatusReport(self is self.model.NODE or self.model.NODE in self.getSupers(), 
            'All Node objects should be explicit isa-children of "node"', 'W')
      self.assertToStatusReport(not self.isa(self.model.RELATION),
            'Node object isa relation')
    elif type(self) is Relation:
      self.assertToStatusReport(self is self.model.RELATION or self.model.RELATION in self.getSupers(),
            'All Relation objects should be explicit isa-children of "relation".', 'W')
      self.assertToStatusReport(not self.isa(self.model.NODE),
            'Relation object isa node')
    elif type(self) is Collection:
      self.assertToStatusReport(self is self.model.COLLECTION or self.model.COLLECTION in self.getSupers(),
            'All Collection objects should be explicit isa-children of "collection".', 'W')
      self.assertToStatusReport(not self.isa(self.model.RELATION),
            'Collection object isa relation')
    elif type(self) is AllModelCollection:
      self.assertToStatusReport(self.model.COLLECTION in self.getSupers(),
            'All Collection objects should be explicit isa-children of "collection".', 'W')
      self.assertToStatusReport(not self.isa(self.model.RELATION),
            'AllModelCollection object isa relation')
    elif type(self) is IsaIndividual:
      pass
    else:
      self.assertToStatusReport(False,
            f'Unknown subtype of GraphObject: {self.__class__.__name__}', 'W')
    return self.statusReport()
  
  # def statusReport(self) -> list[str]:
  #   ret:list[str] = []
  #   for sev, text, _actions in self._statusReport:
  #     ret.append(f'{sev}: {text}')
  #   return ret
  #
  # def status(self) -> str:
  #   stats:list[tuple[str,str,dict[str,Callable[[],None],]]] = self._statusReport
  #   priority = 'IWEF'
  #   pos:int = -1
  #   if not stats:
  #     return ''
  #   for s,_,_ in stats:
  #     p = priority.find(s) 
  #     if p > pos:
  #       pos = p
  #   assert pos>=0
  #   return priority[pos]
  #
  # _STATUS:dict[str,int] = {
  #   '':0,
  #   'E':-1,
  #   'F':-2,
  #   'I':1,
  #   'W':2
  #   }
  #
  # def statsInt(self):
  #   return self._STATUS[self.status()]    
    
  def _isConnected(self):
    '''
    :returns:
    :rtype:
    '''
    return self.id in self.db

  def _disconnect(self, **kwargs) -> None:
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

    :param kwargs:
    :type kwargs:
    '''
    # #TODO: This is a potential problem for chains of transitive relations.
    # assert self._isConnected()
    #
    # children = self.getChildren()
    #
    # # unregister from the model
    # self.db._unregister(self._id)
    #
    # # disconnect from related-to objects
    # for r,_ in self._getIncoming():
    #   r._disconnect(keep=self)
    # for r,_ in self._getOutgoing():
    #   r._disconnect(keep=self)
    super()._disconnect(**kwargs)
      
    for child in self.getChildren(): #TODO: could be more efficient by just fixing the parentCache's.
      child.retract()
    
  def _reconnect(self, **kwargs):
    '''
    Reconnect this disconnected object to it's *Model* by:
    
      - reregistering it to the *Model*
      - reregistering (to other objects) the far ends of the relations 
      - reregistering all the above relations with the *Model*
      
    .. Note::
    
      This method should only be used to undo a _disconnect() operation.
      
    :param kwargs:
    :type kwargs:
    '''
    # assert not self._isConnected()
    #
    # # unregister from the model
    # self.db._register(self, self._id)
    #
    # # disconnect from related-to objects
    # for r,_ in self._getIncoming():
    #   r._reconnect(kept=self)
    # for r,_ in self._getOutgoing():
    #   r._reconnect(kept=self)
    super()._reconnect(**kwargs)

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
    :param asTree:
    :type asTree: bool
    :param rmDups:
    :type rmDups: bool
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

    :param typ:
    :type typ: GraphObject | None
    :param asTree:
    :type asTree: bool
    :param rmDups:
    :type rmDups: bool
    :returns:
    :rtype: list | bool
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
    :param asTree:
    :type asTree: bool
    :param rmDups:
    :type rmDups: bool
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

  def isVariable(self) -> bool:
    '''
    :returns: True iff this is a variable -- its name starts with "?" -- which
      stands for "something" in a pattern (a rule, definition or query).
    :rtype: bool
    '''
    try:
      return self.name.startswith("?")
    except Exception: # eg: during construction, before it has a name
      return False

  def constraints(self) -> dict[str, Any]:
    '''
    :returns: A variable's constraints -- in a pattern, what what it matches
      must be like: the parsed text of its "constraints" attribute (see
      *sn.model.constraints*), eg: ``{"alive": PRESENT, "age": 30}``. For
      anything but a variable, or if the text can't be parsed (see
      *constraintsError()*), {}.
    :rtype: dict[str, Any]
    '''
    from sn.model.constraints import parseConstraints, ConstraintError, CONSTRAINTS
    if not self.isVariable():
      return {}
    try:
      return parseConstraints(self.getLocal(CONSTRAINTS, None))
    except ConstraintError:
      return {}

  def constraintsError(self) -> str|None:
    '''
    :returns: Why a variable\'s constraints can\'t be parsed, or None if they can (or it has none).

    :rtype: str | None
    '''
    from sn.model.constraints import parseConstraints, ConstraintError, CONSTRAINTS
    if not self.isVariable():
      return None
    try:
      parseConstraints(self.getLocal(CONSTRAINTS, None))
    except ConstraintError as ex:
      return str(ex)
    return None

  def constraintsText(self) -> str:
    '''
    :returns: A variable\'s constraints as (normalized) text, eg: "alive, age: 30"; its raw text if it can\'t be parsed; "" if none.

    :rtype: str
    '''
    from sn.model.constraints import formatConstraints, CONSTRAINTS
    if not self.isVariable():
      return ""
    if self.constraintsError() is not None:
      return str(self.getLocal(CONSTRAINTS, "")).strip()
    return formatConstraints(self.constraints())

  def formatConstraints(self) -> str:
    '''
    :returns: *constraintsText()* in braces, eg: "{alive, age: 30}" -- or "" if there are none.

    :rtype: str
    '''
    text = self.constraintsText()
    return "{" + text + "}" if text else ""

  def isPatternElement(self, _seen:set[int]|None=None) -> bool:
    '''
    :param _seen:
    :type _seen: set[int] | None
    :returns: True iff this object describes a pattern rather than the world --
      it's then not data: the reasoner doesn't take it as a fact, and
      *getRelatedTo()* etc. leave it out. That is:
    :rtype: bool

      - a variable (see *isVariable()*), or
      - a relation contained by a context -- the target of a relation that isa
        "contains" (eg: a rule's antecedent or consequent) -- or
      - a relation with a pattern element at either end (eg: ?x -parent-> ?y,
        or ?x's isa link).

      The "contains" relations themselves are real ("this rule contains that"),
      unless contained in turn. Constants in a pattern (eg: fred) are real too:
      they're just what its relations connect.
    '''
    if self.isVariable():
      return True
    if not isinstance(self, Relation):
      return False
    seen = set() if _seen is None else _seen
    if id(self) in seen:
      return False
    seen.add(id(self))
    contains = getattr(self.model, "CONTAINS", None)
    if contains is not None:
      for r in self._incoming:
        if r.dst is self and r.isIndividual() and r.isa(contains): # contained by a context
          return True
      if self.isa(contains): # a containment relation itself is real
        return False
    return any(end is not None and end.isPatternElement(seen) for end in (self.localSrc, self.localDst))

  def _inferredRelated(self, rel:Relation|None, outgoing:bool) -> list[tuple[Relation,GraphObject]]:
    '''
    What the model's last "reason" (see *sn.model.reasoner.reasoningFor()*)
    says this object is related to (*outgoing*) or from, as (relation, other)
    pairs:

      - with *rel* (a relation type): (rel, other) for everything related
        under it, asserted or inferred;
      - without: (relation type, other) for each relation that was inferred or
        inherited -- ie: not asserted -- since there's no individual Relation
        for it.

    [] if there are no reasoning results, or *rel* isn't a relation type.

    :param rel:
    :type rel: Relation | None
    :param outgoing:
    :type outgoing: bool
    :returns:
    :rtype: list[tuple[Relation, GraphObject]]
    '''
    from sn.model.reasoner import reasoningFor
    reasoning = reasoningFor(self.model)
    if reasoning is None:
      return []
    if rel is not None:
      if not rel.isType():
        return []
      others = reasoning.related(self, rel) if outgoing else reasoning.relatedFrom(self, rel)
      return [(rel, o) for o in others]
    if outgoing:
      return [(t, d) for t, s, d in reasoning.newFacts() if s is self]
    return [(t, s) for t, s, d in reasoning.newFacts() if d is self]

  @staticmethod
  def _addNew(pairs:list[tuple[Relation,GraphObject]], more:list[tuple[Relation,GraphObject]], byObjectOnly:bool) -> None:
    '''
    Append the pairs in *more* not already in *pairs* (by identity: of the object, or of both).

    :param pairs:
    :type pairs: list[tuple[Relation, GraphObject]]
    :param more:
    :type more: list[tuple[Relation, GraphObject]]
    :param byObjectOnly:
    :type byObjectOnly: bool
    '''
    have = {id(o) for _, o in pairs} if byObjectOnly else {(id(r), id(o)) for r, o in pairs}
    for r, o in more:
      key = id(o) if byObjectOnly else (id(r), id(o))
      if key not in have:
        have.add(key)
        pairs.append((r, o))

  @overload
  def getRelatedTo(self, *, _seen:set[int]|None=None, inferred:bool=True)                         -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def getRelatedTo(self, rel:Relation|None=None, *, _seen:set[int]|None=None, inferred:bool=True) -> list[GraphObject]: ...
  def getRelatedTo(self, rel:Relation|None=None, *, _seen:set[int]|None=None, inferred:bool=True) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    '''
    :param rel: If given, only relations that isa *rel*, and just the related
      objects are returned; otherwise (relation, object) pairs.
    :type rel: Relation | None
    :param _seen:
    :type _seen: set[int] | None
    :param inferred: [default=True] Also include what the model's last "reason"
      inferred (see *_inferredRelated()*).
    :type inferred: bool
    :returns:
    :rtype: list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
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
    typeOk:Callable[[Relation], bool] = (lambda r: True) if rel is None else (cast(Callable[[Relation], bool], lambda r, typ=rel: r.isa(typ)))
    # pattern relations (inside rules etc.) aren't about the world -- unless we're a pattern element ourselves
    patternOk:Callable[[Relation], bool] = (lambda r: True) if self.isPatternElement() else (lambda r: not r.isPatternElement())
    filtr:Callable[[Relation], bool] = lambda r: typeOk(r) and patternOk(r)
    for r,other in self._getOutgoing(filtr):
      if other is not None:
        ret.append((r, other))
        #seen.add(other.id)
        if r.isTransitive() and other is not self:
          # add in any transitives, filtering out anything we already refer to
          ret += [ret2 for ret2 in other.getRelatedTo(_seen=seen, inferred=False) if filtr(r)]
        if r.isReflexive() and other is not self and self not in seen:
          ret.append((r, self))
    if inferred and _seen is None: # the outermost call only
      self._addNew(ret, self._inferredRelated(rel, outgoing=True), byObjectOnly=rel is not None)
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
    '''
    :param rel:
    :type rel: Relation | None
    :param obj:
    :type obj: GraphObject | None
    :returns:
    :rtype: bool | list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    if obj is None:
      return self.getRelatedTo(rel)
    else:
      return obj in self.getRelatedTo(rel)
    
  @overload
  def getRelatedFrom(self, *, inferred:bool=True)                         -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def getRelatedFrom(self, rel:Relation|None=None, *, inferred:bool=True) -> list[GraphObject]: ...
  def getRelatedFrom(self, rel:Relation|None=None, *, inferred:bool=True) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    '''
    :param rel: If given, only relations that isa *rel*, and just the related
      objects are returned; otherwise (relation, object) pairs.
    :type rel: Relation | None
    :param inferred: [default=True] Also include what the model's last "reason"
      inferred (see *_inferredRelated()*).
    :type inferred: bool
    :returns:
    :rtype: list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    # if rel is not None:
    #   return [other for _rel,other in self._getIncoming(lambda r, typ=rel: r.isa(typ)) if other is not None] #type: ignore[misc]
    # else:
    #   return [(rel,other) for rel,other in self._getIncoming() if other is not None]    
    ret:list[tuple[Relation,GraphObject]] = []
    r: Relation
    typeOk:Callable[[Relation], bool] = (lambda r: True) if rel is None else (cast(Callable[[Relation], bool], lambda r, typ=rel: r.isa(typ)))
    # pattern relations (inside rules etc.) aren't about the world -- unless we're a pattern element ourselves
    patternOk:Callable[[Relation], bool] = (lambda r: True) if self.isPatternElement() else (lambda r: not r.isPatternElement())
    filtr:Callable[[Relation], bool] = lambda r: typeOk(r) and patternOk(r)
    for r,other in self._getIncoming(filtr):
      if other is not None:
        ret.append((r, other))
        seen = [] if ret == [] else list(list(zip(*ret))[1])
        if r.isTransitive() and other is not self:
          # add in any transitives, filtering out anything we already refer to
          ret += [ret2 for ret2 in other.getRelatedFrom(inferred=False) if ret2[1] not in seen and filtr(r)]
        # if r.isReflexive() and other is not self and self not in seen:
        #   ret.append((r, self))
        # if r.isSymmetric():
        #   pass
    if inferred:
      self._addNew(ret, self._inferredRelated(rel, outgoing=False), byObjectOnly=rel is not None)
    if rel is not None: # and not _returnPairs:
      return [o for _, o in ret] # return only the objects
    return ret # return the rel/object pairs


  @overload
  def isRelatedFrom(self) -> list[tuple[Relation,GraphObject]]: ...
  @overload
  def isRelatedFrom(self, rel:Relation) -> list[GraphObject]: ...
  @overload
  def isRelatedFrom(self, rel:Relation, obj:GraphObject) -> bool: ...
  def isRelatedFrom(self, rel:Relation|None=None, obj:GraphObject|None=None) -> bool|list[GraphObject]|list[tuple[Relation,GraphObject]]:
    '''
    :param rel:
    :type rel: Relation | None
    :param obj:
    :type obj: GraphObject | None
    :returns:
    :rtype: bool | list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    if obj is None:
      return self.getRelatedFrom(rel)
    else:
      return obj in self.getRelatedFrom(rel)
    
  @override
  def isIndividual(self)->bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._individual
  
  def isSystemObject(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    from sn.model import TopModel  # @UnresolvedImport -- deferred to dodge the sn.model/model.py circular import; see sn/model/__init__.py
    return type(self.model) is TopModel

  @property
  @override
  def name(self)->str:
    '''
    :returns:
    :rtype: str
    '''
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
    '''
    :returns:
    :rtype: Model
    '''
    return super().db
  
  @override
  def __repr__(self):
    '''
    :returns: A string representation of this object.
    :rtype:
    '''
    return self.torepr()
  
  @override
  def torepr(self, relativeTo:Model|None=None):
    '''
    :param relativeTo:
    :type relativeTo: Model | None
    :returns:
    :rtype:
    '''
    return f'{self.tostring(relativeTo)} @ {self.getPRef().tostring(relativeTo)}'
  
  @override
  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
    :rtype: str
    '''
    return self.tostring()
  
  @override
  def tostring(self, relativeTo:Model|None=None, format="type", inheritMark:str|None=UP_ARROW) -> str:
    '''
    :param relativeTo:
    :type relativeTo: Model | None
    :param format:
    :type format:
    :param inheritMark:
    :type inheritMark: str | None
    :returns:
    :rtype: str
    '''
    localname = self.getLocal("name", None)
    inhMark:str = inheritMark if (inheritMark is not None and localname is None) else ""

    # add quotes to the name if necessary
    name:str = str(self.get("name") if localname is None else localname)
    if name == "":
      name = '""'
    elif not name.replace("-","_").isidentifier():
      name = f'"{name}"'
    
    match format:
      case "minURLnamed":
        return f'{self.getPRef().tostring(relativeTo)}?name={name}'
      case "friendly":
        other = self.getPRef().tostring(relativeTo)
        if other.startswith("#"):
          return f'{name}{other}'
        else:
          return f'{name}#{other}'
      case _:
        return f'{self.__class__.__name__}({inhMark}{name}, {self.getPRef().tostring(relativeTo)}, <{"individual" if self.isIndividual() else "type"}{", <inferred>" if self.inferred else ""}>)'
  
  @override
  def __hash__(self): #type: ignore[override]
    '''
    :returns:
    :rtype:
    '''
    return PRObject.__hash__(self)
  
  @override
  def __delitem__(self, key:str)->None:
    '''
    :param key:
    :type key: str
    '''
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    super().__delitem__(key)
  
  @override
  def __setitem__(self, key:str, value:SerializableType)->None:
    '''
    :param key:
    :type key: str
    :param value:
    :type value: SerializableType
    '''
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    super().__setitem__(key, value)
  
  @override
  def setAttr(self, key:str, attr:Attribute) -> Attribute:
    '''
    :param key:
    :type key: str
    :param attr:
    :type attr: Attribute
    :returns:
    :rtype: Attribute
    '''
    if self.model.writeLocked():
      raise PermissionError(f'DB "{self.model.name}" is write locked.')
    return super().setAttr(key, attr)
    
    
class Model(AbstractGraph[GraphObject, "Relation"], Subject, Dirtyable):
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
    from sn.model import TopModel  # @UnresolvedImport -- deferred to dodge the sn.model/model.py circular import; see sn/model/__init__.py
    model = TopModel("sn:///sn", mode="", _reading=False) # creates a model in memory cache
    model._writeLocked = True
    
  def __new__(cls, url:str, mode:str="w", _reading:bool=False):
    '''
    :param url:
    :type url: str
    :param mode:
    :type mode: str
    :param _reading:
    :type _reading: bool
    :returns:
    :rtype:
    '''
    return PRDb.__new__(cls, url, mode=mode, memoryResident=True, _reading=_reading)
    

  def __init__(self, url:str, mode:str="w", _reading:bool=False):
    '''
    Constructor

    :param url:
    :type url: str
    :param mode:
    :type mode: str
    :param _reading:
    :type _reading: bool
    '''
    PRDb.__init__(self, url, mode=mode, memoryResident=True, _reading=_reading)
    Subject.__init__(self)
    Dirtyable.__init__(self)
    
    self._allowParentsCaching:bool = False

    sn:Model = cast(Model, GORef.eval("$sn"))
    if sn not in self.superDBs:
      self.superDBs.append(sn) #type: ignore[arg-type]
    
    self.TOP:GraphObject = GORef.eval("$sn#top") #type: ignore[assignment]
    self.RELATION:Relation = GORef.eval("$sn#relation") #type: ignore[assignment]
    self.ISA:Relation = GORef.eval("$sn#3") #type: ignore[assignment]
    self.NODE:Node = GORef.eval("$sn#node") #type: ignore[assignment]
    # self.REFLEXIVE:Relation = GORef.eval("$sn#reflexive") #type: ignore[assignment]
    # self.IRREFLEXIVE:Relation = GORef.eval("$sn#irreflexive") #type: ignore[assignment]
    # self.SYMMETRIC:Relation = GORef.eval("$sn#symmetric") #type: ignore[assignment]
    # self.TRANSITIVE:Relation = GORef.eval("$sn#transitive") #type: ignore[assignment] 
    # self.EQUALITY:Relation = GORef.eval("$sn#equality") #type: ignore[assignment]
    self.COLLECTION:Collection = GORef.eval("$sn#collection") #type: ignore[assignment]
    self.CONTEXT:Node = GORef.eval("$sn#context") #type: ignore[assignment]
    self.CONTAINS:Relation = GORef.eval("$sn#contains") #type: ignore[assignment]
    self.RULE:Node = GORef.eval("$sn#rule") #type: ignore[assignment]
    self.ANTECEDENT:Relation = GORef.eval("$sn#antecedent") #type: ignore[assignment]
    self.CONSEQUENT:Relation = GORef.eval("$sn#consequent") #type: ignore[assignment]
    self.QUERY:Node = GORef.eval("$sn#query") #type: ignore[assignment]
    self.DISTINCT:Relation = GORef.eval("$sn#distinct") #type: ignore[assignment]
    self.DEFINITION:Node = GORef.eval("$sn#definition") #type: ignore[assignment]
    self.DEFINIENDUM:Relation = GORef.eval("$sn#definiendum") #type: ignore[assignment]
    self.DEFINIENS:Relation = GORef.eval("$sn#definiens") #type: ignore[assignment]

    if hasattr(self, "_initialized") or _reading: # This means the __new__ method has returned an existing object, so don't truck over it!
      return

    self.nextID:int = 256
    
  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    '''
    :returns:
    :rtype: InstantiationInfo
    '''
    ret:InstantiationInfo = super().getInstantiationInfo()
    ret.class_ = cls
    ret.finalSetters.append(PropertyInfo("_", bool, setter=lambda slf,_t:cast(Model,slf).setDirty(False))) #type: ignore[arg-type]
    ret.finalSetters.append(PropertyInfo("_", bool, setter=lambda slf,_t:cast(Model,slf)._migrate())) #type: ignore[arg-type]
    return ret

  def _migrate(self) -> None:
    '''
    After reading: bring older files up to date (leaving the model dirty if
    anything changed, so it gets saved).
    '''
    from sn.model.constraints import migrateConstraints
    for msg in migrateConstraints(self):
      logger.warning(f'{self.name}: {msg}')

  @override
  @classmethod
  def getDB(cls, url:str, mode="w") -> Model:
    '''
    Override of the super() version to specificatlly return a Model.

    :param url:
    :type url: str
    :param mode:
    :type mode:
    :returns:
    :rtype: Model
    '''
    if url in ("sn","$sn"):
      url = "sn:/sn.xml"
      mode = ""
    ret = super().getDB(url, mode=mode)
    if not isinstance(ret, Model):
      raise TypeError(f'Database "{url}" is of type {ret.__class__.__name__}; expected type Model."')
    return ret
      
  # @override
  # def _register(self, value: GraphObject, _id:Optional[int]=None) -> int: # type: ignore[override]
  #   '''
  #   Overrides the 
  #   :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
  #   to restrict contained objects to :py:class:`GraphObject` subtypes. 
  #   *This violates subsumption rules, but that's what we want here!* 
  #
  #   Also sets the dirty bit and notifies any observers ("add GraphObject" (GraphObject))
  #   '''
  #   assert isinstance(value, GraphObject), \
  #       f'Models are restricted to containing only GraphObject subtypes; got a {value.__class__.__name__} type.'
  #   # self.setDirty()
  #   ret = super()._register(value, _id)
  #   # with Subject.ChangeMgr(self, later=True) as cm:
  #   #   cm.registerTopics(("add GraphObject", (ret, value)))
  #   return ret
  #
  # @override
  # def _unregister(self, _id:int) -> None:
  #   '''
  #   Overrides the 
  #   :py:meth:`parent method <pythonUtils:util.persistence.pRef.PRDb._register>`
  #   to also set the dirty bit and notify any observers () 
  #   '''
  #   super()._unregister(_id)
  #   # self.setDirty()
  #   # with Subject.ChangeMgr(self, later=True) as cm:
  #   #   cm.registerTopics(("del GraphObject", (_id,)))    
  
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
    super().save(saveas=saveas, overwrite=overwrite, format=format)
    self.setDirty(False)

  def validate(self) -> list[tuple[GraphObject,list[str]]]:
    '''
    :returns:
    :rtype: list[tuple[GraphObject, list[str]]]
    '''
    ret:list[tuple[GraphObject,list[str]]] = []
    go:GraphObject
    for go in self.values():
      res = go.validate()
      if res:
        ret.append((go, res))
    return ret
  
  @override
  def _makeDBContainer(self) -> AllModelCollection:
    '''
    :returns:
    :rtype: AllModelCollection
    '''
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
  
  def __init__(self, db:Model, parents:Iterable[GraphObject]=[], individual:bool=False, name:Optional[str]=None, **kwargs):
    '''
    :param db:
    :type db: Model
    :param parents:
    :type parents: Iterable[GraphObject]
    :param individual:
    :type individual: bool
    :param name:
    :type name: Optional[str]
    :param kwargs:
    :type kwargs:
    '''
    super().__init__(db, parents, individual=individual, name=name, **kwargs)

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
    '''
    :param db:
    :type db: Model
    :param parents:
    :type parents: Iterable[GraphObject]
    :param members:
    :type members: Iterable[GraphObject]
    :param individual:
    :type individual: bool
    :param name:
    :type name: Optional[str]
    '''
    super().__init__(db, parents, individual=individual, name=name)
    self.members:list[GraphObject] = list(members)
    
  def addMember(self, member:GraphObject):
    '''
    :param member:
    :type member: GraphObject
    '''
    if member not in self.members:
      self.members.append(member)
      self.setDirty()
      
  def removeMember(self, member:GraphObject):
    '''
    :param member:
    :type member: GraphObject
    '''
    self.members.remove(member)
    self.setDirty()
    
  def getMembers(self) -> Iterator[GraphObject]:
    '''
    :returns:
    :rtype: Iterator[GraphObject]
    '''
    for member in self.members:
      yield member

  def isMember(self, obj:GraphObject) -> bool:
    '''
    :param obj:
    :type obj: GraphObject
    :returns:
    :rtype: bool
    '''
    return obj in self.members
  
  def countMembers(self) -> int:
    '''
    :returns:
    :rtype: int
    '''
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
  def tostring(self, relativeTo:Model | None=None, format="type", inheritMark:str|None=UP_ARROW) -> str:
    '''
    :param relativeTo:
    :type relativeTo: Model | None
    :param format:
    :type format:
    :param inheritMark:
    :type inheritMark: str | None
    :returns:
    :rtype: str
    '''
    ret = super().tostring(relativeTo, format, inheritMark)
    if format in ("friendly", "minURLnamed"): # names only
      return ret
    return f'{ret[:-1]}, {self.countMembers()} members)'
  
  @override
  def torepr(self, relativeTo:Model | None=None) -> str:
    '''
    :param relativeTo:
    :type relativeTo: Model | None
    :returns:
    :rtype: str
    '''
    ret = self.tostring(relativeTo)+":"
    for m in self.getMembers():
      ret += (f'\n    {m.tostring(relativeTo)}')
    return ret
    
class AllModelCollection(Collection, PRDbContainer):
  def __init__(self, model:Model, **kwargs):
    '''
    :param model: The Model this collection is registered as the "all objects"
      container for.
    :type model: Model
    :param kwargs:
    :type kwargs:
    '''
    # Same shape of diamond as *Relation* (see its __init__ for the full
    # explanation): *AllModelCollection* inherits from both *Collection*
    # (-> ... -> AGObject -> PRObject) and *PRDbContainer* (-> PRContainer ->
    # PRObject, neither of which override __init__ at all). The old separate
    # Collection.__init__()/PRDbContainer.__init__() calls each independently
    # walked down to PRObject.__init__() -- which registers this object with
    # *model* -- registering it twice. A single cooperative super().__init__()
    # call lets the MRO run it exactly once instead.
    super().__init__(model, [Model.getDB("$sn").COLLECTION], individual=True, name=model.name)
  
  @override
  def addMember(self, member:GraphObject):
    '''
    :param member:
    :type member: GraphObject
    '''
    raise PermissionError("Cannot add members to an AllModelCollection. To add an object, add it to the Model.")
      
  @override
  def removeMember(self, member:GraphObject):
    '''
    :param member:
    :type member: GraphObject
    '''
    raise PermissionError("Cannot remove members to an AllModelCollection. To remove an object, remove it from the Model.")
    
  @override
  def getMembers(self) -> Iterator[GraphObject]:
    '''
    :returns:
    :rtype: Iterator[GraphObject]
    '''
    for member in list(self.db.values()):
      yield member

  @override
  def isMember(self, obj:GraphObject) -> bool:
    '''
    :param obj:
    :type obj: GraphObject
    :returns:
    :rtype: bool
    '''
    return obj in self.db._db
  
  @override
  def countMembers(self) -> int:
    '''
    :returns:
    :rtype: int
    '''
    return len(self.db._db)
    
    
  
class Relation(GraphObject, AGRelation[Model, GraphObject]):
  def __init__(self, db:Model,
               parents:Iterable[GraphObject]=[],
               src:GraphObject|None=None,
               dst:GraphObject|None=None,
               individual:bool=False,
               name:Optional[str]=None):
    '''
    :param db: The Model in which to create the relation.
    :type db: Model
    :param parents: The direct parents of the object from which they will inherit attributes.
    :type parents: Iterable[GraphObject]
    :param src: The source *GraphObject* of this relation, or *None*.
    :type src: Optional[GraphObject]
    :param dst: The destination *GraphObject* of this relation, or *None*.
    :type dst: Optional[GraphObject]
    :param individual: If True, this will be an individual, otherwise it will be a type. Defaults to False.
    :type individual: bool
    :param name: The given name of the object; see *GraphObject.__init__()*.
    :type name: Optional[str]
    '''
    if not db.reading:
      for p in parents:
        assert not hasattr(db, "RELATION") or isinstance(p, Relation)

    # *Relation* inherits from both *GraphObject* and *AGRelation*, which both
    # in turn inherit from *AGObject* -- a single cooperative super().__init__()
    # call here (instead of the old separate GraphObject.__init__() /
    # AGRelation.__init__() calls) lets Python's MRO run *AGObject.__init__()*
    # (and hence *PRObject.__init__()*, which registers this object with *db*)
    # exactly once, instead of once per inheritance path -- that double
    # registration was the actual bug this replaced. All the constructor
    # arguments for both bases are passed here as keywords; each base
    # consumes the ones it recognizes and forwards the rest via its own
    # **kwargs (see *GraphObject.__init__()* and *AGRelation.__init__()*).
    super().__init__(db=db, parents=parents, individual=individual, name=name, src=src, dst=dst)

    # self._dst:GraphObject|None = None
    # self._src:GraphObject|None = None
    # if db.reading:
    #   self._dst = dst
    #   self._src = src
    # else:
    #   self.connect(source=src, destination=dst)
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.

    :returns:
    :rtype: InstantiationInfo
    '''
    def connectSrc(slf:Relation, source:str, isSource:bool):
      if source is not None and source!="None":
        sideText = "src" if isSource else "dst"
        try:
          obj:Any = GORef.eval(source, slf.db)
          assert isinstance(obj, GraphObject)
          if isSource:
            slf.connect(source=obj)
          else:
            slf.connect(destination=obj) 
        except KeyError:
          #actions = {"remove relation from model": lambda: [slf.model.setDirty(), slf._disconnect(), slf.model.setDirty(), None][-1]}
          slf.assertToStatusReport(False, f'Unexpected read fault on {sideText} for Relation {slf}: "{source}"', "E", 
                                   actions={"remove relation from model": lambda: [slf.model.setDirty(), slf._disconnect(), slf.model.setDirty(), None][-1]})
        except AssertionError:
          slf.assertToStatusReport(False, f'Unexpected type for read on {sideText} for Relation {slf}: {type(obj)}', "E",
                                   actions={"remove relation from model": lambda: [slf.model.setDirty(), slf._disconnect(), slf.model.setDirty(), None][-1]})
        except Exception as ex:
          slf.assertToStatusReport(False, f'Unexpected error on reading {sideText} for Relation {slf}: {ex.__class__.__name__}: {ex}', "E", 
                                   actions={"remove relation from model": lambda: [slf.model.setDirty(), slf._disconnect(), slf.model.setDirty(), None][-1]})
        
    ret = GraphObject.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(Relation, slf).db)],
            conKWArgs=[ParamInfo("individual", bool, lambda slf: cast(Relation, slf)._individual)],
            postconSetters=ret.postconSetters,
            finalSetters=ret.finalSetters+
                          [PropertyInfo("src", str, 
                                        lambda slf: GORef.formatForURL(slf.localSrc, slf.db), #type: ignore[attr-defined]
                                        lambda slf, source: connectSrc(slf, source, isSource=True)),
                           PropertyInfo("dst", str, 
                                        lambda slf: GORef.formatForURL(slf.localDst, slf.db), #type: ignore[attr-defined]
                                        lambda slf, source: connectSrc(slf, source, isSource=False))]
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
    :param localOnly:
    :type localOnly: bool
    :return: The *calculated* destination of this relation; ie: if this relation
      does not have a specific destination, look it up in the ISA hierarchy.
    :rtype: GraphObject | None
    '''
    if localOnly or self.localDst is not None:
      return self.localDst
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        if not isinstance(obj, Relation):#, f'Expected type Relation, got type {type(obj)}.'
          self.assertToStatusReport(False, f'Expected type Relation for supertype, got type {type(obj)}. Probably a changed parent model.', 'E', 
            actions={"delete this relation": lambda: [self._disconnect(), self.view.setDirty(), None][-1]})
          return None
        if obj.localDst is not None:
          return obj.localDst
    return None
  
  @dst.setter
  def dst(self, obj:GraphObject|None):
    '''
    :param obj:
    :type obj: GraphObject | None
    '''
    old = self.localDst
    AGRelation.dst.fset(self, obj) #type: ignore[attr-defined] # @undefinedvariable
    if old is not obj:
      self._endpointChanged("dst", old, obj)
    # # if self._legalDst(obj):
    # #   self._dst = obj
    # self.connect(destination=obj)
    # assert self._dst is obj
    # self.setDirty()
    
  @property
  def src(self, localOnly:bool=False) -> GraphObject|None: #GraphObject|None:
    '''
    :param localOnly:
    :type localOnly: bool
    :return: The *calculated* source of this relation; ie: if this relation
      does not have a specific source, look it up in the ISA hierarchy.
    :rtype: GraphObject | None
    '''
    if localOnly or self.localSrc is not None:
      return self.localSrc
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        if not isinstance(obj, Relation):#, f'Expected type Relation, got type {type(obj)}.'
          self.assertToStatusReport(False, f'Expected type Relation for supertype, got type {type(obj)}. Probably a changed parent model.', 'E', 
            actions={"delete this relation": lambda: [self._disconnect(), self.view.setDirty(), None][-1]})
          return None
        if obj.localSrc is not None:
          return obj.localSrc
    return None
  
  @src.setter
  def src(self, obj:GraphObject|None):
    '''
    :param obj:
    :type obj: GraphObject | None
    '''
    old = self.localSrc
    AGRelation.src.fset(self, obj) #type: ignore[attr-defined] # @undefinedvariable
    if old is not obj:
      self._endpointChanged("src", old, obj)
    # # if self._legalSrc(obj):
    # #   self._src = obj
    # self.connect(source=obj)
    # assert self._src is obj
    # self.setDirty()
      
  def _endpointChanged(self, end:str, old:GraphObject|None, new:GraphObject|None) -> None:
    '''
    Called when the *src* or *dst* (per *end*) setter changes the local
    endpoint from *old* to *new*: tells observers (eg: the VRelations
    showing this relation) with a "mod src" or "mod dst" topic -- and, for a
    relation type, tells the relations below it that inherit that end (see
    *_inheritedEndpointChanged()*).

    :param end:
    :type end: str
    :param old:
    :type old: GraphObject | None
    :param new:
    :type new: GraphObject | None
    '''
    self.notify((f"mod {end}", (old, new)))
    if self.isType():
      self._notifyInheritors(end)

  def _notifyInheritors(self, end:str) -> None:
    '''
    Tell each relation directly below this one (subtype or individual) that
    has no *end* of its own -- so inherits it -- that it changed, and so on
    down. One with its own *end* stops the chain: nothing below it inherits
    from here.

    :param end:
    :type end: str
    '''
    for child in self.getChildren():
      if isinstance(child, Relation) and (child.localSrc if end == "src" else child.localDst) is None:
        child._inheritedEndpointChanged(end)

  def _inheritedEndpointChanged(self, end:str) -> None:
    '''
    The *end* ("src" or "dst") this relation inherits changed: observers are
    told with a "mod inherited src" or "mod inherited dst" topic.

    :param end:
    :type end: str
    '''
    self.notify((f"mod inherited {end}", ()))
    self._notifyInheritors(end)

  def _requireType(self, name:str) -> None:
    '''
    :param name:
    :type name: str
    '''
    if self.isIndividual():
      raise TypeError(f'{name} applies to relation types; use src/dst on individual relations ({self.tostring(format="friendly")}).')

  @property
  def domain(self) -> GraphObject|None:
    '''
    The domain (signature) of a relation type: what the src of its relations
    must be (isa). Sugar for *src* -- so it's the effective value, inherited
    from a supertype if not set locally. Relation types only: raises
    *TypeError* for an individual relation.

    :returns:
    :rtype: GraphObject | None
    '''
    self._requireType("domain")
    return self.src

  @domain.setter
  def domain(self, obj:GraphObject|None) -> None:
    '''
    :param obj:
    :type obj: GraphObject | None
    '''
    self._requireType("domain")
    self.src = obj # (through the setter, so observers are told)

  @property
  def range(self) -> GraphObject|None:
    '''
    The range (signature) of a relation type: what the dst of its relations
    must be (isa). Sugar for *dst* -- see *domain*. Relation types only:
    raises *TypeError* for an individual relation.

    :returns:
    :rtype: GraphObject | None
    '''
    self._requireType("range")
    return self.dst

  @range.setter
  def range(self, obj:GraphObject|None) -> None:
    '''
    :param obj:
    :type obj: GraphObject | None
    '''
    self._requireType("range")
    self.dst = obj # (through the setter, so observers are told)

  @property
  def localSrc(self) -> GraphObject|None:
    '''
    The source set on this relation itself, or None -- unlike *src*, never
    inherited from a supertype. Read-only: set it through *src* (so observers
    are told).

    :returns:
    :rtype: GraphObject | None
    '''
    return self._src

  @property
  def localDst(self) -> GraphObject|None:
    '''
    The destination set on this relation itself, or None -- unlike *dst*, never
    inherited from a supertype. Read-only: set it through *dst* (so observers
    are told).

    :returns:
    :rtype: GraphObject | None
    '''
    return self._dst

  def hasLocalDst(self) -> bool:
    '''
    :returns: True iff and only if this Relation has a locally defined destination.
    :rtype: bool
    '''
    return self.localDst is not None
    
  def hasLocalSrc(self) -> bool:
    '''
    :returns: True iff and only if this Relation has a locally defined source.
    :rtype: bool
    '''
    return self.localSrc is not None
    
  def _legalDst(self, obj:GraphObject) -> bool:
    #TODO: need to fill out _legalDst
    '''
    :param obj:
    :type obj: GraphObject
    :returns:
    :rtype: bool
    '''
    return True
    
  def _legalSrc(self, obj:GraphObject) -> bool:
    #TODO: need to fill out _legalSrc
    '''
    :param obj:
    :type obj: GraphObject
    :returns:
    :rtype: bool
    '''
    return True
  
  @override
  def validate(self) -> list[str]:
    '''
    :returns:
    :rtype: list[str]
    '''
    if self.localSrc is not None:
      self.assertToStatusReport(self in self.localSrc._outgoing, f'src end is not registered with src object, {self.localSrc}', 'E')
    if self.localDst is not None:
      self.assertToStatusReport(self in self.localDst._incoming, f'dst end is not registered with dst object, {self.localDst}', 'E')
    return self.statusReport()
    
  def _hasRelationalProperty(self, prop:str) -> bool:
    '''
    The relational properties (see *sn.model.snAttribute.RELATIONAL_ATTRS*)
    are LOCAL tags on relation *types*: the key's presence is the tag (its value
    is ignored) and they are never inherited -- brother isa sibling, but only
    sibling is symmetric. An individual relation has the property iff one of
    its immediate types does.

    :param prop:
    :type prop: str
    :returns:
    :rtype: bool
    '''
    if self.isType():
      return dict.__contains__(self, prop)
    try:
      parents = self.getParents()
    except (LookupError, AttributeError): # eg: during initialization
      return False
    return any(dict.__contains__(p, prop) for p in parents)

  def isReflexive(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._hasRelationalProperty("reflexive")
  
  def isIrreflexive(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._hasRelationalProperty("irreflexive")
  
  def isSymmetric(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._hasRelationalProperty("symmetric")
  
  def isAsymmetric(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._hasRelationalProperty("asymmetric")
  
  def isTransitive(self) -> bool:
    '''
    :returns:
    :rtype: bool
    '''
    return self._hasRelationalProperty("transitive")
    
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
  def tostring(self, relativeTo:Model|None=None, format="type", inheritMark:str|None=UP_ARROW) -> str:
    '''
    :param relativeTo:
    :type relativeTo: Model | None
    :param format:
    :type format:
    :param inheritMark:
    :type inheritMark: str | None
    :returns:
    :rtype: str
    '''
    def makeStr(o:GraphObject|None, inherited:bool) -> str:
      if o is None:
        return 'None'
      return f'{UP_ARROW if inherited else ""}{o.getPRef().tostring(self.db if relativeTo is None else relativeTo)}'
    ret = super().tostring(relativeTo=relativeTo, format=format, inheritMark=inheritMark)
    if format in ("friendly", "minURLnamed"): # names only
      return ret
    # return f'{ret[:-1]}, {makeStr(self.src, self._src is None)} {RIGHT_ARROW} {makeStr(self.dst, self._src is None)}{ret[-1]}'
    return f'{ret[:-1]}, {makeStr(self.src, self.localSrc is None)} {makeRelationArrow(self)} {makeStr(self.dst, self.localDst is None)}{ret[-1]}'
    #return f'{ret[:-1]}, {UP_ARROW if self._src is None else self._src._id} {"makeRelationArrow(self)"} {UP_ARROW if self._dst is None else self._dst._id}{ret[-1]}'
  
  def __hash__(self): #type: ignore[override]
    '''
    :returns:
    :rtype:
    '''
    return super().__hash__()
  
  def connect(self, source:Optional[GraphObject]=None, destination:Optional[GraphObject]=None):
    '''
    Connects or re-assigns the *src* and/or *dst* links by removing any existing
    links and setting the pointers in both this *Relation* and the target
    *GraphObjects*.
    
    .. Note::
    
      Use this method during Relation construction or when modifying the source 
      and/or destination of the Relation. This method ONLY applies to *Relations*.
      (contrast :py:meth:`GraphObject._disconnect` and 
      :py:meth:`GraphObject._reconnect`) 
    
    :param source: The :py:class:`GraphObject` for the *src* link.
    :type source: GraphObject
    :param destination: The :py:class:`GraphObject` for the *dst* link.
    :type destination: GraphObject
    '''
    if source is not None:
      if self.localSrc is not source: # don't do anything if it's already done.
        if self.localSrc is not None:
          delOne(self.localSrc._outgoing, self)
        self._src = source
        source._outgoing.append(self)
        assert self in source._outgoing
        self.setDirty()
    if destination is not None:
      if self.localDst is not destination: # don't do anything if it's already done.
        if self.localDst is not None:
          delOne(self.localDst._incoming, self)
        self._dst = destination
        destination._incoming.append(self)
        assert self in destination._incoming
        self.setDirty()
    
  # _disconnect()/_reconnect() of the src/dst ends are inherited from AGRelation.

class IsaIndividual(Relation):
  def __init__(self, db:Model, src:GraphObject|None=None, dst:GraphObject|None=None):
    '''
    :param db:
    :type db: Model
    :param src:
    :type src: GraphObject | None
    :param dst:
    :type dst: GraphObject | None
    '''
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

    :returns:
    :rtype: InstantiationInfo
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
    '''
    :param asTree:
    :type asTree: bool
    :param rmDups:
    :type rmDups: bool
    :returns:
    :rtype: list
    '''
    if asTree:
      return [self.db.ISA, [self.db.RELATION, [self.db.TOP]]]
    else:
      return [self.db.ISA, self.db.RELATION, self.db.TOP]
  
  @override
  def getParents(self)->list[GraphObject]:
    '''
    :returns:
    :rtype: list[GraphObject]
    '''
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
  def _endpointChanged(self, end:str, old:GraphObject|None, new:GraphObject|None) -> None:
    # the parents of our src (old and new, if it's the src that moved) have changed
    '''
    :param end:
    :type end: str
    :param old:
    :type old: GraphObject | None
    :param new:
    :type new: GraphObject | None
    '''
    for obj in ((old, new) if end == "src" else (self.localSrc,)):
      if obj is not None:
        obj.retract()
    super()._endpointChanged(end, old, new)

  @override
  def connect(self, source:Optional[GraphObject]=None, destination:Optional[GraphObject]=None):
    '''
    :param source:
    :type source: Optional[GraphObject]
    :param destination:
    :type destination: Optional[GraphObject]
    '''
    retract = source      is not None and source      is not self.localSrc or \
              destination is not None and destination is not self.localDst  
    super().connect(source, destination)
    if retract: #TODO: could be a lot more efficient by just fixing the parentCache's.
      self.retract()
    self.setDirty()
    
    
