
Editing
=======

Making objects
--------------

From the background menu, **model**:

- **new instance of Node** / **new subtype of Node** -- a new individual, or a
  new type, directly under *node*;
- **new instance of Relation** / **new subtype of Relation** -- likewise for
  relations (a new relation type is a new kind of relation, eg: *likes*).

From an object's menu: **make new instance** and **make new subtype** make an
individual of that type, or a subtype of it.

You're asked for the new object's name. (A variable's name can carry its
constraints: see :doc:`contexts`.)

Making relations
----------------

Right-click the source, and choose **make relation to...**: its submenu lists
the relation types you can use, the system model's and any other models' in
submenus of their own. Then a line follows the mouse from the source: click
the destination. Clicking empty space makes a relation with no destination of
its own (it's drawn to its type's range, faded, or left dangling). **Esc**
abandons it.

Relations can connect nodes and relations in any combination -- except *isa*,
which must be between two nodes or two relations.

To change a relation's source or destination, drag its end (the cursor
changes over it) onto another object; its menu also has **reset src** and
**reset dst**.

Selecting, moving and resizing
------------------------------

- **Click** an object to select it (**Shift**- or **Cmd**-click to add to the
  selection); click again to deselect.
- **Option**-click an object to select it together with the relations to and
  from it. **Option-Cmd**- or **Option-Shift**-click does the same, but keeps
  the rest of the selection: it adds the object and its relations, or, if the
  object's already selected, takes them out.
- **Cmd-A** (**Edit | Select All**) selects everything shown (not what's
  hidden, or in a collapsed window). In the terminal pane it selects the text.
- **Drag** to move it -- or, if it's selected, everything selected. When you
  drop it, it's nudged off anything it landed on.
- A selected object has handles at its corners: drag one to **resize** it.
  **fit to text** (in its menu) undoes manual sizing.
- A relation's label normally sits midway between its ends (*floating*);
  dragging it pins it where you put it. **floating** in its menu (or **view |
  float all relations**) puts it back between its ends. A relation *type*
  doesn't float: it has a place of its own, as a node does (a new one starts
  out between its ends -- its domain and range -- and stays there).

Attributes
----------

**edit attributes** (in an object's menu), or **double-clicking** the object,
opens the attribute editor: one row per attribute, with its value, type and
inheritance rules, and the values it inherits shown above it in grey. You can add attributes, change their values
and types, and delete them. Hover over a row's name for its description. A
value the reasoner inferred is greyed out too, marked **I** in the status
column: its **assert** button (then **Save Changes**) makes it an ordinary
value (see :doc:`reasoning`). **Return** saves the changes (as **Save
Changes**), and **Escape** cancels them. **Add New Attribute** asks for the
new attribute's name: **Return** or **Tab** adds it, and puts you in its value.

.. figure:: ../images/user/attribute-editor.png
   :alt: The attribute editor, on the variable ?b: its constraints, its own name (with the name it would inherit, in grey, above), and -- grouped under vis -- the look it inherits from person
   :width: 560px

   The attribute editor, on the variable ?b: its constraints, its own name (with the name it would inherit, in grey, above), and -- grouped under *vis* -- the look it inherits from *person*: its colour and shape.

Removing things
---------------

An object's menu has two kinds of removal:

- **erase from view** (or the **Delete** key): just stop showing it in this
  view (the model keeps it).
- **remove from model** (or **Shift-Delete**, which asks first): delete it
  from the model -- and so from every view of it.

If the object is one of several selected, they act on all of them (the menu
says how many); the keys act on what's selected. What can't be removed here
-- what the reasoner inferred, system objects, and objects of another model
-- is left (with a message). Both can be undone, all at once.

Cut, copy and paste
-------------------

**Cmd-C** (**Edit | Copy**, or **copy** in an object's menu) copies what's
selected; **Cmd-X** (**cut**) copies it and deletes it from the model;
**Cmd-V** (**Edit | Paste**) pastes it, and **model | paste here** pastes it
where you clicked.

A view can't show an object twice, so copying is done in the *model*: pasting
makes **new** objects, copies of the ones you copied -- and they show in every
view of the model, as any new object does. In the window you paste in, they're
drawn as the originals were: the same sizes and layout, back where they were
(if that's clear -- eg: they were cut) or else beside them. They're left
selected, so you can drag them away at once. Paste again for another copy.

What's copied:

- the objects themselves, with their own attributes (not the ones they
  inherit), as they were when you copied them;
- everything a context (a rule, query, definition, ...) contains: copying a
  rule copies its antecedent and consequent too;
- each object's types (its isa links).

A copied relation whose end wasn't copied relates the same object, and a copy
of something whose type wasn't copied is another of that type. So copying a
couple of *has-brother* rules, pasting them, and changing the pasted relations
to *has-sister* (eg: with **reset dst** on their isa links) leaves the
originals as they were.

Since a copy refers to the objects around it (its types, and the ends of its
relations), you can paste into another model only if it builds on the one you
copied from (see **Edit | Model preferences...**): otherwise the paste is refused,
with a message. What the reasoner inferred isn't copied (mark it as asserted
first).

Cut and paste can be undone. In the terminal pane, **Cmd-C** and **Cmd-V**
copy and paste text, as usual.

**Shift-Cmd-C** (**Edit | Copy as picture**, or **copy as picture** in an
object's menu) copies a *picture* of what's selected instead -- with what any
selected context windows contain, and the relations between the selected
objects -- to paste into another program: eg: a rule into Messages, or into
Preview (**File | New from Clipboard**). It's drawn as it is on the canvas
(without the selection handles), at twice the size, so it's sharp on a Retina
screen.

Validation
----------

**model | validate** (or **validate** on an object) checks the model's
consistency. Objects with problems get a red **E** marker: hover over it for
the problems, or choose **show error report** from the object's menu.
