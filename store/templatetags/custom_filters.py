# my_app/templatetags/custom_filters.py

from django import template

register = template.Library()

@register.filter
def sub(value, arg):
    """Subtracts the arg from the value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return ''

@register.filter
def parse_specs_content(content_string):
    """
    Parses a string like "Key1: Value1\nKey2: Value2" into a list of dictionaries.
    Each dictionary will have 'key' and 'value' fields.
    """
    if not content_string:
        return []
    
    specs_list = []
    lines = content_string.strip().split('\n')
    for line in lines:
        parts = line.split(':', 1) # Split only on the first colon
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            specs_list.append({'key': key, 'value': value})
    return specs_list
@register.filter
def split(value, delimiter='\t'):
    return value.split(delimiter)    