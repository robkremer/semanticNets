'''
Turn some Python source files into a Semantic Nets model (see *buildModel()*),
built on the ontology in pythonOntology.snm (its super-model: see *ONTOLOGY*).

The files are parsed (with *ast*) only for their top-level structure:

  - Each file becomes a *module*, named by its file's name (eg: reader); an
    __init__.py is its folder's *package* instead (in Python, a package is a
    module: the ontology has package isa module).
  - Each folder a file is in that's a package (it has an __init__.py) becomes
    a *package* (named by its folder's name), whether or not its __init__.py
    was one of the files; and so does each folder above it that's a package.
    A package *contains-module* each of its modules and sub-packages.
  - A module defines (*defines*) its top-level classes and functions, and a
    *code* block for its ``if __name__ == "__main__":`` part, if it has one.
  - A class defines its methods (*defines-method*) and nested classes
    (*defines*). A method is also a *class-method* if it's a @classmethod, an
    *abstract-method* if it's an @abstractmethod, and an *overriding-method*
    if a class it's derived from (one of the files' classes: it can only tell
    for those) has a method of the same name: as many of those as apply.
  - A module, class or function with a doc string *has-doc* a *doc-string*,
    which has it as its "text": named by its first line (or, if that's a field,
    eg: ":param x: ...", by what it's the doc string of: eg: "go doc").
  - A module *imports* each of the files' modules and packages that it imports
    (anywhere in it): the most specific one each import names. Imports of
    anything else (eg: the standard library) are left out.

Each module, class and function has its full dotted name as its
"qualified-name" (eg: sn.exampleApps.pythonParser.parser.buildModel); a
module or package its file or folder as its "path"; a class or function the
line it starts on as its "line"; a class its "bases"; and a function its
"parameters" (as written).

A file that isn't valid Python is still a module (with a note saying so), but
with nothing in it.

Created on Oct 10, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import ast
import os
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse
from sn.model.model import Model, Node, Relation, GraphObject

ONTOLOGY = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pythonOntology.snm")
"The model the models made build on: the types of things in Python programs (package, module, class, ...)."

SKIP_FOLDERS = {"__pycache__", "build", "dist", "node_modules", "site-packages"}
'''Folders not looked in for .py files when a folder is given (see
*pythonFiles()*): nor are hidden ones (eg: .git, .venv).'''

MAIN_NAMES = {"__main__": 40, "main": 30, "app": 20, "cli": 20, "run": 15, "manage": 15, "start": 10}
"Module names that suggest a program's main module, and how strongly (see *guessMain()*)."

DOC_NAME_LENGTH = 60
"The longest a doc string's node's name (its first line) gets: longer is cut off with an ellipsis."

@dataclass
class SourceModule:
  '''A parsed Python file: a module (or a package's __init__.py).'''
  path:str
  "The file."
  name:str
  '''Its module's dotted name: eg: "sn.model.model" -- a package's for its
  __init__.py (eg: "sn.model").'''
  packages:list[str]
  '''The folders of the packages it's in, outermost first (eg: .../src/sn,
  .../src/sn/model): its own folder is the last, if that's a package.'''
  tree:ast.Module|None = None
  "Its syntax tree, or None if it isn't valid Python (see *error*)."
  error:str|None = None
  "Why it couldn't be parsed, if it couldn't."
  imported:list[str] = field(default_factory=list)
  "The dotted names of the files' modules and packages it imports (see *resolveImports()*)."

  @property
  def isPackage(self) -> bool:
    ":returns: Whether it's a package's __init__.py."
    return os.path.basename(self.path) == "__init__.py"

  @property
  def shortName(self) -> str:
    ":returns: The last part of its dotted name: eg: \"model\"."
    return self.name.rsplit(".", 1)[-1]

  @property
  def packageName(self) -> str|None:
    ''':returns: The dotted name of the package it's in, or None if it isn't in
      one. (For an __init__.py, the package above its own.)'''
    parts = self.name.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else None

  def hasMainBlock(self) -> bool:
    ':returns: Whether it has an ``if __name__ == "__main__":`` part.'
    return self.tree is not None and any(isMainBlock(s) for s in self.tree.body)

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
  :param path: A Python file.
  :type path: str
  :returns: It, parsed (or with the reason it couldn't be).
  :rtype: SourceModule
  '''
  packages = packageFolders(path)
  parts = [os.path.basename(p) for p in packages]
  stem = os.path.splitext(os.path.basename(path))[0]
  if stem != "__init__" or not parts:
    parts.append(stem)
  mod = SourceModule(path, ".".join(parts), packages)
  try:
    with open(path, "rb") as f: # (bytes: ast honours the file's own encoding declaration)
      mod.tree = ast.parse(f.read(), filename=path)
  except (SyntaxError, ValueError, OSError) as ex:
    mod.error = f"{ex.__class__.__name__}: {ex}"
  return mod

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
  if level - 1 > len(here):
    return None
  base = here[:len(here) - (level - 1)]
  return ".".join(base + ([module] if module else [])) or None

def known(name:str, index:dict[str, object]) -> str|None:
  '''
  :param name: A dotted name: eg: "a.b.c".
  :type name: str
  :param index: Known dotted names.
  :type index: dict[str, object]
  :returns: The longest of *name*, and its prefixes (eg: "a.b", "a"), that's in
    *index*, if any.
  :rtype: str | None
  '''
  parts = name.split(".")
  for i in range(len(parts), 0, -1):
    n = ".".join(parts[:i])
    if n in index:
      return n
  return None

def resolveImports(mod:SourceModule, index:dict[str, object]) -> None:
  '''
  Set *mod.imported* to the modules and packages in *index* that it imports.

  :param mod: A parsed module.
  :type mod: SourceModule
  :param index: The dotted names of the files' modules and packages.
  :type index: dict[str, object]
  '''
  if mod.tree is None:
    return
  found:list[str] = []
  for node in ast.walk(mod.tree):
    targets:list[str|None] = []
    if isinstance(node, ast.Import):
      targets = [known(a.name, index) for a in node.names]
    elif isinstance(node, ast.ImportFrom):
      base = importBase(mod, node.level, node.module)
      if base is None:
        continue
      for a in node.names: # (a name imported from a package may be a module in it)
        targets.append(known(f"{base}.{a.name}", index) if a.name != "*" else known(base, index))
    for t in targets:
      if t is not None and t != mod.name and t not in found:
        found.append(t)
  mod.imported = found

def guessMain(modules:list[SourceModule]) -> SourceModule:
  '''
  Guess which of *modules* is the program's main one: the one most like it of

    - one with an ``if __name__ == "__main__":`` part, or named __main__.py
      (or main.py, app.py, ...: see *MAIN_NAMES*);
    - one that no other imports, but that imports others (the more the better);

  the less deep in packages the better (eg: a package's __main__.py rather
  than one of its sub-packages'); and, other things being equal, the first.

  :param modules: Parsed modules (at least one), with their imports resolved.
  :type modules: list[SourceModule]
  :returns: The best guess.
  :rtype: SourceModule
  '''
  importedBy:dict[str, int] = {}
  for m in modules:
    for t in m.imported:
      importedBy[t] = importedBy.get(t, 0) + 1
  def score(m:SourceModule) -> float:
    s = 0.0
    if m.hasMainBlock():
      s += 50
    s += MAIN_NAMES.get(m.shortName.lower(), 0) if not m.isPackage else 0
    if not importedBy.get(m.name):
      s += 10 + min(len(m.imported), 20)
    if m.isPackage:
      s -= 5 # (an __init__.py is seldom where a program starts)
    if m.shortName.startswith("test") or m.shortName == "setup" or m.shortName == "conftest":
      s -= 30
    return s - 10 * len(m.packages) # (a program's main module is outermost: deeper ones start parts of it)
  return max(modules, key=score) # (the first of the best)

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
    folder = os.path.dirname(mod.path)
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

def buildModel(paths:list[str], modelPath:str, modules:list[SourceModule]|None=None) -> Model:
  '''
  Make a model of the Python files *paths* (as described in the module doc),
  as a new model file *modelPath* (not saved: call its *save()*).

  :param paths: The files.
  :type paths: list[str]
  :param modelPath: The model's file: it mustn't exist yet.
  :type modelPath: str
  :param modules: The files already read (see *readModules()*), if they have
    been: then *paths* is ignored.
  :type modules: list[SourceModule] | None
  :returns: The model.
  :rtype: Model
  '''
  if modules is None:
    modules = readModules(paths)
  m = Model(modelPath)
  m.setSuperModels([ONTOLOGY])
  T = ontologyTypes(m)

  def node(types:list[str], name:str, **attrs:object) -> Node:
    n = Node(m, [T[t] for t in types], individual=True, name=name)
    for k, v in attrs.items():
      n[k.replace("_", "-")] = v #type: ignore[assignment]
    return n

  def relate(typ:str, src:GraphObject, dst:GraphObject) -> Relation:
    return Relation(m, [T[typ]], src, dst, individual=True)

  def doc(owner:GraphObject, tree:ast.AST) -> None:
    text = ast.get_docstring(tree) if isinstance(tree, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) else None
    if text:
      relate("has-doc", owner, node(["doc-string"], docName(text, str(owner.name)), text=text))

  # the packages, and what they contain
  packages:dict[str, Node] = {} # dotted name -> its node
  def packageFor(folders:list[str]) -> Node:
    name = ".".join(os.path.basename(f) for f in folders)
    if name not in packages:
      packages[name] = node(["package"], os.path.basename(folders[-1]), path=folders[-1], qualified_name=name)
      if len(folders) > 1:
        relate("contains-module", packageFor(folders[:-1]), packages[name])
    return packages[name]
  objects:dict[str, Node] = {} # a module's dotted name -> its node (a package's, for its __init__.py)
  for mod in modules:
    if mod.isPackage and mod.packages:
      objects[mod.name] = packageFor(mod.packages)
    elif mod.name not in objects:
      objects[mod.name] = node(["module"], mod.shortName, path=mod.path, qualified_name=mod.name)
      if mod.packages:
        relate("contains-module", packageFor(mod.packages), objects[mod.name])
    if mod.error is not None:
      objects[mod.name]["note"] = f"{os.path.basename(mod.path)} couldn't be read: {mod.error}"

  # the classes (first: a method needs to know if a class it's derived from has one of the same name)
  classes = ClassIndex(modules)

  # what's in the modules
  for mod in modules:
    if mod.tree is None:
      continue
    owner = objects[mod.name]
    doc(owner, mod.tree)
    for stmt in mod.tree.body:
      if isinstance(stmt, ast.ClassDef):
        relate("defines", owner, classNode(mod, stmt, mod.name, node, relate, doc, classes))
      elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
        f = node(["function"], stmt.name, qualified_name=f"{mod.name}.{stmt.name}", line=stmt.lineno,
                 parameters=ast.unparse(stmt.args))
        doc(f, stmt)
        relate("defines", owner, f)
      elif isMainBlock(stmt):
        relate("defines", owner, node(["code"], "__main__", qualified_name=f"{mod.name}.__main__", line=stmt.lineno))
    for t in mod.imported:
      target = objects.get(t) or packages.get(t)
      if target is not None and target is not owner:
        relate("imports", owner, target)
  return m

class ClassIndex:
  '''
  The files' classes, so a class's bases (as written: eg: "Base", "mod.Base")
  can be found among them, and so its inherited method names.
  '''
  def __init__(self, modules:list[SourceModule]):
    '''
    :param modules: The parsed files, with their imports resolved.
    :type modules: list[SourceModule]
    '''
    self.classes:dict[str, ast.ClassDef] = {}       # qualified name -> the class
    self.module:dict[str, SourceModule] = {}        # qualified name -> the module it's in
    self.aliases:dict[str, dict[str, str]] = {}     # module name -> {name used in it -> the qualified name it stands for}
    names = {m.name for m in modules}
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
    self._names = names

  def resolve(self, mod:SourceModule, prefix:str, base:ast.expr) -> str|None:
    '''
    :param mod: The module a class is in.
    :type mod: SourceModule
    :param prefix: The qualified name of what the class is in (its module, or
      a class it's nested in).
    :type prefix: str
    :param base: One of its bases, as written.
    :type base: ast.expr
    :returns: The qualified name of that base, if it's one of the files' classes.
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

  def inheritedMethods(self, qualified:str, _seen:set[str]|None=None) -> set[str]:
    '''
    :param qualified: One of the files' classes' qualified name.
    :type qualified: str
    :returns: The names of the methods its bases (those among the files'
      classes), and theirs, define.
    :rtype: set[str]
    '''
    seen = _seen if _seen is not None else {qualified}
    c, mod = self.classes[qualified], self.module[qualified]
    prefix = qualified.rsplit(".", 1)[0]
    ret:set[str] = set()
    for b in c.bases:
      q = self.resolve(mod, prefix, b)
      if q is None or q in seen:
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
    for @abc.abstractmethod.
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

def classNode(mod:SourceModule, c:ast.ClassDef, prefix:str, node, relate, doc, classes:ClassIndex) -> Node:
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
  :param classes: The files' classes.
  :type classes: ClassIndex
  :returns: Its node.
  :rtype: Node
  '''
  q = f"{prefix}.{c.name}"
  cls = node(["class"], c.name, qualified_name=q, line=c.lineno,
             bases=", ".join(ast.unparse(b) for b in c.bases + c.keywords)) #type: ignore[operator]
  doc(cls, c)
  inherited = classes.inheritedMethods(q) if q in classes.classes else set()
  for s in c.body:
    if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
      decorators = decoratorNames(s)
      kinds = [k for k, applies in (("class-method", "classmethod" in decorators),
                                    ("abstract-method", "abstractmethod" in decorators),
                                    ("overriding-method", s.name in inherited)) if applies]
      f = node(kinds or ["method"], s.name, qualified_name=f"{q}.{s.name}", line=s.lineno,
               parameters=ast.unparse(s.args))
      doc(f, s)
      relate("defines-method", cls, f)
    elif isinstance(s, ast.ClassDef):
      relate("defines", cls, classNode(mod, s, q, node, relate, doc, classes))
  return cls

def readModules(paths:list[str]) -> list[SourceModule]:
  '''
  :param paths: Python files and folders (see *pythonFiles()*).
  :type paths: list[str]
  :returns: The files, parsed, with their imports resolved. (If two have the
    same dotted name -- eg: two main.py's in different folders -- only the
    first is kept.)
  :rtype: list[SourceModule]
  '''
  modules:list[SourceModule] = []
  seen:set[str] = set()
  for p in pythonFiles(paths):
    mod = readModule(p)
    if mod.name not in seen:
      seen.add(mod.name)
      modules.append(mod)
  index:dict[str, object] = {m.name: m for m in modules}
  for m in modules: # (the packages they're in can be imported too, whether or not their __init__.py was given)
    for i in range(1, len(m.packages) + 1):
      index.setdefault(".".join(os.path.basename(f) for f in m.packages[:i]), None)
  for m in modules:
    resolveImports(m, index)
  return modules
