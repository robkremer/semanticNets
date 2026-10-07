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
'''
The reasoning toolbar: a strip across the bottom of a view's window with a
*Reason* button (run the reasoner over the view's model: see
*sn.model.reasoner.reason()*), a *Retract* button (take what it inferred back
out: see *sn.model.reasoner.clearReasoning()*), and a line saying what the last
"reason" found. Reasoning isn't redone as the model is edited, so it's a click
away. At its right, a pencil says whether the view's model can be edited --
crossed out if it's write-locked (eg: the system model, or the base rules). Shown and hidden with "View | Reasoning toolbar" (see
*SNGView.showReasoningToolbar()*).

Created on Oct 5, 2026

.. codeauthor:: Rob Kremer <robkremer@me.com>
'''
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING
from util.tooltip import CreateToolTip
if TYPE_CHECKING:
  from sn.view.graphics.sngView import SNGView

TIPS:dict[str, str] = {
  "reason": "Run the reasoner over the model: what it infers is shown (faded) in every view of the model, "
            "and its report goes to the terminal. It isn't redone as you edit: click again after changes.",
  "retract": "Take what the reasoner inferred back out of the model (and its views).",
  "status": "What the last \"reason\" found: the objects it inferred, and the problems (violations) it found.",
  "writable": "The model can be edited (and saved).",
  "locked": "The model is read-only: it can't be changed here (eg: the system model, or the base rules). "
            "Its views can still be arranged and saved.",
}
"Tooltips for the toolbar's controls."

class ReasoningToolbar(ttk.Frame):
  '''
  The reasoning toolbar for a view: see the module doc.
  '''
  PADDING = 4
  "The toolbar's padding (pixels) at its left and right."
  LOCK_SIZE = 18
  "The width and height (pixels) of the pencil that says whether the model's write-locked."

  def __init__(self, master:tk.Misc, view:SNGView):
    '''
    :param master: The widget it's in: the view's window.
    :type master: tk.Misc
    :param view: The view whose model it reasons over.
    :type view: SNGView
    '''
    super().__init__(master, padding=(self.PADDING, 2))
    self.view = view
    tip = lambda widget, text: CreateToolTip(widget, text, wrapLength=300)
    self.reasonButton = ttk.Button(self, text="Reason", width=8, command=self.view.reason)
    self.reasonButton.pack(side=tk.LEFT)
    tip(self.reasonButton, TIPS["reason"])
    self.retractButton = ttk.Button(self, text="Retract", width=8, command=self.view.clearReasoning)
    self.retractButton.pack(side=tk.LEFT, padx=(4, 0))
    tip(self.retractButton, TIPS["retract"])
    self.status = ttk.Label(self, foreground="gray35")
    self.status.pack(side=tk.LEFT, padx=(10, 0))
    tip(self.status, TIPS["status"])
    size = self.LOCK_SIZE
    lockFrame = ttk.Frame(self) # (the tooltip's on this: on a canvas, it'd have to be on one of its items)
    lockFrame.pack(side=tk.RIGHT)
    self.lockIcon = tk.Canvas(lockFrame, width=size, height=size, highlightthickness=0, bd=0,
                              background=ttk.Style().lookup("TFrame", "background") or self.winfo_toplevel().cget("background"))
    self.lockIcon.pack()
    self.lockIcon.create_text(size / 2, size / 2, text="\u270e", font=("Arial", int(size * 0.75)), fill="gray25") # (a pencil)
    self.lockIcon.create_line(3, size - 3, size - 3, 3, fill="red3", width=2, tags=("slash",))
    tip(lockFrame, lambda: TIPS["locked" if self.view.model.writeLocked() else "writable"])
    self.refresh()

  def refresh(self) -> None:
    '''
    Show what the view's model's last "reason" found (see *SNGView.reasoningSummary()*),
    and enable *Retract* only if there's something to retract.
    '''
    summary = self.view.reasoningSummary()
    self.status.configure(text=summary or "not reasoned")
    self.retractButton.state(["!disabled"] if summary else ["disabled"])
    self.refreshLock()

  def refreshLock(self) -> None:
    '''
    Show whether the view's model is write-locked: the pencil crossed out, or not.
    '''
    self.lockIcon.itemconfigure("slash", state=tk.NORMAL if self.view.model.writeLocked() else tk.HIDDEN)
