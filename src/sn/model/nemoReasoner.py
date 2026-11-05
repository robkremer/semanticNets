'''
A :py:class:`~sn.model.reasoner.Reasoner` engine built on
`Nemo <https://github.com/knowsys/nemo>`_ (Datalog with stratified negation and
aggregates, from TU Dresden), through its Python bindings (``pip install
nemo-python``, imported as *nmo_python*).

The engine-neutral facts from :py:meth:`Reasoner.facts` are rendered as Nemo
facts, the rule base in *nemoReasoner.rls* (a port of *clingoReasoner.lp*) is
applied, and the results are mapped back onto the model's *GraphObjects*.
Every *GraphObject* is a constant ``<#N>``.

Unlike clingo, Nemo can say how it reached a conclusion: see
:py:meth:`NemoReasoner.explain`.

Where the two differ (see *nemoReasoner.rls*): a rule's negated attribute test
("not gender: female") is about the attributes the model gives, not those other
rules conclude -- Nemo needs the program stratified as a whole before it runs.

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
from dataclasses import dataclass, field
from pathlib import Path
import importlib.resources
from importlib.resources.abc import Traversable
import re
import tempfile
from typing import Any, override
from urllib.parse import unquote
try:
  import nmo_python
except ModuleNotFoundError as _ex: # (an optional engine: say how to get it -- see Reasoner.create())
  raise ModuleNotFoundError('The "nemo" reasoner needs the Nemo engine: pip install nemo-python', name=_ex.name) from _ex
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact, PROPERTIES, Pattern, patternOf, NewObject, inferredNodeFor, \
  sameClasses, _newObjectKey, _label
from sn.model.constraints import PRESENT, ValueVar, Not
from sn.model.names import NameKind

RULES = importlib.resources.files("sn.model").joinpath("nemoReasoner.rls")
"The default rule base. (Package data, so that it's found in a .pyz or a packaged app too.)"

_RENAMED = {"attr": "attr_base"}
"Facts given under another name (see *nemoReasoner.rls*: attr/3 is these and what the rules conclude)."

_BASE_ARITIES = (1, 2, 3)
"The numbers of violation arguments the rule base itself uses (violation0_N: see *nemoReasoner.rls*)."

@dataclass
class _Facts:
  '''
  The model's facts, rendered for Nemo (see *NemoReasoner._program()*).
  '''
  tables:dict[tuple[str, tuple[str, ...]], list[str]] = field(default_factory=dict)
  "(predicate, its columns' formats) -> rows: tab-separated fields"
  text:list[str] = field(default_factory=list)
  "Facts that don't fit a table, as Nemo facts."

@dataclass
class Step:
  '''
  One step of an explanation (see *NemoReasoner.explain()*): a conclusion and
  how it was reached.
  '''
  fact:str
  "What holds, readably: eg, \"ann -ancestorOf-> fred\"."
  predicate:str
  "Its predicate in the rule base, eg: \"holds\"."
  args:tuple[Any, ...]
  "Its arguments: objects as *GraphObjects*, new ones as *NewObjects*."
  rule:str|None = None
  "The rule of the rule base it follows by, as Nemo has it, or None for a given fact."
  premises:list[Step] = field(default_factory=list)
  "What it follows from."

  @property
  def trivial(self) -> bool:
    '''
    Whether it goes without saying: that something isa itself.
    '''
    return self.predicate in ("isa_star", "isa_base", "isa_data") and len(self.args) == 2 and self.args[0] is self.args[1]

  def shown(self, brief:bool=True) -> tuple[str, list[Step]]:
    '''
    :param brief: Leave out what's about the objects themselves (that they're
      data, types, relation types...), what goes without saying (see
      *trivial*), how what's asserted is asserted, and the steps that just pass
      a conclusion on (eg: holds from link_holds from asserted).
    :returns: What this step says, and the premises an explanation shows under it.
    '''
    if not brief:
      return self.fact, self.premises
    step = self
    while True:
      if step.predicate in _GIVEN:
        return step.fact, []
      ret = [p for p in step.premises if p.predicate not in _HIDDEN and not p.trivial]
      if len(ret) != 1 or ret[0].predicate in _REASONS or ret[0].rule is None and ret[0].fact != self.fact:
        return self.fact, ret
      if ret[0].rule is None: # (a given fact that says the same)
        return self.fact, []
      step = ret[0]

  def lines(self, indent:str="", brief:bool=True) -> list[str]:
    '''
    :param brief: See *shown()*; and without the rule base's rules.
    :returns: The explanation as lines of text, the premises indented below their conclusion.
    '''
    fact, premises = self.shown(brief)
    out = [indent + fact + ("" if brief or self.rule is None else "    [" + self.rule + "]")]
    for p in premises:
      out += p.lines(indent + "  ", brief)
    return out

  def __str__(self) -> str:
    '''
    :returns: A readable string for this object: the brief explanation (see *lines()*).
    '''
    return "\n".join(self.lines())

_HIDDEN:frozenset[str] = frozenset({"obj", "data", "base", "type", "rel_type", "individual", "any_individual", "kind", "name",
                                     "const", "pattern", "new_obj", "card_top", "card_counted"})
"Predicates a brief explanation leaves out (see *Step.shown()*): what objects are, not why something holds."

_GIVEN:frozenset[str] = frozenset({"asserted", "asserted_under"})
"Predicates a brief explanation doesn't explain (see *Step.shown()*): what the model asserts."

_REASONS:frozenset[str] = frozenset({"fired", "rule_isa", "rule_attr", "rule_new", "same"})
"Predicates a brief explanation always shows (see *Step.shown()*): a rule's conclusions, and merged objects."

_FORMATS:dict[str, str] = {
  "holds": "{1} -{0}-> {2}",
  "link_holds": "{1} -{0}-> {2}",
  "asserted": "{1} -{0}-> {2} (asserted)",
  "asserted_under": "{1} -{0}-> {2} (asserted)",
  "link": "{1} -{0}-> {2} (asserted)",
  "inherited": "{1} -{0}-> {2} (inherited)",
  "inferred": "{1} -{0}-> {2} (inferred)",
  "fired": "{2} -{1}-> {3}, by the rule {0}",
  "parent": "{0} isa {1}",
  "isa_star": "{0} isa {1}",
  "isa_base": "{0} isa {1}",
  "isa_data": "{0} isa {1}",
  "rule_isa": "{1} isa {2}, by the rule {0}",
  "rule_attr": "{1}.{2} = {3}, by the rule {0}",
  "rule_new": "{0} exists",
  "attr": "{0}.{1} = {2}",
  "attr_base": "{0}.{1} = {2}",
  "prop": "{0} is {1}",
  "same": "{0} is the same as {1}",
  "src": "the source of {0} is {1}",
  "dst": "the destination of {0} is {1}",
  "domain": "the domain of {0} is {1}",
  "range": "the range of {0} is {1}",
  "member": "{1} is a member of {0}",
}
"How *Step.fact* says what holds, by predicate (the rest: as Nemo has them, with objects named)."

class NemoReasoner(Reasoner, engine="nemo"):
  '''
  Native queries are extra Nemo rules defining an answer predicate (``ans``
  by default) over the fact vocabulary and the rule base's output predicates
  (holds/3, isa_star/2, inherited/3, ...). Objects are constants ``<#N>``,
  best found by name. Eg::

    r.query('ans(?X) :- holds(?T,?F,?X), name(?T,"owns"), name(?F,"fred").')
  '''

  language = "nemo"

  def __init__(self, model:Model, rules:Path|str|Traversable=RULES, showSysRules:bool|None=None):
    '''
    :param rules: The rule base: a file, or package data (see *RULES*).
    :param showSysRules: See *Reasoner.__init__()*.
    '''
    super().__init__(model, showSysRules=showSysRules)
    self.rules:Path|Traversable = Path(rules) if isinstance(rules, str) else rules
    self._ids:dict[int, int] = {}
    "id(GraphObject) -> constant number"
    self._objs:list[GraphObject] = []
    "constant number -> GraphObject"
    self._news:list[tuple[GraphObject, str, tuple[str, ...]]] = []
    "The objects rules create, by the number in their strings (see *_newTerm()*): (rule, variable, the match's variables)."
    self._newIds:dict[tuple, int] = {}
    "(id(rule), variable, the match's variables) -> its number in *_news*"
    self._engine:Any = None
    "The last run's nmo_python.NemoEngine (see *explain()*)."

  # ── Rendering ────────────────────────────────────────────────────────────

  def _term(self, x:Any) -> str:
    '''
    The Nemo term for a fact's argument: an object is <#n>, numbered as it's first met; a symbol a
    constant (or a string, if it isn't a name); a bool, int or string as itself.
    '''
    if isinstance(x, GraphObject):
      n = self._ids.get(id(x))
      if n is None:
        n = len(self._objs)
        self._ids[id(x)] = n
        self._objs.append(x)
      return f'<#{n}>'
    if isinstance(x, Sym):
      return str(x) if _SYMBOL.match(x) and x not in _KEYWORDS else _str(str(x))
    if isinstance(x, bool):
      return "true" if x else "false"
    if isinstance(x, int) and abs(x) < 2**62:
      return str(x)
    if isinstance(x, float) and x.is_integer() and abs(x) < 2**62:
      return str(int(x)) # (the same value as the int, as clingo has it: see ClingoReasoner._term())
    return _str(str(x))

  def _field(self, x:Any) -> tuple[str, str]|None:
    '''
    *x* (a fact's argument) as a field of a table Nemo imports (see
    *_program()*): (the column's format, the field) -- the same value as
    *_term()*\'s. None for a bool: there's no format for those.
    '''
    if isinstance(x, GraphObject):
      return "any", self._term(x)
    if isinstance(x, Sym) and _SYMBOL.match(x) and x not in _KEYWORDS:
      return "any", f"<{x}>" # (a constant: the same as Nemo's bare x)
    if isinstance(x, bool):
      return None
    if isinstance(x, (int, float)) and (term := self._term(x))[:1] != '"':
      return "int", term
    return "string", self._term(str(x))[1:-1] # (percent-encoded: no tabs, line ends or quotes -- see _str())

  def _program(self, facts:list[Fact]) -> _Facts:
    '''
    *facts* rendered for Nemo (objects numbered afresh: see *_term()*): as
    tables to import, by predicate and the formats of their columns, and the
    few that don't fit one (eg: with a bool) as Nemo facts. (Nemo takes a
    moment for each fact it parses, but reads a table at once.)
    '''
    self._ids.clear()
    self._objs.clear()
    self._news.clear()
    self._newIds.clear()
    ret = _Facts()
    for pred, args in facts:
      pred = _RENAMED.get(pred, pred)
      fields = [self._field(a) for a in args]
      if all(f is not None for f in fields):
        ret.tables.setdefault((pred, tuple(f[0] for f in fields)), []).append("\t".join(f[1] for f in fields)) #type: ignore[index]
      else:
        ret.text.append(f'{pred}({", ".join(self._term(a) for a in args)}).')
    return ret

  # ── Solving ──────────────────────────────────────────────────────────────

  def _solve(self, program:str="", facts:_Facts|None=None) -> dict[str, list[list[Any]]]:
    '''
    :param facts: The model's facts, already rendered (see *_program()*) -- for
      a *program* that refers to objects by their <#N> constants, which must come
      from the same rendering. Rendered afresh if None.
    :returns: The rows of each output predicate, as Nemo has them (see *_value()*).
    '''
    if facts is None:
      facts = self._program(self.facts())
    # (Nemo closes the files once it has reasoned; ignore_cleanup_errors only
    # matters if it fails before that, while holding one open on Windows.)
    with tempfile.TemporaryDirectory(prefix="sn-nemo-", ignore_cleanup_errors=True) as folder:
      imports = []
      for i, ((pred, formats), rows) in enumerate(facts.tables.items()):
        path = Path(folder, f"{i}.tsv")
        path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        # The native path: Nemo reads "C:/x" as an IRI with the scheme "C", but
        # "C:\x" (which no IRI can be) as a file. Its strings have no escapes,
        # so the backslashes go in as they are.
        imports.append(f'@import {pred} :- tsv{{resource="{path}", format=({", ".join(formats)})}}.')
      text = "\n".join((self.rules.read_text(encoding="utf-8"), *imports, *facts.text, program))
      try:
        prog = nmo_python.load_string(text)
        engine = nmo_python.NemoEngine(prog)
        engine.reason()
        ret = {pred: [list(row) for row in engine.result(pred)] for pred in prog.output_predicates()}
      except BaseException as ex: # (Nemo's errors, and its panics: pyo3's PanicException is a BaseException)
        if isinstance(ex, (KeyboardInterrupt, SystemExit, GeneratorExit)):
          raise
        raise RuntimeError(f"The rules couldn't be compiled: {ex}") from ex
    self._engine = engine
    return ret

  def _value(self, v:Any) -> Any:
    '''
    Map a Nemo value back to a GraphObject (for <#N>), a NewObject (for the
    strings that stand for them: see *_newTerm()*) or a Python value.
    '''
    if isinstance(v, (bool, int, float)):
      return v
    if isinstance(v, str):
      if v.startswith("<") and v.endswith(">"):
        name = v[1:-1]
        return self._objs[int(name[1:])] if name[:1] == "#" and name[1:].isdigit() else Sym(name)
      if v.startswith('"') and v.endswith('"') and len(v) >= 2:
        s = _unescape(v[1:-1])
        if s.startswith(("%new|", "%card|")):
          return self._newObject(s)
        return unquote(s)
      return v # (eg: a null, "_:3")
    if hasattr(v, "value"): # an nmo_python.NemoLiteral: eg: a language-tagged string
      return v.value()
    return str(v)

  def _object(self, s:str) -> Any:
    '''
    :param s: An object's constant as a string, as an f-string has it: "#12".
    :returns: The object.
    '''
    return self._objs[int(s[1:])] if s[:1] == "#" and s[1:].isdigit() else s

  def _newObject(self, s:str) -> NewObject:
    '''
    :param s: The string for an object a rule creates: "%new|K|#V0|#V1...", K
      its number in *_news*; or one a cardinality creates: "%card|#T|of|#X" (or "to").
    '''
    parts = s.split("|")
    if parts[0] == "%card":
      t = self._object(parts[1])
      return NewObject(t, t.name, ((parts[2], self._object(parts[3])),))
    rule, variable, names = self._news[int(parts[1])]
    return NewObject(rule, variable, tuple(zip(names, (self._object(p) for p in parts[2:]))))

  @override
  def run(self) -> Inferences:
    ret = Inferences()
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    for pred, rows in self._solve(self._rulesProgram(), facts).items():
      for row in rows:
        args = [self._value(a) for a in row]
        if pred not in ("fired", "rule_attr", "rule_isa", "rule_new", "same") and any(isinstance(a, NewObject) for a in args):
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
          case _ if pred.startswith("violation_"):
            ret.violations.append(Violation(args[0], args[1], args[2], tuple(args[3:])))
    return self._finish(ret)

  def _patternBody(self, pat:Pattern, var:dict[str, str], forRule:bool=False, inRule:bool=False) -> list[str]:
    '''
    The Nemo body literals for *pat*, as *ClingoReasoner._patternBody()*\'s.
    *var* maps each variable's name to its Nemo variable (variables with the
    same name are the same variable), and gets value variables ("?a") added.

    :param forRule: For a rule that creates objects: its variables range over base data only.
    :param inRule: For a rule's antecedent (any rule): a negated attribute
      test is about the attributes the model gives (attr_base/3), not those
      the rules conclude (attr/3) -- Nemo needs the program stratified, and
      the rules' conclusions depend on the rules.
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
      body.append(f"holds({term(t)}, {term(s)}, {term(d)})")
      if t.isVariable():
        body.append(f"rel_type({term(t)})")
    body += [f"isa_star({term(x)}, {term(t)})" for x, t in pat.types]
    # (only objects of the model are known to be different: an object a rule concludes exists -- eg: "a mother" -- might be anyone)
    body += [f"{term(x)} != {term(y)}, obj({term(x)}), obj({term(y)})" for x, y in pat.distinct]
    negAttr = "attr_base" if inRule else "attr"
    for v, key, value in pat.constraints:
      neg = isinstance(value, Not) # (negation as failure: it isn't so, as far as the model says)
      if neg:
        value = value.value
      if key in PROPERTIES:           # a relational property: a tag on a relation type
        body.append(f"{'~' if (value is False) ^ neg else ''}prop({term(v)}, {key})")
        continue
      pred = f"~{negAttr}" if neg else "attr"
      if value is PRESENT:
        body.append(f"{pred}({term(v)}, {_str(key)}, _)")
      elif isinstance(value, ValueVar): # (a negated one is bound by the same one, unnegated: see patternOf())
        body.append(f"{pred}({term(v)}, {_str(key)}, {var.setdefault(value, f'?A{len(var)}')})")
      else:
        body.append(f"{pred}({term(v)}, {_str(key)}, {self._term(value)})")
    return body

  @staticmethod
  def _varNames(pat:Pattern) -> dict[str, str]:
    '''
    A Nemo variable for each of *pat*\'s variable names, in answer order.
    '''
    return {name: f"?V{i}" for i, name in enumerate(dict.fromkeys(v.name for v in pat.variables))}

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one rule,
    ``ans(?V0,...) :- <a holds/3 literal per relation, isa_star/2 per type, ...>``,
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
    args = ", ".join(var[n] for n in names) or "0" # (Nemo has no predicates without arguments)
    program = self._rulesProgram() + f"\nans({args}) :- {', '.join(body)}.\n@output ans.\n"
    results = self._solve(program, facts)
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
      vals = [value(a) for a in row] if names else []
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
    in each match: a string, "%new|K|#V0|#V1..." -- K, its number in *_news*,
    saying which rule, variable and match variables it is (a function of the
    match, so one object per match: see *NewObject*).
    '''
    key = (id(rule), name, tuple(matched))
    k = self._newIds.get(key)
    if k is None:
      k = self._newIds[key] = len(self._news)
      self._news.append((rule, name, tuple(matched)))
    if not matched: # (one for the rule: no match variables)
      return f'"%new|{k}"'
    return 'f"%new|' + str(k) + "".join("|{" + var[n] + "}" for n in matched) + '"'

  def _satisfied(self, spec, var:dict[str, str], n:int) -> tuple[str, str]:
    '''
    For a rule that creates objects (see *NewObject*): a Nemo rule saying
    that, for a match, the data already has objects in their place (as
    *ClingoReasoner._satisfied()*) -- and the literal to test it with. ("",
    "") if there's nothing to test.
    '''
    new = {x.name for x in spec.new}
    exist = {name: f"?E{i}" for i, name in enumerate(sorted(new))}
    def term(x) -> str:
      if x.isVariable():
        return exist.get(x.name) or var[x.name]
      return self._term(x)
    lits = [f"asserted_under({term(t)}, {term(s)}, {term(d)})" for t, s, d in spec.heads # (eg: has-father counts as has-parent)
            if any(x is not None and x.isVariable() and x.name in new for x in (s, d)) and s is not None and d is not None]
    lits += [f"isa_base({term(x)}, {term(t)})" for x, t in spec.isas if x.isVariable() and x.name in new]
    if not lits:
      return "", ""
    used = [v for v in var.values() if any(re.search(rf"{re.escape(v)}\b", l) for l in lits)] # the match's variables the test uses
    head = f"sat_{n}({', '.join(used) or '0'})"
    return f"{head} :- {', '.join(lits)}.", head

  def _violation(self, code:Any, severity:str, subject:str, args:list[str], arities:set[int]) -> str:
    '''
    The head violation0_N(Code,Severity,Subject,Args...): N, the number of *args*, is added to *arities*.
    '''
    arities.add(len(args))
    return f'violation0_{len(args)}({", ".join([code, self._term(Sym(severity)), subject, *args])})'

  def _rulesProgram(self) -> str:
    '''
    The rules (see *reasoner.ruleOf()*) -- the model's, its super-models' and
    the base rules (see *Reasoner.ruleObjects()*) -- as Nemo rules, as
    *ClingoReasoner._rulesProgram()* has them in clingo; and the constraints
    (see *reasoner.constraintOf()*), as violation0_N/(3+N) for N arguments (a
    requirement's holding as req_N(Vars...)). And violation_N for each N:
    the violations about the data, as reported. Call after rendering the facts
    (see *_program()*).
    '''
    out:list[str] = []
    arities:set[int] = set(_BASE_ARITIES)
    rules, constraints = self.specs()
    def problem(subject:GraphObject, code:str, args:tuple) -> str:
      return self._violation(self._term(Sym(code)), "warning", self._term(subject), [self._term(a) for a in args], arities) + "."
    for spec in constraints:
      c = spec.constraint
      out += [problem(c, code, args) for code, args in spec.warnings] # (it's still used)
      if spec.problems:
        out += [problem(c, code, args) for code, args in spec.problems]
        continue
      var = self._varNames(spec.pattern)
      body = self._patternBody(spec.pattern, var)
      if spec.required is not None: # a requirement: violated where its condition matches and what it requires doesn't
        condVars = ", ".join(var.values()) or "0" # (the condition's variables, and its value variables)
        for name in dict.fromkeys(v.name for v in spec.required.variables): # (its own: "some")
          var.setdefault(name, f"?V{len(var)}")
        holds = f"req_{len(out)}({condVars})"
        out.append(f"{holds} :- {', '.join(body + self._patternBody(spec.required, var))}.") # (the condition too: it gives the shared variables their values)
        body = body + [f"~{holds}"]
      if not body:
        continue
      term = lambda x: var[x.name] if isinstance(x, GraphObject) and x.isVariable() else self._term(x)
      subject, *args = spec.report
      out.append(f'{self._violation(self._term(spec.code), spec.severity, term(subject), [term(a) for a in args], arities)} :- {", ".join(body)}.')
    for rspec in rules:
      r = rspec.rule
      out += [problem(r, code, rargs) for code, rargs in rspec.warnings] # (it's still used)
      if rspec.problems:
        out += [problem(r, code, rargs) for code, rargs in rspec.problems]
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
      tail = f" :- {', '.join(body)}." if body else "."
      newTail = tail # (for conclusions about new objects: only if the data doesn't already have them)
      if newTerms:
        sat, satLit = self._satisfied(rspec, var, len(out))
        if sat:
          out.append(sat)
          newTail = f" :- {', '.join(body + [f'~{satLit}'])}."
      isNew = lambda *xs: any(x is not None and x.isVariable() and x.name in newTerms for x in xs)
      for n in newTerms.values():
        out.append(f"rule_new({n}){newTail}")
      for x, t in rspec.isas:
        out.append(f"rule_isa({self._term(r)}, {term(x)}, {term(t)}){newTail if isNew(x) else tail}")
      for t, s, d in rspec.heads:
        out.append(f"fired({self._term(r)}, {term(t)}, {term(s)}, {term(d)}){newTail if isNew(s, d) else tail}")
      for x, key, value in rspec.assertions:
        v = "true" if value is PRESENT else var[value] if isinstance(value, ValueVar) else self._term(value)
        out.append(f"rule_attr({self._term(r)}, {term(x)}, {_str(key)}, {v}){newTail if isNew(x) else tail}")
    for arity in sorted(arities): # (only the data's violations are reported)
      vs = "".join(f", ?A{i}" for i in range(arity))
      out.append(f"violation_{arity}(?C, ?S, ?X{vs}) :- violation0_{arity}(?C, ?S, ?X{vs}), data(?X).")
    out += [f"@output violation_{arity}." for arity in sorted(arities)]
    return "\n".join(out)

  @override
  def query(self, query:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    :param query: Extra Nemo rules defining the predicate *answer*; objects
      can be named with ``name(?O,"...")``.
    :returns: The argument tuples of every *answer* atom, with ``<#N>``
      constants mapped back to *GraphObjects*.
    '''
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    program = self._rulesProgram() + "\n" + query + f'\n@output {answer}.\n'
    return [tuple(self._value(a) for a in row) for row in self._solve(program, facts).get(answer, [])]

  # ── Explanations ─────────────────────────────────────────────────────────

  def explain(self, *fact:Any, predicate:str="holds") -> Step|None:
    '''
    How the last *run()* (or *answer()*, *query()*) reached a conclusion: eg:
    ``r.explain(ancestorOf, ann, fred)`` for why ann -ancestorOf-> fred holds.

    :param fact: The conclusion's arguments: objects, or values.
    :param predicate: The conclusion's predicate in the rule base: by
      default holds/3 (relation type, source, destination); eg: isa_star/2,
      or violation_N for a violation with N arguments.
    :returns: The conclusion's derivation, or None if it doesn't hold (or
      there's been no run).
    '''
    if self._engine is None:
      return None
    terms = []
    for a in fact:
      if isinstance(a, GraphObject) and id(a) not in self._ids:
        return None # (not in the last run: so nothing about it holds)
      terms.append(self._term(a))
    try:
      trace = self._engine.trace(f"{predicate}({', '.join(terms)})")
    except BaseException as ex: # (eg: a predicate that isn't in the program)
      if isinstance(ex, (KeyboardInterrupt, SystemExit, GeneratorExit)):
        raise
      raise ValueError(f"Can't explain {predicate}: {ex}") from ex
    return None if trace is None else self._step(trace.dict())

  def _step(self, d:dict) -> Step:
    '''
    :param d: A Nemo trace, as a dict ({"fact": ...} or {"rule": ..., "assignment": ..., "subtraces": [...]}).
    '''
    rule = d.get("rule")
    if rule is None:
      atom = d["fact"]
    else: # (the rule's head, with its variables' values)
      values = d.get("assignment", {})
      atom = re.sub(r"\?\w+", lambda m: values.get(m.group(0), m.group(0)), rule.split(":-")[0].strip())
    m = re.match(r"\s*(\w+)\s*\((.*)\)\s*$", atom, re.S)
    pred, args = (m.group(1), tuple(self._value(a) for a in _splitArgs(m.group(2)))) if m else (atom, ())
    premises = [self._step(s) for s in d.get("subtraces", [])]
    return Step(self._say(pred, args), pred, args, rule, premises)

  def _say(self, pred:str, args:tuple[Any, ...]) -> str:
    '''
    :returns: What *pred* (*args*) says, readably (see *_FORMATS*), objects named relative to the model.
    '''
    names = [_label(a, self.model) for a in args]
    if pred in ("fired", "rule_isa", "rule_attr") and args and isinstance(args[0], GraphObject):
      names[0] = f'"{args[0].name}"' # (the rule)
    template = _FORMATS.get(pred)
    if template is not None and len(re.findall(r"\{\d\}", template)) == len(names):
      return template.format(*names)
    return f"{pred}({', '.join(names)})"

_SYMBOL = re.compile(r"[A-Za-z][A-Za-z0-9_]*$")
"A Nemo constant that needs no brackets (eg: symmetric)."

_KEYWORDS:frozenset[str] = frozenset({"true", "false"})
"Names that aren't constants in Nemo (they're its booleans): written as strings."

_UNSAFE = re.compile(r'[%"\\\x00-\x1f\x7f]')
"What a Nemo string can't contain (it has no escapes: a quote ends it), or might be misread: percent-encoded (see *_str()*)."

def _str(s:str) -> str:
  '''
  A Nemo string literal for *s*. Nemo has no escapes in strings, so a quote,
  a backslash, a control character and the percent sign itself are
  percent-encoded (as in a URL): equal strings stay equal, and *_value()*
  decodes them.
  '''
  return '"' + _UNSAFE.sub(lambda m: f"%{ord(m.group(0)):02X}", s) + '"'

_ESCAPE = re.compile(r'\\(.)')
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}

def _unescape(s:str) -> str:
  '''
  The content of a string as Nemo reports it (with \\\\ for a backslash, \\n for a newline, ...).
  '''
  return _ESCAPE.sub(lambda m: _ESCAPES.get(m.group(1), m.group(1)), s)

def _splitArgs(text:str) -> list[str]:
  '''
  The arguments of an atom as Nemo writes it (eg: '<#3>, "a, b", 42'): split at the commas outside strings and brackets.
  '''
  return [a.strip() for a in re.findall(r'(?:"(?:[^"\\]|\\.)*"|<[^<>]*>|[^,"<])+', text) if a.strip()]
