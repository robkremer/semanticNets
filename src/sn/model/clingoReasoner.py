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
from typing import Any, override
import clingo
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact

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
      if sym.name == "" : # tuple
        return tuple(self._value(a) for a in sym.arguments)
      if not sym.arguments:
        return sym.name
    if sym.type == clingo.SymbolType.Number:
      return sym.number
    if sym.type == clingo.SymbolType.String:
      return sym.string
    return str(sym)

  @override
  def run(self) -> Inferences:
    ret = Inferences()
    for sym in self._solve():
      args = [self._value(a) for a in sym.arguments]
      match sym.name:
        case "holds":     ret.holds.append(tuple(args)) #type: ignore[arg-type]
        case "inferred":  ret.inferred.append(tuple(args)) #type: ignore[arg-type]
        case "inherited": ret.inherited.append(tuple(args)) #type: ignore[arg-type]
        case "classify":  ret.classify.append(tuple(args)) #type: ignore[arg-type]
        case "isa_data":  ret.isa.add(tuple(args)) #type: ignore[arg-type]
        case "violation": ret.violations.append(Violation(*args))
    return ret

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one rule,
    ``ans(V0,...) :- <a holds/3 literal per relation, isa_star/2 per type>``,
    over the reasoner's results -- so matches include inferred relations.
    Variables range over data only (see *GraphObject.isPatternElement()*):
    over individuals if the variable is an individual, over types if it's a
    type, and over relation types if it's used as a relation's type.
    '''
    from sn.model.reasoner import patternOf
    pat = patternOf(context)
    facts = self._program(self.facts()) # (numbers the objects the rule refers to)
    var = {id(v): f"V{i}" for i, v in enumerate(pat.variables)}
    def term(x:GraphObject|None) -> str:
      return "_" if x is None else var.get(id(x)) or self._term(x)
    # a variable ranges over individuals if it's an individual, over types if
    # it's a type -- and over relation types if it's used as one
    relTypeVars = {id(t) for t, _, _ in pat.triples if id(t) in var}
    body = [f"data({var[id(v)]})" + ("" if id(v) in relTypeVars else
                                    f", individual({var[id(v)]})" if v.isIndividual() else f", type({var[id(v)]})")
            for v in pat.variables]
    for t, s, d in pat.triples:
      body.append(f"holds({term(t)},{term(s)},{term(d)})")
      if id(t) in var:
        body.append(f"rel_type({term(t)})")
    body += [f"isa_star({term(x)},{term(t)})" for x, t in pat.types]
    body += [f"{term(x)} != {term(y)}" for x, y in pat.distinct]
    if not body:
      return []
    args = ",".join(var[id(v)] for v in pat.variables)
    head = f"ans({args})" if args else "ans"
    rows = [sym for sym in self._solve(f"{head} :- {', '.join(body)}.\n#show ans/{len(pat.variables)}.", facts)
            if sym.name == "ans"]
    return [dict(zip(pat.variables, (self._value(a) for a in sym.arguments))) for sym in rows]

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
