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
        AttrEditor
        ChangeDescr
        ColorEditor
        HierarchicalAttrEditor
      :parts: 3
      :private-bases:
      :top-classes: util.commandParser.ParsableCommandDef, util.commandParser.ParsableQuery

Created on Mar 17, 2025

.. codeauthor:: Rob Kremer <robkremer@me.com>

----------------
'''

import logging
import tkinter as tk
import re
from tkinter import colorchooser, ttk
from dataclasses import dataclass
from typing import Any, Callable, Union, Optional, override, Type
from types import NoneType
from copy import copy

import sn
from util.attribute import AttributedObject, Attribute, \
  KNOWN_TYPES, isValidType, TYPE_EQUIVALENTS
from util.persistence.pRef import Serializable, PRObject
from util.utils import getFullClassName, xmlToStringIndented
#from sn.model.tgcommands import UpdateAttrsCommand
from util.utils import VerticalScrolledFrame
from util.tooltip import CreateToolTip
from tkinter.ttk import Widget

logger:sn.SNLogger = sn.getLogger(__name__)

DOWN_ARROW = "\u2B07"
INHERIT_KEY_EXT = "-\u2193"

KIND_WIDTH = 10

DOC_QUALIFIER = \
'''Qualifiers:
f:   final:
          The attribute many not be modified in subtypes.
if:  instance final:
          Instances of this type may not modify the attribute.
vni: value not inheritable:
          Instances of this type must override the attribute value.'''

def editAttrsBox(parent:tk.Widget, attrs:AttributedObject, title="Attributes Editor", 
                 editKey:Optional[str]=None, disabled:bool=False) -> Optional[dict[str,Attribute]]:
  '''
  :param parent: The parent widget
  :param attrs: The *AttributedObject* object to be updated.
  :param title: The title of the dialog window. 
  :return: An dict *str->Attribute* with any updates 
   
  displays an *AttrsEditor* or a *HierarchicalAttrsEditor* (depanding on whether 
  *attrs* is an *AttributedObject* or a *HierarchicalAttributedObject* ) and
  updates the result to *attrs* .  
  '''
  if isinstance(attrs, HierarchicalAttributedObject):
    editor = HierarchicalAttrEditor(parent, attrs, title=title, disabled=disabled)
  else:  
    editor = AttrEditor(parent, attrs, title=title, disabled=disabled)
  editor.show(editKey=editKey)
  logger.debug(f'editAttrsBox(): updated: {editor.updatedKeys}')
  return editor.updatedKeys
  
def applyEditAttrsBox(parent:tk.Widget, attrs:AttributedObject, title="Attributes Editor", 
                      editKey:Optional[str]=None) -> None:
  '''
  Same as *editAttrsBox*, but applies the changes.
  '''
  attrChangeList = editAttrsBox(parent, attrs, title, editKey)
  if attrChangeList is not None:
    with attrs.ChangeMgr(attrs) as cm:
      attrs.updateWith(attrChangeList)
      topics = []
      for k,v in attrChangeList.items():
        topics.append(("setattr", k, v))
      cm.registerTopics(topics)
  
def getEditedAttrsCommandObj(parent:tk.Widget, attrs:AttributedObject, title="Attributes Editor", editKey:Optional[str]=None, disabled:bool=False):
  '''
  :return: An *UpdateAttrsCommand* object that displays an *AttrsEditor* or a
      *HierarchicalAttrsEditor* (depanding on whether *attrs* is an *AttributedObject*
      or a *HierarchicalAttributedObject* ) with the appropriate do/undo properties.
  '''
  updates = editAttrsBox(parent, attrs, title=title, editKey=editKey, disabled=disabled)
  return UpdateAttrsCommand(attrs, updates) if updates is not None else None
  
## Utility
def clearGrid(widget:tk.Widget, row=None, column=None):
  for w in widget.grid_slaves(row=row, column=column):
    w.destroy()

@dataclass
class ChangeDescr:
  tkVar:tk.Variable #= None
  editor:tk.Widget #= None
  delete:bool #= False
  saveMethod:Callable #= lambda attr: attr.value
  
  typeLabel = None
  # editTypeButton = None
  qualFinal:tk.BooleanVar = None # tk.BooleanVar()
  qualInstanceFinal:tk.BooleanVar = None # tk.BooleanVar()
  qualValueNotInherited:tk.BooleanVar = None # tk.BooleanVar()
  
  def getValue(self) -> Any:
    if isinstance(self.editor, tk.Text):
      return self.editor.get("1.0", tk.END)
    else:
      return None if self.tkVar is None else self.tkVar.get()

  def setValue(self, val:Any):
    if isinstance(self.editor, tk.Text):
      self.editor.delete("1.0", tk.END)
      self.editor.insert("1.0", val)
    else:
      return self.tkVar.set(val)

SYS_ATTRIBUTES = ['name']
"Used to highlight the 'system' labels on the grid"

class ColorEditor(tk.Frame):
  def __init__(self, master, var:tk.StringVar, color:str):
    self.var = var
    #self.style = ttk.Style()
    #self.style.configure('My.TFrame', background="purple")#color)
    self.c = "systemWindowBackgroundColor" if color=="" else color
    tk.Frame.__init__(self, master)
    self.colorButton = tk.Button(self, text=str(color), command=self.colorChooser)#, highlightbackground=None if color=="" else color, padx=-15)
    self.colorButton.pack(side="left", expand=0)#), fill="x")
    self.transButton = tk.Button(self, text="\u2A37", command=self.setTransparent)#, highlightbackground=None if color=="" else color, padx=-30)
    self.transButton.pack(side="right", expand=0)
    self.swatch = tk.Canvas(self, background=self.c, height=3, width=5, borderwidth=2, relief="groove")
    #self.swatch.pack(side="left", after=self.colorButton, expand=1, anchor="center", fill="both", ipadx=0, ipady=0, padx=0, pady=0)
    self.swatch.pack(side="bottom", expand=1, anchor="center", fill="both", ipadx=0, ipady=0, padx=0, pady=0)

    # self.colorButton.config(command=self.colorChooser)
    # self.transButton.config(command=self.setTransparent)
    self.config(bg=self.c)
    
  def setTransparent(self):
    self.colorButton.configure(text="", highlightbackground=None)
    self.var.set("")
    self.config(bg="")
    
  def colorChooser(self):
    # askcolor() returns (rgb, hex)
    color =self.var.get()
    if color is None:
      color = "black"
    if color == "": # colorchooser() can't handle "" (transparent)
      color = "gray"
    color = colorchooser.askcolor(initialcolor=color, parent=self)
    if color is not None:
      color = color[1]
      self.var.set(color)
      self.config(bg=color)
      self.colorButton.config(text=str(color))
    
  def config(self, **conf):
    
    def setSwatch(key:str):
      self.c = "systemWindowBackgroundColor" if conf[key]=="" else conf[key]
      d = {key: self.c}
      self.swatch.configure(**d)
      del conf[key]
      
    if "bg" in conf:
      setSwatch("bg")
    if "background" in conf: 
      setSwatch("background")
    if "highlightbackground" in conf: 
      setSwatch("highlightbackground")
    if "highlightcolor" in conf: 
      setSwatch("highlightcolor")
    if len(conf) > 0:
      if "!disabled" in conf:
        conf["normal"] = "normal"
        del conf["!disabled"]
      self.colorButton.configure(**conf)
      self.transButton.configure(**conf)
    
class AttrEditor(tk.Toplevel):
  '''
  Implements a graphical editor for an *AttributedObject* of the form:
  
  +--------------------------------+
  | <editor lines> ...             |
  +--------------------------------+
  | [<Message line>]               |
  +--------------------------------+
  | [<Answer line>]                |
  +--------------------------------+
  | <Add New Attribute button>     |
  +--------------------------------+
  | <Cancel button>  <Save button> |
  +--------------------------------+

  where <editor lines> look like this:
  
  +------+---------+----------------+----------------------+--------+
  |<stat>| <label> | <value editor> | <button> <button>... | <type> |
  +------+---------+----------------+----------------------+--------+
  |<stat>| <label> | <value editor> | <button> <button>... | <type> |
  +------+---------+----------------+----------------------+--------+
  
  The <Message line> and <Answer iine> are only visiable when the *setMessage()* 
  or *ask()* methods are called.
  
  '''
  #TODO: Implement "disabled" param
  def __init__(self, parent, attrs:AttributedObject, title="Attribute Editor", disabled=False):
    super().__init__(parent)
    self.parent = parent
    self.title(title if title else "Attribute Editor")
    self.attrs = attrs
    #self.changes = dict() # name:Item
    self.vars:dict[str,ChangeDescr] = dict() # name:ChangeDescr
    
    self.hide = lambda attr: False
    self.disabled = disabled
    #self.editable = lambda attr: not self.disabled
    self.updatedKeys = None
    self.rows = 0 # The total number of rows in the editors list grid.
    
    self.editKey:Optional[str] = None
    self.editWidget:Optional[Widget] = None
    
    # "constants" for the outer grid
    self.rEditors = 0
    self.rMessage = 2
    self.rEnter = 3
    self.rButtons1 = 6
    self.rButtons2 = 8

    # "constants" for the columns in the Editors grid
    self.rowsPerEntry = 1
    self.EntryOffset = 0
    self.cStatus = 0
    self.cLabel = 1
    self.cEdit = 2
    self.cKind = 3
    self.cDel = 4
    self.cspan = 5
    
    self.outerSpan = 2
    

  def show(self, editKey:Optional[str]=None): #, disabled=False):
    '''
    :param editKey: [Optional str] If present, set the edit focus to the *editKey* 
      creating a local attribute if necessary.
    '''
    if editKey is not None:
      self.editKey = editKey
    
    self.geometry("700x600")
    #self.title('Attributes')
    self.resizable(1, 1)

    # configure the outer grid
    self.columnconfigure(0, weight=1)
    self.columnconfigure(1, weight=1)
    self.rowconfigure(0, weight=2)
    self.rowconfigure(1, weight=0)

    scrollFrame = VerticalScrolledFrame(self)
    scrollFrame.grid(column=0, row=self.rEditors, columnspan=self.outerSpan, sticky=tk.W+tk.E+tk.N+tk.S, padx=0, pady=0)
    self.editorsListFrame = scrollFrame.interior
    #self.editorsListFrame.pack()

    # configure list of editor's grid
    self.editorsListFrame.columnconfigure(self.cStatus, weight=0)
    self.editorsListFrame.columnconfigure(self.cLabel, weight=0)
    self.editorsListFrame.columnconfigure(self.cEdit,  weight=2, minsize=200)
    self.editorsListFrame.columnconfigure(self.cKind,  weight=0)
    self.editorsListFrame.columnconfigure(self.cDel,   weight=0)
    
    self.makeHeader(0)
    ttk.Separator(self.editorsListFrame, orient=tk.HORIZONTAL) \
      .grid(column=0, row=1, columnspan=self.cspan, sticky=tk.W+tk.E, padx=0, pady=0)
    i = 2
    keys = list(self.attrs.keys())
    if not tygra.tygraPrefs.get("debug", storeDefault=False):
      keys = [k for k in keys if not k.startswith(".")] # filter out anything beginning with "."
    keys.sort()
    for k in keys:
      try:
        v  = self.attrs.getRecord(k)
        self.vars[k] = ChangeDescr(None, None, False, str)
        row = i+self.EntryOffset
        if self.hide(v): continue # hide system attributes
        self.makeNewEntry(k, v, row, self.disabled, "")
        i += self.rowsPerEntry
      except:
        logger.exception(f'Failed to load on key "{k}"')
      
    self.rows = i
      
    ttk.Separator(self, orient=tk.HORIZONTAL) \
      .grid(column=0, row=self.rMessage-1, columnspan=self.outerSpan, sticky=tk.W+tk.E, padx=0, pady=0)
      
    ttk.Separator(self, orient=tk.HORIZONTAL) \
      .grid(column=0, row=self.rButtons1-2, columnspan=self.outerSpan, sticky=tk.W+tk.E, padx=0, pady=0)
    ttk.Separator(self, orient=tk.HORIZONTAL) \
      .grid(column=0, row=self.rButtons1-1, columnspan=self.outerSpan, sticky=tk.W+tk.E, padx=0, pady=2)
    if not self.disabled:
      ttk.Button(self, text="Add New Attribute", command=self.addNewAttribute) \
        .grid(column=0, row=self.rButtons1, columnspan=self.outerSpan, padx=20, pady=2) #, sticky=tk.W

    ttk.Separator(self, orient=tk.HORIZONTAL) \
      .grid(column=0, row=self.rButtons2-1, columnspan=self.outerSpan, sticky=tk.W+tk.E, padx=0, pady=0)
    ttk.Button(self, text="Dismiss" if self.disabled else "Cancel", command=self.dismiss) \
      .grid(column=0, row=self.rButtons2, columnspan=1, sticky=tk.W, padx=20, pady=10)
    if not self.disabled:
      ttk.Button(self, text="Save Changes", command=self.save) \
        .grid(column=1, row=self.rButtons2, columnspan=1, sticky=tk.E, padx=20, pady=10)

    self.protocol("WM_DELETE_WINDOW", self.dismiss) # intercept close button
    #self.overrideredirect(1) # deletes the title bar

    # make this window modal
    try: # this wait sometimes fails with "TclError: <window> was deleted before its visibility changed" 
      self.wait_visibility() # can't grab until window appears, so we wait
    except:
      pass
    #self.grab_set()       # ensure all input goes to our window
    self.grab_set_global() #   used this version because grab_set() doesn't actually work.
    self.transient(self.parent) # dialog window is related to main
    
    if self.editKey is None:
      self.focus_set()
    else:
      self.editWidget = self.vars[self.editKey].editor
      self.editWidget.focus_set()
      
    self.wait_window()     # block until window is destroyed
    
  def dismiss(self):
    '''
    Call this method to destroy the window. It will also release the modal window.
    '''
    self.grab_release()
    self.destroy()

  ### HANDLERS #################################################################
  
  def addNewAttribute(self):
    self.ask("Enter the new key:", lambda event, ans: self._addNewAttribute2(event, ans), bg="yellow")

  def _addNewAttribute2(self, event, name:str):
    self.clearMessage()
    if name is None:
      return
    if name in list(self.attrs.keys()):
      self.setMessage(f'Attribute name "{name}" is already in use.', bg="red", fg="yellow")
      return
    newAttr = Attribute(name, str, "", AttributeFlags(0))
    self.attrs[name] = newAttr
    self.makeNewEntry(name, newAttr, self.rows+self.EntryOffset, False, keyExt="")
    self.rows += self.rowsPerEntry
    
  def deleteAttr(self, key, item, editor, row, button):
    text = button.config()['text'][-1]
    logger.debug(f"deleteAttr: text = '{text}'")
    if text == 'delete':
      button.config(text='undel')
      editor.config(state="disabled")
      self.vars[key].delete = True
    else:
      button.config(text='delete')
      editor.config(state="!disabled")
      self.vars[key].delete =  False

  def typeInconsistent(self, event, ans, key, row, originalAnswer):
    asn = ans.upper()
    if ans not in ["Y", "N"]:
      return # give up
    if ans == "Y":
      #self.makeKind(self.editorsListFrame, key, originalAnswer, self.cKind, row)
      self.vars[key].setValue("")
      self.resetKind(originalAnswer, key, row)
    self.clearMessage()
       
  def resetKind(self, kind, key, row):
    clearGrid(self.editorsListFrame, column=self.cKind, row=row)
    self.makeKind(self.editorsListFrame, key, kind, self.cKind, row, None, False, "")
    value = self.vars[key].getValue()
    typeLabel = self.vars[key].typeLabel
    tempAttr = copy(self.attrs._attrs[key])
    tempAttr.owner = None
    tempAttr.typ = kind
    tempAttr.value = value
    self.makeEditor(self.editorsListFrame, key, tempAttr, self.cEdit, row, False, "")
    self.vars[key].setValue(value)
    self.vars[key].typeLabel = typeLabel
    
  def editTypeAnswer(self, button, event, ans, key, row): 
    if not isValidType(ans):
      self.clearMessage()
      self.ask(f'Invalid type for key "{key}". Please enter one of the following known types:\n{KNOWN_TYPES}:', 
               lambda event, ans, key=key, row=row: self.editTypeAnswer(event, ans, key, row),
               default=ans, bg="red", fg="yellow")
      return
    if not isValidType(ans, self.vars[key].getValue()):
      self.clearMessage()
      self.ask(f'Entered type for key "{key}" is inconsistent with the value "{ans}".\n  Do you want to keep this type and delete the value? [Y/N]:', 
               lambda event, ans, key=key, row=row, originalAnswer=ans: self.typeInconsistent(event, ans, key, row, originalAnswer),
               default="Y", bg="red", fg="white") 
      return
    self.resetKind(ans, key, row)
    self.clearMessage()
    
  def editType(self, b:tk.Button, parent, key, typ, column, row):
    self.ask(f'Enter new type for key "{key}":', 
             lambda event, ans, b=b, key=key, row=row: self.editTypeAnswer(b, event, ans, key, row),
             default=self.vars[key].typeLabel["text"], bg="yellow") 

  def hasChanged(self, k:str) -> bool:
    if k not in self.attrs._attrs.keys(): # not local definition
      return False
    try:
      origAttr:Attribute = self.attrs._attrs[k] if k in list(self.attrs.keys()) else None
      v = self.vars[k]
      if origAttr is None:
        typeStr = "str"
        origValue = None
      else:
        origValue = origAttr.value
        if isinstance(origAttr.typ, type):
          typeStr = getFullClassName(origAttr.typ)
        else:
          typeStr = str(origAttr.typ)
          
      valueChanged = True # assume it's changed and try to disprove it
      if v.editor is None:
        valueChanged = False
      elif v.editor is tk.Label:
        valueChanged = False
      elif "state" in v.editor.keys() and v.editor["state"]==tk.DISABLED:
        valueChanged = False
      if valueChanged:
        strValue = v.getValue()
        value = v.saveMethod(strValue)
        if value == origValue:
          valueChanged = False
        
      #TODO: check this
      typeChanged = (v.typeLabel["text"] != typeStr) if v.typeLabel is not None else False
  
      return valueChanged or typeChanged
      
    except:
      logger.exception(f"AttributeEditor.hasChanged('{k}'):")
      return False
    
  def _saveKey(self, k:str, origAttr:Attribute):
          v = self.vars[k]
          self.updatedKeys[k] = copy(origAttr) if origAttr is not None else Attribute(k)
          t = v.typeLabel["text"]
          if t == "None":
            t = None
          self.updatedKeys[k]._typ = t
          strValue = v.getValue()
          value = v.saveMethod(strValue)
          self.updatedKeys[k].value = value
          
  def save(self):
    '''
    Stores a key/Attribute dictionary of all attributes that have been modified
    in the *self.updatedKeys* dictionary.  In the case of deleted Attributes, 
    the key maps to *None* .
    '''
    if self.disabled:
      return
    
    self.updatedKeys:dict[str, Optional[Attribute]] = dict()
    for k,v in self.vars.items():
      #ignore the records just used to display inherited items
      if k.endswith(INHERIT_KEY_EXT):
        continue
        
      #handle deletion
      if v.delete:
        self.updatedKeys[k] = None
        logger.debug(f'save(): deleting "{k}"')
        continue
        
      #handle changes
      if k not in self.attrs._attrs.keys(): # 
        continue
      origAttr:Attribute = self.attrs._attrs[k] if k in list(self.attrs._attrs.keys()) else None
      try:
        if self.hasChanged(k):
          logger.debug(f'save(): saving "{k}"')
          self._saveKey(k, origAttr)
      except Exception as ex:
        logger.exception(f'Failed on key {k}, value {v.getValue()}')
        
    if len(self.updatedKeys) == 0:
      self.updatedKeys = None
      
    self.dismiss()
    return
    
    # for k,v in self.vars.items():
    #   if v.delete: # flagged for deletion
    #     self.attrs.remove(k)
    #     continue
    #
    #   # get the kind and the new value
    #   kind = self.attrs._get(k).typ
    #   if kind == 'mtext':
    #     newValue = v.tkVar.get('1.0', 'end').rstrip() # the Text widget is tk, and doesn't use a a ttk.Variable.
    #   else:
    #     newValue = v.tkVar.get() 
    #
    #   if kind == 'int':
    #     try:
    #       newValue = int(newValue)
    #     except:
    #       print(f'WARNING: AttrEditor.save(): attribute {k} of kind int has value {newValue}, which failed the int test.  Not saving.')
    #       continue
    #   if kind == 'float':
    #     try:
    #       newValue = float(newValue)
    #     except:
    #       print(f'WARNING: AttrEditor.save(): attribute {k} of kind float has value {newValue}, which failed the float test.  Not saving.')
    #       continue
    #   elif kind == 'bool':
    #     try:
    #       newValue = newValue.lower() in ['true', 't', 'yes', 'y']
    #     except:
    #       print(f'WARNING: AttrEditor.save(): attribute {k} of kind bool has value {newValue}, which failed the bool test.  Not saving.')
    #       continue
    #
    #   if v.oldValue != newValue:
    #     print(f"AttrEditor.save(): {k} changed from '{v.oldValue}' ({type(v.oldValue).__name__}) to '{newValue}' ({type(newValue).__name__}). Observers={self.attrs.observers}.")
    #     try:
    #       self.attrs.config(k, newValue)
    #     except KeyError:
    #       self.attrs[k] = Attribute(k, newValue)
    #       # need to copy all the details from the inherited record to the new value...
    #       inhRec = self.attrs._get(k, includeLocals=False)
    #       inhRec.value = newValue
    #       inhRec.editable = True # the editable attribute does not inherit
    #       self.attrs.config(k, _record=inhRec)
    #
    #     self.attrs.notifyObservers(k, newValue)
    # self.grab_release()
    # self.destroy()

    
  
  ### UTILITY METHODS ########################################################
  
  def getEditorForType(self, parent:Any, key:str, typ:Union[type, str, NoneType], value:Any, keyExt) -> Any:
    
    def getHeight(text:str):
      return min(text.count('\n')+1, 4)
      
    editor = None

    if typ is None:
      typ = type(value)
      
    # Change the standard type string into actual types to save code below.
    if isinstance(typ, str) and typ not in ["color", "colour"] and typ in TYPE_EQUIVALENTS:
      typ = TYPE_EQUIVALENTS[typ]

    if isinstance(typ, str):
      if typ == 'mtext': # Anomalous in that there is NO textvariable. 
        editor = tk.Text(parent, height=getHeight(value))
        editor.insert('1.0', value)
        self.vars[key+keyExt] = ChangeDescr(None, editor, False, str)
      elif typ in ['color', 'colour']:
        if value is None:
          value = "black"
        v = tk.StringVar(value=str(value))
        # editor = tk.Button(parent, text=str(value), highlightbackground=None if value=="" else value, padx=-15)#, highlightthickness=4)
        # editor.config(command=lambda v=v, e=editor: self.colorChooser(v, e))
        # self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)
        editor = ColorEditor(parent, v, value)
        self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)
      elif typ.startswith('choices['):
        choices = None
        if not typ.endswith(']'):
          logger.error(f'{self.__class__.__name__}.getEditorForType(): Malfored "choices" type: "{typ}" (syntox is "choices[choice, choice, ...]")')
        else:
          choices = typ[8:-1].split(",")
          for i in range(len(choices)):
            choices[i] = choices[i].strip()
        v = tk.StringVar(value=str(value))
        if choices is not None:
          editor = ttk.Combobox(parent, textvariable=v, state="readonly")
          #editor['values'] = validator(None)
          editor['values'] = choices
          #editor.state(["readonly"])
          self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)
      elif typ == 'unknown':
        editor = ttk.Label(parent, text=str(value), foreground="brown")
    elif isinstance(typ, Type):
      if typ is int:
        checkWrapper = (self.winfo_toplevel().register(self.checkInt), '%P')
        v = tk.StringVar(value=str(value))
        editor = ttk.Entry(parent, textvariable=v, validate='key', validatecommand=checkWrapper)
        self.vars[key+keyExt] = ChangeDescr(v, editor, False, int)
      elif typ is float:
        checkWrapper = (self.winfo_toplevel().register(self.checkFloat), '%P')
        v = tk.StringVar(value=str(value))
        editor = ttk.Entry(parent, textvariable=v, validate='key', validatecommand=checkWrapper)
        self.vars[key+keyExt] = ChangeDescr(v, editor, False, float)
      elif typ is bool:
        v = tk.StringVar(value=str(value))
        editor = ttk.Checkbutton(parent, text="", variable=v, onvalue='True', offvalue='False')
        self.vars[key+keyExt] = ChangeDescr(v, editor, False, lambda b: b!='False' and bool(b))
      elif typ is str:
        v = tk.StringVar(value=str("" if value is None else value))
        editor = ttk.Entry(parent, textvariable=v)
        self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)
      elif typ is list:
        buf = xmlToStringIndented(Serializable.serializeAllXML(value, typ))
        editor = tk.Text(parent, height=getHeight(buf))
        editor.insert('1.0', buf)
        self.vars[key+keyExt] = ChangeDescr(None, editor, False, lambda val: Serializable.fromString(val))
      elif issubclass(typ, PRObject):
        # v = tk.StringVar(value=value.toString())
        # editor = ttk.Entry(parent, textvariable=v)
        # self.vars[key+keyExt] = ChangeDescr(v, editor, False, lambda val, c=value.container: PRObject.fromString(val, c))
        buf = xmlToStringIndented(value.serializeXML())
        editor = tk.Text(parent, height=getHeight(buf))
        editor.insert('1.0', buf)
        self.vars[key+keyExt] = ChangeDescr(None, editor, False, lambda val, c=value.container: PRObject.fromString(val, c))
      elif issubclass(typ, Serializable):
        # v = tk.StringVar(value=value.toString())
        # editor = ttk.Entry(parent, textvariable=v)
        # self.vars[key+keyExt] = ChangeDescr(v, editor, False, Serializable.fromString)
        buf = xmlToStringIndented(value.serializeXML())
        editor = tk.Text(parent, height=getHeight(buf))
        editor.insert('1.0', buf)
        self.vars[key+keyExt] = ChangeDescr(None, editor, False, lambda val: Serializable.fromString(val))
    else:
      logger.error(f'AttributeEditor on key "{key}": Types must be strings or Types, got typ {str(typ)} or type {type(typ).__name__}')

    if editor is None: # type not known, try generic methods
      #check if x==(literal_eval(str(x)) -- we can use that blindly if so.
      try:
        if value == (eval(str(value))):
          v = tk.StringVar(value=str(value))
          editor = ttk.Entry(parent, textvariable=v)
          self.vars[key+keyExt] = ChangeDescr(v, editor, False, eval)
      except:
        pass
    if editor is None: # last ditch, just use an uneditable field with the str() representation
      v = tk.StringVar(value=str(value))
      editor = ttk.Label(parent, textvariable=v, foreground="brown")
      #self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)
      self.vars[key+keyExt] = ChangeDescr(v, editor, False, str)

    return editor

  def makeNewEntry(self, k, v, row, disabled, keyExt):
    self.makeLabel(self.editorsListFrame, k, k+":", self.cLabel, row, foreground="grey" if disabled else "black")
    ed = self.makeEditor(self.editorsListFrame, k, v, self.cEdit, row, disabled or not self.attrs.isValueEditable(k), keyExt)
    frame = tk.Frame(self.editorsListFrame)
    frame.grid(column=self.cDel, row=row, sticky=tk.W, padx=0, pady=0)
    if not disabled:
      self.makeButton(frame, k, v, "delete", command=lambda b, k1=k, v1=v, ed1=ed, row=row: self.deleteAttr(k1, v1, ed1, row, b), width=4.2)
    kind = self.makeKind(self.editorsListFrame, k, v.typ, self.cKind, row, None, disabled or not self.attrs.isTypeEditable(k), keyExt)
    #TODO: isn't this redundant?
    if disabled or not self.attrs.isTypeEditable(k):
      kind.configure(state=tk.DISABLED)
    
  def makeTitle(self, col:int, text:str, helpText:str, row:int, **kwargs):
    longestLine = len(max(helpText.split("\n"), key=len))
    width = min(longestLine * 7, 560)
    # Note: background= option doesn't work on aqua
    label = ttk.Label(self.editorsListFrame, text=text, font=('Helvetica', 12, 'bold'), relief=tk.GROOVE, anchor=tk.CENTER, **kwargs)
    label.grid(column=col, row=row, sticky=tk.W+tk.E)
    CreateToolTip(label, helpText, background="yellow", wrapLength=width)

  def makeHeader(self, row, **kwargs):
    self.makeTitle(self.cLabel, "ATTR NAME", f'The name of the Attribute (NOT the value).', row, **kwargs)
    self.makeTitle(self.cEdit, "VALUE", f'The value of the Attribute.', row, **kwargs)
    self.makeTitle(self.cDel, "ACTIONS", f'The actions you can perform on the Attribute.', row, **kwargs)
    self.makeTitle(self.cKind, "TYPE", f'The type of the value.', row, **kwargs)
    
  def makeEditor(self, parent, key, item, column, row, disabled, keyExt):
    editor = self.getEditorForType(parent, key, item.typ, item.value, keyExt)
    editor.grid(column=column, row=row, sticky='EW', padx=0, pady=0)
    if disabled:
      self.conf(editor, state= "disabled")#, foreground="blue")
      if not isinstance(editor, ColorEditor): # This would blank out a ColorEditor's color swatch
        self.conf(editor, foreground="gray", background="gray95")
    return editor

  def makeButton(self, parent, key, item, text, command=None, **kwargs):#, width=4):
    '''
    Unlike the other "make*() methods, this one takes a parent that is a frame that
    will be used as a *pack()* frame as opposed to the others that take a parent
    that's a *grid()* frame.
    '''
    if item.typ == 'unknown':
      return
    button = ttk.Button(parent, text=text, padding=-15, **kwargs)
    button.pack(side=tk.LEFT, anchor=tk.W, padx=0, pady=0)
    if command: 
      button.config(command=lambda b=button: command(b))
    return button

  def makeLabel(self, parent, key, text, column, row, justify=tk.E, **kwargs):
    font = ('Helvetica', 14, 'bold italic') if key in SYS_ATTRIBUTES else ('Helvetica', 14, 'normal')
    label = ttk.Label(parent, text=text, font=font, **kwargs)
    label.grid(column=column, row=row, sticky=justify, ipadx=0, padx=0, pady=0)
    return label

  def makeKind(self, parent, key, typ:Union[type,str], column, row, command, disabled, keyExt, **kwargs):
    #typeDisabled = disabled
    command = None    
    if not disabled:
      command = command=lambda b, parent=self, key=key, typ=typ, column=self.cKind, row=row: \
                                self.editType(b, parent, key, typ, column, row)
    # else:
    #   typeDisabled = True      
    font = ('Helvetica', 8, 'bold') if typ=="unknown" else ('Helvetica', 8, 'normal')
    tname = getFullClassName(typ) if isinstance(typ, type) else str(typ)
    if disabled:
      label = ttk.Label(parent, text=tname, width=KIND_WIDTH, **kwargs)
    else:
      label = ttk.Button(parent, text=tname, padding=-15, width=KIND_WIDTH, **kwargs)
      if command is not None:
        label.config(command=lambda b=label: command(b))
    label.grid(column=column, row=row, padx=0, pady=0)#, sticky="sw")
    self.vars[key+keyExt].typeLabel = label
    return label
    
  def setStatus(self, parent, key, text, column, row, command=None, button=None, **kwargs):
    if button is not None:
      button.grid(column=column, row=row, padx=0, pady=0)#, sticky="sw")
    else:
      label = ttk.Label(parent, text=text, **kwargs)
      label.grid(column=column, row=row, padx=0, pady=0)#, sticky="sw")
      
    
  def setMessage(self, text, hideButton=True, **kwargs):
    self.messageFrame = tk.Frame(self)
    self.messageFrame.grid(column=0, row=self.rMessage, columnspan=2, sticky=tk.E+tk.W)
    self.messageFrame.columnconfigure(0, weight=1)
    self.messageFrame.columnconfigure(1, weight=0)
    self.messageWidget = tk.Text(self.messageFrame, height=1+text.count('\n'))
    self.messageWidget.insert('1.0', text)
    self.messageWidget.configure(state=tk.DISABLED, **kwargs)
    self.messageWidget.grid(column=0, row=0, sticky=tk.E+tk.W)
    if hideButton:
      tk.Button(self.messageFrame, bitmap="error", command=self.messageFrame.destroy)\
        .grid(column=1, row=0, sticky=tk.E+tk.W)
    
  def clearMessage(self, *args): # args are ignored: it's only here so we can call this an tk event.
    try:
      self.messageFrame.destroy()
    except:
      pass
    try:
      self.askWidget.destroy()
    except:
      pass
  
  def ask(self, question:str, handler:Callable[[tk.Event, str], Any], default=None, **kwargs):
    '''
    Asks a question and waits for an answer input within the window. The user
    is expected to fill in the answer and hit <Return> to answer.  If the focus
    is shifted to another widget, the question is removed (as if a "cancel"
    button was pressed.
    
    If the user hits return, *self.answer* will be called, and the user's input
    can be obtained using *self.var.get()*
    
    :param question: The text of the question.
    :param handler: A *Callable* taking an event argument and a string argument containing the answer
    :param kwargs: A dictionary of legal arguments to *ttk.Text()* which controls
        the attributes of the question Text widget.
    '''
    self.setMessage(question, hideButton=False, **kwargs)
    # Doesn't check anything, just clears the question (like a "cancel" button)
    # when the ask dialog looses focus
    checkWrapper = (self.winfo_toplevel().register(self.clearMessage), '%P')
    _var = tk.StringVar()
    if default is not None:
      if isinstance(default, type): default = default.__name__
      _var.set(str(default))
    self.askWidget = ttk.Entry(self, textvariable=_var, validate='focusout', validatecommand=checkWrapper)
    self.askWidget.grid(row=self.rEnter, column=0, columnspan=2, sticky=tk.W+tk.E)
    if default is not None:
      self.askWidget.icursor(len(default))
    def h(event):
      handler(event, _var.get())
      #self.clearMessage()
    self.askWidget.bind('<Return>', lambda event: h(event))
    self.askWidget.focus()
      
  def checkInt(self, newval):
    return re.match(r'^[0-9]*$', newval) is not None and len(newval) <= 20

  def checkFloat(self, newval):
    return re.match(r'^[0-9]*(\.[0-9]*)?$', newval) is not None and len(newval) <= 20

  # def colorChooser(self, tkVar, button):
  #   # askcolor() returns (rgb, hex)
  #   color = tkVar.get()
  #   if color is None:
  #     color = "black"
  #   if color == "": # colorchooser() can't handle "" (transparent)
  #     color = "gray"
  #   color = colorchooser.askcolor(initialcolor=color, parent=self)
  #   if color is not None:
  #     color = color[1]
  #     tkVar.set(color)
  #     button.config(highlightbackground=color, text=str(color))
    
  def conf(self, tkObj, **kwargs):
    '''
    Configure the tk widget *tkObj* with each of the key/value pairs in *kwargs*
    one at a time catching printing any exceptions but otherwise ignoring failures.
    '''
    for k,v in kwargs.items():
      if isinstance(tkObj, tk.Button) and k=="state" and v == "!disabled":  
        v = "normal"
      d = dict()
      d[k] = v
      try: 
        tkObj.config(**d)
      except: 
        if k not in ["foreground", "background", "bg", "fg"]:
          logger.warning(f'AttrEditor.show.conf(): Couldn\'t set attr "{k}" to "{v}" on tk type {type(tkObj).__name__}')

  # def isTypeEditable(self, key:str) -> bool:
  #   '''
  #   Returns *True* if the key is an editable. ie: The editor was not declared
  #   read only and the *AttributedObject* is editable on the *key* parameter.
  #   '''
  #   return  self.editable \
  #           and self.attrs.isTypeEditable(key) \
  #           and self.attrs.getType(key, asString=True) != "list"
                
class HierarchicalAttrEditor(AttrEditor):
  
  def __init__(self, parent, attrs:AttributedObject, title="Attribute Editor", disabled=False):
    super().__init__(parent, attrs, title=title, disabled=disabled)
    
    # "constants" for the columns in the Editors grid
    self.rowsPerEntry = 3 # from 1
    self.EntryOffset = 1 # from 0
    self.cStatus = 0
    self.cLabel = 1
    self.cEdit = 2
    self.cKind = 3
    self.cQuals = 4
    self.cDel = 5
    self.cspan = 6
    
    self.iEntryOffset = 0
    self.sepOffset = 2
  
  @override
  def makeNewEntry(self, k, v, row, disabled, keyExt):
    localRec = self.attrs.getLocalRecord(k)
    inhRec = self.attrs.getInhRecord(k)
    if self.editKey == k and localRec == None:
      self.attrs.setRecord(Attribute(k, typ=None if inhRec is None else inhRec.typ, value=None))
      localRec = self.attrs.getLocalRecord(k)
      #localRec = self.attrs.set[k] = Attribute(k, typ=None if inhRec is None else inhRec.typ)
    if localRec is not None:
      super().makeNewEntry(k, localRec, row+self.EntryOffset, disabled, keyExt="")
      self.makeQuals(self.editorsListFrame, k, localRec.qualifiers, self.cQuals, row+self.EntryOffset, disabled=disabled or not self.attrs.isQualifierEditable(k), keyExt="")
    if inhRec is not None:
      super().makeNewEntry(k, inhRec, row+self.iEntryOffset, disabled=True, keyExt=INHERIT_KEY_EXT)
      self.makeQuals(self.editorsListFrame, k, inhRec.qualifiers, self.cQuals, row+self.iEntryOffset, disabled=True, keyExt=INHERIT_KEY_EXT)
      # self.makeLabel(self.editorsListFrame, k, k+":",        self.cLabel, row+self.iEntryOffset, foreground="gray")
      # self.makeLabel(self.editorsListFrame, k, inhRec.value, self.cEdit,  row+self.iEntryOffset, justify=tk.W, foreground="gray")
      # self.makeKind (self.editorsListFrame, k, inhRec.typ,   self.cKind,  row+self.iEntryOffset, foreground="gray")
      self.setStatus(self.editorsListFrame, k, DOWN_ARROW,    self.cStatus,row+self.iEntryOffset, foreground="gray")
      if localRec is None:
        # action frame
        frame = tk.Frame(self.editorsListFrame)
        frame.grid(column=self.cDel, row=row+self.iEntryOffset, sticky=tk.E+tk.W, padx=0, pady=0)
        #attr =  Attribute(k, inhRec.typ, inhRec.value, None)
        #self.attrs.setRecord(attr)
        if not disabled:
          self.makeButton(frame, k, inhRec, "override", \
                          command=lambda b, k=k, inhRec=inhRec, r=row: (self.makeNewEntry(k, self.attrs.setRecord(Attribute(k, inhRec.typ, inhRec.value, None)), r, disabled=False, keyExt=""), b.destroy()))
    ttk.Separator(self.editorsListFrame, orient=tk.HORIZONTAL) \
        .grid(column=0, row=row+self.sepOffset, columnspan=self.cspan, sticky=tk.W+tk.E, padx=0, pady=2)
   
  @override
  def makeHeader(self, row, **kwargs):
    self.makeTitle(self.cStatus, "S", f'Status:\n  {DOWN_ARROW}: inherited record (not editable)', row, **kwargs)
    AttrEditor.makeHeader(self, row, **kwargs)
    self.makeTitle(self.cQuals, "QUALIFIERS", DOC_QUALIFIER, row, **kwargs)
    
  @override
  def makeQuals(self, parent, key, quals, column, row, disabled, keyExt, **kwargs):
    if quals is None:
      inhRec = self.attrs.getInhRecord(key)
      if inhRec is not None:
        quals = inhRec.qualifiers
    if quals is None:
      quals = AttributeFlags(AttributeFlags.NIL)
      
    # label = ("+f" if quals&AttributeFlags.FINAL                 else "") + \
    #         ("+if" if quals&AttributeFlags.INSTANCE_FINAL        else "") + \
    #         ("+vni" if quals&AttributeFlags.VALUE_NOT_INHERITABLE else "")
    # if len(label) == 0:
    #   label = "-"
    mb = tk.Menubutton(parent, text="=", padx=-15, **kwargs)
    def postLabelText() -> str:
      label = ("+f" if self.vars[key+keyExt].qualFinal.get()               else "") + \
            ("+if" if self.vars[key+keyExt].qualInstanceFinal.get()        else "") + \
            ("+vni" if self.vars[key+keyExt].qualValueNotInheritable.get() else "")
      if len(label) == 0:
        label = "-"
      mb.config(text=label)
      return label
    menu = tk.Menu(mb)
    state = tk.DISABLED if disabled else tk.NORMAL
    self.vars[key+keyExt].qualFinal = tk.BooleanVar(value=bool(quals&AttributeFlags.FINAL))
    menu.add_checkbutton(label="final", variable=self.vars[key+keyExt].qualFinal, command=postLabelText, state=state)
    self.vars[key+keyExt].qualInstanceFinal = tk.BooleanVar(value=bool(quals&AttributeFlags.INSTANCE_FINAL))
    menu.add_checkbutton(label="instance final", variable=self.vars[key+keyExt].qualInstanceFinal, command=postLabelText, state=state)
    self.vars[key+keyExt].qualValueNotInheritable = tk.BooleanVar(value=bool(quals&AttributeFlags.VALUE_NOT_INHERITABLE))
    menu.add_checkbutton(label="value not inheritable", variable=self.vars[key+keyExt].qualValueNotInheritable, command=postLabelText, state=state)
    mb.config(menu=menu, text=postLabelText())
    mb.grid(column=column, row=row, sticky=tk.E)
    if disabled:
      mb.config(foreground="gray")
    
  @override
  def hasChanged(self, k:str)->bool:
    if AttrEditor.hasChanged(self, k):
      return True
    origAttr:Attribute = self.attrs._attrs[k] if k in list(self.attrs.keys()) else None
    if origAttr is None:
      return True
    # origQual:AttributeFlags = origAttr.qualifiers
    # if origQual is None:
    #   origQual = AttributeFlags.NIL
    v = self.vars[k]
    return  v.qualFinal is not None and v.qualFinal.get() != origAttr.isFinal() or \
            v.qualInstanceFinal is not None and v.qualInstanceFinal.get() != origAttr.isInstanceFinal() or \
            v.qualValueNotInherited is not None and v.qualValueNotInherited.get() != origAttr.isValueNotInheritable()
    
  @override
  def _saveKey(self, k:str, origAttr:Attribute):
    AttrEditor._saveKey(self, k, origAttr)
    v = self.vars[k]
    self.updatedKeys[k].qualifiers = AttributeFlags(
              (AttributeFlags.FINAL if v.qualFinal is not None and v.qualFinal.get() else AttributeFlags.NIL) |
              (AttributeFlags.INSTANCE_FINAL if v.qualInstanceFinal is not None and v.qualInstanceFinal.get() else AttributeFlags.NIL) |
              (AttributeFlags.VALUE_NOT_INHERITABLE if v.qualValueNotInherited is not None and v.qualValueNotInheritable.get() else AttributeFlags.NIL))

if __name__ == "__main__":
  root = tk.Tk()
  top2 = tk.Toplevel(root)
  def onClosing():
    root.destroy()
  root.protocol("WM_DELETE_WINDOW", onClosing)
  root.createcommand('::tk::mac::Quit', onClosing)
  def edit(parent, attrs):
    command = getEditedAttrsCommandObj(parent, attrs)
    if command is None:
      print("cancelled")
    else:
      command.do()
      print(repr(attrs))
  but = tk.Button(root, text="show edit window", command=lambda parent=root, attrs=tygra.tygraPrefs: edit(parent, attrs))
  but.pack()

  root.mainloop()