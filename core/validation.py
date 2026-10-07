"""Shared input validation helpers for blueprint create/update handlers.

These helpers centralize two common patterns that were previously duplicated
(and under-validated) across blueprints: bounded integer parsing and JSON
field validation/normalization.
"""

import json


def parse_int_bounded(value, field, lo, hi, default=None):
    """Parse ``value`` as an integer bounded within ``[lo, hi]``.

    - If ``value`` is ``None`` or an empty string:
        - raises ``ValueError('{field}_required')`` when ``default`` is ``None``
        - otherwise returns ``default``
    - If ``value`` cannot be converted to ``int``, raises
      ``ValueError('{field}_not_integer')``.
    - If the parsed integer falls outside ``[lo, hi]``, raises
      ``ValueError('{field}_out_of_range')``.
    """
    if value is None or value == '':
        if default is None:
            raise ValueError(f'{field}_required')
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field}_not_integer')

    if parsed < lo or parsed > hi:
        raise ValueError(f'{field}_out_of_range')

    return parsed


def clean_json_field(value, field):
    """Validate/normalize a JSON-bearing field.

    - Returns ``None`` for ``None``/empty-string ``value``.
    - If ``value`` is already a ``dict``/``list``, returns ``json.dumps(value)``.
    - Otherwise, attempts ``json.loads(value)`` purely to validate the JSON,
      and returns the original string unchanged.
    - Raises ``ValueError('{field}_invalid_json')`` when validation fails.
    """
    if value is None or value == '':
        return None

    if isinstance(value, (dict, list)):
        return json.dumps(value)

    try:
        json.loads(value)
    except (TypeError, ValueError):
        raise ValueError(f'{field}_invalid_json')

    return value
