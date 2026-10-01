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
from typing import Any, ClassVar
import sn
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual
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
    'How it\'s named in messages, eg: "(new ?m for ?p=alice)", with objects named relative to *relativeTo*.'
    match = ", ".join(f"{n}={_label(v, relativeTo)}" for n, v in self.bindings)
    return f"(new {self.variable}{' for ' + match if match else ''})"

  def __str__(self) -> str:
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

  @property
  def message(self) -> str:
    'The message, with objects named relative to the subject\'s model.'
    return self.messageIn(self.subject.model)

  def messageIn(self, relativeTo:Model|None) -> str:
    'The message, with objects named relative to *relativeTo* (see *GraphObject.tostring()*).'
    template = _MESSAGES.get(self.code, "{0}: " + self.code + " {1}")
    return template.format(*(_label(x, relativeTo) for x in (self.subject,) + self.args))

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
    'Everything *src* is related to under *relType* (asserted or inferred).'
    return list(self._index()[0].get((id(src), id(relType)), []))

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    'Everything related to *dst* under *relType* (asserted or inferred).'
    return list(self._index()[1].get((id(dst), id(relType)), []))

  def newFacts(self) -> list[tuple[Relation, GraphObject, GraphObject]]:
    'The inferred and inherited relation triples (each once) -- ie: not asserted.'
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
    'The model objects *rule* concluded something about (not new objects).'
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
    return [v for v in self.violations if v.subject is subject]

  def report(self, model:Model|None=None) -> str:
    '''
    :param model: If given, leave out findings that only involve system
      objects (those of the always-in-memory "sn" model) -- noise to a user.
    :returns: A readable summary: violations, new relations (inferred and
      inherited) and suggested classifications.
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
  :param parts: The "contains"-family relation types to read the pattern from.
    By default, all of them other than "consequent" and "definiendum": so for a
    rule, its antecedent, and for a definition, its definiens.
  :returns: The *Pattern* of *context*: everything it contains (through
    *parts*).

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
  :returns: The *RuleSpec* of *rule*: its antecedent is *patternOf(rule)*; its
    consequent is what it contains through "consequent" relations:

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
  :returns: The two rules a definition amounts to: its definiens (the meaning)
    implies its definiendum (the term defined), and its definiendum implies its
    definiens -- each part of it. Eg: defining ?X -brother-> ?Y as ?X
    -full-sibling-> ?Y, ?Y {gender: male} concludes brothers from full siblings
    who are male, and from a brother both that they're full siblings and that
    he's male. See *ruleOf()*; in the second direction (the definiens as
    conclusions):

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
  ':returns: The rules (or with *kind* "DEFINITION", definitions) among *objects*: individuals that isa "rule" ("definition").'
  ret = []
  for o in objects:
    try:
      if o.isIndividual() and not o.isPatternElement() and o.isa(getattr(o.model, kind)):
        ret.append(o)
    except Exception: # (eg: a half-built object)
      pass
  return ret

def ruleSpecs(objects:list[GraphObject]) -> list[RuleSpec]:
  ':returns: Everything the rules and definitions among *objects* amount to, as *RuleSpec*s.'
  return [ruleOf(r) for r in rules(objects)] + [s for d in rules(objects, "DEFINITION") for s in definitionSpecs(d)]

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

  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Answer the query a context describes (see *patternOf()*) against the
    model, including what the reasoner infers.

    :returns: One dict per match, mapping each of the pattern's variables to
      the object it matched. A pattern without variables gives [{}] if it
      holds, [] if not. An individual variable matches individuals, a type
      variable types, and a variable used as a relation's type relation types.
    '''
    raise NotImplementedError(f'{type(self).__name__} can\'t answer queries.')

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
  '''
  ret = Reasoner.create(model, engine).run()
  model.reasoning = ret #type: ignore[attr-defined]
  model.notify(("reasoned", (ret,)))
  return ret

def clearReasoning(model:Model) -> None:
  'Forget *model*\'s reasoning results; observers are told with a ("reasoning cleared", ()) topic.'
  model.reasoning = None #type: ignore[attr-defined]
  model.notify(("reasoning cleared", ()))

def reasoningFor(model:Model|None) -> Inferences|None:
  'The results of the last *reason()* over *model*, or None.'
  return getattr(model, "reasoning", None)

def _kind(obj:GraphObject) -> str:
  if isinstance(obj, IsaIndividual):
    return "isa"
  if isinstance(obj, Relation):
    return "relation"
  if isinstance(obj, Node):
    return "node"
  return "top"

def _label(x:Any, relativeTo:Model|None=None) -> str:
  'How an object is named in messages: see *GraphObject.tostring()*\'s "friendly" format.'
  if isinstance(x, GraphObject):
    return x.tostring(relativeTo=relativeTo, format="friendly")
  if isinstance(x, NewObject):
    return x.label(relativeTo)
  return str(x)

def relationArrow(relType:Relation) -> str:
  'A relation type as an arrow, as in the conceptual graphs literature: -name->'
  return f'-{relType.name}->'
