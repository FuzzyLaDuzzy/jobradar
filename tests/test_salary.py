"""The salary a posting states: the amount as written, and per month for the filter."""

import pytest

from jobradar import salary


@pytest.mark.parametrize("text,low,high,period", [
    ("Salário: 1.200€ - 1.500€ brutos por mês", 1200, 1500, "month"),
    ("Remuneração entre 1200 a 1500 euros mensais.", 1200, 1500, "month"),
    ("Salary: €30K-40K per year, hybrid", round(30000 / 14), round(40000 / 14), "year"),
    ("Pay range €1,200 - €1,600", 1200, 1600, "month"),
    ("Vencimento base de 1.300 € brutos", 1300, 1300, "month"),
    ("30 000 € brutos/ano", round(30000 / 14), round(30000 / 14), "year"),
    ("We offer 42000 EUR", 3000, 3000, "year"),  # five digits, nothing said: per year
    ("Bolsa de 1.150,50€ por mês", 1150, 1150, "month"),
])
def test_salary_found(text, low, high, period):
    found = salary.find(text)
    assert (found["min"], found["max"], found["period"]) == (low, high, period)
    assert found["text"] in text  # shown as the posting wrote it


@pytest.mark.parametrize("text", [
    "Subsídio de alimentação de 9,60€ por dia",  # an allowance, not a salary
    "Formadores pagos a 25€/hora",  # per hour
    "Python, SQL e 3 anos de experiência",  # no euros at all
    "Seguro de saúde e prémio anual de 300 €",
])
def test_no_salary(text):
    assert salary.find(text) is None


def test_the_first_plausible_amount_wins():
    text = "Cartão refeição 10€. Salário: 1 400 € a 1 800 € por mês."
    assert salary.find(text)["min"] == 1400
