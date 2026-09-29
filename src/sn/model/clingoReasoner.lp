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
%   attr(O,K,V).              effective (local or inherited, per the model's
%                             Restriction rules) non-"vis/" scalar attributes
%   lattr(O,K).               O has K locally
%
% ---- Output ------------------------------------------------------------------
%   isa_star(X,T).            X isa T (reflexive-transitive)
%   holds(T,S,D).             S is related to D under relation type T
%   inferred(T,S,D).          holds, but neither asserted nor implied by a
%                             more specific relation type
%   inherited(T,X,D).         X -T-> D inherited down the isa hierarchy
%   classify(X,C).            X should be classified under C (most specific)
%   violation(Code,Sev,Subject,Args).

type(O) :- obj(O), not individual(O).
rel_type(T) :- kind(T,relation), type(T).

%%% Type hierarchy ------------------------------------------------------------

isa_star(X,X) :- obj(X).
isa_star(X,Z) :- parent(X,Y), isa_star(Y,Z).

%%% Relations -----------------------------------------------------------------

% A relation individual instantiates its parent relation types.
asserted(T,S,D) :- link(R,S,D), parent(R,T), rel_type(T).

% Relations inherit down the isa hierarchy from their source, one isa step at a
% time: dog -has-> tail gives rex -has-> tail. A local relation to a more
% specific destination (rex -has-> tail#12, or rex -hasPart-> stubbyTail where
% hasPart isa has and stubbyTail isa tail) refines -- and so blocks -- the
% inherited one, for the object and everything below it.
link_holds(T,S,D) :- asserted(T,S,D).
link_holds(T,X,D) :- link_holds(T,S,D), parent(X,S), not refined(T,X,D).
refined(T,X,D) :- asserted(T,_,D), asserted(T2,X,D2), isa_star(T2,T), isa_star(D2,D),
                  (T2,D2) != (T,D).
inherited(T,X,D) :- link_holds(T,X,D), not asserted(T,X,D).

% Every relation type subsumes its sub-relation types (relation hierarchy),
% including their inferred pairs.
holds(T,S,D) :- link_holds(T,S,D).
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

need(S,C) :- needs_src(R,_,C), src(R,S).
need(D,C) :- needs_dst(R,_,C), dst(R,D).
% Suggest only the most specific type (satisfying it satisfies the others).
classify(X,C) :- need(X,C), not need_more_specific(X,C).
need_more_specific(X,C) :- need(X,C), need(X,C2), C2 != C, isa_star(C2,C).

%%% Violations ----------------------------------------------------------------

violation(domain, error, R, (T,S,C)) :- needs_src(R,T,C), src(R,S).
violation(range,  error, R, (T,D,C)) :- needs_dst(R,T,C), dst(R,D).

violation(isa_cycle, error, X, (P,)) :- parent(X,P), isa_star(P,X).
violation(isa_individual_parent, error, X, (P,)) :- parent(X,P), individual(P).
violation(redundant_parent, warning, X, (P1,P2)) :-
    parent(X,P1), parent(X,P2), P1 != P2, isa_star(P1,P2), not isa_star(P2,P1).

violation(node_isa_relation, error, X, (R,)) :-
    kind(X,node), const(relation,R), isa_star(X,R).
violation(relation_isa_node, error, X, (N,)) :-
    kind(X,relation), const(node,N), isa_star(X,N).

violation(irreflexive, error, T, (X,)) :- holds(T,X,X), prop(T,irreflexive).
violation(asymmetric, error, T, (X,Y)) :- holds(T,X,Y), holds(T,Y,X), X < Y, prop(T,asymmetric).
violation(asymmetric, error, T, (X,X)) :- holds(T,X,X), prop(T,asymmetric). % asymmetric implies irreflexive
conflicting(reflexive,irreflexive). conflicting(symmetric,asymmetric). conflicting(reflexive,asymmetric).
violation(property_conflict, error, T, (P,Q)) :- prop(T,P), prop(T,Q), conflicting(P,Q).

% An individual relation without a local endpoint silently takes its type's
% endpoint (ultimately top, from relation) -- almost certainly unintended.
has_lsrc(R) :- lsrc(R,_).
has_ldst(R) :- ldst(R,_).
violation(unset_endpoint, warning, R, (src,)) :-
    kind(R,relation), individual(R), not has_lsrc(R).
violation(unset_endpoint, warning, R, (dst,)) :-
    kind(R,relation), individual(R), not has_ldst(R).

#show isa_star/2.
#show holds/3.
#show inferred/3.
#show inherited/3.
#show classify/2.
#show violation/4.
