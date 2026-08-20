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
Created on Aug 18, 2026

@author: robkremer
'''
from __future__ import annotations
import sys
import io
import builtins
import threading
import logging
import sn
import tkinter as tk
from typing import Optional, Callable
from tkinter import ttk
from sn import snPrefs
from util.attribute import Attribute, VAR_DEFAULTED
from util.utils import expandRect
from util.terminal import terminalRegistry, installGlobalIORouting
#from sn.view.textUserInterface import SNTerminalWidget # circular import

logger:sn.SNLogger = sn.getLogger(__name__)

class Application(tk.Tk):
  """The invisible root Tk window and manages one or more Toplevel windows.

  :param appName: Name used for the hidden root window's title (mostly cosmetic,
    since it's never shown).
  :type appName: str
  """

  def __init__(self, appName: str="app") -> None:
    super().__init__()
    self.withdraw()  # hide before it can ever flash visible
    self.title(appName)
    self.defaultChildLocation:tuple[int, int] = (20, 60)

    self.windows: dict[str, tk.Toplevel] = {}
    self.terminalRegistry = terminalRegistry  # shared across all windows

    installGlobalIORouting(self.terminalRegistry)  # install exactly once, here

    # If every hosted window is closed, there's nothing left to interact with —
    # decide here whether that should end the app.
    self.protocol("WM_DELETE_WINDOW", self._noOp)  # root itself is never closed by the user

  def _noOp(self) -> None:
    """Root window has no close button the user can reach, but guard anyway.

    :rtype: None
    """
    pass

  def openWindow(self, name: str, title: str="") -> tk.Toplevel:
    """Create and show a new Toplevel window hosted under the invisible root.

    :param name: A key to refer to this window by (e.g. for closing it later).
    :type name: str
    :param title: Window title. Defaults to name if not given.
    :type title: str
    :returns: The newly created Toplevel window.
    :rtype: tk.Toplevel
    """
    if name in self.windows:
      self.windows[name].lift()
      return self.windows[name]

    window:AppWindow = AppWindow(self, name, title, geometry=f'300x400+{self.defaultChildLocation[0]}+{self.defaultChildLocation[1]}')
    self.defaultChildLocation = (self.defaultChildLocation[0] + 40, self.defaultChildLocation[1] + 40)
    self.windows[name] = window
    return window

  def _closeWindow(self, name: str) -> None:
    """Close a specific hosted window and check whether the app should exit.

    :param name: The window's key, as passed to openWindow.
    :type name: str
    :rtype: None
    """
    window = self.windows.pop(name, None)
    if window is not None:
      self.terminalRegistry.onFocusOut(window.appPanedWidget.textDisplayFrame)
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

  def __init__(self, tkdottk:tk.Tk, name:str, title:str="", geometry:str="300x400+20+20", **kwargs):
    super().__init__(tkdottk, **kwargs)
    self.geometry(geometry)
    self.title(title or name)
    self.protocol("WM_DELETE_WINDOW", lambda name=name: self._root()._closeWindow(name))
    self.appPanedWidget = AppPanedWidget(self)
    self.appPanedWidget.pack(fill=tk.BOTH, side=tk.RIGHT, expand=True, padx=0, pady=0)

    self.option_add('*tearOff', tk.FALSE)
    # self.tkTop.protocol("WM_DELETE_WINDOW", self.onClosing)

    # This window's terminal is the single routing target for BOTH the
    # SNTerminalWidget itself and the graphics editor (SNGFrame) — bind
    # focus on every widget in the window (not just the terminal) so that
    # clicking into the graphics editor also makes its output land here.
    terminal = self.appPanedWidget.textDisplayFrame
    self._bindFocusRouting(self, terminal)

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

  def __init__(self, parent,
               **kwargs):
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
    from sn.view.textUserInterface import SNTerminalWidget
    # fix up kwargs to contain the necessary defaults and create the PanedWindow (super).
    if "orient" not in kwargs: kwargs["orient"] = tk.VERTICAL
    if "showhandle" not in kwargs: kwargs["showhandle"] = False
    if "sashwidth" not in kwargs: kwargs["sashwidth"] = 6
    if "sashrelief" not in kwargs: kwargs["sashrelief"] = "ridge"  # "groove"#"sunken"#
    if "bd" not in kwargs: kwargs["bd"] = 4
    if "bg" not in kwargs: kwargs["bg"] = "lightgrey"
    if "borderwidth" not in kwargs: kwargs["borderwidth"] = 0

    # super constructor
    super().__init__(parent, **kwargs)

    # set up the textDisplayFrame (contains the *loggingWidget* , *commandEntryWidget* and *promptLabel*
    # No registry passed explicitly — it defaults to the same module-level
    # singleton this file already imports for its own use (installGlobalIORouting,
    # onFocusIn/onFocusOut below).
    self.textDisplayFrame = SNTerminalWidget(None, self)
    self.textDisplayFrame.pack(fill=tk.NONE, side=tk.BOTTOM, expand=False)
    stretch = 'always'  # if fixedAppFrame else 'never'
    sticky = 'news'  # if fixedAppFrame else 'new'
    self.add(self.textDisplayFrame, stretch=stretch, sticky=sticky)
    self.paneconfigure(self.textDisplayFrame, stretch=stretch)

    self.appFrame = SNGFrame(self)
    self.appFrame.pack(fill=tk.BOTH,  # if self.fixedAppFrame else tk.BOTH,
                        side=tk.TOP,
                        expand=False)  # if self.fixedAppFrame else True)

    stretch = 'never'  # if self.fixedAppFrame else 'always'
    sticky = 'new'  # if self.fixedAppFrame else 'news'
    self.add(self.appFrame, before=self.textDisplayFrame, stretch=stretch, sticky=sticky)  # 'always', 'first', 'last', 'middle', and 'never'.
    self.paneconfigure(self.appFrame, stretch=stretch)

    # Give the graphics editor a direct reference to this window's terminal
    # and the shared registry, so it can bind its own background threads
    # (runBackgroundWork below) without having to walk back up through
    # winfo_toplevel()/_root() to find them.
    self.appFrame.terminal = self.textDisplayFrame
    self.appFrame.registry = terminalRegistry

    self.pack(fill=tk.BOTH, expand=True)


class SNGFrame(tk.Frame):

  def __init__(self, parent, **kwargs):
    '''
    :param parent: The master Widget.
    :param kwargs: Passed to *Canvas*.
    '''
    # self.scrollRegion:list = [0,0,1000,1000]
    tk.Frame.__init__(self, parent)

    self.hScroll = ttk.Scrollbar(self, orient=tk.HORIZONTAL)
    self.vScroll = ttk.Scrollbar(self, orient=tk.VERTICAL)
    kwargs["yscrollcommand"] = self.vScroll.set
    kwargs["xscrollcommand"] = self.hScroll.set
    if "bg" not in kwargs: kwargs["bg"] = snPrefs.get('view_backgroundColor', storeDefault="grey95", storeType="color")

    # Call the tk.Canvas and PRDb constructors
    self.canvas = tk.Canvas(self, **kwargs)

    self.hScroll['command'] = self.canvas.xview
    self.vScroll['command'] = self.canvas.yview

    self.canvas.grid(column=0, row=0, sticky=tk.N + tk.W + tk.E + tk.S)
    self.hScroll.grid(column=0, row=1, sticky=tk.W + tk.E)
    self.vScroll.grid(column=1, row=0, sticky=tk.N + tk.S)
    self.grid_columnconfigure(0, weight=1)
    self.grid_rowconfigure(0, weight=1)

    # test code **********************
    self.canvas.create_rectangle(500, 500, 700, 650, outline="black", fill="lightblue", width=2)
    self.canvas.create_rectangle(50, 500, 150, 700, outline="black", fill="purple", width=2)
    self.resetScrollRegion()
    print("Hello world!")
    #**********************

  def resetScrollRegion(self):
    self.canvas.configure({"scrollregion":expandRect(self.canvas.bbox("all"), 10)})

  def runBackgroundWork(self, fn: Callable[[], None]) -> None:
    """Launch background work (e.g. a long model computation triggered by the
    graphics editor) bound to THIS window's terminal, so its stdout/stderr/
    logging/input() output lands there regardless of what has focus by the
    time the work actually produces output.

    :param fn: The work to run.
    :type fn: Callable[[], None]
    :rtype: None
    """
    terminal = self.terminal  # set by AppPanedWidget after construction
    registry = self.registry

    def wrapped() -> None:
      registry.bindThreadToTerminal(terminal)
      try:
        fn()
      finally:
        registry.unbindThread()

    threading.Thread(target=wrapped, daemon=True).start()


if __name__ == "__main__":
  app = Application("MyApp")
  win1 = app.openWindow("main", title="Main Window")
  win2 = app.openWindow("settings", title="Settings")
  app.run()
