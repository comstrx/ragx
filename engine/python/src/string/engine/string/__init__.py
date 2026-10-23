from .case import Case, Template
from .codec import Codec, Regex
from .compare import Compare
from .inflect import Inflect
from .safety import Entity, Inspection, Safety, Span
from .script import Probe, Script
from .strand import Kit, Strand, String
from .text import Segment, Text

string = String()

__all__ = [
    "Case", "Codec", "Compare", "Entity", "Inflect", "Inspection", "Kit", "Probe", "Regex", "Safety", "Script",
    "Segment", "Span", "Strand", "String", "Template", "Text", "string",
]
