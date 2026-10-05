
Files and Settings
==================

Models and views
----------------

A **model** (``.snm``) holds the network itself: its objects, their
attributes and relations, and its rules, definitions and queries. A **view**
(``.snv``) holds one way of looking at a model: which objects are shown,
where, how big, what's hidden, and the animation layout's settings. A view
refers to its model, and a model to the models it builds on (always including
the system model, *sn*), so opening a view opens its model, and the model
opens the models it uses.

A model's **super-models** are the models it builds on: their contents are
used as though they were its own -- the reasoner reasons over them too, and
their rules apply -- though they aren't changed through it. The system model
is always one. The terminal's ``super models`` command lists them, and adds
(``--add file``) or removes (``--remove file``) one; they're saved with the
model, relative to its file where they're near it. A super-model that can't be
found when the model is opened is reported, and kept in the list for when it's
there again.

- **File | Open...** opens a view -- or a model, with a default view of it.
- **File | New...** makes a new view, of a new or existing model.
- **File | Save view** saves the window's view.
- **File | Save model** saves the window's model.
- **File | Save view as...** and **File | Save model as...** save a *copy* in
  another file. The window stays on the original (the terminal pane says so),
  and further changes go to the original: open the copy to work on it.
- **File | Close model** closes every window on the window's model (offering
  to save each changed view, and then the model), and forgets the model: open
  it again and it's read afresh from its file. (A model that another open
  model builds on can't be closed: models stay in memory until you quit.)
- Modified models (and views) are offered for saving when you quit: you're
  asked about each one. **File | Save model** (or the terminal's ``save``
  command) saves a model at any time.

Copying and moving files
------------------------

Files refer to one another by **relative** paths when they're in the same
folder, below it, or up to two folders above it -- so a folder of models and
views can be copied or moved as a block, and its files still find one
another. References further afield are kept as full paths.

A file copied *on its own* still finds what it referred to: if the file it
refers to isn't next to the copy, it's looked for where the original was.
Each file also records where it was last saved, and where it was before
that; when you open a copy, the program notices it has moved and says so.

File format
-----------

Files are XML. The current format is compact (simple values are written as
attributes, references to other objects by id); older files, in the original
more verbose XML format, are still read, and are written in the new format
the next time they're saved. Because they're XML, they're readable, and can
be compared or merged with ordinary tools -- but edit them by hand only with
care.

Settings
--------

**Settings...** (in the application menu) shows the
program's settings, and lets you change them. They're kept in ``~/.sn.xml``.
Among them:

===============================================  ==========================================
setting                                          controls
===============================================  ==========================================
``gui/label``                                    the default label template for nodes
                                                 (see :doc:`viewing`)
``gui/relationLabel``                            the default label template for relations
``gui/showSystemTags``,                          whether to show the **S**, **T**, **R** and
``gui/showTypeTags``,                            **{}** markers
``gui/showRemoteTags``,
``gui/showConstraintMarker``
``gui/shadowTypes``                              whether types are drawn with a shadow
``gui/NodeMinSize``,                             the default size and shape of a node
``gui/NodeAspectRatio``
``gui/highlightColor``                           the colour of highlights (eg: a query's
                                                 answers)
``gui/backgroundColor``                          the canvas's colour
``gui/allowEditingSystemObjects``                whether the system model's objects can be
                                                 edited (best left off)
``gui/optimization/aggressiveLabelPlacement``    how hard to look for a free spot for a
                                                 relation's label when placing it: 0 (not
                                                 at all) to 10 (furthest; slow in a crowded
                                                 view, as when showing a big model)
``loggingLevel``                                 how much detail the program's messages go
                                                 into
===============================================  ==========================================

Hover over a setting's name for its description.
