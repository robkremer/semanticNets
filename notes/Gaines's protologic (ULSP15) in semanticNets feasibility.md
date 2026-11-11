# Gaines's protologic (ULSP15) in semanticNets: feasibility

Nov 11, 2026 · @Rob

## The answer

Yes, it's feasible, and more than half of [Gaines (2015), *Universal Logic as a Science of Patterns*](https://gaines.library.uvic.ca/pdf/ULSP15.pdf) fits machinery semanticNets already has. The whole paper is roughly 16 to 25 working days; a useful core (import, kernel inference, marks) is about a week.

- **Fits as it is.** The kernel protologic (inclusion, exclusion, coexclusion, negation, equivalence, inconsistency and the generic patterns) becomes relation types plus ordinary rules, definitions and constraints. These go in a generated rules model, like baseRules.snm, so all four engines run them with no engine code.
- **Fits with one new decorator.** Gaines's truth marks are rule-concluded attributes. They need a decorator that draws vertical and horizontal marks in the paper's colours.
- **Needs new machinery.** Structural conjunction and disjunction need a "for every defining link" test that patterns can't express. Defeasible inference (preferences, normal defaults) is non-monotonic, and the four engines assume one stratified model. Probes and saturation need model enumeration, which clingo can do.

The Rep Plus 2 data is readable without the Xojo code. I decoded the .rnet format and checked a parser against all 1,496 net files. 209 of them store derived links and 105 store propagated marks, which gives ready-made expected results for testing.

Recommended first step: a plugin that imports .rnet files, plus a KNet rules model for the kernel and marks. After that, decide how the engines should handle connectives and defaults (see the last section).

## What the paper defines

The paper builds logic from typed links between labelled nodes, with inference written as before-and-after patterns on graphs. Its constructs fall into six groups.

| Group | Constructs (paper section) |
| --- | --- |
| Kernel links and patterns | Inclusion → as a preorder; cycles as equivalence; loop and repetition patterns (2.1–2.5). Exclusion →❬: "any node that includes the tail is excluded from also including the head"; inconsistent links and paraconsistency (2.6). Generic patterns shared by all link types (2.7). Coexclusion →❬❬: "any node that excludes the head must include the tail"; structural negation (exclusion plus coexclusion), double negation, squares and hexagons of opposition (2.8). |
| Notation | Protoconjunctions and protodisjunctions: grouped labels that define no node (2.4). |
| Dynamics | Minimal and maximal canonical forms; consistent, conservative and ultra-conservative imports and merges; single-node and factoring expansions; five senses of existence; probes (bottom nodes added from outside) and saturation (3). |
| Semantics | Proof-theoretic; truth-theoretic marks (vertical true, horizontal false, both inconsistent, as in Belnap's four values) propagated along links; intensional sets; extensional semantics from sets of admissible probes (4). |
| Structural connectives | Structural conjunction (heavy heads) and disjunction (double heads), which define ideal nodes by extremal conditions; material implication with a conditioning node (5). |
| Defeasible inference | A preference relation among the disjuncts of a structural disjunction; normal defaults; abduction (6). |

Section 7 applies them: merging taxonomies, the contact lens expert system, Gaut's art cluster concept, and states of affairs with thematic roles (Anthony *loves* Cleopatra, Venus as morning and evening star, Armstrong's structural universals).

## How each construct maps onto semanticNets

Of 22 constructs, 12 need only relation types, rules, definitions or constraints, or nothing at all. 10 need new code, 3 of them in the engines. "Rules" below means a generated rules model (say knetRules.snm, made the way tools/makeBaseRules.py makes baseRules.snm), so all four engines get it by translating rules.

| Construct | semanticNets form | Fit |
| --- | --- | --- |
| Nodes, anonymous nodes | Individuals of a *knode* type. Anonymous ones get a generated name and `vis/label` "" | Ready |
| Inclusion → | Its own relation type *includes*, tagged transitive (and reflexive, with the self-loops hidden). Not isa: SN reports isa cycles, which Gaines uses for equivalence, and isa carries every/some inheritance | Ready |
| Cycles, equivalence, loop | Rule: mutual *includes* concludes *equivalent* (symmetric, transitive) | Rules |
| Repetition (parallel links) | Free: what holds is a set, so duplicates collapse | Ready |
| Exclusion →❬ | *excludes*, symmetric. Rule: ?n includes ?t, ?t excludes ?h concludes ?n excludes ?h. Reverse patterns likewise | Rules |
| Inconsistency, paraconsistency | Rule concludes *inconsistent*, which propagates down; a constraint (warning) gives the E marker. Datalog and ASP don't explode, so it stays local | Rules |
| Coexclusion →❬❬ | *coexcludes*, symmetric. Rule: ?n excludes ?h, ?t coexcludes ?h concludes ?n includes ?t; plus its inheritance pattern | Rules |
| Negation, double negation | Definition: *negates* means excludes and coexcludes. Rule: two negations of one node conclude *equivalent* | Rules |
| Generic link patterns | Relation types tagged with properties, rules over ^r type variables, as the base rules already do | Rules |
| Squares and hexagons of opposition | Follow from the four rows above | Ready |
| States of affairs, thematic roles | Role relation types (agent, patient, instrument) between knodes | Ready |
| Link notation | `vis/terminator` stacks cover →, →\| (exclusion, the bar-arrow in the data) and →\|\|; `vis/midMarks` covers the symbols on symmetric links; inferred links already draw faded and dashed | Ready |
| Heavy and double heads (connectives) | Two new mark kinds via `util.lineMarks.registerMarkKind` (pythonUtils) | Small new code |
| Truth marks (true, false, both; provenance colours) | Asserted marks = attributes. Propagation = rules concluding attributes. A new decorator draws them; menu items set and clear them | Rules + new decorator |
| Protoconjunction, protodisjunction | Notation only: expand a grouped label into separate links on input, or draw a group | Small new code |
| Expansion and factoring patterns | Editing commands: add an anonymous node; interpolate one to factor shared links | Small new code |
| Existential status (top, bottom, consistent) | Needs "no node includes ?x", and patterns can't negate relations. Compute in Python | Small new code |
| Canonical forms | Maximal: reason, then mark asserted. Minimal: transitive reduction, generic graph code for pythonUtils | New command |
| Imports and merges | Super-models already import; compare reasoning with and without the import | New command |
| Structural conjunction, disjunction | ?n includes ?c if ?n has every one of ?c's defining links: a "for every" a fixed pattern can't say | New engine machinery |
| Preference, normal defaults, abduction | Non-monotonic, applied "only after all others" | New engine machinery |
| Probes, saturation, extensional semantics | Enumerate admissible probes: clingo choice rules give one answer set per probe | New engine machinery (clingo) |

## New machinery needed

Three of these touch the engines; the rest are a plugin, a decorator and commands.

1. **"For every defining link" (structural connectives).** ?n includes conjunction ?c when ?n has every link ?c is defined by, however many. The obvious encoding ("not all", then negate) recurses through negation, which Nemo and CLIPS refuse. But the condition is monotone, so it can be written without negation: export each connective's defining links numbered 1..k, and check them with a positive recursive chain. That is about six rules in each of the four rule bases, and it stays stratified. The same mechanism carries marks through connectives. The alternative is a general "for every" element in SN patterns, which ordinary models could use too, at roughly twice the work.
2. **Defeasible inference.** Preference exclusions apply "only after all others" and can be blocked, so they are genuinely non-monotonic. Options: (a) clingo only, with ASP defaults and cautious (skeptical) consequences, since clingo can intersect answer sets; (b) a Python loop around any engine: strict closure, then the unblocked defaults, repeated to a fixpoint (order-sensitive when defaults conflict); (c) Prolog's well-founded semantics, which leaves conflicts undefined. The data's default/, Nonmonotonic/ (Lehmann 1995, Stalnaker) and "choice of normalcy" nets are the test cases.
3. **Probe enumeration.** An admissible probe is a choice of links from a new bottom node that is closed under the patterns and adds no new inconsistency. clingo choice rules enumerate them, one answer set each: 2^n in the worst case, fine for nets the size of the paper's figures. Show them as a grid of probes by nodes, as Rep Plus does with .rgrid files. Reconstructing links from probes (A → B iff πA ⊆ πB) is then plain Python.
4. **A marks decorator.** A Decorator that draws a vertical bar (true), a horizontal bar (false) or both beside a node, coloured by provenance: brown asserted, black or blue true, grey or green false. Plugins can't add decorators today (hooks cover labels, double-click and menus), so this is core code or a new generic hook.
5. **Two mark kinds** for heavy and double arrowheads, registered in `util.lineMarks` (pythonUtils).
6. **An .rnet importer** as a plugin, like XML Reader: nodes with positions, sizes and node-type looks; link types as relation types with their terminators, mid marks and colours; asserted links as relations; marks as attributes; derived links and marks kept aside as expected results. Labels repeat across a file's panels (CNet keys nodes by index, not label), so each node gets a unique name and keeps its label as `vis/label`.
7. **Commands:** minimise (transitive reduction), maximise, check an import or merge, add an anonymous node, factor links.

## Effort and phasing

About 16 to 25 working days in all, at this project's usual pace; phases 1 to 3 (about a week) already put the test nets in semanticNets with the kernel inference and marks working. Each phase is usable on its own, and the later ones wait on decisions below.

| Phase | What | Engines touched | Days |
| --- | --- | --- | --- |
| 1 | .rnet importer plugin (and .rgrid, optionally) | None | 2–3 |
| 2 | Kernel rules model and its tests against the data's pattern nets | None (rules) | 1–2 |
| 3 | Marks: attributes, propagation rules, decorator, menu items | None (rules) | 2 |
| 4 | Structural conjunction and disjunction, their arrowheads, marks through them | All four | 3–5 |
| 5 | Preference, normal defaults, abduction | clingo first | 4–6 |
| 6 | Probes and saturation, canonical forms, import and merge checks | clingo | 3–5 |
| 7 | Protoconnective notation, expansion and factoring commands, existential status | None | 1–2 |

Risks:

- **Semantics the paper leaves open**, mainly defaults and marks through connectives. The saved derived links and marks in the data show what KNet actually did, so mismatches will show up in tests.
- **Four-engine parity.** Every engine-level feature costs four ports plus the shared ReasonerSpec tests. Allowing clingo-only features would roughly halve phases 4 to 6.
- **Reflexive loops.** Every node includes itself; the views must hide these or they swamp the picture.
- **Probe blow-up.** Saturation is exponential in the number of nodes; it needs a size limit and a clear message.

## The Rep Plus 2 test data

The folder holds 1,496 nets (.rnet, mostly last saved between 2008 and 2024; 1,316 in format version 9, the rest in 6 to 8) and 336 repertory grids (.rgrid), plus figures, Word files and PDFs. The nets closest to the paper are in Nets-CNet-Dev/knets/paper (inference patterns, structural, paper1/default, probes, states of affairs, clens) and Logic Paper 2024. Each net names the script that reasoned over it: /CNet/ (992 files) or /KNet/ (188).

**.rnet** is UTF-8 text (with a BOM), CR line ends, tab-separated. A header line (`C`, the format version, the background colour) is followed by counted sections:

| Section | One line per | Fields |
| --- | --- | --- |
| D | setting | Key and value: Date, Time, Place, InteractScript, LastScript, NodeType, Window |
| T | node type | Shape, font, size, flags, colours, name (Concept, Entity, Relation, Set, Context:, Title, Note, Grid, ...) |
| A | link type (defined per file) | Head shape (0 none, 1 arrow, 2 heavy, 3 double, 6 generic), head bars (0 inclusion, 1 exclusion, 2 coexclusion), the same two for the tail, line style flags, middle symbol (exclusion, coexclusion, negation, prohibited, preference), four colours, name (Includes, Excludes, Coexcludes, Conjunct includes, Disjunct includes, Negates symmetric, Prefer, and "derived" and "reverse" variants) |
| M | mark kind | Colour, background, name: Asserted (brown), Included (black), Irrelevant (grey), Excluded (green), Coexcluded (blue), Definition, Necessary, Default (purple) |
| N | node | Type (high bits are flags), marks, x, y, width, height, label, extra text. A `P` prefix is a picture node (a base64 PNG and its original path); a `G` prefix is a drawing node, followed by vector records (R, G, L, T) |
| L | pair of nodes | Source index, destination index, a space-separated list of link types (parallel links, the repetition pattern), sometimes a weight |
| G | group (a figure panel) | Node indices, and optionally nested groups |

The marks field is hex. Bits 0–1 are the truth value (1 true, 2 false, 3 both), 0x80 means marked and 0x20 derived, and the next byte indexes the M table, which gives the provenance colour. So 81 is asserted true, 1A1 derived true by inclusion, 3A2 derived false by exclusion. Bit 0x40, set on most derived marks, and a rare third byte are still unexplained.

I checked this by parsing every net: in 1,490 of 1,496 files every node type, link, link type and group index is in range. Of the other six, five (in one NASA folder) use a variant the parser doesn't read yet, and one has a group that points past the last node. Rendering three nets (mark propagation, exclusion patterns, structural) reproduced the paper's figures, marks in the paper's colours included.

**.rgrid** is also tab-separated text: a header (Grid, version 8# or 9#, name, date, place, program version), C lines for constructs (R rating, C categorical, F, I) with their poles or categories, E lines for elements with their values, D lines for defined constructs (not fully decoded), and `_Key` settings (\_Context, the element and construct nouns, window, style). Grid nodes in nets point to .rgrid files, and a grid's elements play the part of probes.

## Do we need the Xojo code?

Not for reading the files: the nets, their link types, marks and groups decode without it, and so do the grids' constructs and elements. It would settle a few leftovers: mark bit 0x40 and the rare third byte, the line-style flag bits in the link-type table, the drawing records in drawing nodes, and the grids' D lines.

What would be worth much more is the code that reasons over the nets: the /CNet/ and /KNet/ scripts each file names. It would pin down what the paper leaves informal, such as how defaults and the connectives behave. Some saved nets carry a status line like "Worlds=6 Inference calls=373", which suggests KNet reasons over enumerated worlds, close to the paper's probes. If the regrid code includes that, it's worth sending; if it only translates the files, it isn't needed.

## Decisions for Rob

Each has a recommendation; none blocks phases 1 to 3.

1. **Where it lives.** Recommended: a KNets plugin (importer, rules model, commands), like XML Reader. The generic pieces go where the project's rule puts them: mark kinds and graph routines in pythonUtils, the decorator hook in the core.
2. **Engine parity.** Must every KNet feature run on all four engines? Recommended: the kernel, marks and connectives on all four; defaults and probes on clingo first, with the others to follow if wanted.
3. **How to say "for every".** Recommended: the numbered-links encoding inside the engines first. A general "for every" element in SN patterns is worth it only if ordinary models want it too.
4. **Inclusion as its own relation type, not isa.** Recommended, for the cycle and inheritance reasons in the mapping table. The cost: KNet nets don't get the isa-based tree layouts for free.
5. **What defaults mean.** Skeptical (what every reading supports) or credulous (what some reading supports), and how KNet itself chose. This one may need Brian's intent or the KNet code.
