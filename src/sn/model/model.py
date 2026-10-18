'''
This is the base definitions of the :py:class:`Model`, its contained objects,
:py:class:`GraphObject` objects and specializations of these:

  - :py:class:`Node`
  
    - :py:class:`Collection`
    
      - :py:class:`AllModelCollection`
    
  - :py:class:`Relation`
  
    - :py:class:`IsaIndividual`
    
Models "live" in memory (:py:attr:`util.persistence.pRef.PRDb.AllDbs`) because 
one model can be shared by any number of views in the process. However, models
don't know about views (though views obviously know about models) and comminicate
with views only indirectly as Subject calling the the upddate() method of an
Observer in an Observer design pattern.

The various subtypes of :py:class:`GraphObject` model a typed graph of objects
in higher order logic ("higher order logic" because  also relations
participate in the type hierarchy). A subtype of :py:class:`Relation` called 
:py:class:`IsaIndividual` is necessary to implement special behaviour to prevent
endless recursion as *isa* is defined in terms of itself.

:py:class:`Node` is a simple subclass of :py:class:`GraphObject`, but acts as
the superclass to :py:class:`Collection` which forms the embodiment of subgraphs
such as queries, rules, and definitions in the logic.

.. inheritance-diagram:: Model GraphObject Node Relation IsaIndividual Collection AllModelCollection
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
from collections import deque
from contextlib import contextmanager
from util.persistence.pRef import PRObject, PRDb, PReference, PRDbContainer
from util.persistence.serialize import InstantiationInfo, ParamInfo, PropertyInfo,\
  SerializableType, Serializable
from util.persistence.serialize import DEFAULT_STRATEGY
from util.utils import delOne, extendsDoc
from typing import override, cast, Generator, Callable, Optional,\
  Iterable, overload, Iterator, Any
from util.attribute import AttributedObject, Attribute, NOVALUE, coerceValue
from util.observer import Subject
import sn
from util.dirtyable import Dirtyable
from util.abstractGraph import AGRelation, AbstractGraph, AGObject
from util.errorReportingObject import ErrorReportingObject
from sn.model.snAttribute import SNAttributedObject
from sn.model import names
from sn.model.names import NameKind

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

def nameMatcher(pattern:str, wholeWord:bool=False, matchCase:bool=False, regex:bool=False) -> Callable[[str], bool]:
  '''
  :param pattern: What to look for in a name: plain text, or with *regex* a
    regular expression (see the *re* module).
  :type pattern: str
  :param wholeWord: Only where it's a whole word (or words) of the name: not
    part of a longer one. As in a text editor, "-" and spaces separate words
    ("parent" is a whole word of "has-parent"); "_" doesn't.
  :type wholeWord: bool
  :param matchCase: Upper and lower case are different.
  :type matchCase: bool
  :param regex: *pattern* is a regular expression.
  :type regex: bool
  :returns: Whether a name matches: it has *pattern* in it anywhere.
  :rtype: Callable[[str], bool]
  :raises re.error: If *pattern* isn't a good regular expression.
  '''
  import re
  body = pattern if regex else re.escape(pattern)
  if wholeWord:
    body = rf'(?<!\w)(?:{body})(?!\w)'
  compiled = re.compile(body, 0 if matchCase else re.IGNORECASE)
  return lambda name: compiled.search(name) is not None

GORef = PReference["GraphObject"]

def removeDuplicateObjects(items:list, asTree:bool=False) -> list:
  '''
  As *util.utils.removeDuplicates()* -- the first of any duplicates is kept;
  if *asTree*, nested lists are de-duplicated too (against everything before
  them), and any left empty are dropped -- but by identity, which for model
  objects is what "==" is too (see *PRObject.__eq__()*), so in linear time,
  not quadratic (eg: 2000 subtypes of a type took *getDescendants()* 108 ms).

  :param items:
  :type items: list
  :param asTree:
  :type asTree: bool
  :returns: A copy of *items* without the duplicates.
  :rtype: list
  '''
  seen:set[int] = set()
  def do(items:list) -> list:
    ret = []
    for x in items:
      if asTree and isinstance(x, list):
        sub = do(x)
        if sub:
          ret.append(sub)
      elif id(x) not in seen:
        seen.add(id(x))
        ret.append(x)
    return ret
  return do(items)

_supersInProgress:set[int] = set()
"The objects whose supertypes *GraphObject.getSupers()* is finding, just now: to stop at an isa cycle."
_retracting:set[int] = set()
"The objects *GraphObject.retract()* is working down from, just now: to stop at an isa cycle."
_reportedSelfParents:set[int] = set()
"The objects whose isa link to themselves has been reported (see *GraphObject.getParents()*): it's said once."

_isaGeneration:int = 0
'''Bumped whenever a relation is connected, disconnected or reconnected, or has an
end changed (see *isaStructureChanged()*): an object's cached parents (see
*GraphObject.getParents()*) are good only for the generation they were found in.'''

def isaStructureChanged() -> None:
  '''
  Say that relations -- perhaps isa links -- have changed: every object's
  cached parents (see *GraphObject.getParents()*) are to be found again.
  Cheap: called on every relation change (eg: thousands of times reading a
  model); the parents are cached, and used, once things settle (eg: while a
  view's objects are made and drawn, which asks for them millions of times).
  '''
  global _isaGeneration
  _isaGeneration += 1

class GraphObject(AGObject["Model", "Relation"], SNAttributedObject, ErrorReportingObject):
  '''
  .. Note::
  
    *GraphObject* is a **subclass** but not strictly a **subtype** of *PRObject* as 
    its container object pointer (*Model*) is subtype of the its parent's pointer
    (*PRDb*).
  '''

  inferredKey:tuple
  "An object the reasoner made: what identifies it (set only on those: see *sn.model.reasoner.materialize()*)."
  inferredKind:str
  "An inferred object: how it came to be, eg: \"new\", \"rule\" (set only on those: see *sn.model.reasoner.materialize()*)."
  
  def __init__(self, db:Model, parents:Iterable[GraphObject]=[], individual:bool=False, name:Optional[str]=None,
               inferred:bool=False, **kwargs):
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
    :param inferred: Whether it's something the reasoner concluded, not
      something asserted (see *inferred*): its isa links are too. Set before
      anyone is told it's there.
    :type inferred: bool
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

    self._parentsCache:list[GraphObject]|None = None
    "This object's parents, found in generation *_parentsGeneration* (see *getParents()*)."
    self._parentsGeneration:int = -1
    
    self._individual = individual
    self.inferred:bool = inferred
    '''
    Whether this is something the reasoner concluded (see
    *sn.model.reasoner.reason()*), not asserted: it's left out when the model
    is saved, and the next "reason" keeps, replaces or removes it.
    '''

    super().__init__(db=db, **kwargs)

    if parents is not None: # Will be None when reading in from persistent store
      for p in parents:
        IsaIndividual(db, self, p, inferred=inferred)
    if name is not None:
      try:
        self["name"] = name
      except Exception as ex:
        logger.warning(f'Cannot update name field ({ex.__class__.__name__}): {ex}')
      

  @classmethod
  @override
  @extendsDoc(Serializable)
  def getInstantiationInfo(cls) -> InstantiationInfo:
    '''
    The *self._outgoing* and *self.incoming* lists and the *parents* constructor
    param are all left empty here as they will be restored by the relevant 
    :py:class:`Relation` objects.
    '''
    # :returns: A description of the constructor parameters and how to fill them
    #   (conArgs, conKWArgs), and a further description of any additional data to
    #   be filled after immediately after the constructor (postconSetters) and 
    #   more after any contained objects have been fully constructed (finalSetters).
    # :rtype: InstantiationInfo
    # '''
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
    for rel in self._incoming: # (an isa is never symmetric: skipped first, as a type's incoming isa's can be many)
      if not isinstance(rel, IsaIndividual) and filtr(rel) and rel.isSymmetric():
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
    for rel in self._outgoing: # (an isa is never symmetric: see _getOutgoing())
      if not isinstance(rel, IsaIndividual) and filtr(rel) and rel.isSymmetric():
        yield rel, rel.localDst if localOnly else rel.dst
        
  def _validateTypesFound(self) -> None:
    '''
    Report (in its status report) a type of its that couldn't be found when it
    was read (eg: deleted from an ontology it uses): its isa link to it is
    left unconnected (see *Relation.getInstantiationInfo()*), and it's taken
    to be of no type.
    '''
    for isa in self._outgoing:
      if isinstance(isa, IsaIndividual) and isa.localDst is None and isa.statusReport():
        why = next((str(x) for x in isa.statusReport() if "couldn't be found" in str(x)), "")
        self.assertToStatusReport(False, f'Its type couldn\'t be found{": " + why.split(": ", 2)[-1] if why else ""}', "E")

  def validate(self) -> list[str]:        
    '''
    :returns:
    :rtype: list[str]
    '''
    self._validateTypesFound()
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
    self._validateSelfIsa()
    return self.statusReport()
  
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
    super()._disconnect(**kwargs)
    isaStructureChanged()
      
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
    super()._reconnect(**kwargs)
    isaStructureChanged()

    for child in self.getChildren(): #TODO: could be more efficient by just fixing the parentCache's.
      child.retract()
      
  def retract(self):
    '''
    Resets the parent cache of this object and all isa-decendents of this object.
    '''
    self._parentsCache = None
    if id(self) in _retracting: # (an isa cycle: see getSupers())
      return
    _retracting.add(id(self))
    try:
      for child in self.getChildren():
        child.retract()
    finally:
      _retracting.discard(id(self))

  @override
  def getSupers(self, asTree:bool=False, rmDups:bool=True) -> list:
    '''
    :param asTree:
    :type asTree: bool
    :param rmDups:
    :type rmDups: bool
    :returns: A list of all super types to this object in mro order.
    :rtype: list[GraphObject]
    '''
    cacheable = not asTree and rmDups and not _supersInProgress # (whole answers only: not part-way round an isa cycle)
    if cacheable:
      cached = self.__dict__.get("_supersCache")
      if cached is not None and cached[0] == _isaGeneration: # (good until relations change: see isaStructureChanged())
        return list(cached[1])
    ret:list = []
    have:set[int] = set() # (ids of ret's objects -- not of its sublists, if asTree)
    for parent in self.getParents(): #gather ancestors in mro order
      if id(parent) not in have: #TODO: this test will likely fail in the the "asTree" case...
        ret.append(parent)
        have.add(id(parent))
        if id(parent) in _supersInProgress: # (an isa cycle -- eg: from an old file: see parentProblem() -- don't go round it forever)
          continue
        _supersInProgress.add(id(parent))
        try:
          if asTree:
            ret.append(parent.getSupers(asTree=asTree, rmDups=rmDups))
          else:
            supers = parent.getSupers(asTree=asTree, rmDups=rmDups)
            ret += supers
            have.update(id(s) for s in supers)
        finally:
          _supersInProgress.discard(id(parent))
    if rmDups:
      ret = removeDuplicateObjects(ret, asTree=asTree)
    if cacheable:
      self.__dict__["_supersCache"] = (_isaGeneration, list(ret))
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
    if self._parentsCache is not None and getattr(self, "_parentsGeneration", -1) == _isaGeneration:
      return list(self._parentsCache) # (a copy: a caller may change what it's given)
    
    ret = [other for _rel,other in self._getOutgoing(lambda r: isinstance(r, IsaIndividual)) if other is not None] 
    if ret == [] and type(self) is not GraphObject:
      raise LookupError("No parent found.")
    if self in ret: # (eg: from a file written before that was refused: see parentProblem()) -- left out, and reported (once)
      if id(self) not in _reportedSelfParents:
        _reportedSelfParents.add(id(self))
        logger.error(f'"{self.name}" ({self.model.url}#{self._id}) has an isa link to itself: it\'s ignored. '
                     f'Remove it (see its error report, or select the link and "remove from model").')
      ret = [p for p in ret if p is not self]
      if ret == [] and type(self) is not GraphObject:
        raise LookupError("No parent found.")

    self._parentsCache, self._parentsGeneration = list(ret), _isaGeneration # (good until relations change: see isaStructureChanged())
    return ret   

  def selfIsaLinks(self) -> list[IsaIndividual]:
    '''
    :returns: This object's (asserted) isa links to itself -- which no longer
      can be made (see *parentProblem()*), but an old file may have.
    :rtype: list[IsaIndividual]
    '''
    return [r for r in self._outgoing if isinstance(r, IsaIndividual) and r.localSrc is self and r.localDst is self]

  def _validateSelfIsa(self) -> None:
    '''
    Report an isa link to itself (see *selfIsaLinks()*) in the status report,
    with an action that removes it.
    '''
    for r in self.selfIsaLinks():
      self.assertToStatusReport(False, f'"{self.name}" has an isa link to itself (ignored).', "E",
                                actions={"remove the isa link to itself": lambda r=r: [r._disconnect(), r.model.setDirty(), None][-1]}) #type: ignore[func-returns-value, misc]

  def parentProblem(self, parent:GraphObject|None) -> str|None:
    '''
    :param parent: A would-be new parent (type) of this object: the
      destination of a new isa link from it.
    :type parent: GraphObject | None
    :returns: Why it can't be: it's this object itself, or one of its own
      subtypes or instances (an isa cycle, which would make each its own
      ancestor); or None if it can.
    :rtype: str | None
    '''
    if parent is None:
      return None
    if parent is self:
      return f'"{self.name}" can\'t be a type of itself.'
    try:
      if parent.isa(self):
        return f'"{parent.name}" is already a kind of "{self.name}": making "{self.name}" one of it would make an isa cycle.'
    except (RecursionError, LookupError):
      pass
    return None

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
      ret = removeDuplicateObjects(ret, asTree=asTree)
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

  def variableKind(self) -> NameKind:
    '''
    :returns: What this object's name makes it (see *sn.model.names*): a
      constant (NameKind.CONSTANT), or a variable that stands for "something"
      in a pattern (a rule, definition, query or constraint) -- individuals
      (NameKind.INDIVIDUAL, eg: "?x"), types (NameKind.TYPE, eg: "^T"), or
      either (NameKind.ANY, eg: "!a").
    :rtype: NameKind
    '''
    try:
      return names.nameKind(self.name)
    except Exception: # eg: during construction, before it has a name
      return NameKind.CONSTANT

  def isVariable(self) -> bool:
    '''
    :returns: True iff this is a variable (see *variableKind()*).
    :rtype: bool
    '''
    return self.variableKind().isVariable

  def isAnyVariable(self) -> bool:
    '''
    :returns: True iff this is an "any" variable (see *variableKind()*), which
      matches individuals and types alike.
    :rtype: bool
    '''
    return self.variableKind() is NameKind.ANY

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
      constr = self.getLocal(CONSTRAINTS, None)
      assert constr is None or isinstance(constr, str) # (None: no constraints)
      return parseConstraints(constr)
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
      constr = self.getLocal(CONSTRAINTS, None)
      assert constr is None or isinstance(constr, str) # (None: no constraints)
      parseConstraints(constr)
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
        under it, asserted or inferred (eg: under a supertype of the
        relations, or through a transitive one);
      - without: nothing -- the relations it inferred or found inherited are
        in the model, as inferred relations (see *GraphObject.inferred*).

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
    return []

  def _chain(self, types:list[Relation], filtr:Callable[[Relation], bool], seen:set[int], outgoing:bool) -> list[tuple[Relation,GraphObject]]:
    '''
    What this object is related to (*outgoing*) or from by chains of relations
    of the transitive relation *types* (or their subtypes; see
    *Relation._transitiveTypes()*): eg: by *has-ancestor* and *has-parent* relations,
    if *has-parent* isa *has-ancestor*, which is transitive.

    :param types: Transitive relation types.
    :type types: list[Relation]
    :param filtr: Which relations may be followed.
    :type filtr: Callable[[Relation], bool]
    :param seen: The ids of objects not to go through again (eg: where the chain starts).
    :type seen: set[int]
    :param outgoing:
    :type outgoing: bool
    :returns: (relation, object) pairs.
    :rtype: list[tuple[Relation, GraphObject]]
    '''
    ret:list[tuple[Relation,GraphObject]] = []
    todo:deque[GraphObject] = deque([self])
    while todo:
      o = todo.popleft()
      if o.id in seen:
        continue
      seen.add(o.id)
      for q, x in (o._getOutgoing if outgoing else o._getIncoming)(lambda q: filtr(q) and any(q.isa(t) for t in types)):
        if x is not None:
          ret.append((q, x))
          todo.append(x)
    return ret

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
    have = {id(o) for _, o in pairs} if byObjectOnly else {(id(r), id(o)) for r, o in pairs} #type: ignore[misc]
    for r, o in more:
      key = id(o) if byObjectOnly else (id(r), id(o))
      if key not in have:
        have.add(key) #type: ignore[arg-type]
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
      inferred: its inferred relations (see *GraphObject.inferred*), and what
      it found related under *rel* (see *_inferredRelated()*).
    :type inferred: bool
    :returns:
    :rtype: list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    seen:set[int] = set() if _seen is None else _seen
    if self.id in seen:
      return []
    else:
      seen.add(self.id)
    return self._related(rel, outgoing=True, inferred=inferred, addInferred=_seen is None) # (the outermost call only)

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
  def getRelatedFrom(self, rel:Relation|None=None, *, inferred:bool=True, _snapshot:bool=True) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    '''
    :param rel: If given, only relations that isa *rel*, and just the related
      objects are returned; otherwise (relation, object) pairs.
    :type rel: Relation | None
    :param inferred: [default=True] Also include what the model's last "reason"
      inferred (as for *getRelatedTo()*).
    :type inferred: bool
    :returns:
    :rtype: list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    return self._related(rel, outgoing=False, inferred=inferred, addInferred=_snapshot)

  def _related(self, rel:Relation|None, *, outgoing:bool, inferred:bool, addInferred:bool) -> list[GraphObject]|list[tuple[Relation,GraphObject]]:
    '''
    What *getRelatedTo()* and *getRelatedFrom()* share: they differ only in the
    direction. A reflexive relation relates *self* to itself too, and an
    irreflexive one never does.

    :param rel: If given, only relations that isa *rel*, and just the related
      objects are returned; otherwise (relation, object) pairs.
    :type rel: Relation | None
    :param outgoing: The relations from *self* (else those to it).
    :type outgoing: bool
    :param inferred: Also include the relations the model's last "reason" inferred.
    :type inferred: bool
    :param addInferred: Also add what that "reason" found related (see *_inferredRelated()*).
    :type addInferred: bool
    :returns:
    :rtype: list[GraphObject] | list[tuple[Relation, GraphObject]]
    '''
    ret:list[tuple[Relation,GraphObject]] = []
    r: Relation
    typeOk:Callable[[Relation], bool] = (lambda r: True) if rel is None else (cast(Callable[[Relation], bool], lambda r, typ=rel: r.isa(typ)))
    # pattern relations (inside rules etc.) aren't about the world -- unless we're a pattern element ourselves
    patternOk:Callable[[Relation], bool] = (lambda r: True) if self.isPatternElement() else (lambda r: not r.isPatternElement())
    filtr:Callable[[Relation], bool] = lambda r: typeOk(r) and patternOk(r) and (inferred or not r.inferred)
    for r,other in (self._getOutgoing(filtr) if outgoing else self._getIncoming(filtr)):
      if other is not None:
        ret.append((r, other))
        if other is not self and (chainTypes := r._transitiveTypes(rel)):
          # add in what's related to (or from) *other* by the same transitive relation (or subtypes of it)
          ret += other._chain(chainTypes, filtr, {self.id}, outgoing=outgoing)
        if r.isReflexive() and other is not self: # (*self* is related to itself by it too)
          ret.append((r, self))
    if inferred and addInferred:
      self._addNew(ret, self._inferredRelated(rel, outgoing=outgoing), byObjectOnly=rel is not None)
      
    if rel is not None:
      ret2:list[GraphObject] = list({id(o): o for _, o in ret}.values()) # return only the objects (each once)
      if rel.isIrreflexive():
        return [x for x in ret2 if x is not self]
      return ret2
    
    return [(r,o) for r,o in ret if not(r.isIrreflexive() and o is self)] # return the rel/object pairs


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

  def individualChangeProblem(self, individual:bool) -> str|None:
    '''
    :param individual: True to make this an individual, False a type.
    :type individual: bool
    :returns: Why it can't be made one (see *setIndividual()*), or None if it can.
    :rtype: str | None
    '''
    what = "an individual" if individual else "a type"
    if self._individual == individual:
      return f'it\'s {what} already'
    if self.model.writeLocked():
      return f'"{self.model.name}" is write locked'
    if getattr(self, "inferred", False):
      return 'it\'s inferred: mark it as asserted first'
    if isinstance(self, Relation): # (a relation type's ends are a domain and range its instances inherit; an individual's are its own)
      return 'it\'s a relation: its ends would mean something else'
    if individual and (children := self.getChildren()): # (an individual can't have instances or subtypes)
      return f'it has instances or subtypes: {", ".join(c.name for c in children[:5])}{", ..." if len(children) > 5 else ""}'
    from util.attribute import NOOVERRIDE
    for key in dict.keys(self): # (an attribute it overrides that it couldn't, as the other kind)
      try:
        inherited = self._getSuperAttr(key)
      except Exception:
        continue
      r = getattr(getattr(inherited, "restriction", None), "individual" if individual else "type", None)
      if r is not None and r & NOOVERRIDE:
        return f'as {what}, it couldn\'t override its inherited "{key}"'
    return None

  def setIndividual(self, individual:bool) -> None:
    '''
    Make this an individual (or, if *individual* is False, a type): eg: a
    pattern variable whose name says it matches individuals (?x), but that was
    made a type. Observers are told with a ("mod individual", (individual,))
    topic. Use it through *ModelContext.set_kind()* (it's undoable).

    :param individual:
    :type individual: bool
    :raises ValueError: If it can't be (see *individualChangeProblem()*).
    '''
    problem = self.individualChangeProblem(individual)
    if problem is not None:
      raise ValueError(f'"{self.name}" can\'t be made {"an individual" if individual else "a type"}: {problem}.')
    self._individual = individual
    self.model.setDirty()
    self.notify(("mod individual", (individual,)))

  DISABLED = "disabled"
  "The attribute that switches a context (a rule, definition, constraint, ...) off: see *isDisabled()*."

  def isDisabled(self) -> bool:
    '''
    :returns: True iff this has a "disabled" attribute (its own, or inherited)
      that isn't false: eg: a rule that's switched off while experimenting.
      The reasoner ignores a disabled rule, definition or constraint (see
      *sn.model.reasoner.rules()*), and the view draws a red slash through it.
      (A value that isn't a bool counts as true -- unless it's "false", "no",
      "0", ... -- see *coerceValue()*.)
    :rtype: bool
    '''
    try:
      value = self.get(self.DISABLED, None)
    except Exception:
      return False
    if value is None or value is NOVALUE or value is False:
      return False
    try:
      return bool(coerceValue(bool, value))
    except ValueError:
      return True

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
    except Exception: # KeyError: none set or inherited; or anything, part-way through making the object (names show in messages)
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
    self._refuseIfInferred("change")
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
    self._refuseIfInferred("change")
    local = dict.get(self, key)
    if isinstance(local, Attribute) and local.inferred and not getattr(self.model, "_inferringDepth", 0):
      # (a value given where one was inferred: it's given now -- a new attribute, so undo puts the inferred one back)
      self.setAttr(key, Attribute(value, local.type, local.restriction, local.note))
      return
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
    self._refuseIfInferred("change")
    return super().setAttr(key, attr)

  def _refuseIfInferred(self, doing:str) -> None:
    '''
    :param doing: What's being done to it, eg: "change", for the message.
    :type doing: str
    :raises PermissionError: If this is inferred (see *inferred*) -- except
      while the reasoner is making or removing inferred objects (see
      *Model.inferring()*). It has to be marked as asserted first (see
      *assertedWith()*, and the "mark asserted" command).
    '''
    if self.inferred and not getattr(self.model, "_inferringDepth", 0):
      raise PermissionError(f'"{self.name}" is inferred: mark it as asserted to {doing} it.')

  def assertedWith(self) -> list[GraphObject]:
    '''
    What has to be marked as asserted along with this inferred object (see
    *inferred*): itself, its inferred isa links, and -- for a relation -- its
    inferred ends (and theirs, ...). (They're all inferred, so not saved: an
    asserted relation can't refer to an object that isn't.) For an object a
    rule concluded exists, the relations the rule gave it too: without them,
    the next "reason" would make another one in its place.

    :returns: The inferred objects, this one first ([] if it isn't inferred).
    :rtype: list[GraphObject]
    '''
    ret:list[GraphObject] = []
    have:set[int] = set() # (ids of ret's)
    pending:deque[GraphObject] = deque([self])
    while pending:
      o = pending.popleft()
      if not getattr(o, "inferred", False) or id(o) in have:
        continue
      ret.append(o)
      have.add(id(o))
      pending += [r for r, _ in o._getOutgoing(lambda r: isinstance(r, IsaIndividual) and r.inferred)]
      if isinstance(o, Relation):
        pending += [e for e in (o.localSrc, o.localDst) if e is not None]
      elif getattr(o, "inferredKind", None) == "new": # (see sn.model.reasoner.materialize())
        rule = lambda r: r.inferred and getattr(r, "inferredKind", None) == "rule"
        pending += [r for r, _ in o._getOutgoing(rule)] + [r for r, _ in o._getIncoming(rule)]
    return ret
    
    
def unresolvedReason(ref:str, ex:Exception) -> str:
  '''
  :param ref: A reference to an object -- eg: "#12", or "http://.../ontology.snm#256" --
    that couldn't be followed.
  :type ref: str
  :param ex: Why not.
  :type ex: Exception
  :returns: Why not, in plain words: eg, there's no model at that URL, or the
    model there has no such object.
  :rtype: str
  '''
  where, _, which = ref.rpartition("#")
  cause:BaseException|None = ex
  while cause is not None:
    if isinstance(cause, FileNotFoundError) or (isinstance(cause, OSError) and getattr(cause, "errno", None) == 2):
      return f'there\'s no model at "{where}"' if where else str(cause)
    cause = cause.__cause__ or cause.__context__
  if isinstance(ex, KeyError):
    return f'"{where or "this model"}" has no object #{which}' if which else f'no such object ({ex})'
  if isinstance(ex, LookupError) and "No strategy succeeded" in str(ex):
    return f'"{where}" couldn\'t be read as a model'
  return f'{type(ex).__name__}: {ex}'

def _isRemote(url:str) -> bool:
  '''
  :returns: Whether *url* is on the web (eg: "https://..."): a model there can
    be read, but not saved there, so it's write-locked once it's read (see
    *Model._wasRead()*).
  '''
  from urllib.parse import urlparse
  return urlparse(url).scheme in ("http", "https")

def _isPackagedBaseRules(url:str) -> bool:
  '''
  :param url: A model's URL.
  :type url: str
  :returns: True iff it's the file of base rules that comes with the program
    (see *sn.model.reasoner.BASE_RULES*) -- opened directly, not as the base
    rules (which read a copy of it).
  :rtype: bool
  '''
  import os
  from urllib.parse import urlparse, unquote
  from importlib.resources.abc import Traversable
  try:
    from sn.model.reasoner import BASE_RULES
    parsed = urlparse(url)
    if parsed.scheme != "file":
      return False
    path = os.path.realpath(unquote(parsed.path))
    return any(isinstance(src, Traversable) and os.path.realpath(str(src)) == path for src in BASE_RULES)
  except Exception:
    return False

SN_URL = "sn:/sn"
'''The system model's URL: a name ("sn:" is for models in memory -- see
*PRDb.namedURLs*), not a file. (Its old names are aliases for it: see
*PRDb.aliases*.)'''

PRDb.aliases.update({old: SN_URL for old in ("sn:/sn.xml", "sn:///sn", "sn:///sn.xml", "sn:sn")})

BASE_RULES_URL = "sn:/baseRules"
'''The base rules' name (see *sn.model.reasoner.BASE_RULES*): they're read from
a temporary copy of a file that comes with the program, so models refer to
them by this (see *PRDb.namedURLs*).'''

def _baseRulesURL() -> str:
  from sn.model import reasoner
  return reasoner._baseURLOfModel(reasoner.BASE_RULES[0])

PRDb.namedURLs[BASE_RULES_URL] = _baseRulesURL

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

  _inferringDepth:int
  "While inside *inferring()* (set only then): how deeply."

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
    model = TopModel(SN_URL, mode="", _reading=False) # creates a model in memory cache
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
    ret = PRDb.__new__(cls, url, mode=mode, memoryResident=True, _reading=_reading)
    if not _reading and isinstance(ret, Model) and getattr(ret, "_initialized", False) and not getattr(ret, "_writeLocked", False) \
       and _isPackagedBaseRules(ret.url):
      ret._writeLocked = True
      logger.info(f'"{ret.url}" is the base rules that come with the program: it\'s read-only here '
                  '(they\'re made by tools/makeBaseRules.py).')
    return ret

  def unlistedModels(self) -> dict[Model, int]:
    '''
    :returns: The models this one's objects refer to (by relations' ends,
      eg: an isa link to a type) that aren't among its super-models (see
      *allSuperDBs()*): each with how many references there are to it. There
      should be none -- eg: an ontology moved to the web, but some objects
      still referring to the local copy (see *replaceSuperModel()*).
    :rtype: dict[Model, int]
    '''
    allowed = {id(self), *(id(db) for db in self.allSuperDBs())}
    ret:dict[Model, int] = {}
    for obj in list(self._db.values()):
      if not isinstance(obj, Relation):
        continue
      for end in (obj.localSrc, obj.localDst):
        db = getattr(end, "db", None)
        if isinstance(db, Model) and id(db) not in allowed:
          ret[db] = ret.get(db, 0) + 1
    return ret

  UNRESOLVED_SHOWN = 10
  "The most references that couldn't be followed listed when a model's read (see *_wasRead()*)."

  @override
  def _wasRead(self, url:str) -> None:
    '''
    Once it's read: say which references to objects couldn't be followed (if
    any: eg, to an object in a model at a URL where there's nothing -- the
    relations are left unconnected at that end, and say why in their status
    reports); and, if it's from the web (eg: an ontology, or a super-model),
    write-lock it: it can't be saved there.

    :param url:
    :type url: str
    '''
    super()._wasRead(url)
    unresolved = self.__dict__.pop("_unresolved", [])
    if unresolved:
      shown = unresolved[:self.UNRESOLVED_SHOWN]
      more = f"\n  ... and {len(unresolved) - len(shown)} more" if len(unresolved) > len(shown) else ""
      logger.warning(f'"{url}": {len(unresolved)} reference{"s" if len(unresolved) > 1 else ""} to objects couldn\'t be '
                     f'followed (the relations are left unconnected at that end):\n  '
                     + "\n  ".join(f"{what}: {why}" for what, why in shown) + more)
    unlisted = self.unlistedModels()
    if unlisted:
      supers = ", ".join(f'"{PRDb.relativeURL(db.url, base=self.url)}"' for db in self.superDBs) or "none"
      logger.warning(f'"{url}": its objects refer to objects in models that aren\'t among its super-models '
                     f'(they are: {supers}):\n  '
                     + "\n  ".join(f'"{db.url}": {n} reference{"s" if n > 1 else ""}' for db, n in unlisted.items())
                     + '\nMake each one of its super-models (Edit | Model preferences...), or put the right one in its place '
                       '(Edit | Replace super-model...).')
    if _isRemote(url) and not self._writeLocked:
      self._writeLocked = True
      logger.info(f'"{url}" is on the web: it\'s read-only here.')
    

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
    if hasattr(self, "_initialized"): # (PRDb.__new__() returned one that's in memory already, or that it's just read: its
      return                          # observers -- eg: its views -- prefs and replacedModels mustn't be lost)
    PRDb.__init__(self, url, mode=mode, memoryResident=True, _reading=_reading)
    Subject.__init__(self)
    Dirtyable.__init__(self)
    
    for db in self.implicitSuperDBs(): # (the system model, then the base rules)
      if db not in self.superDBs:
        self.superDBs.append(db) #type: ignore[arg-type]

    from sn.model.modelPrefs import ModelPrefs, initModelPrefs
    self.replacedModels:dict[str, str] = {}
    '''Models replaced by others as this one's super-models (see *replaceSuperModel()*):
    old URL -> new URL. Its views' references to objects in the old ones are taken to be to
    the same objects in the new ones when they're read.'''
    self.prefs:ModelPrefs = ModelPrefs()
    "This model's own preferences (see *sn.model.modelPrefs*): saved with it."
    initModelPrefs(self.prefs)
    
    self.TOP:GraphObject = GORef.eval("$sn#top") #type: ignore[assignment]
    self.RELATION:Relation = GORef.eval("$sn#relation") #type: ignore[assignment]
    self.ISA:Relation = GORef.eval("$sn#3") #type: ignore[assignment]
    self.NODE:Node = GORef.eval("$sn#node") #type: ignore[assignment]
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
    self.CONSTRAINT:Node = GORef.eval("$sn#constraint") #type: ignore[assignment]
    self.REQUIREMENT:Node = GORef.eval("$sn#requirement") #type: ignore[assignment]
    self.CONDITION:Relation = GORef.eval("$sn#condition") #type: ignore[assignment]
    self.REQUIRED:Relation = GORef.eval("$sn#required") #type: ignore[assignment]

    if _reading: # (its nextID is read too)
      return

    self.nextID:int = 256
    
  @override
  @classmethod
  def getInstantiationInfo(cls) -> InstantiationInfo:
    ret:InstantiationInfo = super().getInstantiationInfo()
    ret.class_ = cls
    def setPrefs(slf:Serializable, prefs:SerializableType) -> None:
      from sn.model.modelPrefs import ModelPrefs, initModelPrefs
      if isinstance(prefs, ModelPrefs):
        cast(Model, slf).prefs = prefs
        initModelPrefs(prefs) # (any added since it was saved; and their notes)
    from sn.model.modelPrefs import ModelPrefs
    for p in ret.postconSetters:
      if p.name == "_db": # (inferred objects aren't saved: see GraphObject.inferred)
        def assertedObjects(slf:Serializable) -> SerializableType:
          from util.persistence.serialize import strdict
          ret:strdict[Any] = strdict()
          for k, v in cast(Model, slf)._db.items():
            if not getattr(v, "inferred", False):
              ret[str(k)] = v
          return ret
        p.getter = assertedObjects
    ret.postconSetters.append(PropertyInfo("replacedModels", dict, lambda slf: dict(cast(Model, slf).replacedModels) or None,
                                           lambda slf, v: setattr(slf, "replacedModels", dict(cast(dict, v or {}))),
                                           omitIfNone=True, inHead=True)) # (references to other files: in the head)
    ret.postconSetters.append(PropertyInfo("prefs", ModelPrefs, lambda slf: cast(Model, slf).prefs, setPrefs,
                                           optional=True)) # optional: older files don't have it
    ret.finalSetters.append(PropertyInfo("_", bool, setter=lambda slf,_t:cast(Model,slf).setDirty(False))) #type: ignore[arg-type]
    ret.finalSetters.append(PropertyInfo("_", bool, setter=lambda slf,_t:cast(Model,slf)._migrate())) #type: ignore[arg-type]
    return ret

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
      if obj is not None and not (getattr(obj, "inferred", False)) and obj.isDirty():
        Dirtyable.setDirty(self, True)
        return True
    return False

  @contextmanager
  def inferring(self, *others:Model) -> Iterator[None]:
    '''
    A context in which the reasoner adds and removes inferred objects (see
    *GraphObject.inferred*) in this model -- and connects them to objects in
    *others* (eg: its super-models) -- without making any of them dirty: they
    aren't saved. It works on write-locked models too: they can be reasoned
    over, though what's inferred can't be marked as asserted in them.

    :param others: Other models whose objects the inferred objects refer to.
    :type others: Model
    '''
    models = [self, *[m for m in others if m is not self]]
    state = [(m, m._writeLocked, m.isDirty()) for m in models]
    for m in models:
      m._writeLocked = False
      m._inferringDepth = getattr(m, "_inferringDepth", 0) + 1 # (inferred objects may be changed: see GraphObject._refuseIfInferred())
    try:
      yield
    finally:
      for m, locked, dirty in state:
        m._writeLocked = locked
        m._inferringDepth -= 1
        if not dirty:
          m.setDirty(False)

  def inferredObjects(self) -> list[GraphObject]:
    '''
    :returns: This model's inferred objects (see *GraphObject.inferred*).
    :rtype: list[GraphObject]
    '''
    return [o for o in self._db.values() if getattr(o, "inferred", False)]

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
      url = SN_URL
      mode = ""
    ret = super().getDB(url, mode=mode)
    if not isinstance(ret, Model):
      raise TypeError(f'Database "{url}" is of type {ret.__class__.__name__}; expected type Model."')
    return ret
      
  @override
  def serializationHeader(self) -> dict[str, Any]:
    '''
    :returns: What's in the head of its file (see *PRDb.serializationHeader()*),
      and the version of the structures it's saved in (see *sn.SCHEMA_VERSION*).
    :rtype: dict[str, Any]
    '''
    return {**super().serializationHeader(), "schema": sn.SCHEMA, "schemaVersion": sn.SCHEMA_VERSION}

  @override
  def objectCount(self) -> int:
    ''':returns: How many of its objects are saved: not those inferred (see *GraphObject.inferred*).'''
    return sum(1 for k, v in self._db.items() if k != 0 and not getattr(v, "inferred", False))

  def implicitSuperDBs(self) -> list[Model]:
    '''
    :returns: The super-models every model has, first: the system model
      (sn), and the base rules (see *sn.model.reasoner.BASE_RULES*) -- but
      not the base rules themselves, while they're being read (see
      *sn.model.reasoner.baseRuleModels()*). They can't be removed. They're
      saved with a model by name ("sn:/sn", "sn:/baseRules": see
      *PRDb.namedURLs*), as its first super-models.
    :rtype: list[Model]
    '''
    from sn.model.reasoner import baseRuleModels
    return [cast(Model, GORef.eval("$sn"))] + [m for m in baseRuleModels() if m is not self]

  def superModelPaths(self) -> list[str]:
    '''
    :returns: This model's super-models (see *PRDb.superDBs*) in order, as
      shown to the user: their files relative to this one's where they're
      near it; then any that couldn't be read when it was. Not the implicit
      ones (see *implicitSuperDBs()*): they're always the first.
    :rtype: list[str]
    '''
    implicit = self.implicitSuperDBs()
    return [PRDb.relativeURL(db.url, base=self.url) for db in self.superDBs if not any(db is i for i in implicit)] \
         + list(self._missingSuperDBs)

  def replacedRef(self, ref:str) -> str:
    '''
    :param ref: A reference to an object, as read (eg: from one of this
      model's views): eg, "familyOntology.snm#256" (relative to the file being
      read).
    :type ref: str
    :returns: *ref*, or -- if it's to an object in a model this one's replaced
      (see *replaceSuperModel()*) -- a reference to the same object in the
      model that replaced it.
    :rtype: str
    '''
    where, hash_, which = ref.rpartition("#")
    if not hash_ or not where or not self.replacedModels:
      return ref
    try:
      url = PRDb.resolveURL(where)
    except Exception:
      return ref
    new = self.replacedModels.get(url)
    return f"{new}#{which}" if new else ref

  def replaceSuperModel(self, old:Model, new:Model) -> int:
    '''
    Put *new* in *old*'s place: as a super-model (in the same position; or
    added, if *old* wasn't one -- see *unlistedModels()*), and as what this
    model's objects refer to -- each reference to one of *old*'s objects
    becomes a reference to the object with the same id in *new* (eg: *new*
    is a copy of *old*, moved to the web). Recorded (see *replacedModels*), so
    the model's views, when they're read, are taken to refer to *new* too.
    Nothing is changed unless every object referred to is in *new*.

    :param old: A model this one's objects refer to.
    :type old: Model
    :param new: The model to refer to instead.
    :type new: Model
    :returns: How many references were changed.
    :rtype: int
    :raises ValueError: If it can't be done -- eg: an object referred to isn't
      in *new*, or it has a different name there -- listing why; or *new* is
      this model, or builds on it.
    '''
    if new is self or self in new.allSuperDBs():
      raise ValueError(f'"{new.url}" can\'t be a super-model of "{self.url}": it is, or builds on, it.')
    if any(old is m for m in self.implicitSuperDBs()):
      raise ValueError(f'"{old.url}" is built in: it can\'t be replaced.')
    changes:list[tuple[Relation, bool, GraphObject]] = []
    problems:list[str] = []
    for obj in list(self._db.values()):
      if not isinstance(obj, Relation):
        continue
      for isSource, end in ((True, obj.localSrc), (False, obj.localDst)):
        if end is None or end.db is not old:
          continue
        target = new._db.get(end._id)
        if not isinstance(target, GraphObject):
          problems.append(f'#{end._id} ({end.name}): not in "{new.url}"')
        elif type(target) is not type(end) or str(target.name) != str(end.name):
          problems.append(f'#{end._id} ({end.name}): in "{new.url}", it\'s {type(target).__name__} "{target.name}"')
        else:
          changes.append((obj, isSource, target))
    if problems:
      raise ValueError(f'"{new.url}" isn\'t a copy of "{old.url}" (as far as this model is concerned):\n  '
                       + "\n  ".join(sorted(set(problems))))
    for rel, isSource, target in changes:
      rel.connect(source=target) if isSource else rel.connect(destination=target)
    supers = [new if db is old else db for db in self.superDBs]
    if not any(db is new for db in supers):
      supers.append(new)
    kept:list[PRDb] = []
    for db in supers: # (new may have been one already: once, where it first is)
      if not any(db is k for k in kept):
        kept.append(db)
    self.superDBs[:] = kept #type: ignore[assignment]
    for k, v in list(self.replacedModels.items()): # (anything replaced by old is now replaced by new)
      if v == old.url:
        self.replacedModels[k] = new.url
    self.replacedModels[old.url] = new.url
    self.setDirty()
    return len(changes)

  def setSuperModels(self, paths:list[str]) -> None:
    '''
    Make this model's super-models those at *paths*, in that order, after the
    implicit ones (always the first: see *implicitSuperDBs()*): eg: as edited
    in its preferences (see *superModelPaths()*). Relative paths are relative to this model's file.
    Nothing is changed unless all of them are fine.

    :param paths: The super-models' files (or URLs).
    :type paths: list[str]
    :raises ValueError: listing the paths that can't be used, and why: eg:
      not a model, can't be read, or builds on this one.
    '''
    implicit = self.implicitSuperDBs()
    dbs:list[PRDb] = []
    missing:list[str] = []
    problems:list[str] = []
    for p in paths:
      p = p.strip()
      if not p:
        continue
      if p in self._missingSuperDBs: # (still missing: kept, as it was)
        missing.append(p)
        continue
      try:
        db:PRDb[Any] = PRDb.getDB(PRDb.absoluteURL(p, base=self.url))
      except Exception as ex:
        problems.append(f'"{p}": {ex}')
        continue
      if not isinstance(db, Model):
        problems.append(f'"{p}" isn\'t a model.')
      elif db is self or self in db.allSuperDBs():
        problems.append(f'"{p}" is, or builds on, this model.')
      elif not any(db is i for i in implicit) and db not in dbs:
        dbs.append(db)
    if problems:
      raise ValueError("\n".join(problems))
    new = implicit + dbs
    if new != self.superDBs or missing != self._missingSuperDBs:
      self.superDBs[:] = new #type: ignore[assignment]
      self._missingSuperDBs[:] = missing
      self.setDirty()

  @override
  def removeSuperDB(self, db:PRDb) -> None:
    '''
    As *PRDb.removeSuperDB()* -- but the implicit super-models (see
    *implicitSuperDBs()*), which every model builds on -- the system model
    (sn: the definitions Semantic Nets needs: node, relation, isa, ...) and
    the base rules -- can't be removed.

    :param db: The model.
    :type db: PRDb
    :raises ValueError: if *db* is one of the implicit super-models.
    '''
    if db is self.TOP.model:
      raise ValueError(f'The system model ("{db.url}") is a super-model of every model: it can\'t be removed.')
    if any(db is m for m in self.implicitSuperDBs()):
      raise ValueError(f'The base rules ("{db.url}") are a super-model of every model: they can\'t be removed.')
    super().removeSuperDB(db)

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
    if saveas is None: # (saving a copy elsewhere doesn't save this: see PRDb.save())
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

  def search(self, pattern:str, wholeWord:bool=False, matchCase:bool=False, regex:bool=False,
             superModels:bool=False) -> list[GraphObject]:
    '''
    :param pattern: What to look for in names (see *nameMatcher()*).
    :type pattern: str
    :param wholeWord: See *nameMatcher()*.
    :type wholeWord: bool
    :param matchCase: See *nameMatcher()*.
    :type matchCase: bool
    :param regex: See *nameMatcher()*.
    :type regex: bool
    :param superModels: Look in its super-models too (see *PRDb.allSuperDBs()*).
    :type superModels: bool
    :returns: The nodes and relations (types and individuals, asserted and
      inferred) whose names match: this model's, in order, then each
      super-model's, nearest first. Not isa links: they're all "isa".
    :rtype: list[GraphObject]
    :raises re.error: If *regex* and *pattern* isn't a good regular expression.
    '''
    matches = nameMatcher(pattern, wholeWord=wholeWord, matchCase=matchCase, regex=regex)
    ret:list[GraphObject] = []
    for db in [self] + (self.allSuperDBs() if superModels else []):
      if not isinstance(db, Model):
        continue
      for go in db.values():
        if isinstance(go, GraphObject) and not isinstance(go, (IsaIndividual, AllModelCollection)) \
           and matches(str(go.name)):
          ret.append(go)
    return ret

  def dependents(self) -> list[tuple[str, str]]:
    '''
    :returns: What still uses this model, as (kind, URL) pairs: ("view", ...)
      for each view of it still observing it (an open window: closing a
      window's view stops it observing -- see *SNGView.detachFromModel()*),
      and ("model", ...) for each other model in memory that builds on it:
      that has a relation into it (eg: an isa link to one of its types), or
      lists it among its super-models.
    :rtype: list[tuple[str, str]]
    '''
    ret:list[tuple[str, str]] = []
    for observer, _topics in self._observers:
      if not getattr(observer, "_closed", False) and getattr(observer, "model", self) is self: # (not a view of another model showing its objects: see SNGView._observeModel())
        ret.append(("view", getattr(observer, "url", repr(observer))))
    for url, db in list(PRDb.AllDBs.items()): # @UndefinedVariable
      if db is self or not isinstance(db, Model):
        continue
      if self in db.superDBs or any(isinstance(o, Relation) and any(end is not None and end.db is self for end in (o.localSrc, o.localDst))
                                    for o in db.values()):
        ret.append(("model", url))
    return ret

  def unload(self) -> None:
    '''
    Forget this model -- eg: to read its file afresh after the file has been
    replaced. It's dropped from the cache of open databases (*PRDb.AllDBs*),
    and its relations are removed from the objects of *other* models they
    connect to (eg: its objects' isa links to the system model's *node*), so
    nothing outside it still leads to it. (The model itself is left as it is,
    and isn't saved.)

    :raises RuntimeError: if anything still uses it (see *dependents()*): an
      open view of it, or another model with relations into it -- which would
      be left pointing at its old objects. Close those first.
    '''
    users = self.dependents()
    if users:
      raise RuntimeError(f'Can\'t unload model {self.url}: still used by ' + ", ".join(f"{kind} {url}" for kind, url in users))
    for obj in list(self.values()):
      if not isinstance(obj, Relation):
        continue
      for end, links in ((obj.localSrc, "_outgoing"), (obj.localDst, "_incoming")):
        if end is not None and end.db is not self:
          delOne(getattr(end, links), obj, throw=False)
    if PRDb.AllDBs.get(self.url) is self: # @UndefinedVariable
      del PRDb.AllDBs[self.url]

  def _makeDBContainer(self) -> AllModelCollection:
    '''
    :returns:
    :rtype: AllModelCollection
    '''
    return AllModelCollection(self)
  
          
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
    
    
  
class Relation(GraphObject, AGRelation[Model, GraphObject]): #type: ignore[misc]
  def __init__(self, db:Model,
               parents:Iterable[GraphObject]=[],
               src:GraphObject|None=None,
               dst:GraphObject|None=None,
               individual:bool=False,
               name:Optional[str]=None,
               inferred:bool=False):
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
    :param inferred: See *GraphObject.__init__()*.
    :type inferred: bool
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
    super().__init__(db=db, parents=parents, individual=individual, name=name, src=src, dst=dst, inferred=inferred)

    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    def connectSrc(slf:Relation, source:str, isSource:bool):
      if source is not None and source!="None":
        sideText = "src" if isSource else "dst"
        problem:str|None = None
        obj:Any = None
        try:
          obj = GORef.eval(source, slf.db)
          assert isinstance(obj, GraphObject)
          if isSource:
            slf.connect(source=obj)
          else:
            slf.connect(destination=obj) 
        except AssertionError:
          problem = f'it isn\'t an object of a model (it\'s a {type(obj).__name__})'
        except Exception as ex:
          problem = unresolvedReason(source, ex)
        if problem is not None:
          described = slf.describeEnd(isSource, source)
          slf.assertToStatusReport(False, f'Its {sideText} couldn\'t be found: {described}: {problem}.', "E",
                                   actions={"remove relation from model": lambda: [slf.model.setDirty(), slf._disconnect(), slf.model.setDirty(), None][-1]}) #type: ignore[func-returns-value]
          slf.db.__dict__.setdefault("_unresolved", []).append((described, problem))
        
    ret = GraphObject.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(Relation, slf).db)],
            conKWArgs=[ParamInfo("individual", bool, lambda slf: cast(Relation, slf)._individual)],
            postconSetters=ret.postconSetters,
            finalSetters=ret.finalSetters+
                          [PropertyInfo("src", str, 
                                        lambda slf: GORef.formatForURL(slf.localSrc, slf.db), #type: ignore[attr-defined]
                                        lambda slf, source: connectSrc(slf, source, isSource=True)), #type: ignore[arg-type]
                           PropertyInfo("dst", str, 
                                        lambda slf: GORef.formatForURL(slf.localDst, slf.db), #type: ignore[attr-defined]
                                        lambda slf, source: connectSrc(slf, source, isSource=False))]  #type: ignore[arg-type]
            )

  def describeEnd(self, isSource:bool, ref:str) -> str:
    '''
    :param isSource: Whether it's this relation's source (else its destination) that's described.
    :type isSource: bool
    :param ref: The reference to it, as it was read (eg: "http://.../ontology.snm#256").
    :type ref: str
    :returns: This relation as its source, its name and *ref* -- eg: "Fred isa
      → http://.../ontology.snm#256" -- for a message saying *ref* couldn't
      be found (see *getInstantiationInfo()*).
    :rtype: str
    '''
    def name(o:Any, depth:int=0) -> str:
      try:
        if isinstance(o, Relation) and depth == 0: # (eg: a relation whose type is missing: by its ends)
          return f'({name(o.localSrc, 1)} \u2192 {name(o.localDst, 1)})'
        return str(o.name) if o is not None else "?"
      except Exception:
        return "?"
    other = name(self.localDst if isSource else self.localSrc)
    return f'{ref} \u2192 {name(self, 1)} \u2192 {other}' if isSource else f'{other} {name(self, 1)} \u2192 {ref}'

  @property
  def dst(self) -> GraphObject|None:
    '''
    :return: The *calculated* destination of this relation; ie: if this relation
      does not have a specific destination, look it up in the ISA hierarchy
      (*self.localDst* is its own).
    :rtype: GraphObject | None
    '''
    if self.localDst is not None:
      return self.localDst
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        if not isinstance(obj, Relation):#, f'Expected type Relation, got type {type(obj)}.'
          self.assertToStatusReport(False, f'Expected type Relation for supertype, got type {type(obj)}. Probably a changed parent model.', 'E', 
            actions={"delete this relation": lambda: [self._disconnect(), self.model.setDirty(), None][-1]}) #type: ignore[arg-type,func-returns-value]
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
   
  @property
  def src(self) -> GraphObject|None:
    '''
    :return: The *calculated* source of this relation; ie: if this relation
      does not have a specific source, look it up in the ISA hierarchy
      (*self.localSrc* is its own).
    :rtype: GraphObject | None
    '''
    if self.localSrc is not None:
      return self.localSrc
    else:
      obj:GraphObject
      supers = self.getSupers()
      for obj in supers:
        if not isinstance(obj, Relation):#, f'Expected type Relation, got type {type(obj)}.'
          self.assertToStatusReport(False, f'Expected type Relation for supertype, got type {type(obj)}. Probably a changed parent model.', 'E', 
            actions={"delete this relation": lambda: [self._disconnect(), self.model.setDirty(), None][-1]}) #type: ignore[arg-type,func-returns-value]
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
    isaStructureChanged()
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
    self._validateTypesFound()
    self._validateSelfIsa()
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
  
  def _transitiveTypes(self, within:Relation|None=None) -> list[Relation]:
    '''
    The transitive relation types (see *isTransitive()*) this relation is one
    of: eg: a *has-parent* is a *has-ancestor*, so where *has-ancestor* is
    transitive, chains of them (and of *has-parent* relations) give
    *has-ancestor* relations, though *has-parent* itself isn't transitive.

    :param within: If given, only the types that are *within* or below it (a
      query about *has-parent* doesn't chain through *has-ancestor*).
    :type within: Relation | None
    :returns:
    :rtype: list[Relation]
    '''
    try:
      types = self.isa()
    except (LookupError, AttributeError): # eg: during initialization
      return []
    return [t for t in types if isinstance(t, Relation) and t.isType() and dict.__contains__(t, "transitive")
            and (within is None or t.isa(within))]

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
    return f'{ret[:-1]}, {makeStr(self.src, self.localSrc is None)} {makeRelationArrow(self)} {makeStr(self.dst, self.localDst is None)}{ret[-1]}'
  
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
    if (source is not None and self.localSrc is not source) or (destination is not None and self.localDst is not destination):
      isaStructureChanged()
    if source is not None:
      if self.localSrc is not source: # don't do anything if it's already done.
        if self.localSrc is not None:
          delOne(self.localSrc._outgoing, self)
        self._src = source
        source._outgoing.append(self)
        assert source._outgoing[-1] is self # (not "self in ...": that compares by == along what can be a long list)
        self.setDirty()
    if destination is not None:
      if self.localDst is not destination: # don't do anything if it's already done.
        if self.localDst is not None:
          delOne(self.localDst._incoming, self)
        self._dst = destination
        destination._incoming.append(self)
        assert destination._incoming[-1] is self
        self.setDirty()
  # _disconnect()/_reconnect() of the src/dst ends are inherited from AGRelation.

class IsaIndividual(Relation):
  def __init__(self, db:Model, src:GraphObject|None=None, dst:GraphObject|None=None, inferred:bool=False):
    '''
    :param db:
    :type db: Model
    :param src:
    :type src: GraphObject | None
    :param dst:
    :type dst: GraphObject | None
    :param inferred: See *GraphObject.__init__()*.
    :type inferred: bool
    '''
    if not db.reading:
      if src is None or dst is None:
        raise ValueError("IsaIndividual.__init__(): ISA relations require both a source and destination.")
    super().__init__(db, [], src, dst, individual=True, inferred=inferred)
    
    
  @classmethod
  @override
  def getInstantiationInfo(cls)->InstantiationInfo:
    sup = Relation.getInstantiationInfo()
    return InstantiationInfo(
            cls, 
            conArgs=[ParamInfo("db", Model, lambda slf: cast(Relation, slf).db)], # no conKWargs
            postconSetters=sup.postconSetters,
            finalSetters=sup.finalSetters
            )

  @override
  def getSupers(self, asTree:bool=False, rmDups:bool=True) -> list:
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
    
  @override
  def _endpointChanged(self, end:str, old:GraphObject|None, new:GraphObject|None) -> None:
    # the parents of our src (old and new, if it's the src that moved) have changed
    '''
    We want to change the end points from one object to another.
    
    :param end: The end to change. Either 'src' or 'dst'
    :type end: str
    :param old: The original object at that end point.
    :type old: GraphObject | None
    :param new: The new object to attach to.
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
    
    
