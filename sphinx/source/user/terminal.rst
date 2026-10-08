
The Terminal
============

Everything in *Semantic Nets* can also be done by typing commands: in the
terminal pane at the bottom of each window, or in a terminal of its own
(``./sn``). In a window, the commands work on that window's model and view,
and what they change is drawn at once -- the canvas and the terminal are two
ways of doing the same things, and share one undo history.

You can have several windows open on the same model, each a different view
of it; a change made in any of them shows in all of them. But each window
keeps its **own** undo history: **Cmd-Z** in a window undoes what was done in
*that* window. So, if two windows have both changed the same thing, undoing
in one of them may not give what you'd expect: it puts back what *that*
window changed, whatever has happened since in the other.

Commands
--------

A command is a few words, then its arguments (eg: ``new node person``).
Arguments that are options start with ``--`` (eg: ``--type``). Typing
``help`` lists the commands; adding ``-h`` to a command (eg: ``new node -h``)
describes it and its arguments.

Objects are referred to by name (``fred``), by id (``#21``), or with the
model they're in (``pets.snm#fred``). Names with spaces must be quoted.

Making and changing things:

=====================  =======================================================
``new model``          make a new model (a file)
``new node``           make a node: an instance or subtype of a type
``new relation``       make a relation, between two objects
``assert``             say something about the model in one line: make an
                       object of a type, add a type to an object, or relate
                       two objects (eg: ``assert fred likes mary``)
``reconnect``          change a relation's source or destination
``remove``             delete an object from the model
``set attribute``      set an object's attribute
``delete attribute``   remove an object's attribute
``undo``, ``redo``     undo or redo the last change
=====================  =======================================================

Looking at things:

=====================  =======================================================
``show``               show an object, or a model (``--detail`` for more)
``get attribute``      an object's attribute (or all of them)
``get pref``           a setting's value
``query``              ask about the model's structure: ``query ? isa person``
                       (the instances and subtypes of *person*), ``query fred
                       likes ?`` (whom *fred* likes), ``query * fred``
                       (*fred* and all its types). ``?`` goes one level, ``*``
                       all the way
``validate``           check an object, or the model
``format``             set how objects are printed
``cache``              list the models in memory
``super models``       list the model's super-models, or add (``--add
                       file``) or remove (``--remove file``) one (see
                       :doc:`files`)
=====================  =======================================================

Reasoning (see :doc:`reasoning`):

=====================  =======================================================
``reason``             reason over the model, and report
``reason silently``    reason, without adding what's inferred to the views;
                       report just a summary
``clear reasoning``    forget the last results
``answer query``       answer a query (or any context): ``answer query
                       ?likes-fred``
``ask reasoner``       ask the reasoner directly, in its own language (for
                       experts: clingo rules defining ``ans``)
=====================  =======================================================

In a window, there are also commands for the view -- the ones the canvas
uses, so that they can be undone: ``move``, ``resize``, ``collapse``,
``represent`` (show objects), ``erase``, ``visibility`` (show, hide or erase
a category) and ``expand``.

Saving and leaving:

=====================  =======================================================
``save``               save the model (``--url`` to save it elsewhere)
``exit``               leave the program (in ``./sn``)
=====================  =======================================================
