"""Стабильные коды пациентов и замена известных имён в выгрузках."""

import re
import secrets
from compass.db import db, rows


def patient_code(ident):
    result = rows("SELECT code FROM research_codes WHERE patient_id=?", (ident,))
    if not result:
        with db() as con:
            con.execute(
                "INSERT OR IGNORE INTO research_codes VALUES(?,?)",
                (ident, "PK-" + secrets.token_hex(4).upper()),
            )
        result = rows("SELECT code FROM research_codes WHERE patient_id=?", (ident,))
    return result[0]["code"]


def export_text(value, patient_name, code):
    # Structured identity uses the code; also replace known name parts in free text.
    parts = [patient_name, *re.findall(r"[\w-]+", patient_name, flags=re.UNICODE)]
    parts = sorted({part for part in parts if len(part) >= 3}, key=len, reverse=True)
    if not parts:
        return value
    pattern = r"(?<!\w)(?:" + "|".join(re.escape(part) for part in parts) + r")(?!\w)"
    return re.sub(pattern, lambda _: code, value, flags=re.IGNORECASE)
