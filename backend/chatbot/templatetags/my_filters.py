import re

from django import template

register = template.Library()


@register.filter
def wa_replace(value, arg):
    i = 0
    for a in arg:
        i += 1
        target = '{{' + str(i) + '}}'
        value = value.replace(str(target), str(a))
    return value


@register.filter
def replace_placeholders(value, arg):
    # Define a regex pattern to match placeholders like {{1}}, {{2}} (digit-based) and {{param_name}} (word-based).
    pattern = r'\{\{(.*?)\}\}'

    # Function to replace each placeholder with the corresponding value from `arg`.
    def replace_match(match):
        placeholder = match.group(1)  # Extract the content inside {{}}.

        if placeholder.isdigit():  # If the placeholder is a number (digit-based).
            index = int(placeholder) - 1  # Convert to 0-based index
            if 0 <= index < len(arg):  # Check if index is within the array bounds.
                return str(arg[index])  # Replace with the corresponding element in `arg`.
            return match.group(0)  # If the index is out of range, return the placeholder as is.

        else:  # If the placeholder is a word (word-based).
            # Check for a dictionary key match in the argument list.

            for item in arg:
                if isinstance(item, dict) and item["param_name"] == placeholder:

                    return str(item["example"])  # Return the value from the dictionary.

            return match.group(0)  # If no match found, return the placeholder as is.

    # Replace all placeholders in `value` using the regex pattern and `replace_match` function.
    return re.sub(pattern, replace_match, value)


@register.simple_tag
def get_range(value):
    """Generates a range for looping in templates."""
    return range(value)


