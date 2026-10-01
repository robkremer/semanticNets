'''
Label templates: what an object's label says, as a string with shell-style
(POSIX parameter expansion) substitutions:

  ``$key`` or ``${key}``    the value of *key*
  ``${key:+text}``          *text* if *key* has a (non-empty) value, else nothing
  ``${key:-text}``          *key*'s value, or *text* if it has none
  ``$$``                    a "$"
  ``\\n``                    a line break

*text* may itself contain substitutions. Keys (see *labelLookup()*) are any
attribute of the object (its effective value), and:

  ``name``         its name
  ``localName``    its name only if it has its own (not one inherited)
  ``type``         the names of its types (parents), comma separated
  ``constraints``  a variable's constraints (see *sn.model.constraints*)
  ``id``           its id

Eg: ``$name${constraints:+ {$constraints}}`` gives "fred" or "?p {alive}";
``$type${name:+: $name}`` gives Sowa's "person: fred".

The template is the object's "vis/label" attribute if it has one (eg: set on a
type, for all its instances), else the "gui/label" preference ("gui/relationLabel"
for relations).

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
from typing import Any, Callable

DEFAULT_LABEL = "$name${constraints:+ {$constraints}}"
"The default label template, for nodes and relations alike."

LABEL_NOTE = '''What an object's label says: text with substitutions --
  $key or ${key}   the value of key
  ${key:+text}     text, if key has a value (else nothing)
  ${key:-text}     key's value, or text if it has none
  $$               a "$"
  \\n               a line break
The text in ${...} may itself contain substitutions.
Keys: any attribute, and
  name             its name
  localName        its name, only if it has its own (not inherited)
  type             its types
  constraints      a variable's constraints
  id               its id
Eg:
  $name${constraints:+ {$constraints}}   "fred", or "?p {alive}" (the default)
  $type${name:+: $name}                  Sowa's "person: fred"
An object's "vis/label" attribute (eg: on its type) overrides this.'''
"The note on the label template preferences (and \"vis/label\"): shown as its tooltip."

_NAME = re.compile(r"[A-Za-z_]\w*")

class TemplateError(ValueError):
  'A label template that can\'t be expanded.'

def expand(template:str, lookup:Callable[[str], str]) -> str:
  '''
  :returns: *template* with its substitutions made (see the module doc);
    *lookup(key)* gives a key's value ("" for none).
  :raises TemplateError: If *template* is malformed (eg: an unclosed "${").
  '''
  out, i = _expand(template, 0, lookup, closer=None)
  return out

def _expand(t:str, i:int, lookup:Callable[[str], str], closer:str|None) -> tuple[str, int]:
  'Expand *t* from *i* up to (not including) an unnested *closer*: (text, index of the closer or end).'
  out:list[str] = []
  depth = 0 # (literal "{"s in the text, which a "}" closes before *closer* does)
  while i < len(t):
    c = t[i]
    if closer is not None and c == closer and depth == 0:
      return "".join(out), i
    if c == "{":
      depth += 1
    elif c == "}" and depth > 0:
      depth -= 1
    if c == "\\" and t[i+1:i+2] == "n":
      out.append("\n"); i += 2
    elif c == "$":
      nxt = t[i+1:i+2]
      if nxt == "$":
        out.append("$"); i += 2
      elif nxt == "{":
        text, i = _braced(t, i + 2, lookup)
        out.append(text)
      elif (m := _NAME.match(t, i + 1)):
        out.append(lookup(m.group())); i = m.end()
      else:
        out.append("$"); i += 1
    else:
      out.append(c); i += 1
  if closer is not None:
    raise TemplateError(f'unclosed "${{" in {t!r}')
  return "".join(out), i

def _braced(t:str, i:int, lookup:Callable[[str], str]) -> tuple[str, int]:
  'A ${...} starting just after the "${": (its expansion, the index after its "}").'
  m = re.compile(r"[A-Za-z_][\w/.-]*").match(t, i)
  if not m:
    raise TemplateError(f'expected a key after "${{" in {t!r}')
  key, i = m.group(), m.end()
  value = lookup(key)
  if t[i:i+1] == "}":
    return value, i + 1
  op = t[i:i+2]
  if op not in (":+", ":-"):
    raise TemplateError(f'expected "}}", ":+" or ":-" after "${{{key}" in {t!r}')
  alt, j = _expand(t, i + 2, lookup, closer="}")
  if op == ":+":
    return (alt if value else ""), j + 1
  return (value if value else alt), j + 1

def labelLookup(mo:Any) -> Callable[[str], str]:
  ':returns: The *lookup* for *expand()* for model object *mo* (see the module doc for the keys).'
  def lookup(key:str) -> str:
    try:
      if key == "name":
        return (mo.name or "").strip()
      if key == "localName":
        return str(mo.getLocal("name", "") or "").strip()
      if key == "type":
        return ", ".join(p.name for p in mo.getParents())
      if key == "constraints":
        return mo.constraintsText().replace(": ", ": ") # (each "key: value" kept on one line)
      if key == "id":
        return str(getattr(mo, "_id", ""))
      v = mo.get(key, None)
    except Exception:
      return ""
    if isinstance(v, bool):
      return "true" if v else "false"
    return str(v) if isinstance(v, (str, int, float)) else ""
  return lookup
