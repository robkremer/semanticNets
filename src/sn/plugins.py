'''
Plugins: programs the editor loads at start-up, that add to it -- menu items
for now (see *PluginContext*); panels, view menus and text commands later.
(Eg: pythonParser and XMLreader, which come with it.)

A plugin is a folder in *PLUGINS_FOLDER* (``~/.sn/plugins/``): a Python
package whose ``__init__.py`` defines ``register(ctx)``, and a
``plugin.toml`` describing it (see *Manifest*)::

    name = "My plugin"
    version = "1.0"
    description = "What it does."
    sn-version = "1.0"     # the oldest sn it works with
    exclude = ["examples/*.snm"]   # files in it not to install (see installBundled())

It's imported as ``snplugins.<folder>`` (a package whose path is the plugins
folder: see *namespace()*), so that its hooks (see *sn.hooks*) have the same
references wherever it's installed -- eg: ``snplugins.myPlugin.hooks:show`` --
and, once it's loaded, they're trusted: it was installed by the user.

The plugins that come with the program (*bundledFolder()*: the project's
``plugins/``; a packaged app's bundled copy) are copied into the plugins
folder (see *installBundled()*) when they aren't there, are older, or have
changed since they were installed (eg: edited in the project) -- copied, not loaded where they are, so that what's in them (eg: an ontology
models are built on) stays at the same place when the app is moved or updated.
A view in one that the user's changed there (eg: laid out) is the user's: it's
kept when the plugin's installed again (see *USER_FILES*).

A plugin that can't be read, imported or registered is logged, and left out:
it doesn't stop the program, or the other plugins. The "plugins/disabled"
preference lists those not to load.

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
import fnmatch
import hashlib
import importlib
import os
import re
import sys
import tomllib
import types
import zipfile
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any, Callable
import tkinter as tk
import sn
from sn import snPrefs, hooks

logger:sn.SNLogger = sn.getLogger(__name__)

NAMESPACE = "snplugins"
"The package plugins are imported in: ``snplugins.<folder>``."

PLUGINS_FOLDER = os.path.join(sn.SN_FOLDER, "plugins")
"Where the plugins are installed."

MANIFEST = "plugin.toml"
"The file in a plugin's folder that describes it (see *Manifest*)."

DISABLED_PREF = "plugins/disabled"
"The preference listing the plugins (their folders' names) not to load."

TOOLS_MENU = "Tools"
"The menu-bar menu a plugin's menu items go in when their path doesn't name one (see *PluginContext.addMenuItem()*)."

_FOLDER_NAME = re.compile(r"[A-Za-z_]\w*")

def version(text:str) -> tuple[int, ...]:
  '''
  :param text: A version: eg: "1.2.10", or one on its way, eg: "1.2.2a".
  :returns: It, to compare with another: eg: (1, 2, 10). Each part counts by
    the number it starts with -- "2a" as 2, so "1.2.2a" is (1, 2, 2): a plugin
    that needs 1.2.1 (or 1.2.2) loads in it -- and one that doesn't start with
    a number (eg: "x") as 0.
  '''
  return tuple(int(m.group()) if (m := _LEADING_NUMBER.match(p.strip())) else 0 for p in str(text).strip().split("."))

_LEADING_NUMBER = re.compile(r"\d+")
"The number a version's part starts with (see *version()*)."

class PluginError(Exception):
  "A plugin that can't be read, or loaded: why."

@dataclass
class Manifest:
  '''A plugin's description: its *MANIFEST* file.'''
  folder:str
  "The plugin's folder."
  name:str
  "Its name, as the user sees it."
  version:str = "0"
  description:str = ""
  snVersion:str = "0"
  "The oldest sn it works with."
  exclude:tuple[str, ...] = ()
  '''The files in its folder not to install (see *installBundled()*): patterns
  (as *fnmatch.fnmatch()* matches) of their paths in it, with "/" (eg: ``examples/*.snm``).'''
  source:Traversable|None = field(default=None, repr=False, compare=False)
  "Its folder, to read from: a folder's, or (for those bundled in a .pyz) a zip file's (see *bundledFolder()*)."

  @property
  def id(self) -> str:
    "Its folder's name: what it's imported as, in *NAMESPACE*, and called in the preferences."
    return self.source.name if self.source is not None else os.path.basename(self.folder)

  @property
  def module(self) -> str:
    "Its package's name: ``snplugins.<folder>``."
    return f"{NAMESPACE}.{self.id}"

  @classmethod
  def read(cls, folder:str|Traversable) -> Manifest:
    '''
    :param folder: A plugin's folder (or one in a zip file: see *bundledFolder()*).
    :returns: Its description.
    :raises PluginError: If it isn't a plugin's folder, or its *MANIFEST* can't be read.
    '''
    source = Path(folder) if isinstance(folder, str) else folder
    name = source.name
    if not _FOLDER_NAME.fullmatch(name):
      raise PluginError(f'A plugin\'s folder must be named as a Python package is: "{name}" isn\'t.')
    try:
      data = tomllib.loads(source.joinpath(MANIFEST).read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as ex:
      raise PluginError(f"{name}'s {MANIFEST} can't be read: {ex}") from ex
    exclude = data.get("exclude", [])
    return cls(str(folder).rstrip("/"), str(data.get("name", name)), str(data.get("version", "0")),
               str(data.get("description", "")), str(data.get("sn-version", "0")),
               tuple(str(e) for e in exclude) if isinstance(exclude, list) else (), source)

def bundledFolder() -> Traversable:
  '''
  :returns: Where the plugins that come with the program are: the project's
    ``plugins/`` (or a packaged app's bundled copy: see *sn.resourcePath()*);
    or, in a .pyz, its ``plugins/`` (a folder in the zip file).
  '''
  path = sn.resourcePath("plugins")
  if os.path.isdir(path):
    return Path(path)
  archive = os.path.dirname(os.path.dirname(os.path.abspath(sn.__file__))) # (sn's in the .pyz: <archive>/sn/__init__.py)
  if os.path.isfile(archive) and zipfile.is_zipfile(archive):
    return zipfile.Path(archive, "plugins/")
  return Path(path)

def manifests(folder:str|Traversable) -> list[Manifest]:
  '''
  :param folder: A folder of plugins (or one in a zip file: see *bundledFolder()*).
  :returns: The descriptions of the plugins in it (folders with a *MANIFEST*),
    by folder name; any that can't be read are logged, and left out.
  '''
  ret:list[Manifest] = []
  top = Path(folder) if isinstance(folder, str) else folder
  if not top.is_dir():
    return ret
  for path in sorted(top.iterdir(), key=lambda p: p.name):
    if path.is_dir() and path.joinpath(MANIFEST).is_file():
      try:
        ret.append(Manifest.read(path))
      except PluginError as ex:
        logger.warning(f"Plugin left out: {ex}")
  return ret

def installBundled(source:str|Traversable|None=None, target:str|None=None) -> list[str]:
  '''
  Install the plugins that come with the program in the plugins folder: those
  that aren't there, are older there (by their version), have changed since
  they were installed there (the same version, but not the same files: eg:
  edited in the project, between releases -- see *STAMP*), or are missing a
  file they come with (eg: a view the user deleted, to get the one that comes
  with the plugin back) -- but for the files they say not to (see
  *Manifest.exclude*), and making their models and views refer to where they
  now are (see *_relocated()*). One that hasn't changed since it was
  installed is left alone.

  Installing one over what's there replaces the files it comes with, and
  removes those it came with before but no longer does -- but leaves the
  user's own: a view (see *USER_FILES*) that isn't as it was installed (eg:
  laid out, and saved), and any file the user's put there.

  :param source: Where the plugins that come with the program are (by default, *bundledFolder()*).
  :param target: The plugins folder (by default, *PLUGINS_FOLDER*).
  :returns: The plugins installed (their folders' names).
  '''
  ret = []
  for m in manifests(source if source is not None else bundledFolder()):
    dest = os.path.join(target if target is not None else PLUGINS_FOLDER, m.id)
    files = _bundledFiles(m, m.source if m.source is not None else Path(m.folder))
    stamp = _contentHash(files)
    old, record = _stamp(dest)
    if os.path.isfile(os.path.join(dest, MANIFEST)):
      try:
        there = version(Manifest.read(dest).version)
        if there > version(m.version) or (there == version(m.version) and old == stamp
                                          and all(os.path.isfile(_path(dest, rel)) for rel, _f in files)):
          continue
      except PluginError:
        pass # (it's replaced)
    try:
      record, kept = _install(m, files, dest, record)
      with open(os.path.join(dest, STAMP), "w", encoding="utf-8") as f:
        f.write(stamp + "\n" + "".join(f"{h} {rel}\n" for rel, h in record.items()))
    except (OSError, zipfile.BadZipFile):
      logger.error(f'Couldn\'t install the plugin {m.name} in "{dest}".', exc_info=True)
      continue
    logger.info(f'Installed the plugin {m.name} {m.version} in "{dest}".'
                + (f' Kept your own {", ".join(kept)} there.' if kept else ""))
    ret.append(m.id)
  return ret

STAMP = ".bundled"
'''The file, in an installed plugin's folder, that says what it was installed
from, and what was installed (see *installBundled()*): a hash of the bundled
plugin's files (see *_contentHash()*); and a line for each file installed --
a hash of what was written (see *_hash()*: its models and views as they were
relocated), and its path in the folder, with "/". One installed without it
(eg: by an older version) is taken to have changed; one installed with just
the first line (by an older version), to have its own views, wherever they
aren't as they come.'''

USER_FILES = ("*.snv",)
'''The files in an installed plugin that are the user's once they've changed
them (patterns of their names): its views -- laid out, as the user wants them
-- which installing the plugin again (eg: a new version) leaves as they are
(see *installBundled()*). (Its code and models are always replaced: the
plugin needs them as they come.) To get one as it comes with the plugin
again, delete it: it's put back the next time the program starts.'''

def _stamp(dest:str) -> tuple[str|None, dict[str, str]|None]:
  '''
  :returns: The *STAMP* of the plugin installed in *dest*: its hash of the
    bundled plugin, and what was installed (path -> hash of what was written) --
    or None for each that it hasn't (eg: an older version wrote just the
    first, and none, nothing).
  '''
  try:
    with open(os.path.join(dest, STAMP), encoding="utf-8") as f:
      lines = f.read().splitlines()
  except (OSError, UnicodeError):
    return None, None
  if not lines:
    return None, None
  record = {rel: h for h, _, rel in (line.partition(" ") for line in lines[1:]) if rel}
  return lines[0].strip(), record if len(lines) > 1 else None

def _bundledFiles(manifest:Manifest, source:Traversable, rel:str="") -> list[tuple[str, Traversable]]:
  '''
  :returns: The files of the plugin's folder *source* (or a folder in it:
    *rel*) that are installed (see *installed()*): their paths in it, with
    "/" (eg: "examples/books.xml"), and them -- in the order they're hashed
    in (see *_contentHash()*): by name, a folder's files where it comes.
  '''
  ret:list[tuple[str, Traversable]] = []
  for child in sorted(source.iterdir(), key=lambda p: p.name):
    path = rel + child.name
    if not installed(manifest, path):
      continue
    if child.is_dir():
      ret += _bundledFiles(manifest, child, path + "/")
    else:
      ret.append((path, child))
  return ret

def _contentHash(files:list[tuple[str, Traversable]]) -> str:
  '''
  :param files: A plugin's files that are installed (see *_bundledFiles()*).
  :returns: A hash of them: their paths, and what's in them.
  '''
  h = hashlib.sha256()
  for path, f in files:
    data = f.read_bytes()
    h.update(f"{path}\0{len(data)}\0".encode("utf-8"))
    h.update(data)
  return h.hexdigest()

def _hash(data:bytes) -> str:
  ":returns: A hash of a file's contents (see *STAMP*)."
  return hashlib.sha256(data).hexdigest()

def _fileHash(path:str) -> str|None:
  ":returns: A hash of the file *path*'s contents (see *_hash()*), or None if it isn't there."
  try:
    with open(path, "rb") as f:
      return _hash(f.read())
  except FileNotFoundError:
    return None

def _path(dest:str, rel:str) -> str:
  ":returns: The file *rel* (a path with \"/\") in the folder *dest*."
  return os.path.join(dest, *rel.split("/"))

def usersFile(rel:str) -> bool:
  '''
  :param rel: A file in a plugin's folder, as a path in it, with "/" (eg: "knet.snv").
  :returns: Whether it's of a kind the user may change, and keep (see *USER_FILES*).
  '''
  name = rel.rpartition("/")[2]
  return any(fnmatch.fnmatch(name, p) for p in USER_FILES)

def _install(manifest:Manifest, files:list[tuple[str, Traversable]], dest:str,
             record:dict[str, str]|None) -> tuple[dict[str, str], list[str]]:
  '''
  Install a plugin's *files* (see *_bundledFiles()*) in *dest* (see
  *installBundled()*): write each that isn't there as it comes (its models
  and views relocated: see *_relocated()*) -- but for the user's (see
  *USER_FILES*) that aren't as they were installed (*record*) -- and remove
  those installed before (in *record*) that it no longer comes with, if
  they're as they were installed.

  :param record: What was installed there before (see *STAMP*), if that's known.
  :returns: What's installed there now (path -> hash: see *STAMP*), and the
    user's files that were kept (paths).
  '''
  os.makedirs(dest, exist_ok=True)
  uri = Path(dest).as_uri() + "/"
  now:dict[str, str] = {}
  kept:list[str] = []
  for rel, f in files:
    data = f.read_bytes()
    if rel.endswith((".snm", ".snv")):
      data = _relocated(data, manifest.id, uri)
    path = _path(dest, rel)
    new, there = _hash(data), _fileHash(path)
    if there is not None and there != new and usersFile(rel) and (record is None or record.get(rel) != there):
      kept.append(rel) # (the user's: changed since it was installed, or not installed by this -- eg: made by the user)
      if record is not None and rel in record:
        now[rel] = record[rel] # (still not as it was installed)
      continue
    if there != new:
      os.makedirs(os.path.dirname(path), exist_ok=True)
      with open(path, "wb") as fd:
        fd.write(data)
    now[rel] = new
  for rel, h in (record or {}).items(): # (what it came with before, and no longer does)
    if rel in now or rel in kept:
      continue
    path = _path(dest, rel)
    there = _fileHash(path)
    if there is None:
      continue
    if there != h: # (changed since it was installed: the user's now)
      kept.append(rel)
      continue
    os.remove(path)
    folder = os.path.dirname(path)
    while folder != dest and os.path.isdir(folder) and not os.listdir(folder):
      os.rmdir(folder)
      folder = os.path.dirname(folder)
  return now, kept

NOT_INSTALLED = ("__pycache__", "*.pyc", "*.log", ".gitignore", ".DS_Store", STAMP)
"The files in any plugin's folder not to install (see *installBundled()*): patterns of their names."

def installed(manifest:Manifest, path:str) -> bool:
  '''
  :param manifest: A plugin's description.
  :param path: A file or folder in its folder, as a path in it, with "/" (eg: "examples/books.xml").
  :returns: Whether it's installed (see *installBundled()*): it isn't one of *NOT_INSTALLED*, nor its *Manifest.exclude*.
  '''
  name = path.rpartition("/")[2]
  return not any(fnmatch.fnmatch(name, p) for p in NOT_INSTALLED) and not any(fnmatch.fnmatch(path, p) for p in manifest.exclude)

def _relocated(data:bytes, id:str, uri:str) -> bytes:
  '''
  Make a plugin's model or view (.snm, .snv), being installed, refer to where
  it now is: to files in a folder of the plugin's name (where it was written:
  eg: the project's plugins/pythonParser/, or a placeholder, such as
  file:///SEMANTIC_NETS_PLUGINS/rnetReader/), as to the same files there --
  so that it isn't taken to have been moved when it's read (as
  *sn.copyExamples()* does for the example models).

  :param data: The file's contents.
  :param id: The plugin's folder's name.
  :param uri: The URL of the folder it's installed in, ending in "/".
  :returns: Them, so changed (or as they were, if they aren't text).
  '''
  try:
    text = data.decode("utf-8")
  except UnicodeError:
    logger.warning(f'Couldn\'t make a file of the plugin {id} refer to where it now is: it isn\'t text.')
    return data
  pattern = re.compile(r'file://[^"\'<>\s]*/' + re.escape(id) + "/")
  return pattern.sub(lambda _m: uri, text).encode("utf-8")

def namespace(folder:str) -> types.ModuleType:
  '''
  :param folder: The plugins folder.
  :returns: The package plugins are imported in (*NAMESPACE*), whose path is
    *folder* -- made, if it isn't there yet (or is another folder's).
  '''
  ns = sys.modules.get(NAMESPACE)
  if ns is None or list(getattr(ns, "__path__", [])) != [folder]:
    ns = types.ModuleType(NAMESPACE, "The installed plugins (see sn.plugins).")
    ns.__path__ = [folder]
    sys.modules[NAMESPACE] = ns
  return ns

def importBundled(id:str, module:str="") -> types.ModuleType:
  '''
  For scripts and tests: import a plugin that comes with the program where it
  is (see *bundledFolder()*) -- not installed, nor registered -- or a module in it.

  :param id: The plugin's folder name: eg: "pythonParser".
  :param module: A module in it (eg: "parser"); by default, the plugin's package itself.
  :returns: It.
  '''
  namespace(str(bundledFolder()).rstrip("/")) # (a zip file's folder is imported from by zipimport)
  return importlib.import_module(f"{NAMESPACE}.{id}" + (f".{module}" if module else ""))

class PluginContext:
  '''
  What a plugin's ``register(ctx)`` is given: the editor, and ways to add to
  it, so that it needn't know how the editor's made.
  '''
  def __init__(self, app:Any, manifest:Manifest):
    '''
    :param app: The editor (an *Application*: anything with a *menubar*, a tk.Menu).
    :param manifest: The plugin's description.
    '''
    self.app = app
    "The editor."
    self.manifest = manifest
    "The plugin's description."
    self.logger:sn.SNLogger = sn.getLogger(manifest.module)
    "The plugin's logger."

  @property
  def folder(self) -> str:
    "The plugin's folder: eg, for files that come with it."
    return self.manifest.folder

  def prefKey(self, key:str) -> str:
    ''':returns: The preference the plugin calls *key*: ``plugins/<folder>/<key>``.'''
    return f"plugins/{self.manifest.id}/{key}"

  def pref(self, key:str, default:Any=None) -> Any:
    '''
    :param key: One of the plugin's preferences (see *prefKey()*).
    :param default: Its value, if it hasn't one.
    :returns: Its value.
    '''
    return snPrefs.get(self.prefKey(key), default)

  def setPref(self, key:str, value:Any) -> None:
    '''Set one of the plugin's preferences (see *prefKey()*): kept with the program's.'''
    snPrefs[self.prefKey(key)] = value

  def menu(self, path:str) -> tk.Menu:
    '''
    :param path: A menu-bar menu, or a submenu in one: eg: "Tools", or
      "Python/Recent" (``/`` separates them). A top-level menu that isn't
      there is added before the Window menu (or at the end, if there's none),
      and a submenu that isn't there at the end of its menu.
    :returns: It.
    '''
    menu:tk.Menu = self.app.menubar
    for depth, label in enumerate(p.strip() for p in path.split("/")):
      sub = _cascade(menu, label)
      if sub is None:
        sub = tk.Menu(menu, tearoff=False)
        before = _index(menu, "Window") if depth == 0 else None
        if before is None:
          menu.add_cascade(label=label, menu=sub)
        else:
          menu.insert_cascade(before, label=label, menu=sub)
      menu = sub
    return menu

  def addMenuItem(self, path:str, command:Callable[[], Any], **options:Any) -> None:
    '''
    Add an item to the menu bar's menus.

    :param path: Where: its menu's path (see *menu()*) and its label, eg:
      "Tools/Python Parser...", "Python/Recent/Last one"; just a label puts it
      in the *TOOLS_MENU*.
    :param command: What it does. (An exception it raises is logged, and shown.)
    :param options: Other options for the item (eg: accelerator).
    '''
    menuPath, _, label = path.rpartition("/")
    def run() -> None:
      try:
        command()
      except Exception:
        self.logger.error(f'The plugin {self.manifest.name}\'s "{label}" failed.', exc_info=True)
        from util.utils import showExceptionDialog
        showExceptionDialog(title=f"{self.manifest.name}: {label.strip()}") # (no parent: the editor's main window is hidden)
    from util.utils import afterMenu
    self.menu(menuPath or TOOLS_MENU).add_command(label=label.strip(), command=afterMenu(run), **options) # (on the Mac, once the menu's done with: a dialog it opens can wait)

  def addSeparator(self, path:str=TOOLS_MENU) -> None:
    '''Add a separator to the end of a menu (see *menu()*).'''
    self.menu(path).add_separator()

def _index(menu:tk.Menu, label:str) -> int|None:
  ''':returns: The index of *menu*'s item labelled *label*, if there is one.'''
  last = menu.index(tk.END)
  for i in range(last + 1 if last is not None else 0):
    try:
      if menu.entrycget(i, "label") == label:
        return i
    except tk.TclError: # (a separator, or a tear-off, has no label)
      pass
  return None

def _cascade(menu:tk.Menu, label:str) -> tk.Menu|None:
  ''':returns: The submenu of *menu*'s item labelled *label*, if there is one.'''
  i = _index(menu, label)
  if i is None or menu.type(i) != "cascade":
    return None
  return menu.nametowidget(menu.entrycget(i, "menu"))

@dataclass
class Plugin:
  '''A plugin that's been loaded.'''
  manifest:Manifest
  module:types.ModuleType
  context:PluginContext

loaded:dict[str, Plugin] = {}
"The plugins loaded: folder name -> it."

problems:dict[str, str] = {}
"The plugins that couldn't be loaded: folder name -> why."

def load(app:Any, manifest:Manifest) -> Plugin:
  '''
  Import a plugin, trust it for hooks, and have it add itself to the editor
  (its ``register(ctx)``).

  :param app: The editor.
  :param manifest: The plugin's description.
  :returns: It.
  :raises PluginError: If it's for a later sn, or can't be imported, or registered.
  '''
  if version(manifest.snVersion) > version(sn.VERSION):
    raise PluginError(f"{manifest.name} {manifest.version} needs {sn.NAME} {manifest.snVersion} or later.")
  namespace(os.path.dirname(manifest.folder))
  try:
    module = importlib.import_module(manifest.module)
  except Exception as ex:
    raise PluginError(f"{manifest.name} can't be imported: {ex}") from ex
  register = getattr(module, "register", None)
  if not callable(register):
    raise PluginError(f"{manifest.name} has no register(ctx) function (in its __init__.py).")
  hooks.trust(manifest.module)
  context = PluginContext(app, manifest)
  try:
    register(context)
  except Exception as ex:
    hooks.trust(manifest.module, False)
    raise PluginError(f"{manifest.name} couldn't add itself to the editor: {ex}") from ex
  return Plugin(manifest, module, context)

def loadAll(app:Any, folder:str|None=None) -> dict[str, Plugin]:
  '''
  Load the plugins in *folder* (see *load()*) -- but those the "plugins/disabled"
  preference lists -- noting those that can't be in *problems* (and the log).

  :param app: The editor.
  :param folder: The plugins folder (by default, *PLUGINS_FOLDER*).
  :returns: The plugins loaded (*loaded*).
  '''
  disabled = snPrefs.get(DISABLED_PREF, [])
  disabled = {str(d).strip() for d in disabled} if isinstance(disabled, list) else set()
  for m in manifests(folder if folder is not None else PLUGINS_FOLDER):
    if m.id in loaded or m.id in disabled:
      continue
    try:
      loaded[m.id] = load(app, m)
      problems.pop(m.id, None)
      logger.info(f"Loaded the plugin {m.name} {m.version}.")
    except PluginError as ex:
      problems[m.id] = str(ex)
      logger.warning(f"Plugin not loaded: {ex}", exc_info=ex.__cause__ is not None)
  return loaded
