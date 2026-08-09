from forecast.formula import RangeValue, evaluate, translate_formula


def _evaluate(formula, values):
    def get_cell(address):
        return values.get(address)

    def get_range(start, end):
        cells = ["A1", "A2", "A3"] if (start, end) == ("A1", "A3") else []
        return RangeValue(cells, [values.get(cell) for cell in cells])

    return evaluate(formula, get_cell, get_range)


def test_average_excel_reference_semantics():
    values = {"A1": 0, "A2": None, "A3": "text"}
    assert _evaluate("=AVERAGE(A1:A3)", values) == 0


def test_average_supports_ranges_multiple_arguments_and_absolute_refs():
    values = {"A1": 2, "A2": 4, "A3": 6, "B1": 8}
    assert _evaluate("=AVERAGE($A$1:$A$3,B1)", values) == 5


def test_average_without_numeric_values_preserves_fallback_signal():
    values = {"A1": None, "A2": "text", "A3": False}
    try:
        _evaluate("=AVERAGE(A1:A3)", values)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("Excel AVERAGE without numeric values must error")


def test_average_propagates_argument_errors():
    def get_cell(address):
        if address == "A1":
            raise ZeroDivisionError
        return 2

    try:
        evaluate("=AVERAGE(A1,B1)", get_cell, lambda _start, _end: None)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("Excel AVERAGE must propagate referenced errors")


def test_average_shared_formula_translation():
    assert translate_formula("=AVERAGE(E1:J1)", "K1", "L1") == "=AVERAGE(F1:K1)"
