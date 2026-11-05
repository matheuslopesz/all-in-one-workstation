import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import defaultdict
from datetime import date, datetime

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "all-in-one-workstation")
FINANCE_FILE = os.path.join(CONFIG_DIR, "finance.json")

ACCOUNTS = {"nubank-card": "Nubank cartão", "nubank-account": "Nubank conta", "itau-card": "Itaú cartão"}
CATEGORIES = ["Mercado", "Restaurantes", "Delivery", "Transporte", "Combustível", "Carro", "Casa", "Contas da casa",
              "Saúde", "Assinaturas", "Compras", "Lazer", "Educação", "Pix para pessoas", "Juros e tarifas", "Outros",
              "Entradas", "Pagamento de fatura", "Movimentação interna"]
# Money that only moves between your own accounts or into them: never counted as spending.
NOT_SPENDING = {"Entradas", "Pagamento de fatura", "Movimentação interna"}
DEFAULT_RULES = [
    ("Pagamento de fatura", ["pagamento recebido", "pagamento de fatura", "pagamento via conta"]),
    ("Movimentação interna", ["resgate rdb", "aplicação rdb", "aplicacao rdb", "transferência entre contas",
                              "dinheiro guardado", "dinheiro resgatado"]),
    ("Juros e tarifas", ["iof", "juros", "multa", "tarifa", "anuidade", "encargo"]),
    ("Delivery", ["ifood", "rappi", "ze delivery", "zé delivery", "aiqfome"]),
    ("Transporte", ["uber", "99app", "99 pop", "99*", "cabify", "metro", "bilhete"]),
    ("Combustível", ["posto", "shell", "ipiranga", "petrobras", "br mania", "combust"]),
    ("Carro", ["auto center", "autocenter", "oficina", "estaciona", "detran", "ipva", "pneu", "lava jato"]),
    ("Mercado", ["supermerc", "mercadinho", "atacad", "assai", "assaí", "carrefour", "pão de açúcar", "villabox",
                 "hortifruti", "frigorif"]),
    ("Restaurantes", ["restaurante", "lanchonete", "padaria", "galeteria", "coxinha", "pizzaria", "burger",
                      "burguer", "cafe ", "café", "churrasc", "sushi", "bar "]),
    ("Contas da casa", ["enel", "energia", "coelce", "cagece", "saneamento", "claro", "vivo", "tim ", "internet",
                        "brisanet", "gás", "condominio", "condomínio", "aluguel"]),
    ("Saúde", ["farmacia", "farmácia", "drogasil", "raia", "pague menos", "clinica", "clínica", "hospital",
               "laborat", "odonto", "dentist", "unimed", "hapvida"]),
    ("Assinaturas", ["netflix", "spotify", "prime video", "disney", "hbo", "max.com", "youtube", "apple.com",
                     "google", "chatgpt", "openai", "anthropic", "claude", "cursor", "github", "icloud"]),
    ("Compras", ["amazon", "mercadolivre", "mercado livre", "shopee", "magalu", "aliexpress", "shein",
                 "home center", "store", "loja"]),
    ("Educação", ["curso", "udemy", "alura", "escola", "faculdade", "livraria"]),
    ("Lazer", ["cinema", "ingresso", "sympla", "steam", "playstation", "xbox", "show"]),
]
ITAU_HINTS = {"restaurante": "Restaurantes", "supermercado": "Mercado", "farmacia": "Saúde", "saude": "Saúde",
              "vestuario": "Compras", "turismo": "Lazer", "educacao": "Educação", "servicos": "Outros"}
INSTALLMENT = re.compile(r"(?:\s*-\s*Parcela\s+|\s+)(\d{1,2})/(\d{1,2})\s*$", re.IGNORECASE)
MONTHS_PT = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro",
             "Novembro", "Dezembro"]


class FinanceError(Exception):
    pass


def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"


def add_months(month, count):
    year, mon = map(int, month.split("-"))
    total = year * 12 + mon - 1 + count
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def month_label(month):
    year, mon = map(int, month.split("-"))
    return f"{MONTHS_PT[mon]} {year}"


def brl(value):
    text = f"{abs(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if value < 0 else ''}R$ {text}"


def parse_brl(text):
    """'1.357,16', '- 287,26' or '-1.357,16' -> float."""
    text = text.replace("R$", "").replace(" ", "").strip()
    return float(text.replace(".", "").replace(",", "."))


def plain(text):
    return unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()


def merchant_key(description):
    """Stable key for a merchant: no installment suffix, Pix prefix, masked document or digits."""
    text = INSTALLMENT.sub("", description)
    text = re.sub(r"^(transferência (enviada|recebida) pelo pix|compra no débito( via nupay)?|"
                  r"pagamento de boleto efetuado)\s*-\s*", "", text, flags=re.IGNORECASE)
    text = re.split(r"\s+-\s+", text)[0]
    text = re.sub(r"[\d•*.,/#-]+", " ", plain(text))
    return " ".join(text.split()[:3])


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def tx(account, day, description, amount, month, hint=None):
    match = INSTALLMENT.search(description)
    entry = {"account": account, "date": day.isoformat(), "description": description.strip(),
             "amount": round(amount, 2), "month": month}
    if match and int(match.group(2)) > 1:
        entry["installment"] = [int(match.group(1)), int(match.group(2))]
    if hint:
        entry["hint"] = hint
    return entry


def read_nubank_card(path):
    """Nubank card bill: Nubank_<due date>.csv with date,title,amount; payments are negative."""
    due = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(path))
    if not due:
        raise FinanceError("Nubank bill file name should carry the due date (Nubank_YYYY-MM-DD.csv)")
    month = f"{due.group(1)}-{due.group(2)}"
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    items = [tx("nubank-card", date.fromisoformat(r["date"]), r["title"], parse_brl(r["amount"]), month) for r in rows]
    return {"account": "nubank-card", "months": [month]}, items


def read_nubank_account(path):
    """Nubank account statement: Data,Valor,Identificador,Descrição; money out is negative."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    items = []
    for r in rows:
        day = datetime.strptime(r["Data"], "%d/%m/%Y").date()
        items.append(tx("nubank-account", day, r["Descrição"], -float(r["Valor"]), month_key(day)))
    if not items:
        raise FinanceError("Empty statement")
    days = sorted(i["date"] for i in items)
    return {"account": "nubank-account", "from": days[0], "to": days[-1]}, items


def read_itau_card(path):
    """Itaú card bill PDF: purchases between 'Lançamentos: compras e saques' and the bill total."""
    try:
        text = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True,
                              check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError) as error:
        raise FinanceError(f"Could not read the PDF (pdftotext): {error}") from error
    due = re.search(r"Vencimento:\s*(\d{2})/(\d{2})/(\d{4})", text)
    if not due:
        raise FinanceError("This doesn't look like an Itaú card bill")
    due_day, due_month, due_year = map(int, due.groups())
    month = f"{due_year:04d}-{due_month:02d}"
    items, inside, last = [], False, None
    for line in text.splitlines():
        if "Lançamentos: compras e saques" in line or "Lançamentos internacionais" in line:
            inside = True
            continue
        if inside and re.search(r"Lançamentos no cartão|Total dos lançamentos", line):
            inside = False
            continue
        if not inside:
            continue
        # Only the left column: the right one holds limits and charges.
        match = re.match(r"^\s{4,}(\d{2})/(\d{2})\s{2,}(.+?)\s{2,}(-?[\d.]+,\d{2})(?:\s|$)", line)
        if match:
            day, mon = int(match.group(1)), int(match.group(2))
            year = due_year if mon <= due_month else due_year - 1
            last = tx("itau-card", date(year, mon, day), match.group(3), parse_brl(match.group(4)), month)
            items.append(last)
            continue
        hint = re.match(r"^\s{10,}([a-zà-ú]+)\s", line)
        if last is not None and hint and "hint" not in last:
            last["hint"] = ITAU_HINTS.get(plain(hint.group(1)))
    if not items:
        raise FinanceError("No purchases found in the Itaú bill")
    return {"account": "itau-card", "months": [month]}, items


def read_file(path):
    name = os.path.basename(path).lower()
    if name.endswith(".pdf"):
        return read_itau_card(path)
    with open(path, encoding="utf-8-sig") as f:
        header = f.readline().strip().lower()
    if header.startswith("date,title,amount"):
        return read_nubank_card(path)
    if header.startswith("data,valor,identificador"):
        return read_nubank_account(path)
    raise FinanceError(f"Unknown file format: {os.path.basename(path)}")


def in_scope(item, scope):
    if item["account"] != scope["account"]:
        return False
    if "months" in scope:
        return item["month"] in scope["months"]
    return scope["from"] <= item["date"] <= scope["to"]


class Finance:
    def __init__(self, path=FINANCE_FILE):
        self.path = path
        self.data = {"transactions": [], "imports": [], "rules": {}, "debts": [], "plan": None}
        self.reload()

    def reload(self):
        try:
            with open(self.path) as f:
                self.data.update(json.load(f))
        except FileNotFoundError:
            pass

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @property
    def transactions(self):
        return self.data["transactions"]

    def categorize(self, item):
        key = merchant_key(item["description"])
        if key in self.data["rules"]:
            return self.data["rules"][key]
        text = plain(item["description"]) + " "
        for category, words in DEFAULT_RULES:
            if any(plain(w) in text for w in words):
                return category
        if item.get("hint"):
            return item["hint"]
        if item["account"] == "nubank-account":
            if item["amount"] < 0:
                return "Entradas"
            if "pix" in text:
                return "Pix para pessoas"
        return "Outros"

    def import_file(self, path):
        """Import a bill or statement; it replaces what was imported before for the same account and period."""
        scope, items = read_file(path)
        manual = {(t["account"], t["date"], t["description"], t["amount"]): t["category"]
                  for t in self.transactions if t.get("manual")}
        self.data["transactions"] = [t for t in self.transactions if not in_scope(t, scope)]
        for item in items:
            key = (item["account"], item["date"], item["description"], item["amount"])
            if key in manual:
                item.update(category=manual[key], manual=True)
            else:
                item["category"] = self.categorize(item)
            self.transactions.append(item)
        self.data["imports"] = [i for i in self.data["imports"] if i["scope"] != scope]
        self.data["imports"].append({"file": os.path.basename(path), "sha256": file_hash(path), "scope": scope,
                                     "count": len(items), "at": datetime.now().isoformat(timespec="seconds")})
        self.transactions.sort(key=lambda t: t["date"])
        self.save()
        return scope, len(items)

    def set_category(self, item, category):
        """Recategorize a transaction and every other one from the same merchant, now and in future imports."""
        key = merchant_key(item["description"])
        self.data["rules"][key] = category
        for t in self.transactions:
            if t is item or (merchant_key(t["description"]) == key and not t.get("manual")):
                t["category"] = category
        item["manual"] = True
        self.save()

    def months(self):
        return sorted({t["month"] for t in self.transactions})

    def month_transactions(self, month):
        return [t for t in self.transactions if t["month"] == month]

    def summary(self, month):
        spent, income = defaultdict(float), 0.0
        for t in self.month_transactions(month):
            if t["category"] == "Entradas":
                income -= t["amount"]
            elif t["category"] not in NOT_SPENDING:
                spent[t["category"]] += t["amount"]
        total = sum(spent.values())
        return {"month": month, "income": round(income, 2), "spent": round(total, 2),
                "left": round(income - total, 2),
                "categories": dict(sorted(((k, round(v, 2)) for k, v in spent.items()), key=lambda kv: -kv[1]))}

    def card_months(self, account):
        return {i["scope"]["months"][0] for i in self.data["imports"]
                if i["scope"]["account"] == account and "months" in i["scope"]}

    def commitments(self, start, count=12):
        """Money already promised per month: card bills imported, remaining installments and fixed debts."""
        rows = []
        for offset in range(count):
            month = add_months(start, offset)
            cards = defaultdict(float)
            for account in ("nubank-card", "itau-card"):
                if month in self.card_months(account):
                    cards[account] = sum(t["amount"] for t in self.month_transactions(month)
                                         if t["account"] == account and t["category"] != "Pagamento de fatura")
                    continue
                for t in self.transactions:
                    if t["account"] != account or "installment" not in t:
                        continue
                    current, total = t["installment"]
                    ahead = (int(month[:4]) * 12 + int(month[5:])) - (int(t["month"][:4]) * 12 + int(t["month"][5:]))
                    if 0 < ahead <= total - current and not any(
                            m in self.card_months(account) for m in [add_months(t["month"], s)
                                                                     for s in range(1, ahead)]):
                        cards[account] += t["amount"]
            fixed = {d["name"]: d["monthly"] for d in self.data["debts"] if d["until"] >= month}
            total = sum(cards.values()) + sum(fixed.values())
            rows.append({"month": month, "cards": {k: round(v, 2) for k, v in cards.items() if v},
                         "fixed": fixed, "total": round(total, 2)})
        return rows

    def add_debt(self, name, monthly, until):
        self.data["debts"].append({"name": name, "monthly": monthly, "until": until})
        self.save()

    def remove_debt(self, debt):
        self.data["debts"].remove(debt)
        self.save()

    def plan_month(self, month):
        plan = self.data.get("plan") or {}
        return next((m for m in plan.get("months", []) if m.get("month") == month), None)


def cli(args):
    """all-in-one-workstation finance summary | import <files> | plan <plan.json>"""
    finance = Finance()
    if args[:1] == ["import"] and args[1:]:
        for path in args[1:]:
            scope, count = finance.import_file(path)
            print(f"{os.path.basename(path)}: {count} lançamentos ({ACCOUNTS[scope['account']]})")
        return 0
    if args[:1] == ["plan"] and len(args) == 2:
        with open(args[1]) as f:
            finance.data["plan"] = json.load(f)
        finance.data["plan"].setdefault("updated", datetime.now().isoformat(timespec="seconds"))
        finance.save()
        print("Plano salvo")
        return 0
    if args[:1] == ["summary"]:
        out = {"months": [finance.summary(m) for m in finance.months()],
               "commitments": finance.commitments(month_key(date.today())),
               "debts": finance.data["debts"], "plan": finance.data.get("plan")}
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return 0
    print(cli.__doc__, file=sys.stderr)
    return 2
