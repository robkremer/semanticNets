'''
Turn some Python source files -- and the modules they import, as far out as
asked (see *readModules()*) -- into a Semantic Nets model (see
*buildModel()*), built on the ontology in pythonOntology.snm (its
super-model: see *ONTOLOGY*).

The modules analysed are parsed (with *ast*) only for their top-level structure:

  - Each file becomes a *module*, named by its file's name (eg: reader); an
    __init__.py is its folder's *package* instead (in Python, a package is a
    module: the ontology has package isa module).
  - Each folder a module is in that's a package (one with an __init__.py, or a
    namespace package: see *ModuleFinder*) becomes a *package* (named by its
    folder's name), whether or not its __init__.py was analysed; and so does
    each folder above it that's a package. A package *contains-module* each of
    its modules, and *has-subpackage* each of its sub-packages.
  - A module defines (*defines*) its top-level classes and functions, and a
    *code* block for its ``if __name__ == "__main__":`` part, if it has one.
  - A class defines its methods (*defines-method*) and nested classes
    (*defines*), and *inherits-from* each of its bases that's one of the
    analysed classes. A method is also a *class-method* if it's a
    @classmethod, a *static-method* if it's a @staticmethod, a *property* if
    it's a @property (or its setter or deleter), an *abstract-method* if it's
    an @abstractmethod, and an *overriding-method* if a class it's derived
    from (one of the analysed classes: it can only tell for those) has a
    method of the same name: as many of those as apply.
  - A module, class or function with a doc string *has-doc* a *doc-string*,
    which has it as its "text": named by its first line (or, if that's a field,
    eg: ":param x: ...", by what it's the doc string of: eg: "go doc").
  - A module *imports* each module it imports (anywhere in it): the most
    specific one each import names that there is (eg: for "from a.b import
    c", the module a.b.c if there is one, otherwise a.b). One that isn't
    analysed -- further away than asked for, in the standard library or an
    installed package (unless asked for), compiled, built in, or not found --
    is an *external-module* (and is in its packages, if it has any).

Each module, class and function has its full dotted name as its
"qualified-name" (eg: sn.model.model.Node); a
module or package its file or folder as its "path", where it's from as its
"origin" (see *ORIGINS*), and how many imports away from the files given it
is as its "import-depth"; a class or function (or ``__main__`` block) the
lines it starts and ends on as its "line" and "end-line", and -- hidden --
its first line as written and a hash of its text, so that it can be found
again in its file after the file's changed (see *source*); a class its
"bases"; and a function its "parameters" (as written).

A file that isn't valid Python is still a module (with a note saying so), but
with nothing in it.

Created on Oct 10, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import ast
import glob
import importlib.util
import os
import site
import sys
import sysconfig
from collections import deque
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import unquote, urlparse
from sn.model.model import Model, Node, Relation, GraphObject
from .source import chunkAttrs

ONTOLOGY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pythonOntology.snm")
"The model the models made build on: the types of things in Python programs (package, module, class, ...)."

PROJECT, STDLIB, INSTALLED, BUILTIN, COMPILED, NOT_FOUND = \
  "project", "standard library", "installed", "built-in", "compiled", "not found"
ORIGINS = (PROJECT, STDLIB, INSTALLED, BUILTIN, COMPILED, NOT_FOUND)
'''Where a module can be from (its "origin"): the project (anything not in the
standard library or an installed package: eg: the files given, and those
next to them); the standard library; an installed package (site-packages);
built into Python; compiled (an extension module: no Python source); or not
found (eg: a package that isn't installed).'''

SKIP_FOLDERS = {"__pycache__", "build", "dist", "node_modules", "site-packages"}
'''Folders not looked in for .py files when a folder is given (see
*pythonFiles()*): nor are hidden ones (eg: .git, .venv).'''

SKIP_IMPORTS = {"__future__"}
"Imports that aren't of anything (eg: \"from __future__ import annotations\" turns on a feature)."

MAX_ANALYSED = 1000
"The most modules analysed (see *readModules()*): the rest are left as external modules."

MAIN_NAMES = {"__main__": 40, "main": 30, "app": 20, "cli": 20, "run": 15, "manage": 15, "start": 10}
"Module names that suggest a program's main module, and how strongly (see *guessMain()*)."

DOC_NAME_LENGTH = 60
"The longest a doc string's node's name (its first line) gets: longer is cut off with an ellipsis."

@dataclass
class SourceModule:
  '''A module (or package): one of the files given, or one they import.'''
  name:str
  '''Its dotted name: eg: "sn.model.model" -- a package's for its __init__.py
  (eg: "sn.model").'''
  path:str|None
  '''Its file -- a .py file (an __init__.py for a package), or a compiled one
  -- or its folder, for a namespace package; None if it's built in, or wasn't
  found.'''
  packages:list[str]
  '''The folders of the packages it's in, outermost first (eg: .../src/sn,
  .../src/sn/model): its own folder is the last, if it's a package.'''
  origin:str = PROJECT
  "Where it's from: one of *ORIGINS*."
  depth:int = -1
  "How many imports away from the files given it is: 0 for one of them; -1 until it's known."
  analysed:bool = False
  "Whether it's been parsed (or tried to be: see *error*)."
  tree:ast.Module|None = None
  "Its syntax tree, if it's been parsed."
  error:str|None = None
  "Why it couldn't be parsed, if it couldn't."
  lines:list[str] = field(default_factory=list)
  "Its file's lines, if it's been parsed (see *source.chunkAttrs()*)."
  imported:list[str] = field(default_factory=list)
  "The dotted names of the modules it imports (see *importedModules()*)."

  @property
  def isPackage(self) -> bool:
    ":returns: Whether it's a package (an __init__.py, or a namespace package's folder)."
    return self.path is not None and (os.path.basename(self.path) == "__init__.py" or os.path.isdir(self.path))

  @property
  def shortName(self) -> str:
    ":returns: The last part of its dotted name: eg: \"model\"."
    return self.name.rsplit(".", 1)[-1]

  def hasMainBlock(self) -> bool:
    ':returns: Whether it has an ``if __name__ == "__main__":`` part.'
    return self.tree is not None and any(isMainBlock(s) for s in self.tree.body)

  def parse(self) -> None:
    '''Parse its file: set *tree*, or *error*.'''
    self.analysed = True
    try:
      with open(self.path or "", "rb") as f: # (bytes: ast honours the file's own encoding declaration)
        data = f.read()
      self.tree = ast.parse(data, filename=self.path or "")
      self.lines = importlib.util.decode_source(data).split("\n")
    except (SyntaxError, ValueError, OSError) as ex:
      self.error = f"{ex.__class__.__name__}: {ex}"

def pythonFiles(paths:list[str]) -> list[str]:
  '''
  :param paths: Python files and folders.
  :type paths: list[str]
  :returns: The files, and the .py files in (and below) the folders -- but not
    in hidden folders, or those in *SKIP_FOLDERS* -- each once, as absolute
    paths, in order.
  :rtype: list[str]
  '''
  ret:list[str] = []
  def add(p:str) -> None:
    p = os.path.realpath(p)
    if p not in ret:
      ret.append(p)
  for p in paths:
    if os.path.isdir(p):
      for folder, subfolders, files in os.walk(p):
        subfolders[:] = sorted(d for d in subfolders if not d.startswith(".") and d not in SKIP_FOLDERS)
        for f in sorted(files):
          if f.endswith(".py"):
            add(os.path.join(folder, f))
    else:
      add(p)
  return ret

def packageFolders(path:str) -> list[str]:
  '''
  :param path: A Python file.
  :type path: str
  :returns: The folders of the packages it's in (those with an __init__.py),
    outermost first: its own folder, and those above it, as far up as they're
    packages.
  :rtype: list[str]
  '''
  ret:list[str] = []
  folder = os.path.dirname(path)
  while os.path.isfile(os.path.join(folder, "__init__.py")):
    ret.insert(0, folder)
    parent = os.path.dirname(folder)
    if parent == folder:
      break
    folder = parent
  return ret

def readModule(path:str) -> SourceModule:
  '''
  :param path: One of the Python files given.
  :type path: str
  :returns: It, parsed (or with the reason it couldn't be), named by the
    packages it's in (see *packageFolders()*).
  :rtype: SourceModule
  '''
  packages = packageFolders(path)
  parts = [os.path.basename(p) for p in packages]
  stem = os.path.splitext(os.path.basename(path))[0]
  if stem != "__init__" or not parts:
    parts.append(stem)
  mod = SourceModule(".".join(parts), path, packages, depth=0)
  mod.parse()
  return mod

def sourceRoot(mod:SourceModule) -> str:
  '''
  :param mod: One of the files given (see *readModule()*).
  :type mod: SourceModule
  :returns: The folder its absolute imports are from: the one its outermost
    package is in (or, if it isn't in one, its own).
  :rtype: str
  '''
  return os.path.dirname(mod.packages[0] if mod.packages else mod.path or "")

def _under(path:str, folders:set[str]) -> bool:
  return any(path == f or path.startswith(f + os.sep) for f in folders)

class ModuleFinder:
  '''
  Finds a module by its dotted name, as Python's import system would (much as
  *importlib.machinery.PathFinder* does, but without importing anything):
  in *roots* -- the folders the files given are from (see *sourceRoot()*) --
  and then *sys.path* (this program's: the standard library, the installed
  packages, ...), the first a.b.c.py, a/b/c/__init__.py or compiled a/b/c.*.so
  (or .pyd) there is; or, failing those, the first folder a/b/c (a namespace
  package).
  '''
  def __init__(self, roots:list[str]):
    '''
    :param roots: The folders to look in first.
    :type roots: list[str]
    '''
    self.roots:list[str] = []
    for r in roots + [p for p in sys.path if p]:
      r = os.path.realpath(r)
      if os.path.isdir(r) and r not in self.roots:
        self.roots.append(r)
    paths = sysconfig.get_paths()
    self.installed = {os.path.realpath(p) for p in [paths.get("purelib", ""), paths.get("platlib", ""),
                                                    *getattr(site, "getsitepackages", lambda: [])(),
                                                    site.getusersitepackages()] if p}
    self.stdlib = {os.path.realpath(p) for p in [paths.get("stdlib", ""), paths.get("platstdlib", "")] if p}
    self.found:dict[str, SourceModule|None] = {}

  def origin(self, path:str) -> str:
    '''
    :param path: A module's file or folder.
    :type path: str
    :returns: Where it's from (see *ORIGINS*): the standard library, an
      installed package, or the project.
    :rtype: str
    '''
    p = os.path.realpath(path)
    if _under(p, self.installed): # (first: site-packages is in the standard library's folder)
      return INSTALLED
    if _under(p, self.stdlib):
      return STDLIB
    return PROJECT

  def find(self, name:str) -> SourceModule|None:
    '''
    :param name: A module's dotted name: eg: "a.b.c".
    :type name: str
    :returns: The module (not analysed), or None if there isn't one.
    :rtype: SourceModule | None
    '''
    if name in self.found:
      return self.found[name]
    ret:SourceModule|None = None
    parts = name.split(".")
    if name in sys.builtin_module_names:
      ret = SourceModule(name, None, [], BUILTIN)
    else:
      namespace:SourceModule|None = None
      for root in self.roots:
        folders = [os.path.join(root, *parts[:i]) for i in range(1, len(parts))]
        if not all(os.path.isdir(f) for f in folders):
          continue
        base = os.path.join(root, *parts)
        if os.path.isfile(os.path.join(base, "__init__.py")):
          ret = SourceModule(name, os.path.join(base, "__init__.py"), folders + [base], self.origin(base))
        elif os.path.isfile(base + ".py"):
          ret = SourceModule(name, base + ".py", folders, self.origin(base))
        else:
          compiled = glob.glob(glob.escape(base) + ".*.so") + glob.glob(glob.escape(base) + ".so") \
                   + glob.glob(glob.escape(base) + ".*.pyd") + glob.glob(glob.escape(base) + ".pyd")
          if compiled:
            ret = SourceModule(name, compiled[0], folders, COMPILED)
          elif namespace is None and os.path.isdir(base):
            namespace = SourceModule(name, base, folders + [base], self.origin(base))
        if ret is not None:
          break
      if ret is None:
        ret = namespace
    self.found[name] = ret
    return ret

  def resolve(self, name:str) -> SourceModule:
    '''
    :param name: A dotted name an import names: eg: "a.b.c".
    :type name: str
    :returns: The module it imports: the longest of *name*, and its prefixes
      (eg: "a.b", "a"), that's a module -- or, if none is, a module (not
      found) named by its first part (eg: "a").
    :rtype: SourceModule
    '''
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
      m = self.find(".".join(parts[:i]))
      if m is not None:
        return m
    top = parts[0]
    if top not in self.found or self.found[top] is None:
      self.found[top] = SourceModule(top, None, [], STDLIB if top in sys.stdlib_module_names else NOT_FOUND)
    return self.found[top] #type: ignore[return-value]

def isMainBlock(stmt:ast.stmt) -> bool:
  '''
  :param stmt: A module's top-level statement.
  :type stmt: ast.stmt
  :returns: Whether it's ``if __name__ == "__main__":`` (either way round).
  :rtype: bool
  '''
  if not isinstance(stmt, ast.If) or not isinstance(stmt.test, ast.Compare) or len(stmt.test.ops) != 1 \
     or not isinstance(stmt.test.ops[0], ast.Eq):
    return False
  sides = [stmt.test.left, stmt.test.comparators[0]]
  return any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides) \
     and any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)

def importBase(mod:SourceModule, level:int, module:str|None) -> str|None:
  '''
  :param mod: The module with the import.
  :type mod: SourceModule
  :param level: The import's level: 0 for an absolute import; the number of
    leading dots of a relative one.
  :type level: int
  :param module: The module named after them, if any (eg: "b" in "from ..b import c").
  :type module: str | None
  :returns: The dotted name the import is from, or None if it goes above the
    outermost package.
  :rtype: str | None
  '''
  if level == 0:
    return module
  here = mod.name.split(".") if mod.isPackage else mod.name.split(".")[:-1] # (the package it's in)
  if level - 1 >= len(here):
    return None
  base = here[:len(here) - (level - 1)]
  return ".".join(base + ([module] if module else [])) or None

def importedModules(mod:SourceModule, find:Callable[[str], SourceModule|None],
                    resolve:Callable[[str], SourceModule]) -> list[SourceModule]:
  '''
  :param mod: A parsed module.
  :type mod: SourceModule
  :param find: Finds a module by its dotted name, if there is one (eg: *ModuleFinder.find()*).
  :type find: Callable[[str], SourceModule | None]
  :param resolve: The module an import of a dotted name imports (eg: *ModuleFinder.resolve()*).
  :type resolve: Callable[[str], SourceModule]
  :returns: The modules it imports (anywhere in it), each once, in order --
    not itself, nor those in *SKIP_IMPORTS*. For "from a.b import c", that's
    the module a.b.c if there is one (c is a module in the package a.b),
    otherwise a.b.
  :rtype: list[SourceModule]
  '''
  if mod.tree is None:
    return []
  ret:list[SourceModule] = []
  for node in ast.walk(mod.tree):
    targets:list[SourceModule] = []
    if isinstance(node, ast.Import):
      targets = [resolve(a.name) for a in node.names if a.name.split(".")[0] not in SKIP_IMPORTS]
    elif isinstance(node, ast.ImportFrom):
      base = importBase(mod, node.level, node.module)
      if base is None or base in SKIP_IMPORTS:
        continue
      for a in node.names:
        sub = find(f"{base}.{a.name}") if a.name != "*" else None
        targets.append(sub if sub is not None else resolve(base))
    for t in targets:
      if t.name != mod.name and t not in ret:
        ret.append(t)
  return ret

def readModules(paths:list[str], depth:int=0, libraries:bool=False,
                progress:Callable[[str], None]|None=None) -> list[SourceModule]:
  '''
  Read the Python files *paths*, and the modules they import, as far out as
  *depth*: the files are analysed (parsed), and so are the modules they import
  (depth 1), the modules those import (depth 2), and so on up to *depth* --
  but only those from the project (see *ORIGINS*), unless *libraries*, and
  only those with Python source. The modules imported by the furthest ones
  analysed, and those not analysed, are there too (as external modules: see
  *buildModel()*), but not what they import.

  Imports are found by *ModuleFinder*: first among the files given (by their
  dotted names: see *readModule()*), then next to them (see *sourceRoot()*),
  then on *sys.path*.

  :param paths: Python files and folders (see *pythonFiles()*).
  :type paths: list[str]
  :param depth: How many imports out from the files to analyse: 0 for just the files.
  :type depth: int
  :param libraries: Whether to analyse modules in the standard library and
    installed packages too.
  :type libraries: bool
  :param progress: Told about each module as it's analysed, if given: eg: to show progress.
  :type progress: Callable[[str], None] | None
  :returns: The modules: the files first (if two have the same dotted name --
    eg: two main.py's in different folders -- only the first is kept), and
    then the others, nearest first; with their imports resolved.
  :rtype: list[SourceModule]
  '''
  modules:dict[str, SourceModule] = {}
  for p in pythonFiles(paths):
    mod = readModule(p)
    modules.setdefault(mod.name, mod)
  finder = ModuleFinder([sourceRoot(m) for m in modules.values()])
  for name, mod in modules.items(): # (the files given are what their names import)
    finder.found[name] = mod
  analysed = len(modules)
  queue = deque(modules.values())
  while queue:
    mod = queue.popleft()
    mod.imported = []
    for t in importedModules(mod, finder.find, finder.resolve):
      t = modules.setdefault(t.name, t)
      mod.imported.append(t.name)
      if t.depth < 0:
        t.depth = mod.depth + 1
        if t.depth <= depth and not t.analysed and t.path is not None and t.path.endswith(".py") \
           and (t.origin == PROJECT or libraries) and analysed < MAX_ANALYSED:
          if progress is not None:
            progress(t.name)
          t.parse()
          analysed += 1
          queue.append(t)
  return list(modules.values())

def guessMain(modules:list[SourceModule]) -> SourceModule:
  '''
  Guess which of the files given (those of *modules* at depth 0) is the
  program's main module: the one most like it of

    - one with an ``if __name__ == "__main__":`` part, or named __main__.py
      (or main.py, app.py, ...: see *MAIN_NAMES*);
    - one that no other imports, but that imports others (the more the better);

  the less deep in packages the better (eg: a package's __main__.py rather
  than one of its sub-packages'); and, other things being equal, the first.

  :param modules: Modules (see *readModules()*), with at least one file given.
  :type modules: list[SourceModule]
  :returns: The best guess.
  :rtype: SourceModule
  '''
  given = [m for m in modules if m.depth == 0]
  names = {m.name for m in given}
  importedBy:dict[str, int] = {}
  for m in given:
    for t in m.imported:
      importedBy[t] = importedBy.get(t, 0) + 1
  def score(m:SourceModule) -> float:
    s = 0.0
    if m.hasMainBlock():
      s += 50
    s += MAIN_NAMES.get(m.shortName.lower(), 0) if not m.isPackage else 0
    if not importedBy.get(m.name):
      s += 10 + min(sum(1 for t in m.imported if t in names), 20)
    if m.isPackage:
      s -= 5 # (an __init__.py is seldom where a program starts)
    if m.shortName.startswith("test") or m.shortName == "setup" or m.shortName == "conftest":
      s -= 30
    return s - 10 * len(m.packages) # (a program's main module is outermost: deeper ones start parts of it)
  return max(given, key=score) # (the first of the best)

def modelName(mod:SourceModule) -> str:
  '''
  :param mod: A program's main module (see *guessMain()*).
  :type mod: SourceModule
  :returns: A name for its model: its module's name -- or, for a __main__.py
    or __init__.py, its package's.
  :rtype: str
  '''
  if (mod.isPackage or mod.shortName == "__main__") and mod.packages:
    return os.path.basename(mod.packages[-1])
  return mod.shortName

def outputPaths(mod:SourceModule) -> tuple[str, str]:
  '''
  :param mod: A program's main module (see *guessMain()*).
  :type mod: SourceModule
  :returns: The model and view files to make for it: named by *modelName()*,
    with "_py" (eg: "reader_py.snm" and "reader_py.snv"), next to its file --
    or, for a __main__.py or __init__.py, next to its package's folder.
  :rtype: tuple[str, str]
  '''
  name = modelName(mod)
  if (mod.isPackage or mod.shortName == "__main__") and mod.packages:
    folder = os.path.dirname(mod.packages[-1])
  else:
    folder = os.path.dirname(mod.path or "")
  base = os.path.join(folder, f"{name}_py")
  return base + ".snm", base + ".snv"

def docName(doc:str, owner:str) -> str:
  '''
  :param doc: A doc string.
  :type doc: str
  :param owner: The name of what it's the doc string of.
  :type owner: str
  :returns: Its first (non-blank) line, cut down to *DOC_NAME_LENGTH* -- or,
    if that's a field (eg: ":param x: ..."), "<owner> doc".
  :rtype: str
  '''
  line = next((l.strip() for l in doc.splitlines() if l.strip()), "")
  if line.startswith(":") or line.startswith(".."):
    return f"{owner} doc"
  return line if len(line) <= DOC_NAME_LENGTH else line[:DOC_NAME_LENGTH - 1].rstrip() + "…"

def ontologyTypes(model:Model) -> dict[str, GraphObject]:
  '''
  :param model: A model with *ONTOLOGY* as a super-model.
  :type model: Model
  :returns: The ontology's types, by name.
  :rtype: dict[str, GraphObject]
  '''
  onto = next(db for db in model.superDBs if isinstance(db, Model) and db.url.startswith("file:")
              and os.path.realpath(unquote(urlparse(db.url).path)) == os.path.realpath(ONTOLOGY))
  return {str(o.name): o for o in onto.values() if o.model is onto and o.isType() and not o.isSystemObject()}

def buildModel(modelPath:str, modules:list[SourceModule]) -> Model:
  '''
  Make a model of *modules* (as described in the module doc), as a new model
  file *modelPath* (not saved: call its *save()*).

  :param modelPath: The model's file: it mustn't exist yet.
  :type modelPath: str
  :param modules: The modules (see *readModules()*).
  :type modules: list[SourceModule]
  :returns: The model.
  :rtype: Model
  '''
  m = Model(modelPath)
  m.setSuperModels([ONTOLOGY])
  T = ontologyTypes(m)
  byName = {mod.name: mod for mod in modules}

  def node(types:list[str], name:str, **attrs:object) -> Node:
    n = Node(m, [T[t] for t in types], individual=True, name=name)
    for k, v in attrs.items():
      if v is not None:
        n[k.replace("_", "-")] = v #type: ignore[assignment]
    return n

  def relate(typ:str, src:GraphObject, dst:GraphObject) -> Relation:
    return Relation(m, [T[typ]], src, dst, individual=True)

  def doc(owner:GraphObject, tree:ast.AST) -> None:
    text = ast.get_docstring(tree) if isinstance(tree, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else None
    if text:
      relate("has-doc", owner, node(["doc-string"], docName(text, str(owner.name)), text=text))

  def moduleAttrs(mod:SourceModule|None) -> dict[str, object]:
    if mod is None:
      return {}
    return {"origin": mod.origin, "import_depth": mod.depth if mod.depth >= 0 else None}

  # the packages, and what they contain
  packages:dict[str, Node] = {} # dotted name -> its node
  def packageFor(folders:list[str]) -> Node:
    name = ".".join(os.path.basename(f) for f in folders)
    if name not in packages:
      packages[name] = node(["package"], os.path.basename(folders[-1]), path=folders[-1], qualified_name=name,
                            **moduleAttrs(byName.get(name)))
      if len(folders) > 1:
        relate("has-subpackage", packageFor(folders[:-1]), packages[name])
    return packages[name]
  objects:dict[str, Node] = {} # a module's dotted name -> its node (a package's, for its __init__.py)
  for mod in modules:
    if mod.isPackage and mod.packages:
      objects[mod.name] = packageFor(mod.packages)
    elif mod.name not in objects:
      objects[mod.name] = node(["module" if mod.analysed else "external-module"],
                               mod.name if mod.origin == NOT_FOUND else mod.shortName,
                               path=mod.path, qualified_name=mod.name, **moduleAttrs(mod))
      if mod.packages:
        relate("contains-module", packageFor(mod.packages), objects[mod.name])
    if mod.error is not None:
      objects[mod.name]["note"] = f"{os.path.basename(mod.path or '')} couldn't be read: {mod.error}"

  # the classes (first: a method needs to know if a class it's derived from has one of the same name)
  analysed = [mod for mod in modules if mod.tree is not None]
  classes = ClassIndex(analysed)
  classNodes:dict[str, Node] = {} # qualified name -> its node

  # what's in the modules
  for mod in analysed:
    assert mod.tree is not None
    owner = objects[mod.name]
    doc(owner, mod.tree)
    for stmt in mod.tree.body:
      if isinstance(stmt, ast.ClassDef):
        relate("defines", owner, classNode(mod, stmt, mod.name, node, relate, doc, classes, classNodes))
      elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        f = node(["function"], stmt.name, qualified_name=f"{mod.name}.{stmt.name}", line=stmt.lineno,
                 parameters=ast.unparse(stmt.args), **chunkAttrs(stmt, mod.lines))
        doc(f, stmt)
        relate("defines", owner, f)
      elif isMainBlock(stmt):
        relate("defines", owner, node(["code"], "__main__", qualified_name=f"{mod.name}.__main__", line=stmt.lineno,
                                      **chunkAttrs(stmt, mod.lines)))

  # the classes' bases (now: they may be defined later, or in a module read later)
  for q, n in classNodes.items():
    for b in classes.bases(q):
      if b in classNodes and b != q:
        relate("inherits-from", n, classNodes[b])

  # the imports
  for mod in analysed:
    owner = objects[mod.name]
    for t in mod.imported:
      target = objects.get(t) or packages.get(t)
      if target is not None and target is not owner:
        relate("imports", owner, target)
  return m

class ClassIndex:
  '''
  The analysed modules' classes, so a class's bases (as written: eg: "Base",
  "mod.Base") can be found among them, and so its inherited method names.
  '''
  def __init__(self, modules:list[SourceModule]):
    '''
    :param modules: The analysed modules, with their imports resolved.
    :type modules: list[SourceModule]
    '''
    self.classes:dict[str, ast.ClassDef] = {}       # qualified name -> the class
    self.module:dict[str, SourceModule] = {}        # qualified name -> the module it's in
    self.aliases:dict[str, dict[str, str]] = {}     # module name -> {name used in it -> the qualified name it stands for}
    for mod in modules:
      if mod.tree is None:
        continue
      def add(c:ast.ClassDef, prefix:str) -> None:
        q = f"{prefix}.{c.name}"
        self.classes[q], self.module[q] = c, mod
        for s in c.body:
          if isinstance(s, ast.ClassDef):
            add(s, q)
      for s in mod.tree.body:
        if isinstance(s, ast.ClassDef):
          add(s, mod.name)
      aliases = self.aliases[mod.name] = {}
      for n in ast.walk(mod.tree):
        if isinstance(n, ast.Import):
          for a in n.names:
            aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        elif isinstance(n, ast.ImportFrom):
          base = importBase(mod, n.level, n.module)
          if base is not None:
            for a in n.names:
              if a.name != "*":
                aliases[a.asname or a.name] = f"{base}.{a.name}"

  def resolve(self, mod:SourceModule, prefix:str, base:ast.expr) -> str|None:
    '''
    :param mod: The module a class is in.
    :type mod: SourceModule
    :param prefix: The qualified name of what the class is in (its module, or
      a class it's nested in).
    :type prefix: str
    :param base: One of its bases, as written.
    :type base: ast.expr
    :returns: The qualified name of that base, if it's one of the analysed classes.
    :rtype: str | None
    '''
    try:
      written = ast.unparse(base)
    except Exception:
      return None
    first, _, rest = written.partition(".")
    candidates = [f"{prefix}.{written}", f"{mod.name}.{written}"]
    alias = self.aliases.get(mod.name, {}).get(first)
    if alias is not None:
      candidates.append(alias + ("." + rest if rest else ""))
    return next((c for c in candidates if c in self.classes), None)

  def bases(self, qualified:str) -> list[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :type qualified: str
    :returns: The qualified names of those of its bases that are analysed classes.
    :rtype: list[str]
    '''
    c, mod = self.classes[qualified], self.module[qualified]
    prefix = qualified.rsplit(".", 1)[0]
    return [q for q in (self.resolve(mod, prefix, b) for b in c.bases) if q is not None]

  def inheritedMethods(self, qualified:str, _seen:set[str]|None=None) -> set[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :type qualified: str
    :returns: The names of the methods its bases (those among the analysed
      classes), and theirs, define.
    :rtype: set[str]
    '''
    seen = _seen if _seen is not None else {qualified}
    ret:set[str] = set()
    for q in self.bases(qualified):
      if q in seen:
        continue
      seen.add(q)
      ret |= {s.name for s in self.classes[q].body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))}
      ret |= self.inheritedMethods(q, seen)
    return ret

def decoratorNames(f:ast.FunctionDef|ast.AsyncFunctionDef) -> set[str]:
  '''
  :param f: A function.
  :type f: ast.FunctionDef | ast.AsyncFunctionDef
  :returns: The last part of each of its decorators' names: eg: "abstractmethod"
    for @abc.abstractmethod, "setter" for @x.setter.
  :rtype: set[str]
  '''
  ret:set[str] = set()
  for d in f.decorator_list:
    d = d.func if isinstance(d, ast.Call) else d
    if isinstance(d, ast.Name):
      ret.add(d.id)
    elif isinstance(d, ast.Attribute):
      ret.add(d.attr)
  return ret

PROPERTY_DECORATORS = {"property", "cached_property", "setter", "getter", "deleter"}
"Decorators that make a method a property (or its setter, getter or deleter)."

def methodKinds(s:ast.FunctionDef|ast.AsyncFunctionDef, inherited:set[str]) -> list[str]:
  '''
  :param s: A method.
  :type s: ast.FunctionDef | ast.AsyncFunctionDef
  :param inherited: The names of the methods its class inherits (see *ClassIndex.inheritedMethods()*).
  :type inherited: set[str]
  :returns: The kinds of method it is (see the module doc): *method* if none.
  :rtype: list[str]
  '''
  decorators = decoratorNames(s)
  kinds = [k for k, applies in (("class-method", "classmethod" in decorators),
                                ("static-method", "staticmethod" in decorators),
                                ("property", bool(decorators & PROPERTY_DECORATORS)),
                                ("abstract-method", "abstractmethod" in decorators),
                                ("overriding-method", s.name in inherited)) if applies]
  return kinds or ["method"]

def classNode(mod:SourceModule, c:ast.ClassDef, prefix:str, node, relate, doc, classes:ClassIndex,
              classNodes:dict[str, Node]) -> Node:
  '''
  Make the node for a class, its methods and nested classes (see *buildModel()*).

  :param mod: The module it's in.
  :type mod: SourceModule
  :param c: The class.
  :type c: ast.ClassDef
  :param prefix: The qualified name of what it's in (its module, or a class).
  :type prefix: str
  :param node: *buildModel()*'s node maker.
  :param relate: *buildModel()*'s relation maker.
  :param doc: *buildModel()*'s doc string maker.
  :param classes: The analysed classes.
  :type classes: ClassIndex
  :param classNodes: The classes' nodes so far, by qualified name: this one's
    (and its nested classes') are added.
  :type classNodes: dict[str, Node]
  :returns: Its node.
  :rtype: Node
  '''
  q = f"{prefix}.{c.name}"
  cls = node(["class"], c.name, qualified_name=q, line=c.lineno,
             bases=", ".join(ast.unparse(b) for b in c.bases + c.keywords), **chunkAttrs(c, mod.lines)) #type: ignore[operator]
  classNodes.setdefault(q, cls)
  doc(cls, c)
  inherited = classes.inheritedMethods(q) if q in classes.classes else set()
  for s in c.body:
    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
      f = node(methodKinds(s, inherited), s.name, qualified_name=f"{q}.{s.name}", line=s.lineno,
               parameters=ast.unparse(s.args), **chunkAttrs(s, mod.lines))
      doc(f, s)
      relate("defines-method", cls, f)
    elif isinstance(s, ast.ClassDef):
      relate("defines", cls, classNode(mod, s, q, node, relate, doc, classes, classNodes))
  return cls
