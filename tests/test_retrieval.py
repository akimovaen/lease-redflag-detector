from lease_redflag_detector.extraction.schema import RedFlag, RedFlagType
from lease_redflag_detector.rag.chunking import Chunk
from lease_redflag_detector.rag.redline_search import (
    ROLES,
    TOPICS,
    RedlineSearch,
    build_query,
)
from lease_redflag_detector.rag.retrieve import Filters, Hit, rrf

POLICY = {"type": "policy", "status": "current"}
CIVIL_CODE = {"type": "law", "status": "current"}
STATE_LAW = {"type": "law", "status": "current", "regime": "law_157_ix"}
STATE_LEASE = {"type": "lease", "status": "current", "regime": "law_157_ix"}
LEASE = {"type": "lease", "status": "current", "regime": "civil_code"}
OLD_POLICY = {"type": "policy", "status": "outdated"}


def test_default_filter_keeps_documents_in_force():
    assert Filters().matches(POLICY)
    assert not Filters().matches(OLD_POLICY)
    assert Filters(status=None).matches(OLD_POLICY)


def test_excluded_regime_drops_only_documents_of_that_regime():
    filters = Filters(types=["law", "lease"], exclude_regimes=["law_157_ix"])
    assert filters.matches(CIVIL_CODE)  # no regime
    assert filters.matches(LEASE)
    assert not filters.matches(STATE_LAW)
    assert not filters.matches(STATE_LEASE)


def test_excluded_regime_is_a_must_not_condition_in_qdrant():
    query = Filters(exclude_regimes=["law_157_ix"]).to_qdrant()
    assert [c.key for c in query.must] == ["status"]
    assert [c.key for c in query.must_not] == ["regime"]
    assert Filters(status=None).to_qdrant() is None


def test_rrf_rewards_items_high_in_both_lists():
    fused = rrf([[1, 2, 3], [3, 1, 4]])
    assert [item for item, _ in fused][:2] == [1, 3]


def test_roles_search_the_sources_meant_for_them():
    roles = {role.name: role.filters for role in ROLES}
    assert roles["position"].matches(POLICY)
    assert not roles["position"].matches(OLD_POLICY)
    assert roles["law"].matches(CIVIL_CODE)
    assert not roles["law"].matches(STATE_LAW)
    assert roles["market"].matches(LEASE)
    assert not roles["market"].matches(STATE_LEASE)
    assert not any(
        f.matches({"type": "marketing", "status": "current"}) for f in roles.values()
    )


def test_every_red_flag_type_has_a_topic_in_the_query():
    assert set(TOPICS) == set(RedFlagType)
    flag = RedFlag(
        type=RedFlagType.SUBLEASE_PERMITTED, quote="Орендар може здати в суборенду."
    )
    query = build_query(flag)
    assert query.startswith("Орендар може здати в суборенду.")
    assert "згоди орендодавця" in query


def test_the_lease_of_the_clause_is_not_its_own_source():
    own = Chunk("lease_1#000", "lease_1", "", [], 10, {})
    other = Chunk("lease_2#000", "lease_2", "", [], 10, {})

    class Retriever:
        def search(self, *args, **kwargs):
            return [Hit(own, 0.9), Hit(other, 0.8)]

    hits = RedlineSearch(Retriever()).search(
        RedFlag(type="sublease_permitted", quote="Орендар може."), exclude_doc="lease_1"
    )
    assert all([h.chunk.doc_id for h in role] == ["lease_2"] for role in hits.values())
