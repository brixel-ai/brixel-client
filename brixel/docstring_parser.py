import re


def parse_docstring(docstring: str):
    """
    Parses a docstring written in Google or NumPy style.
    Returns a dictionary in the format:
        { 'description': str, 'args': {name: {'type': ..., 'desc': ...}}, 'return': {'type': ..., 'desc': ...} }
    """

    parsed = {
        "description": "",
        "args": {},
        "return": {}
    }

    if not docstring:
        return parsed

    lines = docstring.strip().splitlines()
    mode = "desc"

    for line in lines:
        line = line.strip()

        if re.match(r"^(Args|Arguments|Parameters):", line, re.IGNORECASE):
            mode = "args"
            continue
        if re.match(r"^(Returns?|Yields?):", line, re.IGNORECASE):
            mode = "return"
            continue

        if mode == "desc":
            parsed["description"] += line + " "

        elif mode == "args":
            match = re.match(r"^(\w+)\s*\(([^)]+)\):\s*(.+)", line)
            if match:
                arg_name, arg_type, arg_desc = match.groups()
                # Normalize type by stripping "optional", "or None", etc.
                norm_type = arg_type.split(",")[0].split("or")[0].strip()
                parsed["args"][arg_name] = {
                    "type": norm_type,
                    "desc": arg_desc.strip()
                }

        elif mode == "return":
            match = re.match(r"^([^:]+):\s*(.+)", line)
            if match:
                ret_type, ret_desc = match.groups()
                norm_type = ret_type.split(",")[0].split("or")[0].strip()
                parsed["return"] = {
                    "type": norm_type,
                    "desc": ret_desc.strip()
                }

    parsed["description"] = parsed["description"].strip()
    return parsed
