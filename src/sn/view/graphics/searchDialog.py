'''
The search dialog ("Edit | Find...": see *SNGView.openSearchDialog()*): find
nodes and relations by name, and highlight them in the view (see
*SNGView.search()*) -- optionally showing those in the model (and its
super-models) that aren't in the view yet.

Created on Oct 15, 2026

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
import re
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, TYPE_CHECKING
from util.utils import ownDialog
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

CONFIRM_OVER = 25
"Ask before showing more objects than this from the model (see *SearchDialog.confirm()*)."

class SearchDialog(tk.Toplevel):
  '''
  A find dialog over a view: what to look for, how (whole word, match case,
  regular expression), and where (the view, or the whole model -- and its
  super-models). Not modal: it stays open, for searching again, until closed.
  What was last asked for is remembered (for the session) for the next one.
  '''
  last:dict[str, Any] = {"pattern": "", "wholeWord": False, "matchCase": False, "regex": False,
                         "wholeModel": False, "superModels": False}
  "The last search's pattern and options (any view's)."

  def __init__(self, view:SNGView):
    '''
    :param view: The view to search.
    :type view: SNGView
    '''
    super().__init__(view.canvas)
    ownDialog(self, view.canvas) # (over the view's window, not full screen: see ownDialog())
    self.view = view
    self.title(f"Find in {view.model.name}")
    self.resizable(True, False)
    last = SearchDialog.last
    self.pattern = tk.StringVar(value=last["pattern"])
    self.options:dict[str, tk.BooleanVar] = {k: tk.BooleanVar(value=last[k]) for k in last if k != "pattern"}

    frame = ttk.Frame(self, padding=10)
    frame.pack(fill=tk.BOTH, expand=True)
    frame.columnconfigure(1, weight=1)
    ttk.Label(frame, text="Find:").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
    self.entry = ttk.Entry(frame, textvariable=self.pattern, width=32)
    self.entry.grid(row=0, column=1, columnspan=3, sticky=tk.EW)

    how = ttk.Frame(frame)
    how.grid(row=1, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))
    for key, label in (("wholeWord", "Whole word"), ("matchCase", "Match case"), ("regex", "Regular expression")):
      ttk.Checkbutton(how, text=label, variable=self.options[key]).pack(side=tk.LEFT, padx=(0, 12))
    ttk.Checkbutton(frame, text="Whole model (show what's found that isn't in the view)",
                    variable=self.options["wholeModel"], command=self._onWholeModel) \
       .grid(row=2, column=0, columnspan=4, sticky=tk.W, pady=(6, 0))
    self.supersButton = ttk.Checkbutton(frame, text="Include super-models", variable=self.options["superModels"])
    self.supersButton.grid(row=3, column=0, columnspan=4, sticky=tk.W, padx=(22, 0), pady=(2, 0))
    self._onWholeModel()

    self.status = ttk.Label(frame, text="", foreground="gray40", wraplength=340)
    self.status.grid(row=4, column=0, columnspan=4, sticky=tk.W, pady=(8, 0))

    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=4, sticky=tk.EW, pady=(10, 0))
    ttk.Button(buttons, text="Clear highlights", command=self.clear).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Find", command=self.find, default="active").pack(side=tk.RIGHT, padx=(6, 0))
    ttk.Button(buttons, text="Close", command=self.destroy).pack(side=tk.RIGHT)
    self.bind("<Return>", lambda _e: self.find())
    self.bind("<KP_Enter>", lambda _e: self.find())
    self.bind("<Escape>", lambda _e: self.destroy())
    self.bind("<Command-KeyPress-w>", lambda _e: self.destroy())
    self._place()
    self.bringToFront()

  def _onWholeModel(self) -> None:
    "Super-models are searched only with the whole model."
    self.supersButton.state(["!disabled"] if self.options["wholeModel"].get() else ["disabled"])

  def _place(self) -> None:
    "Over the top right of the view's window."
    self.update_idletasks()
    top = self.view.canvas.winfo_toplevel()
    if top.winfo_viewable():
      x = top.winfo_rootx() + max(0, top.winfo_width() - self.winfo_reqwidth() - 40)
      y = top.winfo_rooty() + 60
      self.geometry(f"+{x}+{y}")

  def bringToFront(self) -> None:
    "Show it in front, ready to type in (what's there selected)."
    try:
      self.deiconify()
      self.lift()
      self.focus_force()
      self.entry.focus_set()
      self.entry.select_range(0, tk.END)
      self.entry.icursor(tk.END)
    except tk.TclError:
      pass

  def confirm(self, n:int) -> bool:
    '''
    :param n: How many objects from the model aren't in the view.
    :type n: int
    :returns: Whether to show them: yes, unless there are a lot and the user says not.
    :rtype: bool
    '''
    if n <= CONFIRM_OVER:
      return True
    return messagebox.askyesno("Find", f"{n} objects that match aren't in the view. Show them all?", parent=self)

  def find(self) -> None:
    "Search (see *SNGView.search()*), and say what was found."
    pattern = self.pattern.get()
    opts = {k: v.get() for k, v in self.options.items()}
    SearchDialog.last = {"pattern": pattern, **opts}
    if pattern == "":
      self._say("Type what to look for.", error=True)
      return
    try:
      found, brought = self.view.search(pattern, confirm=self.confirm, **opts)
    except re.error as ex:
      self._say(f"That isn't a good regular expression: {ex}.", error=True)
      return
    if not found:
      where = "the view" if not opts["wholeModel"] else "the model" + (" or its super-models" if opts["superModels"] else "")
      self._say(f"Nothing in {where} matches.", error=True)
      return
    nodes = sum(1 for vo in found if not self._isRelation(vo))
    say = f"{nodes} node{'' if nodes == 1 else 's'} and {len(found) - nodes} relation{'' if len(found) - nodes == 1 else 's'} highlighted"
    self._say(say + (f" ({brought} newly shown)." if brought else "."))

  @staticmethod
  def _isRelation(vo:Any) -> bool:
    from sn.model.model import Relation
    return isinstance(vo.modelObject, Relation)

  def clear(self) -> None:
    "Remove the highlights."
    self.view.clearHighlights()
    self._say("")

  def _say(self, text:str, error:bool=False) -> None:
    self.status.configure(text=text, foreground="firebrick" if error else "gray40")
