'''
A :py:class:`~sn.model.reasoner.Reasoner` engine built on
`clingo <https://potassco.org/clingo/>`_ (answer set programming).

The engine-neutral facts from :py:meth:`Reasoner.facts` are rendered as ASP
facts, the rule base in *clingoReasoner.lp* is applied, and the resulting atoms
are mapped back onto the model's *GraphObjects*. Every *GraphObject* is reified
as a term ``o(N)``, which is what lets relation types take part in the isa
hierarchy (and relations relate relations) while staying first-order.

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
from pathlib import Path
import importlib.resources
from importlib.resources.abc import Traversable
import re
from typing import Any, override
import clingo
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact, PROPERTIES, Pattern, patternOf, NewObject, inferredNodeFor, \
  sameClasses, _newObjectKey
from sn.model.constraints import PRESENT, ValueVar, Not
from sn.model.names import NameKind

RULES = importlib.resources.files("sn.model").joinpath("clingoReasoner.lp")
"The default rule base. (Package data, so that it's found in a .pyz or a packaged app too.)"

class ClingoReasoner(Reasoner, engine="clingo"):
  '''
  Native queries are extra clingo rules defining an answer predicate (``ans``
  by default) over the fact vocabulary and the rule base's output predicates
  (holds/3, isa_star/2, inherited/3, ...). Eg::

    r.query('ans(X) :- holds(T,F,X), name(T,"owns"), name(F,"fred").')
  '''

  language = "asp"

  def __init__(self, model:Model, rules:Path|str|Traversable=RULES, showSysRules:bool|None=None):
    '''
    :param model:
    :type model: Model
    :param rules: The rule base: a file, or package data (see *RULES*).
    :type rules: Path | str | Traversable
    :param showSysRules: See *Reasoner.__init__()*.
    :type showSysRules: bool | None
    '''
    super().__init__(model, showSysRules=showSysRules)
    self.rules:Path|Traversable = Path(rules) if isinstance(rules, str) else rules
    self._ids:dict[int, int] = {}
    "id(GraphObject) -> term number"
    self._objs:list[GraphObject] = []
    "term number -> GraphObject"

  # ── Rendering ────────────────────────────────────────────────────────────

  def _term(self, x:Any) -> str:
    '''
    :param x:
    :type x: Any
    :returns:
    :rtype: str
    '''
    if isinstance(x, GraphObject):
      n = self._ids.get(id(x))
      if n is None:
        n = len(self._objs)
        self._ids[id(x)] = n
        self._objs.append(x)
      return f'o({n})'
    if isinstance(x, Sym):
      return str(x) if _SYMBOL.match(x) else _str(str(x)) # (eg: a word in a constraint's report that isn't one)
    if isinstance(x, bool):
      return "true" if x else "false"
    if isinstance(x, int) and abs(x) < 2**30:
      return str(x)
    return _str(str(x))

  def _program(self, facts:list[Fact]) -> str:
    '''
    :param facts:
    :type facts: list[Fact]
    :returns:
    :rtype: str
    '''
    self._ids.clear()
    self._objs.clear()
    return "\n".join(f'{pred}({",".join(self._term(a) for a in args)}).' for pred, args in facts)

  # ── Solving ──────────────────────────────────────────────────────────────

  def _solve(self, program:str="", facts:str|None=None) -> list[clingo.Symbol]:
    '''
    :param program:
    :type program: str
    :param facts: The model's facts, already rendered (see *_program()*) -- for
      a *program* that refers to objects by their o(N) terms, which must come
      from the same rendering. Rendered afresh if None.
    :type facts: str | None
    :returns:
    :rtype: list[clingo.Symbol]
    '''
    ctl = clingo.Control(["--warn=none"])
    ctl.add("base", [], self.rules.read_text(encoding="utf-8"))
    ctl.add("base", [], self._program(self.facts()) if facts is None else facts)
    if program:
      ctl.add("base", [], program)
    ctl.ground([("base", [])])
    symbols:list[clingo.Symbol] = []
    with ctl.solve(yield_=True) as handle:
      for m in handle: # the rule base is stratified, so exactly one model
        symbols = list(m.symbols(shown=True))
    return symbols

  def _value(self, sym:clingo.Symbol) -> Any:
    '''
    Map a clingo symbol back to a GraphObject (for o(N)) or a Python value.

    :param sym:
    :type sym: clingo.Symbol
    :returns:
    :rtype: Any
    '''
    if sym.type == clingo.SymbolType.Function:
      if sym.name == "o" and len(sym.arguments) == 1:
        return self._objs[sym.arguments[0].number]
      if sym.name == "new" and len(sym.arguments) == 3: # see _newTerm()
        rule, var, bindings = (self._value(a) for a in sym.arguments)
        return NewObject(rule, var, tuple(bindings))
      if sym.name == "" : # tuple
        return tuple(self._value(a) for a in sym.arguments)
      if not sym.arguments:
        return {"true": True, "false": False}.get(sym.name, sym.name) # (see _term())
    if sym.type == clingo.SymbolType.Number:
      return sym.number
    if sym.type == clingo.SymbolType.String:
      return sym.string
    return str(sym)

  @override
  def run(self) -> Inferences:
    '''
    :returns:
    :rtype: Inferences
    '''
    ret = Inferences()
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    for sym in self._solve(self._rulesProgram(), facts):
      args = [self._value(a) for a in sym.arguments]
      if sym.name not in ("fired", "rule_attr", "rule_isa", "rule_new", "same") and any(isinstance(a, NewObject) for a in args):
        continue # (the general results are about the model's objects: see Inferences.newObjects)
      match sym.name:
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
        case "violation": ret.violations.append(Violation(*args))
    return self._finish(ret)

  def _patternBody(self, pat:Pattern, var:dict[str, str], forRule:bool=False) -> list[str]:
    '''
    The clingo body literals for *pat*. *var* maps each variable's name to its
    clingo variable (variables with the same name are the same variable), and
    gets value variables ("?a") added.

    Variables range over data only (see *GraphObject.isPatternElement()*):
    over individuals, types, or both, by their kind (see
    *GraphObject.variableKind()*: eg: "?x", "^T", "!a") -- and over relation
    types if used as one, whatever their kind. A query's variables also range over the objects rules create; a
    rule's (*forRule*: a rule that creates objects) don't -- or it could go on
    creating objects forever.

    :param pat:
    :type pat: Pattern
    :param var:
    :type var: dict[str, str]
    :param forRule:
    :type forRule: bool
    :returns:
    :rtype: list[str]
    '''
    dom, ind = ("base", "individual") if forRule else ("data", "any_individual")
    def term(x:GraphObject|None) -> str:
      return "_" if x is None else var.get(x.name, "") if x.isVariable() else self._term(x)
    relTypeVars = {t.name for t, _, _ in pat.triples if t.isVariable()}
    body:list[str] = []
    guard = {NameKind.INDIVIDUAL: ind, NameKind.TYPE: "type"}
    for v in {v.name: v for v in pat.variables}.values():
      g = None if v.name in relTypeVars else guard.get(v.variableKind()) # (a relation type variable: see rel_type below)
      body.append(f"{dom}({var[v.name]})" + (f", {g}({var[v.name]})" if g else ""))
    for t, s, d in pat.triples:
      body.append(f"holds({term(t)},{term(s)},{term(d)})")
      if t.isVariable():
        body.append(f"rel_type({term(t)})")
    body += [f"isa_star({term(x)},{term(t)})" for x, t in pat.types]
    # (only objects of the model are known to be different: an object a rule concludes exists -- eg: "a mother" -- might be anyone)
    body += [f"{term(x)} != {term(y)}, obj({term(x)}), obj({term(y)})" for x, y in pat.distinct]
    for v, key, value in pat.constraints:
      neg = isinstance(value, Not) # (negation as failure: it isn't so, as far as the model says)
      if neg:
        value = value.value
      if key in PROPERTIES:           # a relational property: a tag on a relation type
        body.append(f"{'not ' if (value is False) ^ neg else ''}prop({term(v)},{key})")
      elif value is PRESENT:
        body.append(f"{'not ' if neg else ''}attr({term(v)},{_str(key)},_)")
      elif isinstance(value, ValueVar): # (a negated one is bound by the same one, unnegated: see patternOf())
        body.append(f"{'not ' if neg else ''}attr({term(v)},{_str(key)},{var.setdefault(value, f'A{len(var)}')})")
      else:
        body.append(f"{'not ' if neg else ''}attr({term(v)},{_str(key)},{self._term(value)})")
    return body

  @staticmethod
  def _varNames(pat:Pattern) -> dict[str, str]:
    '''
    A clingo variable for each of *pat*\'s variable names, in answer order.

    :param pat:
    :type pat: Pattern
    :returns:
    :rtype: dict[str, str]
    '''
    return {name: f"V{i}" for i, name in enumerate(dict.fromkeys(v.name for v in pat.variables))}

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one rule,
    ``ans(V0,...) :- <a holds/3 literal per relation, isa_star/2 per type, ...>``,
    over the reasoner's results (including what the model's rules conclude) --
    so matches include inferred relations. See *_patternBody()*.

    :param context:
    :type context: GraphObject
    :returns:
    :rtype: list[dict[GraphObject, GraphObject]]
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
    args = ",".join(var[n] for n in names)
    head = f"ans({args})" if args else "ans"
    program = self._rulesProgram() + f"\n{head} :- {', '.join(body)}.\n#show ans/{len(names)}."
    symbols = self._solve(program, facts)
    merged = sameClasses([(self._value(sym.arguments[0]), self._value(sym.arguments[1])) for sym in symbols if sym.name == "same"])
    byKey = {_newObjectKey(n): r for n, r in merged.items()}
    def value(a:clingo.Symbol) -> Any: # (a new object: what it was merged into, if it was; and its inferred node, once it's made)
      v = self._value(a)
      if isinstance(v, NewObject):
        v = byKey.get(_newObjectKey(v), v)
      return inferredNodeFor(self.model, v)
    ret:list[dict[GraphObject, GraphObject]] = []
    seen:set[tuple] = set()
    for sym in symbols:
      if sym.name != "ans":
        continue
      vals = [value(a) for a in sym.arguments]
      k = tuple(_newObjectKey(v) if isinstance(v, NewObject) else id(v) for v in vals)
      if k in seen: # (merged: the same answer)
        continue
      seen.add(k)
      byName = dict(zip(names, vals))
      ret.append({v: byName[v.name] for v in pat.variables})
    return ret

  def _newTerm(self, rule:GraphObject, name:str, matched:list[str], var:dict[str, str]) -> str:
    '''
    The term for the object *rule* creates for its consequent variable *name*
    in each match: new(Rule,Name,((Var,Value),...)) -- a function of the match,
    so one object per match (see *NewObject*).

    :param rule:
    :type rule: GraphObject
    :param name:
    :type name: str
    :param matched:
    :type matched: list[str]
    :param var:
    :type var: dict[str, str]
    :returns:
    :rtype: str
    '''
    pairs = "".join(f"({_str(n)},{var[n]})," for n in matched)
    return f"new({self._term(rule)},{_str(name)},({pairs}))"

  def _satisfied(self, spec, var:dict[str, str], n:int) -> tuple[str, str]:
    '''
    For a rule that creates objects (see *NewObject*): a clingo rule saying
    that, for a match, the data already has objects in their place -- related
    as the conclusions say (or by a subtype: has-father for has-parent), and of
    the types they say (asserted relations and types only, so that the program
    stays stratified) -- and the literal to
    test it with. ("", "") if there's nothing to test.

    :param spec:
    :type spec:
    :param var:
    :type var: dict[str, str]
    :param n:
    :type n: int
    :returns:
    :rtype: tuple[str, str]
    '''
    new = {x.name for x in spec.new}
    exist = {name: f"E{i}" for i, name in enumerate(sorted(new))}
    def term(x) -> str:
      if x.isVariable():
        return exist.get(x.name) or var[x.name]
      return self._term(x)
    lits = [f"asserted_under({term(t)},{term(s)},{term(d)})" for t, s, d in spec.heads # (eg: has-father counts as has-parent)
            if any(x is not None and x.isVariable() and x.name in new for x in (s, d)) and s is not None and d is not None]
    lits += [f"isa_base({term(x)},{term(t)})" for x, t in spec.isas if x.isVariable() and x.name in new]
    if not lits:
      return "", ""
    used = [v for v in var.values() if any(re.search(rf"\b{v}\b", l) for l in lits)] # the match's variables the test uses
    head = f"sat_{n}({','.join(used)})" if used else f"sat_{n}"
    return f"{head} :- {', '.join(lits)}.", head

  def _rulesProgram(self) -> str:
    '''
    The rules (see *reasoner.ruleOf()*) -- the model's, its super-models' and
    the base rules (see *Reasoner.ruleObjects()*) -- as clingo rules, one per
    conclusion: ``fired(Rule,T,S,D) :- <antecedent>.`` for a relation, and
    ``rule_attr(Rule,X,Key,Value) :- <antecedent>.`` for an attribute. (The
    rule base takes these as holds/3 and attr/3.) The constraints (see
    *reasoner.constraintOf()*) likewise:
    ``violation0(Code,Severity,Subject,(Args,)) :- <pattern>.`` -- for a
    requirement, ``requirement_holds(Req,(Vars,)) :- <condition>, <required>.``
    and ``violation0(...) :- <condition>, not requirement_holds(Req,(Vars,)).``
    over the condition's variables. A rule or
    constraint with problems isn't used: its problems are reported as
    violations. Call after rendering the facts (see *_program()*).

    :returns:
    :rtype: str
    '''
    out:list[str] = []
    rules, constraints = self.specs()
    warn = lambda subject, code, args: f'violation0({code},warning,{self._term(subject)},({"".join(self._term(a) + "," for a in args)})).'
    for spec in constraints:
      c = spec.constraint
      out += [warn(c, code, args) for code, args in spec.warnings] # (it's still used)
      if spec.problems:
        out += [f'violation0({code},warning,{self._term(c)},({"".join(self._term(a) + "," for a in args)})).'
                for code, args in spec.problems]
        continue
      var = self._varNames(spec.pattern)
      body = self._patternBody(spec.pattern, var)
      if spec.required is not None: # a requirement: violated where its condition matches and what it requires doesn't
        condVars = "(" + "".join(v + "," for v in var.values()) + ")" # (the condition's variables, and its value variables)
        for name in dict.fromkeys(v.name for v in spec.required.variables): # (its own: "some")
          var.setdefault(name, f"V{len(var)}")
        holds = f"requirement_holds({self._term(c)},{condVars})"
        out.append(f"{holds} :- {', '.join(body + self._patternBody(spec.required, var))}.") # (the condition too: it gives the shared variables their values)
        body = body + [f"not {holds}"]
      if not body:
        continue
      term = lambda x: var[x.name] if isinstance(x, GraphObject) and x.isVariable() else self._term(x)
      subject, *args = spec.report
      out.append(f'violation0({self._term(spec.code)},{spec.severity},{term(subject)},({"".join(term(a) + "," for a in args)})) :- {", ".join(body)}.')
    for rspec in rules:
      r = rspec.rule
      out += [warn(r, code, rargs) for code, rargs in rspec.warnings] # (it's still used)
      if rspec.problems:
        for code, rargs in rspec.problems:
          out.append(f'violation0({code},warning,{self._term(r)},({"".join(self._term(a) + "," for a in rargs)})).')
        continue
      if not (rspec.heads or rspec.assertions or rspec.isas or rspec.new):
        continue
      var = self._varNames(rspec.pattern)
      body = self._patternBody(rspec.pattern, var, forRule=bool(rspec.new)) # (a rule that creates nothing can't run away: it ranges over all the data)
      matched = [n for n in var if n in {v.name for v in rspec.pattern.variables}] # (not value variables)
      newTerms = {x.name: self._newTerm(r, x.name, matched, var) for x in rspec.new}
      def term(x:GraphObject|None) -> str:
        if x is not None and x.isVariable():
          return newTerms.get(x.name) or var[x.name]
        return self._term(x)
      tail = f" :- {', '.join(body)}." if body else "."
      newTail = tail # (for conclusions about new objects: only if the data doesn't already have them)
      if newTerms:
        sat, satLit = self._satisfied(rspec, var, len(out))
        if sat:
          out.append(sat)
          newTail = f" :- {', '.join(body + [f'not {satLit}'])}."
      isNew = lambda *xs: any(x is not None and x.isVariable() and x.name in newTerms for x in xs)
      for n in newTerms.values():
        out.append(f"rule_new({n}){newTail}")
      for x, t in rspec.isas:
        out.append(f"rule_isa({self._term(r)},{term(x)},{term(t)}){newTail if isNew(x) else tail}")
      for t, s, d in rspec.heads:
        out.append(f"fired({self._term(r)},{term(t)},{term(s)},{term(d)}){newTail if isNew(s, d) else tail}")
      for x, key, value in rspec.assertions:
        v = "true" if value is PRESENT else var[value] if isinstance(value, ValueVar) else self._term(value)
        out.append(f"rule_attr({self._term(r)},{term(x)},{_str(key)},{v}){newTail if isNew(x) else tail}")
    return "\n".join(out)

  @override
  def query(self, query:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    :param query: Extra clingo rules defining the predicate *answer*; objects
      can be named with ``name(O,"...")``.
    :type query: str
    :param answer:
    :type answer: str
    :returns: The argument tuples of every *answer* atom, with ``o(N)`` terms
      mapped back to *GraphObjects*.
    :rtype: list[tuple[Any, ...]]
    '''
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    program = self._rulesProgram() + "\n" + query + f'\n#show {answer}/{_arity(query, answer)}.'
    return [tuple(self._value(a) for a in sym.arguments)
            for sym in self._solve(program, facts) if sym.name == answer]

_SYMBOL = re.compile(r"_*[a-z]\w*$")
"A clingo symbolic constant (eg: symmetric)."

def _str(s:str) -> str:
  '''
  A clingo string literal.

  :param s:
  :type s: str
  :returns:
  :rtype: str
  '''
  return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'

def _arity(program:str, pred:str) -> int:
  '''
  The arity of the first head occurrence of *pred* in *program*.

  :param program:
  :type program: str
  :param pred:
  :type pred: str
  :returns:
  :rtype: int
  '''
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
