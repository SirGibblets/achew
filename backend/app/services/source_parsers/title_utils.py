from typing import Any

from .timestamp_utils import parse_timestamp

def score_title(value: Any) -> int:
    """Score the likelihood of a value being a chapter title.
    
    Positive score means it resembles typical text or a title.
    Negative score means it is empty, a numeric value, or a timestamp.
    """
    if not isinstance(value, str):
        return -5
        
    s = value.strip()
    if not s:
        return -5
        
    # Pure numbers are usually not preferred as title, 
    # and might just be an index column.
    try:
        float(s)
        return -5
    except ValueError:
        pass
        
    # If it parses as a timestamp, it's highly unlikely to be the title column.
    if parse_timestamp(s) is not None:
        return -5
        
    # Valid string, looks like text.
    # Typical titles are within a reasonable length.
    if 1 <= len(s) <= 250:
        return 2
        
    return 1
