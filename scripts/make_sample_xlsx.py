"""Generate a sample leads Excel file for testing the import (Phase 2)."""
import os

from openpyxl import Workbook

SAMPLE = [
    ("Navneet Sharma", "8209183821"),
    ("Ayush Kumar", "6350012509"),
    ("Manisha Singh", "7424952509"),
    ("Nirlipta Sathpathy", "8249218416"),
    ("Arvind Kumawat", "9782513882"),
    ("Harshal Mathur", "9602546044"),
    ("Kumkum Morya", "9461157520"),
    ("Saksham Gupta", "7906900515"),
    ("Md Uwais", "9081229679"),
    ("Khushbu Sharma", "8302118481"),
]


def main() -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "leads"
    ws.append(["name", "phone"])
    for name, phone in SAMPLE:
        ws.append([name, phone])

    os.makedirs("data", exist_ok=True)
    out = os.path.join("data", "sample_leads.xlsx")
    wb.save(out)
    print(f"Wrote {out} with {len(SAMPLE)} leads.")


if __name__ == "__main__":
    main()
