
Concepts
========

A *semantic network* is a graph: **nodes** (things and kinds of things)
connected by **relations** (how they're related). *Semantic Nets* adds a type
system to that graph, so that much of what a network says can be inherited,
checked and inferred.

Nodes and relations
-------------------

A **node** is a thing (*fred*, *rex*) or a kind of thing (*person*, *dog*).

A **relation** connects a *source* to a *destination*, and has a type: *fred
-likes-> mary* is a relation of type *likes*, from *fred* to *mary*. It's
drawn as an arrow with a label in the middle. Relations are objects in their
own right: a relation can itself be the source or destination of another
relation (eg: *(fred -likes-> mary) -since-> 2020*).

Types and individuals
---------------------

Every object is either a **type** (a kind: *person*, *likes*) or an
**individual** (one particular thing: *fred*, or one particular *likes*
relation). Types are drawn with a shadow; a small **T** marker can show them
too.

Types are arranged in a hierarchy by **isa** links: *dog* isa *animal*, *rex*
isa *dog*. An object can have several types (multiple inheritance). What a
type says is inherited by everything below it: if *dog* has a relation *-has->
tail*, then so does every dog -- unless a more specific relation says
otherwise (*rex -has-> stubby-tail*, where *stubby-tail* isa *tail*).

Relation types have a *signature*: a **domain** (what their sources must be)
and a **range** (what their destinations must be) -- eg: *likes*, from
*person* to *person*. The reasoner reports relations that break their
signature, and suggests how to classify the objects involved.

A relation type's own ends are only its signature: *has-sibling*, from
*person* to *person*, doesn't say that anyone *has* a sibling. To say that,
draw a relation of that type between the types: *person -has-mother->
person* says that **every** person has **some** mother (a person) -- "every"
at the source, "some" at the destination. It's inherited as usual, so *alice
-has-mother-> person* says that alice has a mother, whoever she is; when you
say who (*alice -has-mother-> mary*), that replaces it.

Relational properties
---------------------

A relation type can be tagged with the usual algebraic properties, and the
reasoner draws the conclusions they imply:

==================  ===================================================
property            means
==================  ===================================================
**symmetric**       *a -R-> b* implies *b -R-> a* (eg: *has-sibling*)
**asymmetric**      never both *a -R-> b* and *b -R-> a* (eg: *has-parent*)
**reflexive**       everything related is related to itself
**irreflexive**     nothing is related to itself
**transitive**      *a -R-> b* and *b -R-> c* imply *a -R-> c* (eg: *ancestor*)
==================  ===================================================

These tags belong to the relation type they're set on, and are *not*
inherited: *has-brother* isa *has-sibling*, but only *has-sibling* need be
symmetric.

Between types, they keep to "every ... some": transitivity applies however
the ends are (*a -R-> person* and *person -R-> c* give *a -R-> c*), but
symmetry only turns a relation round to an individual -- *alice
-has-sibling-> person* (she has some sibling) doesn't make *person
-has-sibling-> alice*. Reflexive, irreflexive and asymmetric are about
individuals: *person -has-sibling-> person* doesn't relate anyone to
themselves.

Cardinality
-----------

A relation type can also say how many objects each object is related to by
it: its ``cardinality`` attribute, written *min..max* -- eg: ``1..1``
(exactly one), ``0..1`` (at most one), ``2..2`` (exactly two), ``1..*`` (at
least one), or ``(1,1)``, or just ``2``. It counts its subtypes too: a father
is a parent, so with *has-father* and *has-mother* each ``1..1``,
*has-parent* ``2..2`` agrees. Its ``inverseCardinality`` counts the other
way: how many objects are related *to* each one (eg: a desk that's
*has-desk* ``inverseCardinality`` ``0..1`` is no-one's, or one person's).
Like the relational properties, they belong to the relation type they're
set on, and aren't inherited.

The reasoner uses them:

- **Too many** different objects (ones you've named: they're different
  people) is an error.
- **Too few** is a warning -- for the individuals of the relation type's
  domain (the range's, for ``inverseCardinality``): eg: a person with one
  parent, when *has-parent* is ``2..2``. (Not if the domain is just *top*:
  then it's not known who should have them.)
- **At most one** makes the objects the rules invent the same object: if
  rules give alice "a mother" twice, it's the same mother -- and if alice's
  mother is mary, it's mary, and what the rules said of "a mother" they've
  said of mary.
- **Exactly one** invents one where the model has none: with *has-father*
  ``1..1``, a person with no father gets "(has-father for alice)", a person
  -- which needs no "every person has a father" rule.

Naming relations
----------------

A relation's name has to say which way it reads: does *fred -parent-> mary*
mean that mary is fred's parent, or that fred is mary's? The examples use
names that leave no doubt, and read from the source to the destination:
``has-*`` names (*fred -has-parent-> mary*: fred has mary as a parent), or verbs
(*fred -likes-> mary*). ``has-*`` names also point the same way as *isa*: from
the child to the parent, as from the subtype to the supertype. Which object a
pattern's constraints go on then follows: in *?a -has-brother-> ?b*, the
brother -- the one who's male -- is *?b*.

Attributes
----------

Every object has **attributes**: named values, such as its *name*, a *note*,
or anything you add (*age: 30*). Attributes are inherited down the type
hierarchy too, under rules you can set per attribute -- whether a subtype or
an instance may override the inherited value, must supply its own, and so on.
They're edited in the attribute editor (see :doc:`editing`).

Attributes whose names start with ``vis/`` control how an object is drawn
(its shape, colours, size, label, ...); see :doc:`viewing`.

Models
------

A network is kept in a **model**, saved in a file (``.snm``). A model can use
the types of other models: every model builds on the system model, *sn*, which
defines the basic types -- *top* (the root of everything), *node*,
*relation*, *isa*, and the types used for rules and queries (*context*,
*rule*, *query*, *definition*, ...). Objects from another model are marked
with an **R** (remote).

What you see of a model is a **view** of it, saved in a file of its own
(``.snv``): which of the model's objects are shown, where, and how. A model
can have several views; a view never changes what the model says.

Variables, rules, definitions and queries
-----------------------------------------

An object whose name starts with ``?`` is a **variable**: it stands for
*whatever matches* -- in a **query** (find what matches this pattern), a
**rule** (whenever this pattern matches, conclude that) or a **definition**
(this means exactly that). These are drawn as windows, and are described in
:doc:`contexts`.
