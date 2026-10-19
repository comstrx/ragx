from collections.abc import Iterable
from ipaddress import ip_address, ip_network

V4 = 4
V6 = 6
MASK = { V4: 24, V6: 48 }

class Ip:

    def is_ip ( self, text: str ) -> bool:

        try: ip_address(text.strip())
        except ValueError: return False

        return True

    def is_v4 ( self, text: str ) -> bool:

        try: return ip_address(text.strip()).version == V4
        except ValueError: return False

    def is_v6 ( self, text: str ) -> bool:

        try: return ip_address(text.strip()).version == V6
        except ValueError: return False

    def is_private ( self, text: str ) -> bool:

        try: address = ip_address(text.strip())
        except ValueError: return False

        return address.is_private or address.is_loopback or address.is_link_local

    def is_loopback ( self, text: str ) -> bool:

        try: return ip_address(text.strip()).is_loopback
        except ValueError: return False

    def is_public ( self, text: str ) -> bool:

        try: return ip_address(text.strip()).is_global
        except ValueError: return False

    def in_cidr ( self, text: str, cidr: str ) -> bool:

        try: return ip_address(text.strip()) in ip_network(cidr.strip(), strict=False)
        except ValueError: return False

    def in_any ( self, text: str, cidrs: Iterable[str] ) -> bool:

        return any(self.in_cidr(text, cidr) for cidr in cidrs)

    def client_ip ( self, forwarded: str | None, peer: str | None, trusted: Iterable[str] = () ) -> str:

        hops    = [hop.strip() for hop in (forwarded or "").split(",") if hop.strip()]
        shields = list(trusted)
        chain   = [*hops, *( [peer] if peer else [] )]

        if not shields: return hops[0] if hops else (peer or "anonymous")

        for hop in reversed(chain):

            if self.is_ip(hop) and not self.in_any(hop, shields): return hop

        return chain[0] if chain else "anonymous"

    def anonymize ( self, text: str ) -> str:

        try: address = ip_address(text.strip())
        except ValueError: return text

        return str(ip_network(f"{address}/{MASK[address.version]}", strict=False).network_address)
