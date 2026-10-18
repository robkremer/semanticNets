'''
The constraints of pattern variables: what an object must be like to match a
variable (eg: ``?p``) in a query or a rule's antecedent -- or, in a rule's
consequent, what's concluded about it.

A variable's constraints are the text of its "constraints" attribute, eg::

  alive, age: 30, owner: ?o, nickname: 'Big Al'

- ``key`` alone: has the attribute (any value).
- ``key: value``: has it with that value. A value is a number, ``true`` or
  ``false``, a value variable (a variable's name, eg: ``?o`` -- see
  *sn.model.names*: the same value wherever it's used in the rule or query), or text -- quoted (``'...'`` or ``"..."``) if it has commas,
  colons or quotes in it, or would otherwise read as one of the others.
- The relational properties (symmetric, asymmetric, reflexive, irreflexive,
  transitive) are tags on relation types: ``symmetric`` means it is,
  ``symmetric: false`` that it isn't.
- ``not`` before any of these negates it: ``not alive``: doesn't have the
  attribute; ``not gender: female``: doesn't have it with that value (so
  something with no gender at all passes -- ``gender, not gender: female``
  says it has one, and it isn't female). There can be more than one for a key
  (``not colour: red, not colour: blue``). A negated value variable must also
  be used without ``not`` somewhere in the pattern, which gives it its value.
  They're tests: a rule can't conclude that something *isn't* so.

They may be typed with a variable's name, after ``:where:`` -- eg: ``?p :where:
alive, age: 30`` -- and are then moved into the attribute (see *splitWhere()*).

Created on Sep 29, 2026

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
import re
import logging
from typing import Any
from sn.model import names

logger = logging.getLogger(__name__)

CONSTRAINTS = "constraints"
"The attribute holding a variable's constraints."

WHERE = ":where:"
"Separates a variable's name from its constraints, as typed (see *splitWhere()*)."

CONSTRAINTS_NOTE = '''A variable's constraints: what an object must be like to match it (in a query or a rule's antecedent), or what's concluded about it (in a rule's consequent). Separated by commas:
  alive           has the attribute "alive" (any value)
  age: 30         has "age" equal to 30 (numbers, true/false, or text: quote it if it has commas, colons or quotes, eg: 'Big Al')
  age: ?a         has "age" equal to that of the other constraints using ?a
  symmetric       (of a relation type) is tagged symmetric; "symmetric: false": isn't. Likewise asymmetric, reflexive, irreflexive, transitive.
  not ...         negates any of these, eg: "not gender: female" (true, too, of something with no gender at all), "not alive". Only as tests: not in a rule's consequent.
They can also be typed with the name, after ":where:", eg: ?p :where: alive, age: 30'''
"The note on the constraints attribute: shown as its tooltip in the attribute editor."

class _Present:
  'The value of a constraint that\'s just a key: the attribute is there (with any value).'
  _instance:_Present|None = None
  def __new__(cls):
    '''
    The one *_Present*.
    '''
    if cls._instance is None:
      cls._instance = super().__new__(cls)
    return cls._instance
  def __repr__(self) -> str:
    '''
    :returns: A string representation of this object.
    '''
    return "PRESENT"

PRESENT = _Present()
"A constraint's value when it's just a key (see *parseConstraints()*)."

class ValueVar(str):
  'A value variable, eg: ?a -- the same value wherever it\'s used (as opposed to the text "?a").'
  def __repr__(self) -> str:
    '''
    :returns: A string representation of this object.
    '''
    return f"ValueVar({str.__repr__(self)})"

class Not:
  '''
  A negated constraint's value (in a *Pattern*'s constraints -- see
  *sn.model.reasoner.patternOf()*): what the variable matches mustn't have
  the attribute with *value* (or, if *value* is PRESENT, at all).
  '''
  __slots__ = ("value",)
  def __init__(self, value:Any):
    '''
    :param value: The value it mustn't have: as a constraint's value (see *parseConstraints()*).
    '''
    self.value = value
  def __eq__(self, other:object) -> bool:
    '''
    Whether *other* is a *Not* of the same value (of the same type).
    '''
    return isinstance(other, Not) and type(self.value) is type(other.value) and self.value == other.value
  def __hash__(self) -> int:
    '''
    The hash of its value (as *__eq__()* compares them).
    '''
    return hash(("Not", self.value))
  def __repr__(self) -> str:
    '''
    :returns: A string representation of this object.
    '''
    return f"Not({self.value!r})"

NOT = "not "
'''
The prefix of a negated constraint, as typed (eg: "not gender: female") --
and of its key in the parsed constraints (see *parseConstraints()*).
'''

def isNegated(key:str) -> bool:
  '''
  :param key: A key of parsed constraints (see *parseConstraints()*).
  :returns: True iff it's a negated constraint's ("not gender").
  '''
  return key.startswith(NOT)

def constraintItems(constraints:dict[str, Any]) -> list[tuple[str, Any]]:
  '''
  :param constraints: Parsed constraints (see *parseConstraints()*).
  :returns: Each constraint as (attribute key, value): a negated one's value
    a *Not*, one for each of its values. Eg: {"alive": PRESENT, "not gender":
    ("female",)} -> [("alive", PRESENT), ("gender", Not("female"))].
  '''
  ret:list[tuple[str, Any]] = []
  for k, v in constraints.items():
    if isNegated(k):
      ret += [(k[len(NOT):], Not(x)) for x in v]
    else:
      ret.append((k, v))
  return ret

class ConstraintError(ValueError):
  'Constraints text that can\'t be parsed.'

_KEY = re.compile(r"[A-Za-z_][\w./-]*$")
_NEGATED = re.compile(r"not\s+\S")
"A constraint's key part that's negated: \"not\", a space, and the key (but \"not\" alone is a key)."
_VALUE_VAR_STEM = re.compile(r"\w+$")

def _isValueVar(v:str) -> bool:
  '''
  :returns: True iff *v* is a well-formed value variable: a variable's name
    (see *sn.model.names*; its kind doesn't matter) with a word for a stem.
  '''
  return names.isVariableName(v) and bool(_VALUE_VAR_STEM.match(names.stem(v)))
_NUMBERISH = re.compile(r"[-+]?(\d|\.\d)")

def _split(text:str, sep:str) -> list[str]:
  '''
  Split *text* at *sep* characters that aren\'t inside quotes.
  '''
  parts, cur, quote = [], "", None
  for ch in text:
    if quote:
      cur += ch
      if ch == quote:
        quote = None
    elif ch in "'\"":
      cur += ch
      quote = ch
    elif ch == sep:
      parts.append(cur)
      cur = ""
    else:
      cur += ch
  if quote:
    raise ConstraintError(f"unterminated quote in {text.strip()!r}")
  parts.append(cur)
  return parts

def _value(text:str, key:str) -> Any:
  '''
  The value written in *text* (for *key*, in messages): a quoted string, true or false, a number, or else the
  text itself.
  '''
  v = text.strip()
  if v == "":
    raise ConstraintError(f'"{key}:" has no value')
  if v[0] in "'\"":
    if len(v) < 2 or v[-1] != v[0]:
      raise ConstraintError(f"bad quoting in {v!r}")
    return v[1:-1]
  if v.lower() in ("true", "false"):
    return v.lower() == "true"
  for conv in (int, float):
    try:
      return conv(v)
    except ValueError:
      pass
  if names.isVariableName(v):
    if not _isValueVar(v):
      raise ConstraintError(f"bad value variable {v!r}")
    return ValueVar(v)
  return v

def parseConstraints(text:str|None) -> dict[str, Any]:
  '''
  :returns: The constraints in *text* (see the module doc), in order: key ->
    PRESENT, a number, a bool, text (str), or a *ValueVar*. A negated one's key
    is "not " and its key (eg: "not gender"), and its value is a tuple of
    those values, one for each time it's given (eg: ("female",)). (See
    *constraintItems()*.)
  :raises ConstraintError: If *text* can't be parsed.
  '''
  ret:dict[str, Any] = {}
  if text is None:
    return ret
  text = text.strip()
  if text.startswith("{") and text.endswith("}"): # (as displayed)
    text = text[1:-1]
  for item in _split(text, ","):
    if not item.strip():
      continue
    key, *rest = _split(item, ":")
    key = key.strip()
    negated = bool(_NEGATED.match(key))
    if negated:
      key = key[len(NOT.strip()):].strip()
    if not _KEY.match(key):
      raise ConstraintError(f"bad key {key!r}" if key else f"missing key in {item.strip()!r}")
    if len(rest) > 1:
      raise ConstraintError(f'more than one ":" in {item.strip()!r} (quote the value?)')
    value = _value(rest[0], key) if rest else PRESENT
    if negated:
      old = ret.get(NOT + key, ())
      if Not(value) in [Not(v) for v in old]:
        raise ConstraintError(f'"{item.strip()}" is given twice')
      ret[NOT + key] = old + (value,)
    else:
      if key in ret:
        raise ConstraintError(f'"{key}" is given twice')
      ret[key] = value
  return ret

def _formatValue(v:Any) -> str:
  '''
  *v* written as *_value()* reads it: quoted if it would otherwise read as something else.
  '''
  if isinstance(v, bool):
    return "true" if v else "false"
  if isinstance(v, (int, float, ValueVar)):
    return str(v)
  s = str(v)
  if s == "" or s != s.strip() or any(c in s for c in ",:'\"{}") or s.lower() in ("true", "false") \
     or names.isVariableName(s) or _NUMBERISH.match(s):
    q = "'" if "'" not in s else '"'
    return f"{q}{s}{q}"
  return s

def formatConstraints(constraints:dict[str, Any]) -> str:
  '''
  :returns: *constraints* (as from *parseConstraints()*) as text, eg: "alive, age: 30".
  '''
  def one(k:str, v:Any) -> str:
    return k if v is PRESENT else f"{k}: {_formatValue(v)}"
  return ", ".join(one(NOT + k, v.value) if isinstance(v, Not) else one(k, v) for k, v in constraintItems(constraints))

def splitWhere(text:str) -> tuple[str, str|None]:
  '''
  Split a name as typed at ":where:", eg: "?p :where: alive, age: 30" ->
  ("?p", "alive, age: 30"). The constraints part is None if there's no
  ":where:" (and "" if it's empty).
  '''
  name, sep, rest = text.partition(WHERE)
  return (name.strip(), rest.strip()) if sep else (text.strip(), None)

def mergeConstraints(old:str|None, new:str) -> str:
  '''
  *new*'s constraints added to (or replacing the same keys in) *old*'s, as
  text. If *old* can't be parsed, *new* replaces it.
  :raises ConstraintError: If *new* can't be parsed.
  '''
  added = parseConstraints(new)
  try:
    base = parseConstraints(old)
  except ConstraintError:
    base = {}
  return formatConstraints({**base, **added})

def migrateConstraints(model) -> list[str]:
  '''
  Convert constraints stored the old way -- as a variable's own attributes,
  other than its name, note, "vis/..." and "constraints" -- into its
  "constraints" attribute (see the module doc).

  :returns: A message for each variable converted.
  '''
  from util.attribute import Attribute, VAR
  msgs:list[str] = []
  for obj in list(model.values()):
    try:
      if not obj.isVariable():
        continue
      old = {k: obj.getLocal(k) for k in dict.keys(obj)
             if k not in ("name", "note", CONSTRAINTS) and not k.startswith("vis/")}
    except Exception:
      continue
    if not old:
      continue
    folded = {k: PRESENT if v is True or v == "" else ValueVar(v) if isinstance(v, str) and _isValueVar(v) else v
              for k, v in old.items()}
    text = mergeConstraints(obj.getLocal(CONSTRAINTS, None), formatConstraints(folded))
    for k in old:
      del obj[k]
    obj.setAttr(CONSTRAINTS, Attribute(text, str, VAR, CONSTRAINTS_NOTE))
    msgs.append(f'{obj.name}: moved its attributes {", ".join(old)} into its constraints: {text}')
  return msgs
