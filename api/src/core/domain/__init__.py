from .cloudflare import Cloudflare
from .contract import Availability, Contact, Domain, Local, Record, Registrar, Registration, Verification
from .domains import Domains
from .vercel import Vercel

domain = Domains()

__all__ = [
    "Availability", "Cloudflare", "Contact", "Domain", "Domains", "Local", "Record", "Registrar", "Registration",
    "Vercel", "Verification", "domain",
]
