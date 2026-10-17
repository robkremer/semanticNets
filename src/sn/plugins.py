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
folder (see *installBundled()*) when they aren't there, or are older --
copied, not loaded where they are, so that what's in them (eg: an ontology
models are built on) stays at the same place when the app is moved or updated.

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
import importlib
import os
import re
import shutil
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
  :param text: A version: eg: "1.2.10".
  :type text: str
  :returns: It, to compare with another: eg: (1, 2, 10). (A part that isn't a
    number counts as 0.)
  :rtype: tuple[int, ...]
  '''
  return tuple(int(p) if p.isdigit() else 0 for p in str(text).strip().split("."))

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
    :type folder: str | Traversable
    :returns: Its description.
    :rtype: Manifest
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
  :rtype: Traversable
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
  :type folder: str | Traversable
  :returns: The descriptions of the plugins in it (folders with a *MANIFEST*),
    by folder name; any that can't be read are logged, and left out.
  :rtype: list[Manifest]
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
  Copy the plugins that come with the program into the plugins folder: those
  that aren't there, or are older there (by their version) -- replacing them
  -- but for the files they say not to (see *Manifest.exclude*), and making
  their models and views refer to where they now are (see *_relocate()*).

  :param source: Where the plugins that come with the program are (by default, *bundledFolder()*).
  :type source: str | Traversable | None
  :param target: The plugins folder (by default, *PLUGINS_FOLDER*).
  :type target: str | None
  :returns: The plugins copied (their folders' names).
  :rtype: list[str]
  '''
  ret = []
  for m in manifests(source if source is not None else bundledFolder()):
    dest = os.path.join(target if target is not None else PLUGINS_FOLDER, m.id)
    if os.path.isfile(os.path.join(dest, MANIFEST)):
      try:
        if version(Manifest.read(dest).version) >= version(m.version):
          continue
      except PluginError:
        pass # (it's replaced)
    try:
      if os.path.exists(dest):
        shutil.rmtree(dest)
      _copy(m, m.source if m.source is not None else Path(m.folder), dest)
    except (OSError, zipfile.BadZipFile):
      logger.error(f'Couldn\'t install the plugin {m.name} in "{dest}".', exc_info=True)
      continue
    _relocate(dest)
    logger.info(f'Installed the plugin {m.name} {m.version} in "{dest}".')
    ret.append(m.id)
  return ret

NOT_INSTALLED = ("__pycache__", "*.pyc", "*.log", ".gitignore", ".DS_Store")
"The files in any plugin's folder not to install (see *installBundled()*): patterns of their names."

def installed(manifest:Manifest, path:str) -> bool:
  '''
  :param manifest: A plugin's description.
  :type manifest: Manifest
  :param path: A file or folder in its folder, as a path in it, with "/" (eg: "examples/books.xml").
  :type path: str
  :returns: Whether it's installed (see *installBundled()*): it isn't one of *NOT_INSTALLED*, nor its *Manifest.exclude*.
  :rtype: bool
  '''
  name = path.rpartition("/")[2]
  return not any(fnmatch.fnmatch(name, p) for p in NOT_INSTALLED) and not any(fnmatch.fnmatch(path, p) for p in manifest.exclude)

def _copy(manifest:Manifest, source:Traversable, dest:str, rel:str="") -> None:
  '''
  Copy the plugin's folder *source* (or a folder in it: *rel*) to *dest*: what's
  to be installed (see *installed()*) -- from a folder, or a zip file.
  '''
  os.makedirs(dest, exist_ok=True)
  for child in source.iterdir():
    path = rel + child.name
    if not installed(manifest, path):
      continue
    if child.is_dir():
      _copy(manifest, child, os.path.join(dest, child.name), path + "/")
    else:
      with open(os.path.join(dest, child.name), "wb") as f:
        f.write(child.read_bytes())

def _relocate(folder:str) -> None:
  '''
  Make the models and views (.snm, .snv) in a plugin's folder, just copied
  there, refer to where they now are: to files in a folder of the plugin's
  name (where they were written: eg: the project's plugins/pythonParser/), as
  to the same files here -- so that they aren't taken to have been moved when
  they're read (as *sn.copyExamples()* does for the example models).

  :param folder: The plugin's folder, in the plugins folder.
  :type folder: str
  '''
  pattern = re.compile(r'file://[^"\'<>\s]*/' + re.escape(os.path.basename(folder)) + "/")
  uri = Path(folder).as_uri() + "/"
  for dirpath, _dirs, files in os.walk(folder):
    for f in files:
      if f.endswith((".snm", ".snv")):
        path = os.path.join(dirpath, f)
        try:
          with open(path, encoding="utf-8") as fd:
            text = fd.read()
          new = pattern.sub(lambda _m: uri, text)
          if new != text:
            with open(path, "w", encoding="utf-8") as fd:
              fd.write(new)
        except (OSError, UnicodeError):
          logger.warning(f'Couldn\'t make "{path}" refer to where it now is.', exc_info=True)

def namespace(folder:str) -> types.ModuleType:
  '''
  :param folder: The plugins folder.
  :type folder: str
  :returns: The package plugins are imported in (*NAMESPACE*), whose path is
    *folder* -- made, if it isn't there yet (or is another folder's).
  :rtype: types.ModuleType
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
  :type id: str
  :param module: A module in it (eg: "parser"); by default, the plugin's package itself.
  :type module: str
  :returns: It.
  :rtype: types.ModuleType
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
    :type app: Any
    :param manifest: The plugin's description.
    :type manifest: Manifest
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
    :type key: str
    :param default: Its value, if it hasn't one.
    :type default: Any
    :returns: Its value.
    :rtype: Any
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
    :type path: str
    :returns: It.
    :rtype: tk.Menu
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
    :type path: str
    :param command: What it does. (An exception it raises is logged, and shown.)
    :type command: Callable[[], Any]
    :param options: Other options for the item (eg: accelerator).
    :type options: Any
    '''
    menuPath, _, label = path.rpartition("/")
    def run() -> None:
      try:
        command()
      except Exception:
        self.logger.error(f'The plugin {self.manifest.name}\'s "{label}" failed.', exc_info=True)
        from util.utils import showExceptionDialog
        showExceptionDialog(title=f"{self.manifest.name}: {label.strip()}") # (no parent: the editor's main window is hidden)
    self.menu(menuPath or TOOLS_MENU).add_command(label=label.strip(), command=run, **options)

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
  :type app: Any
  :param manifest: The plugin's description.
  :type manifest: Manifest
  :returns: It.
  :rtype: Plugin
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
  :type app: Any
  :param folder: The plugins folder (by default, *PLUGINS_FOLDER*).
  :type folder: str | None
  :returns: The plugins loaded (*loaded*).
  :rtype: dict[str, Plugin]
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
