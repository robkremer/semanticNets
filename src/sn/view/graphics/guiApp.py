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
      sn.view.graphics.sngView.SNGContext
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
import os
from pathlib import Path
import tkinter as tk
import tkinter.filedialog as filedialog
from tkinter import messagebox
from typing import cast
from types import NoneType
from tkinter import ttk
from sn import snPrefs
from util.utils import showExceptionDialog, fixURL, urlExists,\
  isValidURL
from util.terminal import terminalRegistry, installGlobalIORouting,\
  TerminalWidget, TerminalRegistry
from sn.model.model import Model

logger:sn.SNLogger = sn.getLogger(__name__)

class UnexpectedObjectInFile(Exception):
  pass

class Application(tk.Tk):
  """The invisible root Tk window and manages one or more Toplevel windows.

  :param appName: Name used for the hidden root window's title (mostly cosmetic,
    since it's never shown).
  :type appName: str
  """

  def __init__(self):
    super().__init__()
    self.withdraw()  # hide before it can ever flash visible
    self.title(sn.NAME)
    self.defaultChildLocation:tuple[int, int] = (20, 60)

    self.windows: dict[str, AppWindow] = {}
    self.terminalRegistry = terminalRegistry  # shared across all windows

    installGlobalIORouting(self.terminalRegistry)  # install exactly once, here
    self._installSettingsMenu()
    self._installQuitHandler()
    self.menubar = self._installMenubar()

    self.protocol("WM_DELETE_WINDOW", self._noOp)  # root itself is never closed by the user

  def _noOp(self) -> None:
    """Root window has no close button the user can reach, but guard anyway.

    :rtype: None
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
    command is simply never invoked there — harmless, but it means Settings
    currently has no menu entry point on those platforms. Revisit with a
    real cross-platform Menu/menu bar if that's ever needed.

    Called once, from __init__: there's exactly one root/"app item" no
    matter how many AppWindows get opened, so this belongs here rather
    than being (re-)registered — and guarded against re-registration —
    from every window.

    :rtype: None
    """
    self.createcommand("tk::mac::ShowPreferences", self.openSettings)

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

    :rtype: None
    """
    self.createcommand("tk::mac::Quit", self.onQuit)
    self.createcommand("::tk::mac::OpenDocument", self.onOpenDocument)
    self.createcommand("::tk::mac::ShowHelp", lambda: self.showHelp("user/index.html")) # (the Help menu's own "<App> Help" item)

  def onOpenDocument(self, *paths:str) -> None:
    """Handle files the Finder asks a packaged app to open (double-clicked,
    or dropped on its icon) -- the macOS way of passing them, rather than the
    command line. Each opens in a window, as with *Open...*.

    :param paths: The files' paths.
    :type paths: str
    :rtype: None
    """
    self._openedDocuments = True # (see startUp(): not then reopening the last session too)
    for p in paths:
      self.openWindow(p)

  def onQuit(self) -> None:
    """Handle the "Quit \\<AppName\\>" item in macOS's automatic app menu.

    See *_installQuitHandler()* for why this override is necessary at all:
    without it, quitting via that menu item (or its Cmd+Q shortcut) bypasses
    Python's normal interpreter shutdown entirely, so the *atexit*-registered
    *saveAtExit()*/*savePrefsIfChanged()* never run and unsaved models/views are
    silently lost. Call them explicitly here, then tear down.

    :rtype: None
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

    :returns:
    :rtype: None
    """
    menubar:tk.Menu = tk.Menu(self)
    
    self.filemenu = tk.Menu(menubar, name="file")
    self.filemenu.add_command(label="New...", command=self.doNew)
    self.filemenu.add_command(label="Open...", command=self.doOpen)
    self.recentMenu = tk.Menu(self.filemenu, name="recent")
    self.filemenu.add_cascade(label="Open Recent", menu=self.recentMenu)
    self._fillRecentMenu()
    self.filemenu.add_separator()
    # "Save view" is NOT added here: whichever SNGView's AppWindow currently
    # has focus adds/removes it itself (see SNGView.onWindowFocusIn/Out(),
    # utils.addToMenuBar()/removeFromMenuBar()), so the item is only ever
    # present -- and only ever targets the right view -- while some window
    # is actually focused.
    # TODO (Rob): "Save model", "Save view as...", "Save model as..." go here too.
    menubar.add_cascade(menu=self.filemenu, label="File")

    self.windowmenu = tk.Menu(menubar, name="window")  # macOS auto-fills this (window list, Move & Resize, ...)
    menubar.add_cascade(menu=self.windowmenu, label="Window")

    self.helpmenu = tk.Menu(menubar, name="help")  # macOS auto-fills this (search field, "Python Help", ...)
    menubar.add_cascade(menu=self.helpmenu, label="Help")
    self.helpmenu.add_command(label=f"{sn.NAME} User Guide", command=lambda: self.showHelp("user/index.html"))
    self.helpmenu.add_command(label=f"{sn.NAME} Developer Guide", command=lambda: self.showHelp("developer/index.html"))
    self.helpmenu.add_separator()
    self.helpmenu.add_command(label="Install Example Models", command=self.onInstallExamples)

    self.config(menu=menubar)
    return menubar

  def showHelp(self, page:str) -> None:
    """Show a page of the documentation in the web browser: the copy bundled
    in a packaged app, or else the project's built documentation.

    :param page: The page, relative to the documentation's top, eg: "user/index.html".
    :type page: str
    :rtype: None
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

    :rtype: None
    """
    applyEditAttrsBox(self, snPrefs, title="Semantic Nets Preferences", hideColumns=("type", "qualifiers", "note"))
    self._fillRecentMenu() # (in case "gui/recentFiles" changed)

  def doOpen(self, ): 
    'Respond to the "Open..." menu item.'
    filename = filedialog.askopenfilename(
                title=f"Open a view (.snv) file or the default view for a model (.snm) file.",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
  
  def doNew(self, ): 
    'Respond to the "New..." menu item.'
    filename = filedialog.asksaveasfilename(
                title=f"Specify a view (.snv) file (you will be asked for the corresponding model) or model (.snm) file to create a default view for.",
                defaultextension=".snv",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
  
  def openWindow(self, viewSpec:Model|str) -> tk.Toplevel|None:
    """Create and show a new Toplevel window hosted under the invisible root.

    :param name: A key to refer to this window by (e.g. for closing it later).
    :type name: str
    :param title: Window title. Defaults to name if not given.
    :type title: str
    :param viewSpec:
    :type viewSpec: Model | str
    :returns: The newly created Toplevel window.
    :rtype: tk.Toplevel
    """
    from sn.view.graphics.sngView import SNGView
    assert isinstance(viewSpec, (Model,SNGView,str,NoneType))
    
    def makeViewFromModel(model:Model) -> SNGView:
      url = fixURL(model.url, ".snv", replaceExt=True, mode='w')[0]
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
        ret = PRDb.readFile(url)
        assert isinstance(ret, SNGView)
      else:
        ret = SNGView(url, model=model, mode="w")
      return ret
    
    try:
      model:Model|None = None
      view:SNGView|None = None
      
      if isinstance(viewSpec, Model):
        view = makeViewFromModel(viewSpec)
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
            peekedType = SerializationStrategy.peekTypex(viewSpec, replaceExt=None)
            if issubclass(peekedType, SNGView): # it's a view -- if it's already open, we're done.
              if viewSpec in self.windows:
                view = cast(SNGView, self.windows[viewSpec].view)
              else:
                obj = PRDb.readFile(viewSpec)
                if not isinstance(obj, SNGView):
                  raise TypeError(f'Expected type Model in "{viewSpec}", but got type {type(obj)}.')
                view = obj
            elif issubclass(peekedType, Model): # it's a model -- read it, then find/create its view.
              modelOrView = Model(viewSpec)
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
              if modelURL is None:
                return None 
              obj = PRDb.readFile(modelURL, mode='r')
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
      if name in self.windows:
        self.windows[name].lift()
        return self.windows[name]
  
      self.defaultChildLocation = (self.defaultChildLocation[0] + 40, self.defaultChildLocation[1] + 40)
      self.windows[name] = view.window
      return view.window
    
    except Exception:
      logger.error(f'While opening window for viewSpec "{viewSpec}"')#, exc_info=True)
      try:
        print(traceback.format_exc(), file=sys.__stderr__)
        showExceptionDialog(self, title=f"Semantic Nets: Failed to open window for Model {viewSpec.url if isinstance(viewSpec, Model) else viewSpec}.")
      except Exception:
        logger.error('While displaying exception dialog', exc_info=True)
      return None


  def openViewOn(self, model:Model, viewURL:str) -> tk.Toplevel|None:
    '''
    Open a window on *model*: its view saved at *viewURL* if there is one
    there (see *openWindow()*), or else a new view of it that'll be saved
    there -- eg: a model with no file of its own (the system model, sn), or one
    read from a copy (the base rules).

    :param model: The model.
    :type model: Model
    :param viewURL: Where its view is (or will be) saved.
    :type viewURL: str
    :returns: The window.
    :rtype: tk.Toplevel | None
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

  RECENT_PREF = ".recentFiles"
  '''The preference listing the views opened most recently, most recent first
  (see *noteRecent()*). (Hidden from Settings: see *OPEN_WINDOWS_PREF*.)'''

  RECENT_KEPT = 50
  "How many recent views are remembered, whatever \"gui/recentFiles\" (how many are listed) is."

  def recentFiles(self) -> list[dict[str, str]]:
    '''
    :returns: The views opened most recently, most recent first: each
      {"view": its URL, "model": its model's URL}.
    :rtype: list[dict[str, str]]
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

    :param viewURL:
    :type viewURL: str
    :param modelURL:
    :type modelURL: str
    '''
    entries = [e for e in self.recentFiles() if e.get("view") != viewURL]
    self._setRecentFiles([{"view": viewURL, "model": modelURL}, *entries])

  def openRecent(self, entry:dict[str, str]) -> None:
    '''
    Open a recently opened view (File | Open Recent): its view, if it's been
    saved; else its model (with its default view). If neither can be found any
    more, say so, and take it off the list.

    :param entry: One of *recentFiles()*.
    :type entry: dict[str, str]
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
      menu.add_command(label=label, command=lambda e=e: self.openRecent(e))
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

    :rtype: None
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

  def reopenWindows(self) -> int:
    '''
    Reopen the windows recorded by *rememberOpenWindows()*, in the same size
    and position. A view that was never saved opens as its model's default
    view; one whose files have gone is skipped (with a message). The views
    open as they were last saved -- unsaved changes, and the undo history,
    are gone.

    :returns: The number of windows reopened.
    :rtype: int
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
    reopen the windows open when the app last quit (see *reopenWindows()*);
    and if there were none, ask for a file to open.

    :param files: Files named on the command line.
    :type files: list[str]
    :rtype: None
    '''
    files = [f for f in files if not f.startswith("-psn_")] # (a process serial number some macOS versions pass to an app)
    for f in files:
      self.openWindow(f)
    if files or getattr(self, "_openedDocuments", False) or self.reopenWindows() > 0:
      return
    if not snPrefs.get(self.EXAMPLES_PREF, False) and self.installExamples():
      return
    self.doOpen()

  EXAMPLES_PREF = ".examplesInstalled"
  "True once the example models have been installed (see *installExamples()*): it's only done once. (Hidden from Settings: see *OPEN_WINDOWS_PREF*.)"

  EXAMPLES_FOLDER = os.path.join("~", "Documents", f"{sn.NAME} Examples")
  "Where *installExamples()* puts the example models."

  def installExamples(self, replace:bool=False) -> bool:
    """Copy the example models that come with the app into *EXAMPLES_FOLDER*,
    and open their views: on the first launch (see *startUp()*), or when asked
    to (see *onInstallExamples()*).

    :param replace: Whether to replace copies already there. If not (as on
      the first launch), an existing folder is left as it is.
    :type replace: bool

    :returns: True iff any were opened.
    :rtype: bool
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

    :rtype: None
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
    users = sorted({url for db in list(PRDb.AllDBs.values()) if isinstance(db, Model) and db.url.startswith(prefix)
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

  def closeModel(self, model:Model) -> None:
    """The File menu's *Close model*: close every window on *model* (offering
    to save each changed view, as closing them by hand does), offer to save the
    model if it's changed, and forget it -- so opening it again reads the file
    afresh. If that was the last window, the app quits, as it does when the
    last window is closed by hand.

    A model that other loaded models build on (eg: one of their types isa one
    of its) can't be closed: they'd be left pointing at it. Nothing is changed
    then.

    :param model: The model.
    :type model: Model
    :rtype: None
    """
    users = sorted({url for kind, url in model.dependents() if kind == "model"})
    if users:
      messagebox.showerror(sn.NAME, f'"{os.path.basename(model.url)}" can\'t be closed while other models use it:\n\n  '
                           + "\n  ".join(users) + "\n\nModels stay in memory until you quit.")
      return
    for name, window in list(self.windows.items()):
      if window.view is not None and window.view.model is model:
        self._closeWindow(name, quitIfLast=False)
    sn.checkSaveModified(model, model.url, "model") # (now or never: once forgotten, quitting won't ask)
    try:
      model.unload()
    except RuntimeError: # (eg: a view of it that isn't in a window: it stays in memory, as before)
      logger.warning(f'Couldn\'t forget model "{model.url}".', exc_info=True)
    if not self.windows:
      self.rememberOpenWindows() # (none: it was closed on purpose, so it isn't reopened next time)
      self.quit()

  def closeAllWindows(self) -> None:
    """Close every hosted window via *_closeWindow()*, so each view gets
    exactly the same save check (and clean-up) on quitting as it would if
    the user closed its window individually.

    :rtype: None
    """
    for name in list(self.windows):
      self._closeWindow(name, quitIfLast=False)

  def _closeWindowOf(self, window: "AppWindow") -> None:
    """Close *window* (its close button: see *AppWindow*), whatever it's
    filed under in *windows* -- which needn't be the URL it was made with
    (eg: a copied file's view is filed under where it is now, or a view saved
    as another file). One that isn't filed at all is still closed.

    :param window: The window.
    :type window: AppWindow
    :rtype: None
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
    :type name: str
    :param quitIfLast: Quit the application if this was the last window.
      False when the caller is already quitting (see *closeAllWindows()*).
    :type quitIfLast: bool
    :param askToSave: Whether to offer to save the window's view if it's
      changed. False when the user has already agreed to lose the changes
      (see *onInstallExamples()*).
    :type askToSave: bool
    :rtype: None
    """
    if quitIfLast and list(self.windows) == [name]: # closing the last window quits: remember it for next time
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

    if quitIfLast and not self.windows:
      self.quit()  # or: leave the (invisible) root running headless, your choice

  def quit(self) -> None:
    """Tear down the entire application, including the hidden root.

    :rtype: None
    """
    self.destroy()

  def run(self) -> None:
    """Start the Tk event loop.

    :rtype: None
    """
    self.mainloop()


def _filePath(url:str) -> str:
  '''
  :param url: A file's URL (eg: "file:///Users/me/family.snv").
  :type url: str
  :returns: Its path.
  :rtype: str
  '''
  from urllib.parse import urlparse, unquote
  parsed = urlparse(url)
  return unquote(parsed.path) if parsed.scheme in ("file", "") else url

def _fileName(url:str) -> str:
  '''
  :param url: A file's URL.
  :type url: str
  :returns: Its name (eg: "family.snv").
  :rtype: str
  '''
  return os.path.basename(_filePath(url)) or url

class AppWindow(tk.Toplevel):
  '''
  A top-level SN app window that also acts as the holder of the SNContext
  Model controller.
  '''

  def __init__(self, tkdottk:tk.Tk, viewURL:str, geometry:str="300x400+20+20", **kwargs):
    '''
    :param tkdottk:
    :type tkdottk: tk.Tk
    :param viewURL:
    :type viewURL: str
    :param geometry:
    :type geometry: str
    :param kwargs:
    :type kwargs:
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

    self.option_add('*tearOff', tk.FALSE)
    # self.tkTop.protocol("WM_DELETE_WINDOW", self.onClosing)

    # This window's terminal is the single routing target for BOTH the
    # SNTerminalWidget itself and the graphics editor (SNGFrame) — bind
    # focus on every widget in the window (not just the terminal) so that
    # clicking into the graphics editor also makes its output land here.
    # terminal = self.appPanedWidget.textDisplayFrame
    # self._bindFocusRouting(self, terminal)

    # Also register this window/terminal pair directly, independent of Tk
    # focus — lets TerminalRegistry's active-window fallback (wm stackorder)
    # find this terminal even for interactions (e.g. SNCanvas's right-click
    # popup menu) that never move Tk's logical keyboard focus at all.
    #self._root().terminalRegistry.registerWindow(self, terminal)

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
    :rtype: None
    """
    widget.bind("<FocusIn>", self._onWindowFocusIn, add="+")
    widget.bind("<FocusOut>", self._onWindowFocusOut, add="+")
    if widget is self: # (the window made active again -- eg: after a dialog, or another application -- needn't give any widget a FocusIn)
      widget.bind("<Activate>", self._onWindowFocusIn, add="+")
    for child in widget.winfo_children():
      self._bindFocusTracking(child)

  def _onWindowFocusIn(self, event=None) -> None:
    """Some widget inside this window just gained focus -- let this
    window's *SNGView* (if any) know it's now the focused one.

    :param event: The Tk event.
    :type event:
    :rtype: None
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
    :type event:
    :rtype: None
    """
    self.after_idle(self._checkStillActive)

  def _checkStillActive(self) -> None:
    """Let this window's *SNGView* (if any) know focus has genuinely moved
    outside this window (as opposed to just moving between two of its own
    descendant widgets -- see *_onWindowFocusOut()*).

    :rtype: None
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

  def _bindFocusRouting(self, widget: tk.Misc, terminal: "SNTerminalWidget") -> None: #type: ignore[name-defined]
    """Recursively bind <FocusIn>/<FocusOut> on this widget and all its
    descendants so that focusing ANY widget in the window (terminal or
    graphics editor) sets this window's terminal as the default stdio/input()
    routing target.

    :param widget: The widget (and its children, recursively) to bind.
    :type widget: tk.Widget
    :param terminal: This window's terminal — the routing target.
    :type terminal: SNTerminalWidget
    :rtype: None
    """
    e:tk.Event
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
    :type parent: AppWindow
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

    :param kwargs:
    :type kwargs:
    """
    assert isinstance(parent, AppWindow)
    # fix up kwargs to contain the necessary defaults and create the PanedWindow (super).
    if "orient" not in kwargs: kwargs["orient"] = tk.VERTICAL
    if "showhandle" not in kwargs: kwargs["showhandle"] = False
    if "handlesize" not in kwargs: kwargs["handlesize"] = 8
    if "sashwidth" not in kwargs: kwargs["sashwidth"] = 6
    if "sashrelief" not in kwargs: kwargs["sashrelief"] = "ridge"  # "groove"#"sunken"#
    #if "bd" not in kwargs: kwargs["bd"] = 20
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
    # self.canvasFrame.terminal = self.canvasFrame.terminal

    self.pack(fill=tk.BOTH, expand=True)


class SNGViewFrame(tk.Frame):

  def __init__(self, parent:AppPanedWidget, **kwargs):
    '''
    :param parent: The master Widget.
    :type parent: AppPanedWidget
    :param kwargs: Passed to *Canvas*.
    :type kwargs:
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
  line, or else as *Application.startUp()* says."""
  app = Application()
  app.after(1000, app.startUp, sys.argv[1:])
  app.run()

if __name__ == "__main__":
  main()
