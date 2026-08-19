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
#from sn.view.textUserInterface import SNTerminalWidget # circular import

logger:sn.SNLogger = sn.getLogger(__name__)

# =============================================================================
# Terminal routing: resolves, for any stdout/stderr write, log record, or
# input() call, which SNTerminalWidget it should go to. A thread that has been
# explicitly bound (e.g. a window's command worker, or a background task
# launched by the graphics editor) always routes to its bound terminal,
# regardless of what has focus later. An unbound main-thread call (interactive
# typing, or a stray print()) routes to whichever window currently has focus.
# =============================================================================


class TerminalRegistry:
  """Routes stdio/logging/input() output to the correct SNTerminalWidget.

  :rtype: None
  """

  def __init__(self) -> None:
    self._byThread: dict[int, "SNTerminalWidget"] = {}
    self._focusedMainThreadTarget: Optional["SNTerminalWidget"] = None
    self._lock = threading.Lock()

  def bindThreadToTerminal(self, terminal: "SNTerminalWidget", thread: Optional[threading.Thread]=None) -> None:
    """Associate a thread with a specific terminal for the lifetime of its work.
    Call this from the code that STARTS the thread (e.g. a window's command
    dispatch, or the graphics editor launching a background computation).

    :param terminal: The terminal that output from this thread should route to.
    :type terminal: SNTerminalWidget
    :param thread: The thread to bind. Defaults to the current thread.
    :type thread: Optional[threading.Thread]
    :rtype: None
    """
    targetThread = thread or threading.current_thread()
    with self._lock:
      self._byThread[id(targetThread)] = terminal

  def unbindThread(self, thread: Optional[threading.Thread]=None) -> None:
    """Remove a thread's routing entry once its work is done.

    :param thread: The thread to unbind. Defaults to the current thread.
    :type thread: Optional[threading.Thread]
    :rtype: None
    """
    targetThread = thread or threading.current_thread()
    with self._lock:
      self._byThread.pop(id(targetThread), None)

  def resolveTerminal(self) -> Optional["SNTerminalWidget"]:
    """Determine which terminal the current call should route to.

    :returns: The bound terminal for this thread, or the focused terminal for
      the main thread if unbound, or None if nothing resolves.
    :rtype: Optional[SNTerminalWidget]
    """
    threadId = id(threading.current_thread())
    with self._lock:
      bound = self._byThread.get(threadId)
    if bound is not None:
      return bound
    if threading.current_thread() is threading.main_thread():
      return self._focusedMainThreadTarget
    return None

  def onFocusIn(self, terminal: "SNTerminalWidget") -> None:
    """Set the default routing target for interactive (main-thread) actions.

    :param terminal: The terminal belonging to the window that gained focus.
    :type terminal: SNTerminalWidget
    :rtype: None
    """
    self._focusedMainThreadTarget = terminal

  def onFocusOut(self, terminal: "SNTerminalWidget") -> None:
    """Clear the default target if this terminal's window is the one losing focus.

    :param terminal: The terminal belonging to the window that lost focus.
    :type terminal: SNTerminalWidget
    :rtype: None
    """
    if self._focusedMainThreadTarget is terminal:
      self._focusedMainThreadTarget = None


class LineBufferedRoutingStream(io.TextIOBase):
  """A file-like object that buffers writes by line and routes each complete
  line to whichever terminal the TerminalRegistry resolves to at write time.

  :param registry: The shared registry used to resolve the target terminal.
  :type registry: TerminalRegistry
  :param style: Style name to use when printing (e.g. "stdout", "stderr").
  :type style: Optional[str]
  """

  def __init__(self, registry: TerminalRegistry, style: Optional[str]=None) -> None:
    self.registry = registry
    self.style = style
    self._buffer = ""

  def write(self, text: str) -> int:
    """Buffer incoming text and route complete lines to the resolved terminal.

    :param text: Text written by print() or similar.
    :type text: str
    :returns: Number of characters accepted.
    :rtype: int
    """
    self._buffer += text
    while "\n" in self._buffer:
      line, self._buffer = self._buffer.split("\n", 1)
      self._emit(line)
    return len(text)

  def flush(self) -> None:
    """Emit any partial (no trailing newline) buffered text as a final line.

    :rtype: None
    """
    if self._buffer:
      self._emit(self._buffer)
      self._buffer = ""

  def _emit(self, line: str) -> None:
    """Resolve the current target terminal and print the line to it.
    Silently dropped if no terminal resolves (e.g. unbound background thread
    with no window focused at all).

    :param line: The line to emit.
    :type line: str
    :rtype: None
    """
    terminal = self.registry.resolveTerminal()
    if terminal is not None:
      terminal.printLine(line, style=self.style)


class TerminalLogHandler(logging.Handler):
  """A logging.Handler that routes formatted records to whichever terminal the
  TerminalRegistry resolves to at emit time.

  :param registry: The shared registry used to resolve the target terminal.
  :type registry: TerminalRegistry
  """

  def __init__(self, registry: TerminalRegistry) -> None:
    super().__init__()
    self.registry = registry

  def emit(self, record: logging.LogRecord) -> None:
    """Format and route a log record to the resolved terminal, styled by level.

    :param record: The log record to emit.
    :type record: logging.LogRecord
    :rtype: None
    """
    terminal = self.registry.resolveTerminal()
    if terminal is None:
      return
    message = self.format(record)
    style = "stderr" if record.levelno >= logging.WARNING else "stdout"
    terminal.printLine(message, style=style)


def installGlobalIORouting(registry: TerminalRegistry) -> None:
  """Install stdout/stderr/input() redirection and logging routing ONCE, for
  the lifetime of the application. Call this exactly once at startup.

  :param registry: The shared registry that resolves which terminal each call routes to.
  :type registry: TerminalRegistry
  :rtype: None
  """
  sys.stdout = LineBufferedRoutingStream(registry, style="stdout")
  sys.stderr = LineBufferedRoutingStream(registry, style="stderr")

  def routedInput(prompt: object="") -> str:
    """Global input() replacement, routed through the resolved terminal.

    :param prompt: The prompt to display.
    :type prompt: object
    :returns: The line typed by the user.
    :rtype: str
    :raises RuntimeError: If no terminal can be resolved for this call.
    """
    terminal = registry.resolveTerminal()
    if terminal is None:
      raise RuntimeError("input() called with no bound thread and no focused terminal")
    return terminal.input(str(prompt))

  builtins.input = routedInput

  root = logging.getLogger()

  # util.setupLogger() (called at "sn" package import time) attaches a
  # DynamicStderrHandler that always writes to whatever sys.stderr currently
  # is. Now that sys.stderr has just been redirected above, that handler
  # would ALSO deliver every log record to this terminal — on top of the
  # TerminalLogHandler we're about to add below — producing a duplicate line
  # per record. Evict any such plain StreamHandler (but not FileHandler,
  # which IS a StreamHandler subclass and must keep writing to the log file)
  # so TerminalLogHandler becomes the single route from logging into the
  # terminal.
  for h in list(root.handlers):
    if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
      root.removeHandler(h)

  handler = TerminalLogHandler(registry)
  handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
  root.addHandler(handler)


# Single, app-wide registry. Created here so both AppWindow/AppPanedWidget and
# SNTerminalWidget (once patched — see note below) can reach it via the
# Application instance (self._root().terminalRegistry) or, more simply, this
# module-level reference.
terminalRegistry = TerminalRegistry()

# =============================================================================


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
    self.textDisplayFrame = SNTerminalWidget(None, self, registry=terminalRegistry)
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
