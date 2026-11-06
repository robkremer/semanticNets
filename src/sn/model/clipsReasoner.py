'''
A :py:class:`~sn.model.reasoner.Reasoner` engine built on `CLIPS
<https://www.clipsrules.net>`_ (a forward-chaining production system), through
its Python bindings, clipspy (``pip install clipspy``, imported as *clips*).

The engine-neutral facts from :py:meth:`Reasoner.facts` are rendered as CLIPS
ordered facts, the rule base in *clipsReasoner.clp* (a port of
*clingoReasoner.lp*) is applied, and the results are mapped back onto the
model's *GraphObjects*. Every *GraphObject* is a symbol ``#N``.

CLIPS fires a rule as soon as its conditions match, so a rule that tests that
something isn't so -- a ``(not ...)`` -- must wait until what it tests is
complete. The engine sees to that: it sorts the rules (the rule base's, the
model's and a query's) into strata, and gives each rule a salience by its
stratum (see *_stratify()*); a program that can't be sorted so (it isn't
stratified) is refused.

Where the engine differs from clingo (see *clipsReasoner.clp*): a rule's
negated attribute test ("not gender: female") is about the attributes the
model gives, not those other rules conclude -- as for Nemo.

Created on Nov 5, 2026

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
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import importlib.resources
from importlib.resources.abc import Traversable
import re
from typing import Any, Iterable, override
try:
  import clips
except ModuleNotFoundError as _ex: # (an optional engine: say how to get it -- see Reasoner.create())
  raise ModuleNotFoundError('The "clips" reasoner needs CLIPS: pip install clipspy', name=_ex.name) from _ex
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact, PROPERTIES, Pattern, patternOf, NewObject, inferredNodeFor, \
  sameClasses, _newObjectKey
from sn.model.constraints import PRESENT, ValueVar, Not
from sn.model.names import NameKind

RULES = importlib.resources.files("sn.model").joinpath("clipsReasoner.clp")
"The default rule base. (Package data, so that it's found in a .pyz or a packaged app too.)"

_RENAMED = {"attr": "attr_base"}
"Facts given under another name (see *clipsReasoner.clp*: attr is these and what the rules conclude)."

RESULTS = ("isa_data", "holds", "inferred", "inherited", "classify", "violation", "fired", "rule_attr", "rule_isa", "rule_new", "same",
           "obj", "data", "individual", "card", "card_of", "card_counted")
"The predicates whose facts the engine reads (see *run()*): its results, and what it counts with (see *ClipsReasoner._counted()*)."

_NEW_RESULTS = frozenset({"fired", "rule_attr", "rule_isa", "rule_new", "same"})
"The results that may be about the objects the rules create (the rest are about the model's: see *Inferences.newObjects*)."

_COUNTING = frozenset({"obj", "data", "individual", "card", "card_of", "card_counted"})
"Of *RESULTS*, what the engine counts with, not results itself."

# ── Reading CLIPS ────────────────────────────────────────────────────────────

@dataclass
class _Form:
  '''
  A parenthesized CLIPS form, as *_read()* has it: its items (forms, and
  tokens: words, and strings with their quotes), and where it is in the text.
  '''
  items:list[_Form|str]
  start:int
  end:int
  "Just past its closing parenthesis."
  starts:list[int] = field(default_factory=list)
  "Where each of *items* starts in the text."

  def head(self) -> str|None:
    ''':returns: Its first item, if that's a word (eg: "defrule", or a fact's predicate).'''
    return self.items[0] if self.items and isinstance(self.items[0], str) else None

_TOKEN = re.compile(r'\s+|;[^\n]*|"(?:[^"\\]|\\.)*"|[()]|[^\s()";]+|"', re.S)
"The pieces of CLIPS text: space, comments, strings, parentheses, and words."

def _read(text:str) -> list[_Form]:
  '''
  :returns: The top-level forms of *text* (eg: its defrules), parsed just
    enough to see what each rule tests and concludes (see *_Rule*).
  :raises ValueError: If its parentheses or quotes don't match.
  '''
  stack:list[_Form] = [_Form([], 0, len(text))]
  for m in _TOKEN.finditer(text):
    tok = m.group(0)
    if tok[0].isspace() or tok[0] == ";":
      continue
    if tok == '"':
      raise ValueError(f"syntax error: a string that isn't closed, at character {m.start()}")
    if tok == "(":
      stack.append(_Form([], m.start(), m.start()))
    elif tok == ")":
      if len(stack) == 1:
        raise ValueError(f"syntax error: an unmatched \")\" at character {m.start()}")
      form = stack.pop()
      form.end = m.end()
      stack[-1].items.append(form)
      stack[-1].starts.append(form.start)
    else:
      stack[-1].items.append(tok)
      stack[-1].starts.append(m.start())
  if len(stack) > 1:
    raise ValueError(f"syntax error: an unmatched \"(\" at character {stack[-1].start}")
  ret = []
  for x in stack[0].items:
    if not isinstance(x, _Form):
      raise ValueError(f"syntax error: {x!r} outside a construct")
    ret.append(x)
  return ret

@dataclass
class _Rule:
  '''
  A defrule, and what *_stratify()* needs of it.
  '''
  name:str
  text:str
  "Its text, without a salience (see *salient()*)."
  heads:set[str]
  "The predicates it asserts."
  pos:set[str]
  "The predicates its conditions match."
  neg:set[str]
  "The predicates it tests with (not ...)."
  stratum:int = 0

  def salient(self) -> str:
    ''':returns: Its text, with the salience its stratum gives it: the higher the stratum, the later it fires.'''
    i = re.match(r"\(\s*defrule\s+[^\s()]+", self.text).end() # type: ignore[union-attr]
    m = re.match(r'\s*"(?:[^"\\]|\\.)*"', self.text[i:]) # (its comment)
    if m:
      i += m.end()
    return f"{self.text[:i]} (declare (salience {-self.stratum})){self.text[i:]}"

def _rule(form:_Form, text:str) -> _Rule:
  '''
  :param form: A defrule (see *_read()*) in *text*.
  :raises ValueError: If it isn't one CLIPS will take, or it sets its own salience.
  '''
  items = form.items
  if len(items) < 2 or not isinstance(items[1], str):
    raise ValueError("syntax error: a defrule without a name")
  if "=>" not in items:
    raise ValueError(f'syntax error: the defrule {items[1]} has no "=>"')
  arrow = items.index("=>")
  pos:set[str] = set()
  neg:set[str] = set()
  def conditions(ces:list, negated:bool) -> None:
    for ce in ces:
      if not isinstance(ce, _Form):
        continue # (eg: "?f <-", or a comment string)
      head = ce.head()
      if head == "declare":
        raise ValueError(f"the defrule {items[1]} declares its own salience: the engine gives each rule its own (see clipsReasoner.clp)")
      if head in ("test", None):
        continue
      if head == "not":
        conditions(ce.items[1:], True)
      elif head in ("and", "or", "exists", "logical", "forall"):
        conditions(ce.items[1:], negated or head == "forall") # (forall: "not (a and not b)")
      else:
        (neg if negated else pos).add(head)
  conditions(items[2:arrow], False)
  heads:set[str] = set()
  def actions(xs:list) -> None:
    for x in xs:
      if isinstance(x, _Form):
        if x.head() == "assert":
          heads.update(f.head() or "" for f in x.items[1:] if isinstance(f, _Form))
        actions(x.items)
  actions(items[arrow + 1:])
  return _Rule(items[1], text[form.start:form.end], heads, pos, neg)

def _stratify(rules:list[_Rule]) -> None:
  '''
  Sort *rules* into strata (each rule's *stratum*), so that a rule that tests
  with (not ...) fires only once every rule that could conclude what it tests
  has: the predicates fall into groups that conclude each other (CLIPS runs
  each group to its end), and a group that another tests with (not ...) runs
  first. Within a group no rule may test another's conclusions with (not ...):
  that isn't stratified (and isn't a question of when it runs).

  :raises ValueError: If *rules* aren't stratified: naming the predicates.
  '''
  edges:dict[str, set[tuple[str, bool]]] = defaultdict(set) # head -> (body predicate, negated)
  for r in rules:
    for h in r.heads:
      edges[h] |= {(p, False) for p in r.pos} | {(p, True) for p in r.neg}
  # Tarjan's strongly connected components, without recursion: components come out dependencies first.
  index:dict[str, int] = {}
  low:dict[str, int] = {}
  onStack:set[str] = set()
  stack:list[str] = []
  comp:dict[str, int] = {}
  comps:list[list[str]] = []
  for root in list(edges):
    if root in index:
      continue
    work = [(root, iter(sorted(edges.get(root, ()))))]
    index[root] = low[root] = len(index)
    stack.append(root)
    onStack.add(root)
    while work:
      node, it = work[-1]
      for dep, _neg in it:
        if dep not in index:
          index[dep] = low[dep] = len(index)
          stack.append(dep)
          onStack.add(dep)
          work.append((dep, iter(sorted(edges.get(dep, ())))))
          break
        if dep in onStack:
          low[node] = min(low[node], index[dep])
      else:
        work.pop()
        if work:
          low[work[-1][0]] = min(low[work[-1][0]], low[node])
        if low[node] == index[node]:
          members = []
          while True:
            x = stack.pop()
            onStack.discard(x)
            comp[x] = len(comps)
            members.append(x)
            if x == node:
              break
          comps.append(members)
  strata = [0] * len(comps)
  for c, members in enumerate(comps): # (dependencies first: their strata are known)
    for p in members:
      for dep, negated in edges.get(p, ()):
        if comp.get(dep) == c:
          if negated:
            raise ValueError(f"The rules aren't stratified: {p} depends on not {dep}, which depends on {p}")
          continue
        strata[c] = max(strata[c], strata[comp[dep]] + negated if dep in comp else 0)
  stratum = lambda p: strata[comp[p]] if p in comp else 0 # (a predicate no rule concludes: given facts)
  for r in rules:
    r.stratum = max([stratum(p) for p in r.pos] + [stratum(p) + 1 for p in r.neg] + [0])

_baseRules:dict[str, list[_Rule]] = {}
"The rule base's rules, by its text (read once)."

def _rulesOf(text:str) -> tuple[list[_Rule], list[str]]:
  '''
  :returns: *text*\'s defrules, and its other constructs (eg: deffunctions), as texts.
  :raises ValueError: If it can't be read.
  '''
  rules:list[_Rule] = []
  others:list[str] = []
  for form in _read(text):
    if form.head() == "defrule":
      rules.append(_rule(form, text))
    else:
      others.append(text[form.start:form.end])
  return rules, others

_VARIABLE = re.compile(r"\$?\?[A-Za-z_][\w-]*")
"A CLIPS variable (not a bare ?, which matches anything)."

def _ordered(conditions:list[str]) -> list[str]:
  '''
  *conditions* (a rule's), in the order CLIPS should match them. CLIPS matches
  a rule's conditions in order, keeping every partial match: a pattern that
  shares no variable with those before it multiplies them (eg: (data ?x)
  (data ?y) (data ?z) before the relations between them). So: first a pattern
  with a constant, then each pattern that shares the most with those already
  matched -- and each test, and each (not ...), as soon as the variables it
  tests are bound (a variable that's only in a (not ...) is its own).
  '''
  parsed = [(c, _read(c)[0]) for c in conditions]
  positive = [(c, f) for c, f in parsed if f.head() not in ("not", "test")]
  filters = [(c, f) for c, f in parsed if f.head() in ("not", "test")]
  bound:set[str] = set()
  inPatterns = {v for c, _f in positive for v in _VARIABLE.findall(c)}
  out:list[str] = []
  def score(cf:tuple[str, _Form]) -> tuple:
    c, f = cf
    vs = set(_VARIABLE.findall(c))
    consts = sum(1 for x in f.items[1:] if isinstance(x, str) and x != "?" and not _VARIABLE.fullmatch(x))
    return (not (vs - bound), bool(vs & bound), len(vs & bound) + consts, -len(vs - bound))
  while positive or filters:
    ready = next((cf for cf in filters if set(_VARIABLE.findall(cf[0])) & inPatterns <= bound), None)
    if ready is not None:
      filters.remove(ready)
      out.append(ready[0])
      continue
    if not positive: # (a test of a variable no pattern binds: CLIPS says so)
      out += [c for c, _f in filters]
      break
    best = max(positive, key=score) # (the first of the best)
    positive.remove(best)
    out.append(best[0])
    bound |= set(_VARIABLE.findall(best[0]))
  return out

class _Quiet(clips.Router):
  '''
  Keeps what CLIPS prints (its errors and warnings: clipspy raises the errors
  as CLIPSErrors) off the console.
  '''
  def __init__(self) -> None:
    super().__init__("sn-quiet", 30) # (below clipspy's error router, which passes them on)
    self.messages:list[str] = []

  def query(self, name:str) -> bool:
    return name in ("stdout", "stderr", "stdwrn")

  def write(self, name:str, message:str) -> None:
    self.messages.append(message)

@dataclass
class _Program:
  '''
  What the engine runs for a model: rules, besides the rule base's, and facts.
  '''
  rules:list[str] = field(default_factory=list)
  "Defrules (without saliences: see *_stratify()*)."
  facts:list[str] = field(default_factory=list)
  "Facts, as CLIPS has them: (pred arg ...)."

class ClipsReasoner(Reasoner, engine="clips"):
  '''
  Native queries are extra CLIPS rules asserting answer facts (``(ans ...)``
  by default), matching the fact vocabulary and the rule base's results
  (holds, isa_star, inherited, ...). Objects are symbols ``#N``, best found by
  name. Eg::

    r.query('(defrule q (holds ?t ?f ?x) (name ?t "owns") (name ?f "fred") => (assert (ans ?x)))')
  '''

  language = "clips"

  def __init__(self, model:Model, rules:Path|str|Traversable=RULES, showSysRules:bool|None=None):
    '''
    :param rules: The rule base: a file, or package data (see *RULES*).
    :param showSysRules: See *Reasoner.__init__()*.
    '''
    super().__init__(model, showSysRules=showSysRules)
    self.rules:Path|Traversable = Path(rules) if isinstance(rules, str) else rules
    self._ids:dict[int, int] = {}
    "id(GraphObject) -> its symbol's number"
    self._objs:list[GraphObject] = []
    "symbol number -> GraphObject"
    self._news:list[tuple[GraphObject, str, tuple[str, ...]]] = []
    "The objects rules create, by the number in their symbols (see *_newTerm()*): (rule, variable, the match's variables)."
    self._newIds:dict[tuple, int] = {}
    "(id(rule), variable, the match's variables) -> its number in *_news*"

  # ── Rendering ────────────────────────────────────────────────────────────

  def _term(self, x:Any) -> str:
    '''
    The CLIPS value for a fact's argument: an object is the symbol #n,
    numbered as it's first met; a symbol a symbol (or a string, if it isn't a
    name); a bool TRUE or FALSE; a number or string as itself.
    '''
    if isinstance(x, GraphObject):
      n = self._ids.get(id(x))
      if n is None:
        n = len(self._objs)
        self._ids[id(x)] = n
        self._objs.append(x)
      return f'#{n}'
    if isinstance(x, Sym):
      return str(x) if _SYMBOL.match(x) and x not in _KEYWORDS else _str(str(x))
    if isinstance(x, bool):
      return "TRUE" if x else "FALSE"
    if isinstance(x, int) and abs(x) < 2**62:
      return str(x)
    if isinstance(x, float) and x.is_integer() and abs(x) < 2**62:
      return str(int(x)) # (the same value as the int, as clingo has it: see ClingoReasoner._term())
    return _str(str(x))

  def _program(self, facts:list[Fact]) -> list[str]:
    '''
    *facts* as CLIPS facts (objects numbered afresh: see *_term()*).
    '''
    self._ids.clear()
    self._objs.clear()
    self._news.clear()
    self._newIds.clear()
    return [f'({_RENAMED.get(pred, pred)}{"".join(" " + self._term(a) for a in args)})' for pred, args in facts]

  # ── Running ──────────────────────────────────────────────────────────────

  def _solve(self, program:_Program, facts:list[str]|None=None, query:str="",
             read:Iterable[str]=RESULTS) -> dict[str, list[tuple[Any, ...]]]:
    '''
    :param facts: The model's facts, already rendered (see *_program()*) -- for
      a *program* that refers to objects by their #N symbols, which must come
      from the same rendering. Rendered afresh if None.
    :param query: Extra CLIPS constructs (eg: a native query's defrules).
    :param read: The predicates whose facts are wanted.
    :returns: The facts of each of *read* there are when it's done: their
      fields as CLIPS has them (see *_value()*).
    '''
    if facts is None:
      facts = self._program(self.facts())
    text = self.rules.read_text(encoding="utf-8")
    try:
      base = _baseRules.get(text)
      if base is None:
        base = _baseRules[text] = _rulesOf(text)[0]
      extra, others = _rulesOf("\n".join(program.rules + [query]))
      rules = [_Rule(r.name, r.text, r.heads, r.pos, r.neg) for r in base] + extra # (copies: their strata are this program's)
      _stratify(rules)
    except ValueError as ex:
      raise RuntimeError(f"The rules couldn't be compiled: {ex}") from ex
    names = [r.name for r in rules]
    if len(set(names)) < len(names):
      twice = sorted({n for n in names if names.count(n) > 1})
      raise RuntimeError(f"The rules couldn't be compiled: there's more than one rule named {', '.join(twice)} (see clipsReasoner.clp)")
    env = clips.Environment()
    env.add_router(_Quiet())
    try:
      for construct in others:
        env.build(construct)
      for r in rules:
        env.build(r.salient())
      routers = list(env.routers())
      for router in routers: # (CLIPS asks each of them about every character it reads: the facts are ours, and right)
        router.deactivate()
      try:
        env.load_facts(" ".join(facts + program.facts))
      finally:
        for router in routers:
          router.activate()
      env.run()
    except clips.CLIPSError as ex:
      raise RuntimeError(f"The rules couldn't be compiled: {ex}") from ex
    ret:dict[str, list[tuple[Any, ...]]] = defaultdict(list)
    templates = {t.name: t for t in env.templates()}
    for pred in read:
      if pred in templates:
        ret[pred] = [f[:] for f in templates[pred].facts()]
    return ret

  def _value(self, v:Any) -> Any:
    '''
    Map a CLIPS value back to a GraphObject (for #N), a NewObject (for the
    symbols that stand for them: see *_newTerm()*) or a Python value.
    '''
    if isinstance(v, clips.Symbol):
      s = str(v)
      if s[:1] == "#" and s[1:].isdigit():
        return self._objs[int(s[1:])]
      if s.startswith(("%new:", "%card:")):
        return self._newObject(s)
      return {"TRUE": True, "FALSE": False}.get(s, Sym(s))
    if isinstance(v, (bool, int, float)):
      return v
    return str(v)

  def _object(self, s:str) -> Any:
    '''
    :param s: An object's symbol as a string: "#12".
    :returns: The object.
    '''
    return self._objs[int(s[1:])] if s[:1] == "#" and s[1:].isdigit() else s

  def _newObject(self, s:str) -> NewObject:
    '''
    :param s: The symbol for an object a rule creates: %new:K:#V0:#V1..., K
      its number in *_news*; or one a cardinality creates: %card:#T:of:#X (or "to").
    '''
    parts = s.split(":")
    if parts[0] == "%card":
      t = self._object(parts[1])
      return NewObject(t, t.name, ((parts[2], self._object(parts[3])),))
    rule, variable, names = self._news[int(parts[1])]
    return NewObject(rule, variable, tuple(zip(names, (self._object(p) for p in parts[2:]))))

  @staticmethod
  def _counted(results:dict[str, list[tuple[Any, ...]]]) -> list[list[Any]]:
    '''
    The cardinality violations that count (CLIPS has no aggregates: see
    *clipsReasoner.clp*), as clingoReasoner.lp's: too many of what each source
    (or destination) is related to, or too few.

    :returns: The violations, as rows of fields: (Code Severity Subject Args...).
    '''
    objs = {x[0] for x in results.get("obj", [])}
    individuals = {x[0] for x in results.get("individual", [])}
    counted = {x[0] for x in results.get("card_counted", [])}
    related:dict[tuple, dict[Any, set]] = defaultdict(lambda: defaultdict(set)) # (T, out|in) -> X -> what X is related to (from)
    for t, src, dst in results.get("holds", []):
      related[t, "out"][src].add(dst)
      related[t, "in"][dst].add(src)
    cardOf:dict[tuple, list] = defaultdict(list) # (T, out|in) -> [X]
    for t, direction, x in results.get("card_of", []):
      cardOf[t, direction].append(x)
    ret = []
    for t, direction, low, high in results.get("card", []):
      suffix = "" if direction == "out" else "_in"
      byX = related.get((t, str(direction)), {})
      if high >= 0:
        for x, others in byX.items():
          n = len(others & objs)
          if x in individuals and n > high:
            ret.append([clips.Symbol("cardinality_max" + suffix), clips.Symbol("error"), x, t, n, high])
      for x in cardOf.get((t, direction), []):
        n = len(byX.get(x, set()) & counted)
        if n < low:
          ret.append([clips.Symbol("cardinality_min" + suffix), clips.Symbol("warning"), x, t, n, low])
    return ret

  @override
  def run(self) -> Inferences:
    ret = Inferences()
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    results = self._solve(self._rulesProgram(), facts)
    data = {x[0] for x in results.get("data", [])}
    results["violation"] += [tuple(v) for v in self._counted(results) if v[2] in data] # (only the data's are reported)
    for pred, rows in results.items():
      if pred in _COUNTING:
        continue
      for row in rows:
        args = [self._value(a) for a in row]
        if pred not in _NEW_RESULTS and any(isinstance(a, NewObject) for a in args):
          continue # (the general results are about the model's objects: see Inferences.newObjects)
        match pred:
          case "holds":     ret.holds.append(tuple(args)) #type: ignore[arg-type]
          case "inferred":  ret.inferred.append(tuple(args)) #type: ignore[arg-type]
          case "inherited": ret.inherited.append(tuple(args)) #type: ignore[arg-type]
          case "classify":  ret.classify.append(tuple(args)) #type: ignore[arg-type]
          case "isa_data":  ret.isa.add(tuple(args)) #type: ignore[arg-type]
          case "fired":     ret.fired.append(tuple(args)) #type: ignore[arg-type]
          case "rule_attr": ret.ruleAttrs.append(tuple(args)) #type: ignore[arg-type]
          case "rule_isa":  ret.ruleIsa.append(tuple(args)) #type: ignore[arg-type]
          case "rule_new":  ret.newObjects.append(args[0])
          case "same":      ret.same.append((args[0], args[1]))
          case "violation": ret.violations.append(Violation(args[0], args[1], args[2], tuple(args[3:])))
    return self._finish(ret)

  def _patternBody(self, pat:Pattern, var:dict[str, str], forRule:bool=False, inRule:bool=False) -> list[str]:
    '''
    The CLIPS conditions for *pat*, as *ClingoReasoner._patternBody()*\'s
    literals: the patterns first, then the tests, then the (not ...)s (but see
    *_ordered()*, which orders them for a rule). *var* maps each variable's
    name to its CLIPS variable (variables with the same name are the same
    variable), and gets value variables ("?a") added.

    :param forRule: For a rule that creates objects: its variables range over base data only.
    :param inRule: For a rule's antecedent (any rule): a negated attribute
      test is about the attributes the model gives (attr_base), not those the
      rules conclude (attr) -- so that the program stays stratified (see
      *_stratify()*): the rules' conclusions depend on the rules.
    '''
    dom, ind = ("base", "individual") if forRule else ("data", "any_individual")
    def term(x:GraphObject|None) -> str:
      return "?" if x is None else var.get(x.name, "?") if x.isVariable() else self._term(x)
    relTypeVars = {t.name for t, _, _ in pat.triples if t.isVariable()}
    patterns:list[str] = []
    tests:list[str] = []
    nots:list[str] = []
    guard = {NameKind.INDIVIDUAL: ind, NameKind.TYPE: "type"}
    for v in {v.name: v for v in pat.variables}.values():
      g = None if v.name in relTypeVars else guard.get(v.variableKind()) # (a relation type variable: see rel_type below)
      patterns.append(f"({dom} {var[v.name]})")
      if g:
        patterns.append(f"({g} {var[v.name]})")
    for t, s, d in pat.triples:
      patterns.append(f"(holds {term(t)} {term(s)} {term(d)})")
      if t.isVariable():
        patterns.append(f"(rel_type {term(t)})")
    patterns += [f"(isa_star {term(x)} {term(t)})" for x, t in pat.types]
    # (only objects of the model are known to be different: an object a rule concludes exists -- eg: "a mother" -- might be anyone)
    for x, y in pat.distinct:
      patterns += [f"(obj {term(x)})", f"(obj {term(y)})"]
      tests.append(f"(test (neq {term(x)} {term(y)}))")
    negAttr = "attr_base" if inRule else "attr"
    for v, key, value in pat.constraints:
      neg = isinstance(value, Not) # (negation as failure: it isn't so, as far as the model says)
      if neg:
        value = value.value
      if key in PROPERTIES:           # a relational property: a tag on a relation type
        p = f"(prop {term(v)} {key})"
        (nots if (value is False) ^ neg else patterns).append(f"(not {p})" if (value is False) ^ neg else p)
        continue
      pred = negAttr if neg else "attr"
      if value is PRESENT:
        p = f"({pred} {term(v)} {_str(key)} ?)"
      elif isinstance(value, ValueVar): # (a negated one is bound by the same one, unnegated: see patternOf())
        p = f"({pred} {term(v)} {_str(key)} {var.setdefault(value, f'?A{len(var)}')})"
      else:
        p = f"({pred} {term(v)} {_str(key)} {self._term(value)})"
      (nots if neg else patterns).append(f"(not {p})" if neg else p)
    return patterns + tests + nots

  @staticmethod
  def _varNames(pat:Pattern) -> dict[str, str]:
    '''
    A CLIPS variable for each of *pat*\'s variable names, in answer order.
    '''
    return {name: f"?V{i}" for i, name in enumerate(dict.fromkeys(v.name for v in pat.variables))}

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one rule,
    ``(defrule ans <a holds pattern per relation, isa_star per type, ...> => (assert (ans ?V0 ...)))``,
    over the reasoner's results (including what the model's rules conclude) --
    so matches include inferred relations. See *_patternBody()*.
    '''
    pat = patternOf(context)
    if pat.errors:
      raise ValueError("; ".join(f"the constraints of {x.name} can't be read: {err}" for x, err in pat.errors))
    facts = self._program(self.facts()) # (numbers the objects the rule refers to)
    var = self._varNames(pat)
    names = list(var)
    body = self._patternBody(pat, var)
    if not body:
      return []
    program = self._rulesProgram()
    program.rules.append(f"(defrule sn-answer {' '.join(_ordered(body))} => (assert (ans{''.join(' ' + var[n] for n in names)})))")
    results = self._solve(program, facts, read=("same", "ans"))
    merged = sameClasses([(self._value(a), self._value(b)) for a, b in results.get("same", [])])
    byKey = {_newObjectKey(n): r for n, r in merged.items()}
    def value(a:Any) -> Any: # (a new object: what it was merged into, if it was; and its inferred node, once it's made)
      v = self._value(a)
      if isinstance(v, NewObject):
        v = byKey.get(_newObjectKey(v), v)
      return inferredNodeFor(self.model, v)
    ret:list[dict[GraphObject, GraphObject]] = []
    seen:set[tuple] = set()
    for row in results.get("ans", []):
      vals = [value(a) for a in row]
      k = tuple(_newObjectKey(v) if isinstance(v, NewObject) else id(v) for v in vals)
      if k in seen: # (merged: the same answer)
        continue
      seen.add(k)
      byName = dict(zip(names, vals))
      ret.append({v: byName[v.name] for v in pat.variables})
    return ret

  def _newTerm(self, rule:GraphObject, name:str, matched:list[str], var:dict[str, str]) -> str:
    '''
    The value for the object *rule* creates for its consequent variable *name*
    in each match: a symbol, %new:K:#V0:#V1... -- K, its number in *_news*,
    saying which rule, variable and match variables it is (a function of the
    match, so one object per match: see *NewObject*).
    '''
    key = (id(rule), name, tuple(matched))
    k = self._newIds.get(key)
    if k is None:
      k = self._newIds[key] = len(self._news)
      self._news.append((rule, name, tuple(matched)))
    if not matched: # (one for the rule: no match variables)
      return f"%new:{k}"
    return f'(sym-cat "%new:{k}"' + "".join(f' ":" {var[n]}' for n in matched) + ")"

  def _satisfied(self, spec, var:dict[str, str], n:int) -> tuple[str, str]:
    '''
    For a rule that creates objects (see *NewObject*): a CLIPS rule saying
    that, for a match, the data already has objects in their place (as
    *ClingoReasoner._satisfied()*) -- and the pattern to test it with. ("",
    "") if there's nothing to test.
    '''
    new = {x.name for x in spec.new}
    exist = {name: f"?E{i}" for i, name in enumerate(sorted(new))}
    def term(x) -> str:
      if x.isVariable():
        return exist.get(x.name) or var[x.name]
      return self._term(x)
    lits = [f"(asserted_under {term(t)} {term(s)} {term(d)})" for t, s, d in spec.heads # (eg: has-father counts as has-parent)
            if any(x is not None and x.isVariable() and x.name in new for x in (s, d)) and s is not None and d is not None]
    lits += [f"(isa_base {term(x)} {term(t)})" for x, t in spec.isas if x.isVariable() and x.name in new]
    if not lits:
      return "", ""
    used = [v for v in var.values() if any(re.search(rf"{re.escape(v)}(?![\w-])", l) for l in lits)] # the match's variables the test uses
    head = f"(sat_{n}{''.join(' ' + v for v in used)})"
    return f"(defrule sn-sat-{n} {' '.join(_ordered(lits))} => (assert {head}))", head

  def _rulesProgram(self) -> _Program:
    '''
    The rules (see *reasoner.ruleOf()*) -- the model's, its super-models' and
    the base rules (see *Reasoner.ruleObjects()*) -- as CLIPS rules, one per
    conclusion, as *ClingoReasoner._rulesProgram()* has them in clingo: a rule
    asserting ``(fired Rule T S D)`` for a relation, ``(rule_attr Rule X Key
    Value)`` for an attribute, ... And the constraints (see
    *reasoner.constraintOf()*), as rules asserting ``(violation0 Code
    Severity Subject Args...)`` (a requirement's holding as ``(req_N
    Vars...)``). Call after rendering the facts (see *_program()*).
    '''
    out = _Program()
    rules, constraints = self.specs()
    def problem(subject:GraphObject, code:str, args:tuple) -> str:
      return f'(violation0 {self._term(Sym(code))} warning {self._term(subject)}{"".join(" " + self._term(a) for a in args)})'
    def rule(kind:str, body:list[str], head:str) -> None:
      if body:
        out.rules.append(f"(defrule sn-{kind}-{len(out.rules)} {' '.join(_ordered(body))} => (assert {head}))")
      else:
        out.facts.append(head)
    for spec in constraints:
      c = spec.constraint
      out.facts += [problem(c, code, args) for code, args in spec.warnings] # (it's still used)
      if spec.problems:
        out.facts += [problem(c, code, args) for code, args in spec.problems]
        continue
      var = self._varNames(spec.pattern)
      body = self._patternBody(spec.pattern, var)
      if spec.required is not None: # a requirement: violated where its condition matches and what it requires doesn't
        condVars = "".join(" " + v for v in var.values()) # (the condition's variables, and its value variables)
        for name in dict.fromkeys(v.name for v in spec.required.variables): # (its own: "some")
          var.setdefault(name, f"?V{len(var)}")
        holds = f"(req_{len(out.rules)}{condVars})"
        rule("requirement", body + self._patternBody(spec.required, var), holds) # (the condition too: it gives the shared variables their values)
        body = body + [f"(not {holds})"]
      if not body:
        continue
      term = lambda x: var[x.name] if isinstance(x, GraphObject) and x.isVariable() else self._term(x)
      subject, *args = spec.report
      rule("constraint", body, f'(violation0 {self._term(spec.code)} {self._term(Sym(spec.severity))} {term(subject)}{"".join(" " + term(a) for a in args)})')
    for rspec in rules:
      r = rspec.rule
      out.facts += [problem(r, code, rargs) for code, rargs in rspec.warnings] # (it's still used)
      if rspec.problems:
        out.facts += [problem(r, code, rargs) for code, rargs in rspec.problems]
        continue
      if not (rspec.heads or rspec.assertions or rspec.isas or rspec.new):
        continue
      var = self._varNames(rspec.pattern)
      body = self._patternBody(rspec.pattern, var, forRule=bool(rspec.new), inRule=True) # (a rule that creates nothing can't run away: it ranges over all the data)
      matched = [n for n in var if n in {v.name for v in rspec.pattern.variables}] # (not value variables)
      newTerms = {x.name: self._newTerm(r, x.name, matched, var) for x in rspec.new}
      def term(x:GraphObject|None) -> str:
        if x is not None and x.isVariable():
          return newTerms.get(x.name) or var[x.name]
        return self._term(x)
      newBody = body # (for conclusions about new objects: only if the data doesn't already have them)
      if newTerms:
        sat, satLit = self._satisfied(rspec, var, len(out.rules))
        if sat:
          out.rules.append(sat)
          newBody = body + [f"(not {satLit})"]
      isNew = lambda *xs: any(x is not None and x.isVariable() and x.name in newTerms for x in xs)
      for n in newTerms.values():
        rule("rule", newBody, f"(rule_new {n})")
      for x, t in rspec.isas:
        rule("rule", newBody if isNew(x) else body, f"(rule_isa {self._term(r)} {term(x)} {term(t)})")
      for t, s, d in rspec.heads:
        rule("rule", newBody if isNew(s, d) else body, f"(fired {self._term(r)} {term(t)} {term(s)} {term(d)})")
      for x, key, value in rspec.assertions:
        v = "TRUE" if value is PRESENT else var[value] if isinstance(value, ValueVar) else self._term(value)
        rule("rule", newBody if isNew(x) else body, f"(rule_attr {self._term(r)} {term(x)} {_str(key)} {v})")
    return out

  @override
  def query(self, query:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    :param query: Extra CLIPS rules asserting *answer* facts; objects can be
      named with ``(name ?o "...")``. (The engine gives each rule its salience:
      see *_stratify()*.)
    :returns: The fields of every *answer* fact, with ``#N`` symbols mapped
      back to *GraphObjects*.
    '''
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    return [tuple(self._value(a) for a in row) for row in self._solve(self._rulesProgram(), facts, query, read=(answer,)).get(answer, [])]

_SYMBOL = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*$")
"A CLIPS symbol that a symbol is written as (eg: symmetric): others are strings."

_KEYWORDS:frozenset[str] = frozenset({"TRUE", "FALSE", "nil", "not", "and", "or", "test", "exists", "forall", "logical", "declare"})
"Names that aren't plain symbols in CLIPS (its booleans, nothing, and the words of its rules): written as strings."

def _str(s:str) -> str:
  '''
  A CLIPS string literal.
  '''
  return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
