try:
    import typing as ty
    from contextlib import contextmanager

    import sqlalchemy as sa
    from rich.console import Console
    from rich.prompt import Confirm, Prompt

    class SQLDebugger:
        def __init__(self, engine: sa.Engine, echo: bool = True):

            self.engine = engine
            self.inspector = sa.inspect(engine)
            self._console = Console(color_system="truecolor")
            self._echo = echo

        def __str__(self):
            return f"{self.__class__.__name__}({self.engine.url})"

        def __call__(self, sql: str) -> list[dict[str, ty.Any]]:
            return self.execute(sql)

        @property
        def tables(self):
            return self.inspector.get_table_names()

        @property
        def console(self):
            return self._console

        def show_sql(self, sql: str) -> None:
            from rich.syntax import Syntax

            sql_ = Syntax(sql, "sql", theme="nord-darker", line_numbers=True)
            self._console.log(sql_)

        def show_result(
            self, cols: sa.engine.result.RMKeyView, result: list[dict[str, ty.Any]]
        ) -> None:
            from rich.style import Style
            from rich.table import Table

            table = Table(expand=True, show_lines=True)
            column_style = Style(color="green")

            for col in cols:
                table.add_column(col, style=column_style)

            for row in result:
                table.add_row(*[str(row[col]) for col in cols])

            self._console.print(table)

        def execute(self, sql: str) -> list[dict[str, ty.Any]]:
            with self.engine.begin() as conn:
                res = conn.execute(sa.text(sql))
                cols = res.keys()
                rows = res.all()

            results = [dict(row._mapping) for row in rows]  # type: ignore

            if self._echo:
                self.console.log(f"\n[bold green]success[/bold green]")
                self.show_result(cols, results)
            return results

        def interactive(self) -> None:

            while True:
                sql_caluse = Prompt.ask("sql> ")
                self.show_sql(sql_caluse)
                if sql_caluse == "exit":
                    break
                self.execute(sql_caluse)

        def close(self) -> None:
            self.engine.dispose()
            self.console.log(f"\n[bold green]connection released[/]")

        def confirm(self, sql: str) -> bool:
            self.show_sql(sql)
            result = Confirm.ask("\n[bold red]Are you sure to execute? \\[yes/N][/]")
            return result

        @contextmanager
        def lifespan(self):
            try:
                yield self
            except KeyboardInterrupt:
                self.console.log(f"\n[bold red]canceled[/bold red]")
            finally:
                self.close()

        @classmethod
        def from_url(cls, db_url: str):
            from sqlalchemy import create_engine

            engine = create_engine(db_url, isolation_level="SERIALIZABLE", echo=True)
            return cls(engine)

    def get_parser():
        from argparse import ArgumentParser

        parser = ArgumentParser()
        parser.add_argument("sql", nargs="?")
        parser.add_argument("--url", action="store")
        parser.add_argument("-i", "--interactive", action="store_true")
        return parser

    def sqlcli():
        import os
        import sys

        from sqlalchemy import create_engine

        parser = get_parser()
        ns = parser.parse_args()

        if not ns.sql and not ns.interactive:
            print(f"sql or interactive mode required")
            sys.exit(0)

        url = os.environ["DB_URL"]

        engine = create_engine(url)
        sqldbg = SQLDebugger(engine)
        with sqldbg.lifespan() as sqldbg:
            if ns.interactive:
                sqldbg.interactive()
                sys.exit(0)
            sql_query = ns.sql

            if sqldbg.confirm(sql_query):
                result = sqldbg.execute(sql_query)
                print(result)
            sys.exit(0)

    if __name__ == "__main__":
        sqlcli()
except ImportError:
    pass
