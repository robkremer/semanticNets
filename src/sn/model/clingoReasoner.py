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
import re
from typing import Any, override
import clingo
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact, PROPERTIES, Pattern, patternOf, ruleOf, rules, ruleSpecs, NewObject
from sn.model.constraints import PRESENT, ValueVar

RULES = Path(__file__).with_name("clingoReasoner.lp")
"The default rule base."

class ClingoReasoner(Reasoner, engine="clingo"):
  '''
  Native queries are extra clingo rules defining an answer predicate (``ans``
  by default) over the fact vocabulary and the rule base's output predicates
  (holds/3, isa_star/2, inherited/3, ...). Eg::

    r.query('ans(X) :- holds(T,F,X), name(T,"owns"), name(F,"fred").')
  '''

  language = "asp"

  def __init__(self, model:Model, rules:Path|str=RULES):
    super().__init__(model)
    self.rules = Path(rules)
    self._ids:dict[int, int] = {}
    "id(GraphObject) -> term number"
    self._objs:list[GraphObject] = []
    "term number -> GraphObject"

  # ── Rendering ────────────────────────────────────────────────────────────

  def _term(self, x:Any) -> str:
    if isinstance(x, GraphObject):
      n = self._ids.get(id(x))
      if n is None:
        n = len(self._objs)
        self._ids[id(x)] = n
        self._objs.append(x)
      return f'o({n})'
    if isinstance(x, Sym):
      return str(x)
    if isinstance(x, bool):
      return "true" if x else "false"
    if isinstance(x, int) and abs(x) < 2**30:
      return str(x)
    return _str(str(x))

  def _program(self, facts:list[Fact]) -> str:
    self._ids.clear()
    self._objs.clear()
    return "\n".join(f'{pred}({",".join(self._term(a) for a in args)}).' for pred, args in facts)

  # ── Solving ──────────────────────────────────────────────────────────────

  def _solve(self, program:str="", facts:str|None=None) -> list[clingo.Symbol]:
    '''
    :param facts: The model's facts, already rendered (see *_program()*) -- for
      a *program* that refers to objects by their o(N) terms, which must come
      from the same rendering. Rendered afresh if None.
    '''
    ctl = clingo.Control(["--warn=none"])
    ctl.load(str(self.rules))
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
    'Map a clingo symbol back to a GraphObject (for o(N)) or a Python value.'
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
    ret = Inferences()
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    for sym in self._solve(self._rulesProgram(), facts):
      args = [self._value(a) for a in sym.arguments]
      if sym.name not in ("fired", "rule_attr", "rule_isa", "rule_new") and any(isinstance(a, NewObject) for a in args):
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
        case "violation": ret.violations.append(Violation(*args))
    return ret

  def _patternBody(self, pat:Pattern, var:dict[str, str], forRule:bool=False) -> list[str]:
    '''
    The clingo body literals for *pat*. *var* maps each variable's name to its
    clingo variable (variables with the same name are the same variable), and
    gets value variables ("?a") added.

    Variables range over data only (see *GraphObject.isPatternElement()*):
    over individuals if the variable is an individual, over types if it's a
    type, and over relation types if it's used as one. A query's variables
    also range over the objects rules create; a rule's (*forRule*) don't --
    or a rule could go on creating objects forever.
    '''
    dom, ind = ("base", "individual") if forRule else ("data", "any_individual")
    def term(x:GraphObject|None) -> str:
      return "_" if x is None else var.get(x.name, "") if x.isVariable() else self._term(x)
    relTypeVars = {t.name for t, _, _ in pat.triples if t.isVariable()}
    body:list[str] = []
    for v in {v.name: v for v in pat.variables}.values():
      body.append(f"{dom}({var[v.name]})" + ("" if v.name in relTypeVars else
                  f", {ind}({var[v.name]})" if v.isIndividual() else f", type({var[v.name]})"))
    for t, s, d in pat.triples:
      body.append(f"holds({term(t)},{term(s)},{term(d)})")
      if t.isVariable():
        body.append(f"rel_type({term(t)})")
    body += [f"isa_star({term(x)},{term(t)})" for x, t in pat.types]
    body += [f"{term(x)} != {term(y)}" for x, y in pat.distinct]
    for v, key, value in pat.constraints:
      if key in PROPERTIES:           # a relational property: a tag on a relation type
        body.append(f"{'not ' if value is False else ''}prop({term(v)},{key})")
      elif value is PRESENT:
        body.append(f"attr({term(v)},{_str(key)},_)")
      elif isinstance(value, ValueVar):
        body.append(f"attr({term(v)},{_str(key)},{var.setdefault(value, f'A{len(var)}')})")
      else:
        body.append(f"attr({term(v)},{_str(key)},{self._term(value)})")
    return body

  @staticmethod
  def _varNames(pat:Pattern) -> dict[str, str]:
    'A clingo variable for each of *pat*\'s variable names, in answer order.'
    return {name: f"V{i}" for i, name in enumerate(dict.fromkeys(v.name for v in pat.variables))}

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one rule,
    ``ans(V0,...) :- <a holds/3 literal per relation, isa_star/2 per type, ...>``,
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
    args = ",".join(var[n] for n in names)
    head = f"ans({args})" if args else "ans"
    program = self._rulesProgram() + f"\n{head} :- {', '.join(body)}.\n#show ans/{len(names)}."
    rows = [sym for sym in self._solve(program, facts) if sym.name == "ans"]
    ret = []
    for sym in rows:
      byName = dict(zip(names, (self._value(a) for a in sym.arguments)))
      ret.append({v: byName[v.name] for v in pat.variables})
    return ret

  def _newTerm(self, rule:GraphObject, name:str, matched:list[str], var:dict[str, str]) -> str:
    '''
    The term for the object *rule* creates for its consequent variable *name*
    in each match: new(Rule,Name,((Var,Value),...)) -- a function of the match,
    so one object per match (see *NewObject*).
    '''
    pairs = "".join(f"({_str(n)},{var[n]})," for n in matched)
    return f"new({self._term(rule)},{_str(name)},({pairs}))"

  def _satisfied(self, spec, var:dict[str, str], n:int) -> tuple[str, str]:
    '''
    For a rule that creates objects (see *NewObject*): a clingo rule saying
    that, for a match, the data already has objects in their place -- related
    as the conclusions say, and of the types they say (asserted relations and
    types only, so that the program stays stratified) -- and the literal to
    test it with. ("", "") if there's nothing to test.
    '''
    new = {x.name for x in spec.new}
    exist = {name: f"E{i}" for i, name in enumerate(sorted(new))}
    def term(x) -> str:
      if x.isVariable():
        return exist.get(x.name) or var[x.name]
      return self._term(x)
    lits = [f"asserted({term(t)},{term(s)},{term(d)})" for t, s, d in spec.heads
            if any(x is not None and x.isVariable() and x.name in new for x in (s, d)) and s is not None and d is not None]
    lits += [f"isa_base({term(x)},{term(t)})" for x, t in spec.isas if x.isVariable() and x.name in new]
    if not lits:
      return "", ""
    used = [v for v in var.values() if any(re.search(rf"\b{v}\b", l) for l in lits)] # the match's variables the test uses
    head = f"sat_{n}({','.join(used)})" if used else f"sat_{n}"
    return f"{head} :- {', '.join(lits)}.", head

  def _rulesProgram(self) -> str:
    '''
    The model's rules (see *reasoner.ruleOf()*) as clingo rules, one per
    conclusion: ``fired(Rule,T,S,D) :- <antecedent>.`` for a relation, and
    ``rule_attr(Rule,X,Key,Value) :- <antecedent>.`` for an attribute. (The
    rule base takes these as holds/3 and attr/3.) A rule with problems isn't
    used: its problems are reported as violations. Call after rendering the
    facts (see *_program()*).
    '''
    out:list[str] = []
    for spec in ruleSpecs(self.objects()):
      r = spec.rule
      if spec.problems:
        for code, args in spec.problems:
          out.append(f'violation0({code},warning,{self._term(r)},({"".join(self._term(a) + "," for a in args)})).')
        continue
      if not (spec.heads or spec.assertions or spec.isas or spec.new):
        continue
      var = self._varNames(spec.pattern)
      body = self._patternBody(spec.pattern, var, forRule=True)
      matched = [n for n in var if not n.startswith("?") or n in {v.name for v in spec.pattern.variables}]
      newTerms = {x.name: self._newTerm(r, x.name, matched, var) for x in spec.new}
      def term(x:GraphObject|None) -> str:
        if x is not None and x.isVariable():
          return newTerms.get(x.name) or var[x.name]
        return self._term(x)
      tail = f" :- {', '.join(body)}." if body else "."
      newTail = tail # (for conclusions about new objects: only if the data doesn't already have them)
      if newTerms:
        sat, satLit = self._satisfied(spec, var, len(out))
        if sat:
          out.append(sat)
          newTail = f" :- {', '.join(body + [f'not {satLit}'])}."
      isNew = lambda *xs: any(x is not None and x.isVariable() and x.name in newTerms for x in xs)
      for n in newTerms.values():
        out.append(f"rule_new({n}){newTail}")
      for x, t in spec.isas:
        out.append(f"rule_isa({self._term(r)},{term(x)},{term(t)}){newTail if isNew(x) else tail}")
      for t, s, d in spec.heads:
        out.append(f"fired({self._term(r)},{term(t)},{term(s)},{term(d)}){newTail if isNew(s, d) else tail}")
      for x, key, value in spec.assertions:
        v = "true" if value is PRESENT else var[value] if isinstance(value, ValueVar) else self._term(value)
        out.append(f"rule_attr({self._term(r)},{term(x)},{_str(key)},{v}){newTail if isNew(x) else tail}")
    return "\n".join(out)

  @override
  def query(self, query:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    :param query: Extra clingo rules defining the predicate *answer*; objects
      can be named with ``name(O,"...")``.
    :returns: The argument tuples of every *answer* atom, with ``o(N)`` terms
      mapped back to *GraphObjects*.
    '''
    query += f'\n#show {answer}/{_arity(query, answer)}.'
    return [tuple(self._value(a) for a in sym.arguments)
            for sym in self._solve(query) if sym.name == answer]

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
