'''
The layout panel: a pane at the right of a view's window (beside the canvas;
its divider can be dragged) for trying layouts out without going through the
menus. Shown and hidden with "View | Layout panel" (see
*SNGView.showLayoutPanel()*). Its top has

  - a switch between the three kinds of layout (see *layout.CATEGORIES*):
    "arrange now" (static), "keep arranged" (dynamic) and "animate";
  - for the first two, a list of the layouts of that kind (the one keeping the
    view arranged is ticked); and
  - a bar of buttons for what's shown, which never scrolls away: for the first
    two, **Revert** (back to the values the layout was last used with) and
    **Arrange** (arrange the view once, as one undoable command) or **Use**
    (make it the view's dynamic layout); for "animate", the animation layout's
    start/stop button and what it's doing.

Below that is a page for the chosen layout: its parameters (the form its
dialog shows: see *layoutDialog.LayoutForm*) -- or, for "animate", the
animation layout's settings (see *animationControls*), which take effect at
once. Edits not yet used are kept while other pages are shown.

The page is made afresh each time it's chosen, so its lists of relation types
are the model's as they are then.

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
import tkinter as tk
from tkinter import ttk, font as tkfont
from typing import Any, TYPE_CHECKING
from sn.view.graphics.layout import STATIC, DYNAMIC, ANIMATED, LAYOUTS, LayoutHeuristic, layoutsFor
from sn.view.graphics.layoutDialog import LayoutForm
from sn.view.graphics.animationControls import AnimationControls, TIPS, statusText
from util.tooltip import CreateToolTip
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

PAGES:tuple[tuple[str, str], ...] = ((STATIC, "Arrange now"), (DYNAMIC, "Keep arranged"), (ANIMATED, "Animate"))
"The kinds of layout the panel's switch chooses between, and what it calls them."

HINTS:dict[str, str] = {
  STATIC: "Arranges the view once, as one undoable command.",
  DYNAMIC: "Keeps the view arranged as it changes (one layout at a time).",
}
"Said under a layout's name on its page."

TIPS_LAYOUT:dict[str, str] = {
  STATIC: "Arrange the view with this layout, once. It's one command: undo puts everything back.",
  DYNAMIC: "Make this the layout that keeps the view arranged as it changes.",
  "revert": "Put back the settings this layout was last used with in this view (or its defaults).",
}
"Tooltips for the bar's buttons, for a layout."

SCROLL_TAG = "LayoutPanelScroll"
"The bind tag that scrolls the page with the mouse wheel, given to everything on it (see *LayoutPanel._scrollable()*)."

class LayoutPanel(ttk.Frame):
  '''
  The layout panel for a view: see the module doc.
  '''
  WIDTH = 360
  "Its width (pixels) when it's first shown."
  MIN_WIDTH = 260
  "The narrowest it can be dragged."
  POLL_MS = 250
  "How often (ms) it shows the animation layout's state (and any settings changed elsewhere, eg: the menu)."

  def __init__(self, master:tk.Misc, view:SNGView):
    '''
    :param master: The widget it's in: the split beside the view's canvas.
    :type master: tk.Misc
    :param view: The view whose layouts it's for.
    :type view: SNGView
    '''
    super().__init__(master, padding=(8, 6, 4, 4))
    self.view = view
    self.width = self.WIDTH
    "Its width: as it was last shown (see *SNGView.showLayoutPanel()*)."
    self._polling = False
    self.category = tk.StringVar(self, value=ANIMATED)
    "The kind of layout shown (of *layout.CATEGORIES*)."
    self.chosen:dict[str, str] = {}
    "The layout chosen for each kind of layout, by name: what its list shows when the kind's switched to."
    self.drafts:dict[tuple[str, str], dict[str, Any]] = {}
    "A page's values not yet used, by (kind, layout name): kept while other pages are shown."
    self.form:LayoutForm|None = None
    self.animation:AnimationControls|None = None
    self._dynamicName = ""
    self._page:tuple[str, str|None] = (ANIMATED, None)
    "The kind of layout and the layout the page is for (see *_build()*)."
    tip = lambda widgets, text: [CreateToolTip(w, text, wrapLength=300) for w in widgets]

    switch = ttk.Frame(self)
    switch.pack(side=tk.TOP, fill=tk.X)
    for i, (category, text) in enumerate(PAGES):
      b = ttk.Radiobutton(switch, text=text, value=category, variable=self.category, style="Toolbutton",
                          command=self._switched)
      b.grid(row=0, column=i, sticky=tk.EW, padx=1)
      switch.columnconfigure(i, weight=1, uniform="switch")

    self.list = ttk.Treeview(self, show="tree", selectmode="browse", height=4)
    self.list.bind("<<TreeviewSelect>>", lambda _e: self._picked())

    self.bar = ttk.Frame(self)
    "The buttons for what's shown: *animationBar* or *layoutBar*."
    self.bar.pack(side=tk.TOP, fill=tk.X, pady=(6, 0))
    self.animationBar = ttk.Frame(self.bar)
    self.playButton = ttk.Button(self.animationBar, width=7, command=self.view.toggleAnimationLayout)
    self.playButton.pack(side=tk.LEFT)
    self.status = ttk.Label(self.animationBar, foreground="gray35")
    self.status.pack(side=tk.LEFT, padx=(4, 0), fill=tk.X, expand=True)
    tip([self.playButton], TIPS["play"]); tip([self.status], TIPS["status"])
    self.layoutBar = ttk.Frame(self.bar)
    self.actButton = ttk.Button(self.layoutBar, width=8, default="active")
    "Arrange (for arrange now) or Use (for keep arranged)."
    self.actButton.pack(side=tk.RIGHT, padx=(4, 0))
    self.revertButton = ttk.Button(self.layoutBar, text="Revert", width=8, command=self.revert)
    self.revertButton.pack(side=tk.RIGHT)
    tip([self.revertButton], TIPS_LAYOUT["revert"])
    CreateToolTip(self.actButton, lambda: TIPS_LAYOUT.get(self.category.get(), ""), wrapLength=300)

    ttk.Separator(self).pack(side=tk.TOP, fill=tk.X, pady=6)

    body = ttk.Frame(self)
    body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
    self.canvas = tk.Canvas(body, highlightthickness=0, borderwidth=0, background=str(ttk.Style().lookup("TFrame", "background") or "systemWindowBackgroundColor"))
    self.scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=self.canvas.yview)
    self.canvas.configure(yscrollcommand=self.scrollbar.set)
    self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    self.page = ttk.Frame(self.canvas)
    "What's on the page (in the canvas, so it scrolls)."
    self._pageItem = self.canvas.create_window(0, 0, window=self.page, anchor=tk.NW)
    self.page.bind("<Configure>", lambda _e: self._fit())
    self.canvas.bind("<Configure>", lambda _e: self._fit())
    self.bind_class(SCROLL_TAG, "<MouseWheel>", self._wheel)
    self._listFor(ANIMATED)
    self._build()

  # ---- choosing a page -------------------------------------------------------

  def show(self, category:str, name:str|None=None) -> None:
    '''
    Show a kind of layout, and (unless it's "animate") one of them.

    :param category: Of *layout.CATEGORIES*.
    :type category: str
    :param name: The layout's name (in *layout.LAYOUTS*): by default, the one
      last shown for *category* -- or, for "keep arranged", the view's.
    :type name: str | None
    '''
    self._keepDraft()
    if name is not None:
      self.chosen[category] = name
    self.category.set(category)
    self._listFor(category)
    self._build()

  def current(self) -> tuple[str, str|None]:
    '''
    :returns: The kind of layout shown, and the layout (None for "animate").
    :rtype: tuple[str, str | None]
    '''
    category = self.category.get()
    return category, None if category == ANIMATED else self.chosen.get(category)

  def _switched(self) -> None:
    'The switch was clicked: its variable is already set.'
    self._keepDraft(self._page)
    category = self.category.get()
    self._listFor(category)
    self._build()

  def _listFor(self, category:str) -> None:
    '''
    Fill the list with the layouts of a kind (and select the one chosen), or
    hide it, for "animate".

    :param category: Of *layout.CATEGORIES*.
    :type category: str
    '''
    if category == ANIMATED:
      self.list.pack_forget()
      return
    names = [cls.NAME for cls in layoutsFor(category)]
    if self.chosen.get(category) not in names:
      dynamic = self.view.localLayout.NAME if self.view.localLayout is not None else ""
      self.chosen[category] = dynamic if category == DYNAMIC and dynamic in names else names[0]
    self.list.delete(*self.list.get_children())
    for name in names:
      self.list.insert("", tk.END, iid=name, text=self._listText(category, name))
    self.list.configure(height=len(names))
    self.list.pack(side=tk.TOP, fill=tk.X, pady=(6, 0), before=self.bar)
    self.list.selection_set(self.chosen[category])
    self.list.see(self.chosen[category])
    self._dynamicName = self.view.localLayout.NAME if self.view.localLayout is not None else ""

  def _listText(self, category:str, name:str) -> str:
    '''
    :returns: How a layout's listed: for "keep arranged", the view's is ticked.
    :rtype: str
    '''
    if category != DYNAMIC:
      return name
    return ("✓ " if self.view.localLayout is not None and self.view.localLayout.NAME == name else " ") + name

  def _picked(self) -> None:
    'A layout was picked in the list.'
    category = self.category.get()
    picked = self.list.selection()
    if category == ANIMATED or not picked or picked[0] == self.chosen.get(category):
      return
    self._keepDraft()
    self.chosen[category] = picked[0]
    self._build()

  # ---- the page --------------------------------------------------------------

  def _build(self) -> None:
    'Make the page for what\'s chosen afresh (so its relation types are the model\'s now).'
    for w in self.page.winfo_children():
      w.destroy()
    self.form = self.animation = None
    category, name = self.current()
    self._page = (category, name)
    self._showBar(category)
    if category == ANIMATED:
      self.animation = AnimationControls(self.page, self.view)
      self.animation.pack(side=tk.TOP, fill=tk.X, padx=(0, 4))
    else:
      self._buildLayout(category, LAYOUTS[str(name)])
    self.canvas.yview_moveto(0)
    self._scrollable(self.page)
    self._fit()

  def _buildLayout(self, category:str, cls:type[LayoutHeuristic]) -> None:
    '''
    Make the page for a layout: its name and its parameters (its buttons are in the bar: see *_showBar()*).

    :param category: *STATIC* or *DYNAMIC*.
    :type category: str
    :param cls: The layout.
    :type cls: type[LayoutHeuristic]
    '''
    bold = tkfont.nametofont("TkDefaultFont").copy()
    bold.configure(weight="bold")
    self._bold = bold # (keep it alive)
    ttk.Label(self.page, text=cls.NAME, font=bold).pack(side=tk.TOP, anchor=tk.W)
    self.hint = ttk.Label(self.page, text=HINTS[category], foreground="gray40", wraplength=self.WIDTH - 40)
    self.hint.pack(side=tk.TOP, anchor=tk.W, pady=(0, 6))
    draft = self.drafts.get((category, cls.NAME))
    asked, values = cls.parametersFor(category, draft if draft is not None else self.view.lastLayoutParameters(cls))
    self.values = values
    if asked:
      self.form = LayoutForm(self.page, cls, asked, values, self.view, wrap=self.WIDTH - 60, compact=True)
      self.form.pack(side=tk.TOP, fill=tk.X)
    else:
      ttk.Label(self.page, text="(It has no settings.)", foreground="gray40").pack(side=tk.TOP, anchor=tk.W, padx=8)
    self.revertButton.configure(state="normal" if asked else "disabled")

  def _showBar(self, category:str) -> None:
    '''
    Show the buttons for a kind of layout in the bar (see *bar*).

    :param category: Of *layout.CATEGORIES*.
    :type category: str
    '''
    shown, hidden = (self.animationBar, self.layoutBar) if category == ANIMATED else (self.layoutBar, self.animationBar)
    hidden.pack_forget()
    shown.pack(side=tk.TOP, fill=tk.X)
    if category != ANIMATED:
      self.actButton.configure(text="Arrange" if category == STATIC else "Use",
                               command=self.arrange if category == STATIC else self.use)

  def _values(self) -> dict[str, Any]|None:
    '''
    :returns: The page's values (as keyword arguments for the layout's
      constructor) -- or None, having said why, if one won't do.
    :rtype: dict[str, Any] | None
    '''
    return self.form.read() if self.form is not None else dict(self.values)

  def _keepDraft(self, page:tuple[str, str|None]|None=None) -> None:
    '''
    Keep the page's values (if it's a layout's), to show again when it's shown again.

    :param page: What the page is for (see *_page*): by default, what it's for now.
    :type page: tuple[str, str | None] | None
    '''
    category, name = page if page is not None else self._page
    if self.form is not None and name is not None:
      values = self.form.read(complain=False)
      if values is not None:
        self.drafts[(category, name)] = values

  def arrange(self) -> None:
    '"Arrange": arrange the view once with the page\'s layout (one undoable command: it remembers its values).'
    category, name = self._page
    values = self._values()
    if values is None or name is None:
      return
    self.drafts.pop((category, name), None)
    LAYOUTS[name](self.view, **values).arrange()

  def use(self) -> None:
    '"Use": make the page\'s layout the view\'s dynamic layout (it remembers its values).'
    category, name = self._page
    values = self._values()
    if values is None or name is None:
      return
    self.drafts.pop((category, name), None)
    self.view.setDynamicLayout(LAYOUTS[name](self.view, **values))
    self.refresh()

  def revert(self) -> None:
    '"Revert": show the values the page\'s layout was last used with (or its defaults) again.'
    self.drafts.pop(self._page, None) # type: ignore[arg-type]
    self._build()

  # ---- scrolling and fitting -------------------------------------------------

  def _fit(self) -> None:
    'Make the page as wide as the panel (its notes wrapped to fit), and scrollable if it\'s taller.'
    width = self.canvas.winfo_width()
    if width <= 1:
      return
    if int(self.canvas.itemcget(self._pageItem, "width") or 0) != width:
      self.canvas.itemconfigure(self._pageItem, width=width)
    wrap = max(120, width - 40)
    if self.form is not None:
      self.form.setWrap(wrap - 20)
    hint = self.__dict__.get("hint")
    if hint is not None and hint.winfo_exists() and int(str(hint.cget("wraplength")) or 0) != wrap:
      hint.configure(wraplength=wrap)
    height = self.page.winfo_reqheight()
    self.canvas.configure(scrollregion=(0, 0, width, height))
    if height > self.canvas.winfo_height():
      if not self.scrollbar.winfo_ismapped():
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=self.canvas)
    elif self.scrollbar.winfo_ismapped():
      self.scrollbar.pack_forget()
      self.canvas.yview_moveto(0)

  def _scrollable(self, widget:tk.Misc) -> None:
    '''
    Let the mouse wheel scroll the page over *widget* and everything in it
    (see *SCROLL_TAG*).

    :param widget:
    :type widget: tk.Misc
    '''
    tags = widget.bindtags()
    if SCROLL_TAG not in tags:
      widget.bindtags((SCROLL_TAG, *tags))
    for child in widget.winfo_children():
      self._scrollable(child)

  def _wheel(self, event:tk.Event) -> str|None:
    'The mouse wheel, over the page: scroll it (if it\'s taller than the panel).'
    if not self.scrollbar.winfo_ismapped():
      return None
    delta = int(event.delta)
    self.canvas.yview_scroll(-delta if abs(delta) < 120 else -delta // 120, "units")
    return "break" # (not a combobox's or a slider's change too)

  # ---- keeping it up to date -------------------------------------------------

  def refresh(self) -> None:
    'Show the animation layout\'s state and settings, and which layout keeps the view arranged (eg: changed from the menu).'
    layout = self.view.animationLayout()
    self.playButton.configure(text="■ Stop" if layout.active else "▶ Start")
    self.status.configure(text=statusText(layout))
    if self.animation is not None:
      self.animation.refresh()
    dynamic = self.view.localLayout.NAME if self.view.localLayout is not None else ""
    if dynamic != self._dynamicName:
      self._dynamicName = dynamic
      if self.category.get() == DYNAMIC:
        for name in self.list.get_children():
          self.list.item(name, text=self._listText(DYNAMIC, name))

  def startPolling(self) -> None:
    'Keep the panel up to date while it\'s shown (see *POLL_MS*).'
    if not self._polling:
      self._polling = True
      self._poll()

  def stopPolling(self) -> None:
    'Stop keeping the panel up to date (it\'s hidden).'
    self._polling = False

  def _poll(self) -> None:
    if not self._polling or not self.winfo_exists():
      self._polling = False
      return
    try:
      self.refresh()
      self._scrollable(self.page) # (what's been remade since, too: eg: a relation table's rows, moved)
    finally:
      self.after(self.POLL_MS, self._poll)

  # ---- saved with the view ---------------------------------------------------

  def savedState(self) -> str:
    '''
    :returns: What's saved with the view about the panel, besides whether it's
      shown: what's chosen and how wide it is -- eg: "page=static;static=tree;dynamic=avoid overlaps;width=340".
    :rtype: str
    '''
    if self.winfo_ismapped() and self.winfo_width() > 1:
      self.width = self.winfo_width()
    parts = {"page": self.category.get(), **self.chosen, "width": str(self.width)}
    return ";".join(f"{k}={v}" for k, v in parts.items())

  def setSavedState(self, state:dict[str, str]) -> None:
    '''
    Put back what *savedState()* saved (parsed): what's chosen, and how wide it is.

    :param state:
    :type state: dict[str, str]
    '''
    for category in (STATIC, DYNAMIC):
      if state.get(category) in LAYOUTS:
        self.chosen[category] = state[category]
    try:
      self.width = max(self.MIN_WIDTH, int(state.get("width", self.width)))
    except ValueError:
      pass
    page = state.get("page", ANIMATED)
    self.show(page if page in (STATIC, DYNAMIC, ANIMATED) else ANIMATED)
