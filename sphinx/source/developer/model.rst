
The Model
=========

The model package, :py:mod:`sn.model`, is the data and its meaning. It has
no user interface, and can be used (and is tested) on its own.

Objects
-------

.. inheritance-diagram:: sn.model.model.Node sn.model.model.Collection sn.model.model.IsaIndividual sn.model.TopModel
   :parts: 1

:py:class:`~sn.model.model.GraphObject`
  Anything in a model. It's a type or an individual
  (:py:meth:`~sn.model.model.GraphObject.isIndividual`), has a name, and has
  attributes (below). Its types -- its *parents* -- are given by its outgoing
  *isa* relations (:py:meth:`~sn.model.model.GraphObject.getParents`), and
  :py:meth:`~sn.model.model.GraphObject.isa` answers whether it's of a type,
  directly or not.

:py:class:`~sn.model.model.Node`
  A node.

:py:class:`~sn.model.model.Relation`
  A relation: a GraphObject with a source and a destination, so relations
  can relate relations. A relation's ends may be set locally
  (:py:attr:`~sn.model.model.Relation.localSrc`) or inherited from its type
  (:py:attr:`~sn.model.model.Relation.src`, ``dst``); for a relation *type*,
  the ends are its signature (:py:attr:`~sn.model.model.Relation.domain`,
  ``range``).

:py:class:`~sn.model.model.IsaIndividual`
  An *isa* link. These are relations like any other -- so they can be
  drawn, selected and deleted -- and are what makes an object's types.

:py:class:`~sn.model.model.Collection`
  A node with members (not currently offered in the GUI).

The graph structure (objects, incoming and outgoing relations) comes from
pythonUtils' :py:mod:`util.abstractGraph`.

Models
------

A :py:class:`~sn.model.model.Model` holds GraphObjects, and is saved in a
file. A model builds on other models -- its *super-models*, at least the
system model -- and can use their objects (as types, or as ends of
relations); a reference to another model's object carries that model's URL.

The **system model**, :py:class:`~sn.model.TopModel` (``sn:///sn``), is made
in memory at start-up and is write-locked. It defines the objects everything
else depends on, and the code refers to them by attribute (``model.ISA``,
``model.RULE``, ...):

.. graphviz::

   digraph top {
     rankdir=BT;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];
     edge [arrowhead=empty];
     top; node_ [label="node"]; relation; isa;
     context; rule; query; definition;
     contains; antecedent; consequent; definiendum; definiens; distinct;
     node_ -> top; relation -> top; isa -> relation;
     context -> node_; rule -> context; query -> context; definition -> context;
     contains -> relation; distinct -> relation;
     antecedent -> contains; consequent -> contains;
     definiendum -> contains; definiens -> contains;
   }

Attributes
----------

Objects have attributes through
:py:class:`~sn.model.snAttribute.SNAttributedObject`, built on pythonUtils'
:py:mod:`util.attribute`. An attribute has a type and a value, and a
:py:class:`~util.attribute.Restriction` on how it's inherited (eg:
*NOINHERIT*: subtypes and instances must fill it in themselves;
*NOOVERRIDE*: they may not change it). An object's *effective* value of an
attribute is its own, or the one it inherits down its isa links.

Attributes are used for:

- the object's own data (``name``, ``note``, anything the user adds);
- the relational properties, as boolean tags on relation types (``symmetric``,
  ``transitive``, ...), which are deliberately *not* inherited;
- a variable's ``constraints`` (below);
- how it's drawn: the ``vis/`` attributes, read by the view (see
  :doc:`view`). These are inherited, so a type sets them for its instances.

Patterns: variables, contexts and constraints
---------------------------------------------

An object whose name starts with ``?`` is a **variable**. A relation
contained by a context (the destination of a relation that isa *contains*:
eg: *antecedent*) is part of a pattern, as is any relation with a variable at
either end. :py:meth:`~sn.model.model.GraphObject.isPatternElement` says
whether an object is part of a pattern; if so, it describes the pattern, not
the world, so the reasoner doesn't take it as a fact, and
``getRelatedTo()`` and the like leave it out.

A variable's **constraints** are the text of its ``constraints`` attribute
(eg: ``alive, age: 30, owner: ?o``). :py:mod:`sn.model.constraints` parses
it (:py:func:`~sn.model.constraints.parseConstraints`), formats it back
(:py:func:`~sn.model.constraints.formatConstraints`), splits it from a name
typed with ``:where:`` (:py:func:`~sn.model.constraints.splitWhere`) and
merges edits into it (:py:func:`~sn.model.constraints.mergeConstraints`). A
text attribute -- rather than, say, one attribute per constraint -- keeps
the constraints in one place to edit, and away from the variable's own
attributes (a variable ``?p`` with a constraint ``age: 30`` doesn't *have*
an age; it matches things that do). Older models, which stored constraints
as attributes of their own, are converted when they're read
(:py:func:`~sn.model.constraints.migrateConstraints`, via ``Model._migrate``).

Copying
-------

Cut, copy and paste work on the model (:py:mod:`sn.model.copying`): a view
can't show an object twice, so a copy has to be new model objects.
:py:func:`~sn.model.copying.copyObjects` takes a snapshot -- a
:py:class:`~sn.model.copying.Clip` -- of the objects, the contents of any
contexts among them, and their isa links; :py:func:`~sn.model.copying.pasteInto`
makes new objects from it, with new ids. What isn't copied (a type, a
relation's end) is referred to, not copied, so a clip can be pasted only into
a model that can see those objects: the one it came from, or one that builds
on it (:py:func:`~sn.model.copying.pasteProblem`). The commands are
``copy``, ``cut`` and ``paste`` on the
:py:class:`~sn.controller.modelInterface.ModelContext`; a view adds to the
clip how it showed the objects (``Clip.geometry``), so it can show the copies
the same way (``SNGView.showPasted()``).

Persistence
-----------

Models (and views) are :py:class:`~util.persistence.pRef.PRDb`\ s: databases
of :py:class:`~util.persistence.pRef.PRObject`\ s, each with an id, saved to
and read from a URL. pythonUtils does the work; what a class provides is a
description of how to rebuild an object -- its
``getInstantiationInfo()`` -- in terms of:

- **constructor arguments** (``conArgs``, ``conKWArgs``): what's passed to
  the class to make the object;
- **post-construction setters** (``postconSetters``): properties set once
  it's made (eg: a view's hidden categories, or its animation settings);
- **final setters** (``finalSetters``): run once everything in the file has
  been read -- when the objects it refers to exist (eg: ``Model._migrate``).

Each is a :py:class:`~util.persistence.serialize.ParamInfo` or
:py:class:`~util.persistence.serialize.PropertyInfo`, with a getter and
setter, so a class can save what it likes in whatever form suits it.
References between objects are saved as
:py:class:`~util.persistence.pRef.PReference`\ s and resolved lazily.

The file format is chosen by a
:py:class:`~util.persistence.serialize.SerializationStrategy`. The default is
``XML2`` (:py:mod:`util.persistence.serializeXML2`), a compact XML: simple
values and references are written as XML attributes rather than as elements
of their own. Files are read by trying the strategies in turn -- the
preferred ones, and those for the file's extension, first -- so the older
formats are still read.

Copied and moved files
~~~~~~~~~~~~~~~~~~~~~~

References to other files are written relative to the file being written,
when the target is close by (in the same folder, below it, or at most
``PRDb.MAX_UP`` folders up): a folder of models and views can then be moved
or copied as a block. Each file's header records the URL it was saved to,
and the one before that. When a file is read from somewhere else
(:py:meth:`~util.persistence.pRef.PRDb.readFile`), it's noticed and
reported, and a relative reference that isn't found next to the copy is
looked for where the original was.
