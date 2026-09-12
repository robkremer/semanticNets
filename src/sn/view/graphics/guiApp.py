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
#from sn.controller.modelInterface import ModelContext
import traceback
import util
from util.persistence.serialize import SerializationStrategy
from util.attributeEditor import applyEditAttrsBox
#from sn.view.graphics.snCanvas import SNGContext
import sys
import io
import builtins
import threading
import logging
import sn
import tkinter as tk
import tkinter.filedialog as filedialog
from typing import Optional, Callable, cast, Any
from types import NoneType
from tkinter import ttk
from sn import snPrefs
from util.attribute import Attribute, VAR_DEFAULTED, isValidType
from util.utils import expandRect, showExceptionDialog, fixURL, urlExists,\
  isValidURL
from util.terminal import terminalRegistry, installGlobalIORouting,\
  TerminalWidget, TerminalRegistry
from sn.view.graphics.utils import getSubMenu
from sn.model.model import Model
# from sn.view.graphics.snCanvas import SNGView
#from sn.view.textUserInterface import SNTerminalWidget # circular import

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

  def _installMenubar(self) -> tk.Menu:
    """Builds the app menu bar.

    Creates the menu bar. Tk *will*
    keep auto-populating a cascade we create under one of its reserved
    names ("apple", "window", "help"), so recreate "window" and "help" here
    to get that native content back. 

    Called once, from __init__, alongside _installSettingsMenu().

    :rtype: None
    """
    menubar:tk.Menu = tk.Menu(self)
    
    self.filemenu = tk.Menu(menubar, name="file")
    self.filemenu.add_command(label="New...", command=self.doNew)
    self.filemenu.add_command(label="Open...", command=self.doOpen)
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

    self.config(menu=menubar)
    return menubar

  def openSettings(self) -> None:
    """Show the app-wide Settings dialog, editing *sn.snPrefs* in place.

    Builds its form generically from whatever's currently in snPrefs: each
    key becomes a labelled row, rendered as a dropdown if the Attribute's
    type is a "choices[...]" constraint (see util.attribute), a checkbox if
    its current value is a bool, otherwise a plain text entry. Save writes
    each edited value back via snPrefs[key] = ... (which validates against
    the Attribute's type/restriction) and persists immediately via
    snPrefs.save(), rather than relying solely on the atexit hook.

    :rtype: None
    """
    applyEditAttrsBox(self, snPrefs, title="Semantic Nets Preferences")

  def doOpen(self, ): # respond to the "Open..." menu item.
    filename = filedialog.askopenfilename(
                title=f"Open a view (.snv) file or the default view for a model (.snm) file.",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
  
  def doNew(self, ): # respond to the "New..." menu item.
    filename = filedialog.asksaveasfilename(
                title=f"Specify a view (.snv) file (you will be asked for the corresponding model) or model (.snm) file to create a default view for.",
                defaultextension=".snv",
                filetypes=[("View files", "*.snv *.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
    if filename:
      self.openWindow(filename)
      # if filename.endswith(".snm"): # a model
      #   model = SerializationStrategy.readx(filename, replaceExt=None)
      #   if isinstance(model, Model): # verified to be a model.
      #     viewURL = fixURL(model.utl, ".snv", replaceExt=True, mode='w')[0]
      #     SNGView(viewURL, model=model, mode='w')
      #     return
      #   raise UnexpectedObjectInFile(f'File "{filename}" contains an object of type {model.__class__.__name__}. Expected a Model or a SNGView object')
      # modelURL = filedialog.askopenfilename(
      #   title=f"Select a Model file for the new view {filename}",
      #   filetypes=[("Model files", "*.snm"), ("xml files", "*.xml"), ("All Files", "*.*")])
      # if modelURL is None:
      #   return None 
      # model = SerializationStrategy.readx(modelURL, replaceExt=None)
      # view = SNGView(viewSpec, model=model)
  
  def openWindow(self, viewSpec:Model|str) -> tk.Toplevel|None:
    """Create and show a new Toplevel window hosted under the invisible root.

    :param name: A key to refer to this window by (e.g. for closing it later).
    :type name: str
    :param title: Window title. Defaults to name if not given.
    :type title: str
    :returns: The newly created Toplevel window.
    :rtype: tk.Toplevel
    """
    from util.persistence.pRef import PRDb
    from sn.model.model import Model
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
        ret = SerializationStrategy.readx(url, replaceExt=None)
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
                modelOrView = SerializationStrategy.readx(viewSpec, replaceExt=None)
                assert isinstance(modelOrView, SNGView)
                view = modelOrView
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
              model = SerializationStrategy.readx(modelURL, replaceExt=None, mode='r')
              view = SNGView(viewSpec, model=model)
            else:
              splt = viewSpec.rsplit(".", 1)
              ext = "" if len(splt)==1 else splt[1] 
              raise NameError(f'Don\'t know what to do with a file ending in ".{ext}"')
        else:
          raise ReferenceError(f'Invalid URL: {viewSpec}')
      
      name = view.url    
      if name in self.windows:
        self.windows[name].lift()
        return self.windows[name]
  
      #TODO: passing viewSpec as just None is just a temporary thing. 
#      window:AppWindow = AppWindow(self, model, geometry=f'{snPrefs.get("gui/WindowSize", storeDefault="800x600", storeType=str)}+{self.defaultChildLocation[0]}+{self.defaultChildLocation[1]}')
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


  def _closeWindow(self, name: str) -> None:
    """Close a specific hosted window and check whether the app should exit.

    :param name: The window's key, as passed to openWindow.
    :type name: str
    :rtype: None
    """
    window = self.windows.pop(name, None)
    if window is not None:
      # If this window's view is currently the one advertising "Save view"
      # in the File menu, make sure it's withdrawn -- closing a window isn't
      # guaranteed to fire a Tk <FocusOut> on its widgets first (unlike
      # AppWindow._onWindowFocusOut()/_checkStillActive(), which handles the
      # ordinary defocus-without-closing case).
      if window.view is not None:
        window.view.onWindowFocusOut()
      self.terminalRegistry.onFocusOut(window.appPanedWidget.textDisplayFrame)
      self.terminalRegistry.unregisterWindow(window)
      window.destroy()

    if not self.windows:
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


class AppWindow(tk.Toplevel):
  '''
  A top-level SN app window that also acts as the holder of the SNContext
  Model controller.
  '''

  def __init__(self, tkdottk:tk.Tk, viewURL:str, geometry:str="300x400+20+20", **kwargs):
    from sn.view.graphics.sngView import SNGContext
    # establish we have model and a context
    # assert isinstance(model, Model)
    # self.model:Model = model
    # self.context:SNGContext = SNGContext(model)
        
    # initialize the window
    super().__init__(tkdottk, **kwargs)
    self.geometry(geometry)
    name = viewURL
    self.title(name)
    self.protocol("WM_DELETE_WINDOW", lambda name=name: self._root()._closeWindow(name))

    self.view: "SNGView|None" = None
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

  def _bindFocusTracking(self, widget: tk.Widget) -> None:
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
    for child in widget.winfo_children():
      self._bindFocusTracking(child)

  def _onWindowFocusIn(self, event=None) -> None:
    """Some widget inside this window just gained focus -- let this
    window's *SNGView* (if any) know it's now the focused one.

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

    :rtype: None
    """
    self.after_idle(self._checkStillActive)

  def _checkStillActive(self) -> None:
    """Let this window's *SNGView* (if any) know focus has genuinely moved
    outside this window (as opposed to just moving between two of its own
    descendant widgets -- see *_onWindowFocusOut()*).

    :rtype: None
    """
    app = self._root()
    current = app.focus_get()
    stillActive = current is not None and current.winfo_toplevel() is self
    if not stillActive and self.view is not None:
      self.view.onWindowFocusOut()

  def _bindFocusRouting(self, widget: tk.Widget, terminal: "SNTerminalWidget") -> None:
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
    widget.bind("<FocusIn>", lambda e, t=terminal: self._root().terminalRegistry.onFocusIn(t), add="+")
    widget.bind("<FocusOut>", lambda e, t=terminal: self._root().terminalRegistry.onFocusOut(t), add="+")
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
    from sn.view.textUserInterface import SNTerminalWidget
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
    self.canvasFrame.terminal = self.textDisplayFrame
    self.canvasFrame.registry = terminalRegistry

    self.pack(fill=tk.BOTH, expand=True)

  # @property
  # def model(self) -> Model:
  #   return cast(AppWindow, self.master).model
  #
  # @property
  # def context(self) -> ModelContext:
  #   return cast(AppWindow, self.master).context
    

class SNGViewFrame(tk.Frame):

  def __init__(self, parent:AppPanedWidget, **kwargs):
    '''
    :param parent: The master Widget.
    :param kwargs: Passed to *Canvas*.
    '''
    from sn.view.graphics.sngView import SNGView
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
    
#    self.view = SNGView(None, self.canvas, self.model)

    # test code **********************
    # self.canvas.create_rectangle(500, 500, 700, 650, outline="black", fill="lightblue", width=2)
    # self.canvas.create_rectangle(50, 500, 150, 700, outline="black", fill="purple", width=2)
    # self.resetScrollRegion()
    # **********************
    
    self.terminal:TerminalWidget
    self.registry:TerminalRegistry

  # @property
  # def model(self) -> Model:
  #   ret = cast(AppPanedWidget, self.master).model
  #   assert isinstance(ret, Model)
  #   return ret
  #
  # @property
  # def context(self) -> ModelContext:
  #   return cast(AppPanedWidget, self.master).context
    
  # def resetScrollRegion(self):
  #   self.canvas.configure({"scrollregion":expandRect(self.canvas.bbox("all"), 10)})
  #
  # def runBackgroundWork(self, fn: Callable[[], None]) -> None:
  #   """Launch background work (e.g. a long model computation triggered by the
  #   graphics editor) bound to THIS window's terminal, so its stdout/stderr/
  #   logging/input() output lands there regardless of what has focus by the
  #   time the work actually produces output.
  #
  #   :param fn: The work to run.
  #   :type fn: Callable[[], None]
  #   :rtype: None
  #   """
  #   terminal = self.terminal  # set by AppPanedWidget after construction
  #   registry = self.registry
  #
  #   def wrapped() -> None:
  #     registry.bindThreadToTerminal(terminal)
  #     try:
  #       fn()
  #     finally:
  #       registry.unbindThread()
  #
  #   threading.Thread(target=wrapped, daemon=True).start()


if __name__ == "__main__":
  app = Application()
  # #win1 = app.openWindow("temp1.snv")
  # win2 = app.openWindow("temp2.snm")
  # app.run()
  # app.after(1000, app.openWindow, Model("temp1"))
  app.after(1000, app.openWindow, "temp2.snm")
  app.run()
