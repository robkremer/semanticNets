#################################################################################
# (c) Copyright 2024-2026, Rob Kremer, MIT open source license.                 #
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
'''
.. inheritance-diagram::
      Application
      AppWindow
      AppPanedWidget
      SNGViewFrame
      sn.view.graphics.sngView.SNGView
      sn.view.graphics.sngContext.SNGContext
      sn.model.model.Model
    :parts: 2
    :private-bases:
    :top-classes: tkinter.PanedWindow, tkinter.Frame, tkinter.Canvas, tkinter.BaseWidget, tkinter.Tk, tkinter.Toplevel

    
.. figure:: /images/guiApp.png
   :width: 800px
   :alt: Relationship diagram for the guiApp classes.
   :align: center
   
   Relationship diagram for the guiApp classes.
   
Created on Aug 18, 2026

@author: robkremer
'''
from __future__ import annotations
import sn # (first: it sets up logging -- see sn/__init__.py -- before util's modules, which get their loggers as they're imported)
import traceback
from util.persistence.serialize import SerializationStrategy
from util.persistence.pRef import PRDb
from util.attributeEditor import applyEditAttrsBox
from util.attribute import Attribute, VAR_DEFAULTED
import sys
import atexit
import os
from pathlib import Path
import tkinter as tk
import tkinter.filedialog as filedialog
from tkinter import messagebox
from typing import cast, TYPE_CHECKING
from types import NoneType
from tkinter import ttk
from sn import snPrefs
from util.utils import afterMenu, showExceptionDialog, fixURL, urlExists,\
  isValidURL, keepLast
from util.platformSupport import MAC, shortcut, openFile, setUpLook, setDPIAware, documentsFolder
from util.singleInstance import SingleInstance
from util.terminal import terminalRegistry, installGlobalIORouting,\
  TerminalWidget, TerminalRegistry
from sn.model.model import Model
from sn.view.graphics import progress
from sn.view.graphics.directoryWindow import DirectoryPane, ReadProgress, noteFolderOf, seedSearchPath, askModelURL
from sn.model.directory import Entry, pathOf, isRemote
if TYPE_CHECKING:
  from sn.view.textUserInterface import SNTerminalWidget
  from sn.view.graphics.sngView import SNGView

logger:sn.SNLogger = sn.getLogger(__name__)

class UnexpectedObjectInFile(Exception):
  pass

class Application(tk.Tk):
  """The invisible root Tk window and manages one or more Toplevel windows.

  :param appName: Name used for the hidden root window's title (mostly cosmetic,
    since it's never shown).
  :type appName: str
  """

  current:Application|None = None
  "The application (there's just the one)."

  def __init__(self):
    super().__init__()
    self.withdraw()  # hide before it can ever flash visible
    Application.current = self
    self.title(sn.NAME)
    self.defaultChildLocation:tuple[int, int] = (20, 60)

    self.windows: dict[str, AppWindow] = {}
    self.terminalRegistry = terminalRegistry  # shared across all windows
    self.directoryPane:DirectoryPane|None = None
    "The model directory, once it's been shown: it fills this (the main) window (see *showDirectory()*)."
    self._directoryShown = tk.BooleanVar(self, value=False) # (the Window menu's check mark)
    self._directoryShownForProgress = False
    progress.listener = self._onProgress
    from sn.view.graphics.sngView import SNGView
    SNGView.askForMissingModel = self.askForMissingModel # (see readModel() in SNGView.getInstantiationInfo())

    self.option_add('*tearOff', tk.FALSE) # (before any menu's made: Windows' and X11's menus have tear-off lines otherwise)
    setUpLook(self)
    installGlobalIORouting(self.terminalRegistry)  # install exactly once, here
    self._installSettingsMenu()
    self._installQuitHandler()
    self.menubar = self._installMenubar()

    self.protocol("WM_DELETE_WINDOW", self._onDirectoryClose) # (it's the model directory, when it's shown)

  def _noOp(self) -> None:
    """Root window has no close button the user can reach, but guard anyway.
    """
    pass
  
  def _installSettingsMenu(self) -> None:
    """Wire up a Settings item under the app item in the menu bar.

    On macOS, Tk always shows an "Application menu" — the one named after
    the app, to the immediate right of the Apple logo — whether or not the
    app defines any menu of its own. That's "the app item." Its
    "Preferences…" entry is present but disabled/inert unless something
    registers the special Tcl command 'tk::mac::ShowPreferences'; this does
    that registration, so choosing it (or its standard ⌘, shortcut) opens
    openSettings() below.

    On Windows/Linux, Tk has no equivalent automatic app menu, so this
    command is never invoked there: Settings is in the File menu there
    instead (see *_installMenubar()*).

    Called once, from __init__: there's exactly one root/"app item" no
    matter how many AppWindows get opened, so this belongs here rather
    than being (re-)registered — and guarded against re-registration —
    from every window.
    """
    self.createcommand("tk::mac::ShowPreferences", afterMenu(self.openSettings)) # (its dialog waits: not from inside the menu's action)

  def _installQuitHandler(self) -> None:
    """Wire up the "Quit" item under the app item in the menu bar.

    Same macOS mechanism as *_installSettingsMenu()* above, but where
    "Preferences…" is inert until registered, "Quit \\<AppName\\>" already
    does something by default: Tk wires it to the Tcl procedure
    'tk::mac::Quit', whose default implementation calls Tcl's own *exit*
    command directly. Since Tcl is embedded inside this same Python process
    (not the reverse), that tears the whole process down at the C level
    without ever going back through CPython's normal shutdown sequence --
    which is the only thing that runs the *atexit* callbacks registered in
    *sn/__init__.py* (*saveAtExit()*, *savePrefsIfChanged()*). Registering our own
    handler here (see *onQuit()*) intercepts that default and runs the same
    cleanup explicitly before tearing down, instead of silently skipping it.

    Called once, from __init__, alongside _installSettingsMenu() -- see its
    docstring for why this belongs here rather than being (re-)registered
    from every window.
    """
    self.createcommand("tk::mac::Quit", self.onQuit)
    self.createcommand("::tk::mac::OpenDocument", self.onOpenDocument)
    self.createcommand("::tk::mac::ShowHelp", lambda: self.showHelp("user/index.html")) # (the Help menu's own "<App> Help" item)

  def onOpenDocument(self, *paths:str) -> None:
    """Handle files the Finder asks a packaged app to open (double-clicked,
    or dropped on its icon) -- the macOS way of passing them, rather than the
    command line. Each opens in a window, as with *Open...*.

    :param paths: The files' paths.
    """
    self._openedDocuments = True # (see startUp(): not then reopening the last session too)
    for p in paths:
      self.openWindow(p)

  def onOpenFromAnotherCopy(self, paths:list[str]) -> None:
    """Handle the editor being started again while it's running (on Windows
    and Linux: see *main()*): open the files it was started with, each in a
    window, as *onOpenDocument()* does; or if there are none, bring a window
    to the front.

    :param paths: The files.
    """
    if paths:
      for p in paths:
        self.openWindow(p)
      return
    window = next(reversed(list(self.windows.values())), None)
    if window is not None:
      window.deiconify()
      window.lift()
      window.focus_force()
    else:
      self.showDirectory()

  def onQuit(self) -> None:
    """Handle the "Quit \\<AppName\\>" item in macOS's automatic app menu.

    See *_installQuitHandler()* for why this override is necessary at all:
    without it, quitting via that menu item (or its Cmd+Q shortcut) bypasses
    Python's normal interpreter shutdown entirely, so the *atexit*-registered
    *saveAtExit()*/*savePrefsIfChanged()* never run and unsaved models/views are
    silently lost. Call them explicitly here, then tear down.
    """
    self.rememberOpenWindows() # (before they're closed: see reopenWindows())
    self.closeAllWindows() # each gets the same save check as closing it by hand
    sn.saveAtExit()
    sn.savePrefsIfChanged()
    self.quit()
    sys.exit(0)  #TODO: shouldn't be necessary -- self.quit()/destroy() should
    #             have exited the app on its own, but doesn't; mirrors the
    #             same workaround in loggingPanedWindow.py's AppWindow.onQuit().

  def _installMenubar(self) -> tk.Menu:
    """Builds the app menu bar.

    Creates the menu bar. Tk *will*
    keep auto-populating a cascade we create under one of its reserved
    names ("apple", "window", "help"), so recreate "window" and "help" here
    to get that native content back. 

    Called once, from __init__, alongside _installSettingsMenu().

    :returns: The menu bar.
    """
    menubar:tk.Menu = tk.Menu(self)
    
    self.filemenu = tk.Menu(menubar, name="file")
    self.filemenu.add_command(label="New...", command=afterMenu(self.doNew)) # (afterMenu(): its dialog waits)
    self.filemenu.add_command(label="Open...", command=afterMenu(self.doOpen))
    self.filemenu.add_command(label="Open URL...", command=afterMenu(self.doOpenURL))
    self.recentMenu = tk.Menu(self.filemenu, name="recent")
    self.filemenu.add_cascade(label="Open Recent", menu=self.recentMenu)
    self._fillRecentMenu()
    self.filemenu.add_separator()
    # "Save view" is NOT added here: whichever SNGView's AppWindow currently
    # has focus adds/removes it itself (see SNGView.onWindowFocusIn/Out(),
    # util.utils.addToMenuBar()/removeFromMenuBar()), so the item is only ever
    # present -- and only ever targets the right view -- while some window
    # is actually focused.
    # TODO (Rob): "Save model", "Save view as...", "Save model as..." go here too.
    menubar.add_cascade(menu=self.filemenu, label="File")

    self.windowmenu = tk.Menu(menubar, name="window")  # macOS auto-fills this (window list, Move & Resize, ...)
    menubar.add_cascade(menu=self.windowmenu, label="Window")
    self.windowmenu.add_checkbutton(label="Model Directory", variable=self._directoryShown,
                                    command=lambda: self.showDirectory(self._directoryShown.get()))
    self.windowmenu.add_separator()

    self.helpmenu = tk.Menu(menubar, name="help")  # macOS auto-fills this (search field, "Python Help", ...)
    menubar.add_cascade(menu=self.helpmenu, label="Help")
    self.helpmenu.add_command(label=f"{sn.NAME} User Guide", command=afterMenu(lambda: self.showHelp("user/index.html")))
    self.helpmenu.add_command(label=f"{sn.NAME} Developer Guide", command=afterMenu(lambda: self.showHelp("developer/index.html")))
    self.helpmenu.add_command(label="Keys and Mouse", command=afterMenu(lambda: self.showHelp("user/shortcuts.html")))
    self.helpmenu.add_separator()
    self.helpmenu.add_command(label="Install Example Models", command=afterMenu(self.onInstallExamples))
    self.helpmenu.add_command(label="Reveal Plugins Folder", command=afterMenu(self.revealPlugins))

    if not MAC:
      # (on the Mac, Settings and Quit are in the app's own menu: see
      # _installSettingsMenu(), _installQuitHandler(); elsewhere, they end the
      # File menu, below whatever the windows add to it -- see keepLast())
      settingsKey, quitKey = shortcut("comma", label=","), shortcut("q")
      self.filemenu.add_separator()
      self.filemenu.add_command(label="Settings...", command=self.openSettings, accelerator=settingsKey[1])
      self.filemenu.add_command(label="Quit", command=self.onQuit, accelerator=quitKey[1])
      keepLast(self.filemenu, "Settings...", "Quit")
      self.bind_all(settingsKey[0], lambda _e: self.openSettings())
      self.bind_all(quitKey[0], lambda _e: self.onQuit())

    self.config(menu=menubar)
    return menubar

  def showHelp(self, page:str) -> None:
    """Show a page of the documentation in the web browser: the copy bundled
    in a packaged app, or else the project's built documentation.

    :param page: The page, relative to the documentation's top, eg: "user/index.html".
    """
    import webbrowser
    for top in (sn.resourcePath("help"), sn.resourcePath("sphinx", "build", "html")):
      path = os.path.join(top, page)
      if os.path.exists(path):
        webbrowser.open(Path(path).as_uri())
        return
    logger.error(f'The documentation ("{page}") isn\'t available: build it with the "doc" ant target.')

  def openSettings(self) -> None:
    """Show the app-wide Settings dialog: an attribute editor on *sn.snPrefs*,
    applying the changes to it (saved when the program ends: see
    *sn.savePrefsIfChanged()*). Only the settings' values are shown: their
    types and qualifiers are fixed, and their notes -- documentation, from
    *sn.PREFS* -- are their names' tooltips.
    """
    applyEditAttrsBox(self, snPrefs, title="Semantic Nets Preferences", hideColumns=("type", "qualifiers", "note"))
    self._fillRecentMenu() # (in case "gui/recentFiles" changed)

  def doOpen(self, ): 
    'Respond to the "Open..." menu item.'
    filename = filedialog.askopenfilename(
                title="Open a view (.snv) file or the default view for a model (.snm) file.",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
  
  def doOpenURL(self) -> None:
    '''
    Respond to the "Open URL..." menu item: open a view, or a model in its
    default view, at a URL (eg: on the web: opened read-only -- see
    *openEntry()*).
    '''
    from sn.model.directory import scanFile, scanURL
    url = askModelURL(self.focus_get() or self, "Open URL",
                      prompt='The URL of a view (.snv), or a model (.snm) to open in its default view -- '
                             'eg: "https://example.org/ontologies/animals.snm":')
    if url:
      path = pathOf(url)
      self.openEntry(scanFile(path) if path is not None else scanURL(url))

  def doNew(self, ): 
    'Respond to the "New..." menu item.'
    filename = filedialog.asksaveasfilename(
                title="Specify a view (.snv) file (you will be asked for the corresponding model) or model (.snm) file to create a default view for.",
                defaultextension=".snv",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
  
  def openWindow(self, viewSpec:Model|SNGView|str) -> tk.Toplevel|None:
    """Create and show a new Toplevel window hosted under the invisible root.

    :param viewSpec: What to show: a model (in its view, beside it: read, or
      made), a view (eg: one just made, to be saved somewhere else: its own
      window), or a model's or view's file or URL.
    :returns: The newly created Toplevel window.
    """
    from sn.view.graphics.sngView import SNGView
    assert isinstance(viewSpec, (Model,SNGView,str,NoneType))
    
    def makeViewFromModel(model:Model) -> SNGView:
      remote = isRemote(model.url) # (eg: on the web: its view there is read, not written -- "Save view as..." saves a copy)
      url = fixURL(model.url, ".snv", replaceExt=True, mode="" if remote else 'w')[0]
      if url in self.windows:
        # This model's view already has an open window -- hand back its live
        # SNGView as-is rather than re-decoding the .snv file from disk. This
        # matters for more than just avoiding wasted work: re-reading here
        # unconditionally, on every repeat "Open" of an already-loaded model,
        # is what let a stale/bad persisted "model" reference on disk (e.g. a
        # .snv pointing at the wrong -- or, worse, a self-referential -- URL)
        # get re-triggered by a second open of a file that hadn't actually
        # changed. The one-and-only decode of this .snv already happened when
        # its window was first opened; trust that live object instead.
        existingView = self.windows[url].view
        assert isinstance(existingView, SNGView)
        return existingView
      if urlExists(url):
        ret = PRDb.readFile(url, mode="r" if remote else "w")
        assert isinstance(ret, SNGView)
      else:
        ret = SNGView(url, model=model, mode="" if remote else "w")
      return ret
    
    reading = ReadProgress()
    PRDb.readProgress = reading
    try:
      model:Model|None = None
      view:SNGView|None = None
      
      if isinstance(viewSpec, Model):
        view = makeViewFromModel(viewSpec)
      elif isinstance(viewSpec, SNGView):
        view = viewSpec
      else:
        if not isValidURL(viewSpec):
          viewSpec = fixURL(viewSpec, None, replaceExt=None, mode='w')[0]
        if isValidURL(viewSpec):
          if urlExists(viewSpec): # we got reference to a file that could be a Model or a SNGView
            # We don't yet know which of the two this file holds, and legally
            # it could be either -- but SerializationStrategy.readx() finding
            # out FOR us means fully decoding it, which means constructing
            # (and registering into PRDb.AllDBs) whatever's in it. Peeking
            # first tells us the type for free -- no construction, no
            # PRDb.AllDBs registration, no side effects at all -- so we only
            # ever construct the one object we actually end up wanting, and
            # only via the single readx() call below meant for it.
            readMode = "r" if isRemote(viewSpec) else "w" # (on the web, say: it can be read, not written)
            peekedType = SerializationStrategy.peekTypex(viewSpec, replaceExt=None, mode=readMode)
            if issubclass(peekedType, SNGView): # it's a view -- if it's already open, we're done.
              if viewSpec in self.windows:
                view = cast(SNGView, self.windows[viewSpec].view)
              else:
                obj = PRDb.readFile(viewSpec, mode=readMode)
                if not isinstance(obj, SNGView):
                  raise TypeError(f'Expected type Model in "{viewSpec}", but got type {type(obj)}.')
                view = obj
            elif issubclass(peekedType, Model): # it's a model -- read it, then find/create its view.
              modelOrView = PRDb.readFile(viewSpec, mode=readMode) if isRemote(viewSpec) else Model(viewSpec)
              assert isinstance(modelOrView, Model)
              view = makeViewFromModel(modelOrView)
            else: # it's something we didn't expect
              raise UnexpectedObjectInFile(f'File "{viewSpec}" contains an object of type {peekedType.__name__}. Expected a Model or a SNGView object')
          else: # A new file
            if viewSpec.endswith(".snm"): # we were given a non-existant model file so create a default model and it's default view.
              viewURL = fixURL(viewSpec, ".snv", replaceExt=True, mode='w')[0]
              view = SNGView(viewURL, model=Model(viewSpec), mode='w')
            elif viewSpec.endswith(".snv"): # we were given a non-existant view file, need a model
              modelURL = filedialog.askopenfilename(
                title=f"Open a Model file for the new view {viewSpec}",
                filetypes=[("Model files", "*.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
              if not modelURL: # (cancelled: "" or ())
                return None 
              # (the one in memory, if it's there -- eg: its default view's open: reading its file again would
              # read it into that model again, and that view would show every object in it, as just added)
              modelURL = fixURL(modelURL, None, replaceExt=None, mode='r')[0]
              obj = PRDb.AllDBs.get(modelURL) or PRDb.readFile(modelURL, mode='r')
              if not isinstance(obj, Model):
                raise TypeError(f'Expected type Model in "{modelURL}", but got type {type(obj)}.')
              model = obj
              view = SNGView(viewSpec, model=model)
            else:
              splt = viewSpec.rsplit(".", 1)
              ext = "" if len(splt)==1 else splt[1] 
              raise NameError(f'Don\'t know what to do with a file ending in ".{ext}"')
        else:
          raise ReferenceError(f'Invalid URL: {viewSpec}')
      
      name = view.url    
      self.noteRecent(view.url, view.model.url)
      self.noteFile(view.url, view.model.url)
      if name in self.windows:
        self.windows[name].lift()
        return self.windows[name]
  
      self.defaultChildLocation = (self.defaultChildLocation[0] + 40, self.defaultChildLocation[1] + 40)
      self.windows[name] = view.window
      self._refreshDirectory()
      return view.window
    
    except Exception:
      logger.error(f'While opening window for viewSpec "{viewSpec}"')#, exc_info=True)
      try:
        print(traceback.format_exc(), file=sys.__stderr__)
        showExceptionDialog(self, title=f"Semantic Nets: Failed to open window for Model {viewSpec.url if isinstance(viewSpec, Model) else viewSpec}.")
      except Exception:
        logger.error('While displaying exception dialog', exc_info=True)
      return None
    finally:
      PRDb.readProgress = None
      reading.finish()


  def openViewOn(self, model:Model, viewURL:str) -> tk.Toplevel|None:
    '''
    Open a window on *model*: its view saved at *viewURL* if there is one
    there (see *openWindow()*), or else a new view of it that'll be saved
    there -- eg: a model with no file of its own (the system model, sn), or one
    read from a copy (the base rules).

    :param model: The model.
    :param viewURL: Where its view is (or will be) saved.
    :returns: The window.
    '''
    from sn.view.graphics.sngView import SNGView
    if viewURL in self.windows:
      self.windows[viewURL].lift()
      return self.windows[viewURL]
    if urlExists(viewURL):
      return self.openWindow(viewURL)
    try:
      view = SNGView(viewURL, model=model, mode="w")
    except Exception:
      logger.error(f'While opening a view of "{model.url}" at "{viewURL}"', exc_info=True)
      return None
    self.defaultChildLocation = (self.defaultChildLocation[0] + 40, self.defaultChildLocation[1] + 40)
    self.windows[view.url] = view.window
    return view.window

  # ── A view's model ───────────────────────────────────────────────────────

  def modelCopiesOf(self, url:str) -> list[Entry]:
    '''
    :param url: Where a model was.
    :returns: The models that have been moved or copied from there (see
      *Directory.copiesOf()*): in the model directory, if it's been filled;
      else in the search path's folders on this computer.
    '''
    from sn.model.directory import copiesOf
    from sn.view.graphics.directoryWindow import searchPath
    pane = self.directoryPane
    if pane is not None and pane.directory.entries:
      return pane.directory.copiesOf(url)
    try:
      return copiesOf(url, searchPath())
    except Exception:
      logger.warning(f'Couldn\'t look for copies of "{url}".', exc_info=True)
      return []

  def askForMissingModel(self, viewURL:str, modelURL:str) -> str|None:
    '''
    A view being read names a model that can't be found (eg: it's been
    moved): ask which to show in its place (see *SNGView.askForMissingModel*).

    :returns: Its URL; or None (cancelled).
    '''
    from sn.view.graphics.chooseModelDialog import ChooseModelDialog
    view, model = _fileName(viewURL) or viewURL, _filePath(modelURL) or modelURL
    return ChooseModelDialog(self.focus_get() or self, f"{view}: its model can't be found",
                             f'The view "{view}" shows the model\n\n  {model}\n\nwhich isn\'t there. Which model '
                             f'should it show? (Its objects show the objects with the same ids in it.) '
                             f'Cancel to open it with an empty model there.',
                             self.modelCopiesOf(modelURL), near=viewURL, ok="Open").show()

  def changeModel(self, view:SNGView, url:str) -> tk.Toplevel|None:
    '''
    Show another model in *view* (File | Change model...): eg, a copy of its
    model. Its window is closed and the view's read again from its file, with
    the model at *url* in place of its own (see *SNGView.modelReplacements*):
    its objects show the objects with the same ids in it. It's changed then:
    saving it names the new model. (Its unsaved changes are lost: see
    *FilesMixin.doChangeModel()*.)

    :returns: The view's new window, if it's opened.
    '''
    from sn.view.graphics.sngView import SNGView
    old = view.model.url
    name = next((k for k, w in self.windows.items() if w is view.window), None)
    if name is not None:
      self._closeWindow(name, quitIfLast=False, askToSave=False)
    SNGView.modelReplacements[old] = url
    try:
      return self.openWindow(view.url)
    finally:
      del SNGView.modelReplacements[old]

  # ── The model directory ──────────────────────────────────────────────────

  DIRECTORY_PREF = ".directory"
  '''The model directory's geometry, if it was shown when the app last quit
  (see *rememberOpenWindows()*); else "". (Hidden from Settings: see
  *OPEN_WINDOWS_PREF*.)'''

  DIRECTORY_GEOMETRY = "860x520+40+60"
  "Where the model directory's first shown."

  PROGRESS_DELAY = 0.5
  "Seconds a job (eg: opening a file) goes on before the directory's shown, if it's hidden, for its progress bar."

  def directoryShown(self) -> bool:
    '''
    :returns: Whether the model directory is shown (see *showDirectory()*).
    '''
    return self.directoryPane is not None and self.state() != "withdrawn"

  def showDirectory(self, show:bool=True, geometry:str|None=None) -> None:
    '''
    Show (or hide) the model directory (see *DirectoryPane*): the models and
    views in the search path's folders. It's this, the app's main window --
    hidden while it isn't shown. (Window | Model Directory.)

    :param geometry: Its size and position, if not as it was.
    '''
    if show:
      if self.directoryPane is None:
        examples = os.path.expanduser(os.path.join(self.EXAMPLES_FOLDER, "x.snm"))
        seedSearchPath([u for e in self.recentFiles() for u in (e.get("view", ""), e.get("model", "")) if u] + [examples])
        self.title(f"{sn.NAME}: Model Directory")
        self.directoryPane = DirectoryPane(self)
        self.directoryPane.pack(fill=tk.BOTH, expand=True)
        self.geometry(geometry or self.DIRECTORY_GEOMETRY)
        self.directoryPane.rescan()
      elif geometry:
        self.geometry(geometry)
      self.deiconify()
      self.lift()
    else:
      self.withdraw()
    self._directoryShown.set(show)
    self._directoryShownForProgress = False

  def _onDirectoryClose(self) -> None:
    '''
    The model directory's close button: hide it -- and if there are no other
    windows, quit, as closing the last window does.
    '''
    self.showDirectory(False)
    if not self.windows:
      self.onQuit()

  def _refreshDirectory(self) -> None:
    "Show what's open, and what isn't, in the model directory (if it's been shown)."
    if self.directoryPane is not None:
      self.directoryPane.refresh()

  def noteFile(self, *urls:str) -> None:
    '''
    Models or views at *urls* have been opened, made or saved: add their
    folders to the search path (if they aren't in it), and show them in the
    model directory as they are now.
    '''
    added = [noteFolderOf(url) for url in urls]
    pane = self.directoryPane
    if pane is None:
      return
    if any(added):
      pane.rescan()
      return
    for url in urls:
      path = pathOf(url)
      if path:
        pane.directory.update(path)
    pane.refresh()

  def openEntry(self, entry:Entry, readOnly:bool=False) -> tk.Toplevel|None:
    '''
    Open a model directory entry: a view, or a model in its default view (see
    *openWindow()*).

    :param entry:
    :type entry: sn.model.directory.Entry
    :param readOnly: Whether to write-lock its model, so it can't be changed
      (nor saved). Not if the model's open already, and not locked: it's
      opened as it is then (and the user's told).
    :returns: Its window.
    '''
    if entry.remote: # (it can't be saved there)
      readOnly = True
    modelURL = entry.url if entry.kind == "model" else entry.modelURL
    already = PRDb.AllDBs.get(modelURL) if modelURL else None # @undefinedVariable
    if readOnly and already is not None and not already.writeLocked():
      messagebox.showinfo(sn.NAME, f'"{entry.name}" isn\'t opened read-only: its model, '
                          f'"{_fileName(already.url)}", is already open, and can be changed.', parent=self)
      readOnly = False
    window = self.openWindow(entry.path or entry.url)
    view = getattr(window, "view", None)
    if readOnly and view is not None and already is None:
      view.model._writeLocked = True
      bar = view.__dict__.get("_reasoningToolbar")
      if bar is not None:
        bar.refreshLock()
      logger.info(f'"{view.model.url}" is open read-only (write-locked): it can\'t be changed or saved.')
      self._refreshDirectory()
    return window

  def _onProgress(self, label:str|None, done:int, total:int|None) -> None:
    '''
    Show how a job's going (see *progress*) in the model directory -- showing
    it, if it's hidden, once the job's gone on for *PROGRESS_DELAY* seconds
    (and hiding it again when it's done).
    '''
    import time
    if label is None:
      self.__dict__.pop("_progressSince", None)
      if self._directoryShownForProgress: # (hidden once the event loop's back: hiding it now could run what's queued, mid-job)
        self.after(100, self._hideAfterProgress)
    elif not self.directoryShown():
      since = self.__dict__.setdefault("_progressSince", time.monotonic())
      if time.monotonic() - since >= self.PROGRESS_DELAY:
        self.showDirectory()
        self._directoryShownForProgress = True
    if self.directoryPane is not None and self.directoryShown():
      self.directoryPane._showProgress(label, done, total)

  def _hideAfterProgress(self) -> None:
    "Hide the model directory, if it was shown just for a job's progress (see *_onProgress()*), and no job's under way now."
    if self._directoryShownForProgress and not progress.busy():
      self.showDirectory(False)

  RECENT_PREF = ".recentFiles"
  '''The preference listing the views opened most recently, most recent first
  (see *noteRecent()*). (Hidden from Settings: see *OPEN_WINDOWS_PREF*.)'''

  RECENT_KEPT = 50
  "How many recent views are remembered, whatever \"gui/recentFiles\" (how many are listed) is."

  def recentFiles(self) -> list[dict[str, str]]:
    '''
    :returns: The views opened most recently, most recent first: each
      {"view": its URL, "model": its model's URL}.
    '''
    entries = snPrefs.get(self.RECENT_PREF, [])
    return [e for e in entries if isinstance(e, dict) and e.get("view")] if isinstance(entries, list) else []

  def _setRecentFiles(self, entries:list[dict[str, str]]) -> None:
    snPrefs[self.RECENT_PREF] = Attribute(entries[:self.RECENT_KEPT], list, VAR_DEFAULTED,
      "The views opened most recently (view and model), most recent first: for File | Open Recent.")
    self._fillRecentMenu()

  def noteRecent(self, viewURL:str, modelURL:str) -> None:
    '''
    Put a view (and its model) at the top of the recently opened ones (see
    *recentFiles()*, and File | Open Recent).
    '''
    entries = [e for e in self.recentFiles() if e.get("view") != viewURL]
    self._setRecentFiles([{"view": viewURL, "model": modelURL}, *entries])

  def openRecent(self, entry:dict[str, str]) -> None:
    '''
    Open a recently opened view (File | Open Recent): its view, if it's been
    saved; else its model (with its default view). If neither can be found any
    more, say so, and take it off the list.

    :param entry: One of *recentFiles()*.
    '''
    viewURL, modelURL = entry.get("view"), entry.get("model")
    spec = viewURL if viewURL and urlExists(viewURL) else modelURL if modelURL and urlExists(modelURL) else None
    if spec is None:
      logger.warning(f'Can\'t open "{_fileName(viewURL or "")}": neither it nor its model "{modelURL}" can be found. It\'s been taken off File | Open Recent.')
      self._setRecentFiles([e for e in self.recentFiles() if e.get("view") != viewURL])
      return
    self.openWindow(spec)

  def _fillRecentMenu(self) -> None:
    '''
    (Re)fill the File | Open Recent menu from *recentFiles()*: as many as the
    "gui/recentFiles" preference says, each named by its file (and, if two have
    the same name, its folder), then "Clear Menu".
    '''
    menu = self.__dict__.get("recentMenu")
    if menu is None:
      return
    menu.delete(0, tk.END)
    pref = snPrefs.get("gui/recentFiles", 10)
    count = max(0, pref) if isinstance(pref, int) else 10
    entries = self.recentFiles()[:count]
    names = [_fileName(e["view"]) for e in entries]
    for e, name in zip(entries, names):
      label = name
      if names.count(name) > 1: # (eg: two family.snv's: say which)
        label = f"{name} \u2014 {os.path.basename(os.path.dirname(_filePath(e['view'])))}"
      menu.add_command(label=label, command=afterMenu(lambda e=e: self.openRecent(e)))
    if entries:
      menu.add_separator()
    menu.add_command(label="Clear Menu", command=lambda: self._setRecentFiles([]),
                     state=tk.NORMAL if entries else tk.DISABLED)

  OPEN_WINDOWS_PREF = ".openWindows"
  '''The preference recording the windows open when the app last quit (see
  *rememberOpenWindows()*). (Its name starts with ".", so the Settings dialog
  doesn't show it: it isn't for the user to edit.)'''

  def rememberOpenWindows(self) -> None:
    '''
    Record the open windows -- each one's view, its model and its size and
    position -- in the preferences, for *reopenWindows()* the next time the app
    starts. (When packaged as a .app, the app is normally started with no
    files to open, so this is how it comes back the way it was left.)
    '''
    entries = []
    for window in self.windows.values():
      view = window.view
      if view is None:
        continue
      try:
        entries.append({"view": view.url, "model": view.model.url, "geometry": window.geometry()})
      except Exception:
        logger.warning(f'Couldn\'t record window "{window.title()}" for reopening.', exc_info=True)
    snPrefs[self.OPEN_WINDOWS_PREF] = Attribute(entries, list, VAR_DEFAULTED,
      "The windows open when the app last quit (view, model, size and position), reopened when it next starts.")
    snPrefs[self.DIRECTORY_PREF] = Attribute(self.geometry() if self.directoryShown() else "", str, VAR_DEFAULTED,
      "The model directory's size and position, if it was shown when the app last quit (it's shown again when it next starts).")

  def reopenWindows(self) -> int:
    '''
    Reopen the windows recorded by *rememberOpenWindows()*, in the same size
    and position. A view that was never saved opens as its model's default
    view; one whose files have gone is skipped (with a message). The views
    open as they were last saved -- unsaved changes, and the undo history,
    are gone.

    :returns: The number of windows reopened.
    '''
    entries = snPrefs.get(self.OPEN_WINDOWS_PREF, [])
    count = 0
    for entry in entries if isinstance(entries, list) else []:
      if not isinstance(entry, dict):
        continue
      viewURL, modelURL = entry.get("view"), entry.get("model")
      spec = viewURL if viewURL and urlExists(viewURL) else modelURL if modelURL and urlExists(modelURL) else None
      if spec is None:
        logger.warning(f'Not reopening "{viewURL}": neither it nor its model "{modelURL}" can be found.')
        continue
      window = self.openWindow(spec)
      if window is not None:
        count += 1
        if entry.get("geometry"):
          try:
            window.geometry(entry["geometry"])
          except tk.TclError:
            pass
    return count

  def startUp(self, files:list[str]) -> None:
    '''
    Open a window on each of *files* (views, .snv, or models, .snm); with none,
    reopen the windows open when the app last quit (see *reopenWindows()*) --
    and the model directory, if it was shown then -- and if there were none,
    show the model directory (see *showDirectory()*).

    :param files: Files named on the command line.
    '''
    files = [f for f in files if not f.startswith("-psn_")] # (a process serial number some macOS versions pass to an app)
    self.loadPlugins()
    for f in files:
      self.openWindow(f)
    if files or getattr(self, "_openedDocuments", False):
      return
    geometry = snPrefs.get(self.DIRECTORY_PREF, "")
    if isinstance(geometry, str) and geometry:
      self.showDirectory(geometry=geometry)
    if self.reopenWindows() > 0:
      return
    if not snPrefs.get(self.EXAMPLES_PREF, False) and self.installExamples():
      return
    self.showDirectory()

  def loadPlugins(self) -> None:
    '''
    Install the plugins that come with the program (if they're missing, or
    older), and load the plugins (see *sn.plugins*): they add to the menu bar.
    Done on start-up (see *startUp()*), not when an Application's made, so
    that a script (eg: a test) that makes one gets the editor without them.
    '''
    from sn import plugins
    plugins.installBundled()
    plugins.loadAll(self)

  def revealPlugins(self) -> None:
    '''
    The Help menu's *Reveal Plugins Folder*: open the folder the plugins are
    installed in (see *sn.plugins.PLUGINS_FOLDER*) in the Finder -- made, if
    it isn't there yet. (A plugin added or changed there is loaded when the
    editor next starts.)
    '''
    import webbrowser
    from sn import plugins
    os.makedirs(plugins.PLUGINS_FOLDER, exist_ok=True)
    try:
      openFile(plugins.PLUGINS_FOLDER)
    except OSError:
      webbrowser.open(Path(plugins.PLUGINS_FOLDER).as_uri())

  EXAMPLES_PREF = ".examplesInstalled"
  "True once the example models have been installed (see *installExamples()*): it's only done once. (Hidden from Settings: see *OPEN_WINDOWS_PREF*.)"

  EXAMPLES_FOLDER = os.path.join(documentsFolder(), f"{sn.NAME} Examples")
  "Where *installExamples()* puts the example models."

  def installExamples(self, replace:bool=False) -> bool:
    """Copy the example models that come with the app into *EXAMPLES_FOLDER*,
    and open their views: on the first launch (see *startUp()*), or when asked
    to (see *onInstallExamples()*).

    :param replace: Whether to replace copies already there. If not (as on
      the first launch), an existing folder is left as it is.

    :returns: True iff any were opened.
    """
    if not sn.exampleNames():
      return False
    target = os.path.expanduser(self.EXAMPLES_FOLDER)
    try:
      if replace or not os.path.exists(target): # (unless replacing, an existing copy is left as it is)
        sn.copyExamples(target)
    except OSError:
      logger.error(f'Couldn\'t copy the examples to "{target}".', exc_info=True)
      return False
    snPrefs[self.EXAMPLES_PREF] = True
    views = sorted(f for f in os.listdir(target) if f.endswith(".snv"))
    for v in views:
      self.openWindow(os.path.join(target, v))
    return len(views) > 0

  def onInstallExamples(self) -> None:
    """The Help menu's *Install Example Models*: put fresh copies of the
    example models that come with this version of the app in *EXAMPLES_FOLDER*
    -- replacing any copies there (once the user agrees: changes made to them
    are lost) -- and open them. Their windows are closed first, and the models
    forgotten, so the new files are read afresh. (Any other files in the folder
    are left alone.)
    """
    from util.persistence.pRef import PRDb
    target = os.path.expanduser(self.EXAMPLES_FOLDER)
    names = sn.exampleNames()
    if not names:
      messagebox.showerror(sn.NAME, "This version doesn't have any example models to install.")
      return
    existing = [n for n in names if os.path.exists(os.path.join(target, n))]
    if existing and not messagebox.askokcancel(sn.NAME,
        f'Replace the example models in "{target}" with fresh copies?\n\n'
        "Any changes you've made to them will be lost.", icon=messagebox.WARNING):
      return
    prefix = Path(target).as_uri() + "/"
    # Another model that builds on an example (eg: one of its types isa an
    # example's) would be left pointing at the old examples: stop, with
    # nothing changed. (Views of the examples are fine: they're closed below.)
    users = sorted({url for db in list(PRDb.AllDBs.values()) if isinstance(db, Model) and db.url.startswith(prefix) # @undefinedVariable
                        for kind, url in db.dependents() if kind == "model" and not url.startswith(prefix)})
    if users:
      messagebox.showerror(sn.NAME, "The example models can't be replaced while other models use them:\n\n  "
                           + "\n  ".join(users) + "\n\nModels stay in memory until you quit: quit, start again, and install "
                           "the examples before opening those.")
      return
    for name, window in list(self.windows.items()): # (their windows: no "save changes?" -- the user has just agreed to lose them)
      view = window.view
      if name.startswith(prefix) or (view is not None and view.model is not None and view.model.url.startswith(prefix)):
        self._closeWindow(name, quitIfLast=False, askToSave=False)
    for url in [u for u in PRDb.AllDBs if u.startswith(prefix)]: # (forget the old models, so the new files are read)
      db = PRDb.AllDBs[url]
      if isinstance(db, Model):
        db.unload() # (and unlink it from the system model's objects)
      else:
        del PRDb.AllDBs[url]
    self.installExamples(replace=True)

  def closeModel(self, model:Model, askToSave:bool=True, quitIfNone:bool=True) -> bool:
    """The File menu's *Close model*: close every window on *model* (offering
    to save each changed view, as closing them by hand does), offer to save the
    model if it's changed, and forget it -- so opening it again reads the file
    afresh. If that was the last window, the app quits, as it does when the
    last window is closed by hand.

    A model that other loaded models build on (eg: one of their types isa one
    of its) can't be closed: they'd be left pointing at it. Nothing is changed
    then.

    :param model: The model.
    :param askToSave: Whether to offer to save the model and its changed
      views. False when they're being replaced (see *replacingModel()*).
    :param quitIfNone: Whether to quit if no window is left open. False when
      another is about to be opened (see *replacingModel()*).
    :returns: Whether it was closed.
    """
    users = sorted({url for kind, url in model.dependents() if kind == "model"})
    if users:
      messagebox.showerror(sn.NAME, f'"{os.path.basename(model.url)}" can\'t be closed while other models use it:\n\n  '
                           + "\n  ".join(users) + "\n\nModels stay in memory until you quit.")
      return False
    for name, window in list(self.windows.items()):
      if window.view is not None and window.view.model is model:
        self._closeWindow(name, quitIfLast=False, askToSave=askToSave)
    if askToSave:
      sn.checkSaveModified(model, model.url, "model") # (now or never: once forgotten, quitting won't ask)
    try:
      model.unload()
    except RuntimeError: # (eg: a view of it that isn't in a window: it stays in memory, as before)
      logger.warning(f'Couldn\'t forget model "{model.url}".', exc_info=True)
    self._refreshDirectory()
    if quitIfNone and not self.windows and not self.directoryShown():
      self.rememberOpenWindows() # (none: it was closed on purpose, so it isn't reopened next time)
      self.quit()
    return True

  def replacingModel(self, path:str, askToSave:bool=False) -> bool:
    """Before a model's file is made afresh, in place of the one that's there
    (eg: by a plugin, once the user's agreed to replace it): if the model at
    *path* is in memory -- eg: its window is open -- close its windows, without
    offering to save them (they're being replaced), and forget it. Otherwise
    *Model(path)* would hand back that model, with all it had, and what's made
    would be added to it -- and its open views told of each new object.

    Or, with *askToSave*, before a model's file is changed by a program (eg: a
    plugin updating it): offering to save it, and its changed views, first --
    so that the program reads (and changes) the file as it's been left.

    :param path: The model's file (or URL).
    :param askToSave: Whether to offer to save the model and its changed views.
    :returns: False if it can't be forgotten (other models use it: see
      *closeModel()*), and so mustn't be replaced; else True.
    """
    model = PRDb.AllDBs.get(PRDb.resolveURL(fixURL(path, None, replaceExt=None, mode="w")[0])) # @undefinedVariable
    if not isinstance(model, Model):
      return True
    return self.closeModel(model, askToSave=askToSave, quitIfNone=False)

  def closeAllWindows(self) -> None:
    """Close every hosted window via *_closeWindow()*, so each view gets
    exactly the same save check (and clean-up) on quitting as it would if
    the user closed its window individually.
    """
    for name in list(self.windows):
      self._closeWindow(name, quitIfLast=False)

  def _closeWindowOf(self, window: "AppWindow") -> None:
    """Close *window* (its close button: see *AppWindow*), whatever it's
    filed under in *windows* -- which needn't be the URL it was made with
    (eg: a copied file's view is filed under where it is now, or a view saved
    as another file). One that isn't filed at all is still closed.

    :param window: The window.
    """
    name = next((k for k, w in self.windows.items() if w is window), None)
    if name is None:
      logger.warning(f'Closing a window that isn\'t in the list of open windows: "{window.title()}".')
      name = f"<unlisted window {id(window)}>"
      self.windows[name] = window # (so it's closed just as any other)
    self._closeWindow(name)

  def _closeWindow(self, name: str, quitIfLast: bool = True, askToSave: bool = True) -> None:
    """Close a specific hosted window and check whether the app should exit.

    :param name: The window's key, as passed to openWindow.
    :param quitIfLast: Quit the application if this was the last window.
      False when the caller is already quitting (see *closeAllWindows()*).
    :param askToSave: Whether to offer to save the window's view if it's
      changed. False when the user has already agreed to lose the changes
      (see *onInstallExamples()*).
    """
    if quitIfLast and list(self.windows) == [name] and not self.directoryShown(): # closing the last window quits: remember it for next time
      self.rememberOpenWindows()
    window = self.windows.pop(name, None)
    if window is not None:
      # Give the user a chance to save this window's SNGView before it's
      # gone for good. SNGViews are never memory-resident (see
      # sn.saveAtExit()'s comment on that), so closing a window individually
      # -- rather than quitting the whole app -- is the ONLY chance to save
      # it; nothing else keeps a reference to it once the window is torn
      # down. Must happen before onWindowFocusOut()/destroy() below.
      if window.view is not None:
        if askToSave:
          sn.checkSaveModified(window.view, window.view.url, "view")
        window.view.detachFromModel() # (the model stays in memory: its changes mustn't reach this window once it's gone)
      # If this window's view is currently the one advertising "Save view"
      # in the File menu, make sure it's withdrawn -- closing a window isn't
      # guaranteed to fire a Tk <FocusOut> on its widgets first (unlike
      # AppWindow._onWindowFocusOut()/_checkStillActive(), which handles the
      # ordinary defocus-without-closing case).
      if window.view is not None:
        window.view.onWindowFocusOut()
      self.terminalRegistry.onFocusOut(window.appPanedWidget.canvasFrame.terminal)
      self.terminalRegistry.unregisterWindow(window)
      window.destroy()

    self._refreshDirectory()
    if quitIfLast and not self.windows and not self.directoryShown(): # (with the directory shown, the app carries on)
      self.quit()

  def quit(self) -> None:
    """Tear down the entire application, including the hidden root.
    """
    self.destroy()

  def run(self) -> None:
    """Start the Tk event loop.
    """
    self.mainloop()


def _filePath(url:str) -> str:
  '''
  :param url: A file's URL (eg: "file:///Users/me/family.snv").
  :returns: Its path.
  '''
  from util.utils import urlPath
  path = urlPath(url)
  return path if path is not None else url

def _fileName(url:str) -> str:
  '''
  :param url: A file's URL.
  :returns: Its name (eg: "family.snv").
  '''
  return os.path.basename(_filePath(url)) or url

class AppWindow(tk.Toplevel):
  '''
  A top-level SN app window that also acts as the holder of the SNContext
  Model controller.
  '''

  def __init__(self, tkdottk:tk.Tk, viewURL:str, geometry:str="300x400+20+20", **kwargs):
    '''
    A window for the view at *viewURL*: titled with it, at *geometry*; closing it closes the view's window
    (see *Application._closeWindowOf()*).
    '''
    from sn.view.graphics.sngView import SNGView
    
    # initialize the window
    super().__init__(tkdottk, **kwargs)
    self.geometry(geometry)
    name = viewURL
    self.title(name)
    self.protocol("WM_DELETE_WINDOW", lambda: self._root()._closeWindowOf(self)) #type: ignore[misc, attr-defined]

    self.view: SNGView|None = None
    'The SNGView that owns this window -- set by SNGView.__init__() right after it constructs this AppWindow, so this window\'s FocusIn/FocusOut handling (see _onWindowFocusIn()/_onWindowFocusOut()) can dispatch straight to the SNGView that should react to it.'

    # create content
    self.appPanedWidget = AppPanedWidget(self)
    self.appPanedWidget.pack(fill=tk.BOTH, side=tk.RIGHT, expand=True, padx=0, pady=0)
    # Each window has the app's menu bar, which Tk copies for it and keeps up
    # to date as items are added and taken away. Elsewhere it's drawn in the
    # window; on the Mac it's put at the top of the screen while the window is
    # in front. (Tk 8.6 on the Mac left the last menu bar showing for a window
    # without one, but Tk 9 shows its bare default menu bar instead.)
    self.config(menu=tkdottk.cget("menu"))

    self.option_add('*tearOff', tk.FALSE)

    self._bindFocusTracking(self)

  def _bindFocusTracking(self, widget: tk.Misc) -> None:
    """Recursively bind <FocusIn>/<FocusOut> on this widget and all its
    descendants so this *AppWindow* notices when the user's focus enters or
    genuinely leaves it, wherever within it that focus lands.

    Binding only on ``self`` (the *AppWindow*/*Toplevel* itself) is not
    enough -- Tk's FocusIn/FocusOut events fire on the specific widget that
    gained/lost focus, not on its ancestors, so focusing e.g. a canvas or
    entry deep inside this window would never reach a binding placed only
    on the top-level widget. Same shape of problem as (and modeled on)
    *_bindFocusRouting()* above.

    :param widget: The widget (and its children, recursively) to bind.
    :type widget: tk.Widget
    """
    widget.bind("<FocusIn>", self._onWindowFocusIn, add="+")
    widget.bind("<FocusOut>", self._onWindowFocusOut, add="+")
    if widget is self: # (the window made active again -- eg: after a dialog, or another application -- needn't give any widget a FocusIn)
      widget.bind("<Activate>", self._onWindowFocusIn, add="+")
      if MAC:
        widget.bind("<Activate>", lambda e: self._refreshSizeLimits() if e.widget is self else None, add="+")
    for child in widget.winfo_children():
      self._bindFocusTracking(child)

  def _refreshSizeLimits(self) -> None:
    """Have Tk recompute this window's largest size from the screens there are now.

    On the Mac, Tk gives a window a maximum size (the area all the screens
    cover) only when it sets the window's geometry, and doesn't update it
    when a screen is added or rearranged: a window opened before a bigger
    monitor was connected couldn't be made any larger than the old screens.
    Setting the minimum size (to what it is) has Tk set both limits again.
    """
    self.wm_minsize(*self.wm_minsize())

  def _onWindowFocusIn(self, event=None) -> None:
    """Some widget inside this window just gained focus -- let this
    window's *SNGView* (if any) know it's now the focused one.

    :param event: The Tk event.
    """
    if self.view is not None:
      self.view.onWindowFocusIn()

  def _onWindowFocusOut(self, event=None) -> None:
    """Some widget inside this window just lost focus.

    This alone doesn't mean the *window* was deactivated -- moving focus
    between two widgets in the SAME window (e.g. tabbing fields) fires a
    FocusOut on the old one too. Defer the real check to *_checkStillActive()*
    via *after_idle()*, by which point the new focus owner (if any) has
    already been set, so *self.focus_get()* reliably reflects where focus
    actually ended up.

    :param event: The Tk event.
    """
    self.after_idle(self._checkStillActive)

  def _checkStillActive(self) -> None:
    """Let this window's *SNGView* (if any) know focus has genuinely moved
    outside this window (as opposed to just moving between two of its own
    descendant widgets -- see *_onWindowFocusOut()*).
    """
    app = self._root() #type: ignore[attr-defined]
    try:
      current = app.focus_get()
    except Exception: # (eg: focus in a native dialog, which Tk can't name)
      current = None
    if current is None:
      # Focus is nowhere Tk knows of: another application, or a native dialog
      # (eg: a save dialog) -- this window is still the one the menu bar is
      # for when the application is active again, so it keeps its items.
      return
    top = current.winfo_toplevel()
    if top is self or getattr(top, "view", None) is not None:
      # Still here; or now in another view's window, which put its own items in
      # the menu bar when it gained focus (perhaps before this ran): leave them be.
      return
    if self.view is not None: # (in another of the application's windows: eg: the attribute editor)
      self.view.onWindowFocusOut()

  def _bindFocusRouting(self, widget: tk.Misc, terminal: SNTerminalWidget) -> None:
    """Recursively bind <FocusIn>/<FocusOut> on this widget and all its
    descendants so that focusing ANY widget in the window (terminal or
    graphics editor) sets this window's terminal as the default stdio/input()
    routing target.

    :param widget: The widget (and its children, recursively) to bind.
    :type widget: tk.Widget
    :param terminal: This window's terminal — the routing target.
    """
    widget.bind("<FocusIn>", lambda e, t=terminal: self._root().terminalRegistry.onFocusIn(t), add="+") #type: ignore[attr-defined,call-overload]
    widget.bind("<FocusOut>", lambda e, t=terminal: self._root().terminalRegistry.onFocusOut(t), add="+") #type: ignore[attr-defined,call-overload]
    for child in widget.winfo_children():
      self._bindFocusRouting(child, terminal)


class AppPanedWidget(tk.PanedWindow):
  '''
  A (tkinter.PanedWindow) with two panes: above, and application widget according the
  *frame* parameter of the constructor, and below, a disabled text widget which is used
  by this class's various service methods to display messages such as logging info:

    +-------------------------+
    |                         |
    |AppPanedWidget (graphics)|
    |                         |
    +-------------------------+
    | SNTerminalWidget (text) |
    +-------------------------+
  '''

  def __init__(self, parent:AppWindow, **kwargs):
    r"""
    :param parent: The parent *AppWindow*.
    :param fixedAppFrame: [bool, default:False] Specifies whether the application *frame*
      is fixed-size or stretchable.
    :param commandParser: [CommandParser , default: an new *TygraCommandParser()* ] User input
      from the *commmandEntryWidget* is sent to this parser.
    :param \*\*kwargs: An arguments *dict* to passed to the *tk.PanedWindow* constructor.
      The following arguments are defaulted if not present:

        - "orient" default = tk.VERTICAL
        - "showhandle" default = False
        - "sashwidth" default = 3
        - "bd" default = 4
        - "bg" default = "grey"
        - "borderwidth" default = 0
    """
    assert isinstance(parent, AppWindow)
    # fix up kwargs to contain the necessary defaults and create the PanedWindow (super).
    if "orient" not in kwargs: kwargs["orient"] = tk.VERTICAL
    if "showhandle" not in kwargs: kwargs["showhandle"] = False
    if "handlesize" not in kwargs: kwargs["handlesize"] = 8
    if "sashwidth" not in kwargs: kwargs["sashwidth"] = 6
    if "sashrelief" not in kwargs: kwargs["sashrelief"] = "ridge"  # "groove"#"sunken"#
    if "bg" not in kwargs: kwargs["bg"] = "darkgrey" #lightgrey"
    if "borderwidth" not in kwargs: kwargs["borderwidth"] = 0

    # super constructor
    super().__init__(parent, **kwargs)

    # set up the textDisplayFrame (contains the *loggingWidget* , *commandEntryWidget* and *promptLabel*
    # No registry passed explicitly — it defaults to the same module-level
    # singleton this file already imports for its own use (installGlobalIORouting,
    # onFocusIn/onFocusOut below).
    self.textDisplayFrame = tk.Frame(self)#SNTerminalWidget(self.model, self, context=self.context)
    self.textDisplayFrame.pack(fill=tk.NONE, side=tk.BOTTOM, expand=False)
    stretch = 'never'  # if fixedAppFrame else 'never'
    sticky = 'news'  # if fixedAppFrame else 'new'
    self.add(self.textDisplayFrame, stretch=stretch, sticky=sticky)
    self.paneconfigure(self.textDisplayFrame, stretch=stretch, height=60, minsize=20)

    self.canvasFrame:SNGViewFrame = SNGViewFrame(self)
    self.canvasFrame.pack(fill=tk.BOTH, side=tk.TOP, expand=False)
    stretch = 'always'  # if self.fixedAppFrame else 'always'
    sticky = 'news'  # if self.fixedAppFrame else 'news'
    self.add(self.canvasFrame, before=self.textDisplayFrame, stretch=stretch, sticky=sticky)  # 'always', 'first', 'last', 'middle', and 'never'.
    self.paneconfigure(self.canvasFrame, stretch=stretch, minsize=0)

    # Give the graphics editor a direct reference to this window's terminal
    # and the shared registry, so it can bind its own background threads
    # (runBackgroundWork below) without having to walk back up through
    # winfo_toplevel()/_root() to find them.
    self.canvasFrame.registry = terminalRegistry

    self.pack(fill=tk.BOTH, expand=True)


class SNGViewFrame(tk.Frame):

  def __init__(self, parent:AppPanedWidget, **kwargs):
    '''
    :param parent: The master Widget.
    :param kwargs: Passed to *Canvas*.
    '''
    assert isinstance(parent, AppPanedWidget)
    # self.scrollRegion:list = [0,0,1000,1000]
    tk.Frame.__init__(self, parent)

    self.hScroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
    self.vScroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
    kwargs["yscrollcommand"] = self.vScroll.set
    kwargs["xscrollcommand"] = self.hScroll.set
    if "bg" not in kwargs: 
      kwargs["bg"] = snPrefs.get('gui/backgroundColor', storeDefault="grey95", storeType="color")
    if kwargs["bg"] == "": # "" (transparent) color isn't allowed here.
      kwargs["bg"] = "white"

    # Call the tk.Canvas and PRDb constructors
    self.canvas = tk.Canvas(self, **kwargs)#SNCanvas(self, **kwargs)

    self.hScroll['command'] = self.canvas.xview
    self.vScroll['command'] = self.canvas.yview

    self.canvas.grid(column=0, row=0, sticky=tk.N + tk.W + tk.E + tk.S)
    self.hScroll.grid(column=0, row=1, sticky=tk.W + tk.E)
    self.vScroll.grid(column=1, row=0, sticky=tk.N + tk.S)
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(0, weight=1)
    
    self.terminal:TerminalWidget
    self.registry:TerminalRegistry


def main() -> None:
  """Run the graphical editor: a window on each file named on the command
  line, or else as *Application.startUp()* says. On Windows and Linux, if the
  editor's already running, the files are handed to it instead (see
  *util.singleInstance*): on the Mac, the Finder does that itself (see
  *Application.onOpenDocument()*)."""
  instance:SingleInstance|None = None
  if not MAC:
    instance = SingleInstance(sn.SHORT_NAME, sn.SN_FOLDER)
    if instance.handOff(sys.argv[1:]):
      return
    atexit.register(instance.close)
  setDPIAware() # (before the first window)
  app = Application()
  if instance is not None:
    instance.listen(app, app.onOpenFromAnotherCopy)
  app.after(1000, app.startUp, sys.argv[1:])
  app.run()

if __name__ == "__main__":
  # (run as "python -m sn.view.graphics.guiApp", this module is __main__: run the one imported as
  # sn.view.graphics.guiApp instead, so there's one Application class -- whose current one, eg, the views ask for)
  from sn.view.graphics.guiApp import main as packageMain
  packageMain()
