def apply_update_operator(current, operator: str, value):
    """
    Applies an assignment operator (+=, -=, *=, etc.) to an existing value.

    Args:
        current: The current value.
        operator: A string representing the operator (e.g., "+=").
        value: The value to apply.

    Returns:
        The result of the operation.

    Raises:
        ValueError: ValueError: If the operator is not supported.
    """
    if operator == "+=":
        return current + value
    elif operator == "-=":
        return current - value
    elif operator == "*=":
        return current * value
    elif operator == "/=":
        return current / value
    elif operator == "//=":
        return current // value
    elif operator == "%=":
        return current % value
    elif operator == "**=":
        return current ** value
    elif operator == "&=":
        return current & value
    elif operator == "|=":
        return current | value
    elif operator == "^=":
        return current ^ value
    elif operator == "<<=":
        return current << value
    elif operator == ">>=":
        return current >> value
    else:
        raise ValueError(f"Unsupported operator '{operator}'")
