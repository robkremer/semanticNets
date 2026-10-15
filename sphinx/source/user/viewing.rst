
Viewing
=======

A view shows as much or as little of its model as you like, and remembers how
it's arranged. Nothing here changes the model.

What's shown
------------

- **view | show | all** brings every object of the model into the view.
- **view | show | relations...** asks which relation types to show (each
  includes its subtypes): their relations between the nodes in the view
  are brought in -- and, if you tick it, the nodes at their other ends.
- **view | show | nodes...** asks which node types to show: their
  individuals (and their subtypes') are brought in, with -- unless you
  untick it -- their relations to what's shown, and to each other.
- **view | show | node** lists the model's objects that aren't in the view:
  choose one to bring it in.
- **expand all** (on an object's menu; it says how many relations the object
  has) brings in everything related to it, 1 to 4 levels out.
- **expand by relation...** asks which relations to follow: each type the
  object's relations are, each way round -- *has-mother →* (its mother) or
  *← has-mother* (its children) -- with how many there are; a type includes its
  subtypes (*has-parent →* takes *has-father* and *has-mother* too). Or all
  relations, all outgoing, or all incoming (which, at every level, follow
  any relation that way). And how many **levels** out to go. Relations in a
  hidden or erased category (eg: isa links) are listed too, greyed and
  marked *hidden*: ticked, they -- and what they lead to -- are shown anyway
  (undo hides them again). "All" leaves them hidden.
- **erase from view** (on an object's menu, or the **Delete** key) takes it
  out of the view.
- **erase everything else** (on an object's menu) takes everything *but* it
  -- or, if it's selected, but the selection -- out of the view: eg: to look
  at one corner of a big model, then **expand** from there. (It keeps what
  they need, too: the relations between them, the ends of their relations,
  and the windows they're in.)

All of these are one command each: **Cmd-Z** takes back what they brought in,
or puts back what they erased.

Hiding and erasing by category
------------------------------

**view | hide by category** and **view | erase by category** each list the
categories of objects:

==========================  ====================================================
category                    is
==========================  ====================================================
system objects              the system model's objects (*top*, *node*, *isa*, ...)
isa individuals             the *isa* links themselves
higher-order isa relations  the *isa* links from individual relations to their
                            relation types (eg: from *alice -has-parent-> bob*
                            to *has-parent*)
types                       all types
non-local                   objects from other models
rules                       rules
queries                     queries
constraints                 constraints
inferred objects            what the reasoner inferred (see :doc:`reasoning`)
==========================  ====================================================

Each menu also has **relation types...**, which asks which relation types to
hide (or erase): their relations, and their subtypes', are hidden like a
category -- eg: *has-sibling*, to see a family tree's lines of descent by
themselves.

Checking a category in the **hide** menu stops drawing those objects (they
stay in the view, with their positions); in the **erase** menu, takes them
out of the view. Unchecking it shows them again. Relations to or from hidden
objects are hidden too. Either way, **expand** won't bring more of them in.
The settings are saved with the view.

Hiding is *soft*: it applies to what's there when you check the category. An
object you make (or ask for, with **show node**) that's in a hidden category
is shown anyway, and a message in the terminal says so. To hide it too,
uncheck and re-check the category. (What the reasoner infers isn't
something you made: with *inferred objects* hidden, reasoning again adds
them hidden; erased, it doesn't add them to the view at all.)

Arranging
---------

- **Drag** objects to where you want them (see :doc:`editing`).
- **view | layout**: let the program arrange things, once or as the view
  changes -- as trees, balloons, round hubs, or with the animation layout.
  See :doc:`layouts` and :doc:`animation`.
- **view | float all relations** puts every relation's label back midway
  between its ends.

Zooming and scrolling
---------------------

**view | Zoom** (or the keys) zooms about the middle of the window:

==============  ======================================
key             zooms
==============  ======================================
**Cmd-+**       in
**Cmd--**       out
**Cmd-0**       to normal size
**Cmd-9**       to fit: everything shown, in the window
==============  ======================================

The menu also has fixed sizes (eg: 50%). The canvas scrolls with the
scroll wheel or trackpad (**Shift** for sideways); **view | reset scroll
region** fits the scrollable area to the drawing. A view saves its zoom and
where it was scrolled to.

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
``vis/titlebarColor``       a context window's title bar (rules, queries
                            and definitions each have their own)
``vis/label``               what its label says (below)
``vis/tooltip``             what its tooltip says (below)
``vis/tooltipFont``         its tooltip's font (eg: ``TkFixedFont``, for code)
``vis/tooltipWrap``         the width its tooltip wraps at, in pixels
                            (0: no wrapping)
==========================  =============================================

Labels
------

What an object's label says is set by a **template**: text with
substitutions, in the style of the shell's:

========================  =====================================================
in a template             gives
========================  =====================================================
``$key``, ``${key}``      the value of *key*
``${key:+text}``          *text* if *key* has a value, else nothing
``${key:-text}``          *key*'s value, or *text* if it has none
``$$``                    a ``$``
``\n``                    a line break
``$(module:function)``    what a *hook* returns: a function, provided by a
                          program that made the model (eg: an object's source
                          code); ``${(module:function):+text}`` likewise
========================  =====================================================

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

Tooltips are templates too: the object's ``vis/tooltip`` attribute, or else the
``gui/tooltip`` setting -- by default, the name, and then the note if there is
one. A tooltip longer than the ``gui/tooltipMaxLines`` setting (40 lines) is cut
short.
