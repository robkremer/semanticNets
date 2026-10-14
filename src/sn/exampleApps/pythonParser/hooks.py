'''
The hooks (see *sn.hooks*) that pythonParser's ontology (pythonOntology.snm)
names, so that a model of Python code made by the parser can show its code:

  - on python-code-block (so on modules, packages, classes, functions and
    ``__main__`` blocks): ``.menu/Show source`` (*showSource()*: in a window
    here), ``.menu/Open in editor`` (*openInEditor()*: the "gui/editorCommand"
    setting's editor), and ``.menu/Reveal in Finder`` (*reveal()*);
  - on class, function and code: ``.doubleClick`` (*openInEditor()*), and a
    tooltip with the code (*sourceTip()*).

A class or function is found in its file as it is now (see *source.locate()*),
not where it was when the model was made.

Created on Oct 14, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import os
import subprocess
import sys
import textwrap
from typing import Any
import sn
from sn.hooks import hook, HookContext
from sn.exampleApps.pythonParser import source

logger:sn.SNLogger = sn.getLogger(__name__)

RULE = "▔" * 18
"The line between a tooltip's name and its code."

def fileOf(obj:Any) -> str|None:
  '''
  :param obj: A node of a model made by the parser.
  :type obj: Any
  :returns: The Python file it's in (or is: a module's; a package's
    __init__.py), if it has one that's there; else None (eg: a type, or a
    built-in or compiled module).
  :rtype: str | None
  '''
  try:
    if not obj.isIndividual():
      return None
    mod = source.moduleOf(obj)
    path = mod.get("path", None) if mod is not None else None
  except Exception:
    return None
  if not isinstance(path, str):
    return None
  if os.path.isdir(path):
    path = os.path.join(path, "__init__.py")
  return path if path.endswith(".py") and os.path.isfile(path) else None

def hasFile(obj:Any, _context:HookContext) -> bool:
  ''':returns: Whether *obj* has a Python file (see *fileOf()*): the hooks' *appliesTo*.'''
  return fileOf(obj) is not None

def _where(obj:Any) -> tuple[str, int, int]|None:
  '''
  :returns: The file, line and last line to show for *obj*: its chunk's, as
    it is now (see *source.locateNode()*), or the whole file's start, for a
    module; None (logged) if its chunk can't be found.
  '''
  path = fileOf(obj)
  if path is None:
    return None
  loc = source.locateNode(obj)
  if loc is None: # (a module, or a package)
    return path, 1, 1
  if not loc.found:
    logger.warning(f'{obj.name}: {loc.problem}')
    return None
  if loc.how == source.GUESS:
    logger.warning(f'{obj.name}: not found in {os.path.basename(loc.path)} -- showing where it was (line {loc.line}).')
  return loc.path, loc.line, loc.end

def _parent(context:HookContext) -> Any:
  view = context.view
  return getattr(view, "canvas", None)

@hook(appliesTo=hasFile)
def showSource(obj:Any, context:HookContext) -> None:
  '''
  Show *obj*'s source -- its chunk, highlighted -- in a window here (see
  *sourceWindow.showSource()*), whatever the editor setting.
  '''
  from sn.view.graphics.sourceWindow import showSource as show
  where = _where(obj)
  if where is not None:
    path, line, end = where
    show(path, line, end, _parent(context))

@hook(appliesTo=hasFile)
def openInEditor(obj:Any, context:HookContext) -> None:
  '''
  Open *obj*'s source at its chunk in the editor (the "gui/editorCommand"
  setting; or, if there isn't one, a window here: see *sourceWindow.openSource()*).
  '''
  from sn.view.graphics.sourceWindow import openSource
  where = _where(obj)
  if where is not None:
    path, line, end = where
    openSource(path, line, end, _parent(context))

@hook(appliesTo=hasFile)
def reveal(obj:Any, _context:HookContext) -> None:
  '''Show *obj*'s file in the Finder (on a Mac; elsewhere, open its folder).'''
  path = fileOf(obj)
  if path is None:
    return
  try:
    if sys.platform == "darwin":
      subprocess.Popen(["open", "-R", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
      import webbrowser
      webbrowser.open(os.path.dirname(path))
  except OSError as ex:
    logger.warning(f"Couldn't show {path}: {ex}")

@hook
def sourceTip(obj:Any, _context:HookContext) -> str:
  '''
  :returns: For a tooltip: *obj*'s code as it is now, under a rule -- with a
    word on it if it wasn't found by its name, or it's changed since the model
    was made; empty if it isn't a chunk with a file (eg: a type), or it can't
    be found.
  '''
  if fileOf(obj) is None:
    return ""
  loc = source.locateNode(obj)
  if loc is None or loc.how is None or loc.how == source.GUESS: # (how is None: not found)
    return ""
  notes = []
  if loc.how != source.NAME:
    notes.append({source.GREP: "found by its name, but the file doesn't parse just now",
                  source.FUZZY: "not found by its name: renamed?"}.get(loc.how, loc.how))
  if loc.changed:
    notes.append("changed since the model was made")
  head = f"{os.path.basename(loc.path)}:{loc.line}" + (f"  ({'; '.join(notes)})" if notes else "")
  return f"{RULE}\n{head}\n{textwrap.dedent(loc.text)}"
