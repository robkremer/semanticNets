
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
is always one, and comes first. Set them in **Edit | Model preferences...**
(*superModels*: **Add file...** chooses a model file, **Add URL...** takes the
URL of one -- eg: an ontology on the web, which is read-only here -- and the
arrows set the order
-- a name that could mean objects in more than one model is looked up in the
first first), or with the terminal's ``super models`` command (``--add file``,
``--remove file``). They're saved with the model, relative to its file where
they're near it. A super-model that can't be
found when the model is opened is reported, and kept in the list for when it's
there again.

- **File | Open...** opens a view -- or a model, with a default view of it.
- **File | Open URL...** does the same for one at a URL, eg: on the web
  (``https://...``). It's checked before it's taken; recent URLs are offered.
  A model or view on the web is read-only: it can't be saved there, but
  **Save view as...** and **Save model as...** save a copy.
- **File | Open Recent** lists the views you've opened most recently, newest
  first (how many: the ``gui/recentFiles`` setting, 10 to start with). One
  that was never saved opens as its model's default view; one that's gone is
  taken off the list. **Clear Menu** empties it.
- **File | Open super model** opens a window on one of the window's model's
  super-models (they're listed): its view -- the file next to it with the
  same name, ending ".snv" -- or, if there isn't one, a new view that will be
  saved there. The base rules' view is next to the file they come with; the
  system model, sn, has no file, so its view is taken to be there too
  (``sn.snv``). Both are read-only.
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

The model directory
-------------------

**Window | Model Directory** shows the models and views in the folders it
searches: each model (shaded) with its views under it, with how many objects
they have, their size, their location (the URL of their folder), and when they
were last changed and created. The number of objects is at most that many: as
many as have ever been made in it (fewer if some have been deleted -- only
reading the whole file would tell). Select one to see its full URL. It's the app's main window: it's shown when
the app starts with nothing to open, and while it's showing, closing the last
other window doesn't quit (closing it then does).

- **Open** (or double-click) opens a view, or a model in its default view.
- **Open Read-only** opens it with its model write-locked: it can't be changed
  or saved (the pencil at the right of the reasoning toolbar is crossed out).
  Not if the model's open already: it's opened as it is then.
- **Move to Trash** moves a model or view to the Trash (the Finder's **Put
  Back** restores it) -- and, for a model, its views too, if you say so.
  Nothing that's open is moved: close it first.
- **Folders...** sets the folders searched, one per line: a path or a
  ``file:`` URL. End a folder with ``/**`` to search the folders below it, too.
  A line can also be the URL of a model or view elsewhere, eg:
  ``https://example.org/ontologies/animals.snm`` (a folder on the web can't be
  looked through). The folders of the models and views you open, make or save
  are added by themselves. (The ``gui/directoryPath`` setting holds them,
  separated by ``;``.) **Rescan** looks through them again.

Only the start of each file is read, so even a large folder of large models is
listed quickly -- and only the start of a remote one is fetched. A model that a
listed view uses, in a folder that isn't searched (or on the web), is listed too
(in grey). Remote models and views open read-only: they can't be saved there,
nor moved to the Trash.

While a model or view is being opened -- and its window drawn -- a progress bar
at the bottom of the directory says how far it's got. (If the directory's
hidden, it's shown for an open that takes more than half a second, and hidden
again afterwards.)

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
``gui/recentFiles``                              how many views **File | Open Recent** lists
``gui/directoryPath``                            the folders the model directory searches
``gui/NodeMinSize``,                             the default size and shape of a node
``gui/NodeAspectRatio``
``gui/highlightColor``                           the colour of highlights (eg: a query's
                                                 answers, and the query)
``gui/highlightColorNegative``                   the colour of a query that has no
                                                 answers
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
