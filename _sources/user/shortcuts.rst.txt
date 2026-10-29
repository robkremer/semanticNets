Keys and mouse
==============

Every key shortcut and mouse gesture in *Semantic Nets*, in one place. (Help
| **Keys and Mouse** opens this page.) On Windows and Linux, **Cmd** is
**Ctrl** and **Option** is **Alt**, as the second column shows.

The keys in a view work while the mouse is over its drawing (the canvas takes
the keyboard when the mouse comes into it); in the terminal pane, the usual
text keys work instead.

Editing
-------

=======================  =======================  ===========================================================
Mac                      Windows and Linux        does
=======================  =======================  ===========================================================
**Cmd-Z**                **Ctrl+Z**               undo (each window has its own history: see :doc:`terminal`)
**Shift-Cmd-Z**          **Shift+Ctrl+Z**         redo
**Cmd-X**                **Ctrl+X**               cut: copy what's selected, and delete it from the model
**Cmd-C**                **Ctrl+C**               copy what's selected
**Cmd-V**                **Ctrl+V**               paste
**Shift-Cmd-C**          **Shift+Ctrl+C**         copy as picture: the selection, or the whole view
**Cmd-A**                **Ctrl+A**               select everything shown
**Delete**               **Backspace**, **Del**   erase what's selected from the view (the model keeps it)
**Shift-Delete**         **Shift+Del**            remove what's selected from the model (after asking)
**Option-V**             **Alt+V**                validate the model (**model | validate**)
**Esc**                  **Esc**                  abandon a relation being made (the line following the
                                                  mouse); otherwise, clear the highlights
=======================  =======================  ===========================================================

(The Mac's **delete** key is the one Tk calls *BackSpace*; **fn-delete**,
forward delete, works too.) See :doc:`editing`.

Viewing
-------

=======================  =======================  ===========================================================
Mac                      Windows and Linux        does
=======================  =======================  ===========================================================
**Cmd-F**                **Ctrl+F**               find objects by name (**Edit | Find...**: see :doc:`viewing`)
**Cmd-+**                **Ctrl++**               zoom in (**Cmd-=** too, unshifted)
**Cmd--**                **Ctrl+-**               zoom out
**Cmd-0**                **Ctrl+0**               normal size
**Cmd-9**                **Ctrl+9**               zoom to fit: everything shown, in the window
**Cmd-R**                **Ctrl+R**               repaint the view
=======================  =======================  ===========================================================

The program
-----------

=======================  =======================  ===========================================================
Mac                      Windows and Linux        does
=======================  =======================  ===========================================================
**Cmd-,**                **Ctrl+,**               settings (on the Mac, in the **Semantic Nets** menu;
                                                  elsewhere, **File | Settings...**)
**Cmd-Q**                **Ctrl+Q**               quit (offering to save what's changed)
**Cmd-?**                                         the User Guide (the Mac's **Help | Semantic Nets Help**)
=======================  =======================  ===========================================================

The mouse in a view
-------------------

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Mac
     - Windows and Linux
     - does
   * - click an object
     - click an object
     - select it (again: deselect it)
   * - **Shift**- or **Cmd**-click
     - **Shift**- or **Ctrl**-click
     - add the object to the selection, or take it out
   * - **Option**-click an object
     - **Alt**-click an object
     - select it and the relations to and from it
   * - **Option-Cmd**- or **Option-Shift**-click
     - **Alt+Ctrl**- or **Alt+Shift**-click
     - the same, keeping the rest of the selection (if it's selected: take it and them out)
   * - drag an object
     - drag an object
     - move it -- or, if it's selected, everything selected
   * - drag on the background
     - drag on the background
     - select what's in the box
   * - drag a selected object's corner
     - drag a selected object's corner
     - resize it
   * - drag a relation's end
     - drag a relation's end
     - connect it to another object (the cursor changes over the end)
   * - double-click an object
     - double-click an object
     - edit its attributes (or what its type's double-click does: see :doc:`exampleApps`)
   * - click a window's triangle
     - click a window's triangle
     - collapse or expand the context window (see :doc:`contexts`)
   * - right-click, two-finger click or **Control**-click
     - right-click
     - the menu: an object's own, or the background's
   * - **Cmd**-drag (anywhere)
     - **Ctrl**-drag (anywhere)
     - pan the view; objects stay put
   * - **Shift**-drag on the background
     - **Shift**-drag on the background
     - pan the view
   * - **Option**-drag (anywhere)
     - **Alt**-drag (anywhere)
     - zoom about where it was pressed: up to zoom in, down to zoom out
   * - scroll, two-finger drag
     - scroll wheel
     - scroll up and down
   * - **Shift**-scroll
     - **Shift**-scroll
     - scroll sideways
   * - hover over an object
     - hover over an object
     - after a second, its tooltip

While making a relation (after **make relation to...**, or dragging a
relation's end), a line follows the mouse: click the object to connect it to;
click empty space to leave that end empty (not for *isa*); **Esc** abandons
it.

The terminal pane
-----------------

=======================  =======================  ===========================================================
Mac                      Windows and Linux        does
=======================  =======================  ===========================================================
**Return**               **Enter**                run the command typed (or answer the question asked)
**Up**, **Down**         **Up**, **Down**         step back and forth through the commands typed before
**Control-D**            **Ctrl+D**               end of input, for a question being asked
**Cmd-C**, **Cmd-V**     **Ctrl+C**, **Ctrl+V**   copy and paste text
**Cmd-A**                **Ctrl+A**               select all the text
=======================  =======================  ===========================================================

See :doc:`terminal`.

Dialogs
-------

- **Return** (or **Enter**) presses the default button (eg: **OK**, **Find**,
  **Save Changes**), and **Esc** cancels or closes. **Cmd-W** (**Ctrl+W**)
  closes the find dialog and the source window too.
- In the attribute editor, **double-click** an attribute to edit it; when it
  asks for a new attribute's name, **Return** or **Tab** goes on to its value.
- In the model directory (**Window | Model Directory**), **double-click** or
  **Return** opens what's selected.
- In a list of choices (eg: choosing a model), **double-click** chooses.
- In the Python parser's list of files, **Delete** (**Backspace**) takes the
  selected ones out.
