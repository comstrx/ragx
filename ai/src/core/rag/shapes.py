from core.json import Shape

def answer_shape ( identifiers: tuple[str, ...] ) -> Shape:

    return Shape({
        "type": "object",
        "properties": {
            "answer": {"type": "string", "minLength": 1},
            "citations": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": list(identifiers)}},
        },
        "required": ["answer", "citations"], "additionalProperties": False,
    })

def evaluation_shape () -> Shape:

    return Shape({
        "type": "object",
        "properties": {
            "score": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
        },
        "required": ["score", "reasoning"], "additionalProperties": False,
    })
