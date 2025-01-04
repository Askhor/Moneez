import re
import subprocess
import sys
from collections import defaultdict

try:
    from datetime import datetime
    from pathlib import Path
    from matplotlib.pyplot import subplots, show, pause, title
    import mplcursors
    import json
    import argparse
except ImportError as e:
    necessary_modules = ["mplcursors", "matplotlib", "pathlib", "datetime", "json", "argparse"]
    print(
        f"There was an error during importing one of the modules {necessary_modules}",
        "Now downloading and installing the modules", sep="\n")
    print(f"The python executable used will be {sys.executable}")
    subprocess.run([sys.executable, "-m", "pip", "install", *necessary_modules])
    print(f"Now exiting program, install should have worked. Try to rerun the program.")
    sys.exit(-1)

PARSER = argparse.ArgumentParser("Moneez",
                                 description="A primitive program to automatically generate plots from csv files containing payments")
PARSER.add_argument("config_file", metavar="CONFIG-FILE",
                    help="The file containing instructions on how to the formatting and where to find the csv files")
PARSER.add_argument("year", metavar="YEAR", help="The year for which to generate an overview")
PARSER.add_argument("-w", "--wait",
                    help="How long to wait in between placing new bars in the graph. Just exists to look cool.")
ARGS = PARSER.parse_args()


def load_json(path: Path):
    with open(path) as file:
        return json.load(file)


JSON = load_json(Path(ARGS.config_file))

ALL_PAYMENTS = []

PAYMENTS_BY_YEAR = defaultdict(lambda: [[] for _ in range(12)])

CATEGORY_COLORS = JSON["category colors"]


class Payment:
    def __init__(self):
        self.usage = None
        self.payment_type = None
        self.bic = None
        self.iban = None
        self.name = None
        self.amount = None
        self.date: datetime = None
        self.amount_left = None
        self.innate_category = None
        self.category = None
        self.relevant_for_tax = None

    def __str__(self):
        return f"On {self.date}: {self.amount} change by {self.name} ({self.iban}) ({self.category}) ({self.payment_type})\n\t{self.usage})"


def associate_category(payment):
    payment.category = "Unknown"

    if payment.iban in known_ibans:
        payment.category = known_ibans[payment.iban]
        return

    name: str = payment.name.lower()
    usage: str = payment.usage.lower()
    for kw in keywords:
        if kw in name or kw in usage:
            payment.category = keywords[kw]
            return


def process_payments(payments):
    global ALL_PAYMENTS
    print(f"Processing {len(payments)} payments")

    for p in payments:
        associate_category(p)

    ALL_PAYMENTS += payments

    for p in payments:
        year = p.date.year
        month = p.date.month
        PAYMENTS_BY_YEAR[year][month - 1].append(p)


def gls_process_field(payment: Payment, key: str, value: str):
    match key:
        case "Buchungstag":
            payment.date = datetime.strptime(value, "%d.%m.%Y")
        case "Name Zahlungsbeteiligter":
            payment.name = value
        case "IBAN Zahlungsbeteiligter":
            payment.iban = value
        case "BIC (SWIFT-Code) Zahlungsbeteiligter":
            payment.bic = value
        case "Buchungstext":
            payment.payment_type = value
        case "Verwendungszweck":
            payment.usage = re.sub("\\W+", " ", value)
        case "Betrag":
            payment.amount = float(value.replace(",", "."))
        case "Waehrung":
            if value != "EUR":
                print(f"Unknown currency: {value}")
                sys.exit(-1)
        case "Saldo nach Buchung":
            payment.amount_left = float(value.replace(",", "."))
        case "Bemerkung":
            if value.strip() != "":
                print(f"Wat {value}")
                sys.exit()
        case "Kategorie":
            payment.innate_category = value
        case "Steuerrelevant":
            payment.relevant_for_tax = value
        case "Glaeubiger ID":
            pass
        case "Mandatsreferenz":
            pass
        case "Valutadatum":
            pass
        case "Bezeichnung Auftragskonto" | "IBAN Auftragskonto" | "BIC Auftragskonto" | "Bankname Auftragskonto":
            pass
        case _:
            print(f"Unknown key: {key}")
            sys.exit(-1)


def process_csv(file: Path, col_sep, row_sep, field_processor):
    string = file.read_text().strip()

    rows = string.split(row_sep)
    rows = [r.split(col_sep) for r in rows]

    keys = rows[0]
    rows = rows[1:]

    rows_keyed = []

    for row in rows:
        kv = {}
        rows_keyed.append(kv)
        for index, value in enumerate(row):
            kv[keys[index]] = value

    payments = [Payment() for _ in range(len(rows_keyed))]

    for payment, row in zip(payments, rows_keyed):
        for key, value in row.items():
            field_processor(payment, key, value)

    process_payments(payments)


known_ibans = JSON["ibans"]
keywords = JSON["keywords"]


def in_out_year(year):
    payments = PAYMENTS_BY_YEAR[year]
    print(year)
    for i in range(12):
        plus = sum(p.amount for p in payments[i] if p.amount > 0)
        minus = sum(p.amount for p in payments[i] if p.amount < 0)
        print(f"Month {i + 1:2}: {plus:10.2f} {minus:10.2f}")


def show_categories():
    categories = set()
    categories |= set(known_ibans.values())
    categories |= set(keywords.values())
    print(f"The following categories exist: {", ".join(categories)}")
    print(
        f"The following categories do not have an associated color: {", ".join(categories - set(CATEGORY_COLORS.keys()))}")


def sleep_interactive(seconds):
    show(block=False)
    pause(seconds)


def add_text_to_cursor(cursor, text):
    @cursor.connect("add")
    def on_add(sel):
        sel.annotation.set(text=text)


def overview_year(year, payments: list, category_colors=None, color_default=None, build_interval=None):
    if category_colors is None: category_colors = {}
    fig, ax = subplots()
    title(year)

    categories = list(set(
        payment.category
        for month in range(12) for payment in payments[month]
    ))
    cat_colors = [(f"C{i}" if color_default is None else color_default) for i in range(len(categories))]

    for category, color in category_colors.items():
        try:
            cat_colors[categories.index(category)] = color
        except ValueError:
            print(f"Categories for {year}: {categories}")
            print(f"Unused category-color assignment? {category}: {color}")

    for i in range(len(categories)):
        ax.plot([0], [0], color=cat_colors[i], label=categories[i])
    ax.plot([0, 13], [0, 0], color="red")

    ax.legend()

    for month in range(12):
        bottom_positives = 0
        top_negatives = 0

        for index, category in enumerate(categories):
            Σ = sum(p.amount for p in payments[month] if p.category == category)

            bottom = bottom_positives if Σ >= 0 else top_negatives
            bar = ax.bar(month + 1, Σ, bottom=bottom, color=cat_colors[index])
            cursor = mplcursors.cursor(bar, hover=True)
            add_text_to_cursor(cursor, f"{category}: {Σ:.2f}")

            if Σ >= 0:
                bottom_positives += Σ
            else:
                top_negatives += Σ

            if build_interval is not None and build_interval != 0:
                sleep_interactive(float(build_interval))

    show()


def search(predicate):
    results = list(filter(predicate, ALL_PAYMENTS))
    print(*results, sep="\n")
    print(len(results), "results")


def show_current_amount():
    payments = sorted(ALL_PAYMENTS, key=lambda p: p.date)
    print(f"The current balance is: {payments[-1].amount_left:.2f}€")


def show_year(year):
    overview_year(year, PAYMENTS_BY_YEAR[year], CATEGORY_COLORS,
                  JSON["default color"] if "default color" in JSON else None,
                  ARGS.wait)


def process_all_input_files():
    for file_info in JSON["input files"]:
        file = file_info["file"]
        col_sep = ";"
        row_sep = "\n"
        field_processor = "gls"

        if "columns" in file_info:
            col_sep = file_info["columns"]
        if "rows" in file_info:
            row_sep = file_info["rows"]
        if "field processor" in file_info:
            field_processor = file_info["field processor"]

        match field_processor:
            case "gls":
                field_processor = gls_process_field
            case _:
                print(f"Unknown field processor: {field_processor}")

        process_csv(Path(file).expanduser(), col_sep, row_sep, field_processor)


def main():
    process_all_input_files()

    for YEAR in PAYMENTS_BY_YEAR:
        in_out_year(YEAR)

    show_current_amount()

    show_year(int(ARGS.year))


try:
    main()
except KeyboardInterrupt:
    print("Program interrupted by user")
