"""input/purchase_history/*.csv（楽天・Amazonの購入履歴）を集計し、
「今月の商品候補」のベースとなる一覧を output/purchase_candidates_日時.md に出力する。

このスクリプトが行うのは機械的な集計のみ（リピート回数・金額・直近購入日の整理）。
どの商品を実際にROOM/SNSで紹介するかの判断は、この一覧をもとにClaudeとの対話で行う。

使い方:
    python3 scripts/analyze_purchase_history.py
    python3 scripts/analyze_purchase_history.py --days 90   # 直近90日の購入のみ対象
    python3 scripts/analyze_purchase_history.py --top 20    # 上位20件のみ出力
"""
import argparse
import csv
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = ROOT / "input" / "purchase_history"
OUTPUT_DIR = ROOT / "output"

# ヘッダー名の表記ゆれを吸収するための別名リスト。
# 実際のCSVのヘッダーがどれにも当てはまらない場合はここに追記する。
HEADER_ALIASES = {
    "date": ["注文日時", "注文日", "購入日", "order date", "purchase date"],
    "product_name": ["商品名", "タイトル", "品名", "title", "product name"],
    "price": ["小計", "商品小計", "単価", "価格", "合計", "item total", "item subtotal", "price"],
    "quantity": ["数量", "個数", "quantity", "qty"],
}

DATE_FORMATS = [
    "%Y/%m/%d", "%Y-%m-%d", "%Y年%m月%d日",
    "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
]


def find_column(header: list[str], field: str) -> str | None:
    aliases = HEADER_ALIASES[field]
    lower_header = {h.strip().lower(): h for h in header}
    for alias in aliases:
        alias_lower = alias.lower()
        for h_lower, original in lower_header.items():
            if alias_lower in h_lower:
                return original
    return None


def parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def parse_price(raw: str) -> float:
    cleaned = re.sub(r"[^\d.\-]", "", raw.replace(",", ""))
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_quantity(raw: str) -> int:
    cleaned = re.sub(r"[^\d]", "", raw)
    return int(cleaned) if cleaned else 1


def detect_source(path: Path) -> str | None:
    name = path.name.lower()
    if name.startswith("rakuten"):
        return "楽天"
    if name.startswith("amazon"):
        return "Amazon"
    return None


def normalize_name(name: str) -> str:
    collapsed = re.sub(r"\s+", " ", name.strip())
    return collapsed[:40]


def load_rows(path: Path, source: str) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        columns = {field: find_column(header, field) for field in ("date", "product_name", "price")}
        missing = [field for field, col in columns.items() if col is None]
        if missing:
            print(
                f"[スキップ] {path.name}: 列が見つかりません（{missing}）。"
                f" 実際のヘッダー: {header}。HEADER_ALIASES に追記してください。",
                file=sys.stderr,
            )
            return []
        qty_col = find_column(header, "quantity")

        rows = []
        for row in reader:
            date = parse_date(row.get(columns["date"], ""))
            product_name = row.get(columns["product_name"], "").strip()
            if not product_name:
                continue
            price = parse_price(row.get(columns["price"], ""))
            quantity = parse_quantity(row.get(qty_col, "1")) if qty_col else 1
            rows.append(
                {
                    "date": date,
                    "product_name": product_name,
                    "price": price,
                    "quantity": quantity,
                    "source": source,
                }
            )
        return rows


def collect_rows(since: datetime | None) -> list[dict]:
    all_rows = []
    for path in sorted(INPUT_DIR.glob("*.csv")):
        source = detect_source(path)
        if source is None:
            print(
                f"[スキップ] {path.name}: ファイル名が rakuten_ / amazon_ で始まっていません。",
                file=sys.stderr,
            )
            continue
        rows = load_rows(path, source)
        all_rows.extend(rows)

    if since is not None:
        all_rows = [r for r in all_rows if r["date"] is None or r["date"] >= since]
    return all_rows


def aggregate(rows: list[dict]) -> list[dict]:
    groups = defaultdict(lambda: {
        "display_name": "",
        "occurrences": 0,
        "total_spend": 0.0,
        "sources": set(),
        "last_date": None,
        "first_date": None,
    })

    for row in rows:
        key = normalize_name(row["product_name"])
        g = groups[key]
        g["display_name"] = row["product_name"]
        g["occurrences"] += 1
        g["total_spend"] += row["price"] * row["quantity"]
        g["sources"].add(row["source"])
        if row["date"] is not None:
            if g["last_date"] is None or row["date"] > g["last_date"]:
                g["last_date"] = row["date"]
                g["display_name"] = row["product_name"]
            if g["first_date"] is None or row["date"] < g["first_date"]:
                g["first_date"] = row["date"]

    candidates = []
    for g in groups.values():
        candidates.append(
            {
                "product_name": g["display_name"],
                "occurrences": g["occurrences"],
                "total_spend": g["total_spend"],
                "sources": "・".join(sorted(g["sources"])),
                "last_date": g["last_date"].strftime("%Y-%m-%d") if g["last_date"] else "不明",
            }
        )

    candidates.sort(key=lambda c: (c["occurrences"], c["total_spend"]), reverse=True)
    return candidates


def write_report(candidates: list[dict], top: int, since: datetime | None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = OUTPUT_DIR / f"purchase_candidates_{timestamp}.md"

    lines = ["# 購入履歴からの商品候補", ""]
    if since is not None:
        lines.append(f"対象期間: {since.strftime('%Y-%m-%d')} 以降")
    lines.append(f"集計件数: {len(candidates)}件中、上位{min(top, len(candidates))}件を表示")
    lines.append("")
    lines.append(
        "この一覧は購入回数・金額を機械的に集計したものです。"
        "実際にROOM/SNSで紹介するかどうかは、ママ向け発信のテーマに合うか・"
        "すでに紹介済みでないかを確認しながらClaudeとの対話で選んでください。"
    )
    lines.append("")
    lines.append("| 商品名 | 購入回数 | 合計金額 | 購入元 | 直近購入日 |")
    lines.append("|---|---|---|---|---|")
    for c in candidates[:top]:
        lines.append(
            f"| {c['product_name']} | {c['occurrences']} | "
            f"{c['total_spend']:,.0f}円 | {c['sources']} | {c['last_date']} |"
        )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=None, help="直近N日分のみ対象にする")
    parser.add_argument("--top", type=int, default=30, help="出力する候補数（デフォルト30件）")
    args = parser.parse_args()

    if not INPUT_DIR.exists() or not any(INPUT_DIR.glob("*.csv")):
        print(f"[エラー] {INPUT_DIR} にCSVファイルが見つかりません。", file=sys.stderr)
        sys.exit(1)

    since = datetime.now() - timedelta(days=args.days) if args.days else None
    rows = collect_rows(since)
    if not rows:
        print("[エラー] 集計できる購入データがありませんでした。", file=sys.stderr)
        sys.exit(1)

    candidates = aggregate(rows)
    out_path = write_report(candidates, args.top, since)
    print(f"{len(rows)}件の購入データから{len(candidates)}件の商品候補を集計し、"
          f"{out_path.relative_to(ROOT)} に出力しました。")


if __name__ == "__main__":
    main()
