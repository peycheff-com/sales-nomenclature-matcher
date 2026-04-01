from __future__ import annotations

from matcher.normalization.pipeline import run_pipeline


class TestUnicodeCleanup:
    def test_lowercase(self):
        ctx = run_pipeline("Кабель ВВГ")
        assert "кабель" in ctx.text
        assert "ввг" in ctx.text

    def test_strips_control_chars(self):
        ctx = run_pipeline("кабель\x00 ввг\x0b")
        assert "\x00" not in ctx.text
        assert "\x0b" not in ctx.text

    def test_normalizes_whitespace(self):
        ctx = run_pipeline("кабель   ввг   3х2.5")
        assert "  " not in ctx.text

    def test_normalizes_dashes(self):
        ctx = run_pipeline("насос — grundfos")
        assert "—" not in ctx.text
        assert "-" in ctx.text


class TestCyrillicLatin:
    def test_normalizes_dimension_separator(self):
        ctx = run_pipeline("кабель 3х2.5")
        # Should normalize cyrillic х to x between digits
        assert "3x2.5" in ctx.text

    def test_mixed_script_token(self):
        # 'ВВГнг' with some latin chars mixed in should normalize
        ctx = run_pipeline("ввгнг")
        # All should be single script
        text = ctx.text
        assert text  # Should not be empty


class TestNumberExtraction:
    def test_extracts_simple_numbers(self):
        ctx = run_pipeline("кабель 3x2.5")
        assert 3.0 in ctx.numbers
        assert 2.5 in ctx.numbers

    def test_extracts_comma_decimals(self):
        ctx = run_pipeline("труба 32,5 мм")
        assert 32.5 in ctx.numbers

    def test_extracts_dimensions(self):
        ctx = run_pipeline("лист 1200x600x50")
        assert ctx.dimensions

    def test_extracts_multiple_numbers(self):
        ctx = run_pipeline("насос 25-40 180")
        assert 25.0 in ctx.numbers
        assert 40.0 in ctx.numbers
        assert 180.0 in ctx.numbers


class TestUnitNormalization:
    def test_normalizes_mm(self):
        ctx = run_pipeline("труба 32 мм")
        assert "mm" in ctx.text
        assert ctx.unit == "mm"

    def test_normalizes_ml(self):
        ctx = run_pipeline("пена 750 мл")
        assert "ml" in ctx.text
        assert ctx.unit == "ml"

    def test_normalizes_kg(self):
        ctx = run_pipeline("клей 25 кг")
        assert "kg" in ctx.text
        assert ctx.unit == "kg"

    def test_normalizes_liters(self):
        ctx = run_pipeline("грунтовка 10 л")
        assert ctx.unit == "l"

    def test_normalizes_watts(self):
        ctx = run_pipeline("лампа 60 вт")
        assert ctx.unit == "w"


class TestBrandDetection:
    def test_detects_grundfos(self):
        ctx = run_pipeline("насос grundfoss 25-40")
        assert ctx.brand == "grundfos"

    def test_detects_cyrillic_brand(self):
        ctx = run_pipeline("насос грундфос 25-40")
        assert ctx.brand == "grundfos"

    def test_detects_knauf(self):
        ctx = run_pipeline("штукатурка кнауф ротбанд 30 кг")
        assert ctx.brand == "knauf"

    def test_detects_bosch(self):
        ctx = run_pipeline("перфоратор бош gbh 2-26")
        assert ctx.brand == "bosch"


class TestStopwords:
    def test_removes_stopwords(self):
        ctx = run_pipeline("кабель для прокладки")
        assert "для" not in ctx.text.split()

    def test_removes_gost(self):
        ctx = run_pipeline("кабель ввг гост 31996")
        assert "гост" not in ctx.text.split()

    def test_removes_article_marker(self):
        ctx = run_pipeline("арт. 12345 кабель")
        tokens = ctx.text.split()
        assert "арт." not in tokens


class TestTokenizer:
    def test_produces_tokens(self):
        ctx = run_pipeline("кабель ввг 3x2.5")
        assert len(ctx.tokens) > 0

    def test_removes_punctuation(self):
        ctx = run_pipeline("кабель (ввг), 3x2.5;")
        for token in ctx.tokens:
            assert "(" not in token
            assert ")" not in token
            assert ";" not in token


class TestFullPipeline:
    """Integration tests with real product name patterns."""

    def test_cable_vvg(self):
        ctx = run_pipeline("Кабель ВВГнг 3х2,5 ГОСТ")
        assert "кабель" in ctx.text
        assert "ввгнг" in ctx.text
        assert 3.0 in ctx.numbers
        assert 2.5 in ctx.numbers
        assert "гост" not in ctx.text.split()

    def test_pump_grundfos(self):
        ctx = run_pipeline("Насос grundfoss 25-40")
        assert ctx.brand == "grundfos"
        assert 25.0 in ctx.numbers
        assert 40.0 in ctx.numbers

    def test_foam_winter(self):
        ctx = run_pipeline("Пена монтажная зимняя 750 мл")
        assert "пена" in ctx.text
        assert "монтажная" in ctx.text
        assert ctx.unit == "ml"
        assert 750.0 in ctx.numbers

    def test_plaster_knauf(self):
        ctx = run_pipeline("Штукатурка Кнауф Ротбанд 30 кг")
        assert ctx.brand == "knauf"
        assert ctx.unit == "kg"
        assert 30.0 in ctx.numbers

    def test_drill_bosch(self):
        ctx = run_pipeline("Перфоратор Bosch GBH 2-26 DRE")
        assert ctx.brand == "bosch"
        assert 2.0 in ctx.numbers
        assert 26.0 in ctx.numbers

    def test_pipe_32mm(self):
        ctx = run_pipeline("Труба ПП 32 мм 2.0 м")
        assert ctx.unit is not None  # Should detect mm or m
        assert 32.0 in ctx.numbers
        assert 2.0 in ctx.numbers

    def test_insulation_rockwool(self):
        ctx = run_pipeline("Утеплитель Роквул Лайт Баттс 1000x600x50 мм")
        assert ctx.brand == "rockwool"
        assert ctx.dimensions  # Should extract dimensions
        assert ctx.unit == "mm"

    def test_valve_danfoss(self):
        ctx = run_pipeline("Клапан данфосс RA-N 15 1/2")
        assert ctx.brand is not None  # danfoss

    def test_wire_3x2_5(self):
        ctx = run_pipeline("Провод ПВС 3x2,5 белый 100м")
        assert 3.0 in ctx.numbers
        assert 2.5 in ctx.numbers
        assert 100.0 in ctx.numbers

    def test_paint_10l(self):
        ctx = run_pipeline("Краска интерьерная белая 10 л")
        assert ctx.unit == "l"
        assert 10.0 in ctx.numbers

    def test_preserves_original(self):
        original = "Кабель ВВГ 3х2.5"
        ctx = run_pipeline(original)
        assert ctx.original == original

    def test_empty_input(self):
        ctx = run_pipeline("")
        assert ctx.text == ""
        assert ctx.tokens == []
        assert ctx.numbers == []

    def test_whitespace_only_input(self):
        ctx = run_pipeline("   ")
        assert ctx.text == ""

    def test_makita_brand(self):
        ctx = run_pipeline("Дрель Макита DP4003")
        assert ctx.brand == "makita"

    def test_hilti_brand(self):
        ctx = run_pipeline("Перфоратор хилти TE 7-C")
        assert ctx.brand == "hilti"

    def test_rehau_pipe(self):
        ctx = run_pipeline("Труба Рехау Rautherm 17x2.0 мм")
        assert ctx.brand == "rehau"
        assert 17.0 in ctx.numbers
        assert 2.0 in ctx.numbers

    def test_unit_pcs(self):
        ctx = run_pipeline("Дюбель 100 шт")
        assert ctx.unit == "pcs"
        assert 100.0 in ctx.numbers

    def test_unit_sqm(self):
        ctx = run_pipeline("Плитка 1.2 м2")
        assert ctx.unit == "sqm"
        assert 1.2 in ctx.numbers

    def test_schneider_brand(self):
        ctx = run_pipeline("Автомат шнайдер 16А")
        assert ctx.brand == "schneider electric"

    def test_abb_brand(self):
        ctx = run_pipeline("Выключатель абб 25А")
        assert ctx.brand == "abb"
