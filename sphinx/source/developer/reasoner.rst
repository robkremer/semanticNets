
The Reasoner
============

The reasoner works out what follows from a model. It's in two layers:

:py:mod:`sn.model.reasoner`
  The engine-independent part: the :py:class:`~sn.model.reasoner.Reasoner`
  interface, the export of a model as facts, the reading of rules,
  definitions and queries into patterns, and what an engine returns
  (:py:class:`~sn.model.reasoner.Inferences`,
  :py:class:`~sn.model.reasoner.Violation`).

:py:mod:`sn.model.clingoReasoner`
  The engine: :py:class:`~sn.model.clingoReasoner.ClingoReasoner`, built on
  `clingo <https://potassco.org/clingo/>`_, an answer set programming (ASP)
  system, with its rule base in ``clingoReasoner.lp``.

Engines register themselves by name (``class ClingoReasoner(Reasoner,
engine="clingo")``) and are made with
:py:meth:`Reasoner.create(model, engine) <sn.model.reasoner.Reasoner.create>`
(by default, the ``reasoner/engine`` preference's: see
:py:func:`~sn.model.reasoner.defaultEngine`). Another engine implements the
same interface; ``test/test_model/test_reasoner.py`` pins down the semantics
every engine must share (*ReasonerSpec*), and ``test/test_model/test_rules.py``
runs the rules tests by each engine. There are three more already: Nemo,
CLIPS and SWI-Prolog (see `The Nemo engine`_, `The CLIPS engine`_ and `The
Prolog engine`_ below).

What the program knows about an engine before it's imported is in
:py:data:`~sn.model.reasoner.ENGINES`: the Python module it needs, the package
that provides it (and what must be installed before it, if anything: SWI-Prolog,
for janus-swi), whether it can explain a conclusion, and whether the apps
include it (their ``--selftest`` reasons, and explains, with each one they
should have: see ``sn/__main__.py``). So
:py:func:`~sn.model.reasoner.engineInstalled` can tell whether one can be used
without loading it, *Reasoner.create()* raises
:py:class:`~sn.model.reasoner.EngineMissing` (an *ImportError*) for one that
isn't installed -- which the GUI shows with a link to the User Guide's
"Installing an engine" (:py:data:`~sn.model.reasoner.INSTALL_HELP`, by
:py:func:`~sn.view.graphics.viewReasoning.showEngineMissing`) -- and
**explain** uses :py:func:`~sn.model.reasoner.explainingEngine`: the default
engine if it can explain, or else an installed one that can. A new engine adds
itself to *ENGINES*, to the ``reasoner/engine`` preference's choices
(``sn.PREFS``: a test checks the two agree), and to "Installing an engine".

The apps have their own Python, which pip can't install into. So when an
engine's module isn't in an app, it looks for it in the packages of a Python
on the computer that can share them -- the same version, build and processor
as its own: the ``reasoner/python`` preference's, or else one where installers
put them -- and puts their folders at the end of *sys.path* (see
:py:mod:`util.localPython`, in *pythonUtils*). The Mac app can load that
Python's compiled packages because it's ad hoc signed, without the hardened
runtime.

Why ASP
-------

A semantic network's meaning -- inheritance, relational properties,
signatures, rules -- is naturally a set of logic rules over its structure,
and clingo evaluates such rules directly, to a fixed point, with negation
(for "unless a more specific relation says otherwise"). The rules are short,
declarative, and kept in one file (``clingoReasoner.lp``), separate from the
Python.

To keep relation types first-class -- in the isa hierarchy, and themselves
related -- while staying first-order, every GraphObject is *reified* as a
term ``o(N)``: "fred likes mary" is ``link(o(31), o(21), o(23))`` together
with ``parent(o(31), o(12))`` (the relation is a *likes*), not
``likes(fred, mary)``.

The pipeline
------------

.. graphviz::

   digraph pipeline {
     rankdir=LR;
     node [shape=box, style=rounded, fontname="Helvetica", fontsize=10];
     model [label="Model"];
     facts [label="Reasoner.facts()\nobj, parent, link, prop,\nattr, pattern, ..."];
     rules [label="_rulesProgram()\nthe user's rules and\ndefinitions, as clingo rules"];
     lp [label="clingoReasoner.lp\nthe rule base"];
     clingo [label="clingo\n(ground & solve)"];
     inf [label="Inferences\nholds, inferred, inherited,\nclassify, violation, fired, ..."];
     model -> facts -> clingo; model -> rules -> clingo; lp -> clingo; clingo -> inf;
   }

1. :py:meth:`~sn.model.reasoner.Reasoner.facts` exports the model as
   engine-neutral facts (their vocabulary is listed in the module's
   documentation). Pattern elements -- the contents of rules and queries --
   are exported too, but marked ``pattern``, so the rule base doesn't take
   them as facts about the world.
2. The user's rules and definitions are compiled to clingo rules (below).
3. clingo grounds and solves the facts, the compiled rules and the rule
   base together. The program is *stratified* (no recursion through
   negation), so there's exactly one answer set, and it's found without
   search.
4. The atoms shown (``#show``) are mapped back to GraphObjects, as an
   :py:class:`~sn.model.reasoner.Inferences`.

:py:func:`sn.model.reasoner.reason` runs this, keeps the result on the model
(``model.reasoning``), and notifies the model's observers with a
``("reasoned", (inferences,))`` topic: every view draws the results. They're
a snapshot -- not saved, and not updated as the model is edited -- until the
next ``reason()`` or :py:func:`~sn.model.reasoner.clearReasoning`.

What was inferred is also put in the model, as **inferred objects**
(:py:attr:`GraphObject.inferred <sn.model.model.GraphObject.inferred>`):
:py:func:`~sn.model.reasoner.materialize` makes a relation for each inferred
or inherited relation, an isa link for each one the rules concluded, and a
node for each object the rules concluded exists
(:py:class:`~sn.model.reasoner.NewObject`) -- named for the rule's variable
and the match, eg: "(m for alice)" -- with the types, attributes and
relations the rules gave it. Each one's ``inferredKind`` says what it is
("inferred", "inherited", "rule" or "new"); a new object is kept from one
"reason" to the next by its rule, variable and match. So the model's own
queries -- :py:meth:`~sn.model.model.GraphObject.getRelatedTo`, isa,
inherited attributes -- see them like anything else. They're kept apart from
what's asserted:

- they're **not saved** (the model's object table leaves them out), and
  adding or removing them doesn't make the model dirty, or go on the undo
  list -- even a write-locked model can be reasoned over (see
  :py:meth:`Model.inferring() <sn.model.model.Model.inferring>`);
- the reasoner **doesn't read them**: while it gathers its facts they're
  taken out of the model and put back afterwards
  (:py:func:`~sn.model.reasoner.withoutInferences`) -- otherwise an inferred
  isa link, say, would give its object the type's attributes, and justify
  itself;
- the next ``reason()`` **keeps** those still inferred (the same objects),
  adds the new ones, and removes the rest; ``clearReasoning()`` removes them
  all;
- they're **the reasoner's**: changing one's attributes raises
  ``PermissionError`` (``GraphObject._refuseIfInferred()``), and the model
  commands refuse to remove, reconnect or relate them, or make instances of
  them -- until the ``mark asserted`` command
  (:py:meth:`ModelContext.mark_asserted() <sn.controller.modelInterface.ModelContext.mark_asserted>`,
  undoable; not in a write-locked model) makes one asserted, with what has to
  come with it (:py:meth:`GraphObject.assertedWith() <sn.model.model.GraphObject.assertedWith>`:
  its inferred isa links, a relation's inferred ends, and the relations a
  rule gave a new object -- without them the next ``reason()`` would make
  another in its place).

Attribute values the rules conclude for the model's own objects
(``ruleAttrs``) become **inferred attributes** (``Attribute.inferred``, in
pythonUtils): set where the object has no value of its own (nor that value
inherited), not saved with it, taken out while the reasoner gathers its facts,
and kept, updated or removed by the next ``reason()``. Setting a value where
one is inferred replaces it with an ordinary one (``GraphObject.__setitem__``),
so undo brings the inferred one back; the attribute editor's **assert** button
does the same.

Views show the new objects related to objects they show (beside them), and
the inferred relations between objects they show
(``SNGView._showInferred()``, on the ``"reasoned"`` topic) as ordinary view
objects that are drawn faded (``VObject.isInferred()``; the vis cache fades
their colours toward the background) with dashed lines -- dotted for
inherited ones (the relation's ``inferredKind``). They take part in layouts
like anything else, but aren't saved with the view, and neither they nor the
model's inferred objects count when a view or model checks whether it's dirty.

The rule base
-------------

``clingoReasoner.lp`` defines, over the facts:

- ``isa_star``: the reflexive-transitive isa closure (including types that
  rules conclude);
- ``holds(T,S,D)``: S is related to D under relation type T -- directly, by
  a subtype of T, by inheritance down the isa hierarchy, or by a rule
  (including the base rules: see below);
- ``inferred`` and ``inherited``: the holds that weren't asserted (and
  aren't implied by a more specific relation type);
- ``classify(X,C)``: a type that would make a relation's end fit its
  signature;
- ``violation(Code, Severity, Subject, Args)``: the problems, whose codes
  are turned into messages by ``reasoner._MESSAGES``.

Rules and definitions
---------------------

:py:func:`~sn.model.reasoner.patternOf` reads a context (or some of its
parts: see :doc:`model`) into a :py:class:`~sn.model.reasoner.Pattern`: its
variables, constants, relations, isa links and constraints;
:py:func:`~sn.model.reasoner.patternsOf` reads it into one pattern per
alternative (one per antecedent part, say).
:py:func:`~sn.model.reasoner.ruleSpecsOf` reads a rule into
:py:class:`~sn.model.reasoner.RuleSpec` objects, one per antecedent part
(several antecedents are a disjunction): the antecedent's pattern, and the
consequent's conclusions (all its consequent parts together) -- relations
(``heads``), attribute values (``assertions``), types (``isas``), and the
variables that only the consequent has (``new``: objects to create).
(:py:func:`~sn.model.reasoner.ruleOf` reads it as one, the antecedents
merged.) A definition is two RuleSpecs, one each way
(:py:func:`~sn.model.reasoner.definitionSpecs`) -- or, with several
definiens parts, just the RuleSpecs from each to the definiendum, with a
``definition_one_way`` warning. A requirement is one
:py:class:`~sn.model.reasoner.ConstraintSpec` per condition part
(:py:func:`~sn.model.reasoner.constraintSpecsOf`). Problems found on the
way (eg: a consequent relation with no end; a part shared by two boxes,
``part_shared``, or not quoted, ``part_unquoted``) are recorded in the
spec, and reported instead of compiling the rule (or, for warnings, with
it).

``ClingoReasoner._rulesProgram`` then compiles each spec to one clingo rule
per conclusion, the antecedent as the body (``_patternBody``):

.. code-block:: none

   fired(Rule, T, S, D)        :- <antecedent>.    % a relation
   rule_attr(Rule, X, Key, V)  :- <antecedent>.    % an attribute value
   rule_isa(Rule, X, Type)     :- <antecedent>.    % a type

and the rule base feeds these back in, as ``holds``, ``attr`` and isa. So
rules chain: one rule's conclusions can satisfy another's antecedent.

New objects
~~~~~~~~~~~

A consequent-only variable stands for an object that exists for each match.
It's represented by a term that's a function of the match --
``new(Rule, Name, ((Var, Value), ...))`` -- so there's exactly one per match,
and reported as a :py:class:`~sn.model.reasoner.NewObject`. Two things keep
this finite and stratified:

- the variables of a rule that creates objects range over the model's data
  only, never over created objects (``base``/``individual`` rather than
  ``data``/``any_individual``), so it can't keep creating objects from its
  own creations (a rule that creates nothing can't run away, so its
  variables range over all the data, created objects included);
- an object is created only if the data doesn't already have one doing the
  job (``_satisfied``) -- tested against *asserted* relations and types
  only, so the test doesn't depend on its own outcome.

Cardinality
~~~~~~~~~~~

A relation type's ``cardinality`` and ``inverseCardinality`` attributes
(:py:data:`~sn.model.reasoner.CARDINALITY`, read by
:py:func:`~sn.model.reasoner.parseCardinality`) are exported as
``card(T, out|in, Min, Max)`` facts (``Max`` -1 for any number), and the rule
base (``clingoReasoner.lp``, "Cardinality") gives them their meaning:

- **Merging** (at most one): ``same(X, Y)`` for two objects related to (or
  from) the same object, one of them new -- and its symmetric and transitive
  closure. What's true of one is then true of the other (``holds``, ``attr``
  and ``isa_star`` are copied across): positive rules, so the program stays
  stratified. Two of the model's objects are never merged (they have
  different names): their being the same is reported, as too many.
  :py:func:`~sn.model.reasoner.mergeSame` then replaces each new object by what
  stands for its class (:py:func:`~sn.model.reasoner.sameClasses`: the model's
  object, if there's one, else one of the new ones) in the results, and the
  engine's ``answer()`` does the same for answers.
- **Inventing** (exactly one): a ``new(T, Name, (("of", X),))`` object (``"to"``
  for ``in``) for each of the domain's (range's) individuals with no asserted
  relation by T -- like a rule's new objects, only for the model's own
  individuals (``base``), and tested against asserted relations only.
- **Checking**: ``cardinality_max`` (``_in``) counts the model's objects only
  (a new one might be any of them); ``cardinality_min`` (``_in``) counts new
  ones too, once per merged class.

The relation triples in the results are sorted into the models' order (see
*Reasoner._finish()*), so they don't depend on the engine's.

Defining links
~~~~~~~~~~~~~~

A relation type tagged ``meet`` or ``join`` (:py:data:`~sn.model.reasoner.DEFINING`:
Gaines's structural connectives) makes its links define a node. Its
"for every defining link" clause has no negation (which would loop through
``holds``): :py:meth:`~sn.model.reasoner.Reasoner._definingFacts` numbers
each node's defining links (``def_part(C, D, I, A, P, Pol)``, ``def_last(C,
D, N, Q, R)``), and the rule base (``clingoReasoner.lp``, "Nodes defined by
their links") chains along them: ``def_ok(C, D, X, I)`` says X stands as
required to links 1..I, so at N, X has the order Q to C (C to X, for a
join), as a ``fired`` conclusion of the tagged type R. With truth attributes
(``def_marks``), prefix and suffix chains of the links that hold (or fail)
give "all of them" and "all but one", as ``rule_attr`` conclusions. A node
one of whose links' ends has both marks locally (``def_mixed``, a fact)
blocks "all but one" -- negation of a fact, so the program stays
stratified. Each engine's rule base has the same rules.

Exploring (``necessaryValue``: ``def_world(C, D, NV, DV)``) needs choice,
so it's clingo's alone, in three solves of the same ground program
(:py:meth:`~sn.model.clingoReasoner.ClingoReasoner._explore`), each adding
a ``#program`` part of ``clingoReasoner.lp``:

1. ``marks``, with the rest: ``world_mark0`` (the marks before exploring)
   and ``world_open0`` (the open connectives: a true join with no link
   holding, a false meet with none failing). If there are none, that's all.
2. ``explored``, solved cautiously (the intersection of the answer sets):
   one case (``world_pick``) for each open connective still open
   (``world_need``), among its links that didn't fail; a world that gives a
   node both marks it hadn't both of is dropped. The marks every world
   adds are the necessary ones.
3. ``preferred``, if there are ``def_prefer`` facts: as (2), plus a default
   rule (A's link fails while B's might hold, for each ``world_pref`` --
   the prefer relation's ``holds`` among one connective's ends) and a weak
   constraint per connective, at the priority ``def_rank`` gives it (from
   *DEFAULT_ORDER*, then the model's order), counting the preferred ends
   that fail; solved for the optimal answer sets, cautiously. What they
   add beyond the necessary marks are the defaults.

The new marks are ``rule_attr`` conclusions of the first ``def_world``'s
tagged type, as the other connectives' are.

Probes (:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.probes`: KNet's,
see *PROBE_KINDS*) are clingo's too: each is an answer set, so they're
enumerated, not intersected. Two more ``#program`` parts, each solved with
the model's facts and rules and the probe facts (``probe_key``: the true and
false attributes; ``probe_node``: the nodes to probe; ``probe_asserted``:
those with an asserted mark):

1. ``probe_marks``: the marks the rules give, ``probe_value`` -- of the model
   as it is, and with a node given a mark (an ``attr`` fact) for admissible
   probes.
2. ``probed``, with those marks as ``probe_mark0`` and ``probe_kind``: for a
   consistent probe, a choice of one mark (``probe_set``, a ``rule_attr``
   conclusion) for each node without one, and a constraint that no node
   gets both marks it hadn't both of; for a compatible one, a choice of
   marks, at least those it had, for each node not asserted, with no
   constraint. Each answer set's ``probe_out`` is a probe.

An admissible probe is a consistent one, of the model with a node's
opposite mark added, or then (from those marks) its own mark again: so
there's a ``probe_marks`` and a ``probed`` solve for each node with one
derived mark. The facts and rules are rendered once per reasoner (each
part of a net is probed in turn), and more than ``limit`` probes raise
*TooManyProbes*. The rnetReader plugin's ``probes`` module finds a net's
probes part by part, and reconstructs its links from them.

Constraints
-----------

:py:func:`~sn.model.reasoner.constraintOf` reads a constraint into a
:py:class:`~sn.model.reasoner.ConstraintSpec`: its pattern, and from its
attributes the violation's code, severity, what it reports (subject first)
and message. Each compiles to one clingo rule:

.. code-block:: none

   violation0(Code, Severity, Subject, (Args,)) :- <pattern>.

A requirement (a constraint that isa *requirement*) has a second pattern, its
required part (:py:attr:`~sn.model.reasoner.ConstraintSpec.required`); its
pattern is its condition. It compiles to two rules, over the condition's
variables (``Vars``):

.. code-block:: none

   requirement_holds(Req, (Vars,)) :- <condition>, <required>.
   violation0(Code, Severity, Subject, (Args,)) :- <condition>, not requirement_holds(Req, (Vars,)).

The first has the condition in its body too, so the variables the two parts
share have values even where the required part only uses them in a ``not``
(eg: ``not gender: ?g``); its own variables are existential.

:py:meth:`~sn.model.reasoner.Reasoner._finish` -- which every engine passes
its results through -- reports a violation once per set of objects it's
about (so a constraint matching a-b and b-a reports it once), and gives a
constraint's violations its message.

The base rules
--------------

The meaning of the relational properties (symmetric, transitive, reflexive,
irreflexive, asymmetric) isn't in ``clingoReasoner.lp``: it's ordinary rules
and constraints, in a model of **base rules** (``sn/model/baseRules.snm``,
made by ``tools/makeBaseRules.py``) that every reasoner applies to every
model (:py:meth:`~sn.model.reasoner.Reasoner.ruleObjects`), so a new engine
gets them by translating rules, with nothing more to write. They use a
relation-type variable (``^r``) tagged with the property, and individual
(``?a``) or "any" (``!a``) variables by what a relation with a type at an end
means -- "every" at its source, "some" at its destination: eg: ``!a -^r-> ?b``
with ``^r {symmetric}`` concludes ``?b -^r-> !a`` (but nothing from ``a -r->
T``: which T?); transitivity is all ``!``; reflexive, irreflexive and
asymmetric are all ``?``. See ``tools/makeBaseRules.py``.

Variable names
--------------

Which names are variables, and of which kind, is decided in one place:
:py:meth:`sn.model.names.NameGrammar.parse` (``?x`` individual, ``^T`` type,
``!a`` any; anything else a constant -- and a variable whose stem starts with
``_``, eg: ``?_b``, is hidden: :py:func:`~sn.model.reasoner.reportedAnswers`
leaves it out of a query's answers). Everything else asks it, through
:py:meth:`~sn.model.model.GraphObject.variableKind` or
:py:func:`sn.model.names.isVariableName` -- the engines (a variable's kind
is a guard in clingo: ``individual(V)``, ``type(V)`` or none), the
constraints' value variables, the views. An application that needs its own
syntax for names subclasses it and installs it with
:py:func:`~sn.model.names.setGrammar`; it should leave the names it doesn't
claim to the default (``super().parse()``), as the base rules are written in
it.

:py:data:`~sn.model.reasoner.BASE_RULES` lists the base rules' models, and
an application can change it (eg: to base rules of its own), before it makes
or reads a model. :py:func:`~sn.model.reasoner.baseRuleModels` reads them
(write-locked) once. Like the system model, they're super-models of every
model (:py:meth:`~sn.model.model.Model.implicitSuperDBs`): they can't be
removed, and aren't saved with it (the file read may be a temporary copy of
package data), but are added again when it's read.
:py:meth:`~sn.model.reasoner.Reasoner.objects` leaves them out: their
objects aren't facts, and their conclusions are reported as plain
inferences, unless the ``reasoner/showSysRules`` preference (or the
reasoner's *showSysRules*) is on.

The Nemo engine
---------------

:py:mod:`sn.model.nemoReasoner`
  :py:class:`~sn.model.nemoReasoner.NemoReasoner` (``engine="nemo"``), built
  on `Nemo <https://github.com/knowsys/nemo>`_, a Datalog engine (stratified
  negation, aggregates) from TU Dresden, through its Python bindings
  (``pip install nemo-python``, imported as ``nmo_python``). The apps include
  it (Linux's library stripped of its debugging symbols: 233 MB down to 17);
  for the ``.pyz`` and the source it's optional: if it's missing, the program
  says how to install it (see above), and the tests skip it.

Its rule base, ``nemoReasoner.rls``, is ``clingoReasoner.lp`` ported rule
for rule, and ``_rulesProgram()`` compiles the user's rules the same way, so
the two give the same results. Where Nemo differs:

- Objects are constants ``<#N>``. Nemo strings have no escapes, so strings
  are percent-encoded (``%22`` for a quote, ...), and decoded on the way back.
- There are no tuples or function terms: a violation with *N* arguments is
  ``violation0_N``/``violation_N``; an object a rule creates is a string
  (``"%new|K|#V0|..."``, K saying which rule and variable) made with an
  f-string in the rule's head.
- Nemo checks that the whole program is stratified before it runs. A rule's
  negated attribute test can't be on ``attr/3`` (which the rules feed), so it's
  on ``attr_base/3``, the attributes the model gives -- a small difference in
  meaning from clingo's, for rules only.
- Counting is an aggregate in a rule's head, so "too few" has a rule for none
  at all.
- Nemo takes a moment for each fact it parses, so most facts go to it as
  tab-separated tables it imports (in a temporary folder).

What it adds is :py:meth:`~sn.model.nemoReasoner.NemoReasoner.explain`: the
derivation of a conclusion from Nemo's trace, as
:py:class:`~sn.model.nemoReasoner.Step` objects, briefly (leaving out the
bookkeeping: what's data, a type, ...) or in full. The terminal's
``explain`` and an inferred relation's **explain (why it holds)** use it.

The CLIPS engine
----------------

:py:mod:`sn.model.clipsReasoner`
  :py:class:`~sn.model.clipsReasoner.ClipsReasoner` (``engine="clips"``),
  built on `CLIPS <https://www.clipsrules.net>`_, a forward-chaining
  production rule system, through its Python bindings (``pip install
  clipspy``, imported as ``clips``). The apps don't include it: they use it
  from a Python on the computer (see above). For the ``.pyz`` and the source
  it's optional, as Nemo is.

Its rule base, ``clipsReasoner.clp``, is ``clingoReasoner.lp`` ported rule
for rule, as ordered facts (``(holds ?t ?s ?d)``), and ``_rulesProgram()``
compiles the user's rules the same way, so the engines give the same results.
Where CLIPS differs:

- CLIPS fires a rule as soon as its conditions match, so a ``(not ...)`` is
  only right once what it tests is complete. The engine reads the rules (the
  rule base's, the model's and a query's: a small reader of CLIPS's
  parentheses, ``_read()``), sorts their predicates into strata
  (``_stratify()``: the groups that conclude each other, each after those it
  tests with ``(not ...)``), and gives each rule the salience of its stratum,
  so that it fires only once the strata below are done. A program that isn't
  stratified is refused, as Nemo refuses one -- so a rule's negated attribute
  test is on ``attr_base``, as Nemo's is.
- CLIPS matches a rule's conditions in order, keeping every partial match: a
  condition that shares no variable with those before it multiplies them. So
  the rule base's conditions are written in a good order, and the engine
  orders a compiled rule's (``_ordered()``): first a pattern with a constant,
  then each that shares the most with those before, each test or
  ``(not ...)`` as soon as its variables are bound. (Before that, a
  transitive rule's ``(data ?x) (data ?y) (data ?z)`` took a minute.)
- Objects are symbols ``#N``; an object a rule creates is a symbol
  (``%new:K:#V0:...``) made with ``sym-cat`` in the rule's action.
- There are no aggregates: the cardinality violations that count (too many,
  too few) are counted in Python, from the ``holds``, ``card``, ``card_of``
  and ``card_counted`` facts (``_counted()``).

The Prolog engine
-----------------

:py:mod:`sn.model.prologReasoner`
  :py:class:`~sn.model.prologReasoner.PrologReasoner` (``engine="prolog"``),
  built on `SWI-Prolog <https://www.swi-prolog.org>`_ (9.1.12 or later)
  through its Python interface, janus (``pip install janus-swi``, imported as
  ``janus_swi``; pip builds it against the ``swipl`` it finds, so SWI-Prolog
  comes first). The apps don't include either: they use them from the
  computer (see above), as CLIPS. Before importing janus, the module tells
  SWI-Prolog where its home is (SWI_HOME_DIR: see
  :py:mod:`pythonUtils:util.swiProlog`), from the library folder janus was
  built against, or else a ``swipl`` program's: started from an IDE or the
  Finder, with no ``swipl`` on the ``PATH``, SWI-Prolog otherwise may not find
  it, and stops the whole program ("FATAL: could not find SWI-Prolog home").

Its rule base, ``prologReasoner.pl``, is ``clingoReasoner.lp`` ported rule
for rule, and ``_rulesProgram()`` compiles the user's rules as clingo's does
(Prolog's syntax is close to ASP's), so the engines give the same results.
Each run loads the rule base, the facts and the rules, as one text, into a
module of its own (``in_temporary_module/3``), which goes when it's done; a
small helper module (``_HELPER``, loaded once) does that, keeps the errors
(to raise them in Python, saying whether the query or the rules have them),
and gives the true answers back as Python values. Prolog runs on one thread
(``_call()``), whichever thread asks. Where Prolog differs:

- It's top-down: SWI-Prolog's tabling, with the well-founded semantics, does
  what clingo's grounding does -- recursion ends, and a negation (``tnot/1``,
  ``not_exists/1``) waits until what it tests is known. So a rule's negated
  attribute test is about what the rules conclude too, as clingo's is (Nemo
  and CLIPS need a stratified program). A loop through a negation leaves what
  depends on it undefined, and only true answers are read.
- It works in two steps. The closure -- what the rules conclude, and what that
  depends on -- is tabled, with ``r_holds/3``, ``r_isa_star/2`` and
  ``r_attr/3`` for the rules to test. Then ``sn_close/0`` states its results
  as facts (``holds/3``, ``isa_star/2``, ``attr/3``), and the rest -- what's
  inferred, the violations, the constraints, queries -- reads them with plain
  Prolog. A tabled call makes a table for each call pattern: asking about
  each triple that way worked each out again (a model of 3,000 objects took
  45 s); a fact is just looked up.
- Prolog runs a body in order, so a compiled rule's literals are ordered as
  CLIPS's conditions are (``_ordered()``): first one with a constant, then
  each sharing the most, each test or negation once what it tests is bound.
- Objects are atoms ``'#N'``, not clingo's ``o(N)``: Prolog finds a fact by an
  atom argument, but not by the number inside a compound term (with ``o(N)``,
  every ``kind/2`` lookup read every fact: 30 s of a 10,000-object model's
  31). An object a rule creates is a term ``new(Rule,Var,[[Name,Value],...])``
  -- made last in a clause's body, not in its head, where a call like
  ``holds(T,S,S)`` would unify a variable with a term holding it.
- The facts are grouped by predicate: SWI-Prolog warns of each clause that
  isn't with the others of its predicate, slowly (8 s of a big model's load).

A 15,000-object model takes about as long as with clingo (most of it the
shared export of the facts).

Queries
-------

:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.answer` compiles a
query's pattern to an ``ans(...)`` rule, solves it with the model's facts
and the results of reasoning (a query's variables *do* range over created
objects), and returns one dict per match: variable to object.
:py:meth:`~sn.model.clingoReasoner.ClingoReasoner.query` takes clingo
rules defining ``ans`` directly (the terminal's ``ask reasoner``); Nemo's
takes Nemo rules (``ans(?X) :- holds(?T,?F,?X), name(?T,"owns"), ...``),
CLIPS's CLIPS rules asserting ``ans`` facts (``(defrule q (holds ?t ?f ?x)
(name ?t "owns") ... => (assert (ans ?x)))``), and Prolog's Prolog clauses
(``ans(X) :- name(T,"owns"), name(F,"fred"), holds(T,F,X).``: they run in the
order they're written).
