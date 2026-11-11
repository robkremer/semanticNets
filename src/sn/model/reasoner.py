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
  ``member(C,M)``             M is a member of box C: a collection (of any Python
                              class) that doesn't quote what it contains (see
                              GraphObject.isCollection(), quotesContents())
  ``attr(O,K,V)``             effective non-"vis/" scalar attributes
  ``lattr(O,K)``              O has attribute K locally
  ``card(T,Dir,Min,Max)``     relation type T's cardinality: each source (Dir
                              *out*) or destination (*in*) has Min..Max others
                              by T (Max -1: any number). See *CARDINALITY*.
  ``card_error(T,K,M)``       T's cardinality attribute K can't be read: message M
  ``pattern(X)``              X describes a pattern (in a rule etc.), not the world
                              (see GraphObject.isPatternElement())
  ``var_kind(X,K)``           X is a variable over K: individual, type or any
                              (see GraphObject.variableKind() and sn.model.names)
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
from dataclasses import dataclass, field, replace
from importlib import import_module
import importlib.resources
import importlib.util
from importlib.resources.abc import Traversable
import atexit
import os
import sys
from pathlib import Path
import shutil
import tempfile
from typing import Any, ClassVar, Iterable, Iterator
from contextlib import contextmanager, ExitStack
from util.observer import Subject
from util.persistence.pRef import PRDb
from util.utils import urlPath
import sn
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual, BASE_RULES_URL
from util.attribute import Attribute, Restriction, coerceValue, VAR_DEFAULTED
from sn.model.constraints import CONSTRAINTS, PRESENT, ValueVar, Not, constraintItems
from sn.model import names

logger:sn.SNLogger = sn.getLogger(__name__)

PROPERTIES = ("reflexive", "irreflexive", "symmetric", "asymmetric", "transitive")
"The relational properties, which are tags on specific relations."

CARDINALITY = {"cardinality": "out", "inverseCardinality": "in"}
'''
The cardinality attributes of a relation type -- like the relational
properties, its own (not inherited by its subtypes): how many objects each
source is related to by it (or by its subtypes: a father is a parent), and how
many each destination is related from. Eg: has-father's "cardinality" "1..1"
(everyone has exactly one father), has-parent's "2..2", has-child's "0..*", a
desk's has-desk "inverseCardinality" "0..1" (no desk is two people's). See
*parseCardinality()* for how they're written, and *clingoReasoner.lp* for what
they mean: too many different (named) objects is an error and too few (for
the domain's individuals: the range's, for "in") a warning; at most one makes
the objects the rules invent the same object (as each other, or as a named
one); and exactly one invents one where the model has none.
'''

def parseCardinality(text:Any) -> tuple[int, int|None]:
  '''
  :param text: A cardinality: "min..max" (eg: "1..1", "0..1", "1..*"), "n"
    (exactly n), or "(min,max)" / "min,max". The max may be "*" or "n" (or
    missing: "1..") for any number.
  :returns: (min, max), max None for any number.
  :raises ValueError: If it can't be read, or min > max.
  '''
  t = str(text).strip()
  if t.startswith("(") and t.endswith(")"):
    t = t[1:-1].strip()
  for sep in ("..", ",", "-"):
    if sep in t:
      lo, hi = (x.strip() for x in t.split(sep, 1))
      break
  else:
    lo, hi = t, t
  try:
    low = int(lo or "0")
    high = None if hi in ("*", "n", "N", "") else int(hi)
  except ValueError:
    raise ValueError(f'"{text}" isn\'t a cardinality: write eg: 1..1, 0..1, 2, or 1..* (or (1,1))') from None
  if low < 0 or (high is not None and high < low):
    raise ValueError(f'"{text}": the bounds must be 0 or more, the smaller first')
  return low, high

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
  "rule_negated":          "rule {0}: {1} in the consequent has a negated constraint ({2}): a rule can't conclude that something isn't so",
  "bad_constraints":       "{0}: the constraints of {1} can't be read: {2}",
  "variable_kind":         "{0}: its name makes it a variable over {1}s, but it's {2}",
  "constraint_report":     "constraint {0}: {1} in its report isn't one of its variables",
  "constraint_severity":   "constraint {0}: its severity is {1}; it should be error or warning",
  "requirement_empty":     "requirement {0}: nothing is required (its required pane is empty), so it can't be violated",
  "pattern_disconnected":  "{0}: its {1} is in parts that aren't related to each other ({2}): every match of one is paired with every match of the others",
  "requirement_unanchored": "requirement {0}: {1} in its required part isn't related to its condition: it only checks that something like it exists",
  "cardinality_max":       "{0}: {2} different objects by {1}, but it allows at most {3}",
  "cardinality_max_in":    "{0}: {2} different objects have it by {1}, but it allows at most {3}",
  "cardinality_min":       "{0}: {2} by {1}, but it needs at least {3}",
  "cardinality_min_in":    "{0}: {2} have it by {1}, but it needs at least {3}",
  "bad_cardinality":       "{0}: its {1} can't be read: {2}",
  "unused_variable":       "{0} is a variable (by its name), but isn't in any query, rule, definition, constraint or requirement: it, and its relations, are ignored -- to stand for someone unknown, give it an ordinary name",
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
    '''
    match = ", ".join(f"{n}={_label(v, relativeTo)}" for n, v in self.bindings)
    return f"(new {self.variable}{' for ' + match if match else ''})"

  def __str__(self) -> str:
    '''
    :returns: A readable string for this object.
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
    '''
    return self.messageIn(self.subject.model)

  def messageIn(self, relativeTo:Model|None) -> str:
    '''
    The message, with objects named relative to *relativeTo* (see *GraphObject.tostring()*).
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
    '''
    return f'{self.severity[0].upper()}: {self.message}'

def assertedIsa(x:GraphObject, t:GraphObject) -> bool:
  '''
  :returns: Whether *x* is a *t* by what's asserted: following only isa links
    that aren't inferred (see *GraphObject.inferred*) -- so not by what a
    reason added (see *materialize()*), which a rule's conclusion is news in
    spite of.
  '''
  seen:set[int] = set()
  pending:list[GraphObject] = [x]
  while pending:
    o = pending.pop()
    if o is t:
      return True
    if id(o) in seen:
      continue
    seen.add(id(o))
    pending += [r.localDst for r in o._outgoing if isinstance(r, IsaIndividual) and r.localSrc is o and not r.inferred and r.localDst is not None]
    if not any(isinstance(r, IsaIndividual) and r.localSrc is o for r in o._outgoing): # (no isa links: its parents are implicit -- eg: node's)
      try:
        pending += o.getParents()
      except LookupError:
        pass
  return False

def _assertedValue(x:GraphObject, key:str, value:Any) -> bool:
  '''
  :returns: Whether *x* has *value* for *key* by what's asserted -- its own
    value (not an inferred one: see *materialize()*), or, without one of its
    own, what it inherits -- so a rule's conclusion that it has isn't news.
  '''
  if value is PRESENT:
    return False
  local = x.getLocalAttr(key)
  if local is not None:
    return not local.inferred and local.value == value
  return x.get(key, None) == value

class ReasoningScope:
  '''
  Which of a model's reasoning results are shown -- put in the model (see
  *materialize()*), marked on its objects and reported: everything, after a
  whole "reason"; or what's about the objects reasoned about (see *reason()*'s
  *about*), less what's about those retracted (see *retractReasoning()*).

  Something is about an object (see *Inferences.restricted()*) if the object
  takes part in it: a relation's ends and type, the rules that concluded it, a
  violation's objects, a new object's match, types and relations -- or, for an
  individual relation, if it's between the same two objects (eg: reasoning
  about ann -has-parent-> bob shows ann -has-ancestor-> bob, and bob
  -has-child-> ann).

  The last say wins: something about two objects, one reasoned about and the
  other retracted, is shown if the first was reasoned about after the other
  was retracted, and not if it was before. Reasoning about the whole model
  again starts afresh: everything's shown.
  '''

  def __init__(self, everything:bool=False):
    '''
    :param everything: Whether everything's shown (as after a whole "reason"); otherwise nothing is, yet.
    '''
    self._seq:int = 0
    self._everything:int|None = None
    "When the whole model was last reasoned about (see *_seq*), or None."
    self._stamps:dict[int, tuple[int, bool, GraphObject]] = {}
    "id(object) -> (when, whether it was reasoned about, not retracted, the object), since *_everything*."
    self._relations:list[tuple[Relation, tuple[int, bool]]]|None = None
    "The individual relations among *_stamps*, with their stamps (see *_stamped()*)."
    if everything:
      self.add(None)

  def copy(self) -> ReasoningScope:
    '''
    :returns: A copy, to change (results restricted to this one keep it: see *Inferences.scope*).
    '''
    ret = ReasoningScope()
    ret._seq, ret._everything, ret._stamps = self._seq, self._everything, dict(self._stamps)
    return ret

  def add(self, objects:Iterable[GraphObject]|None) -> None:
    '''
    Show what's about *objects* (or about anything: everything, if *objects* is None).
    '''
    self._seq += 1
    if objects is None:
      self._everything, self._stamps = self._seq, {}
    else:
      self._stamps.update({id(o): (self._seq, True, o) for o in objects})
    self._relations = None

  def remove(self, objects:Iterable[GraphObject]) -> None:
    '''
    Stop showing what's about *objects*.
    '''
    self._seq += 1
    self._stamps.update({id(o): (self._seq, False, o) for o in objects})
    self._relations = None

  def isEverything(self) -> bool:
    '''
    :returns: Whether everything's shown: the whole model was reasoned about, and nothing's been retracted since.
    '''
    return self._everything is not None and all(shown for _, shown, _ in self._stamps.values())

  def objects(self, shown:bool=True) -> list[GraphObject]:
    '''
    :returns: The objects reasoned about (or, if not *shown*, retracted) since the whole model was last, oldest first.
    '''
    return [o for _, s, o in sorted(self._stamps.values(), key=lambda x: x[0]) if s == shown]

  def _stamped(self) -> list[tuple[Relation, tuple[int, bool]]]:
    '''
    :returns: The individual relations reasoned about or retracted, with when, and which.
    '''
    if self._relations is None:
      self._relations = [(o, (when, shown)) for when, shown, o in self._stamps.values()
                         if isinstance(o, Relation) and o.isIndividual()]
    return self._relations

  def shows(self, objects:Iterable[Any], ends:tuple[Any, Any]|None=None, among:bool=False) -> bool:
    '''
    :param objects: What a conclusion (or violation) is about (see *Inferences.restricted()*): anything
      that isn't a *GraphObject* is ignored.
    :param ends: For a relation, its ends: it's about an individual relation between the same two.
    :param among: Instead of *ends*: whether it's about an individual relation whose two (different) ends are
      both among *objects* (eg: a violation about a, b and their relation type, for a -r-> b).
    :returns: Whether it's shown: by the last say about any of them.
    '''
    best:tuple[int, bool]|None = (self._everything, True) if self._everything is not None else None
    def consider(stamp:tuple[int, bool]|None) -> None:
      nonlocal best
      if stamp is not None and (best is None or stamp[0] > best[0]):
        best = stamp
    ids:set[int] = set()
    for o in objects:
      if isinstance(o, GraphObject):
        ids.add(id(o))
        stamp = self._stamps.get(id(o))
        consider(None if stamp is None else stamp[:2])
    if ends is not None or among:
      pair = {id(ends[0]), id(ends[1])} if ends is not None else None
      for rel, stamp in self._stamped():
        s, d = rel.src, rel.dst
        if s is None or d is None:
          continue
        if (pair is not None and {id(s), id(d)} == pair) or (among and s is not d and id(s) in ids and id(d) in ids):
          consider(stamp)
    return best is not None and best[1]

  def describe(self) -> str:
    '''
    :returns: What's shown, for a summary: "" (everything), eg: "about carol", "about carol and bob",
      "about 4 objects"; or, after a whole "reason", eg: "all but carol".
    '''
    def objs(os:list[GraphObject]) -> str:
      return (os[0].name if len(os) == 1 else f"{os[0].name} and {os[1].name}" if len(os) == 2 else f"{len(os)} objects")
    if self.isEverything():
      return ""
    if self._everything is not None:
      return f"all but {objs(self.objects(shown=False))}"
    shown = self.objects()
    return f"about {objs(shown)}" if shown else "about nothing"

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
  same:list[tuple[GraphObject|NewObject, GraphObject|NewObject]] = field(default_factory=list)
  '''
  Pairs the reasoner found must be the same object (by a cardinality of at
  most one: see *CARDINALITY*), at least one of each an object the rules
  invented. *Reasoner._finish()* merges them: see *mergeSame()*.
  '''
  merged:dict[NewObject, GraphObject|NewObject] = field(default_factory=dict)
  "Each invented object that was merged, and what it was merged into (see *mergeSame()*)."
  newObjects:list[NewObject] = field(default_factory=list)
  '''
  The objects the rules concluded exist. Relations involving them are only in
  *fired* (not *holds*, *inferred*, ...: those are about the model's objects).
  '''
  full:Inferences|None = field(default=None, repr=False, compare=False)
  "If these are restricted to a scope (see *restricted()*), everything the reasoner found."
  scope:ReasoningScope|None = field(default=None, repr=False, compare=False)
  "The scope these are restricted to (see *restricted()*), or None: everything the reasoner found."

  def restricted(self, scope:ReasoningScope) -> Inferences:
    '''
    :param scope: What to show.
    :returns: What *scope* shows of everything the reasoner found (*full*, if these are restricted
      already): see *ReasoningScope* for what each conclusion and violation is about. *holds* keeps
      every pair that isn't inferred or inherited, and *isa* stays whole: they answer queries.
    '''
    src = self.full if self.full is not None else self
    if scope.isEverything():
      return replace(src, full=src, scope=scope)
    rulesOf:dict[tuple[int, int, int], list[GraphObject]] = {}
    for r, t, s, d in src.fired:
      if isinstance(s, GraphObject) and isinstance(d, GraphObject):
        rulesOf.setdefault((id(t), id(s), id(d)), []).append(r)
    # what each new object is about: its rule and match, its types, and what it's related to
    about:dict[tuple, list[Any]] = {_newObjectKey(n): [n.rule, *(v for _, v in n.bindings)] for n in src.newObjects}
    for r, x, typ in src.ruleIsa:
      if isinstance(x, NewObject) and (k := _newObjectKey(x)) in about:
        about[k].append(typ)
    for r, t, s, d in src.fired:
      for a, b in ((s, d), (d, s)):
        if isinstance(a, NewObject) and (k := _newObjectKey(a)) in about and isinstance(b, GraphObject):
          about[k].append(b)
    newOnes = [n for n in src.newObjects if scope.shows(about[_newObjectKey(n)])]
    kept = {_newObjectKey(n) for n in newOnes}
    isNew = lambda x: isinstance(x, NewObject)
    def triple(t:Any, s:Any, d:Any) -> bool:
      return scope.shows([t, s, d, *rulesOf.get((id(t), id(s), id(d)), [])], (s, d))
    def fired(r:Any, t:Any, s:Any, d:Any) -> bool:
      ends = [x for x in (s, d) if isNew(x)]
      if not ends:
        return triple(t, s, d)
      if any(_newObjectKey(x) not in kept for x in ends): # (not without the new object it's about)
        return False
      return scope.shows([t, r, s, d, *(y for x in ends for y in about[_newObjectKey(x)])], (s, d))
    shownTriples = lambda rows: [(t, s, d) for t, s, d in rows if triple(t, s, d)]
    new = {(id(t), id(s), id(d)) for t, s, d in src.inferred + src.inherited}
    return replace(src,
      holds=[(t, s, d) for t, s, d in src.holds if (id(t), id(s), id(d)) not in new or triple(t, s, d)],
      inferred=shownTriples(src.inferred),
      inherited=shownTriples(src.inherited),
      classify=[(x, c) for x, c in src.classify if scope.shows([x, c], (x, c))],
      violations=[v for v in src.violations if scope.shows([v.subject, *v.args], among=True)],
      fired=[row for row in src.fired if fired(*row)],
      ruleAttrs=[(r, x, k, v) for r, x, k, v in src.ruleAttrs
                 if (_newObjectKey(x) in kept if isNew(x) else scope.shows([x, r]))],
      ruleIsa=[(r, x, typ) for r, x, typ in src.ruleIsa
               if (_newObjectKey(x) in kept if isNew(x) else scope.shows([x, typ, r], (x, typ)))],
      newObjects=newOnes,
      full=src, scope=scope)

  def about(self, objects:Iterable[GraphObject]) -> Inferences:
    '''
    :returns: What's about *objects*, of everything the reasoner found (see *restricted()*).
    '''
    scope = ReasoningScope()
    scope.add(objects)
    return self.restricted(scope)

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
    '''
    Everything *src* is related to under *relType* (asserted or inferred).
    '''
    return list(self._index()[0].get((id(src), id(relType)), []))

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    Everything related to *dst* under *relType* (asserted or inferred).
    '''
    return list(self._index()[1].get((id(dst), id(relType)), []))

  def newFacts(self) -> list[tuple[Relation, GraphObject, GraphObject]]:
    '''
    The inferred and inherited relation triples (each once) -- ie: not asserted.
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
    '''
    new = {(id(t), id(s), id(d)) for t, s, d in self.inferred}
    by = lambda r: "" if rule is not None else f"   (by {_label(r, model)})"
    mine = lambda r: rule is None or r is rule
    lines = [f'{_label(s, model)} {relationArrow(t)} {_label(d, model)}{by(r)}' for r, t, s, d in self.fired
             if mine(r) and ((id(t), id(s), id(d)) in new or isinstance(s, NewObject) or isinstance(d, NewObject))]
    attr = lambda k, v: k if v is True or v is PRESENT else f"{k}: {v}"
    lines += [f'{_label(x, model)} {{{attr(k, v)}}}{by(r)}' for r, x, k, v in self.ruleAttrs
              if mine(r) and not isinstance(x, NewObject) and not _assertedValue(x, k, v)]
    lines += [f'{_label(x, model)} -isa-> {_label(t, model)}{by(r)}' for r, x, t in self.ruleIsa
              if mine(r) and not isinstance(x, NewObject) and not assertedIsa(x, t)]
    for n in self.newObjects: # (one line each: that it exists, its types and its attributes)
      if mine(n.rule):
        types = ", ".join(_label(t, model) for _, x, t in self.ruleIsa if x == n)
        attrs = ", ".join(attr(k, v) for _, x, k, v in self.ruleAttrs if x == n)
        lines.append(f'{_label(n, model)} exists{": a " + types if types else ""}{" {" + attrs + "}" if attrs else ""}{by(n.rule)}')
    return lines

  def ruleObjects(self, rule:GraphObject) -> list[GraphObject]:
    '''
    The model objects *rule* concluded something about (not new objects).
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
    The violations about *subject*.
    '''
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
  If *value* is a *Not*, the reverse: it mustn't have the attribute with
  *value.value* (or at all, if that's PRESENT).
  '''
  errors:list[tuple[GraphObject, str]] = field(default_factory=list)
  "(variable, message): constraints that can't be parsed (see *GraphObject.constraintsError()*)."

def patternOf(context:GraphObject, parts:tuple[GraphObject, ...]|None=None, outer:Pattern|None=None) -> Pattern:
  '''
  :param parts: The "contains"-family relation types to read the pattern from.
    By default, all of them other than "consequent", "definiendum" and "required": so for a
    rule, its antecedent, for a definition, its definiens, and for a
    requirement, its condition.
  :param outer: The pattern this one's evaluated within, if any (eg: a
    requirement's condition, for its required part): its value variables have
    values here too.
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
      ret.constraints += [(x, k, v) for k, v in constraintItems(x.constraints())]
      if (err := x.constraintsError()) is not None:
        ret.errors.append((x, err))
      for p in x.getParents():
        if p not in (m.NODE, m.RELATION, m.TOP) and not isinstance(x, IsaIndividual):
          ret.types.append((x, p))
  inPattern = (lambda r: any(r.isa(p) for p in parts)) if parts is not None else \
              (lambda r: r.isa(m.CONTAINS) and not r.isa(m.CONSEQUENT) and not r.isa(m.DEFINIENDUM) and not r.isa(m.REQUIRED))
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
  bound = {v for _, _, v in ret.constraints + (outer.constraints if outer is not None else []) if isinstance(v, ValueVar)}
  for x, k, v in ret.constraints: # (a negated value variable gets its value elsewhere)
    if isinstance(v, Not) and isinstance(v.value, ValueVar) and v.value not in bound:
      ret.errors.append((x, f'{v.value} in "not {k}: {v.value}" must also be used without "not", to give it a value'))
  return ret

def variableGroups(pat:Pattern) -> list[list[str]]:
  '''
  :returns: *pat*'s variables' names, in groups of those related to each
    other: through its relations (and their types, if they're variables), its
    isa links, its "distinct"s, and their constraints' value variables (eg:
    "age: ?a" on two of them). Not through constants: ?a -likes-> fred and ?b
    -likes-> fred don't relate ?a and ?b -- every ?a pairs with every ?b.
    Each group is sorted; the groups are in order of their first names.
  '''
  parent:dict[tuple[str, str], tuple[str, str]] = {}
  def find(k:tuple[str, str]) -> tuple[str, str]:
    while parent.setdefault(k, k) != k:
      k = parent[k]
    return k
  def link(*xs:Any) -> None:
    keys = [("var", x.name) for x in xs if isinstance(x, GraphObject) and x.isVariable()] \
         + [("value", str(x)) for x in xs if isinstance(x, ValueVar)]
    for k in keys[1:]:
      parent[find(k)] = find(keys[0])
    if keys:
      find(keys[0])
  for v in pat.variables:
    link(v)
  for t, s, d in pat.triples:
    link(t, s, d)
  for x, t in pat.types:
    link(x, t)
  for x, y in pat.distinct:
    link(x, y)
  for x, _, v in pat.constraints:
    link(x, v.value if isinstance(v, Not) else v)
  groups:dict[tuple[str, str], set[str]] = {}
  for k in list(parent):
    if k[0] == "var":
      groups.setdefault(find(k), set()).add(k[1])
  return sorted((sorted(g) for g in groups.values()), key=lambda g: g[0])

def patternWarnings(pat:Pattern, part:str) -> list[tuple[str, tuple[Any, ...]]]:
  '''
  :param pat: A query's, rule's, definition's, constraint's or requirement's pattern.
  :param part: What it is, for the message: eg: "antecedent", "condition".
  :returns: A "pattern_disconnected" warning (violation code, args) if its
    variables are in groups that aren't related to each other (see
    *variableGroups()*): every match of one pairs with every match of the
    others -- which is seldom meant (eg: "?x -likes-> fred" and "?y" pairs
    each one who likes fred with everything). Else [].
  '''
  groups = variableGroups(pat)
  if len(groups) < 2:
    return []
  return [("pattern_disconnected", (Sym(part), Sym(" | ".join(", ".join(g) for g in groups))))]

def reportedAnswers(rows:list[dict[GraphObject, Any]]) -> list[dict[GraphObject, Any]]:
  '''
  :param rows: A query's answers (see *Reasoner.answer()*).
  :returns: Them as they're reported: without their hidden variables (eg:
    ?_b: see *names.isHiddenName()*), and once each -- eg: who has a brother,
    once, however many brothers they have. [{}] (yes) if there were answers
    but all their variables are hidden.
  '''
  ret:list[dict[GraphObject, Any]] = []
  seen:set[tuple] = set()
  for row in rows:
    shown = {v: x for v, x in row.items() if not names.isHiddenName(v.name)}
    key = tuple((v.name, id(x)) for v, x in shown.items())
    if key not in seen:
      seen.add(key)
      ret.append(shown)
  return ret

def unusedVariables(objects:list[GraphObject]) -> list[GraphObject]:
  '''
  :param objects: A model's objects (and its super-models').
  :returns: The variables among them (see *GraphObject.isVariable()*) that
    aren't in any context's pattern: not contained by one, nor an end or a
    type of a relation it contains, nor a type of such a variable. As
    variables, they -- and their relations -- aren't facts, so they're ignored:
    eg: a node named ?mother2 to say that two people have the same, unknown,
    mother.
  '''
  used:set[int] = set()
  pending:list[GraphObject] = []
  def use(x:GraphObject|None) -> None:
    if x is not None and id(x) not in used:
      used.add(id(x))
      pending.append(x)
  for c in objects:
    try:
      if not (isinstance(c, Node) and c.isa(c.model.COLLECTION) and c.quotesContents()): # (as GraphObject.isPatternElement(): an individual context or not)
        continue
      for _r, e in c._getOutgoing(lambda r: r.isIndividual() and r.isa(c.model.CONTAINS)):
        use(e)
    except Exception: # (eg: a half-built object)
      continue
  while pending:
    x = pending.pop()
    if isinstance(x, Relation):
      use(x.localSrc); use(x.localDst)
    try:
      for p in x.getParents(): # (eg: a relation's type variable, a variable's type variable)
        use(p)
    except Exception:
      pass
  return [x for x in objects if id(x) not in used and not isinstance(x, IsaIndividual) and x.isVariable()]

def queryWarnings(context:GraphObject) -> list[str]:
  '''
  :param context: A query (or any context) about to be answered.
  :returns: Warnings about its pattern (see *patternWarnings()*), as messages.
  '''
  return [_MESSAGES[code].format(context.name, *args) for code, args in patternWarnings(patternOf(context), "query")]

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
  heads:list[tuple[GraphObject, GraphObject|None, GraphObject|None]] = field(default_factory=list)
  "(relation type, src, dst): what the rule concludes holds (an end None: a problem -- see *problems*)."
  assertions:list[tuple[GraphObject, str, Any]] = field(default_factory=list)
  "(variable, key, value): attributes the rule concludes -- the constraints of the consequent's own variables."
  isas:list[tuple[GraphObject, GraphObject]] = field(default_factory=list)
  "(x, type): isa links the rule concludes."
  new:list[GraphObject] = field(default_factory=list)
  "The consequent's variables the antecedent doesn't bind: a new object for each match (see *NewObject*)."
  problems:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): why the rule can't be used (it's skipped)."
  warnings:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): what may not be meant, reported as warnings -- the rule's still used (see *patternWarnings()*)."

def ruleOf(rule:GraphObject) -> RuleSpec:
  '''
  :returns: The *RuleSpec* of *rule*: its antecedent is *patternOf(rule)*; its
    consequent is what it contains through "consequent" relations:

    - A relation concludes a relation, between its (local) ends, for each of
      its types -- which may be variables.
    - A variable's constraints (see *GraphObject.constraints()*) and its
      types (as drawn) are conclusions if it's the consequent's own variable
      (not one of the antecedent's nodes, whose constraints and types are
      tests) -- a copy of an antecedent variable, or a new one.
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
  spec.warnings += patternWarnings(spec.pattern, "antecedent" if parts is None else " and ".join(p.name for p in parts))
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
  typed = own.values() # (the consequent's own variables -- new or bound copies -- are their types, as drawn)
  for x in {id(x): x for x in typed}.values():
    for p in x.getParents():
      if p not in (m.NODE, m.RELATION, m.TOP) and not isinstance(x, IsaIndividual):
        spec.isas.append((x, p))
  for x in own.values():
    if (err := x.constraintsError()) is not None:
      spec.problems.append(("bad_constraints", (x, err)))
    for k, v in constraintItems(x.constraints()):
      if isinstance(v, Not):
        spec.problems.append(("rule_negated", (x, Sym(f"not {k}"))))
        continue
      if isinstance(v, ValueVar) and v not in bound:
        spec.problems.append(("rule_unbound", (v,)))
      spec.assertions.append((x, k, v))
  return spec

def rules(objects:list[GraphObject], kind:str="RULE") -> list[GraphObject]:
  '''
  :returns: The rules (or with *kind* "DEFINITION" or "CONSTRAINT", definitions or constraints) among *objects*: individuals that isa "rule" ("definition", "constraint").
  '''
  return _contexts(objects).get(kind, [])

def _contexts(objects:list[GraphObject]) -> dict[str, list[GraphObject]]:
  '''
  :returns: The rules, definitions and constraints among *objects*, in one
    pass: "RULE" -> the rules, ... (see *rules()*). Not disabled ones (see
    *GraphObject.isDisabled()*): they're ignored.
  '''
  ret:dict[str, list[GraphObject]] = {}
  for o in objects:
    try:
      if o.isIndividual() and isinstance(o, Node) and o.isa(o.model.CONTEXT) and not o.isPatternElement() and not o.isDisabled():
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

  A requirement (a constraint that isa "requirement") also has *required*:
  then a match of *pattern* (its condition) is a violation only if *required*
  doesn't match too, for the same values of the variables they share. Its
  variables of its own are "some": there must be something for each of them.
  '''
  constraint:GraphObject
  pattern:Pattern
  "What it contains (see *patternOf()*): a requirement's condition."
  code:str
  severity:str
  "error or warning"
  required:Pattern|None = None
  "A requirement's required part (see *patternOf()*); None for any other constraint."
  report:list[Any] = field(default_factory=list)
  "The subject, then the args: the pattern's variables, or constants (*Sym*)."
  template:str|None = None
  "The message template ({0}: the subject; {1}...: the args), or None for the code's (see *_MESSAGES*)."
  problems:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): why the constraint can't be used (it's skipped)."
  warnings:list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
  "(violation code, args): what may not be meant, reported as warnings -- the constraint's still used (see *patternWarnings()*)."

CONSTRAINT_ATTRIBUTES:dict[str, str] = {
  "code":     "The code of the violations it reports (default: the constraint's name).",
  "severity": "error (the default) or warning.",
  "report":   "What a violation is about, as a comma-separated list: its subject, then its arguments -- each one "
              "of the constraint's variables (eg: ^r), or a word taken as is (eg: reflexive). By default, all "
              "its variables, in name order (or the constraint itself if it has none).",
  "message":  "The message, with {0} for the subject and {1}, {2}, ... for the arguments. By default, the "
              "code's built-in message, if it has one.",
  }
"The attributes a constraint is read from: key -> note (see *constraintOf()*)."

def constraintOf(constraint:GraphObject) -> ConstraintSpec:
  '''
  :returns: The *ConstraintSpec* of *constraint*: its pattern is what it
    contains (see *patternOf()*) -- for a requirement, its condition, and its
    *required* what's in its required pane -- and the rest is from its attributes (see
    *CONSTRAINT_ATTRIBUTES*). Eg: a constraint named "irreflexive" containing
    ?a -^r-> ?a, with ^r {irreflexive} and report "^r, ?a", reports each
    irreflexive relation type relating something to itself.
  '''
  pat = patternOf(constraint) # (a requirement's condition: not its "required" pane, which isa consequent)
  def attr(key:str) -> str|None:
    try:
      v = constraint.get(key, None)
    except Exception:
      return None
    return None if v is None or str(v).strip() == "" else str(v).strip()
  spec = ConstraintSpec(constraint, pat, attr("code") or constraint.name, (attr("severity") or "error").lower(),
                        template=attr("message"))
  spec.problems += [("bad_constraints", (x, err)) for x, err in pat.errors]
  m = constraint.model
  if constraint.isa(m.REQUIREMENT):
    spec.warnings += patternWarnings(pat, "condition")
    req = spec.required = patternOf(constraint, (m.REQUIRED,), outer=pat)
    spec.problems += [("bad_constraints", (x, err)) for x, err in req.errors]
    if not (req.variables or req.triples or req.types or req.distinct):
      spec.problems.append(("requirement_empty", ()))
    condition = {v.name for v in pat.variables} | {str(v) for _, _, v in pat.constraints if isinstance(v, ValueVar)}
    for g in variableGroups(req): # (a part related to none of the condition's variables: it can't fail for one match and not another)
      if not condition & set(g) and not any(isinstance(v, ValueVar) and str(v) in condition
                                            for x, _, v in req.constraints if x.name in g):
        spec.warnings.append(("requirement_unanchored", (Sym(", ".join(g)),)))
  else:
    spec.warnings += patternWarnings(pat, "pattern")
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
      if names.isVariableName(tok):
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
  '''
  return [constraintOf(c) for c in rules(objects, "CONSTRAINT")]

def ruleSpecs(objects:list[GraphObject]) -> list[RuleSpec]:
  '''
  :returns: Everything the rules and definitions among *objects* amount to, as *RuleSpec* objects.
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

def baseRulesSource(model:Model) -> str|None:
  '''
  :param model: A model.
  :returns: If *model* is one of the base rules (see *baseRuleModels()*),
    the URL of the file it's read from -- for package data, the package's own
    file, not the copy it's actually read from -- else None.
  '''
  path = urlPath(model.url) if model.url.startswith("file:") else None
  for src in BASE_RULES:
    if isinstance(src, str):
      if Model.absoluteURL(src) == model.url:
        return model.url
    elif path is not None and _baseFiles.get(str(src)) and os.path.realpath(_baseFiles[str(src)]) == os.path.realpath(path):
      return Path(str(src)).as_uri()
  return None

def _baseURL(src:str|Traversable) -> str:
  '''
  :param src: One of *BASE_RULES*.
  :returns: Its URL: package data's is that of a copy in a temporary folder,
    made to refer to where it then is (made the first time).
  '''
  if isinstance(src, str):
    return src
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
  return Path(path).as_uri()

def _baseURLOfModel(src:str|Traversable) -> str:
  '''
  :returns: The URL of *src*, one of *BASE_RULES* -- read (see
    *baseRuleModels()*), so it's there when the URL's used.
  '''
  baseRuleModels()
  return _baseURL(src)

def baseRuleModels() -> list[Model]:
  '''
  :returns: The models of *BASE_RULES*, read (and write-locked) if need be.
    Package data -- which may be in a zip, and is stored as being in
    *BASE_RULES_PLACEHOLDER* -- is read from a copy in a temporary folder,
    made to refer to where it then is. (None while they're being read: see
    *Model.implicitSuperDBs()*.)
  '''
  if _readingBase:
    return []
  ret:list[Model] = []
  for i, src in enumerate(BASE_RULES):
    url = _baseURL(src)
    if not isinstance(src, str): # (named -- "sn:/baseRules", ... -- as written in the models that build on it)
      name = BASE_RULES_URL if i == 0 else f"{BASE_RULES_URL}{i + 1}"
      PRDb.namedURLs.setdefault(name, lambda src=src: _baseURLOfModel(src)) # type: ignore[misc] # @undefinedVariable
      PRDb._namesOf[url] = name
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

# ── Engines ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class EngineInfo:
  '''
  What the program knows about a reasoner engine without importing it: what it
  needs installed, and what it can do. So a missing engine can say how to
  install it (see *EngineMissing*), and a feature can use any installed engine
  that can do what it needs (see *explainingEngine()*).
  '''
  name:str
  "The engine's name (eg: \"nemo\"): its module is sn.model.<name>Reasoner."
  module:str
  "The Python module it needs (eg: \"nmo_python\")."
  package:str
  "The package that provides *module*, as pip names it (eg: \"nemo-python\")."
  explains:bool = False
  "Whether it can say why a conclusion holds (see *sn.model.nemoReasoner.NemoReasoner.explain()*)."
  bundled:bool = True
  "Whether the apps include it (their self-test checks that it's there: see *sn.__main__.selftest()*)."
  needs:str = ""
  "What must be installed before *package*, if anything (eg: SWI-Prolog, which janus-swi is the Python interface to)."

ENGINES:dict[str, EngineInfo] = {e.name: e for e in (
  EngineInfo("clingo", "clingo", "clingo"),
  EngineInfo("nemo", "nmo_python", "nemo-python", explains=True),
  EngineInfo("clips", "clips", "clipspy", bundled=False),
  EngineInfo("prolog", "janus_swi", "janus-swi", bundled=False, needs="SWI-Prolog (9.1.12 or later, from swi-prolog.org)"),
)}
'''
The known reasoner engines, by name. A new engine adds itself here, and to the
"reasoner/engine" preference's choices (see *sn.PREFS*), and its install
instructions to the User Guide (see *INSTALL_HELP*).
'''

PIP = f"python{sys.version_info[0]}.{sys.version_info[1]} -m pip"
"How to run pip for a Python of this one's version, which an engine must be installed for: eg, \"python3.14 -m pip\"."

INSTALL_HELP = "user/reasoning.html#installing-an-engine"
"The User Guide's page (and section) on installing a reasoner engine: see *sn.view.graphics.guiApp.showHelp()*."

class EngineMissing(ImportError):
  '''
  A reasoner engine isn't installed, or can't be loaded: raised by
  *Reasoner.create()*, saying how to install it. (The GUI shows it with a link
  to *INSTALL_HELP*: see *sn.view.graphics.viewReasoning.showEngineMissing()*.)
  '''
  def __init__(self, engine:str, detail:str=""):
    '''
    :param engine: The engine's name (eg: "nemo").
    :param detail: Why it couldn't be loaded, if it's installed but broken.
    '''
    info = ENGINES.get(engine)
    self.engine:str = engine
    self.package:str|None = info.package if info is not None else None
    self.detail:str = detail
    how = "" if info is None else \
          f'install {info.needs}, then "{PIP} install {info.package}" ' if info.needs else f'install it with "{PIP} install {info.package}" '
    super().__init__(f'The "{engine}" reasoner engine isn\'t {"working" if detail else "installed"}'
                     f'{f" ({detail})" if detail else ""}: {how}(see "Installing an engine" in the User Guide).',
                     name=info.module if info is not None else None)

def engineInstalled(engine:str) -> bool:
  '''
  :returns: Whether *engine* can be used: it's loaded already, or what it needs
    is installed. (It's looked for, not loaded: if it's broken, *Reasoner.create()*
    still raises *EngineMissing*.)
  '''
  if engine in Reasoner.engines:
    return True
  info = ENGINES.get(engine)
  if info is None:
    return False
  try:
    return importlib.util.find_spec(info.module) is not None \
        or _lookOutside() and importlib.util.find_spec(info.module) is not None
  except (ImportError, ValueError):
    return False

def _lookOutside() -> bool:
  '''
  In a packaged app -- which has its own Python, so pip can't install into it
  -- make the packages of a Python of the same version on this computer
  importable (see *util.localPython.addPackages()*): the "reasoner/python"
  setting's, or else the first found. So an engine the app doesn't include can
  be installed for that Python, and used.

  :returns: Whether there's such a Python (whose packages are now on the path).
  '''
  if not getattr(sys, "frozen", False):
    return False
  from util.localPython import addPackages
  return bool(addPackages(str(sn.snPrefs.get("reasoner/python", "") or "") or None))

def _importEngine(engine:str) -> None:
  '''
  Import *engine*'s module (which registers it): if what it needs isn't
  installed, after looking for it in a Python on this computer (see *_lookOutside()*).
  '''
  try:
    import_module(f'sn.model.{engine}Reasoner')
  except ModuleNotFoundError as ex:
    info = ENGINES.get(engine)
    if info is None or ex.name != info.module or not _lookOutside():
      raise
    import_module(f'sn.model.{engine}Reasoner') # (again, with that Python's packages)

def installedEngines() -> list[str]:
  ''':returns: The names of the engines that can be used (see *engineInstalled()*).'''
  return [e for e in dict.fromkeys([*ENGINES, *Reasoner.engines]) if engineInstalled(e)]

def explainingEngine() -> str:
  '''
  :returns: The engine to explain a conclusion with (see
    *sn.controller.modelInterface.ModelContext.explain()*): the default one if
    it can, or else the first installed one that can -- or, if none is
    installed, the first that can (so *Reasoner.create()* says how to install it).
  '''
  able = [e for e, info in ENGINES.items() if info.explains] \
       + [e for e, cls in Reasoner.engines.items() if e not in ENGINES and callable(getattr(cls, "explain", None))]
  default = defaultEngine()
  return min(able, key=lambda e: (not engineInstalled(e), e != default))

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
  that lives there needs no other registration; which engine is used by
  default is a preference (see *defaultEngine()*).
  '''

  engines:ClassVar[dict[str, type[Reasoner]]] = {}
  "Registered engines by name."

  language:ClassVar[str|None] = None
  "The name of the language :py:meth:`query` accepts, or None if it has none."

  def __init_subclass__(cls, engine:str|None=None, **kwargs): # @NoSelf (implicitly a classmethod)
    '''
    A subclass made with an *engine* name is the reasoner for that engine (see *create()*).
    '''
    super().__init_subclass__(**kwargs)
    if engine is not None:
      Reasoner.engines[engine] = cls

  @classmethod
  def create(cls, model:Model, engine:str|None=None, **kwargs) -> Reasoner:
    '''
    A reasoner over *model* by *engine* (its module, sn.model.<engine>Reasoner, imported if need be); *kwargs*
    are its constructor's.

    :param engine: The engine's name (eg: "clingo", "nemo"); by default, the preference's (see *defaultEngine()*).
    :raises EngineMissing: If the engine (or what it needs: eg, nemo's Nemo) isn't installed, or won't load.
    :raises ValueError: If there's no such engine.
    '''
    if engine is None:
      engine = defaultEngine()
    if engine not in cls.engines:
      try:
        _importEngine(engine)
      except ImportError as ex:
        if engine not in ENGINES and ex.name == f'sn.model.{engine}Reasoner':
          raise ValueError(f'There\'s no "{engine}" reasoner engine: the engines are {", ".join(ENGINES)}.') from ex
        missing = isinstance(ex, ModuleNotFoundError) and engine in ENGINES and ex.name == ENGINES[engine].module
        raise EngineMissing(engine, "" if missing else str(ex)) from ex
    return cls.engines[engine](model, **kwargs)

  def __init__(self, model:Model, showSysRules:bool|None=None):
    '''
    :param showSysRules: Whether the base rules (see *BASE_RULES*) show in
      the results: their objects as data, and their conclusions as rule
      conclusions (rather than plain inferences). By default, as the
      "reasoner/showSysRules" preference says.
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
    '''

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
    '''
    :returns: Everything *src* is related to under *relType*, asserted or inferred.
    '''
    return self.run().related(src, relType)

  def relatedFrom(self, dst:GraphObject, relType:Relation) -> list[GraphObject]:
    '''
    :returns: Everything related to *dst* under *relType*, asserted or inferred.
    '''
    return [s for t,s,d in self.run().holds if d is dst and t is relType]

  def isa(self, obj:GraphObject, typ:GraphObject) -> bool:
    '''
    Whether *obj* isa *typ*, as reasoned (see *run()*).
    '''
    return any(x is obj and t is typ for x,t in self.run().isa)

  def instances(self, typ:GraphObject, individualsOnly:bool=True) -> list[GraphObject]:
    '''
    :returns: Every (individual) object that isa *typ*, other than *typ* itself.
    '''
    return [x for x,t in self.run().isa if t is typ and x is not typ
            and (x.isIndividual() or not individualsOnly)]

  def violations(self, subject:GraphObject|None=None) -> list[Violation]:
    '''
    The violations found by reasoning (see *run()*): all of them, or those about *subject*.
    '''
    return [v for v in self.run().violations if subject is None or v.subject is subject]

  # ── Model export ─────────────────────────────────────────────────────────

  def objects(self) -> list[GraphObject]:
    '''
    :returns: The objects of the model and (transitively) its super-models --
      but not the base rules' (see *BASE_RULES*), unless it's one of them:
      they're rules, not data (see *ruleObjects()*).
    '''
    return [obj for m in self.dataModels() for obj in list(m.values()) if not getattr(obj, "inferred", False)]

  def dataModels(self) -> list[Model]:
    '''
    :returns: The model and (transitively) its super-models -- but not the base
      rules (see *BASE_RULES*), unless it's one of them (see *objects()*).
    '''
    return dataModelsOf(self.model)

  def ruleObjects(self) -> list[GraphObject]:
    '''
    :returns: What the rules, definitions and constraints are read from:
      *objects()*, and the base rules' (see *BASE_RULES*).
    '''
    ret = self.objects()
    have = {id(o.model) for o in ret}
    return ret + [o for m in baseRuleModels() if id(m) not in have for o in list(m.values())]

  def specs(self) -> tuple[list[RuleSpec], list[ConstraintSpec]]:
    '''
    :returns: The rules and definitions (see *ruleSpecs()*), and the
      constraints (see *constraintSpecs()*), of *ruleObjects()*. (The base
      rules' are read once: they're read-only.)
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

  def isSystem(self, obj:Any, bases:list[Model]|None=None) -> bool:
    '''
    :param bases: The base rules' models (see *baseRuleModels()*), if the
      caller has them already: eg: to ask of many objects.
    :returns: True iff *obj* is (or is made by) one of the base rules (see *BASE_RULES*).
    '''
    if isinstance(obj, NewObject):
      obj = obj.rule
    return isinstance(obj, GraphObject) and any(obj.model is m for m in (baseRuleModels() if bases is None else bases))

  def _finish(self, ret:Inferences) -> Inferences:
    '''
    What every engine does with its results, before returning them from *run()*:

      - A violation is reported once per set of objects it's about: eg: an
        asymmetric relation between a and b once, not again for b and a. (Of
        such, the one whose args come first in the models' order is kept.)
      - A constraint's violations get its message (see *ConstraintSpec*).
      - Objects that must be the same (*Inferences.same*) are merged (see
        *mergeSame()*).
      - The relation triples (*holds*, ...) are put in the models' order.
      - Unless *showSysRules*, the base rules' conclusions aren't reported as
        rule conclusions (*fired*, ...): what they conclude is in *holds*,
        *inferred*, ... as any inference is.

    :returns: *ret*, changed.
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
    mergeSame(ret)
    for name in ("holds", "inferred", "inherited", "classify"): # (in the models' order, not the engine's: the same each time)
      setattr(ret, name, sorted(getattr(ret, name), key=lambda row: [order(x) for x in row]))
    specs = getattr(self, "_constraintSpecs", None) # (as the engine used them: see specs())
    templates = {s.code: s.template for s in (specs if specs is not None else self.specs()[1]) if s.template}
    ret.violations = [v for v in ret.violations if best[key(v)] is v]
    ret.violations += [Violation("unused_variable", "warning", x, ()) for x in unusedVariables(self.objects())]
    for v in ret.violations:
      if v.template is None and v.code in templates:
        v.template = templates[v.code]
    if not self.showSysRules:
      bases = baseRuleModels() # (once: each call looks for their files, and gets their models)
      ret.fired = [x for x in ret.fired if not self.isSystem(x[0], bases)]
      ret.ruleAttrs = [x for x in ret.ruleAttrs if not self.isSystem(x[0], bases)]
      ret.ruleIsa = [x for x in ret.ruleIsa if not self.isSystem(x[0], bases)]
      ret.newObjects = [x for x in ret.newObjects if not self.isSystem(x, bases)]
    return ret

  def facts(self) -> list[Fact]:
    '''
    :returns: The model (and its super-models) as engine-neutral facts; see
      the module documentation for the vocabulary. With *showSysRules*, the
      base rules too (see *BASE_RULES*). What a previous "reason" inferred
      isn't among them (see *withoutInferences()*).
    '''
    with withoutInferences([*self.dataModels(), *baseRuleModels()]):
      return self._facts()

  def _facts(self) -> list[Fact]:
    '''
    :returns: *facts()*, with the inferred objects out of the way.
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
      if (vk := obj.variableKind()).isVariable and dict.__contains__(obj, "name"): # (not a ^r's relations, which inherit its name)
        out.append(("var_kind", (obj, Sym(vk.value))))
      out.append(("kind", (obj, Sym(_kind(obj)))))
      out.append(("name", (obj, obj.name)))
      try:
        for p in obj.getParents():
          out.append(("parent", (obj, ref(p))))
      except RecursionError:
        out.append(("parent", (obj, obj))) # getParents() refuses self-parenting; let the rules report it
      except LookupError:
        pass
      if obj.selfIsaLinks(): # (getParents() leaves it out: the rules report it -- see isa_cycle)
        out.append(("parent", (obj, obj)))
      if isinstance(obj, Collection):
        out.append(("collection", (obj,)))
      if obj.isCollection() and not obj.quotesContents(): # (a box of facts, whatever its Python class: not AllModelCollection,
        out += [("member", (obj, ref(m))) for m in obj.getMembers()] # which would just list the model; nor a rule's patterns)
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
    The facts about relation *rel*: its ends (its own and inherited), and, for an individual relation that
    isn't a pattern, that it relates them (*ref* refers to an end).
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
      for key, direction in CARDINALITY.items(): # (its own, too: see CARDINALITY)
        text = rel.getLocal(key, None)
        if text is None or str(text).strip() == "":
          continue
        try:
          low, high = parseCardinality(text)
        except ValueError as ex:
          out.append(("card_error", (rel, key, str(ex))))
          continue
        out.append(("card", (rel, Sym(direction), low, -1 if high is None else high)))
    return out

# ── Shared results ────────────────────────────────────────────────────────

def dataModelsOf(model:Model) -> list[Model]:
  '''
  :returns: *model* and (transitively) its super-models -- but not the base
    rules (see *BASE_RULES*), unless it's one of them: what a reasoner over
    *model* reasons over (see *Reasoner.dataModels()*).
  '''
  base = [m for m in baseRuleModels() if m is not model]
  models:list[Model] = []
  pending = [model]
  while pending:
    m = pending.pop()
    if m not in models and not any(m is b for b in base):
      models.append(m)
      pending.extend(m.superDBs) #type: ignore[arg-type]
  return models

def defaultEngine() -> str:
  '''
  :returns: The name of the reasoner engine to use when none is given: the
    "reasoner/engine" preference (clingo, unless it's set to another).
  '''
  return str(sn.snPrefs.get("reasoner/engine", "clingo") or "clingo")

def setDefaultEngine(engine:str) -> None:
  '''
  Make *engine* the one used when none is given: the "reasoner/engine"
  preference, as Settings would set it (keeping its type -- the engines to
  choose from -- which a plain value would replace).
  '''
  typ, _default, note = sn.PREFS["reasoner/engine"]
  sn.snPrefs["reasoner/engine"] = Attribute(engine, typ, VAR_DEFAULTED, note)

def reason(model:Model, engine:str|None=None, silent:bool=False, about:Iterable[GraphObject]|None=None) -> Inferences:
  '''
  Run the reasoner over *model* and keep the results on the model (see
  *reasoningFor()*), where everything using the model -- the command line,
  every view -- finds the same ones. Observers of the model are told with a
  ("reasoned", (inferences, silent, shown)) topic: *shown* is None, or (when
  reasoning *about* some objects) the inferred objects about them, for views to
  show (see *inferredObjectsFor()*). The results aren't saved with the model,
  and aren't updated as it's edited: they're a snapshot until the next
  *reason()*, *retractReasoning()* or *clearReasoning()*.

  :param engine: The reasoner engine; by default the preference's (see *defaultEngine()*).
  :param silent: True if views shouldn't show what's inferred (eg: just so
    that queries find it): they show only the problems (see *SNGView._showReasoning()*).
  :param about: Objects to reason about (eg: those selected in a view): the
    reasoner still reasons over the whole model -- what holds of an object can
    depend on any of it -- but only what's about these (see *ReasoningScope*) is
    added to what the model's results show: to its inferred objects, and the
    violations marked. By default, the whole model: all of it is shown.
  :returns: What the model's results show now (see *Inferences.restricted()*):
    with *about*, what's about them and what was shown before (where it still
    holds); *full* has everything the reasoner found.
  '''
  reasoner = Reasoner.create(model, engine)
  full = reasoner.run()
  objects = None if about is None else list(about)
  prev = reasoningFor(model)
  scope = prev.scope.copy() if objects is not None and prev is not None and prev.scope is not None else ReasoningScope()
  scope.add(objects)
  ret = full.restricted(scope)
  materialize(model, ret, reasoner.dataModels())
  model.reasoning = ret #type: ignore[attr-defined]
  shown = None if objects is None else inferredObjectsFor(model, full.about(objects))
  model.notify(("reasoned", (ret, silent, shown)))
  return ret

def retractReasoning(model:Model, objects:Iterable[GraphObject]) -> Inferences|None:
  '''
  Take back what *model*'s reasoning results (see *reason()*) say about
  *objects* (see *ReasoningScope*): the inferred objects about them go from
  the model (and so from its views), and the violations about them aren't
  marked. The rest stay, and nothing's reasoned again. Observers are told with
  a ("reasoning retracted", (inferences, objects)) topic.

  :returns: What the results show now, or None if there are none (nothing to take back).
  '''
  r = reasoningFor(model)
  if r is None:
    return None
  objects = list(objects)
  scope = r.scope.copy() if r.scope is not None else ReasoningScope(everything=True)
  scope.remove(objects)
  ret = r.restricted(scope)
  materialize(model, ret, dataModelsOf(model), add=False) # (what's left is there already: the model may have changed since)
  model.reasoning = ret #type: ignore[attr-defined]
  model.notify(("reasoning retracted", (ret, objects)))
  return ret

def inferredObjectsFor(model:Model, inferences:Inferences) -> list[GraphObject]:
  '''
  :param model: A model whose results have been put in it (see *materialize()*).
  :param inferences: Some of them: eg, what's about some objects (see *Inferences.about()*).
  :returns: *model*'s inferred objects for *inferences*' conclusions: the
    relations and isa links (not a new object's own isa links, which go with it)
    and the new objects (see *GraphObject.inferred*).
  '''
  rels = _inferredRelations(model)
  nodes = {o.inferredKey: o for o in model.inferredObjects()
           if not isinstance(o, Relation) and getattr(o, "inferredKey", None) is not None and o._isConnected()}
  keys = {(id(t), id(s), id(d)) for t, s, d in inferences.newFacts()}
  keys |= {(id(model.ISA), id(x), id(typ)) for _, x, typ in inferences.ruleIsa if isinstance(x, GraphObject)}
  real = lambda o: nodes.get(_newObjectKey(o)) if isinstance(o, NewObject) else o
  for _, t, s, d in inferences.fired:
    if isinstance(s, NewObject) or isinstance(d, NewObject):
      rs, rd = real(s), real(d)
      if rs is not None and rd is not None:
        keys.add((id(t), id(rs), id(rd)))
  ret:list[GraphObject] = [n for n in (nodes.get(_newObjectKey(x)) for x in inferences.newObjects) if n is not None]
  return ret + [r for k, r in rels.items() if k in keys and r._isConnected()]

def summary(model:Model) -> str:
  '''
  :returns: What *model*'s last "reason" found, in a line -- eg: "inferred:
    3 relations, 4 new objects; 1 error, 2 warnings", or (if only some of it's
    shown: see *ReasoningScope*) eg: "about carol: inferred: 1 relation; no
    problems" -- or "" if it hasn't been reasoned over (or that's been retracted).
  '''
  r = reasoningFor(model)
  if r is None:
    return ""
  plural = lambda n, what: f"{n} {what}{'' if n == 1 else 's'}"
  rels = len(_inferredRelations(model))
  new = sum(1 for o in model.inferredObjects() if getattr(o, "inferredKind", None) == "new")
  found = [plural(rels, "relation")] + ([plural(new, "new object")] if new else [])
  errors = sum(1 for v in r.violations if v.severity == "error")
  warnings = len(r.violations) - errors
  problems = ", ".join([plural(errors, "error")] * bool(errors) + [plural(warnings, "warning")] * bool(warnings)) or "no problems"
  scope = r.scope.describe() if r.scope is not None else ""
  return f"{scope + ': ' if scope else ''}inferred: {', '.join(found)}; {problems}"

def clearReasoning(model:Model) -> None:
  '''
  Forget *model*\'s reasoning results; observers are told with a ("reasoning cleared", ()) topic.
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
  :returns: The inferred attributes (see *Attribute.inferred*) of their
    objects: (object, key, attribute).
  '''
  return [(o, k, a) for m in models for o in list(m.values()) if o is not None
          for k, a in list(dict.items(o)) if isinstance(a, Attribute) and a.inferred]

def _inferredRelations(model:Model) -> dict[tuple[int, int, int], Relation]:
  '''
  :param model: A model.
  :returns: *model*'s inferred relations -- not the isa links of inferred
    relations, which go with them -- by (id(type), id(src), id(dst)); an isa
    link's type is the model's ISA.
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

def sameClasses(pairs:list[tuple[Any, Any]]) -> dict[NewObject, GraphObject|NewObject]:
  '''
  :param pairs: Pairs of objects that must be the same (see *Inferences.same*).
  :returns: For each invented object (*NewObject*) among them, what stands for
    its class -- the objects all the same as it: the model's object, if
    there's just one in the class (the invented ones are it); else one of the
    invented ones, the same each time (one a rule made, rather than a
    cardinality -- its name is the user's -- then the shortest name, then the
    first by name). (Two of the model's objects can't be the same: that's reported --
    see *CARDINALITY* -- and their invented ones stay invented.)
  '''
  key = lambda o: ("g", id(o)) if isinstance(o, GraphObject) else ("n", _newObjectKey(o)) # (by identity: see _newObjectKey())
  parent:dict[tuple, tuple] = {}
  objs:dict[tuple, Any] = {}
  def find(k:tuple) -> tuple:
    while parent.setdefault(k, k) != k:
      parent[k] = parent[parent[k]]
      k = parent[k]
    return k
  for a, b in pairs:
    ka, kb = key(a), key(b)
    objs[ka], objs[kb] = a, b
    ra, rb = find(ka), find(kb)
    if ra != rb:
      parent[ra] = rb
  classes:dict[tuple, list[Any]] = {}
  for k, o in objs.items():
    classes.setdefault(find(k), []).append(o)
  ret:dict[NewObject, GraphObject|NewObject] = {}
  for members in classes.values():
    named = [o for o in members if isinstance(o, GraphObject)]
    invented = sorted((o for o in members if isinstance(o, NewObject)), # (one a rule made first: its name is the user's)
                      key=lambda n: (not names.isVariableName(n.variable), len(_newObjectName(n, None)), _newObjectName(n, None)))
    if not invented:
      continue
    rep = named[0] if len(named) == 1 else invented[0]
    for n in invented:
      ret[n] = rep
  return ret

def mergeSame(ret:Inferences) -> None:
  '''
  Merge the objects that must be the same (*ret.same*: see *sameClasses()*):
  each invented object is replaced by what stands for its class, in the rules'
  conclusions (*fired*, *ruleAttrs*, *ruleIsa*), and only those that stand for
  a class (or weren't merged) are left in *newObjects*. (What the engine
  concluded about the model's objects -- *holds*, ... -- already includes what
  it concluded about the invented ones that are them.) *ret.merged* is set.
  '''
  m = sameClasses(ret.same)
  ret.merged = m
  if not m:
    return
  byKey = {_newObjectKey(n): r for n, r in m.items()}
  f = lambda x: byKey.get(_newObjectKey(x), x) if isinstance(x, NewObject) else x
  def unique(rows:list) -> list: # (by identity: GraphObjects compare as dicts)
    seen:set = set()
    out = []
    for row in rows:
      k = tuple(_newObjectKey(x) if isinstance(x, NewObject) else ("g", id(x)) if isinstance(x, GraphObject) else ("v", repr(x)) for x in row)
      if k not in seen:
        seen.add(k)
        out.append(row)
    return out
  ret.fired = unique([(r, t, f(s), f(d)) for r, t, s, d in ret.fired])
  ret.ruleAttrs = unique([(r, f(x), k, v) for r, x, k, v in ret.ruleAttrs])
  ret.ruleIsa = unique([(r, f(x), t) for r, x, t in ret.ruleIsa])
  ret.newObjects = [n for (n,) in unique([(n,) for n in ret.newObjects]) if f(n) is n or (isinstance(f(n), NewObject) and _newObjectKey(f(n)) == _newObjectKey(n))] # type: ignore[arg-type]

def _newObjectKey(n:NewObject) -> tuple:
  '''
  :param n: An object a rule concluded exists.
  :returns: What identifies it from one "reason" to the next: the rule, the
    variable, and the match (by identity, for the model's objects).
  '''
  return (id(n.rule), n.variable, tuple((name, id(v) if isinstance(v, GraphObject) else repr(v)) for name, v in n.bindings))

def _newObjectName(n:NewObject, model:Model|None) -> str:
  '''
  :param n: An object a rule concluded exists.
  :param model: The model it's made in (objects are named relative to it).
  :returns: The name of the inferred node made for it, eg: "(m for alice)" --
    not a variable's name (see *sn.model.names*: it isn't a pattern).
  '''
  what = names.stem(n.variable) or "new"
  match = ", ".join(v.name if isinstance(v, GraphObject) else str(v) for _, v in n.bindings)
  return f"({what} for {match})" if match else f"(new {what})"

def inferredNodeFor(model:Model, n:Any) -> Any:
  '''
  :param model: A model that's been reasoned over.
  :param n: Anything: eg: an answer's value.
  :returns: If *n* is an object a rule concluded exists (see *NewObject*), the
    inferred node made for it in *model* (see *materialize()*), if there is one;
    otherwise *n*.
  '''
  if not isinstance(n, NewObject):
    return n
  key = _newObjectKey(n)
  return next((o for o in model.inferredObjects() if getattr(o, "inferredKey", None) == key and o._isConnected()), n)

def _retype(node:GraphObject, types:list[GraphObject]) -> None:
  '''
  Make inferred *node*'s types *types*: its isa links to others are taken
  out, and ones to those it hasn't are made (inferred, as it is).
  '''
  links = [r for r in node._outgoing if isinstance(r, IsaIndividual) and r.localSrc is node]
  for r in links:
    if not any(r.localDst is t for t in types) and r._isConnected():
      r._disconnect()
  for t in types:
    if not any(r.localDst is t and r._isConnected() for r in links):
      IsaIndividual(node.model, node, t, inferred=True)

def materialize(model:Model, inferences:Inferences, models:list[Model], add:bool=True) -> None:
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
  :param inferences: What the reasoner concluded.
  :param models: *model* and its super-models.
  :param add: False to only remove those no longer inferred: none are made,
    and none are changed (eg: to take back some of the results, which may
    be about a model that's changed since).
  '''
  want:dict[tuple[int, int, int], tuple[GraphObject, Any, Any]] = {}
  kinds:dict[tuple[int, int, int], str] = {}
  inherited = {(id(t), id(s), id(d)) for t, s, d in inferences.inherited}
  for t, s, d in inferences.newFacts():
    if isinstance(s, GraphObject) and isinstance(d, GraphObject) and isinstance(t, Relation):
      key = (id(t), id(s), id(d))
      want[key], kinds[key] = (t, s, d), "inherited" if key in inherited else "inferred"
  for _, x, typ in inferences.ruleIsa:
    if isinstance(x, GraphObject) and isinstance(typ, GraphObject) and \
       not any(p is typ for _, p in x._getOutgoing(lambda r: isinstance(r, IsaIndividual) and not r.inferred)): # (not asserted already)
      key = (id(model.ISA), id(x), id(typ))
      want[key], kinds[key] = (model.ISA, x, typ), "inferred"
  # the new objects: kept by what identifies them (see _newObjectKey())
  newOnes = {_newObjectKey(n): n for n in inferences.newObjects}
  haveNodes = {o.inferredKey: o for o in model.inferredObjects()
               if not isinstance(o, Relation) and getattr(o, "inferredKey", None) is not None}
  have = _inferredRelations(model)
  with model.inferring(*models):
    nodes:dict[tuple, GraphObject] = {}
    for key, n in newOnes.items():
      node = haveNodes.get(key)
      types = [t for _, x, t in inferences.ruleIsa if isinstance(x, NewObject) and _newObjectKey(x) == key and isinstance(t, GraphObject)]
      if node is None or not node._isConnected():
        if not add:
          continue
        try:
          node = Node(model, types or [model.NODE], individual=True, name=_newObjectName(n, model), inferred=True)
        except Exception as ex:
          logger.warning(f"Couldn't add the new object {n}: {type(ex).__name__}: {ex}")
          continue
        node.inferredKey, node.inferredKind = key, "new"
      elif add: # (kept: but the rule may say something else about it now -- its types as it says now)
        _retype(node, types or [model.NODE])
      nodes[key] = node
    wantNew:dict[int, set[str]] = {id(node): set() for node in nodes.values()}
    for _, x, k, v in inferences.ruleAttrs: # (their attributes -- the model's own objects' are just reported)
      node = nodes.get(_newObjectKey(x)) if isinstance(x, NewObject) else None
      if node is not None:
        wantNew[id(node)].add(k)
        if add and node.get(k, None) != v:
          try:
            node[k] = v
          except Exception as ex:
            logger.warning(f"Couldn't give {node.name} {k}={v}: {type(ex).__name__}: {ex}")
    for node in nodes.values(): # (a kept one's attributes the rule no longer gives it)
      for k in [k for k in dict.keys(node) if k != "name" and k not in wantNew[id(node)]]:
        del node[k]
    # the attribute values the rules concluded for the model's own objects: inferred attributes
    # (not where the object has a value of its own -- given beats inferred)
    wantAttrs:dict[tuple[int, str], tuple[GraphObject, str, Any]] = {}
    for _, x, k, v in inferences.ruleAttrs:
      if isinstance(x, GraphObject) and not getattr(x, "inferred", False):
        wantAttrs[(id(x), k)] = (x, k, v)
    for o, k, a in _inferredAttributes(models):
      if (id(o), k) not in wantAttrs:
        del o[k]
    for x, k, v in wantAttrs.values() if add else ():
      local = x.getLocalAttr(k)
      try:
        inh = x._getSuperAttr(k)
        v = coerceValue(inh.type if inh is not None else None, v) # (eg: 30 for a float: 30.0)
        if local is None:
          if x.get(k, None) == v: # (it has that value already: inherited)
            continue
          # an inherited attribute's type (and restrictions) are its type's: the value is just a value
          x.setAttr(k, Attribute(v, None, None, inferred=True) if inh is not None else
                       Attribute(v, type(v), Restriction.fromstring("VAR"), inferred=True))
        elif local.inferred and local.value != v:
          local.value = v
          x.notify(("mod attribute", (k, v)))
          x._notifyAttributeInheritors(k)
      except Exception as ex:
        logger.warning(f"Couldn't give {x.name} the inferred {k}={v}: {type(ex).__name__}: {ex}")
    real = lambda o: nodes.get(_newObjectKey(o)) if isinstance(o, NewObject) else o
    for _, ft, fs, fd in inferences.fired: # (the relations the rules gave the new objects)
      if isinstance(fs, NewObject) or isinstance(fd, NewObject):
        rs, rd = real(fs), real(fd)
        if isinstance(ft, Relation) and isinstance(rs, GraphObject) and isinstance(rd, GraphObject):
          key = (id(ft), id(rs), id(rd))
          want[key], kinds[key] = (ft, rs, rd), "rule"
    for key, old in have.items():
      if key not in want and old._isConnected():
        old._disconnect()
    for key, node in haveNodes.items():
      if key not in nodes and node._isConnected():
        node._disconnect()
    for key, (rt, s, d) in want.items():
      try:
        obj = have.get(key)
        if obj is None or not obj._isConnected():
          if not add:
            continue
          if rt is model.ISA and (problem := s.parentProblem(d)) is not None: # (a rule concluded an isa cycle -- or one that's asserted)
            if not s.isaLinksTo(d):
              logger.warning(f"Not adding the inferred isa from {s.name} to {d.name}: {problem}")
            continue
          obj = IsaIndividual(model, s, d, inferred=True) if rt is model.ISA else Relation(model, [rt], s, d, individual=True, inferred=True)
        obj.inferredKind = kinds[key] # (for how it's drawn)
      except Exception as ex:
        logger.warning(f"Couldn't add the inferred {rt.name} from {s.name} to {d.name}: {type(ex).__name__}: {ex}")

def reasoningFor(model:Model|None) -> Inferences|None:
  '''
  The results of the last *reason()* over *model*, or None.
  '''
  return getattr(model, "reasoning", None)

def _kind(obj:GraphObject) -> str:
  '''
  What kind of object *obj* is, for the reasoner's facts: "isa", "relation", "node" or "top".
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
  '''
  if isinstance(x, GraphObject):
    return x.tostring(relativeTo=relativeTo, format="friendly")
  if isinstance(x, NewObject):
    return x.label(relativeTo)
  return str(x)

def relationArrow(relType:Relation) -> str:
  '''
  A relation type as an arrow, as in the conceptual graphs literature: -name->
  '''
  return f'-{relType.name}->'
