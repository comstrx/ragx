from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re

type Value = object
type Where = Mapping[str, Value]

IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class Statement:

    sql    : str
    params : tuple[Value, ...] = ()


class Query:

    def ident ( self, name: str ) -> str:

        if name == "*": return name
        if not IDENT.match(name): raise ValueError(name)

        return f'"{name}"'

    def columns ( self, columns: Sequence[str] ) -> str:
        return ", ".join(self.ident(column) for column in columns) or "*"

    def order ( self, order: Sequence[str] ) -> str:

        parts = []

        for entry in order:

            descending = entry.startswith("-")
            column     = self.ident(entry.lstrip("-+"))

            parts.append(f"{column} DESC" if descending else f"{column} ASC")

        return f" ORDER BY {', '.join(parts)}" if parts else ""

    def where ( self, where: Where | None, start: int = 1 ) -> tuple[str, list[Value]]:

        if not where: return "", []

        clauses: list[str]  = []
        params: list[Value] = []

        for column, value in where.items():

            name = self.ident(column)

            if value is None: clauses.append(f"{name} IS NULL")
            elif isinstance(value, list | tuple | set | frozenset):

                params.append(list(value))
                clauses.append(f"{name} = ANY(${start + len(params) - 1})")

            else:

                params.append(value)
                clauses.append(f"{name} = ${start + len(params) - 1}")

        return " WHERE " + " AND ".join(clauses), params

    def select (
        self, table: str, columns: Sequence[str] = ("*",), where: Where | None = None,
        order: Sequence[str] = (), limit: int | None = None, offset: int | None = None,
    ) -> Statement:

        clause, params = self.where(where)
        sql            = f"SELECT {self.columns(columns)} FROM {self.ident(table)}{clause}{self.order(order)}"

        if limit is not None:

            params.append(int(limit))
            sql += f" LIMIT ${len(params)}"

        if offset:

            params.append(int(offset))
            sql += f" OFFSET ${len(params)}"

        return Statement(sql, tuple(params))

    def count ( self, table: str, where: Where | None = None ) -> Statement:

        clause, params = self.where(where)

        return Statement(f"SELECT count(*) FROM {self.ident(table)}{clause}", tuple(params))

    def insert ( self, table: str, values: Mapping[str, Value], returning: Sequence[str] = ("*",) ) -> Statement:

        if not values: raise ValueError(table)

        names   = ", ".join(self.ident(column) for column in values)
        holders = ", ".join(f"${index}" for index in range(1, len(values) + 1))
        back    = f" RETURNING {self.columns(returning)}" if returning else ""

        return Statement(f"INSERT INTO {self.ident(table)} ({names}) VALUES ({holders}){back}", tuple(values.values()))

    def update (
        self, table: str, values: Mapping[str, Value], where: Where, returning: Sequence[str] = ("*",),
    ) -> Statement:

        if not values or not where: raise ValueError(table)

        sets           = ", ".join(f"{self.ident(column)} = ${index}" for index, column in enumerate(values, start=1))
        clause, params = self.where(where, start=len(values) + 1)
        back           = f" RETURNING {self.columns(returning)}" if returning else ""

        return Statement(f"UPDATE {self.ident(table)} SET {sets}{clause}{back}", (*values.values(), *params))

    def delete ( self, table: str, where: Where, returning: Sequence[str] = () ) -> Statement:

        if not where: raise ValueError(table)

        clause, params = self.where(where)
        back           = f" RETURNING {self.columns(returning)}" if returning else ""

        return Statement(f"DELETE FROM {self.ident(table)}{clause}{back}", tuple(params))

    def raw ( self, sql: str, *params: Value ) -> Statement:
        return Statement(sql, params)
