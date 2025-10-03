from datetime import date
from calendar import monthrange

def month_first(day: date) -> date:
    return day.replace(day=1)

def parse_month(s: str) -> date:
    # "YYYY-MM" → first day of month
    y, m = s.split('-')
    return date(int(y), int(m), 1)

# billing/utils.py
from datetime import date

def next_month(d: date) -> date:
    """Return first day of the next month for a given date."""
    y, m = d.year, d.month
    if m == 12:
        return date(y + 1, 1, 1)
    return date(y, m + 1, 1)
