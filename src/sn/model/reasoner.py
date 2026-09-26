'''
The engine-independent interface to back-end reasoners for
:py:class:`~sn.model.model.Model` objects.

A reasoner engine subclasses :py:class:`Reasoner` (see
:py:class:`sn.model.clingoReasoner.ClingoReasoner`). What is shared here:

- :py:meth:`Reasoner.facts` exports the model as engine-neutral facts. Their
  vocabulary is the contract every engine reasons over:

  ==========================  ================================================
  ``obj(O)``                  every GraphObject (including those of super-models)
  ``individual(O)``           GraphObject.isIndividual()
  ``kind(O,K)``               K in top, node, relation, isa
  ``collection(O)``           O is a Collection (also of kind node)
  ``name(O,S)``               GraphObject.name
  ``const(K,O)``              well-known objects: top, relation, isa, node, ...
  ``parent(X,P)``             GraphObject.getParents() (incl. implicit defaults)
  ``lsrc(R,C)``, ``ldst``     locally set relation endpoints (Relation._src/_dst)
  ``src(R,S)``, ``dst``       effective endpoints (Relation.src/.dst, inherited)
  ``link(R,S,D)``             individual, non-isa relation R with both endpoints
  ``prop(T,P)``               relation type T is tagged with P (reflexive,
                              irreflexive, symmetric, asymmetric, transitive)
  ``member(C,M)``             Collection membership
  ``attr(O,K,V)``             effective non-"vis/" scalar attributes
  ``lattr(O,K)``              O has attribute K locally
  ==========================  ================================================

- :py:class:`Inferences` and :py:class:`Violation` are what every engine
  returns, and the violation codes (see *_MESSAGES*) are shared.

- The typed queries (:py:meth:`Reasoner.related`, :py:meth:`Reasoner.isa`, ...)
  work with any engine. :py:meth:`Reasoner.query` is the engine's *native*
  query language (see :py:attr:`Reasoner.language`), and so is not portable.

The semantics every engine must implement are pinned down by
*test/test_model/test_reasoner.py*: an engine is conforming if it passes
*ReasonerSpec*.

The *Model* remains the single source of truth: reasoners never modify it.

Created on Sep 24, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>

'''
#################################################################################
# (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
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
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, ClassVar
import sn
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual

logger:sn.SNLogger = sn.getLogger(__name__)

PROPERTIES = ("reflexive", "irreflexive", "symmetric", "asymmetric", "transitive")
"The relational properties, which are tags on specific relations."

_MESSAGES:dict[str,str] = {
  "domain":                "source {2} of {0} is not a {3} (required by {1})",
  "range":                 "destination {2} of {0} is not a {3} (required by {1})",
  "isa_cycle":             "{0} is in an isa cycle through {1}",
  "isa_individual_parent": "{0} isa individual {1}",
  "redundant_parent":      "{0} has redundant parent {1} (already implied by {2})",
  "node_isa_relation":     "node {0} isa {1}",
  "relation_isa_node":     "relation {0} isa {1}",
  "irreflexive":           "irreflexive {0} relates {1} to itself",
  "asymmetric":            "asymmetric {0} relates {1} and {2} both ways",
  "property_conflict":     "{0} is both {1} and {2}",
  "unset_endpoint":        "{0} has no local {1}; it inherits its type's",
  }
"Message templates for violation codes: {0} is the subject, {1}... are the args."

class Sym(str):
  '''
  A symbolic constant in a fact (eg: the *node* in ``kind(O,node)``), as
  opposed to a plain *str*, which is string data (eg: a name).
  '''
  def __repr__(self) -> str:
    return f'Sym({str.__repr__(self)})'

Fact = tuple[str, tuple[Any, ...]]
"(predicate, args); args are GraphObjects, Syms, strs, ints, floats or bools."

@dataclass
class Violation:
  code:str
  "The rule that was violated, e.g. 'domain' or 'isa_cycle'."
  severity:str
  "'error' or 'warning'."
  subject:GraphObject
  "The object the violation should be reported against."
  args:tuple[Any, ...]
  "Other objects (or plain values) involved, in rule-specific order."

  @property
  def message(self) -> str:
    template = _MESSAGES.get(self.code, "{0}: " + self.code + " {1}")
    return template.format(*(_label(x) for x in (self.subject,) + self.args))

  def __str__(self) -> str:
    return f'{self.severity[0].upper()}: {self.message}'

@dataclass
class Inferences:
  '''
  The results of a :py:meth:`Reasoner.run`. Relation triples are
  ``(relationType, src, dst)``.
  '''
  holds:list[tuple[Relation, GraphObject, GraphObject]] = field(default_factory=list)
  "Every pair related under every relation type (asserted and inferred)."
  inferred:list[tuple[Relation, GraphObject, GraphObject]] = field(default_factory=list)
  "Pairs that are neither asserted nor implied by a more specific relation type."
  inherited:list[tuple[Relation, GraphObject, GraphObject]] = field(default_factory=list)
  "Pairs inherited down the isa hierarchy from the source's ancestors."
  classify:list[tuple[GraphObject, GraphObject]] = field(default_factory=list)
  "(object, type) suggestions: *object* should isa *type* to satisfy a signature."
  violations:list[Violation] = field(default_factory=list)
  isa:set[tuple[GraphObject, GraphObject]] = field(default_factory=set)
  "The reflexive-transitive isa closure."

  def related(self, src:GraphObject, relType:Relation) -> list[GraphObject]:
    return [d for t,s,d in self.holds if s is src and t is relType]

class Reasoner(ABC):
  '''
  The abstract base class of all reasoner engines. Usage::

    r = Reasoner.create(model)              # or eg: ClingoReasoner(model)
    result = r.run()
    for v in result.violations:
      print(v)
    r.related(fred, owns)                   # portable
    r.query('ans(X) :- ...')                # native to the engine

  Engines register themselves by name when subclassing::

    class MyReasoner(Reasoner, engine="mine"): ...

  :py:meth:`create` imports *sn.model.<engine>Reasoner* on demand, so an engine
  that lives there needs no other registration.
  '''

  engines:ClassVar[dict[str, type[Reasoner]]] = {}
  "Registered engines by name."

  language:ClassVar[str|None] = None
  "The name of the language :py:meth:`query` accepts, or None if it has none."

  def __init_subclass__(cls, engine:str|None=None, **kwargs):
    super().__init_subclass__(**kwargs)
    if engine is not None:
      Reasoner.engines[engine] = cls

  @classmethod
  def create(cls, model:Model, engine:str="clingo", **kwargs) -> Reasoner:
    if engine not in cls.engines:
      import_module(f'sn.model.{engine}Reasoner')
    return cls.engines[engine](model, **kwargs)

  def __init__(self, model:Model):
    self.model = model

  # ── Engine interface ─────────────────────────────────────────────────────

  @abstractmethod
  def run(self) -> Inferences:
    'Reason over the current state of the model.'

  def query(self, query:str) -> list[tuple[Any, ...]]:
    '''
    Run a query in the engine's native language (see :py:attr:`language`).

    :returns: Answer tuples, with the engine's object references mapped back
      to *GraphObjects*.
    '''
    raise NotImplementedError(f'{type(self).__name__} has no native query language.')

  # ── Portable queries ─────────────────────────────────────────────────────
  # These default to filtering a full run(); engines may override them with
  # something cheaper.

  def related(self, src:GraphObject, relType:Relation) -> list[GraphObject]:
    ':returns: Everything *src* is related to under *relType*, asserted or inferred.'
    return self.run().related(src, relType)

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    ':returns: Everything related to *dst* under *relType*, asserted or inferred.'
    return [s for t,s,d in self.run().holds if d is dst and t is relType]

  def isa(self, obj:GraphObject, typ:GraphObject) -> bool:
    return any(x is obj and t is typ for x,t in self.run().isa)

  def instances(self, typ:GraphObject, individualsOnly:bool=True) -> list[GraphObject]:
    ':returns: Every (individual) object that isa *typ*, other than *typ* itself.'
    return [x for x,t in self.run().isa if t is typ and x is not typ
            and (x.isIndividual() or not individualsOnly)]

  def violations(self, subject:GraphObject|None=None) -> list[Violation]:
    return [v for v in self.run().violations if subject is None or v.subject is subject]

  # ── Model export ─────────────────────────────────────────────────────────

  def objects(self) -> list[GraphObject]:
    ':returns: The objects of the model and (transitively) its super-models.'
    models:list[Model] = []
    pending = [self.model]
    while pending:
      m = pending.pop()
      if m not in models:
        models.append(m)
        pending.extend(m.superDBs) #type: ignore[arg-type]
    return [obj for m in models for obj in list(m.values())]

  def facts(self) -> list[Fact]:
    '''
    :returns: The model (and its super-models) as engine-neutral facts; see
      the module documentation for the vocabulary.
    '''
    out:list[Fact] = []
    for key in ("top", "relation", "isa", "node", "collection"):
      out.append(("const", (Sym(key), getattr(self.model, key.upper()))))

    # Work through a queue that grows if an object refers to one we haven't seen.
    queue = self.objects()
    seen = {id(o) for o in queue}
    def ref(obj:GraphObject) -> GraphObject:
      if id(obj) not in seen:
        seen.add(id(obj))
        queue.append(obj)
      return obj

    i = 0
    while i < len(queue):
      obj = queue[i]
      i += 1
      out.append(("obj", (obj,)))
      if obj.isIndividual():
        out.append(("individual", (obj,)))
      out.append(("kind", (obj, Sym(_kind(obj)))))
      out.append(("name", (obj, obj.name)))
      try:
        for p in obj.getParents():
          out.append(("parent", (obj, ref(p))))
      except RecursionError:
        out.append(("parent", (obj, obj))) # getParents() refuses self-parenting; let the rules report it
      except LookupError:
        pass
      if isinstance(obj, Collection):
        out.append(("collection", (obj,)))
        if type(obj) is Collection: # AllModelCollection would just list the model
          out += [("member", (obj, ref(m))) for m in obj.getMembers()]
      if isinstance(obj, Relation):
        out += self._relationFacts(obj, ref)
      for key in obj: # local and inherited keys
        if key == "name" or key.startswith("vis/"):
          continue
        if dict.__contains__(obj, key):
          out.append(("lattr", (obj, key)))
        try:
          value = obj.get(key, None) # effective value, per the Restriction rules
        except Exception:
          continue
        if isinstance(value, (bool, int, float, str)):
          out.append(("attr", (obj, key, value)))
    return out

  def _relationFacts(self, rel:Relation, ref) -> list[Fact]:
    out:list[Fact] = []
    if rel._src is not None:
      out.append(("lsrc", (rel, ref(rel._src))))
    if rel._dst is not None:
      out.append(("ldst", (rel, ref(rel._dst))))
    src, dst = rel.src, rel.dst
    if src is not None:
      out.append(("src", (rel, ref(src))))
    if dst is not None:
      out.append(("dst", (rel, ref(dst))))
    if rel.isIndividual() and not isinstance(rel, IsaIndividual) \
        and src is not None and dst is not None:
      out.append(("link", (rel, src, dst)))
    # Relational properties are LOCAL tags on relation types -- the key's
    # presence is the tag -- and are never inherited (brother isa sibling, but
    # brother isn't symmetric). See Relation._hasRelationalProperty().
    if rel.isType():
      for prop in PROPERTIES:
        if dict.__contains__(rel, prop):
          out.append(("prop", (rel, Sym(prop))))
    return out

def _kind(obj:GraphObject) -> str:
  if isinstance(obj, IsaIndividual):
    return "isa"
  if isinstance(obj, Relation):
    return "relation"
  if isinstance(obj, Node):
    return "node"
  return "top"

def _label(x:Any) -> str:
  if isinstance(x, GraphObject):
    return f'"{x.name}"({x.id})'
  return str(x)
