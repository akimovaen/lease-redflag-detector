"""Search the corpus for a red flag found by the stage 1 extractor, source by source.

A redline proposal has parts, and each part rests on its own kind of source:

- **position**: what the landlord's policy requires, i.e. what is wrong with the clause;
- **wording**: the approved clauses to base the changed clause on;
- **law**: the acts that bound the change (which rules are mandatory, caps on penalties);
- **precedent**: deviations the lease committee has approved before;
- **market**: market research and signed leases, as background only.

One ranked list over the whole corpus lets one kind crowd out another (leases of state
property pushed the Civil Code out of the top 10 in the retrieval evaluation), so every
role is searched on its own with a metadata filter and its own k. Conflicts between the
sources are resolved later, in generation, not by ranking here.

The query is the clause and a short Ukrainian description of the red flag type: a
clause on sublease often never says "згода", while the policy is about consent.
Hits the reranker scores below `min_score` are dropped, so a role with nothing relevant
(most red flags have no precedent) comes back empty instead of padded with noise.

    uv run python -m lease_redflag_detector.rag.redline_search sublease_permitted \
        "Орендар має право передавати приміщення в суборенду без згоди Орендодавця."
"""

from dataclasses import dataclass, field

from lease_redflag_detector.extraction.schema import RedFlag, RedFlagType
from lease_redflag_detector.rag.retrieve import Filters, Hit, Retriever, load_chunks

# State-property acts and leases follow Law 157-IX; the landlord's leases do not.
STATE_PROPERTY = ["law_157_ix"]
# Fewer reranked candidates than in the general search: one kind of source is searched.
RERANK_CANDIDATES = 15
# The reranker's sigmoid score below which a hit is not relevant. On the first red flags
# unrelated minutes scored up to 0.004, a related item packed with others 0.02.
# To be tuned on the red flag retrieval set.
MIN_SCORE = 0.05


@dataclass(frozen=True)
class Role:
    name: str
    k: int
    filters: Filters = field(default_factory=Filters)


ROLES = (
    Role("position", 3, Filters(types=["policy"])),
    Role("wording", 2, Filters(types=["clause_library"])),
    Role("law", 3, Filters(types=["law"], exclude_regimes=STATE_PROPERTY)),
    Role("precedent", 2, Filters(types=["minutes"])),
    Role(
        "market",
        2,
        Filters(types=["research", "lease"], exclude_regimes=STATE_PROPERTY),
    ),
)

# What each red flag type is about, in the words of the corpus (policy, Civil Code).
TOPICS = {
    RedFlagType.LANDLORD_REPAIRS: (
        "Орендодавець бере на себе поточний ремонт, утримання інженерних систем "
        "і обладнання приміщення. Хто проводить і оплачує поточний і капітальний "
        "ремонт орендованого приміщення."
    ),
    RedFlagType.SERVICE_CHARGES_LIMITED: (
        "Експлуатаційні витрати, комунальні послуги, податки і страхування несе "
        "орендодавець, вони включені в орендну плату або відшкодування їх орендарем "
        "обмежене. Відшкодування орендарем експлуатаційних витрат."
    ),
    RedFlagType.TENANT_BREAK_OPTION: (
        "Орендар має право достроково в односторонньому порядку відмовитися від "
        "договору оренди. Дострокове розірвання договору з ініціативи орендаря, "
        "строк попередження, компенсація орендодавцю."
    ),
    RedFlagType.INDEXATION_LIMITED: (
        "Орендна плата не змінюється, її індексація обмежена або потребує згоди "
        "орендаря. Щорічна індексація орендної плати, граничний розмір індексації."
    ),
    RedFlagType.SUBLEASE_PERMITTED: (
        "Орендар може передати приміщення в суборенду або відступити права за "
        "договором без згоди орендодавця. Згода орендодавця на суборенду."
    ),
}


def build_query(red_flag: RedFlag, topic: bool = True) -> str:
    """The clause, followed by the description of its red flag type unless `topic` is
    false (the evaluation compares the two)."""
    return f"{red_flag.quote}\n{TOPICS[red_flag.type]}" if topic else red_flag.quote


class RedlineSearch:
    def __init__(
        self, retriever: Retriever, min_score: float = MIN_SCORE, topic: bool = True
    ):
        self.retriever = retriever
        self.min_score = min_score
        self.topic = topic

    def search(self, red_flag: RedFlag) -> dict[str, list[Hit]]:
        """The hits for every role, best first; a role may come back empty."""
        query = build_query(red_flag, self.topic)
        return {
            role.name: [
                hit
                for hit in self.retriever.search(
                    query,
                    "hybrid_rerank",
                    role.k,
                    role.filters,
                    rerank_candidates=RERANK_CANDIDATES,
                )
                if hit.score >= self.min_score
            ]
            for role in ROLES
        }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Search the corpus for a red flag.")
    parser.add_argument("type", choices=[t.value for t in RedFlagType])
    parser.add_argument("quote", help="the clause that raises the flag")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE)
    args = parser.parse_args()

    search = RedlineSearch(Retriever(load_chunks()), args.min_score)
    red_flag = RedFlag(type=args.type, quote=args.quote)
    for role, hits in search.search(red_flag).items():
        print(f"== {role}" + ("" if hits else ": nothing above the threshold"))
        for hit in hits:
            chunk = hit.chunk
            print(f"{hit.score:7.3f}  {chunk.id}  {chunk.context}")
            print("         " + chunk.text[:160].replace("\n", " "))


if __name__ == "__main__":
    main()
