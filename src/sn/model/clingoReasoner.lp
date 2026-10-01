%################################################################################
% (c) Copyright 2026, Rob Kremer, MIT open source license.                      #
%################################################################################
%
% Rule base for sn.model.clingoReasoner.ClingoReasoner (clingo / answer set programming).
%
% Every GraphObject -- node, relation, relation type, isa link -- is reified as
% a term o(N), so relation types participating in the isa hierarchy (and
% relations between relations) are ordinary first-order facts.
%
% ---- Input facts, see sn.model.reasoner.Reasoner.facts() -----------------------------
%   obj(O).                   every GraphObject
%   individual(O).            GraphObject.isIndividual()
%   kind(O,K).                K in top, node, relation, isa
%   collection(O).            O is a Collection (also kind node)
%   name(O,S).                GraphObject.name
%   const(K,O).               well-known objects: top, relation, isa, node, ...
%   parent(X,P).              GraphObject.getParents() (includes the implicit
%                             defaults to node/relation)
%   lsrc(R,C). ldst(R,C).     locally set relation endpoints (Relation.localSrc/.localDst)
%   domain(T,C). range(T,C).  the signature of relation type T (Relation.domain/.range)
%   src(R,S). dst(R,D).       effective endpoints (Relation.src/.dst, inherited)
%   link(R,S,D).              individual, non-isa relation R with both endpoints
%   prop(T,P).                relation type T is tagged with P (reflexive,
%                             irreflexive, symmetric, asymmetric, transitive)
%   member(C,M).              Collection membership
%   pattern(X).               X is a pattern element (see GraphObject.isPatternElement())
%   attr(O,K,V).              effective (local or inherited, per the model's
%                             Restriction rules) non-"vis/" scalar attributes
%   lattr(O,K).               O has K locally
%
% ---- Output ------------------------------------------------------------------
%   isa_data(X,T).            X isa T (reflexive-transitive), X not a pattern element
%   holds(T,S,D).             S is related to D under relation type T
%   inferred(T,S,D).          holds, but neither asserted nor implied by a
%                             more specific relation type
%   inherited(T,X,D).         X -T-> D inherited down the isa hierarchy
%   classify(X,C).            X should be classified under C (most specific)
%   violation(Code,Sev,Subject,Args).
%   fired(Rule,T,S,D).        a user rule concluded S -T-> D
%   rule_attr(Rule,X,K,V).    a user rule concluded that X has attribute K = V
%   rule_isa(Rule,X,T).       a user rule concluded that X isa T
%   rule_new(N).              a user rule concluded that object N exists: N is
%                             new(Rule,Var,Match), one per match of the rule
%
% ---- User rules --------------------------------------------------------------
%   The model's rules (see sn.model.reasoner.ruleOf()) are added to this program
%   as rules concluding fired/4 and rule_attr/4, whose bodies use the predicates
%   here (holds/3, isa_star/2, attr/3, prop/2, ...); see ClingoReasoner._rulesProgram().

type(O) :- obj(O), not individual(O).
rel_type(T) :- kind(T,relation), type(T).

% Pattern elements -- the variables (?x) and relations inside a context (a rule,
% definition or query), and relations involving them -- describe patterns, not
% the world: they're exported marked pattern(X), their relations aren't links,
% and nothing is inferred, classified or reported about them. See
% GraphObject.isPatternElement().
data(X) :- obj(X), not pattern(X).

% The objects the user's rules create (see rule_new/1) are data too -- but not
% "base" data: rules' variables range over base data only, so that a rule
% can't go on creating objects forever. (Queries' variables range over all
% data.)
base(X) :- obj(X), not pattern(X).
data(N) :- rule_new(N).
any_individual(X) :- individual(X).
any_individual(N) :- rule_new(N).

%%% Type hierarchy ------------------------------------------------------------

isa_star(X,X) :- obj(X).
isa_star(X,Z) :- parent(X,Y), isa_star(Y,Z).
% ... including what the user's rules conclude (see rule_isa/3). isa_base is
% the asserted hierarchy alone: what the refinement of inherited relations
% (below) uses under negation, so that the program stays stratified.
isa_star(N,N) :- rule_new(N).
isa_star(X,Z) :- rule_isa(_,X,Y), isa_star(Y,Z).
isa_base(X,X) :- obj(X).
isa_base(X,Z) :- parent(X,Y), isa_base(Y,Z).

%%% Relations -----------------------------------------------------------------

% A relation individual instantiates its parent relation types.
asserted(T,S,D) :- link(R,S,D), parent(R,T), rel_type(T).

% Relations inherit down the isa hierarchy from their source, one isa step at a
% time: dog -has-> tail gives rex -has-> tail. A local relation to a more
% specific destination (rex -has-> tail#12, or rex -hasPart-> stubbyTail where
% hasPart isa has and stubbyTail isa tail) refines -- and so blocks -- the
% inherited one, for the object and everything below it.
link_holds(T,S,D) :- asserted(T,S,D).
link_holds(T,X,D) :- link_holds(T,S,D), parent(X,S), data(X), not refined(T,X,D).
link_holds(T,X,D) :- link_holds(T,S,D), rule_isa(_,X,S), data(X), not refined(T,X,D).
refined(T,X,D) :- asserted(T,_,D), asserted(T2,X,D2), isa_base(T2,T), isa_base(D2,D),
                  (T2,D2) != (T,D).
inherited(T,X,D) :- link_holds(T,X,D), not asserted(T,X,D).

% Every relation type subsumes its sub-relation types (relation hierarchy),
% including their inferred pairs.
holds(T,S,D) :- link_holds(T,S,D).
% What the user's rules conclude holds too -- and so feeds everything else:
% the relation hierarchy, the algebraic properties, other rules, ...
holds(T,S,D) :- fired(_,T,S,D).
holds(T2,S,D) :- holds(T,S,D), parent(T,T2), rel_type(T2).

% Algebraic properties. These are tags on specific relation types and are NOT
% inherited (brother isa sibling, but only sibling is symmetric); brother pairs
% still count as sibling pairs, and so get sibling's symmetric closure.
holds(T,D,S) :- holds(T,S,D), prop(T,symmetric).
holds(T,X,Z) :- holds(T,X,Y), holds(T,Y,Z), prop(T,transitive), not equiv_minus_id(T).
% Symmetric + transitive + irreflexive (eg: full-sibling) means "an equivalence
% minus identity": plain transitivity would force x -T-> x for anything related
% at all (x->y, y->x, so x->x), making the three tags contradictory. So such a
% type's transitivity skips the diagonal. (A transitive, irreflexive type that
% ISN'T symmetric keeps the plain rule: there a self-pair can only come from a
% cycle -- a real error the irreflexive violation should catch.)
equiv_minus_id(T) :- prop(T,symmetric), prop(T,transitive), prop(T,irreflexive).
holds(T,X,Z) :- holds(T,X,Y), holds(T,Y,Z), X != Z, equiv_minus_id(T).
holds(T,X,X) :- holds(T,X,_), prop(T,reflexive).
holds(T,X,X) :- holds(T,_,X), prop(T,reflexive).

% Report only genuinely new pairs, not those that follow by mere subsumption.
sub_holds(T,S,D) :- holds(T2,S,D), parent(T2,T), rel_type(T2).
inferred(T,S,D) :- holds(T,S,D), not asserted(T,S,D), not sub_holds(T,S,D).

%%% Signatures (domain/range) and classification ------------------------------

% A relation type's domain and range are its signature: every relation or
% sub-type below it must have a src that isa the domain, and a dst that isa
% the range.
needs_src(R,T,C) :- src(R,S), isa_star(R,T), R != T, domain(T,C), not isa_star(S,C).
needs_dst(R,T,C) :- dst(R,D), isa_star(R,T), R != T, range(T,C), not isa_star(D,C).

need(S,C) :- needs_src(R,_,C), src(R,S), data(R), data(S).
need(D,C) :- needs_dst(R,_,C), dst(R,D), data(R), data(D).
% Suggest only the most specific type (satisfying it satisfies the others).
classify(X,C) :- need(X,C), not need_more_specific(X,C).
need_more_specific(X,C) :- need(X,C), need(X,C2), C2 != C, isa_star(C2,C).

%%% Violations ----------------------------------------------------------------

violation0(domain, error, R, (T,S,C)) :- needs_src(R,T,C), src(R,S).
violation0(range,  error, R, (T,D,C)) :- needs_dst(R,T,C), dst(R,D).

violation0(isa_cycle, error, X, (P,)) :- parent(X,P), isa_star(P,X).
violation0(isa_individual_parent, error, X, (P,)) :- parent(X,P), individual(P).
violation0(redundant_parent, warning, X, (P1,P2)) :-
    parent(X,P1), parent(X,P2), P1 != P2, isa_star(P1,P2), not isa_star(P2,P1).

violation0(node_isa_relation, error, X, (R,)) :-
    kind(X,node), const(relation,R), isa_star(X,R).
violation0(relation_isa_node, error, X, (N,)) :-
    kind(X,relation), const(node,N), isa_star(X,N).

violation0(irreflexive, error, T, (X,)) :- holds(T,X,X), prop(T,irreflexive).
violation0(asymmetric, error, T, (X,Y)) :- holds(T,X,Y), holds(T,Y,X), X < Y, prop(T,asymmetric).
violation0(asymmetric, error, T, (X,X)) :- holds(T,X,X), prop(T,asymmetric). % asymmetric implies irreflexive
conflicting(reflexive,irreflexive). conflicting(symmetric,asymmetric). conflicting(reflexive,asymmetric).
violation0(property_conflict, error, T, (P,Q)) :- prop(T,P), prop(T,Q), conflicting(P,Q).

% An individual relation without a local endpoint silently takes its type's
% endpoint (ultimately top, from relation) -- almost certainly unintended.
has_lsrc(R) :- lsrc(R,_).
has_ldst(R) :- ldst(R,_).
violation0(unset_endpoint, warning, R, (src,)) :-
    kind(R,relation), individual(R), not has_lsrc(R).
violation0(unset_endpoint, warning, R, (dst,)) :-
    kind(R,relation), individual(R), not has_ldst(R).

%%% User rules' attribute conclusions ------------------------------------------

attr(X,K,V) :- rule_attr(_,X,K,V).

% Report only violations about the data (not about pattern elements).
violation(C,S,X,A) :- violation0(C,S,X,A), data(X).

% The isa closure, as reported: data only (a variable isn't an instance of anything).
isa_data(X,T) :- isa_star(X,T), data(X).
#show isa_data/2.
#show holds/3.
#show inferred/3.
#show inherited/3.
#show classify/2.
#show violation/4.
#show fired/4.
#show rule_attr/4.
#show rule_isa/3.
#show rule_new/1.
