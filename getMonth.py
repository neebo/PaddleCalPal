from datetime import datetime

def get_month_from_string(date_string: str) -> int:
    """Convert short month text to a month number."""
    try:
        return datetime.strptime(date_string[:3], "%b").month
    except Exception:
        return 0