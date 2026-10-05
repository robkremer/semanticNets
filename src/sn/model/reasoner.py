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
  ``lsrc(R,C)``, ``ldst``     locally set relation endpoints (Relation.localSrc/.localDst)
  ``domain(T,C)``, ``range``  the signature of relation type T (Relation.domain/.range)
  ``src(R,S)``, ``dst``       effective endpoints (Relation.src/.dst, inherited)
  ``link(R,S,D)``             individual, non-isa relation R with both endpoints
  ``prop(T,P)``               relation type T is tagged with P (reflexive,
                              irreflexive, symmetric, asymmetric, transitive)
  ``member(C,M)``             Collection membership
  ``attr(O,K,V)``             effective non-"vis/" scalar attributes
  ``lattr(O,K)``              O has attribute K locally
  ``pattern(X)``              X describes a pattern (in a rule etc.), not the world
                              (see GraphObject.isPatternElement())
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
import importlib.resources
from importlib.resources.abc import Traversable
import atexit
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, ClassVar, Iterator
from contextlib import contextmanager, ExitStack
from util.observer import Subject
import sn
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual
from util.attribute import Attribute, Restriction
from sn.model.constraints import CONSTRAINTS, PRESENT, ValueVar

logger:sn.SNLogger = sn.getLogger(__name__)

PROPERTIES = ("reflexive", "irreflexive", "symmetric", "asymmetric", "transitive")
"The relational properties, which are tags on specific relations."

_MESSAGES:dict[str,str] = {
  "domain":                "{2}, the source of {0}, is not in the domain of {1} ({3})",
  "range":                 "{2}, the destination of {0}, is not in the range of {1} ({3})",
  "isa_cycle":             "{0} is in an isa cycle through {1}",
  "isa_individual_parent": "{0} isa individual {1}",
  "redundant_parent":      "{0} has redundant parent {1} (already implied by {2})",
  "node_isa_relation":     "node {0} isa {1}",
  "relation_isa_node":     "relation {0} isa {1}",
  "irreflexive":           "irreflexive {0} relates {1} to itself",
  "asymmetric":            "asymmetric {0} relates {1} and {2} both ways",
  "property_conflict":     "{0} is both {1} and {2}",
  "unset_endpoint":        "{0} has no local {1}; it inherits its type's",
  "rule_unbound":          "rule {0}: {1} in the consequent isn't bound by the antecedent",
  "rule_open_end":         "rule {0}: {1} in the consequent has no {2}",
  "rule_unsupported":      "rule {0}: {1} in the consequent isn't supported (yet)",
  "bad_constraints":       "{0}: the constraints of {1} can't be read: {2}",
  "constraint_report":     "constraint {0}: {1} in its report isn't one of its variables",
  "constraint_severity":   "constraint {0}: its severity is {1}; it should be error or warning",
  }
"Message templates for violation codes: {0} is the subject, {1}... are the args."

class Sym(str):
  '''
  A symbolic constant in a fact (eg: the *node* in ``kind(O,node)``), as
  opposed to a plain *str*, which is string data (eg: a name).
  '''
  def __repr__(self) -> str:
    '''
    :returns: A string representation of this object.
    :rtype: str
    '''
    return f'Sym({str.__repr__(self)})'

Fact = tuple[str, tuple[Any, ...]]
"(predicate, args); args are GraphObjects, Syms, strs, ints, floats or bools."

@dataclass(frozen=True)
class NewObject:
  '''
  An object a rule concludes exists: one per match of the rule's antecedent,
  for a consequent variable the antecedent doesn't bind (eg: "every person
  has a mother": ?m). It's not in the model -- just in the reasoning results.
  '''
  rule:GraphObject
  variable:str
  "The consequent variable's name, eg: \"?m\"."
  bindings:tuple[tuple[str, Any], ...]
  "The match it's for: (variable name, value) pairs of the antecedent's variables."

  def label(self, relativeTo:Model|None=None) -> str:
    '''
    How it\'s named in messages, eg: "(new ?m for ?p=alice)", with objects named relative to *relativeTo*.

    :param relativeTo:
    :type relativeTo: Model | None
    :returns:
    :rtype: str
    '''
    match = ", ".join(f"{n}={_label(v, relativeTo)}" for n, v in self.bindings)
    return f"(new {self.variable}{' for ' + match if match else ''})"

  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
    :rtype: str
    '''
    return self.label()

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
  template:str|None = field(default=None, compare=False)
  "The message template (as *_MESSAGES*'), if not the code's: eg: a constraint's own message (see *ConstraintSpec*)."

  @property
  def message(self) -> str:
    '''
    The message, with objects named relative to the subject\'s model.

    :returns:
    :rtype: str
    '''
    return self.messageIn(self.subject.model)

  def messageIn(self, relativeTo:Model|None) -> str:
    '''
    The message, with objects named relative to *relativeTo* (see *GraphObject.tostring()*).

    :param relativeTo:
    :type relativeTo: Model | None
    :returns:
    :rtype: str
    '''
    template = self.template or _MESSAGES.get(self.code) or ("{0}: " + self.code + "".join(f" {{{i}}}" for i in range(1, len(self.args) + 1)))
    labels = [_label(x, relativeTo) for x in (self.subject,) + self.args]
    try:
      return template.format(*labels)
    except (IndexError, KeyError, ValueError): # (a user's template that doesn't fit)
      return f'{template} ({", ".join(labels)})'


  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
    :rtype: str
    '''
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
  fired:list[tuple[GraphObject, Relation, GraphObject|NewObject, GraphObject|NewObject]] = field(default_factory=list)
  "(rule, relationType, src, dst): relations the rules concluded (see *ruleOf()*)."
  ruleAttrs:list[tuple[GraphObject, GraphObject|NewObject, str, Any]] = field(default_factory=list)
  "(rule, object, key, value): attributes the rules concluded."
  ruleIsa:list[tuple[GraphObject, GraphObject|NewObject, GraphObject]] = field(default_factory=list)
  "(rule, object, type): isa links the rules concluded."
  newObjects:list[NewObject] = field(default_factory=list)
  '''
  The objects the rules concluded exist. Relations involving them are only in
  *fired* (not *holds*, *inferred*, ...: those are about the model's objects).
  '''

  def _index(self) -> tuple[dict, dict]:
    '''
    ({(id(src), id(type)): [dst...]}, {(id(dst), id(type)): [src...]}) over
    *holds*, built on first use: results don't change once made.

    :returns:
    :rtype: tuple[dict, dict]
    '''
    idx = self.__dict__.get("_idx")
    if idx is None:
      fwd:dict[tuple[int, int], list[GraphObject]] = {}
      back:dict[tuple[int, int], list[GraphObject]] = {}
      for t, s, d in self.holds:
        fwd.setdefault((id(s), id(t)), []).append(d)
        back.setdefault((id(d), id(t)), []).append(s)
      idx = self.__dict__["_idx"] = (fwd, back)
    return idx

  def related(self, src:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    Everything *src* is related to under *relType* (asserted or inferred).

    :param src:
    :type src: GraphObject
    :param relType:
    :type relType: Relation
    :returns:
    :rtype: list[GraphObject]
    '''
    return list(self._index()[0].get((id(src), id(relType)), []))

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    Everything related to *dst* under *relType* (asserted or inferred).

    :param dst:
    :type dst: GraphObject
    :param relType:
    :type relType: Relation
    :returns:
    :rtype: list[GraphObject]
    '''
    return list(self._index()[1].get((id(dst), id(relType)), []))

  def newFacts(self) -> list[tuple[Relation, GraphObject, GraphObject]]:
    '''
    The inferred and inherited relation triples (each once) -- ie: not asserted.

    :returns:
    :rtype: list[tuple[Relation, GraphObject, GraphObject]]
    '''
    seen:set[tuple[int, int, int]] = set()
    ret = []
    for t, s, d in self.inferred + self.inherited:
      if (id(t), id(s), id(d)) not in seen:
        seen.add((id(t), id(s), id(d)))
        ret.append((t, s, d))
    return ret

  def ruleConclusions(self, rule:GraphObject|None=None, model:Model|None=None) -> list[str]:
    '''
    What the rules (or just *rule*) concluded that's new -- relations not
    already asserted, attributes, isa links and new objects -- one line each,
    with the rule that concluded it. Objects are named relative to *model*.

    :param rule:
    :type rule: GraphObject | None
    :param model:
    :type model: Model | None
    :returns:
    :rtype: list[str]
    '''
    new = {(id(t), id(s), id(d)) for t, s, d in self.inferred}
    by = lambda r: "" if rule is not None else f"   (by {_label(r, model)})"
    mine = lambda r: rule is None or r is rule
    lines = [f'{_label(s, model)} {relationArrow(t)} {_label(d, model)}{by(r)}' for r, t, s, d in self.fired
             if mine(r) and ((id(t), id(s), id(d)) in new or isinstance(s, NewObject) or isinstance(d, NewObject))]
    attr = lambda k, v: k if v is True or v is PRESENT else f"{k}: {v}"
    known = lambda x, k, v: v is not PRESENT and x.get(k, None) == v # (already so: not news)
    lines += [f'{_label(x, model)} {{{attr(k, v)}}}{by(r)}' for r, x, k, v in self.ruleAttrs
              if mine(r) and not isinstance(x, NewObject) and not known(x, k, v)]
    lines += [f'{_label(x, model)} -isa-> {_label(t, model)}{by(r)}' for r, x, t in self.ruleIsa
              if mine(r) and not isinstance(x, NewObject) and not x.isa(t)]
    for n in self.newObjects: # (one line each: that it exists, its types and its attributes)
      if mine(n.rule):
        types = ", ".join(_label(t, model) for _, x, t in self.ruleIsa if x == n)
        attrs = ", ".join(attr(k, v) for _, x, k, v in self.ruleAttrs if x == n)
        lines.append(f'{_label(n, model)} exists{": a " + types if types else ""}{" {" + attrs + "}" if attrs else ""}{by(n.rule)}')
    return lines

  def ruleObjects(self, rule:GraphObject) -> list[GraphObject]:
    '''
    The model objects *rule* concluded something about (not new objects).

    :param rule:
    :type rule: GraphObject
    :returns:
    :rtype: list[GraphObject]
    '''
    ret:dict[int, GraphObject] = {}
    new = {(id(t), id(s), id(d)) for t, s, d in self.inferred}
    for r, t, s, d in self.fired:
      if r is rule and ((id(t), id(s), id(d)) in new or isinstance(s, NewObject) or isinstance(d, NewObject)):
        ret.update({id(x): x for x in (s, d) if isinstance(x, GraphObject)})
    for r, x, *_ in self.ruleAttrs + self.ruleIsa: # type: ignore[operator]
      if r is rule and isinstance(x, GraphObject):
        ret[id(x)] = x
    return list(ret.values())

  def violationsFor(self, subject:GraphObject) -> list[Violation]:
    '''
    :param subject:
    :type subject: GraphObject
    :returns:
    :rtype: list[Violation]
    '''
    return [v for v in self.violations if v.subject is subject]

  def report(self, model:Model|None=None) -> str:
    '''
    :param model: If given, leave out findings that only involve system
      objects (those of the always-in-memory "sn" model) -- noise to a user.
    :type model: Model | None
    :returns: A readable summary: violations, new relations (inferred and
      inherited) and suggested classifications.
    :rtype: str
    '''
    def relevant(*objs:Any) -> bool:
      return model is None or any(isinstance(o, GraphObject) and not o.isSystemObject() for o in objs)
    def triple(t:Relation, s:GraphObject, d:GraphObject) -> str:
      return f'  {_label(s, model)} {relationArrow(t)} {_label(d, model)}'
    lines:list[str] = []
    violations = [v for v in self.violations if relevant(v.subject, *v.args)]
    errors = sum(v.severity == "error" for v in violations)
    lines.append(f'Violations: {errors} error(s), {len(violations) - errors} warning(s)')
    lines += [f'  {v.severity[0].upper()}: {v.messageIn(model)}' for v in sorted(violations, key=lambda v: (v.severity != "error", v.code))]
    inherited = {(id(t), id(s), id(d)) for t, s, d in self.inherited}
    inferred = [(t, s, d) for t, s, d in self.inferred if relevant(s, d) and (id(t), id(s), id(d)) not in inherited]
    lines.append(f'Inferred relations: {len(inferred)}')
    lines += [triple(*x) for x in inferred]
    lines.append(f'Rule conclusions: {len(self.ruleConclusions())}')
    lines += [f'  {c}' for c in self.ruleConclusions(model=model)]
    inh = [(t, s, d) for t, s, d in self.inherited if relevant(s, d)]
    lines.append(f'Inherited relations: {len(inh)}')
    lines += [triple(*x) for x in inh]
    cls = [(x, c) for x, c in self.classify if relevant(x)]
    lines.append(f'Suggested classifications: {len(cls)}')
    lines += [f'  {_label(x, model)} -isa-> {_label(c, model)}' for x, c in cls]
    return "\n".join(lines)

@dataclass
class Pattern:
  '''
  The pattern a context (eg: a query, or a rule's antecedent) describes, in an
  engine-neutral form: engines translate it (see *Reasoner.answer()*). Any
  object below may be a variable (see *GraphObject.isVariable()*); None as a
  relation end means "something" (an unterminated relation).
  '''
  context:GraphObject
  variables:list[GraphObject] = field(default_factory=list)
  "The variables, in answer order (by name)."
  triples:list[tuple[GraphObject, GraphObject|None, GraphObject|None]] = field(default_factory=list)
  "(relation type, src, dst): the relation must hold."
  types:list[tuple[GraphObject, GraphObject]] = field(default_factory=list)
  "(x, type): x isa type."
  distinct:list[tuple[GraphObject, GraphObject]] = field(default_factory=list)
  "(x, y): x and y are different objects (a contained \"distinct\" relation)."
  constraints:list[tuple[GraphObject, str, Any]] = field(default_factory=list)
  '''
  (variable, key, value): what the variable matches must have attribute *key*
  (see *GraphObject.constraints()* and *sn.model.constraints*) -- with any
  value if *value* is PRESENT; the same value as other constraints naming it
  if it's a *ValueVar*; else equal to *value*. A relational property
  (symmetric, ...) is a tag: PRESENT or True means it's there, False not.
  '''
  errors:list[tuple[GraphObject, str]] = field(default_factory=list)
  "(variable, message): constraints that can't be parsed (see *GraphObject.constraintsError()*)."

def patternOf(context:GraphObject, parts:tuple[GraphObject, ...]|None=None) -> Pattern:
  '''
  :param context:
  :type context: GraphObject
  :param parts: The "contains"-family relation types to read the pattern from.
    By default, all of them other than "consequent" and "definiendum": so for a
    rule, its antecedent, and for a definition, its definiens.
  :type parts: tuple[GraphObject, ...] | None
  :returns: The *Pattern* of *context*: everything it contains (through
    *parts*).
  :rtype: Pattern

    - A contained relation must hold, between its (local) ends, for each of its
      types; an end it doesn't have is "something".
    - A contained isa link is a type constraint; so are a variable's own isa
      parents (other than the base node/relation types, which say nothing).
    - A relation whose type is a variable ranges over relation types.
    - A contained "distinct" relation says its two ends are different objects
      (the usual "for all x, y: x != y, ..."), rather than a relation to find.
    - A variable's own attributes are constraints on what it matches (see
      *GraphObject.constraints()*).
  '''
  m = context.model
  ret = Pattern(context)
  variables:dict[int, GraphObject] = {}
  def note(x:GraphObject|None) -> None:
    if x is not None and x.isVariable() and id(x) not in variables:
      variables[id(x)] = x
      ret.constraints += [(x, k, v) for k, v in x.constraints().items()]
      if (err := x.constraintsError()) is not None:
        ret.errors.append((x, err))
      for p in x.getParents():
        if p not in (m.NODE, m.RELATION, m.TOP) and not isinstance(x, IsaIndividual):
          ret.types.append((x, p))
  inPattern = (lambda r: any(r.isa(p) for p in parts)) if parts is not None else \
              (lambda r: r.isa(m.CONTAINS) and not r.isa(m.CONSEQUENT) and not r.isa(m.DEFINIENDUM))
  contained = [r.localDst for r, _ in context._getOutgoing(lambda r: r.isIndividual() and inPattern(r))
               if r.localDst is not None]
  for e in contained:
    if isinstance(e, IsaIndividual):
      if e.localSrc is not None and e.localDst is not None:
        ret.types.append((e.localSrc, e.localDst))
        note(e.localSrc); note(e.localDst)
    elif isinstance(e, Relation) and e.isIndividual() and e.isa(m.DISTINCT):
      if e.localSrc is not None and e.localDst is not None: # a constraint, not a relation that must hold
        ret.distinct.append((e.localSrc, e.localDst))
      note(e.localSrc); note(e.localDst)
    elif isinstance(e, Relation) and e.isIndividual():
      for t in e.getParents():
        ret.triples.append((t, e.localSrc, e.localDst))
        note(t)
      note(e.localSrc); note(e.localDst)
    else:
      note(e)
  ret.types = list({(id(x), id(t)): (x, t) for x, t in ret.types}.values()) # once each
  ret.variables = sorted(variables.values(), key=lambda v: v.name)
  return ret

@dataclass
class RuleSpec:
  '''
  A rule, in an engine-neutral form: when its antecedent's *pattern* matches,
  its consequent's relations (*heads*) hold and its *assertions* (attributes)
  are true, for the matching values of the variables. Variables are the same
  variable wherever they have the same name in the rule, so the consequent can
  have its own copies of the antecedent's variables.
  '''
  rule:GraphObject
  pattern:Pattern
  "The antecedent (see *patternOf()*)."
  heads:list[tuple[GraphObject, GraphObject, GraphObject]] = field(default_factory=list)
  "(relation type, src, dst): what the rule concludes holds."
  assertions:list[tuple[GraphObject, str, Any]] = field(default_factory=list)
  "(variable, key, value): attributes the rule concludes -- the constraints of the consequent's own variables."
  isas:list[tuple[GraphObject, GraphObject]] = field(default_factory=list)
  "(x, type): isa links the rule concludes."
  new:list[GraphObject] = field(default_factory=list)
  "The consequent's variables the antecedent doesn't bind: a new object for each match (see *NewObject*)."
  problems:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): why the rule can't be used (it's skipped)."

def ruleOf(rule:GraphObject) -> RuleSpec:
  '''
  :param rule:
  :type rule: GraphObject
  :returns: The *RuleSpec* of *rule*: its antecedent is *patternOf(rule)*; its
    consequent is what it contains through "consequent" relations:
  :rtype: RuleSpec

    - A relation concludes a relation, between its (local) ends, for each of
      its types -- which may be variables.
    - A variable's constraints (see *GraphObject.constraints()*) are
      conclusions if it's the consequent's own variable (not one of the
      antecedent's nodes, whose constraints are tests).
    - An isa link concludes an isa link.
    - A consequent variable the antecedent doesn't bind (by name) stands for a
      new object, one per match: it's concluded to exist, isa its types (as
      drawn), and have its constraints. (Relation types can't be new.)
    - Value variables ("?a") must be bound by the antecedent.
    - "distinct", and relations or isa links with a missing end, aren't
      supported: they're reported as problems, and the rule isn't used.
  '''
  return _spec(rule, None, rule.model.CONSEQUENT)

def definitionSpecs(definition:GraphObject) -> list[RuleSpec]:
  '''
  :param definition:
  :type definition: GraphObject
  :returns: The two rules a definition amounts to: its definiens (the meaning)
    implies its definiendum (the term defined), and its definiendum implies its
    definiens -- each part of it. Eg: defining ?X -brother-> ?Y as ?X
    -full-sibling-> ?Y, ?Y {gender: male} concludes brothers from full siblings
    who are male, and from a brother both that they're full siblings and that
    he's male. See *ruleOf()*; in the second direction (the definiens as
    conclusions):
  :rtype: list[RuleSpec]

    - its variables' types (as drawn) are concluded, as well as their
      constraints -- they're part of the meaning;
    - its "distinct"s are left out: they're tests, not something that can be
      concluded;
    - its variables the definiendum doesn't bind are new objects (eg:
      grandparent defined through an intermediate parent).
  '''
  m = definition.model
  return [_spec(definition, (m.DEFINIENS,), m.DEFINIENDUM),
          _spec(definition, (m.DEFINIENDUM,), m.DEFINIENS, meaning=True)]

def _spec(rule:GraphObject, parts:tuple[GraphObject, ...]|None, consequentType:GraphObject, meaning:bool=False) -> RuleSpec:
  '''
  The *RuleSpec* for *rule*, with the pattern from its *parts* (see
  *patternOf()*) as the antecedent and what it contains through
  *consequentType* as the consequent (see *ruleOf()*). With *meaning* (the
  consequent is a definiens: see *definitionSpecs()*), the consequent's
  variables' types are concluded too, and its "distinct"s are left out.

  :param rule:
  :type rule: GraphObject
  :param parts:
  :type parts: tuple[GraphObject, ...] | None
  :param consequentType:
  :type consequentType: GraphObject
  :param meaning:
  :type meaning: bool
  :returns:
  :rtype: RuleSpec
  '''
  m = rule.model
  spec = RuleSpec(rule, patternOf(rule, parts))
  anteObjs = {id(v) for v in spec.pattern.variables}
  bound = {v.name for v in spec.pattern.variables}
  bound |= {v for _, _, v in spec.pattern.constraints if isinstance(v, ValueVar)}
  spec.problems += [("bad_constraints", (x, err)) for x, err in spec.pattern.errors]
  consequent = [r.localDst for r, _ in rule._getOutgoing(lambda r: r.isIndividual() and r.isa(consequentType))
                if r.localDst is not None]
  own:dict[int, GraphObject] = {} # the consequent's own variables
  new:dict[str, GraphObject] = {}  # the new ones, by name
  def use(x:GraphObject|None, relType:bool=False) -> None:
    if x is not None and x.isVariable():
      if x.name not in bound:
        if relType:
          spec.problems.append(("rule_unbound", (x,)))
        else:
          new.setdefault(x.name, x)
          own[id(x)] = x
      elif id(x) not in anteObjs:
        own[id(x)] = x
  for e in consequent:
    if isinstance(e, Relation) and e.isa(m.DISTINCT):
      if not meaning: # (in a definiens, a test: nothing to conclude)
        spec.problems.append(("rule_unsupported", (e,)))
    elif isinstance(e, IsaIndividual) or (isinstance(e, Relation) and e.isIndividual() and m.ISA in e.getParents()):
      if e.localSrc is None or e.localDst is None:
        spec.problems.append(("rule_open_end", (e, Sym("src" if e.localSrc is None else "dst"))))
      else:
        spec.isas.append((e.localSrc, e.localDst))
        use(e.localSrc); use(e.localDst)
    elif isinstance(e, Relation) and e.isIndividual():
      for end, x in (("src", e.localSrc), ("dst", e.localDst)):
        if x is None:
          spec.problems.append(("rule_open_end", (e, Sym(end))))
      for t in e.getParents():
        spec.heads.append((t, e.localSrc, e.localDst))
        use(t, relType=True)
      use(e.localSrc); use(e.localDst)
    else:
      use(e)
  spec.new = list(new.values())
  typed = own.values() if meaning else new.values() # (a new object isa its types, as drawn; so is a definiens' variable)
  for x in {id(x): x for x in typed}.values():
    for p in x.getParents():
      if p not in (m.NODE, m.RELATION, m.TOP) and not isinstance(x, IsaIndividual):
        spec.isas.append((x, p))
  for x in own.values():
    if (err := x.constraintsError()) is not None:
      spec.problems.append(("bad_constraints", (x, err)))
    for k, v in x.constraints().items():
      if isinstance(v, ValueVar) and v not in bound:
        spec.problems.append(("rule_unbound", (v,)))
      spec.assertions.append((x, k, v))
  return spec

def rules(objects:list[GraphObject], kind:str="RULE") -> list[GraphObject]:
  '''
  :returns: The rules (or with *kind* "DEFINITION" or "CONSTRAINT", definitions or constraints) among *objects*: individuals that isa "rule" ("definition", "constraint").

  :param objects:
  :type objects: list[GraphObject]
  :param kind:
  :type kind: str
  :rtype: list[GraphObject]
  '''
  return _contexts(objects).get(kind, [])

def _contexts(objects:list[GraphObject]) -> dict[str, list[GraphObject]]:
  '''
  :returns: The rules, definitions and constraints among *objects*, in one
    pass: "RULE" -> the rules, ... (see *rules()*).
  :param objects:
  :type objects: list[GraphObject]
  :rtype: dict[str, list[GraphObject]]
  '''
  ret:dict[str, list[GraphObject]] = {}
  for o in objects:
    try:
      if o.isIndividual() and isinstance(o, Node) and o.isa(o.model.CONTEXT) and not o.isPatternElement():
        for kind in ("RULE", "DEFINITION", "CONSTRAINT"):
          if o.isa(getattr(o.model, kind)):
            ret.setdefault(kind, []).append(o)
    except Exception: # (eg: a half-built object)
      pass
  return ret

@dataclass
class ConstraintSpec:
  '''
  A constraint (a context that isa "constraint"), in an engine-neutral form:
  its *pattern* must not match -- each match is a *Violation*, of *code* and
  *severity*, reported against the first of *report* (the subject) with the
  rest as its args. Read from the constraint's attributes (see *constraintOf()*).
  '''
  constraint:GraphObject
  pattern:Pattern
  "What it contains (see *patternOf()*)."
  code:str
  severity:str
  "error or warning"
  report:list[Any] = field(default_factory=list)
  "The subject, then the args: the pattern's variables, or constants (*Sym*)."
  template:str|None = None
  "The message template ({0}: the subject; {1}...: the args), or None for the code's (see *_MESSAGES*)."
  problems:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): why the constraint can't be used (it's skipped)."

CONSTRAINT_ATTRIBUTES:dict[str, str] = {
  "code":     "The code of the violations it reports (default: the constraint's name).",
  "severity": "error (the default) or warning.",
  "report":   "What a violation is about, as a comma-separated list: its subject, then its arguments -- each one "
              "of the constraint's variables (eg: ?r), or a word taken as is (eg: reflexive). By default, all "
              "its variables, in name order (or the constraint itself if it has none).",
  "message":  "The message, with {0} for the subject and {1}, {2}, ... for the arguments. By default, the "
              "code's built-in message, if it has one.",
  }
"The attributes a constraint is read from: key -> note (see *constraintOf()*)."

def constraintOf(constraint:GraphObject) -> ConstraintSpec:
  '''
  :param constraint:
  :type constraint: GraphObject
  :returns: The *ConstraintSpec* of *constraint*: its pattern is what it
    contains (see *patternOf()*), and the rest is from its attributes (see
    *CONSTRAINT_ATTRIBUTES*). Eg: a constraint named "irreflexive" containing
    !a -?r-> !a, with ?r {irreflexive} and report "?r, !a", reports each
    irreflexive relation type relating something to itself.
  :rtype: ConstraintSpec
  '''
  pat = patternOf(constraint)
  def attr(key:str) -> str|None:
    try:
      v = constraint.get(key, None)
    except Exception:
      return None
    return None if v is None or str(v).strip() == "" else str(v).strip()
  spec = ConstraintSpec(constraint, pat, attr("code") or constraint.name, (attr("severity") or "error").lower(),
                        template=attr("message"))
  spec.problems += [("bad_constraints", (x, err)) for x, err in pat.errors]
  if spec.severity not in ("error", "warning"):
    spec.problems.append(("constraint_severity", (spec.severity,)))
  byName = {v.name: v for v in pat.variables}
  text = attr("report")
  if text is None:
    spec.report = list(byName.values()) or [constraint]
  else:
    for tok in (t.strip() for t in text.split(",")):
      if not tok:
        continue
      if tok.startswith(("?", "!")):
        if tok in byName:
          spec.report.append(byName[tok])
        else:
          spec.problems.append(("constraint_report", (tok,)))
      else:
        spec.report.append(Sym(tok))
    if not spec.report or not isinstance(spec.report[0], GraphObject): # (the subject must be an object)
      spec.report.insert(0, constraint)
  return spec

def constraintSpecs(objects:list[GraphObject]) -> list[ConstraintSpec]:
  '''
  :returns: The constraints among *objects*, as *ConstraintSpec* objects.

  :param objects:
  :type objects: list[GraphObject]
  :rtype: list[ConstraintSpec]
  '''
  return [constraintOf(c) for c in rules(objects, "CONSTRAINT")]

def ruleSpecs(objects:list[GraphObject]) -> list[RuleSpec]:
  '''
  :returns: Everything the rules and definitions among *objects* amount to, as *RuleSpec* objects.

  :param objects:
  :type objects: list[GraphObject]
  :rtype: list[RuleSpec]
  '''
  return [ruleOf(r) for r in rules(objects)] + [s for d in rules(objects, "DEFINITION") for s in definitionSpecs(d)]

# ── Base rules ────────────────────────────────────────────────────────────

BASE_RULES_PLACEHOLDER = "file:///SEMANTIC_NETS_BASE_RULES"
"The folder the base rules that come with the program are stored as being in (see *baseRuleModels()*)."

BASE_RULES:list[str|Traversable] = [importlib.resources.files("sn.model").joinpath("baseRules.snm")]
'''
The models of base rules every model builds on: like the system model (sn),
they're super-models of every model (see *Model.implicitSuperDBs()*), but
not saved with it, and read-only. By default, the meaning of the relational
properties (symmetric, transitive, reflexive, irreflexive, asymmetric) --
package data, made by *tools/makeBaseRules.py*. An application can change
the list (eg: to its own base rules) -- before it makes or reads any model:
a file or URL (str), or package data (Traversable). A reasoner applies their
rules, definitions and constraints (see *Reasoner.ruleObjects()*), but
doesn't take their objects as data (see *Reasoner.objects()*).
'''

_baseFiles:dict[str, str] = {}
"Package data in *BASE_RULES* -> the path of the copy it's read from (see *baseRuleModels()*)."
_baseFolder:list[str] = []
_baseSpecs:dict[int, tuple[Model, list, list]] = {}
"id(base rules model) -> (it, its RuleSpecs, its ConstraintSpecs): see *Reasoner.specs()*."
_readingBase:list[bool] = []
"Non-empty while *baseRuleModels()* is reading them: the base rules don't build on themselves."

def baseRuleModels() -> list[Model]:
  '''
  :returns: The models of *BASE_RULES*, read (and write-locked) if need be.
    Package data -- which may be in a zip, and is stored as being in
    *BASE_RULES_PLACEHOLDER* -- is read from a copy in a temporary folder,
    made to refer to where it then is. (None while they're being read: see
    *Model.implicitSuperDBs()*.)
  :rtype: list[Model]
  '''
  if _readingBase:
    return []
  ret:list[Model] = []
  for src in BASE_RULES:
    if isinstance(src, str):
      url = src
    else:
      path = _baseFiles.get(str(src), "")
      if not path or not os.path.exists(path): # (eg: the first time)
        if not _baseFolder:
          _baseFolder.append(os.path.realpath(tempfile.mkdtemp(prefix="snBaseRules-")))
          atexit.register(shutil.rmtree, _baseFolder[0], True)
        folder = os.path.join(_baseFolder[0], str(len(_baseFiles))) # (a folder each: they may have the same name)
        os.makedirs(folder, exist_ok=True)
        path = _baseFiles[str(src)] = os.path.join(folder, src.name)
        with open(path, "w", encoding="utf-8") as fd:
          fd.write(src.read_text(encoding="utf-8").replace(BASE_RULES_PLACEHOLDER, Path(folder).as_uri()))
      url = Path(path).as_uri()
    _readingBase.append(True)
    try:
      m = Model.getDB(url, mode="")
    except Exception:
      logger.error(f'Couldn\'t read the base rules "{src}".', exc_info=True)
      continue
    finally:
      _readingBase.pop()
    m._writeLocked = True
    ret.append(m)
  return ret

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
    '''
    :param engine:
    :type engine: str | None
    :param kwargs:
    :type kwargs:
    '''
    super().__init_subclass__(**kwargs)
    if engine is not None:
      Reasoner.engines[engine] = cls

  @classmethod
  def create(cls, model:Model, engine:str="clingo", **kwargs) -> Reasoner:
    '''
    :param model:
    :type model: Model
    :param engine:
    :type engine: str
    :param kwargs:
    :type kwargs:
    :returns:
    :rtype: Reasoner
    '''
    if engine not in cls.engines:
      import_module(f'sn.model.{engine}Reasoner')
    return cls.engines[engine](model, **kwargs)

  def __init__(self, model:Model, showSysRules:bool|None=None):
    '''
    :param model:
    :type model: Model
    :param showSysRules: Whether the base rules (see *BASE_RULES*) show in
      the results: their objects as data, and their conclusions as rule
      conclusions (rather than plain inferences). By default, as the
      "reasoner/showSysRules" preference says.
    :type showSysRules: bool | None
    '''
    self.model = model
    if showSysRules is None:
      showSysRules = bool(sn.snPrefs.get("reasoner/showSysRules", False))
    self.showSysRules:bool = showSysRules

  # ── Engine interface ─────────────────────────────────────────────────────

  @abstractmethod
  def run(self) -> Inferences:
    '''
    Reason over the current state of the model. An engine reasons with the
    rules, definitions and constraints of *ruleObjects()* (so including the
    base rules), and passes what it finds through *_finish()*.

    :returns:
    :rtype: Inferences
    '''

  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Answer the query a context describes (see *patternOf()*) against the
    model, including what the reasoner infers.

    :param context:
    :type context: GraphObject
    :returns: One dict per match, mapping each of the pattern's variables to
      the object it matched. A pattern without variables gives [{}] if it
      holds, [] if not. An individual variable matches individuals, a type
      variable types, and a variable used as a relation's type relation types.
    :rtype: list[dict[GraphObject, GraphObject]]
    '''
    raise NotImplementedError(f'{type(self).__name__} can\'t answer queries.')

  def query(self, query:str) -> list[tuple[Any, ...]]:
    '''
    Run a query in the engine's native language (see :py:attr:`language`).

    :param query:
    :type query: str
    :returns: Answer tuples, with the engine's object references mapped back
      to *GraphObjects*.
    :rtype: list[tuple[Any, ...]]
    '''
    raise NotImplementedError(f'{type(self).__name__} has no native query language.')

  # ── Portable queries ─────────────────────────────────────────────────────
  # These default to filtering a full run(); engines may override them with
  # something cheaper.

  def related(self, src:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    :returns: Everything *src* is related to under *relType*, asserted or inferred.

    :param src:
    :type src: GraphObject
    :param relType:
    :type relType: Relation
    :rtype: list[GraphObject]
    '''
    return self.run().related(src, relType)

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    :returns: Everything related to *dst* under *relType*, asserted or inferred.

    :param dst:
    :type dst: GraphObject
    :param relType:
    :type relType: Relation
    :rtype: list[GraphObject]
    '''
    return [s for t,s,d in self.run().holds if d is dst and t is relType]

  def isa(self, obj:GraphObject, typ:GraphObject) -> bool:
    '''
    :param obj:
    :type obj: GraphObject
    :param typ:
    :type typ: GraphObject
    :returns:
    :rtype: bool
    '''
    return any(x is obj and t is typ for x,t in self.run().isa)

  def instances(self, typ:GraphObject, individualsOnly:bool=True) -> list[GraphObject]:
    '''
    :returns: Every (individual) object that isa *typ*, other than *typ* itself.

    :param typ:
    :type typ: GraphObject
    :param individualsOnly:
    :type individualsOnly: bool
    :rtype: list[GraphObject]
    '''
    return [x for x,t in self.run().isa if t is typ and x is not typ
            and (x.isIndividual() or not individualsOnly)]

  def violations(self, subject:GraphObject|None=None) -> list[Violation]:
    '''
    :param subject:
    :type subject: GraphObject | None
    :returns:
    :rtype: list[Violation]
    '''
    return [v for v in self.run().violations if subject is None or v.subject is subject]

  # ── Model export ─────────────────────────────────────────────────────────

  def objects(self) -> list[GraphObject]:
    '''
    :returns: The objects of the model and (transitively) its super-models --
      but not the base rules' (see *BASE_RULES*), unless it's one of them:
      they're rules, not data (see *ruleObjects()*).
    :rtype: list[GraphObject]
    '''
    return [obj for m in self.dataModels() for obj in list(m.values()) if not getattr(obj, "inferred", False)]

  def dataModels(self) -> list[Model]:
    '''
    :returns: The model and (transitively) its super-models -- but not the base
      rules (see *BASE_RULES*), unless it's one of them (see *objects()*).
    :rtype: list[Model]
    '''
    base = [m for m in baseRuleModels() if m is not self.model]
    models:list[Model] = []
    pending = [self.model]
    while pending:
      m = pending.pop()
      if m not in models and not any(m is b for b in base):
        models.append(m)
        pending.extend(m.superDBs) #type: ignore[arg-type]
    return models

  def ruleObjects(self) -> list[GraphObject]:
    '''
    :returns: What the rules, definitions and constraints are read from:
      *objects()*, and the base rules' (see *BASE_RULES*).
    :rtype: list[GraphObject]
    '''
    ret = self.objects()
    have = {id(o.model) for o in ret}
    return ret + [o for m in baseRuleModels() if id(m) not in have for o in list(m.values())]

  def specs(self) -> tuple[list[RuleSpec], list[ConstraintSpec]]:
    '''
    :returns: The rules and definitions (see *ruleSpecs()*), and the
      constraints (see *constraintSpecs()*), of *ruleObjects()*. (The base
      rules' are read once: they're read-only.)
    :rtype: tuple[list[RuleSpec], list[ConstraintSpec]]
    '''
    objs = self.objects()
    have = {id(o.model) for o in objs}
    found = _contexts(objs)
    rs = [ruleOf(r) for r in found.get("RULE", [])] + [s for d in found.get("DEFINITION", []) for s in definitionSpecs(d)]
    cs = [constraintOf(c) for c in found.get("CONSTRAINT", [])]
    for m in baseRuleModels():
      if id(m) not in have:
        cached = _baseSpecs.get(id(m))
        if cached is None or cached[0] is not m:
          objs = list(m.values())
          cached = _baseSpecs[id(m)] = (m, ruleSpecs(objs), constraintSpecs(objs))
        rs += cached[1]
        cs += cached[2]
    self._constraintSpecs = cs
    return rs, cs

  def isSystem(self, obj:Any) -> bool:
    '''
    :param obj:
    :type obj: Any
    :returns: True iff *obj* is (or is made by) one of the base rules (see *BASE_RULES*).
    :rtype: bool
    '''
    if isinstance(obj, NewObject):
      obj = obj.rule
    return isinstance(obj, GraphObject) and any(obj.model is m for m in baseRuleModels())

  def _finish(self, ret:Inferences) -> Inferences:
    '''
    What every engine does with its results, before returning them from *run()*:

      - A violation is reported once per set of objects it's about: eg: an
        asymmetric relation between a and b once, not again for b and a. (Of
        such, the one whose args come first in the models' order is kept.)
      - A constraint's violations get its message (see *ConstraintSpec*).
      - Unless *showSysRules*, the base rules' conclusions aren't reported as
        rule conclusions (*fired*, ...): what they conclude is in *holds*,
        *inferred*, ... as any inference is.

    :param ret:
    :type ret: Inferences
    :returns: *ret*, changed.
    :rtype: Inferences
    '''
    def order(x:Any) -> tuple:
      return (str(x.model.url), x._id) if isinstance(x, GraphObject) else ("", str(x))
    def key(v:Violation) -> tuple:
      return (v.code, v.severity, id(v.subject), tuple(sorted((order(a) for a in v.args))))
    best:dict[tuple, Violation] = {}
    for v in ret.violations:
      k = key(v)
      if k not in best or [order(a) for a in v.args] < [order(a) for a in best[k].args]:
        best[k] = v
    specs = getattr(self, "_constraintSpecs", None) # (as the engine used them: see specs())
    templates = {s.code: s.template for s in (specs if specs is not None else self.specs()[1]) if s.template}
    ret.violations = [v for v in ret.violations if best[key(v)] is v]
    for v in ret.violations:
      if v.template is None and v.code in templates:
        v.template = templates[v.code]
    if not self.showSysRules:
      ret.fired = [x for x in ret.fired if not self.isSystem(x[0])]
      ret.ruleAttrs = [x for x in ret.ruleAttrs if not self.isSystem(x[0])]
      ret.ruleIsa = [x for x in ret.ruleIsa if not self.isSystem(x[0])]
      ret.newObjects = [x for x in ret.newObjects if not self.isSystem(x)]
    return ret

  def facts(self) -> list[Fact]:
    '''
    :returns: The model (and its super-models) as engine-neutral facts; see
      the module documentation for the vocabulary. With *showSysRules*, the
      base rules too (see *BASE_RULES*). What a previous "reason" inferred
      isn't among them (see *withoutInferences()*).
    :rtype: list[Fact]
    '''
    with withoutInferences([*self.dataModels(), *baseRuleModels()]):
      return self._facts()

  def _facts(self) -> list[Fact]:
    '''
    :returns: *facts()*, with the inferred objects out of the way.
    :rtype: list[Fact]
    '''
    out:list[Fact] = []
    for key in ("top", "relation", "isa", "node", "collection"):
      out.append(("const", (Sym(key), getattr(self.model, key.upper()))))

    # Work through a queue that grows if an object refers to one we haven't seen.
    queue = self.ruleObjects() if self.showSysRules else self.objects()
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
      if obj.isPatternElement():
        out.append(("pattern", (obj,)))
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
        if key in ("name", CONSTRAINTS) or key.startswith("vis/"): # (a variable's constraints aren't facts about it)
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
    '''
    :param rel:
    :type rel: Relation
    :param ref:
    :type ref:
    :returns:
    :rtype: list[Fact]
    '''
    out:list[Fact] = []
    if rel.localSrc is not None:
      out.append(("lsrc", (rel, ref(rel.localSrc))))
    if rel.localDst is not None:
      out.append(("ldst", (rel, ref(rel.localDst))))
    src, dst = rel.src, rel.dst
    if src is not None:
      out.append(("src", (rel, ref(src))))
    if dst is not None:
      out.append(("dst", (rel, ref(dst))))
    if rel.isIndividual() and not isinstance(rel, IsaIndividual) \
        and src is not None and dst is not None and not rel.isPatternElement(): # a pattern relation isn't a fact
      out.append(("link", (rel, src, dst)))
    if rel.isType(): # its signature
      if rel.domain is not None:
        out.append(("domain", (rel, ref(rel.domain))))
      if rel.range is not None:
        out.append(("range", (rel, ref(rel.range))))
    # Relational properties are LOCAL tags on relation types -- the key's
    # presence is the tag -- and are never inherited (brother isa sibling, but
    # brother isn't symmetric). See Relation._hasRelationalProperty().
    if rel.isType():
      for prop in PROPERTIES:
        if dict.__contains__(rel, prop):
          out.append(("prop", (rel, Sym(prop))))
    return out

# ── Shared results ────────────────────────────────────────────────────────

def reason(model:Model, engine:str="clingo") -> Inferences:
  '''
  Run the reasoner over *model* and keep the results on the model (see
  *reasoningFor()*), where everything using the model -- the command line,
  every view -- finds the same ones. Observers of the model are told with a
  ("reasoned", (inferences,)) topic. The results aren't saved with the model,
  and aren't updated as it's edited: they're a snapshot until the next
  *reason()* or *clearReasoning()*.

  :param model:
  :type model: Model
  :param engine:
  :type engine: str
  :returns:
  :rtype: Inferences
  '''
  reasoner = Reasoner.create(model, engine)
  ret = reasoner.run()
  materialize(model, ret, reasoner.dataModels())
  model.reasoning = ret #type: ignore[attr-defined]
  model.notify(("reasoned", (ret,)))
  return ret

def clearReasoning(model:Model) -> None:
  '''
  Forget *model*\'s reasoning results; observers are told with a ("reasoning cleared", ()) topic.

  :param model:
  :type model: Model
  '''
  with model.inferring(*model.allSuperDBs()): #type: ignore[arg-type]
    for obj in [*_inferredRelations(model).values(), *model.inferredObjects()]: # (relations first: then the new objects)
      if obj._isConnected():
        obj._disconnect()
    for o, k, _ in _inferredAttributes([model, *model.allSuperDBs()]): #type: ignore[list-item]
      del o[k]
  model.reasoning = None #type: ignore[attr-defined]
  model.notify(("reasoning cleared", ()))

@contextmanager
def withoutInferences(models:list[Model]) -> Iterator[None]:
  '''
  A context in which the inferred objects of *models* (see
  *GraphObject.inferred*) are out of them -- so what the reasoner reads is
  what's asserted: an inferred isa link, eg, would otherwise give its object
  the type's attributes, and justify itself. They're put back (the same
  objects) afterwards. Nobody's told: as far as the models' observers are
  concerned, nothing happened.

  :param models: The models.
  :type models: list[Model]
  '''
  models = [m for i, m in enumerate(models) if not any(m is n for n in models[:i])]
  objs = [o for m in models for o in m.inferredObjects()]
  attrs = _inferredAttributes(models)
  for o, k, _ in attrs: # (taken out quietly: straight from the object's dict -- see Attribute.inferred)
    dict.__delitem__(o, k)
  if not objs:
    try:
      yield
    finally:
      for o, k, a in attrs:
        dict.__setitem__(o, k, a)
    return
  with ExitStack() as stack:
    for m in models: # (hold the models' notifications, to drop those about this)
      stack.enter_context(Subject.ChangeMgr(m))
    out:list[GraphObject] = []
    with models[0].inferring(*models[1:]):
      for o in objs:
        if o._isConnected(): # (not one taken out with another: eg: a relation's isa link)
          o._disconnect()
          out.append(o)
    try:
      yield
    finally:
      with models[0].inferring(*models[1:]):
        for o in reversed(out):
          if not o._isConnected():
            o._reconnect()
      ids = {(id(o.model), o.id) for o in objs}
      for m in models:
        m._topics = [t for t in m._topics if not (t[0] in ("new", "del") and (id(m), t[1][0]) in ids)]
      for o, k, a in attrs:
        dict.__setitem__(o, k, a)

def _inferredAttributes(models:list[Model]) -> list[tuple[GraphObject, str, Attribute]]:
  '''
  :param models: Some models.
  :type models: list[Model]
  :returns: The inferred attributes (see *Attribute.inferred*) of their
    objects: (object, key, attribute).
  :rtype: list[tuple[GraphObject, str, Attribute]]
  '''
  return [(o, k, a) for m in models for o in list(m.values()) if o is not None
          for k, a in list(dict.items(o)) if isinstance(a, Attribute) and a.inferred]

def _inferredRelations(model:Model) -> dict[tuple[int, int, int], Relation]:
  '''
  :param model: A model.
  :type model: Model
  :returns: *model*'s inferred relations -- not the isa links of inferred
    relations, which go with them -- by (id(type), id(src), id(dst)); an isa
    link's type is the model's ISA.
  :rtype: dict[tuple[int, int, int], Relation]
  '''
  ret:dict[tuple[int, int, int], Relation] = {}
  for o in model.inferredObjects():
    if not isinstance(o, Relation) or not o.isIndividual():
      continue
    src, dst = o.localSrc, o.localDst
    if isinstance(o, IsaIndividual):
      if src is not None and getattr(src, "inferred", False):
        continue # (an inferred relation's own isa link)
      t:GraphObject = model.ISA
    else:
      parents = [p for _, p in o._getOutgoing(lambda r: isinstance(r, IsaIndividual)) if p is not None]
      if not parents:
        continue
      t = parents[0]
    ret[(id(t), id(src), id(dst))] = o
  return ret

def _newObjectKey(n:NewObject) -> tuple:
  '''
  :param n: An object a rule concluded exists.
  :type n: NewObject
  :returns: What identifies it from one "reason" to the next: the rule, the
    variable, and the match (by identity, for the model's objects).
  :rtype: tuple
  '''
  return (id(n.rule), n.variable, tuple((name, id(v) if isinstance(v, GraphObject) else repr(v)) for name, v in n.bindings))

def _newObjectName(n:NewObject, model:Model) -> str:
  '''
  :param n: An object a rule concluded exists.
  :type n: NewObject
  :param model: The model it's made in (objects are named relative to it).
  :type model: Model
  :returns: The name of the inferred node made for it, eg: "(m for alice)" --
    not a variable's name (no leading "?" or "!": it isn't a pattern).
  :rtype: str
  '''
  what = n.variable.lstrip("?!") or "new"
  match = ", ".join(v.name if isinstance(v, GraphObject) else str(v) for _, v in n.bindings)
  return f"({what} for {match})" if match else f"(new {what})"

def materialize(model:Model, inferences:Inferences, models:list[Model]) -> None:
  '''
  Bring *model*'s inferred objects (see *GraphObject.inferred*) into line with
  *inferences*:

  - a relation for each relation it inferred or found inherited, and an isa
    link for each one the rules concluded, between objects of the model or
    its super-models (*models*);
  - a node for each object the rules concluded exists (*NewObject*), of the
    types they said (or just a node), with the attributes they gave it, and
    the relations they gave it.

  Those already there are kept (the same objects, so the views keep them where
  they are); those no longer inferred are removed. None of this is saved,
  dirties the model, or is undone (see *Model.inferring()*). Each object's
  *inferredKind* says what it is: "inferred" or "inherited" (a relation),
  "rule" (a relation the rules gave a new object), or "new" (a new object).

  :param model: The model reasoned over.
  :type model: Model
  :param inferences: What the reasoner concluded.
  :type inferences: Inferences
  :param models: *model* and its super-models.
  :type models: list[Model]
  '''
  want:dict[tuple[int, int, int], tuple[GraphObject, Any, Any]] = {}
  kinds:dict[tuple[int, int, int], str] = {}
  inherited = {(id(t), id(s), id(d)) for t, s, d in inferences.inherited}
  for t, s, d in inferences.newFacts():
    if isinstance(s, GraphObject) and isinstance(d, GraphObject) and isinstance(t, Relation):
      key = (id(t), id(s), id(d))
      want[key], kinds[key] = (t, s, d), "inherited" if key in inherited else "inferred"
  for _, x, t in inferences.ruleIsa:
    if isinstance(x, GraphObject) and isinstance(t, GraphObject) and \
       not any(p is t for _, p in x._getOutgoing(lambda r: isinstance(r, IsaIndividual) and not r.inferred)): # (not asserted already)
      key = (id(model.ISA), id(x), id(t))
      want[key], kinds[key] = (model.ISA, x, t), "inferred"
  # the new objects: kept by what identifies them (see _newObjectKey())
  newOnes = {_newObjectKey(n): n for n in inferences.newObjects}
  haveNodes = {o.inferredKey: o for o in model.inferredObjects()
               if not isinstance(o, Relation) and getattr(o, "inferredKey", None) is not None}
  have = _inferredRelations(model)
  with model.inferring(*models):
    nodes:dict[tuple, GraphObject] = {}
    for key, n in newOnes.items():
      node = haveNodes.get(key)
      if node is None or not node._isConnected():
        types = [t for _, x, t in inferences.ruleIsa if isinstance(x, NewObject) and _newObjectKey(x) == key and isinstance(t, GraphObject)]
        try:
          node = Node(model, types or [model.NODE], individual=True, name=_newObjectName(n, model), inferred=True)
        except Exception as ex:
          logger.warning(f"Couldn't add the new object {n}: {type(ex).__name__}: {ex}")
          continue
        node.inferredKey, node.inferredKind = key, "new"
      nodes[key] = node
    for _, x, k, v in inferences.ruleAttrs: # (their attributes -- the model's own objects' are just reported)
      node = nodes.get(_newObjectKey(x)) if isinstance(x, NewObject) else None
      if node is not None and node.get(k, None) != v:
        try:
          node[k] = v
        except Exception as ex:
          logger.warning(f"Couldn't give {node.name} {k}={v}: {type(ex).__name__}: {ex}")
    # the attribute values the rules concluded for the model's own objects: inferred attributes
    # (not where the object has a value of its own -- given beats inferred)
    wantAttrs:dict[tuple[int, str], tuple[GraphObject, str, Any]] = {}
    for _, x, k, v in inferences.ruleAttrs:
      if isinstance(x, GraphObject) and not getattr(x, "inferred", False):
        wantAttrs[(id(x), k)] = (x, k, v)
    for o, k, a in _inferredAttributes(models):
      if (id(o), k) not in wantAttrs:
        del o[k]
    for x, k, v in wantAttrs.values():
      local = x.getLocalAttr(k)
      try:
        if local is None:
          if x.get(k, None) == v: # (it has that value already: inherited)
            continue
          inh = x._getSuperAttr(k)
          x.setAttr(k, Attribute(v, inh.type if inh is not None else type(v),
                                 inh.restriction if inh is not None and inh.restriction is not None else Restriction.fromstring("VAR"),
                                 inferred=True))
        elif local.inferred and local.value != v:
          local.value = v
          x.notify(("mod attribute", (k, v)))
      except Exception as ex:
        logger.warning(f"Couldn't give {x.name} the inferred {k}={v}: {type(ex).__name__}: {ex}")
    real = lambda o: nodes.get(_newObjectKey(o)) if isinstance(o, NewObject) else o
    for _, t, s, d in inferences.fired: # (the relations the rules gave the new objects)
      if isinstance(s, NewObject) or isinstance(d, NewObject):
        rs, rd = real(s), real(d)
        if isinstance(t, Relation) and isinstance(rs, GraphObject) and isinstance(rd, GraphObject):
          key = (id(t), id(rs), id(rd))
          want[key], kinds[key] = (t, rs, rd), "rule"
    for key, obj in have.items():
      if key not in want and obj._isConnected():
        obj._disconnect()
    for key, node in haveNodes.items():
      if key not in nodes and node._isConnected():
        node._disconnect()
    for key, (t, s, d) in want.items():
      try:
        obj = have.get(key)
        if obj is None or not obj._isConnected():
          obj = IsaIndividual(model, s, d, inferred=True) if t is model.ISA else Relation(model, [t], s, d, individual=True, inferred=True)
        obj.inferredKind = kinds[key] # (for how it's drawn)
      except Exception as ex:
        logger.warning(f"Couldn't add the inferred {t.name} from {s.name} to {d.name}: {type(ex).__name__}: {ex}")

def reasoningFor(model:Model|None) -> Inferences|None:
  '''
  The results of the last *reason()* over *model*, or None.

  :param model:
  :type model: Model | None
  :returns:
  :rtype: Inferences | None
  '''
  return getattr(model, "reasoning", None)

def _kind(obj:GraphObject) -> str:
  '''
  :param obj:
  :type obj: GraphObject
  :returns:
  :rtype: str
  '''
  if isinstance(obj, IsaIndividual):
    return "isa"
  if isinstance(obj, Relation):
    return "relation"
  if isinstance(obj, Node):
    return "node"
  return "top"

def _label(x:Any, relativeTo:Model|None=None) -> str:
  '''
  How an object is named in messages: see *GraphObject.tostring()*\'s "friendly" format.

  :param x:
  :type x: Any
  :param relativeTo:
  :type relativeTo: Model | None
  :returns:
  :rtype: str
  '''
  if isinstance(x, GraphObject):
    return x.tostring(relativeTo=relativeTo, format="friendly")
  if isinstance(x, NewObject):
    return x.label(relativeTo)
  return str(x)

def relationArrow(relType:Relation) -> str:
  '''
  A relation type as an arrow, as in the conceptual graphs literature: -name->

  :param relType:
  :type relType: Relation
  :returns:
  :rtype: str
  '''
  return f'-{relType.name}->'
