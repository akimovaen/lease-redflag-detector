from lease_redflag_detector.rag.chunking import (
    EMBEDDING_MAX_TOKENS,
    PASSAGE_PREFIX,
    chunk_fixed,
    chunk_structural,
    count_tokens,
    sections,
    split_long_block,
)
from lease_redflag_detector.rag.document import Block, Document


def policy(clause_words: int = 20, clauses: int = 3) -> Document:
    blocks = [Block("heading", "Політика оренди", level=1)]
    for section in (1, 2):
        blocks.append(Block("heading", f"{section}. Розділ {section}", level=2))
        for clause in range(1, clauses + 1):
            words = " ".join(["слово"] * clause_words)
            blocks.append(Block("paragraph", f"{section}.{clause}. {words}."))
    blocks.append(Block("list_item", "пункт списку"))
    return Document("policy", "Політика оренди", blocks, {"type": "policy"})


def test_sections_drop_the_document_title_from_paths():
    paths = [s.path for s in sections(policy())]
    assert paths == [["1. Розділ 1"], ["2. Розділ 2"]]


def test_a_section_that_fits_is_one_chunk_with_its_header():
    chunks = chunk_structural(policy())
    assert len(chunks) == 2
    assert chunks[1].context == "Політика оренди > 2. Розділ 2"
    assert chunks[1].search_text.startswith("Політика оренди > 2. Розділ 2\n2.1.")
    # The list item stays with the clause before it.
    assert chunks[1].text.endswith("\n- пункт списку")
    assert chunks[0].meta["type"] == "policy"


def test_long_sections_are_cut_between_clauses():
    chunks = chunk_structural(
        policy(clause_words=60, clauses=6), target=120, max_tokens=160
    )
    assert len(chunks) > 2
    for chunk in chunks:
        assert chunk.tokens <= 160
        # Every chunk starts at a clause, so no clause is split.
        assert chunk.text.split(". ", 1)[0].replace(".", "").isdigit()


def test_fixed_windows_overlap_and_ignore_structure():
    chunks = chunk_fixed(policy(clause_words=60, clauses=6), size=100, overlap=20)
    assert all(chunk.section_path == [] for chunk in chunks)
    # Re-tokenizing a window cut at token offsets may add a token at its edges.
    assert all(chunk.tokens <= 102 for chunk in chunks)
    assert len(chunks) > 5


def test_signature_stubs_of_contracts_are_dropped():
    blocks = [
        Block("heading", "1. ПРЕДМЕТ ДОГОВОРУ", level=2),
        Block("paragraph", "1.1. Орендодавець передає Орендарю приміщення."),
        Block("heading", "ПІДПИСИ СТОРІН", level=2),
        Block("paragraph", "АКЦІОНЕРНЕ ТОВАРИСТВО ОРЕНДАР:"),
    ]
    lease = Document("lease", "Договір оренди", blocks, {"type": "lease"})
    assert [c.section for c in chunk_structural(lease)] == ["1. ПРЕДМЕТ ДОГОВОРУ"]
    # The same short text outside a contract is kept.
    other = Document("doc", "Документ", blocks, {"type": "policy"})
    assert len(chunk_structural(other)) == 2


def test_header_counts_toward_the_embedding_limit():
    heading = " ".join(["ЗАГОЛОВОК"] * 60)
    blocks = [Block("heading", heading, level=2)]
    blocks += [Block("paragraph", f"{i}. " + "слово " * 80 + ".") for i in range(10)]
    document = Document("doc", "Документ", blocks, {"type": "policy"})
    for chunk in chunk_structural(document):
        full = f"{PASSAGE_PREFIX}{chunk.search_text}"
        assert count_tokens(full) <= EMBEDDING_MAX_TOKENS


def test_a_table_row_too_long_for_a_chunk_is_split():
    rows = [["Орендар", "Документи"], ["1. Орган", "документ; " * 200], ["2. Б", "в"]]
    block = Block("table", "", rows=rows)
    pieces = split_long_block(block, 100)
    assert all(count_tokens(piece) <= 100 for piece in pieces)
    assert pieces[0].startswith("1. Орган | документ;")
    assert pieces[-1] == "| Орендар | Документи |\n|---|---|\n| 2. Б | в |"
