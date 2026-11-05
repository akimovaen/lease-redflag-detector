from bs4 import BeautifulSoup

from lease_redflag_detector.rag.clean import (
    clean_blocks,
    fix_script,
    normalize,
    pseudonymize,
    vocabulary,
)
from lease_redflag_detector.rag.document import Block
from lease_redflag_detector.rag.extract import (
    is_plain_heading,
    plain_text_blocks,
    rada_table,
    select_sections,
)
from lease_redflag_detector.rag.ingest import shingles, short_name
from lease_redflag_detector.rag.markdown import parse


def test_markdown_structure():
    blocks = parse(
        "# Title\n\n2.1. **Базова позиція.** Текст\nпродовження.\n\n"
        "- пункт\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n> цитата\n"
    )
    assert [b.kind for b in blocks] == [
        "heading",
        "paragraph",
        "list_item",
        "table",
        "quote",
    ]
    assert blocks[1].text == "2.1. **Базова позиція.** Текст продовження."
    assert blocks[3].rows == [["A", "B"], ["1", "2"]]


def test_normalize_fixes_latin_lookalikes_in_cyrillic_words():
    assert normalize("OPEHДA\u00a0за ВІД\u00adПОВІД") == "ОРЕНДА за ВІДПОВІД"
    # Fully Latin words are left alone.
    assert normalize("індекс CPI, код UA") == "індекс CPI, код UA"


def test_fully_latin_words_are_read_by_the_corpus_vocabulary():
    words = vocabulary(["права та обов'язки сторін, товариство, вартості"], min_count=1)
    fixed = fix_script("5. ПРАВА TA ОБОВ'ЯЗКИ CTOPIH; TOBAPHCTBO; BapTocTi", words)
    # "H" is read as "И" where that makes a word: ТОВАРИСТВО, not ТОВАРНСТВО.
    assert fixed == "5. ПРАВА ТА ОБОВ'ЯЗКИ СТОРІН; ТОВАРИСТВО; Вартості"
    # Unknown words, Roman numerals, codes and English text stay as they are.
    words |= {"он", "іх"}
    kept = "Глава IX, код UA, THX, Convention on Combating"
    assert fix_script(kept, words) == kept


def test_clean_drops_ocr_noise():
    blocks = [
        Block("paragraph", "Ї, 22h pany) pS"),
        Block("paragraph", "Орендар сплачує плату."),
    ]
    assert [b.text for b in clean_blocks(blocks)] == ["Орендар сплачує плату."]


def test_pseudonymize_in_one_pass_and_in_capitals():
    pseudonyms = {"Іванц": "Кравц", "Кравц": "Шевц"}
    text = pseudonymize("директора Іванця А.В. / ІВАНЕЦЬ", pseudonyms)
    # The replacement is not replaced again by the second entry.
    assert text == "директора Кравця А.В. / ІВАНЕЦЬ"
    assert pseudonymize("ІВАНЦЯ", pseudonyms) == "КРАВЦЯ"


def test_pseudonymize_masks_ocr_garbled_details():
    text = (
        "IBAN N2UA783057490000002600031165501 в банку; "
        "Ten.: 09111444787, e-mail: o.pinchuk @example.com"
    )
    masked = pseudonymize(text, {})
    assert "N2UA[IBAN] в банку" in masked
    assert "[phone]" in masked and "09111444787" not in masked
    assert "[email]" in masked and "pinchuk" not in masked


def test_plain_text_contract_structure():
    text = (
        "ДОГОВІР ОРЕНДИ\n"
        "1. ПРЕДМЕТ ДОГОВОРУ\n"
        "1.1. Орендодавець передає, а Орендар при-\n"
        "ймає приміщення.\n"
        "- 2 -\n"
        "1.2. Строк оренди 3 роки.\n"
    )
    blocks = plain_text_blocks(text)
    assert [(b.kind, b.level) for b in blocks] == [
        ("heading", 1),
        ("heading", 2),
        ("paragraph", 0),
        ("paragraph", 0),
    ]
    assert blocks[2].text == "1.1. Орендодавець передає, а Орендар приймає приміщення."


def test_select_sections_keeps_heading_subtree():
    blocks = [
        Block("heading", "Глава 57", level=3),
        Block("paragraph", "інше"),
        Block("heading", "Глава 58 НАЙМ", level=3),
        Block("heading", "Стаття 759.", level=5),
        Block("paragraph", "текст"),
        Block("heading", "Глава 59", level=3),
    ]
    selected = select_sections(blocks, ["Глава 58"])
    assert [b.text for b in selected] == ["Глава 58 НАЙМ", "Стаття 759.", "текст"]


def test_short_name():
    assert (
        short_name('АТ "АКЦІОНЕРНЕ ТОВАРИСТВО "ДТЕК ЗАХІДЕНЕРГО""')
        == "АТ «ДТЕК Західенерго»"
    )
    assert short_name('АКЦІОНЕРНЕ ТОВАРИСТВО "УКPНAФТА"') == "АТ «Укрнафта»"


def test_shingles_similarity_of_template_copies():
    a = shingles("орендар сплачує орендну плату щомісяця до 5 числа")
    b = shingles("орендар сплачує орендну плату щомісяця до 10 числа")
    assert 0.3 < len(a & b) / len(a | b) < 1


def test_table_rows_read_as_text_are_not_headings():
    assert is_plain_heading("5. ПРАВА ТА ОБОВ'ЯЗКИ СТОРІН")
    assert not is_plain_heading("27 | ВАРНА СТІЙКА З ВІТРИНОЮ 31.10.2005")
    assert not is_plain_heading("22 ПОЛИЦЯ НАСТІННА 30.09.2005 010000057250")


def test_rada_two_column_table_is_data():
    rows = "".join(
        f"<tr><td><p>{a}</p></td><td><p>{b}</p></td></tr>"
        for a, b in [
            ("Потенційний орендар", "Перелік документів"),
            ("1. Орган влади", "інформація про реєстрацію"),
            ("2. Релігійна організація", "статут організації"),
        ]
    )
    table = BeautifulSoup(f"<table>{rows}</table>", "lxml").find("table")
    [block] = rada_table(table)
    assert block.kind == "table"
    assert block.rows[2] == ["2. Релігійна організація", "статут організації"]
