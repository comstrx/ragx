from .safety import Entity, Inspection, Safety
from .segments import Segment, Segments
from .case import Case
from .codec import Codec
from .compare import Compare
from .inflect import Inflect
from .probe import Probe
from .regex import Regex
from .script import Script
from .strand import Kit, Strand
from .string import String
from .template import Template
from .text import Text

string = String()

safety = Safety()
segments = Segments()

__all__ = [
    "Case", "Codec", "Compare", "Entity", "Inflect", "Inspection",
    "Kit", "Probe", "Regex", "Safety", "Script", "Segment",
    "Segments", "Strand", "String", "Template", "Text", "safety",
    "segments", "string",
]
