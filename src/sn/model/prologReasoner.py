'''
A :py:class:`~sn.model.reasoner.Reasoner` engine built on `SWI-Prolog
<https://www.swi-prolog.org>`_ (Prolog, with tabling), through its Python
interface, janus (``pip install janus-swi``, imported as *janus_swi*: it needs
SWI-Prolog 9.1.12 or later installed).

The engine-neutral facts from :py:meth:`Reasoner.facts` are rendered as Prolog
facts, the rule base in *prologReasoner.pl* (a port of *clingoReasoner.lp*) is
applied, and the results are mapped back onto the model's *GraphObjects*.
Every *GraphObject* is an atom ``'#N'``.

Prolog's tabling, with the well-founded semantics, does what clingo's
grounding does: recursion ends, and a negation is evaluated once what it
tests is known -- so a rule's negated attribute test ("not gender: female")
is about the attributes the rules conclude too, as for clingo. (If rules make
a loop through a negation, so that what they conclude can't be decided, what
depends on it is left out.)

Each run loads the rule base, the facts and the rules into a module of its
own, which goes when it's done (see *_HELPER*). Prolog is called from one
thread (see *_call()*), whatever thread asks.

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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import importlib.resources
from importlib.resources.abc import Traversable
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Callable, Iterable, override

def _swiHome() -> None:
  '''
  On Windows, tell SWI-Prolog where it's installed (the SWI_HOME_DIR
  environment variable), from the swipl on the PATH -- the one whose DLL janus
  loads -- unless it's set already. SWI-Prolog otherwise looks in the
  registry, where an installer run without its dialogs (eg: by Chocolatey)
  may not have put it: then loading janus stops the program ("Could not find
  system resources").
  '''
  if sys.platform != "win32" or os.environ.get("SWI_HOME_DIR"):
    return
  exe = shutil.which("swipl")
  if exe is None:
    return
  try:
    out = subprocess.run([exe, "--dump-runtime-variables"], capture_output=True, text=True, timeout=60,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
  except (OSError, subprocess.SubprocessError):
    return
  home = re.search(r'^PLBASE="(.*)";\s*$', out, re.M)
  if home is not None and Path(home.group(1)).is_dir():
    os.environ["SWI_HOME_DIR"] = home.group(1)

_swiHome()
try:
  import janus_swi as janus # type: ignore[import-untyped]
except ModuleNotFoundError as _ex: # (an optional engine: say how to get it -- see Reasoner.create())
  raise ModuleNotFoundError('The "prolog" reasoner needs SWI-Prolog and its Python interface: install SWI-Prolog, then pip install janus-swi',
                            name=_ex.name) from _ex
except (ImportError, RuntimeError, OSError) as _ex: # (janus is there, but SWI-Prolog isn't: eg, "Could not find SWI-Prolog")
  raise ImportError(f'The "prolog" reasoner needs SWI-Prolog (9.1.12 or later) installed: {_ex}') from _ex
from sn.model.model import Model, GraphObject
from sn.model.reasoner import Reasoner, Inferences, Violation, Sym, Fact, PROPERTIES, Pattern, patternOf, NewObject, inferredNodeFor, \
  sameClasses, _newObjectKey
from sn.model.constraints import PRESENT, ValueVar, Not
from sn.model.names import NameKind

RULES = importlib.resources.files("sn.model").joinpath("prologReasoner.pl")
"The default rule base. (Package data, so that it's found in a .pyz or a packaged app too.)"

_RENAMED = {"attr": "attr_base"}
"Facts given under another name (see *prologReasoner.pl*: attr/3 is these, and what the rules conclude)."

RESULTS = ("isa_data", "holds", "inferred", "inherited", "classify", "violation", "fired", "rule_attr", "rule_isa", "rule_new", "same")
"The predicates whose answers the engine reads (see *run()*)."

_NEW_RESULTS = frozenset({"fired", "rule_attr", "rule_isa", "rule_new", "same"})
"The results that may be about the objects the rules create (the rest are about the model's: see *Inferences.newObjects*)."

# ── Prolog ───────────────────────────────────────────────────────────────────

_HELPER = r'''
:- module(sn_janus, [sn_run/4]).
% Loads a program (text) into a module of its own, and reads the true answers
% of some of its predicates: see PrologReasoner._solve().

:- dynamic sn_error/1.
:- multifile user:message_hook/3.

% While a program loads and runs: its errors are kept (to be raised in Python),
% and its warnings (eg: singleton variables) aren't printed.
user:message_hook(Term, Kind, _) :-
    nb_current(sn_quiet, true), !,
    ( Kind == error -> sn_text(Term, S), assertz(sn_error(S)) ; true ).

sn_text(Term, S) :-
    catch(( '$messages':translate_message(Term, Lines, []),
            with_output_to(string(S0), print_message_lines(current_output, '', Lines)) ), _, fail), !,
    S = S0.
sn_text(Term, S) :- term_string(Term, S).

% sn_run(+Text, +Preds, -Results, -Errors): Results is a list of Pred-Rows, a
% row a list of the arguments of a true answer (as Python can have them: see
% sn_py/2); or Errors, a list of messages.
sn_run(Text, Preds, Results, Errors) :-
    retractall(sn_error(_)),
    setup_call_cleanup(nb_setval(sn_quiet, true),
        catch(in_temporary_module(M, true, sn_load(M, Text, Preds, Results0)), Ex,
              ( sn_text(Ex, S), assertz(sn_error(S)), Results0 = [] )),
        ( nb_setval(sn_quiet, false), abolish_all_tables )),
    findall(S1, sn_error(S1), Errors),
    ( Errors == [] -> Results = Results0 ; Results = [] ).

sn_load(M, Text, Preds, Results) :-
    setup_call_cleanup(open_string(Text, In),
        load_files(M:sn_program, [stream(In), silent(true)]),
        close(In)),
    ( sn_error(_) -> Results = []
    ; ( current_predicate(M:sn_close/0) -> M:sn_close ; true ), % (see prologReasoner.pl)
      maplist(sn_rows(M), Preds, Results) ).

sn_rows(M, P, P-Rows) :-
    findall(Row, ( current_predicate(M:P/N), functor(G, P, N), call_delays(M:G, true),
                   G =.. [_|Args], maplist(sn_py, Args, Row) ), Rows0),
    sort(Rows0, Rows).

% A term as janus can give it to Python: a compound term f(A,...) is a tuple
% (f,A,...) -- -(f,A,...) to janus -- an object '#N' is (o,N), true and false
% are Python's.
sn_py(A, o-N) :- atom(A), sub_atom(A, 0, 1, After, '#'), After > 0, sub_atom(A, 1, After, 0, Digits),
    catch(atom_number(Digits, N), _, fail), integer(N), !.
sn_py(true, @(true)) :- !.
sn_py(false, @(false)) :- !.
sn_py(L, P) :- is_list(L), !, maplist(sn_py, L, P).
sn_py(T, P) :- compound(T), !, compound_name_arguments(T, F, As), maplist(sn_py, As, Ps), P =.. [-, F|Ps].
sn_py(X, X).
'''
"The Prolog module (sn_janus) the engine runs programs with: loaded once (see *_call()*)."

_worker:ThreadPoolExecutor|None = None
"The thread that calls Prolog (see *_call()*)."
_lock = threading.Lock()

def _call(fn:Callable[..., Any], *args:Any) -> Any:
  '''
  :returns: fn(\\*args), called in the thread that calls Prolog -- one thread,
    so one Prolog engine, whatever thread asks (eg: a reasoning in the
    background: see *SNGView.runBackgroundWork()*).
  '''
  global _worker
  with _lock:
    if _worker is None:
      _worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sn-prolog")
      _worker.submit(janus.consult, "sn_janus", _HELPER).result()
  return _worker.submit(fn, *args).result()

def _run(text:str, preds:list[str]) -> tuple[list[tuple[str, list[list[Any]]]], list[str]]:
  '''
  :returns: Loading *text*, the true answers of each of *preds* (see
    *_HELPER*'s sn_run/4); and the errors.
  '''
  ans = janus.query_once("sn_janus:sn_run(Text, Preds, Results, Errors)", {"Text": text, "Preds": preds})
  return ans["Results"], ans["Errors"]

# ── Ordering a rule's body ───────────────────────────────────────────────────

_QUOTED = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')
"A Prolog string or quoted atom."

_VARIABLE = re.compile(r"(?<![\w])[A-Z]\w*|(?<![\w])_\w+")
"A named Prolog variable (in text without strings or quoted atoms: see *_QUOTED*)."

_FILTERS = ("\\+ ", "tnot(", "not_exists(")
"How a negated literal starts."

def _variables(lit:str) -> set[str]:
  ''':returns: The variables of the literal *lit* (eg: "holds('#3',V0,V1)": V0 and V1).'''
  return set(_VARIABLE.findall(_QUOTED.sub("''", lit)))

def _args(lit:str) -> list[str]:
  ''':returns: The arguments of the literal *lit* (eg: "holds('#3',V0,_)": '#3', V0 and _: strings and quoted atoms as '').'''
  text = _QUOTED.sub("''", lit)
  start = text.find("(")
  if start < 0:
    return []
  args, depth, arg = [], 0, ""
  for c in text[start + 1:]:
    if c in "([":
      depth += 1
    elif c in ")]":
      if depth == 0:
        break
      depth -= 1
    elif c == "," and depth == 0:
      args.append(arg.strip())
      arg = ""
      continue
    arg += c
  return args + [arg.strip()]

def _ordered(body:list[str]) -> list[str]:
  '''
  *body* (a rule's literals), in the order Prolog should run them. Prolog runs
  a body in order: a literal that shares no variable with those before it
  multiplies their answers (eg: data(X), data(Y), data(Z) before the relations
  between them), and a test (\\\\==) or a negation must wait until what it tests
  is bound. So, as for CLIPS (see *sn.model.clipsReasoner._ordered()*): first
  a literal with a constant, then each that shares the most with those already
  run -- and each test, and each negation, as soon as the variables it tests
  are bound (a variable that's only in a negation is its own).
  '''
  isFilter = lambda lit: lit.startswith(_FILTERS) or " \\== " in lit
  positive = [lit for lit in body if not isFilter(lit)]
  filters = [lit for lit in body if isFilter(lit)]
  bound:set[str] = set()
  inPositive = {v for lit in positive for v in _variables(lit)}
  out:list[str] = []
  def score(lit:str) -> tuple:
    vs = _variables(lit)
    consts = sum(1 for a in _args(lit) if a != "_" and not _VARIABLE.fullmatch(a))
    return (not (vs - bound), bool(vs & bound), len(vs & bound) + consts, -len(vs - bound))
  while positive or filters:
    ready = next((lit for lit in filters if _variables(lit) & inPositive <= bound), None)
    if ready is not None:
      filters.remove(ready)
      out.append(ready)
      continue
    if not positive:
      out += filters
      break
    best = max(positive, key=score) # (the first of the best)
    positive.remove(best)
    out.append(best)
    bound |= _variables(best)
  return out

# ── The engine ───────────────────────────────────────────────────────────────

class PrologReasoner(Reasoner, engine="prolog"):
  '''
  Native queries are extra Prolog clauses defining an answer predicate
  (``ans`` by default) over the fact vocabulary and the rule base's results
  (holds/3, isa_star/2, inherited/3, ...), as for clingo. Strings are written
  in double quotes. Eg::

    r.query('ans(X) :- name(F,"fred"), name(T,"owns"), holds(T,F,X).')

  A query's clauses run in the order they're written (start with what binds
  the most); a predicate of their own that's recursive should be tabled
  (``:- table p/2.``).
  '''

  language = "prolog"

  def __init__(self, model:Model, rules:Path|str|Traversable=RULES, showSysRules:bool|None=None):
    '''
    :param rules: The rule base: a file, or package data (see *RULES*).
    :param showSysRules: See *Reasoner.__init__()*.
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
    The Prolog term for a fact's argument: an object is the atom '#n',
    numbered as it's first met (see *prologReasoner.pl*); a symbol an atom (or
    a string, if it isn't a name, as clingo has it); a bool true or false; a
    number or string as itself.
    '''
    if isinstance(x, GraphObject):
      n = self._ids.get(id(x))
      if n is None:
        n = len(self._objs)
        self._ids[id(x)] = n
        self._objs.append(x)
      return f"'#{n}'"
    if isinstance(x, Sym):
      return f"'{x}'" if _SYMBOL.match(x) else _str(str(x))
    if isinstance(x, bool):
      return "true" if x else "false"
    if isinstance(x, int) and abs(x) < 2**62:
      return str(x)
    if isinstance(x, float) and x.is_integer() and abs(x) < 2**62:
      return str(int(x)) # (the same value as the int, as clingo has it: see ClingoReasoner._term())
    return _str(str(x))

  def _program(self, facts:list[Fact]) -> str:
    '''
    The Prolog facts stating *facts*, one a line (objects numbered afresh: see
    *_term()*), each predicate's together: Prolog warns of each clause that
    isn't with the others of its predicate -- slowly.
    '''
    self._ids.clear()
    self._objs.clear()
    byPred:dict[str, list[str]] = {}
    for pred, args in facts:
      pred = _RENAMED.get(pred, pred)
      byPred.setdefault(pred, []).append(f'{pred}({",".join(self._term(a) for a in args)}).' if args else f"{pred}.")
    return "\n".join(line for lines in byPred.values() for line in lines)

  # ── Running ──────────────────────────────────────────────────────────────

  def _solve(self, program:str, facts:str|None=None, query:str="", read:Iterable[str]=RESULTS) -> dict[str, list[list[Any]]]:
    '''
    :param program: The rules' clauses (see *_rulesProgram()*).
    :param facts: The model's facts, already rendered (see *_program()*) -- for
      a *program* that refers to objects by their '#N' atoms, which must come
      from the same rendering. Rendered afresh if None.
    :param query: More clauses (eg: a native query's).
    :param read: The predicates whose answers are wanted.
    :returns: The true answers of each of *read*: their arguments as janus has
      them (see *_value()*).
    '''
    if facts is None:
      facts = self._program(self.facts())
    parts = [("the rule base", self.rules.read_text(encoding="utf-8")), ("the facts", facts), ("the rules", program), ("the query", query)]
    text, starts, line = "", [], 1
    for what, part in parts:
      starts.append((line, what))
      text += part + "\n"
      line += part.count("\n") + 1
    results, errors = _call(_run, text, list(read))
    if errors:
      raise RuntimeError(f"The rules couldn't be compiled: {'; '.join(_where(e, starts) for e in errors)}")
    return dict(results)

  def _value(self, v:Any) -> Any:
    '''
    Map a value from Prolog (see *_HELPER*'s sn_py/2) back to a GraphObject
    (for '#N', which sn_py/2 gives as (o,N)), a NewObject (for new(...) and card(...): see *_newTerm()* and
    *prologReasoner.pl*) or a Python value: a list is a tuple.
    '''
    if isinstance(v, tuple):
      if v[0] == "o" and len(v) == 2 and isinstance(v[1], int):
        return self._objs[v[1]]
      if v[0] == "new" and len(v) == 4:
        rule, variable, bindings = self._value(v[1]), v[2], v[3]
        return NewObject(rule, variable, tuple((name, self._value(value)) for name, value in bindings))
      if v[0] == "card" and len(v) == 4:
        t = self._value(v[1])
        return NewObject(t, t.name, ((v[2], self._value(v[3])),))
      return tuple(self._value(a) for a in v)
    if isinstance(v, list):
      return tuple(self._value(a) for a in v)
    return v

  @override
  def run(self) -> Inferences:
    ret = Inferences()
    facts = self._program(self.facts()) # (numbers the objects the rules refer to)
    for pred, rows in self._solve(self._rulesProgram(), facts).items():
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
          case "violation": ret.violations.append(Violation(*args))
    return self._finish(ret)

  def _patternBody(self, pat:Pattern, var:dict[str, str], forRule:bool=False, inRule:bool=False) -> list[str]:
    '''
    The Prolog body literals for *pat*, as *ClingoReasoner._patternBody()*\'s
    (in no particular order: see *_ordered()*). *var* maps each variable's
    name to its Prolog variable (variables with the same name are the same
    variable), and gets value variables ("?a") added.

    :param forRule: For a rule that creates objects: its variables range over base data only.
    :param inRule: For a rule's antecedent (any rule): it's part of the
      closure (see *prologReasoner.pl*), so it tests r_holds/3, r_isa_star/2
      and r_attr/3 (tabled), and negates with not_exists/1. Otherwise (a
      constraint, a query) it tests the closure's results: holds/3, ... (facts).
    '''
    dom, ind = ("base", "individual") if forRule else ("data", "any_individual")
    holds, isa, attr, neg_ = ("r_holds", "r_isa_star", "r_attr", "not_exists({})") if inRule else ("holds", "isa_star", "attr", "\\+ {}")
    def term(x:GraphObject|None) -> str:
      return "_" if x is None else var.get(x.name, "_") if x.isVariable() else self._term(x)
    relTypeVars = {t.name for t, _, _ in pat.triples if t.isVariable()}
    body:list[str] = []
    guard = {NameKind.INDIVIDUAL: ind, NameKind.TYPE: "type"}
    for v in {v.name: v for v in pat.variables}.values():
      g = None if v.name in relTypeVars else guard.get(v.variableKind()) # (a relation type variable: see rel_type below)
      body.append(f"{dom}({var[v.name]})")
      if g:
        body.append(f"{g}({var[v.name]})")
    for t, s, d in pat.triples:
      body.append(f"{holds}({term(t)},{term(s)},{term(d)})")
      if t.isVariable():
        body.append(f"rel_type({term(t)})")
    body += [f"{isa}({term(x)},{term(t)})" for x, t in pat.types]
    # (only objects of the model are known to be different: an object a rule concludes exists -- eg: "a mother" -- might be anyone)
    for x, y in pat.distinct:
      body += [f"obj({term(x)})", f"obj({term(y)})", f"{term(x)} \\== {term(y)}"]
    for v, key, value in pat.constraints:
      neg = isinstance(value, Not) # (negation as failure: it isn't so, as far as the model says)
      if neg:
        value = value.value
      if key in PROPERTIES:           # a relational property: a tag on a relation type
        p = f"prop({term(v)},{self._term(Sym(key))})"
        body.append(f"\\+ {p}" if (value is False) ^ neg else p) # (an input fact)
        continue
      if value is PRESENT:
        p = f"{attr}({term(v)},{_str(key)},_)"
      elif isinstance(value, ValueVar): # (a negated one is bound by the same one, unnegated: see patternOf())
        p = f"{attr}({term(v)},{_str(key)},{var.setdefault(value, f'A{len(var)}')})"
      else:
        p = f"{attr}({term(v)},{_str(key)},{self._term(value)})"
      body.append(neg_.format(p) if neg else p)
    return body

  @staticmethod
  def _varNames(pat:Pattern) -> dict[str, str]:
    '''
    A Prolog variable for each of *pat*\'s variable names, in answer order.
    '''
    return {name: f"V{i}" for i, name in enumerate(dict.fromkeys(v.name for v in pat.variables))}

  @override
  def answer(self, context:GraphObject) -> list[dict[GraphObject, GraphObject]]:
    '''
    Translates the context's *Pattern* into one clause,
    ``ans(V0,...) :- <a holds/3 literal per relation, isa_star/2 per type, ...>``,
    over the reasoner's results (including what the model's rules conclude) --
    so matches include inferred relations. See *_patternBody()*.
    '''
    pat = patternOf(context)
    if pat.errors:
      raise ValueError("; ".join(f"the constraints of {x.name} can't be read: {err}" for x, err in pat.errors))
    facts = self._program(self.facts()) # (numbers the objects the clause refers to)
    var = self._varNames(pat)
    names = list(var)
    body = self._patternBody(pat, var)
    if not body:
      return []
    args = ",".join(var[n] for n in names)
    head = f"sn_ans({args})" if args else "sn_ans"
    results = self._solve(self._rulesProgram(), facts, f"{head} :- {', '.join(_ordered(body))}.", read=("same", "sn_ans"))
    merged = sameClasses([(self._value(a), self._value(b)) for a, b in results.get("same", [])])
    byKey = {_newObjectKey(n): r for n, r in merged.items()}
    def value(a:Any) -> Any: # (a new object: what it was merged into, if it was; and its inferred node, once it's made)
      v = self._value(a)
      if isinstance(v, NewObject):
        v = byKey.get(_newObjectKey(v), v)
      return inferredNodeFor(self.model, v)
    ret:list[dict[GraphObject, GraphObject]] = []
    seen:set[tuple] = set()
    for row in results.get("sn_ans", []):
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
    The term for the object *rule* creates for its consequent variable *name*
    in each match: new(Rule,Name,[[Var,Value],...]) -- a function of the match,
    so one object per match (see *NewObject*).
    '''
    pairs = ",".join(f"[{_str(n)},{var[n]}]" for n in matched)
    return f"new({self._term(rule)},{_str(name)},[{pairs}])"

  def _satisfied(self, spec, var:dict[str, str], n:int) -> tuple[str, str]:
    '''
    For a rule that creates objects (see *NewObject*): a Prolog clause saying
    that, for a match, the data already has objects in their place (as
    *ClingoReasoner._satisfied()*) -- and the literal to test it with. ("",
    "") if there's nothing to test.
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
    used = [v for v in var.values() if any(v in _variables(l) for l in lits)] # the match's variables the test uses
    head = f"sn_sat_{n}({','.join(used)})" if used else f"sn_sat_{n}"
    return f"{head} :- {', '.join(_ordered(lits))}.", head

  def _rulesProgram(self) -> str:
    '''
    The rules (see *reasoner.ruleOf()*) -- the model's, its super-models' and
    the base rules (see *Reasoner.ruleObjects()*) -- as Prolog clauses, one per
    conclusion, as *ClingoReasoner._rulesProgram()* has them in clingo:
    ``fired(Rule,T,S,D) :- <antecedent>.`` for a relation,
    ``rule_attr(Rule,X,Key,Value) :- <antecedent>.`` for an attribute, ...
    And the constraints (see *reasoner.constraintOf()*), as clauses for
    ``violation0(Code,Severity,Subject,[Args...])`` (a requirement's holding as
    ``requirement_holds(Constraint,[Vars...])``). Call after rendering the
    facts (see *_program()*).
    '''
    out:list[str] = []
    rules, constraints = self.specs()
    def problem(subject:GraphObject, code:str, args:tuple) -> str:
      return f'violation0({self._term(Sym(code))},warning,{self._term(subject)},[{",".join(self._term(a) for a in args)}]).'
    def clause(head:str, body:list[str], news:Iterable[str]=()) -> str:
      made:list[str] = [] # (a created object's term is made last: see prologReasoner.pl)
      for term in news:
        if term in head:
          head = head.replace(term, f"N{len(made)}")
          made.append(f"N{len(made)} = {term}")
      body = _ordered(body) + made
      return f"{head} :- {', '.join(body)}." if body else f"{head}."
    for spec in constraints:
      c = spec.constraint
      out += [problem(c, code, args) for code, args in spec.warnings] # (it's still used)
      if spec.problems:
        out += [problem(c, code, args) for code, args in spec.problems]
        continue
      var = self._varNames(spec.pattern)
      body = self._patternBody(spec.pattern, var)
      if spec.required is not None: # a requirement: violated where its condition matches and what it requires doesn't
        condVars = f"[{','.join(var.values())}]" # (the condition's variables, and its value variables)
        for name in dict.fromkeys(v.name for v in spec.required.variables): # (its own: "some")
          var.setdefault(name, f"V{len(var)}")
        holds = f"requirement_holds({self._term(c)},{condVars})"
        out.append(clause(holds, body + self._patternBody(spec.required, var))) # (the condition too: it gives the shared variables their values)
        body = body + [f"\\+ {holds}"]
      if not body:
        continue
      term = lambda x: var[x.name] if isinstance(x, GraphObject) and x.isVariable() else self._term(x)
      subject, *args = spec.report
      out.append(clause(f'violation0({self._term(spec.code)},{self._term(Sym(spec.severity))},{term(subject)},[{",".join(term(a) for a in args)}])', body))
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
      newBody = body # (for conclusions about new objects: only if the data doesn't already have them)
      if newTerms:
        sat, satLit = self._satisfied(rspec, var, len(out))
        if sat:
          out.append(sat)
          newBody = body + [f"not_exists({satLit})"]
      isNew = lambda *xs: any(x is not None and x.isVariable() and x.name in newTerms for x in xs)
      for n in newTerms.values():
        out.append(clause(f"rule_new({n})", newBody, newTerms.values()))
      for x, t in rspec.isas:
        out.append(clause(f"rule_isa({self._term(r)},{term(x)},{term(t)})", newBody if isNew(x) else body, newTerms.values()))
      for t, s, d in rspec.heads:
        out.append(clause(f"fired({self._term(r)},{term(t)},{term(s)},{term(d)})", newBody if isNew(s, d) else body, newTerms.values()))
      for x, key, value in rspec.assertions:
        v = "true" if value is PRESENT else var[value] if isinstance(value, ValueVar) else self._term(value)
        out.append(clause(f"rule_attr({self._term(r)},{term(x)},{_str(key)},{v})", newBody if isNew(x) else body, newTerms.values()))
    return "\n".join(out)

  @override
  def query(self, query:str, answer:str="ans") -> list[tuple[Any, ...]]:
    '''
    :param query: Extra Prolog clauses defining the predicate *answer*;
      objects can be named with ``name(O,"...")``.
    :returns: The arguments of every true *answer*, with ``'#N'`` atoms mapped
      back to *GraphObjects*.
    '''
    facts = self._program(self.facts()) # (numbers the objects the clauses refer to)
    return [tuple(self._value(a) for a in row) for row in self._solve(self._rulesProgram(), facts, query, read=(answer,)).get(answer, [])]

_SYMBOL = re.compile(r"[a-z]\w*$")
"A symbol that's written as an atom (eg: symmetric), as clingo has it (see *ClingoReasoner._term()*): others are strings."

def _str(s:str) -> str:
  '''
  A Prolog string literal (with the double_quotes flag "string": see *prologReasoner.pl*).
  '''
  return '"' + re.sub(r'[\\"\x00-\x1f\x7f]', lambda m: _ESCAPES.get(m.group(0)) or f"\\x{ord(m.group(0)):x}\\", s) + '"'

_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t"}

_LOCATION = re.compile(r"sn_program:(\d+):(\d+): ")
"Where in the program an error is (see *_where()*)."

def _where(message:str, starts:list[tuple[int, str]]) -> str:
  '''
  :returns: Prolog's *message*, saying where an error is by the part of the
    program it's in (the query, the rules, ...: *starts* has the line each
    starts on), not the whole program's line; and without the name of the
    module the program was loaded into.
  '''
  def where(m:re.Match) -> str:
    line, col = int(m.group(1)), int(m.group(2))
    start, what = next((s, w) for s, w in reversed(starts) if s <= line)
    return f"{what}, line {line - start + 1}, column {col}: "
  message = _LOCATION.sub(where, message.strip())
  return re.sub(r"'?tmp-[\d-]+'?:|'\$wfs_call'/\d+: ", "", message)
