def apply_update_operator(current, operator: str, value):
    """
    Applique un opérateur d'affectation (+=, -=, *=, etc.) sur une valeur existante.

    Args:
        current: La valeur actuelle.
        operator: Une chaîne représentant l'opérateur (ex: "+=").
        value: La valeur à appliquer.

    Returns:
        Le résultat de l'opération.

    Raises:
        ValueError: Si l'opérateur n'est pas supporté.
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
