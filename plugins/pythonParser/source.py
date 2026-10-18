'''
Finding the source of a class, function or ``__main__`` block -- a *chunk* --
again, in its file as it is now: the model keeps only where it was (its
"line" and "end-line") and what it looked like (its first line, and a hash of
its text: see *chunkAttrs()*), not the code itself, so that small changes to
the file don't lose it.

*locate()* looks for it, in turn:

  1. by its name (eg: Class.method), in the file parsed afresh: found
     wherever it's moved to in the file, whatever's changed in it -- unless
     it's been renamed (or moved to another class);
  2. failing that (eg: the file doesn't parse just now), by a ``def name`` /
     ``class name`` line, the nearest to where it was;
  3. failing that (eg: it's been renamed), by the line most like its first
     line was, near where it was;
  4. failing that, where it was -- marked as a guess.

and says whether it's changed since the model was made (its hash).

*locateNode()* does it for a node of a model made by the parser: its file is
its module's (found through the *defines* relations up to it).

Created on Oct 14, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import ast
import difflib
import hashlib
import importlib.util
import os
import re
import textwrap
from dataclasses import dataclass
from typing import Any

MAIN = "__main__"
"The name of a module's ``if __name__ == \"__main__\":`` part (a *code* node's)."

HASH_LENGTH = 12
"How many hex digits of a chunk's hash are kept (see *sourceHash()*)."

FUZZY_CUTOFF = 0.6
"How alike (0..1) a line must be to a chunk's first line to be taken for it (see *locate()*, step 3)."

NAME, GREP, FUZZY, GUESS = "name", "grep", "fuzzy", "guess"
"How a chunk was found (see *Location.how*)."

@dataclass
class Location:
  '''Where a chunk is now (see *locate()*).'''
  path:str
  "Its file."
  start:int = 0
  "Its first line (1-based), its decorators' if it has any; 0 if it wasn't found."
  end:int = 0
  "Its last line (1-based)."
  line:int = 0
  "Its ``def`` / ``class`` / ``if`` line (1-based): where an editor should go."
  how:str|None = None
  "How it was found: *NAME*, *GREP*, *FUZZY* or *GUESS*; None if it wasn't (see *problem*)."
  changed:bool|None = None
  "Whether it's changed since the model was made; None if that can't be told (eg: no hash was kept)."
  problem:str|None = None
  "Why it wasn't found (eg: no such file)."
  lines:list[str]|None = None
  "The file's lines (without their ends), if it was read."

  @property
  def found(self) -> bool:
    ":returns: Whether it was found (if only as a guess)."
    return self.how is not None

  @property
  def text(self) -> str:
    ":returns: Its source, as it is now; empty if it wasn't found."
    if not self.found or self.lines is None:
      return ""
    return "\n".join(self.lines[self.start - 1:self.end])

def readSource(path:str) -> str:
  '''
  :param path: A Python file.
  :returns: Its text: decoded as Python would (its encoding declaration, if
    it has one), with its line ends made "\\n".
  :raises OSError: If it can't be read.
  '''
  with open(path, "rb") as f:
    return importlib.util.decode_source(f.read())

def chunkStart(node:ast.stmt) -> int:
  '''
  :param node: A class or function (or any statement).
  :returns: Its first line: its first decorator's, if it has any.
  '''
  decorators = getattr(node, "decorator_list", [])
  return min([node.lineno] + [d.lineno for d in decorators])

def sourceHash(lines:list[str]) -> str:
  '''
  :param lines: A chunk's lines.
  :returns: A short hash of them, the same whatever their indentation (eg: a
    function made a method) and trailing white space.
  '''
  text = textwrap.dedent("\n".join(l.rstrip() for l in lines)).strip("\n")
  return hashlib.sha1(text.encode("utf-8")).hexdigest()[:HASH_LENGTH]

def chunkAttrs(node:ast.stmt, lines:list[str]) -> dict[str, Any]:
  '''
  :param node: A class, function or ``__main__`` block, as parsed.
  :param lines: Its file's lines.
  :returns: What its model node keeps to find it again (see *locate()*):
    "end-line"; ".signature-line", its ``def`` / ``class`` / ``if`` line as
    written; and ".source-hash" (see *sourceHash()*). (The keys starting with
    "." are hidden by the attribute editor.)
  '''
  start, end = chunkStart(node), node.end_lineno or node.lineno
  return {"end-line": end,
          ".signature-line": lines[node.lineno - 1].strip() if node.lineno <= len(lines) else "",
          ".source-hash": sourceHash(lines[start - 1:end])}

def _isMainBlock(stmt:ast.stmt) -> bool:
  from .parser import isMainBlock # (here: the parser imports this module)
  return isMainBlock(stmt)

def _byName(tree:ast.Module, names:list[str], near:int) -> ast.stmt|None:
  '''
  :param tree: A module.
  :param names: A chunk's names, outermost first: eg: ["Class", "method"], or ["__main__"].
  :param near: The line it was on: of several of the same name (eg: a
    property's getter and setter), the nearest is taken.
  :returns: The chunk, if there is one by that name.
  '''
  body:list[ast.stmt] = tree.body
  found:ast.stmt|None = None
  for i, name in enumerate(names):
    last = i == len(names) - 1
    if name == MAIN and last and i == 0:
      matches = [s for s in body if _isMainBlock(s)]
    else:
      kinds = (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef) if last else (ast.ClassDef,)
      matches = [s for s in body if isinstance(s, kinds) and s.name == name] # type: ignore[attr-defined]
    if not matches:
      return None
    found = min(matches, key=lambda s: abs(s.lineno - near)) if last else matches[0]
    body = getattr(found, "body", [])
  return found

def _blockEnd(lines:list[str], line:int) -> int:
  '''
  :param lines: A file's lines.
  :param line: A ``def`` / ``class`` / ``if`` line (1-based).
  :returns: The last line of the block it starts, going by indentation: the
    last non-blank line before the next one indented no more than it (for
    when the file can't be parsed).
  '''
  indent = len(lines[line - 1]) - len(lines[line - 1].lstrip())
  end = line
  for i in range(line, len(lines)):
    text = lines[i]
    if not text.strip():
      continue
    if len(text) - len(text.lstrip()) <= indent and not text.lstrip().startswith((")", "]", "}")):
      break
    end = i + 1
  return end

def _decoratorsAbove(lines:list[str], line:int) -> int:
  '''
  :returns: The first line of the decorators just above *line* (1-based), or *line* if there are none.
  '''
  start = line
  while start > 1 and lines[start - 2].lstrip().startswith("@"):
    start -= 1
  return start

def locate(path:str, names:list[str], line:int=0, signature:str="", oldHash:str="") -> Location:
  '''
  Find a chunk in its file (see the module doc).

  :param path: Its file.
  :param names: Its names within its module, outermost first: eg: ["Class",
    "method"], or ["__main__"].
  :param line: The line it was on (its "line"); 0 if not known.
  :param signature: Its first line, as it was (its ".signature-line").
  :param oldHash: Its hash, as it was (its ".source-hash"; see *sourceHash()*).
  :returns: Where it is now.
  '''
  try:
    text = readSource(path)
  except OSError as ex:
    return Location(path, problem=f"{path} can't be read: {ex.strerror or ex}")
  lines = text.split("\n")
  if lines and lines[-1] == "": # (the end of the last line)
    lines.pop()
  ret = Location(path, lines=lines)
  try:
    tree:ast.Module|None = ast.parse(text, filename=path)
  except (SyntaxError, ValueError):
    tree = None
  node = _byName(tree, names, line) if tree is not None and names else None
  if node is not None:
    ret.start, ret.end, ret.line, ret.how = chunkStart(node), node.end_lineno or node.lineno, node.lineno, NAME
  else:
    at = _grep(lines, names, line) if names else None
    how = GREP
    if at is None and signature.strip():
      at, how = _fuzzy(lines, signature, line), FUZZY
    if at is not None:
      ret.start, ret.end, ret.line, ret.how = _decoratorsAbove(lines, at), _blockEnd(lines, at), at, how
    elif 0 < line <= len(lines):
      ret.start, ret.end, ret.line, ret.how = line, _blockEnd(lines, line), line, GUESS
    else:
      ret.problem = f"{'.'.join(names) or 'It'} isn't in {path} (nor is there a line {line})."
      return ret
  if oldHash and ret.how != GUESS:
    ret.changed = sourceHash(lines[ret.start - 1:ret.end]) != oldHash
  return ret

def _grep(lines:list[str], names:list[str], near:int) -> int|None:
  '''
  :returns: The line (1-based) nearest *near* that starts the chunk named by
    the last of *names* (``def name``, ``class name``, or ``if __name__ ==``),
    if there's one -- within the block of the class named by the one before
    it, and so on (each the nearest *near*), as far as they can be found.
  '''
  lo, hi = 1, len(lines) # (the lines looked in)
  for outer in names[:-1]:
    at = _nearest(lines, re.compile(rf"\s*class\s+{re.escape(outer)}\b"), near, lo, hi)
    if at is None:
      break
    lo, hi = at + 1, _blockEnd(lines, at)
  name = names[-1]
  if name == MAIN and len(names) == 1:
    pattern = re.compile(r"if\s+(__name__\s*==\s*['\"]__main__['\"]|['\"]__main__['\"]\s*==\s*__name__)\s*:")
  else:
    pattern = re.compile(rf"\s*((async\s+)?def|class)\s+{re.escape(name)}\b")
  return _nearest(lines, pattern, near, lo, hi)

def _nearest(lines:list[str], pattern:re.Pattern, near:int, lo:int, hi:int) -> int|None:
  ''':returns: The line (1-based), from *lo* to *hi*, that *pattern* matches the start of, nearest *near*.'''
  hits = [i for i in range(lo, hi + 1) if pattern.match(lines[i - 1])]
  return min(hits, key=lambda n: abs(n - near)) if hits else None

def _fuzzy(lines:list[str], signature:str, near:int) -> int|None:
  '''
  :returns: The line (1-based) most like *signature* (at least *FUZZY_CUTOFF*
    alike), the nearest *near* of those as alike; None if none is.
  '''
  want = signature.strip()
  best:tuple[float, int]|None = None
  for i, l in enumerate(lines):
    if not l.strip():
      continue
    m = difflib.SequenceMatcher(None, want, l.strip())
    if m.real_quick_ratio() < FUZZY_CUTOFF or m.quick_ratio() < FUZZY_CUTOFF:
      continue
    r = m.ratio()
    if r >= FUZZY_CUTOFF and (best is None or (r, -abs(i + 1 - near)) > (best[0], -abs(best[1] - near))):
      best = (r, i + 1)
  return best[1] if best is not None else None

DEFINES = ("defines", "defines-method")
"The relations from what defines a chunk (a module, or a class) to it."

def moduleOf(node:Any) -> Any|None:
  '''
  :param node: A node of a model made by the parser: a class, function or
    ``__main__`` block (or a module).
  :returns: The module (or package) it's in, following *DEFINES* relations
    back from it; None if there's none.
  '''
  seen:set[int] = set()
  while node is not None and id(node) not in seen:
    seen.add(id(node))
    if node.get("path", None):
      return node
    node = next((src for r, src in node._getIncoming(lambda r: _isA(r, DEFINES))), None)
  return None

def _isA(rel:Any, names:tuple[str, ...]) -> bool:
  ''':returns: Whether *rel* is of one of the types named *names* (or a subtype of one).'''
  todo, seen = list(rel.getParents()), set()
  while todo:
    p = todo.pop()
    if id(p) in seen:
      continue
    seen.add(id(p))
    if p.name in names:
      return True
    todo += p.getParents()
  return False

def locateNode(node:Any) -> Location|None:
  '''
  Find the source of a node of a model made by the parser (see *locate()*).

  :param node: A class, function or ``__main__`` block's node.
  :returns: Where it is now; None if it isn't one of those (eg: a module, or
    a type), or its module has no file. (A chunk in a package is in its
    __init__.py.)
  '''
  q = node.get("qualified-name", None)
  mod = moduleOf(node)
  if not isinstance(q, str) or mod is None or mod is node:
    return None
  path, prefix = mod.get("path", None), mod.get("qualified-name", None)
  if not isinstance(path, str) or not isinstance(prefix, str) or not q.startswith(prefix + "."):
    return None
  if os.path.isdir(path): # (a package: its node's path is its folder)
    path = os.path.join(path, "__init__.py")
  line = node.get("line", 0)
  return locate(path, q[len(prefix) + 1:].split("."), line if isinstance(line, int) else 0,
                str(node.get(".signature-line", "") or ""), str(node.get(".source-hash", "") or ""))
