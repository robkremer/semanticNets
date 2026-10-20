'''
The relation table of the layouts that arrange nodes as trees (tree, balloon,
radial: see *treeLayout.TreeLayout*), and of the hubs layout, if it follows
it: an ordered table of relation types, each with a role -- it shapes the
trees (with which end is the parent), pulls things together (for joining
trees, and putting things near what they're related to), or is ignored --
and a row for the relation types' own ends (their domain and range: see
*TERMINALS*).

A row covers its relation type's subtypes too, unless a subtype has a row of
its own: the most specific row wins. A relation no row covers pulls things
together. Earlier rows win: eg: a node with two parents goes under the one
it's related to by the higher row.

Created on Oct 17, 2026

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
from typing import Any, Iterable, Iterator
from urllib.parse import quote, unquote
from sn.model.model import IsaIndividual, Model, Relation

PARENT_ENDS = ("source", "destination")
'''Which end of a relation is the parent: eg: the source for "includes" (a
package includes its modules); the destination for "isa" (a subtype isa its
type) and "has-parent" (a child has-parent its parent). For the relation
types' own ends (see *TERMINALS*), the relation type is the source, and its
domain (or range) the destination.'''

TERMINALS = "(domain and range of relation types)"
'''The row for the relation types' own ends: each relation type shown is
related to its domain and its range (its source and destination), as if by a
relation from it to each of them.'''

SHAPES, PULLS, IGNORED = "shapes the tree", "pulls together", "ignored"
ROLES = (SHAPES, PULLS, IGNORED)
'''What a row's relations do: shape the trees (each relates a parent and a
child); pull things together (only for joining trees, and putting things in
no tree near what they're related to); or nothing.'''

_CODES = {SHAPES: "shapes", PULLS: "pulls", IGNORED: "ignored"}
"Each role as it's saved (see *RelationTable.encode()*)."

def defaultParentEnd(name:str) -> str:
  '''
  :param name: A relation type's name, or *TERMINALS*.
  :returns: Which end of its relations is usually the parent (see
    *PARENT_ENDS*): the destination for isa and has-* relations (a subtype isa
    its type; a child has-parent its parent), and for the relation types' own
    ends (a relation type goes under its domain and range); the source
    otherwise (eg: a package includes its modules).
  '''
  return "destination" if name in ("isa", TERMINALS) or name.startswith("has-") else "source"

@dataclass(frozen=True)
class RelationRow:
  '''
  A row of a relation table (see *RelationTable*).
  '''
  relation:str
  "A relation type's name, or *TERMINALS*."
  role:str = PULLS
  "What its relations do: one of *ROLES*."
  parentEnd:str = ""
  "For *SHAPES*: which end of its relations is the parent (see *PARENT_ENDS*): if empty, the usual (see *defaultParentEnd()*)."

  def __post_init__(self):
    if self.role not in ROLES:
      raise ValueError(f'RelationRow: role must be one of {", ".join(ROLES)}, not "{self.role}".')
    if not self.parentEnd:
      object.__setattr__(self, "parentEnd", defaultParentEnd(self.relation))
    elif self.parentEnd not in PARENT_ENDS:
      raise ValueError(f'RelationRow: parentEnd must be one of {", ".join(PARENT_ENDS)}, not "{self.parentEnd}".')

class RelationTable:
  '''
  An ordered table of relation types, each with a role (see the module doc):
  a layout's "relations" parameter (see *layout.LayoutParameter*). Its rows
  name the relation types: what they are is found in the view's model (see
  *roles()*). Saved as text (see *encode()*): its *str()*.
  '''
  def __init__(self, rows:Iterable[RelationRow]=()):
    self.rows:tuple[RelationRow, ...] = tuple(rows)

  @classmethod
  def single(cls, relation:Any, parentEnd:str|None=None) -> RelationTable:
    '''
    :param relation: A relation type (a *Relation*), or its name.
    :param parentEnd: Which end of its relations is the parent (see
      *PARENT_ENDS*): if None, the usual (see *defaultParentEnd()*).
    :returns: The table that's like a single relation type, as layouts took
      before there were tables: it shapes the trees; every other relation, and
      the relation types' ends (last), pull things together.
    '''
    name = str(getattr(relation, "name", relation))
    return cls([RelationRow(name, SHAPES, parentEnd or ""), RelationRow(TERMINALS, PULLS)])

  def encode(self) -> str:
    '''
    :returns: The table as text, for saving with a view's layout's parameters
      (see *layout.LayoutHeuristic.encodeParameters()*): each row's relation
      type's name (%-quoted), role and parent end, separated by ":", and the
      rows by ",": eg: "isa:shapes:destination,likes:pulls:source".
    '''
    return ",".join(f"{quote(r.relation, safe='')}:{_CODES[r.role]}:{r.parentEnd}" for r in self.rows)

  @classmethod
  def decode(cls, text:str) -> RelationTable:
    '''
    :param text: What *encode()* made (rows it can't read are left out).
    '''
    roles = {code: role for role, code in _CODES.items()}
    rows:list[RelationRow] = []
    for part in text.split(","):
      fields = part.split(":")
      if len(fields) == 3 and fields[1] in roles and fields[2] in PARENT_ENDS and fields[0]:
        rows.append(RelationRow(unquote(fields[0]), roles[fields[1]], fields[2]))
    return cls(rows)

  def __str__(self) -> str:
    return self.encode()

  def __repr__(self) -> str:
    return f"RelationTable({self.encode()!r})"

  def __eq__(self, other:object) -> bool:
    return isinstance(other, RelationTable) and self.rows == other.rows

  def __hash__(self) -> int:
    return hash(self.rows)

  def roles(self, model:Model) -> RelationRoles:
    ":returns: The table, for finding what each relation in *model* does (see *RelationRoles*)."
    return RelationRoles(self, model)

class RelationRoles:
  '''
  A relation table (see *RelationTable*), for a model: what each relation
  does, and how highly it's ranked.
  '''
  def __init__(self, table:RelationTable, model:Model):
    from sn.view.graphics.layout import relationTypes
    self.table, self.model = table, model
    named:dict[str, Relation] = {}
    for t in relationTypes(model) if any(r.relation not in ("isa", TERMINALS) for r in table.rows) else []:
      named.setdefault(str(t.name), t) # (the first of that name: as *layout.relationNamed()*)
    self.types:dict[int, int] = {}
    "The rows (by index) of the relation types there are in the model (by *id()*): those named by rows that aren't *TERMINALS*."
    for i, row in enumerate(table.rows):
      if row.relation == TERMINALS:
        continue
      rt = model.ISA if row.relation == "isa" else named.get(row.relation)
      if rt is not None and id(rt) not in self.types:
        self.types[id(rt)] = i
    self._cache:dict[int, tuple[int, RelationRow]|None] = {}
    self.terminals:tuple[int, RelationRow]|None = next(((i, r) for i, r in enumerate(table.rows) if r.relation == TERMINALS), None)
    "The row for the relation types' own ends (see *TERMINALS*), and its index, if there's one."

  def rowOfType(self, t:Relation) -> tuple[int, RelationRow]|None:
    '''
    :param t: A relation type.
    :returns: The row (and its index) that covers it: its own, or else its
      nearest supertype's (the earliest row, of those as near) -- if any.
    '''
    if id(t) in self._cache:
      return self._cache[id(t)]
    ret:tuple[int, RelationRow]|None = None
    level, seen = [t], {id(t)}
    while level and ret is None:
      hits = [self.types[id(p)] for p in level if id(p) in self.types]
      if hits:
        ret = (min(hits), self.table.rows[min(hits)])
        break
      nxt = []
      for p in level:
        for q in p.getParents():
          if isinstance(q, Relation) and id(q) not in seen:
            seen.add(id(q))
            nxt.append(q)
      level = nxt
    self._cache[id(t)] = ret
    return ret

  def typeOf(self, mo:Relation) -> Relation|None:
    ''':returns: An individual relation's relation type: isa for an isa link; else its first relation type, if any.'''
    if isinstance(mo, IsaIndividual):
      return self.model.ISA
    return next((p for p in mo.getParents() if isinstance(p, Relation)), None)

  def rowOf(self, mo:Relation) -> tuple[int, RelationRow]|None:
    '''
    :param mo: An individual relation.
    :returns: The row (and its index) that covers its relation type (see
      *rowOfType()*), if any.
    '''
    t = self.typeOf(mo)
    return self.rowOfType(t) if t is not None else None

  def role(self, mo:Relation|None) -> str:
    ''':returns: What an individual relation does (see *ROLES*): *PULLS* if no row covers it. (None: the relation types' own ends.)'''
    hit = self.terminals if mo is None else self.rowOf(mo)
    return hit[1].role if hit is not None else PULLS

  def rank(self, mo:Relation|None) -> int:
    ''':returns: Its row's index (after all the rows if none covers it): lower wins. (None: the relation types' own ends.)'''
    hit = self.terminals if mo is None else self.rowOf(mo)
    return hit[0] if hit is not None else len(self.table.rows)

  def parentEnd(self, mo:Relation|None) -> str:
    ''':returns: Which end of it is the parent (see *PARENT_ENDS*). (None: the relation types' own ends.)'''
    hit = self.terminals if mo is None else self.rowOf(mo)
    if hit is not None:
      return hit[1].parentEnd
    t = self.typeOf(mo) if mo is not None else None
    return defaultParentEnd(TERMINALS if mo is None else str(getattr(t, "name", "")))

  def group(self, mo:Relation|None) -> int:
    '''
    :returns: Which group, of the children by its row, a child related by
      *mo* is in: 0 for the row's relation type itself; else 1 + which of its
      direct subtypes (in the order they were made) *mo*'s type is a kind of.
    '''
    hit = self.terminals if mo is None else self.rowOf(mo)
    t = self.typeOf(mo) if mo is not None else None
    if hit is None or t is None or self.types.get(id(t)) == hit[0]:
      return 0
    rowType = next((r for r in self._rowTypes() if self.types[id(r)] == hit[0]), None)
    if rowType is None:
      return 0
    subs = sorted((c for c in rowType.getChildren() if isinstance(c, Relation) and c.isType()), key=lambda c: c._id)
    return next((i + 1 for i, s in enumerate(subs) if t is s or t.isa(s)), len(subs) + 1)

  def _rowTypes(self) -> list[Relation]:
    if "_types" not in self.__dict__:
      from sn.view.graphics.layout import relationTypes
      self.__dict__["_types"] = [t for t in relationTypes(self.model) if id(t) in self.types]
    return self.__dict__["_types"]

def shownRelationTypes(view:Any) -> list[Relation]:
  '''
  :param view: A view.
  :type view: SNGView
  :returns: The relation types of the relations shown in it (not hidden): isa
    for isa links; else each relation's first relation type -- each once, in
    the order they were made.
  '''
  from sn.view.graphics.vrelations import VRelation
  ret:dict[int, Relation] = {}
  for r in view.values():
    mo = r.modelObject if isinstance(r, VRelation) else None
    if mo is None or not mo.isIndividual() or not r._isConnected() or r.isHidden():
      continue
    t = view.model.ISA if isinstance(mo, IsaIndividual) else next((p for p in mo.getParents() if isinstance(p, Relation)), None)
    if t is not None:
      ret.setdefault(id(t), t)
  return sorted(ret.values(), key=lambda t: t._id)

@dataclass(eq=False)
class TypeNode:
  '''
  A relation type in the tree a relation table's edited as (see
  *relationTree()*): its subtypes are its children.
  '''
  name:str
  "The relation type's name (or *TERMINALS*): what a row for it names."
  type:Relation|None = None
  "The relation type (None for *TERMINALS*, or a row's that isn't in the model)."
  children:list[TypeNode] = field(default_factory=list)
  "Its subtypes in the tree."
  parent:TypeNode|None = None
  "Its supertype in the tree (its first, if it has several), if any."

  def walk(self) -> Iterator[TypeNode]:
    ''':returns: It, and its descendants, in order (preorder).'''
    yield self
    for c in self.children:
      yield from c.walk()

def relationTree(table:RelationTable, model:Model, shown:Iterable[Relation]) -> list[TypeNode]:
  '''
  The relation types a relation table may have rows for, as a tree (for
  editing it: see *layoutDialog.RelationTableEditor*): those *shown*, their
  supertypes (not the system's: eg: *relation*), and those the table's rows
  name -- each under its supertype (its first, if it has several), so a row
  for a supertype can stand for all of its subtypes (see the module doc);
  and *TERMINALS*. Each level is in the order of the table's rows -- a type
  before another if its row, or one of its subtypes', is before theirs --
  then the order the types were made.

  :param table: The table.
  :param model: The view's model.
  :param shown: The relation types of the relations shown in the view (see *shownRelationTypes()*).
  :returns: The tree's roots.
  '''
  from sn.view.graphics.layout import relationTypes
  byName:dict[str, Relation] = {}
  for t in relationTypes(model):
    byName.setdefault(str(t.name), t)
  types:dict[int, Relation] = {}
  def add(t:Relation) -> None:
    if id(t) in types or (t.isSystemObject() and t is not model.ISA):
      return
    types[id(t)] = t
    for p in t.getParents():
      if isinstance(p, Relation) and p.isType() and p is not t:
        add(p)
  for t in shown:
    add(t)
  for r in table.rows:
    if r.relation in byName:
      add(byName[r.relation])
  nodes:dict[str, TypeNode] = {}
  for t in sorted(types.values(), key=lambda t: t._id):
    nodes.setdefault(str(t.name), TypeNode(str(t.name), t))
  for r in table.rows: # (a row for one that isn't in the model, kept as it is)
    nodes.setdefault(r.relation, TypeNode(r.relation))
  nodes.setdefault(TERMINALS, TypeNode(TERMINALS))
  roots:list[TypeNode] = []
  for n in nodes.values():
    up = next((nodes[str(p.name)] for p in (n.type.getParents() if n.type is not None else [])
               if isinstance(p, Relation) and id(p) in types and nodes.get(str(p.name)) is not n), None)
    n.parent = up
    (up.children if up is not None else roots).append(n)
  index = {r.relation: i for i, r in reversed(list(enumerate(table.rows)))}
  def rank(n:TypeNode) -> int:
    return min((index[d.name] for d in n.walk() if d.name in index), default=len(table.rows))
  def order(level:list[TypeNode]) -> list[TypeNode]:
    for n in level:
      n.children = order(n.children)
    return sorted(level, key=lambda n: (rank(n), n.type is None, n.type._id if n.type is not None else 0))
  return order(roots)
