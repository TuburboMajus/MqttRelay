import re
from datetime import datetime
from typing import Any, Mapping

# --- helpers ---------------------------------------------------------------

def _get_by_path(ctx: Mapping[str, Any], path: str, default=None):
    cur = ctx
    for part in path.split('.'):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def _to_dt(x):
    # optional: promote ISO-8601 strings to datetime for comparison
    if isinstance(x, str):
        try:
            return datetime.fromisoformat(x.replace('Z', '+00:00'))
        except Exception:
            return x
    return x

def _cmp(op, left, right):
    left, right = _to_dt(left), _to_dt(right)
    if op == '$eq':  return left == right
    if op == '$ne':  return left != right
    if op == '$gt':  return left >  right
    if op == '$gte': return left >= right
    if op == '$lt':  return left <  right
    if op == '$lte': return left <= right
    raise ValueError(f'unsupported op {op}')

def _regex_match(val, spec):
    if isinstance(spec, dict):
        pattern = spec.get('pattern', '')
        flags_s = spec.get('flags', '')
        flags = 0
        if 'i' in flags_s: flags |= re.IGNORECASE
        if 'm' in flags_s: flags |= re.MULTILINE
    else:
        pattern, flags = str(spec), 0
    return isinstance(val, str) and re.search(pattern, val, flags) is not None

def _contains(container, needle):
    if isinstance(container, str) and isinstance(needle, str):
        return needle in container
    if isinstance(container, (list, tuple, set)):
        return needle in container
    return False

def _between(val, rng):
    if not isinstance(rng, (list, tuple)) or len(rng) != 2:
        return False
    lo, hi = rng
    val, lo, hi = _to_dt(val), _to_dt(lo), _to_dt(hi)
    return val is not None and lo is not None and hi is not None and lo <= val <= hi

# --- core ------------------------------------------------------------------

def eval_mongo_dsl(rule: Any, ctx: Mapping[str, Any]) -> bool:
    """
    rule: dict/list/bool using $and/$or/$not and per-field ops
    ctx:  message context, e.g. {
           "topic": "...",
           "message": {"qos": 1, "retain": False, "received_at": "2025-09-16T19:20:25Z"},
           "payload": {"battery": 3.71, "alarms": ["LOW_BATT"]},
           "device": {...}, "device_type": {...}
         }
    """
    if rule is True:  return True
    if rule is False: return False

    if isinstance(rule, list):
        # implicit AND over list
        return all(eval_mongo_dsl(r, ctx) for r in rule)

    if isinstance(rule, dict):
        # logical
        if '$and' in rule: return all(eval_mongo_dsl(r, ctx) for r in rule['$and'])
        if '$or'  in rule: return any(eval_mongo_dsl(r, ctx) for r in rule['$or'])
        if '$not' in rule: return not eval_mongo_dsl(rule['$not'], ctx)

        # field predicate(s)
        for field, cond in rule.items():
            val = _get_by_path(ctx, field, default=None)
            # shorthand equality: {"field": 123}
            if not isinstance(cond, dict) or not any(k.startswith('$') for k in cond.keys()):
                if val != cond:
                    return False
                continue

            for op, arg in cond.items():
                if op in ('$eq','$ne','$gt','$gte','$lt','$lte'):
                    if not _cmp(op, val, arg): return False
                elif op == '$in':
                    if val not in arg: return False
                elif op == '$nin':
                    if val in arg: return False
                elif op == '$exists':
                    exists = (val is not None)
                    if bool(arg) != exists: return False
                elif op == '$regex':
                    if not _regex_match(val, arg): return False
                elif op == '$contains':
                    if not _contains(val, arg): return False
                elif op == '$startswith':
                    if not (isinstance(val, str) and val.startswith(str(arg))): return False
                elif op == '$endswith':
                    if not (isinstance(val, str) and val.endswith(str(arg))): return False
                elif op == '$between':
                    if not _between(val, arg): return False
                elif op == '$elemMatch':
                    if not isinstance(val, list) or not any(eval_mongo_dsl(arg, {"this": e, **ctx}) or eval_mongo_dsl(arg, e) for e in val):
                        return False
                else:
                    raise ValueError(f'unsupported operator {op}')
        return True

    # anything else is invalid
    return False
