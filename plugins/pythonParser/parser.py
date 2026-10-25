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
    method of the same name: as many of those as apply. A class also
    *depends-on-type* each other analysed class that's the type of one of its
    attributes (see *ClassIndex.attributeTypes()*).
  - A class defines (*defines-attr*) its variables: a *class-var* for each
    one set in its body (eg: "x = 0", or "x:ClassVar[int] = 0") or by a
    @classmethod ("cls.x = ..."); an *instance-var* for each one declared in
    its body without a value (eg: "x:int", or a dataclass's field) or set on
    self in one of its methods ("self.x = ..."). One its bases (those among
    the analysed classes) already define is left to them. A variable has its
    type, if it can be told (see *ClassIndex.variables()*), as its
    "attr/type" (eg: "int", "list[Node]"), and *has-type* each analysed class
    that names (eg: Node, for "list[Node]", "dict[str, Node]" or
    "Node|None"); none for a type that isn't one of them (eg: "int", "list").
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
lines it starts and ends on as its "line" and "end-line" (a variable the
line it's first set or declared on), and -- hidden --
its first line as written and a hash of its text, so that it can be found
again in its file after the file's changed (see *source*); a class its
"bases"; and a function its "parameters" (as written).

A file that isn't valid Python is still a module (with a note saying so), but
with nothing in it.

A model made before can be brought up to date with the code, rather than made
afresh, so that its views still work (see *updateModel()*): what's still there
keeps its node, and its id.

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
from util.utils import urlPath
from sn.model.model import Model, Node, Relation, GraphObject, IsaIndividual
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

BUILTIN_TYPES = {"int", "float", "complex", "bool", "str", "bytes", "bytearray", "list", "tuple", "set",
                 "frozenset", "dict", "object", "type", "range", "memoryview", "slice"}
"Python's built-in types: a variable made by calling one of these (eg: \"set()\") is of that type."

RECORD_BASES = {"NamedTuple", "TypedDict"}
"Bases of a class whose annotated class attributes are its instances' fields (as a dataclass's are), even with a value (a default)."

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
  :returns: The files, and the .py files in (and below) the folders -- but not
    in hidden folders, or those in *SKIP_FOLDERS* -- each once, as absolute
    paths, in order.
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
  :returns: The folders of the packages it's in (those with an __init__.py),
    outermost first: its own folder, and those above it, as far up as they're
    packages.
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
  :returns: It, parsed (or with the reason it couldn't be), named by the
    packages it's in (see *packageFolders()*).
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
  :returns: The folder its absolute imports are from: the one its outermost
    package is in (or, if it isn't in one, its own).
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
    :returns: Where it's from (see *ORIGINS*): the standard library, an
      installed package, or the project.
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
    :returns: The module (not analysed), or None if there isn't one.
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
    :returns: The module it imports: the longest of *name*, and its prefixes
      (eg: "a.b", "a"), that's a module -- or, if none is, a module (not
      found) named by its first part (eg: "a").
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
  :returns: Whether it's ``if __name__ == "__main__":`` (either way round).
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
  :param level: The import's level: 0 for an absolute import; the number of
    leading dots of a relative one.
  :param module: The module named after them, if any (eg: "b" in "from ..b import c").
  :returns: The dotted name the import is from, or None if it goes above the
    outermost package.
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
  :param find: Finds a module by its dotted name, if there is one (eg: *ModuleFinder.find()*).
  :param resolve: The module an import of a dotted name imports (eg: *ModuleFinder.resolve()*).
  :returns: The modules it imports (anywhere in it), each once, in order --
    not itself, nor those in *SKIP_IMPORTS*. For "from a.b import c", that's
    the module a.b.c if there is one (c is a module in the package a.b),
    otherwise a.b.
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
  :param depth: How many imports out from the files to analyse: 0 for just the files.
  :param libraries: Whether to analyse modules in the standard library and
    installed packages too.
  :param progress: Told about each module as it's analysed, if given: eg: to show progress.
  :returns: The modules: the files first (if two have the same dotted name --
    eg: two main.py's in different folders -- only the first is kept), and
    then the others, nearest first; with their imports resolved.
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
  :returns: The best guess.
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
  :returns: A name for its model: its module's name -- or, for a __main__.py
    or __init__.py, its package's.
  '''
  if (mod.isPackage or mod.shortName == "__main__") and mod.packages:
    return os.path.basename(mod.packages[-1])
  return mod.shortName

def outputPaths(mod:SourceModule) -> tuple[str, str]:
  '''
  :param mod: A program's main module (see *guessMain()*).
  :returns: The model and view files to make for it: named by *modelName()*,
    with "_py" (eg: "reader_py.snm" and "reader_py.snv"), next to its file --
    or, for a __main__.py or __init__.py, next to its package's folder.
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
  :param owner: The name of what it's the doc string of.
  :returns: Its first (non-blank) line, cut down to *DOC_NAME_LENGTH* -- or,
    if that's a field (eg: ":param x: ..."), "<owner> doc".
  '''
  line = next((l.strip() for l in doc.splitlines() if l.strip()), "")
  if line.startswith(":") or line.startswith(".."):
    return f"{owner} doc"
  return line if len(line) <= DOC_NAME_LENGTH else line[:DOC_NAME_LENGTH - 1].rstrip() + "…"

def ontologyTypes(model:Model) -> dict[str, GraphObject]:
  '''
  :param model: A model with *ONTOLOGY* as a super-model.
  :returns: The ontology's types, by name.
  '''
  onto = next(db for db in model.superDBs if isinstance(db, Model) and db.url.startswith("file:")
              and os.path.realpath(urlPath(db.url) or "") == os.path.realpath(ONTOLOGY))
  return {str(o.name): o for o in onto.values() if o.model is onto and o.isType() and not o.isSystemObject()}

def buildModel(modelPath:str, modules:list[SourceModule]) -> Model:
  '''
  Make a model of *modules* (as described in the module doc), as a new model
  file *modelPath* (not saved: call its *save()*).

  :param modelPath: The model's file: it mustn't exist yet.
  :param modules: The modules (see *readModules()*).
  :returns: The model.
  '''
  m = Model(modelPath)
  m.setSuperModels([ONTOLOGY])
  fillModel(m, modules, ModelUpdate(m))
  return m

def updateModel(model:Model, modules:list[SourceModule]) -> ModelUpdate:
  '''
  Bring a model made by *buildModel()* (or by this) up to date with
  *modules*, in place (not saved: call its *save()*), so that the views of it
  still work: what's still in the code keeps its node, and that node's id
  (corrected: eg: its line, its doc string, a function become a method, ...);
  what's new gets a new node; and what's gone from the code is removed from
  the model -- and shows as missing in the views that showed it. (What's
  matched with what: see *ModelUpdate*.) Anything else in the model (eg:
  nodes and relations of types of your own, or a note added to a class) is
  left as it is -- except a relation to, or from, something that's removed.

  :param model: The model.
  :param modules: The modules (see *readModules()*).
  :returns: What was done: what was kept, added and removed.
  :raises ValueError: If *model* isn't built on *ONTOLOGY* (it wasn't made by *buildModel()*).
  '''
  try:
    ontologyTypes(model)
  except StopIteration:
    raise ValueError(f'"{os.path.basename(urlPath(model.url) or model.url)}" isn\'t a model the Python parser made: '
                     f'it isn\'t built on {os.path.basename(ONTOLOGY)}.') from None
  update = ModelUpdate(model, reuse=True)
  fillModel(model, modules, update)
  update.removeRest()
  return update

PARSER_ATTRIBUTES = {"path", "qualified-name", "origin", "import-depth", "line", "end-line", ".signature-line",
                     ".source-hash", "bases", "parameters", "text", "note", "attr/type"}
'''The attributes *buildModel()* sets (besides "name"): one of these a node
no longer has (eg: the "note" saying its file couldn't be read) is removed
from it when the model's updated (see *ModelUpdate*); any others are its own.'''

class ModelUpdate:
  '''
  Makes the objects of a model of some Python code (see *fillModel()*): new
  ones -- or, updating a model (*reuse*), those it already has, where they're
  the same things.

  What's the same thing is told by a key (see *node()* and *relate()*):

    - a package or module: its dotted name (its "qualified-name"), whatever
      it is now (eg: an external module that's now analysed);
    - a class, function, method or ``__main__`` block: its qualified name
      (eg: "sn.model.model.Node.isa"), whatever it is now (eg: a function
      that's become a class) -- of several of the same name (eg: a property's
      getter and setter), the first, the second, ... in its file;
    - a variable: its qualified name (eg: "sn.model.model.Node.db"),
      whether it's a class or an instance variable;
    - a doc string: what it's the doc string of;
    - a relation: its type, and what it's from and to (each by its key).

  So something that's renamed (or moved to another module or class) is taken
  to be gone, and something else to be new.
  '''
  def __init__(self, model:Model, reuse:bool=False):
    '''
    :param model: The model: built on *ONTOLOGY*.
    :param reuse: Whether to use the objects the model has (one made by
      *fillModel()*) for the same things, rather than making new ones.
    '''
    self.model = model
    self.T = ontologyTypes(model)
    self.keys:dict[int, tuple] = {}
    "The objects made (or reused) so far: id() -> its key."
    self.counts:dict[tuple, int] = {}
    "How many of each key (without its count) there've been so far."
    self.old:dict[tuple, GraphObject] = {}
    "The model's objects that were made by *fillModel()*, by their keys: those not reused yet."
    self.kept:list[GraphObject] = []
    "The objects reused."
    self.added:list[GraphObject] = []
    "The objects made."
    self.removed:list[GraphObject] = []
    "The objects removed (see *removeRest()*)."
    if reuse:
      self._index()

  def _claim(self, key:tuple) -> tuple:
    ''':returns: *key*, with how many of it there've been before: (eg: the setter of a property is (..., 1)).'''
    n = self.counts.get(key, 0)
    self.counts[key] = n + 1
    return key + (n,)

  def _index(self) -> None:
    '''Find the objects in the model *fillModel()* made, and their keys (see *old*).'''
    T, model = self.T, self.model
    mine = sorted((o for o in model.values() if o.model is model and o.isIndividual() and not isinstance(o, IsaIndividual)
                   and not getattr(o, "inferred", False)), # (not what the reasoner concluded: eg: has-attr)
                  key=lambda o: int(o.id)) # (in the order they were made: as in their files)
    keys:dict[int, tuple] = {}
    counts:dict[tuple, int] = {}
    def claim(o:GraphObject, key:tuple) -> None:
      n = counts.get(key, 0)
      counts[key] = n + 1
      keys[id(o)] = key + (n,)
      self.old[key + (n,)] = o
    nodes = [o for o in mine if isinstance(o, Node)]
    for o in nodes:
      q = o.getLocal("qualified-name")
      if isinstance(q, str):
        claim(o, ("module" if o.isa(T["module"]) else "var" if o.isa(T["variable"]) else "code", q))
    for o in nodes:
      if id(o) not in keys and o.isa(T["doc-string"]):
        owner = next((s for s in o.isRelatedFrom(T["has-doc"]) if id(s) in keys), None) #type: ignore[call-overload, union-attr]
        if owner is not None:
          claim(o, ("doc", keys[id(owner)]))
    ours = {id(t) for t in T.values() if isinstance(t, Relation)}
    for r in mine:
      if isinstance(r, Relation) and id(r.src) in keys and id(r.dst) in keys:
        types = r.getParents()
        if len(types) == 1 and id(types[0]) in ours:
          claim(r, (str(types[0].name), keys[id(r.src)], keys[id(r.dst)]))

  def keyOf(self, o:GraphObject) -> tuple:
    ''':returns: The key of *o*, one of the objects made (or reused) so far.'''
    return self.keys[id(o)]

  def node(self, key:tuple, types:list[str], name:str, attrs:dict[str, object]) -> Node:
    '''
    :param key: What it is (see the class doc): eg: ("code", "a.b.C").
    :param types: Its types' names (in the ontology).
    :param name: Its name.
    :param attrs: Its attributes (see *PARSER_ATTRIBUTES*): None for none.
    :returns: The node for it: the model's, if it has one (updated), or a new one.
    '''
    key = self._claim(key)
    n = self.old.pop(key, None)
    if not isinstance(n, Node):
      if n is not None: # (eg: a relation, where there'd been one of ours: can't be)
        self.old[key] = n
      n = Node(self.model, [self.T[t] for t in types], individual=True, name=name)
      self.added.append(n)
    else:
      self.kept.append(n)
      self._retype(n, [self.T[t] for t in types])
      if n.getLocal("name") != name:
        n["name"] = name
      for k in PARSER_ATTRIBUTES:
        if attrs.get(k) is None and n.getLocalAttr(k) is not None:
          del n[k]
    for k, v in attrs.items():
      if v is not None and n.getLocal(k) != v:
        n[k] = v #type: ignore[assignment]
    self.keys[id(n)] = key
    return n

  def _retype(self, o:GraphObject, types:list[GraphObject]) -> None:
    ''':param types: What *o*'s types are to be: its isa links are made, or removed, to make them so.'''
    links = [r for r in o._outgoing if isinstance(r, IsaIndividual) and r.localSrc is o and not r.inferred]
    if {id(r.localDst) for r in links} == {id(t) for t in types}:
      return
    for t in types:
      if not any(r.localDst is t for r in links):
        IsaIndividual(self.model, o, t)
    for r in links:
      if not any(r.localDst is t for t in types):
        r._disconnect()
    self.model.setDirty()

  def relate(self, typ:str, src:GraphObject, dst:GraphObject) -> Relation:
    '''
    :param typ: Its type's name (in the ontology).
    :param src: What it's from: made (or reused) by *node()*.
    :param dst: What it's to: made (or reused) by *node()*.
    :returns: The relation: the model's, if it has one, or a new one.
    '''
    key = self._claim((typ, self.keyOf(src), self.keyOf(dst)))
    r = self.old.pop(key, None)
    if isinstance(r, Relation) and r.src is src and r.dst is dst:
      self.kept.append(r)
    else:
      r = Relation(self.model, [self.T[typ]], src, dst, individual=True)
      self.added.append(r)
    self.keys[id(r)] = key
    return r

  def removeRest(self) -> None:
    '''Remove the objects *fillModel()* made that weren't reused: the things they were are gone from the code.'''
    for o in sorted(self.old.values(), key=lambda o: isinstance(o, Relation)): # (nodes first: their relations go with them)
      if o._isConnected():
        o._disconnect()
        self.removed.append(o)
      elif isinstance(o, Relation): # (gone with one of its ends)
        self.removed.append(o)
    self.old.clear()
    if self.removed:
      self.model.setDirty()

  def summary(self) -> str:
    ''':returns: How many nodes were kept, added and removed: eg: "12 kept, 3 added, 1 removed".'''
    count = lambda objects: sum(1 for o in objects if isinstance(o, Node))
    return f"{count(self.kept)} kept, {count(self.added)} added, {count(self.removed)} removed"

def fillModel(m:Model, modules:list[SourceModule], make:ModelUpdate) -> None:
  '''
  Put the objects for *modules* (as described in the module doc) in *m* (see
  *buildModel()*, *updateModel()*).

  :param m: The model: built on *ONTOLOGY*.
  :param modules: The modules (see *readModules()*).
  :param make: Makes (or reuses) the objects.
  '''
  byName = {mod.name: mod for mod in modules}

  def node(types:list[str], name:str, key:tuple, **attrs:object) -> Node:
    return make.node(key, types, name, {k.replace("_", "-"): v for k, v in attrs.items()})

  def code(types:list[str], name:str, **attrs:object) -> Node: # (a class, function, method, or __main__ block)
    return node(types, name, ("code", attrs["qualified_name"]), **attrs)

  def relate(typ:str, src:GraphObject, dst:GraphObject) -> Relation:
    return make.relate(typ, src, dst)

  typed:list[tuple[Node, list[str]]] = [] # each variable made, and the analysed classes it has-type
  def variable(v:Variable, owner:str) -> Node:
    q = f"{owner}.{v.name}"
    n = node([v.kind], v.name, ("var", q), qualified_name=q, line=v.line, end_line=v.line,
             **{"attr/type": v.type, ".signature-line": v.signature})
    typed.append((n, v.types))
    return n

  def doc(owner:GraphObject, tree:ast.AST) -> None:
    text = ast.get_docstring(tree) if isinstance(tree, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else None
    if text:
      relate("has-doc", owner, node(["doc-string"], docName(text, str(owner.name)), ("doc", make.keyOf(owner)), text=text))

  def moduleAttrs(mod:SourceModule|None) -> dict[str, object]:
    if mod is None:
      return {}
    return {"origin": mod.origin, "import_depth": mod.depth if mod.depth >= 0 else None}

  # the packages, and what they contain
  packages:dict[str, Node] = {} # dotted name -> its node
  def packageFor(folders:list[str]) -> Node:
    name = ".".join(os.path.basename(f) for f in folders)
    if name not in packages:
      packages[name] = node(["package"], os.path.basename(folders[-1]), ("module", name), path=folders[-1],
                            qualified_name=name, **moduleAttrs(byName.get(name)))
      if len(folders) > 1:
        relate("has-subpackage", packageFor(folders[:-1]), packages[name])
    return packages[name]
  objects:dict[str, Node] = {} # a module's dotted name -> its node (a package's, for its __init__.py)
  for mod in modules:
    note = f"{os.path.basename(mod.path or '')} couldn't be read: {mod.error}" if mod.error is not None else None
    if mod.isPackage and mod.packages:
      objects[mod.name] = packageFor(mod.packages)
      if note is not None:
        objects[mod.name]["note"] = note
    elif mod.name not in objects:
      objects[mod.name] = node(["module" if mod.analysed else "external-module"],
                               mod.name if mod.origin == NOT_FOUND else mod.shortName, ("module", mod.name),
                               path=mod.path, qualified_name=mod.name, note=note, **moduleAttrs(mod))
      if mod.packages:
        relate("contains-module", packageFor(mod.packages), objects[mod.name])

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
        relate("defines", owner, classNode(mod, stmt, mod.name, code, relate, doc, classes, classNodes, variable))
      elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        f = code(["function"], stmt.name, qualified_name=f"{mod.name}.{stmt.name}", line=stmt.lineno,
                 parameters=ast.unparse(stmt.args), **chunkAttrs(stmt, mod.lines))
        doc(f, stmt)
        relate("defines", owner, f)
      elif isMainBlock(stmt):
        relate("defines", owner, code(["code"], "__main__", qualified_name=f"{mod.name}.__main__", line=stmt.lineno,
                                      **chunkAttrs(stmt, mod.lines)))

  # the classes' bases (now: they may be defined later, or in a module read later)
  for q, n in classNodes.items():
    for b in classes.bases(q):
      if b in classNodes and b != q:
        relate("inherits-from", n, classNodes[b])
    for t in classes.attributeTypes(q):
      if t in classNodes and t != q:
        relate("depends-on-type", n, classNodes[t])
  for v, types in typed:
    for t in types:
      if t in classNodes:
        relate("has-type", v, classNodes[t])

  # the imports
  for mod in analysed:
    owner = objects[mod.name]
    for t in mod.imported:
      target = objects.get(t) or packages.get(t)
      if target is not None and target is not owner:
        relate("imports", owner, target)

@dataclass
class Variable:
  '''A class's variable (see *ClassIndex.variables()*).'''
  name:str
  kind:str
  "*class-var* or *instance-var*."
  line:int
  "The line it's first set or declared on."
  signature:str
  "That line, as written."
  type:str|None = None
  "Its type, as written (eg: \"list[Node]\"), if it can be told."
  types:list[str] = field(default_factory=list)
  "The qualified names of the analysed classes its type names (eg: Node's, for \"list[Node]\")."

def literalType(value:ast.expr) -> str|None:
  '''
  :param value: What a variable's set to.
  :returns: The built-in type it's of, if that can be told from it as
    written: eg: "int" for 0, "list" for [] or [x for x in y], "set" for
    set(); None for None (a variable's often set to it until it's given its
    real value), or anything else.
  '''
  if isinstance(value, ast.Constant):
    return None if value.value is None or value.value is Ellipsis else type(value.value).__name__
  if isinstance(value, ast.JoinedStr):
    return "str"
  for kinds, name in (((ast.List, ast.ListComp), "list"), ((ast.Dict, ast.DictComp), "dict"),
                      ((ast.Set, ast.SetComp), "set"), ((ast.Tuple,), "tuple")):
    if isinstance(value, kinds):
      return name
  if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in BUILTIN_TYPES:
    return value.func.id
  return None

def written(e:ast.expr, lines:list[str]) -> str:
  '''
  :param e: An expression (eg: an annotation).
  :param lines: Its file's lines.
  :returns: It as written (eg: "Node|None", not "Node | None"): a string's
    text, for a forward reference (eg: "Node" for 'Node'); its unparsed form,
    if it's on more than one line.
  '''
  if isinstance(e, ast.Constant) and isinstance(e.value, str):
    return e.value.strip()
  if e.lineno == e.end_lineno and 0 < e.lineno <= len(lines) and e.end_col_offset is not None:
    line = lines[e.lineno - 1].encode("utf-8") # (the offsets are of its bytes)
    return line[e.col_offset:e.end_col_offset].decode("utf-8", errors="replace")
  return ast.unparse(e)

def lastName(e:ast.expr) -> str|None:
  ''':returns: The last part of a name as written (eg: "ClassVar" for typing.ClassVar), if *e* is one.'''
  return e.id if isinstance(e, ast.Name) else e.attr if isinstance(e, ast.Attribute) else None

class ClassIndex:
  '''
  The analysed modules' classes, so a class's bases (as written: eg: "Base",
  "mod.Base") can be found among them, and so its inherited method names.
  '''
  def __init__(self, modules:list[SourceModule]):
    '''
    :param modules: The analysed modules, with their imports resolved.
    '''
    self.classes:dict[str, ast.ClassDef] = {}       # qualified name -> the class
    self.module:dict[str, SourceModule] = {}        # qualified name -> the module it's in
    self.aliases:dict[str, dict[str, str]] = {}     # module name -> {name used in it -> the qualified name it stands for}
    self._variables:dict[str, list[Variable]] = {}  # qualified name -> its variables (see *variables()*)
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
    :param prefix: The qualified name of what the class is in (its module, or
      a class it's nested in).
    :param base: One of its bases, as written.
    :returns: The qualified name of that base, if it's one of the analysed
      classes (a generic one's, eg: "Base[T]", is Base's) -- eg: "Base" in
      a module with "from a.b import Base", where a.b in turn imports it from
      a.c, is a.c.Base (see *reexported()*).
    '''
    while isinstance(base, ast.Subscript): # (a generic class's: eg: "Base[T]" is Base)
      base = base.value
    try:
      written = ast.unparse(base)
    except Exception:
      return None
    first, _, rest = written.partition(".")
    candidates = [f"{prefix}.{written}", f"{mod.name}.{written}"]
    alias = self.aliases.get(mod.name, {}).get(first)
    if alias is not None:
      candidates.append(alias + ("." + rest if rest else ""))
    return next((q for q in (self.reexported(c) for c in candidates) if q in self.classes), None)

  def reexported(self, qualified:str) -> str:
    '''
    :param qualified: A qualified name: eg: "a.b.C".
    :returns: What it stands for, if a module imports it from elsewhere (eg:
      a.b has "from a.c import C": "a.c.C" -- and so on, if a.c imports it
      too); otherwise *qualified*.
    '''
    seen = {qualified}
    while qualified not in self.classes:
      parts = qualified.split(".")
      module = next((i for i in range(len(parts) - 1, 0, -1) if ".".join(parts[:i]) in self.aliases), None)
      if module is None:
        break
      alias = self.aliases[".".join(parts[:module])].get(parts[module])
      if alias is None:
        break
      target = ".".join([alias] + parts[module + 1:])
      if target in seen:
        break
      seen.add(target)
      qualified = target
    return qualified

  def typesIn(self, mod:SourceModule, prefix:str, annotation:ast.expr|None) -> list[str]:
    '''
    :param mod: The module a type annotation is in.
    :param prefix: The qualified name of what it's in (eg: a class).
    :param annotation: The annotation: eg: "Node", "list[Node]", "Node|None",
      "Optional['Node']", "dict[str, a.Node]".
    :returns: The qualified names of the analysed classes it names, each once,
      in order (eg: for the first four, Node's).
    '''
    ret:list[str] = []
    def visit(e:ast.expr|None) -> None:
      if e is None:
        return
      if isinstance(e, ast.Constant) and isinstance(e.value, str): # (a forward reference: eg: "Node")
        try:
          visit(ast.parse(e.value.strip(), mode="eval").body)
        except SyntaxError:
          pass
      elif isinstance(e, (ast.Name, ast.Attribute)):
        q = self.resolve(mod, prefix, e)
        if q is not None and q not in ret:
          ret.append(q)
      elif isinstance(e, ast.Subscript):
        visit(e.value)
        visit(e.slice)
      elif isinstance(e, ast.BinOp): # (eg: Node|None)
        visit(e.left)
        visit(e.right)
      elif isinstance(e, (ast.Tuple, ast.List)):
        for x in e.elts:
          visit(x)
    visit(annotation)
    return ret

  def attributeTypes(self, qualified:str) -> list[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :returns: The qualified names of the analysed classes that are the types
      of its attributes, each once, in order: those of its annotated class
      attributes (eg: a dataclass's fields: "x:Node"); and, in its methods,
      of the attributes of self (their first parameter) that are annotated
      ("self.x:Node = ..."), assigned a new object ("self.x = Node(...)"), or
      assigned an annotated parameter ("def __init__(self, n:Node): self.x = n").
    '''
    c, mod = self.classes[qualified], self.module[qualified]
    ret:list[str] = []
    def add(types:list[str]) -> None:
      ret.extend(t for t in types if t not in ret)
    def isSelfAttr(target:ast.expr, me:str) -> bool:
      return isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == me
    for s in c.body:
      if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
        add(self.typesIn(mod, qualified, s.annotation))
      elif isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and "staticmethod" not in decoratorNames(s):
        args = s.args.posonlyargs + s.args.args
        if not args:
          continue
        me = args[0].arg
        params = {a.arg: a.annotation for a in args[1:] + s.args.kwonlyargs if a.annotation is not None}
        for n in ast.walk(s):
          if isinstance(n, ast.AnnAssign) and isSelfAttr(n.target, me):
            add(self.typesIn(mod, qualified, n.annotation))
          if isinstance(n, (ast.Assign, ast.AnnAssign)) and n.value is not None \
             and any(isSelfAttr(t, me) for t in (n.targets if isinstance(n, ast.Assign) else [n.target])):
            v = n.value
            if isinstance(v, ast.Call):
              q = self.resolve(mod, qualified, v.func)
              if q is not None:
                add([q])
            elif isinstance(v, ast.Name) and v.id in params:
              add(self.typesIn(mod, qualified, params[v.id]))
    return ret

  def variables(self, qualified:str) -> list[Variable]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :returns: Its variables (not those of its bases), each once, in order:
      first those in its body, then those set in its methods. A variable is:

        - a *class-var* if it's set in the class's body ("x = 0", "x:int =
          0"), annotated as a ClassVar ("x:ClassVar[int]"), or set on the
          class in a @classmethod ("cls.x = 0");
        - an *instance-var* if it's annotated in the class's body without a
          value ("x:int") -- or with one, in a dataclass, NamedTuple or
          TypedDict (a field's default) -- or set on self in a method
          ("self.x = 0").

      (Whichever is found first: eg: "x = 0" in its body and "self.x = 1" in
      a method is a class variable, given a new value for an instance.) Its
      type is its first annotation, as written (eg: "x:list[Node]", or
      "self.x:Node|None = None"; ClassVar[T]'s is T's); if it has none, what
      it's first set to that tells: a new object of a class ("self.x =
      Node()", or "self.x = tk.Canvas()": a capitalized name is taken to be a
      class), an annotated parameter ("def __init__(self, n:Node): self.x =
      n"), or a value of a built-in type (see *literalType()*). Names like
      __slots__ (starting and ending with "__") aren't variables.
    '''
    if qualified in self._variables:
      return self._variables[qualified]
    c, mod = self.classes[qualified], self.module[qualified]
    found:dict[str, Variable] = {}
    annotated:set[str] = set() # (those with their type from an annotation)
    lines = mod.lines
    def add(target:ast.expr, kind:str, line:int, annotation:ast.expr|None=None, value:ast.expr|None=None,
            params:dict[str, ast.expr]|None=None) -> None:
      name = target.attr if isinstance(target, ast.Attribute) else target.id if isinstance(target, ast.Name) else None
      if name is None or (name.startswith("__") and name.endswith("__")):
        return
      v = found.get(name)
      if v is None:
        v = found[name] = Variable(name, kind, line, lines[line - 1].strip() if 0 < line <= len(lines) else "")
      if name in annotated:
        return
      if annotation is not None:
        v.type, v.types = written(annotation, lines), self.typesIn(mod, qualified, annotation)
        annotated.add(name)
      elif v.type is None and value is not None:
        v.type, v.types = self.valueType(mod, qualified, value, params or {})
    def classVar(annotation:ast.expr) -> tuple[bool, ast.expr|None]:
      ''':returns: Whether *annotation* is a ClassVar, and the type it's of (eg: for "ClassVar[int]": True, int).'''
      if lastName(annotation) == "ClassVar":
        return True, None
      if isinstance(annotation, ast.Subscript) and lastName(annotation.value) == "ClassVar":
        return True, annotation.slice
      return False, annotation
    record = "dataclass" in decoratorNames(c) or any(lastName(b) in RECORD_BASES for b in c.bases) #type: ignore[arg-type]
    targetsOf = lambda n: n.targets if isinstance(n, ast.Assign) else [n.target]
    def unpacked(target:ast.expr, value:ast.expr|None) -> list[tuple[ast.expr, ast.expr|None]]:
      ''':returns: What's set to what (eg: for "a, b = 1, x": a to 1, b to x; for "a, b = f()": a and b to unknown).'''
      if not isinstance(target, (ast.Tuple, ast.List)):
        return [(target, value)]
      if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts) \
         and not any(isinstance(e, ast.Starred) for e in target.elts + value.elts):
        return list(zip(target.elts, value.elts))
      return [(e, None) for e in target.elts]
    for s in c.body:
      if isinstance(s, ast.Assign):
        for t in s.targets:
          for e, value in unpacked(t, s.value):
            add(e, "class-var", s.lineno, value=value)
      elif isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
        isClassVar, annotation = classVar(s.annotation)
        kind = "class-var" if isClassVar or (s.value is not None and not record) else "instance-var"
        add(s.target, kind, s.lineno, annotation, s.value)
    for s in c.body:
      if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)) and "staticmethod" not in decoratorNames(s):
        args = s.args.posonlyargs + s.args.args
        if not args:
          continue
        me = args[0].arg
        kind = "class-var" if "classmethod" in decoratorNames(s) else "instance-var"
        params = {a.arg: a.annotation for a in args[1:] + s.args.kwonlyargs if a.annotation is not None}
        for n in ast.walk(s):
          if isinstance(n, (ast.Assign, ast.AnnAssign)):
            for t in targetsOf(n):
              for e, value in unpacked(t, n.value):
                if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name) and e.value.id == me:
                  add(e, kind, n.lineno, n.annotation if isinstance(n, ast.AnnAssign) else None, value, params)
    ret = self._variables[qualified] = list(found.values())
    return ret

  def valueType(self, mod:SourceModule, prefix:str, value:ast.expr, params:dict[str, ast.expr]) -> tuple[str|None, list[str]]:
    '''
    :param mod: The module a variable's class is in.
    :param prefix: Its class's qualified name.
    :param value: What it's set to.
    :param params: The annotated parameters of the method it's set in: name -> annotation.
    :returns: Its type (as written), if *value* tells it (see *variables()*),
      and the analysed classes that names.
    '''
    if isinstance(value, ast.Call):
      q = self.resolve(mod, prefix, value.func)
      if q is not None:
        return written(value.func, mod.lines), [q]
      name = lastName(value.func)
      if name is not None and name[:1].isupper():
        return written(value.func, mod.lines), []
    elif isinstance(value, ast.Name) and value.id in params:
      a = params[value.id]
      return written(a, mod.lines), self.typesIn(mod, prefix, a)
    return literalType(value), []

  def inheritedVariables(self, qualified:str, _seen:set[str]|None=None) -> set[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :returns: The names of the variables its bases (those among the analysed
      classes), and theirs, define.
    '''
    seen = _seen if _seen is not None else {qualified}
    ret:set[str] = set()
    for q in self.bases(qualified):
      if q in seen:
        continue
      seen.add(q)
      ret |= {v.name for v in self.variables(q)}
      ret |= self.inheritedVariables(q, seen)
    return ret

  def bases(self, qualified:str) -> list[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :returns: The qualified names of those of its bases that are analysed classes.
    '''
    c, mod = self.classes[qualified], self.module[qualified]
    prefix = qualified.rsplit(".", 1)[0]
    return [q for q in (self.resolve(mod, prefix, b) for b in c.bases) if q is not None]

  def inheritedMethods(self, qualified:str, _seen:set[str]|None=None) -> set[str]:
    '''
    :param qualified: One of the analysed classes' qualified name.
    :returns: The names of the methods its bases (those among the analysed
      classes), and theirs, define.
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
  :returns: The last part of each of its decorators' names: eg: "abstractmethod"
    for @abc.abstractmethod, "setter" for @x.setter.
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
  :param inherited: The names of the methods its class inherits (see *ClassIndex.inheritedMethods()*).
  :returns: The kinds of method it is (see the module doc): *method* if none.
  '''
  decorators = decoratorNames(s)
  kinds = [k for k, applies in (("class-method", "classmethod" in decorators),
                                ("static-method", "staticmethod" in decorators),
                                ("property", bool(decorators & PROPERTY_DECORATORS)),
                                ("abstract-method", "abstractmethod" in decorators),
                                ("overriding-method", s.name in inherited)) if applies]
  return kinds or ["method"]

def classNode(mod:SourceModule, c:ast.ClassDef, prefix:str, node, relate, doc, classes:ClassIndex,
              classNodes:dict[str, Node], variable) -> Node:
  '''
  Make the node for a class, its methods, nested classes and variables (see *fillModel()*).

  :param mod: The module it's in.
  :param c: The class.
  :param prefix: The qualified name of what it's in (its module, or a class).
  :param node: *fillModel()*'s node maker (for a class, function, ...).
  :param relate: *fillModel()*'s relation maker.
  :param doc: *fillModel()*'s doc string maker.
  :param classes: The analysed classes.
  :param classNodes: The classes' nodes so far, by qualified name: this one's
    (and its nested classes') are added.
  :param variable: *fillModel()*'s variable maker: (a *Variable*, the
    qualified name of its class) -> its node.
  :returns: Its node.
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
      relate("defines", cls, classNode(mod, s, q, node, relate, doc, classes, classNodes, variable))
  if q in classes.classes:
    inheritedVars = classes.inheritedVariables(q)
    for v in classes.variables(q):
      if v.name not in inheritedVars:
        relate("defines-attr", cls, variable(v, q))
  return cls
