;################################################################################
; (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
;################################################################################
;
; Rule base for sn.model.clipsReasoner.ClipsReasoner (CLIPS: a forward-chaining
; production system; see https://www.clipsrules.net, and clipspy, its Python
; bindings).
;
; A port of clingoReasoner.lp, rule for rule: see there for what each rule
; means. Every fact is an ordered fact, (predicate arg ...), as clingo's
; predicate(arg,...). CLIPS matches a rule's conditions in order, keeping
; every partial match: so each condition shares variables with those before
; it (the engine orders the model's rules' conditions so too: see
; ClipsReasoner._ordered()). Where CLIPS differs from clingo:
;
;   - Every GraphObject is a symbol #N; a symbol (out, symmetric, ...) a
;     symbol; a string a string; true and false are TRUE and FALSE.
;   - A rule fires as soon as its conditions match: a (not ...) is only right
;     once what it tests is complete. So each rule's salience is set by its
;     stratum (see ClipsReasoner._stratify(), which also checks that the
;     rules, with the model's, are stratified): the rules that conclude what a
;     rule tests with (not ...) have all fired before it does. Leave the
;     saliences out here.
;   - There are no function terms. An object a rule creates is a symbol,
;     %new:K:#V0:#V1... (one per match of the rule), and one a cardinality
;     creates %card:#T:of:#X (or "to"): see ClipsReasoner._value().
;   - A violation's arguments are the fact's last fields:
;     (violation Code Severity Subject Arg ...).
;   - CLIPS has no aggregates: the cardinality violations that count (too
;     many, too few) are counted in Python, from the holds, card, card_of,
;     card_counted and individual facts here (see ClipsReasoner._counted()).
;   - A rule's negated attribute test is about the attributes the model gives
;     (attr_base, as for Nemo: see nemoReasoner.rls), so that the program
;     stays stratified.
;
; ---- Input facts, see sn.model.reasoner.Reasoner.facts() -----------------------------
;   As clingoReasoner.lp's, but attr(O,K,V) is given as (attr_base O K V) (attr
;   is that and what the rules conclude).
;
; ---- Output ------------------------------------------------------------------
;   As clingoReasoner.lp's: isa_data, holds, inferred, inherited, classify,
;   violation, fired, rule_attr, rule_isa, rule_new, same.

(defrule type (obj ?o) (not (individual ?o)) => (assert (type ?o)))
(defrule rel_type (kind ?t relation) (type ?t) => (assert (rel_type ?t)))

; Pattern elements describe patterns, not the world (see clingoReasoner.lp).
(defrule data (obj ?x) (not (pattern ?x)) => (assert (data ?x)))

; The objects the rules create are data, but not base data: the variables of
; rules that create objects range over base data only.
(defrule base (obj ?x) (not (pattern ?x)) => (assert (base ?x)))
(defrule data-new (rule_new ?n) => (assert (data ?n)))
(defrule any_individual (individual ?x) => (assert (any_individual ?x)))
(defrule any_individual-new (rule_new ?n) => (assert (any_individual ?n)))

;;; Type hierarchy ------------------------------------------------------------

(defrule isa_star-self (obj ?x) => (assert (isa_star ?x ?x)))
(defrule isa_star (parent ?x ?y) (isa_star ?y ?z) => (assert (isa_star ?x ?z)))
(defrule isa_star-new (rule_new ?n) => (assert (isa_star ?n ?n)))
(defrule isa_star-rule (rule_isa ? ?x ?y) (isa_star ?y ?z) => (assert (isa_star ?x ?z)))
(defrule isa_base-self (obj ?x) => (assert (isa_base ?x ?x)))
(defrule isa_base (parent ?x ?y) (isa_base ?y ?z) => (assert (isa_base ?x ?z)))

;;; Relations -----------------------------------------------------------------

(defrule asserted (link ?r ?s ?d) (parent ?r ?t) (rel_type ?t) => (assert (asserted ?t ?s ?d)))
(defrule asserted_under (asserted ?t2 ?s ?d) (isa_base ?t2 ?t) (rel_type ?t) => (assert (asserted_under ?t ?s ?d)))

; Relations inherit down the isa hierarchy from their source, unless refined.
(defrule link_holds (asserted ?t ?s ?d) => (assert (link_holds ?t ?s ?d)))
(defrule link_holds-inherit (link_holds ?t ?s ?d) (parent ?x ?s) (data ?x) (not (refined ?t ?x ?d))
  => (assert (link_holds ?t ?x ?d)))
(defrule link_holds-rule_isa (link_holds ?t ?s ?d) (rule_isa ? ?x ?s) (data ?x) (not (refined ?t ?x ?d))
  => (assert (link_holds ?t ?x ?d)))
(defrule refined (asserted ?t ? ?d) (rel_type ?t2) (isa_base ?t2 ?t) (isa_base ?d2 ?d) (asserted ?t2 ?x ?d2)
    (test (or (neq ?t2 ?t) (neq ?d2 ?d)))
  => (assert (refined ?t ?x ?d)))
(defrule inherited (link_holds ?t ?x ?d) (not (asserted ?t ?x ?d)) => (assert (inherited ?t ?x ?d)))

(defrule holds (link_holds ?t ?s ?d) => (assert (holds ?t ?s ?d)))
(defrule holds-fired (fired ? ?t ?s ?d) => (assert (holds ?t ?s ?d)))
(defrule holds-up (holds ?t ?s ?d) (parent ?t ?t2) (rel_type ?t2) => (assert (holds ?t2 ?s ?d)))

; (The relational properties are in the base rules: see clingoReasoner.lp.)

(defrule sub_holds (holds ?t2 ?s ?d) (parent ?t2 ?t) (rel_type ?t2) => (assert (sub_holds ?t ?s ?d)))
(defrule inferred (holds ?t ?s ?d) (not (asserted ?t ?s ?d)) (not (sub_holds ?t ?s ?d))
  => (assert (inferred ?t ?s ?d)))

;;; Signatures (domain/range) and classification ------------------------------

(defrule needs_src (src ?r ?s) (isa_star ?r ?t&~?r) (domain ?t ?c) (not (isa_star ?s ?c))
  => (assert (needs_src ?r ?t ?c)))
(defrule needs_dst (dst ?r ?d) (isa_star ?r ?t&~?r) (range ?t ?c) (not (isa_star ?d ?c))
  => (assert (needs_dst ?r ?t ?c)))

(defrule need-src (needs_src ?r ? ?c) (src ?r ?s) (data ?r) (data ?s) => (assert (need ?s ?c)))
(defrule need-dst (needs_dst ?r ? ?c) (dst ?r ?d) (data ?r) (data ?d) => (assert (need ?d ?c)))
(defrule classify (need ?x ?c) (not (need_more_specific ?x ?c)) => (assert (classify ?x ?c)))
(defrule need_more_specific (need ?x ?c) (need ?x ?c2&~?c) (isa_star ?c2 ?c) => (assert (need_more_specific ?x ?c)))

;;; Violations ----------------------------------------------------------------

(defrule domain-violation (needs_src ?r ?t ?c) (src ?r ?s) => (assert (violation0 domain error ?r ?t ?s ?c)))
(defrule range-violation (needs_dst ?r ?t ?c) (dst ?r ?d) => (assert (violation0 range error ?r ?t ?d ?c)))

(defrule isa_cycle (parent ?x ?p) (isa_star ?p ?x) => (assert (violation0 isa_cycle error ?x ?p)))
(defrule isa_individual_parent (parent ?x ?p) (individual ?p) => (assert (violation0 isa_individual_parent error ?x ?p)))
(defrule redundant_parent (parent ?x ?p1) (parent ?x ?p2&~?p1) (isa_star ?p1 ?p2) (not (isa_star ?p2 ?p1))
  => (assert (violation0 redundant_parent warning ?x ?p1 ?p2)))

(defrule node_isa_relation (kind ?x node) (const relation ?r) (isa_star ?x ?r)
  => (assert (violation0 node_isa_relation error ?x ?r)))
(defrule relation_isa_node (kind ?x relation) (const node ?n) (isa_star ?x ?n)
  => (assert (violation0 relation_isa_node error ?x ?n)))

(defrule has_lsrc (lsrc ?r ?) => (assert (has_lsrc ?r)))
(defrule has_ldst (ldst ?r ?) => (assert (has_ldst ?r)))
(defrule unset_endpoint-src (kind ?r relation) (individual ?r) (not (has_lsrc ?r))
  => (assert (violation0 unset_endpoint warning ?r src)))
(defrule unset_endpoint-dst (kind ?r relation) (individual ?r) (not (has_ldst ?r))
  => (assert (violation0 unset_endpoint warning ?r dst)))

;;; Cardinality ---------------------------------------------------------------

(defrule new_obj (rule_new ?n) => (assert (new_obj ?n)))

; At most one: objects that must be the same.
(defrule same-out (card ?t out ? 1) (new_obj ?d1) (holds ?t ?s ?d1) (holds ?t ?s ?d2&~?d1) => (assert (same ?d1 ?d2)))
(defrule same-in (card ?t in ? 1) (new_obj ?s1) (holds ?t ?s1 ?d) (holds ?t ?s2&~?s1 ?d) => (assert (same ?s1 ?s2)))
(defrule same-symmetric (same ?y ?x) => (assert (same ?x ?y)))
(defrule same-transitive (same ?x ?y) (same ?y ?z&~?x) => (assert (same ?x ?z)))
(defrule same-holds-dst (same ?x ?y) (holds ?t ?s ?x) => (assert (holds ?t ?s ?y)))
(defrule same-holds-src (same ?x ?y) (holds ?t ?x ?d) => (assert (holds ?t ?y ?d)))
(defrule same-attr (same ?x ?y) (attr ?x ?k ?v) => (assert (attr ?y ?k ?v)))
(defrule same-isa (same ?x ?y) (isa_star ?x ?t&~?x) => (assert (isa_star ?y ?t)))

; Exactly one: an object of the model's that has none gets a new one.
(defrule card_top (const top ?c) => (assert (card_top ?c)))
(defrule card_of-out (card ?t out ?min&:(> ?min 0) ?) (domain ?t ?c) (not (card_top ?c))
    (isa_star ?x ?c) (base ?x) (individual ?x) (kind ?x node)
  => (assert (card_of ?t out ?x)))
(defrule card_of-in (card ?t in ?min&:(> ?min 0) ?) (range ?t ?c) (not (card_top ?c))
    (isa_star ?x ?c) (base ?x) (individual ?x) (kind ?x node)
  => (assert (card_of ?t in ?x)))
(defrule card_has-out (asserted_under ?t ?x ?) => (assert (card_has ?t out ?x)))
(defrule card_has-in (asserted_under ?t ? ?x) => (assert (card_has ?t in ?x)))
(defrule card_new (card_of ?t ?dir ?x) (card ?t ?dir ? 1) (not (card_has ?t ?dir ?x)) => (assert (card_new ?t ?dir ?x)))
; (clingo's new(T,Name,(("of",X),)): see ClipsReasoner._value())
(defrule card_obj-out (card_new ?t out ?x) => (assert (card_obj ?t out ?x (sym-cat "%card:" ?t ":of:" ?x))))
(defrule card_obj-in (card_new ?t in ?x) => (assert (card_obj ?t in ?x (sym-cat "%card:" ?t ":to:" ?x))))
(defrule card_obj-new (card_obj ? ? ? ?n) => (assert (rule_new ?n)))
(defrule card_obj-fired-out (card_obj ?t out ?x ?n) => (assert (fired ?t ?t ?x ?n)))
(defrule card_obj-isa-out (card_obj ?t out ? ?n) (range ?t ?c) (not (card_top ?c)) => (assert (rule_isa ?t ?n ?c)))
(defrule card_obj-fired-in (card_obj ?t in ?x ?n) => (assert (fired ?t ?t ?n ?x)))
(defrule card_obj-isa-in (card_obj ?t in ? ?n) (domain ?t ?c) (not (card_top ?c)) => (assert (rule_isa ?t ?n ?c)))

; Too many, too few: counted in Python (see above). A merged new object is
; counted once: as the object it's the same as, or as the first of those that
; are the same (by name order).
(defrule card_counted (obj ?d) => (assert (card_counted ?d)))
(defrule card_counted-new (new_obj ?n) (not (card_merged ?n)) => (assert (card_counted ?n)))
(defrule card_merged (same ?n ?x) (obj ?x) (new_obj ?n) => (assert (card_merged ?n)))
(defrule card_merged-new (same ?n ?x) (new_obj ?n) (new_obj ?x) (test (< (str-compare ?x ?n) 0))
  => (assert (card_merged ?n)))
(defrule bad_cardinality (card_error ?t ?k ?m) => (assert (violation0 bad_cardinality warning ?t ?k ?m)))

;;; Attributes -----------------------------------------------------------------

(defrule attr (attr_base ?o ?k ?v) => (assert (attr ?o ?k ?v)))
(defrule attr-rule (rule_attr ? ?x ?k ?v) => (assert (attr ?x ?k ?v)))

;;; Nodes defined by their links (Gaines's structural connectives) --------------
; See clingoReasoner.lp.

(defrule def_ok-meet (def_part ?c meet 1 ?a ?p ?) (holds ?p ?x ?a) => (assert (def_ok ?c meet ?x 1)))
(defrule def_ok-meet-self (def_part ?c meet 1 ?a ? pos) => (assert (def_ok ?c meet ?a 1)))
(defrule def_ok-meet-next (def_ok ?c meet ?x ?i) (def_part ?c meet =(+ ?i 1) ?a ?p ?) (holds ?p ?x ?a)
  => (assert (def_ok ?c meet ?x (+ ?i 1))))
(defrule def_ok-meet-next-self (def_ok ?c meet ?a ?i) (def_part ?c meet =(+ ?i 1) ?a ? pos)
  => (assert (def_ok ?c meet ?a (+ ?i 1))))
(defrule def_ok-join (def_part ?c join 1 ?a ?p ?) (holds ?p ?a ?x) => (assert (def_ok ?c join ?x 1)))
(defrule def_ok-join-self (def_part ?c join 1 ?a ? pos) => (assert (def_ok ?c join ?a 1)))
(defrule def_ok-join-next (def_ok ?c join ?x ?i) (def_part ?c join =(+ ?i 1) ?a ?p ?) (holds ?p ?a ?x)
  => (assert (def_ok ?c join ?x (+ ?i 1))))
(defrule def_ok-join-next-self (def_ok ?c join ?a ?i) (def_part ?c join =(+ ?i 1) ?a ? pos)
  => (assert (def_ok ?c join ?a (+ ?i 1))))
(defrule def-meet (def_last ?c meet ?n ?q ?r) (def_ok ?c meet ?x&~?c ?n) => (assert (fired ?r ?q ?x ?c)))
(defrule def-join (def_last ?c join ?n ?q ?r) (def_ok ?c join ?x&~?c ?n) => (assert (fired ?r ?q ?c ?x)))

(defrule def_key-pos (def_part ?c ?d ?i ?a ? pos) (def_marks ?c ?d ?tk ?fk ?) => (assert (def_key ?c ?d ?i ?a ?tk ?fk)))
(defrule def_key-neg (def_part ?c ?d ?i ?a ? neg) (def_marks ?c ?d ?tk ?fk ?) => (assert (def_key ?c ?d ?i ?a ?fk ?tk)))
(defrule def_holds (def_key ?c ?d ?i ?a ?y ?) (attr ?a ?y ?) => (assert (def_holds ?c ?d ?i)))
(defrule def_fails (def_key ?c ?d ?i ?a ? ?n) (attr ?a ?n ?) => (assert (def_fails ?c ?d ?i)))
(defrule def_hpre-0 (def_marks ?c ?d ? ? ?) => (assert (def_hpre ?c ?d 0)))
(defrule def_hpre (def_hpre ?c ?d ?h) (def_holds ?c ?d =(+ ?h 1)) => (assert (def_hpre ?c ?d (+ ?h 1))))
(defrule def_hsuf-0 (def_marks ?c ?d ? ? ?) (def_last ?c ?d ?n ? ?) => (assert (def_hsuf ?c ?d (+ ?n 1))))
(defrule def_hsuf (def_hsuf ?c ?d ?h) (def_holds ?c ?d =(- ?h 1)) => (assert (def_hsuf ?c ?d (- ?h 1))))
(defrule def_fpre-0 (def_marks ?c ?d ? ? ?) => (assert (def_fpre ?c ?d 0)))
(defrule def_fpre (def_fpre ?c ?d ?h) (def_fails ?c ?d =(+ ?h 1)) => (assert (def_fpre ?c ?d (+ ?h 1))))
(defrule def_fsuf-0 (def_marks ?c ?d ? ? ?) (def_last ?c ?d ?n ? ?) => (assert (def_fsuf ?c ?d (+ ?n 1))))
(defrule def_fsuf (def_fsuf ?c ?d ?h) (def_fails ?c ?d =(- ?h 1)) => (assert (def_fsuf ?c ?d (- ?h 1))))
(defrule def-meet-true (def_last ?c meet ?n ? ?r) (def_hpre ?c meet ?n) (def_marks ?c meet ?tk ? ?v)
  => (assert (rule_attr ?r ?c ?tk ?v)))
(defrule def-join-false (def_last ?c join ?n ? ?r) (def_fpre ?c join ?n) (def_marks ?c join ? ?fk ?v)
  => (assert (rule_attr ?r ?c ?fk ?v)))
(defrule def-meet-fails (def_marks ?c meet ? ?fk ?v) (attr ?c ?fk ?) (def_key ?c meet ?i ?a ? ?n) (not (def_mixed ?c meet))
    (def_hpre ?c meet =(- ?i 1)) (def_hsuf ?c meet =(+ ?i 1)) (def_last ?c meet ? ? ?r)
  => (assert (rule_attr ?r ?a ?n ?v)))
(defrule def-join-holds (def_marks ?c join ?tk ? ?v) (attr ?c ?tk ?) (def_key ?c join ?i ?a ?y ?) (not (def_mixed ?c join))
    (def_fpre ?c join =(- ?i 1)) (def_fsuf ?c join =(+ ?i 1)) (def_last ?c join ? ? ?r)
  => (assert (rule_attr ?r ?a ?y ?v)))

; Report only violations about the data.
(defrule violation (violation0 ?c ?s ?x $?args) (data ?x) => (assert (violation ?c ?s ?x $?args)))

; A variable whose name says what it ranges over, though the object is the other.
(defrule variable_kind-individual (var_kind ?x individual) (type ?x)
  => (assert (violation variable_kind warning ?x individual "a type")))
(defrule variable_kind-type (var_kind ?x type) (individual ?x)
  => (assert (violation variable_kind warning ?x type "an individual")))

; The isa closure, as reported: data only.
(defrule isa_data (isa_star ?x ?t) (data ?x) => (assert (isa_data ?x ?t)))
