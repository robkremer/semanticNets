
Viewing
=======

A view shows as much or as little of its model as you like, and remembers how
it's arranged. Nothing here changes the model.

What's shown
------------

- **view | show all** brings every object of the model into the view.
- **view | show node** lists the model's objects that aren't in the view:
  choose one to bring it in.
- **expand** (on an object's menu) brings in the objects related to it, to 1
  to 4 levels out.
- **erase from view** (on an object's menu) takes it out of the view.

Hiding and erasing by category
------------------------------

**view | hide by category** and **view | erase by category** each list the
categories of objects:

==================  ====================================================
category            is
==================  ====================================================
system objects      the system model's objects (*top*, *node*, *isa*, ...)
isa individuals     the *isa* links themselves
types               all types
non-local           objects from other models
rules               rules
queries             queries
==================  ====================================================

Checking a category in the **hide** menu stops drawing those objects (they
stay in the view, with their positions); in the **erase** menu, takes them
out of the view. Unchecking it shows them again. Relations to or from hidden
objects are hidden too. Either way, **expand** won't bring more of them in.
The settings are saved with the view.

Hiding is *soft*: it applies to what's there when you check the category. An
object you make (or ask for, with **show node**) that's in a hidden category
is shown anyway, and a message in the terminal says so. To hide it too,
uncheck and re-check the category.

Arranging
---------

- **Drag** objects to where you want them (see :doc:`editing`).
- **view | animation layout** (or the **animation toolbar**): let the
  program arrange things. See :doc:`animation`.
- **view | gather nodes** pulls objects that have strayed far from the rest
  back toward them.
- **view | float all relations** puts every relation's label back midway
  between its ends.
- **view | Zoom**: zoom in and out, or to a fixed size. The canvas scrolls
  with the scroll wheel (**Shift** for sideways); **view | reset scroll
  region** fits the scrollable area to the drawing.

Markers
-------

Small tags at an object's top left corner tell you about it. Hover over one
for details.

========  ==============================================================
marker    means
========  ==============================================================
**E**     (red) the object has problems: from validation or reasoning
**S**     a system object
**T**     a type
**R**     a remote object: from another model
**{}**    a variable with constraints; **{!}** (red) if they can't be read
========  ==============================================================

The **S**, **T**, **R** and **{}** markers can be turned off in the settings
(``gui/showSystemTags``, ``gui/showTypeTags``, ``gui/showRemoteTags``,
``gui/showConstraintMarker``).

How things are drawn
--------------------

An object's look comes from its attributes whose names start with ``vis/``
-- and since attributes are inherited, setting one on a type changes all of
its instances:

==========================  =============================================
attribute                   controls
==========================  =============================================
``vis/shape``               a node's shape
``vis/fillColor``           its fill colour
``vis/borderColor``,        its border
``vis/borderWidth``,
``vis/borderSmooth``
``vis/textColor``           its text
``vis/shadowColor``         a type's shadow
``vis/lineColor``,          a relation's line
``vis/lineWidth``,
``vis/lineType``
``vis/minSize``,            its size limits, and the shape of its box
``vis/maxSize``,
``vis/aspectRatio``
``vis/label``               what its label says (below)
==========================  =============================================

Labels
------

What an object's label says is set by a **template**: text with
substitutions, in the style of the shell's:

====================  =================================================
in a template         gives
====================  =================================================
``$key``, ``${key}``  the value of *key*
``${key:+text}``      *text* if *key* has a value, else nothing
``${key:-text}``      *key*'s value, or *text* if it has none
``$$``                a ``$``
``\n``                a line break
====================  =================================================

*text* can contain substitutions itself. A *key* is any of the object's
attributes, or one of:

===============  ==================================================
key              is
===============  ==================================================
``name``         its name
``localName``    its name, only if it has its own (not inherited)
``type``         the names of its types, separated by commas
``constraints``  a variable's constraints
``id``           its id
===============  ==================================================

The default is ``$name${constraints:+ {$constraints}}`` -- the name, then the
constraints in braces if there are any. ``$type${name:+: $name}`` gives the
"type: name" style of conceptual graphs (*person: fred*).

The template is the object's ``vis/label`` attribute, if it has one (set it
on a type for all its instances); otherwise the ``gui/label`` setting
(``gui/relationLabel`` for relations).
