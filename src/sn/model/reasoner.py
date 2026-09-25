'''
A back-end reasoner for :py:class:`~sn.model.model.Model` objects, built on
`clingo <https://potassco.org/clingo/>`_ (answer set programming).

The model is exported as a set of ground facts (see the header of
*reasoner.lp* for the vocabulary), the rule base in *reasoner.lp* is applied,
and the resulting atoms are mapped back onto the model's *GraphObjects*.
Every *GraphObject* -- including relation types and isa links -- is reified
as a term ``o(N)``, which is what lets relation types take part in the isa
hierarchy (and relations relate relations) while staying first-order.

The *Model* remains the single source of truth: the reasoner never modifies
it. Callers (typically the controller) decide what to do with the results.

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import clingo
import sn
from sn.model.model import Model, GraphObject, Node, Collection, Relation, IsaIndividual

logger:sn.SNLogger = sn.getLogger(__name__)

RULES = Path(__file__).with_name("reasoner.lp")
"The default rule base."

_MESSAGES:dict[str,str] = {
  "domain":                "source {2} of {0} is not a {3} (required by {1})",
  "range":                 "destination {2} of {0} is not a {3} (required by {1})",
  "isa_cycle":             "{0} is in an isa cycle through {1}",
  "isa_individual_parent": "{0} isa individual {1}",
  "redundant_parent":      "{0} has redundant parent {1} (already implied by {2})",
  "node_isa_relation":     "node {0} isa {1}",
  "relation_isa_node":     "relation {0} isa {1}",
  "irreflexive":           "irreflexive {0} relates {1} to itself",
  "property_conflict":     "{0} is both {1} and {2}",
  "unset_endpoint":        "{0} has no local {1}; it inherits its type's",
  }
"Message templates for violation codes: {0} is the subject, {1}... are the args."

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

class Reasoner:
  '''
  Usage::

    r = Reasoner(model)
    result = r.run()
    for v in result.violations:
      print(v)
    r.query('ans(X) :- holds(T,F,X), name(T,"owns"), name(F,"fred").')
  '''

  def __init__(self, model:Model, rules:Path|str=RULES):
    self.model = model
    self.rules = Path(rules)
    self._ids:dict[int, int] = {}
    "id(GraphObject) -> term number"
    self._objs:list[GraphObject] = []
    "term number -> GraphObject"

  # ── Export ───────────────────────────────────────────────────────────────

  def _term(self, obj:GraphObject) -> str:
    n = self._ids.get(id(obj))
    if n is None:
      n = len(self._objs)
      self._ids[id(obj)] = n
      self._objs.append(obj)
    return f'o({n})'

  def _facts(self) -> str:
    '''
    :returns: The model (and its super-models) as clingo facts.
    '''
    self._ids.clear()
    self._objs.clear()

    # this model and (transitively) its super-models, eg: the TopModel
    models:list[Model] = []
    pending = [self.model]
    while pending:
      m = pending.pop()
      if m not in models:
        models.append(m)
        pending.extend(m.superDBs) #type: ignore[arg-type]
    for m in models:
      for obj in list(m.values()):
        self._term(obj)

    out:list[str] = []
    for key in ("top", "relation", "isa", "node", "collection",
                "reflexive", "irreflexive", "symmetric", "transitive", "equality"):
      out.append(f'const({key},{self._term(getattr(self.model, key.upper()))}).')

    # self._objs grows as we go if an object refers to one we haven't seen.
    i = 0
    while i < len(self._objs):
      obj = self._objs[i]
      i += 1
      t = self._term(obj)
      out.append(f'obj({t}).')
      if obj.isIndividual():
        out.append(f'individual({t}).')
      out.append(f'kind({t},{_kind(obj)}).')
      out.append(f'name({t},{_str(obj.name)}).')
      try:
        for p in obj.getParents():
          out.append(f'parent({t},{self._term(p)}).')
      except RecursionError:
        out.append(f'parent({t},{t}).') # getParents() refuses self-parenting; let the rules report it
      except LookupError:
        pass
      if isinstance(obj, Collection):
        out.append(f'collection({t}).')
        if type(obj) is Collection: # AllModelCollection would just list the model
          out += [f'member({t},{self._term(m)}).' for m in obj.getMembers()]
      if isinstance(obj, Relation):
        out += self._relationFacts(obj, t)
      for key in obj: # local and inherited keys
        if key == "name" or key.startswith("vis/"):
          continue
        if dict.__contains__(obj, key):
          out.append(f'lattr({t},{_str(key)}).')
        try:
          value = obj.get(key, None) # effective value, per the Restriction rules
        except Exception:
          continue
        if isinstance(value, bool):
          out.append(f'attr({t},{_str(key)},{"true" if value else "false"}).')
        elif isinstance(value, int) and abs(value) < 2**30:
          out.append(f'attr({t},{_str(key)},{value}).')
        elif isinstance(value, (str, float)):
          out.append(f'attr({t},{_str(key)},{_str(str(value))}).')
    return "\n".join(out)

  def _relationFacts(self, rel:Relation, t:str) -> list[str]:
    out:list[str] = []
    if rel._src is not None:
      out.append(f'lsrc({t},{self._term(rel._src)}).')
    if rel._dst is not None:
      out.append(f'ldst({t},{self._term(rel._dst)}).')
    src, dst = rel.src, rel.dst
    if src is not None:
      out.append(f'src({t},{self._term(src)}).')
    if dst is not None:
      out.append(f'dst({t},{self._term(dst)}).')
    if rel.isIndividual() and not isinstance(rel, IsaIndividual) \
        and src is not None and dst is not None:
      out.append(f'link({t},{self._term(src)},{self._term(dst)}).')
    # Relational properties are tags on specific relations and do not inherit
    # (brother isa sibling, but brother isn't symmetric), so only local values
    # count. The rules also count a direct isa to an sn property type as a tag.
    for prop in ("reflexive", "irreflexive", "symmetric", "transitive"):
      if rel.getLocal(prop, False) is True:
        out.append(f'prop({t},{prop}).')
    return out

  # ── Solving ──────────────────────────────────────────────────────────────

  def _solve(self, program:str="") -> list[clingo.Symbol]:
    ctl = clingo.Control(["--warn=none"])
    ctl.load(str(self.rules))
    ctl.add("base", [], self._facts())
    if program:
      ctl.add("base", [], program)
    ctl.ground([("base", [])])
    symbols:list[clingo.Symbol] = []
    with ctl.solve(yield_=True) as handle:
      for m in handle: # the rule base is stratified, so exactly one model
        symbols = list(m.symbols(shown=True))
    return symbols

  def _value(self, sym:clingo.Symbol) -> Any:
    'Map a clingo symbol back to a GraphObject (for o(N)) or a Python value.'
    if sym.type == clingo.SymbolType.Function:
      if sym.name == "o" and len(sym.arguments) == 1:
        return self._objs[sym.arguments[0].number]
      if sym.name == "" : # tuple
        return tuple(self._value(a) for a in sym.arguments)
      if not sym.arguments:
        return sym.name
    if sym.type == clingo.SymbolType.Number:
      return sym.number
    if sym.type == clingo.SymbolType.String:
      return sym.string
    return str(sym)

  def run(self) -> Inferences:
    ret = Inferences()
    for sym in self._solve():
      args = [self._value(a) for a in sym.arguments]
      match sym.name:
        case "holds":     ret.holds.append(tuple(args)) #type: ignore[arg-type]
        case "inferred":  ret.inferred.append(tuple(args)) #type: ignore[arg-type]
        case "inherited": ret.inherited.append(tuple(args)) #type: ignore[arg-type]
        case "classify":  ret.classify.append(tuple(args)) #type: ignore[arg-type]
        case "isa_star":  ret.isa.add(tuple(args)) #type: ignore[arg-type]
        case "violation": ret.violations.append(Violation(*args))
    return ret

  def query(self, program:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    Run an ad-hoc query. *program* is extra clingo rules defining the predicate
    *answer*; objects can be named with ``name(O,"...")``. Eg::

      r.query('ans(X) :- holds(T,F,X), name(T,"owns"), name(F,"fred").')

    :returns: The argument tuples of every *answer* atom, with ``o(N)`` terms
      mapped back to *GraphObjects*.
    '''
    program += f'\n#show {answer}/{_arity(program, answer)}.'
    return [tuple(self._value(a) for a in sym.arguments)
            for sym in self._solve(program) if sym.name == answer]

def _kind(obj:GraphObject) -> str:
  if isinstance(obj, IsaIndividual):
    return "isa"
  if isinstance(obj, Relation):
    return "relation"
  if isinstance(obj, Node):
    return "node"
  return "top"

def _str(s:str) -> str:
  'A clingo string literal.'
  return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'

def _arity(program:str, pred:str) -> int:
  'The arity of the first head occurrence of *pred* in *program*.'
  start = program.find(pred + "(")
  if start < 0:
    return 0
  depth, arity = 0, 1
  for c in program[start + len(pred):]:
    if c == "(":
      depth += 1
    elif c == ")":
      depth -= 1
      if depth == 0:
        return arity
    elif c == "," and depth == 1:
      arity += 1
  return arity

def _label(x:Any) -> str:
  if isinstance(x, GraphObject):
    return f'"{x.name}"({x.id})'
  return str(x)
