import unittest

from sqlglot import parse_one
from sqlglot.diff import diff, Insert, Keep, Move, Remove, Update
from sqlglot.expressions import Join, to_identifier


class TestDiff(unittest.TestCase):
    def test_simple(self):
        self._validate_delta_only(
            diff(parse_one("SELECT a + b"), parse_one("SELECT a - b")),
            [
                Remove(parse_one("a + b")),  # the Add node
                Insert(parse_one("a - b")),  # the Sub node
            ],
        )

        self._validate_delta_only(
            diff(parse_one("SELECT a, b, c"), parse_one("SELECT a, c")),
            [
                Remove(to_identifier("b", quoted=False)),  # the Identifier node
                Remove(parse_one("b")),  # the Column node
            ],
        )

        self._validate_delta_only(
            diff(parse_one("SELECT a, b"), parse_one("SELECT a, b, c")),
            [
                Insert(to_identifier("c", quoted=False)),  # the Identifier node
                Insert(parse_one("c")),  # the Column node
            ],
        )

        self._validate_delta_only(
            diff(
                parse_one("SELECT a FROM table_one"),
                parse_one("SELECT a FROM table_two"),
            ),
            [
                Update(
                    to_identifier("table_one", quoted=False),
                    to_identifier("table_two", quoted=False),
                ),  # the Identifier node
            ],
        )

    def test_node_position_changed(self):
        self._validate_delta_only(
            diff(parse_one("SELECT a, b, c"), parse_one("SELECT c, a, b")),
            [
                Move(parse_one("c")),  # the Column node
            ],
        )

        self._validate_delta_only(
            diff(parse_one("SELECT a + b"), parse_one("SELECT b + a")),
            [
                Move(parse_one("a")),  # the Column node
            ],
        )

        self._validate_delta_only(
            diff(parse_one("SELECT aaaa AND bbbb"), parse_one("SELECT bbbb AND aaaa")),
            [
                Move(parse_one("aaaa")),  # the Column node
            ],
        )

        self._validate_delta_only(
            diff(
                parse_one("SELECT aaaa OR bbbb OR cccc"),
                parse_one("SELECT cccc OR bbbb OR aaaa"),
            ),
            [
                Move(parse_one("aaaa")),  # the Column node
                Move(parse_one("cccc")),  # the Column node
            ],
        )

    def test_cte(self):
        expr_src = """
            WITH
                cte1 AS (SELECT a, b, LOWER(c) AS c FROM table_one WHERE d = 'filter'),
                cte2 AS (SELECT d, e, f FROM table_two)
            SELECT a, b, d, e FROM cte1 JOIN cte2 ON f = c
        """
        expr_tgt = """
            WITH
                cte1 AS (SELECT a, b, c FROM table_one WHERE d = 'different_filter'),
                cte2 AS (SELECT d, e, f FROM table_two)
            SELECT a, b, d, e FROM cte1 JOIN cte2 ON f = c
        """

        self._validate_delta_only(
            diff(parse_one(expr_src), parse_one(expr_tgt)),
            [
                Remove(parse_one("LOWER(c) AS c")),  # the Alias node
                Remove(to_identifier("c", quoted=False)),  # the Identifier node
                Remove(parse_one("LOWER(c)")),  # the Lower node
                Remove(parse_one("'filter'")),  # the Literal node
                Insert(parse_one("'different_filter'")),  # the Literal node
            ],
        )

    def test_join(self):
        expr_src = "SELECT a, b FROM t1 LEFT JOIN t2 ON t1.key = t2.key"
        expr_tgt = "SELECT a, b FROM t1 RIGHT JOIN t2 ON t1.key = t2.key"

        changes = diff(parse_one(expr_src), parse_one(expr_tgt))
        changes = _delta_only(changes)

        self.assertEqual(len(changes), 2)
        self.assertTrue(isinstance(changes[0], Remove))
        self.assertTrue(isinstance(changes[1], Insert))
        self.assertTrue(all(isinstance(c.expression, Join) for c in changes))

    def test_window_functions(self):
        expr_src = parse_one("SELECT ROW_NUMBER() OVER (PARTITION BY a ORDER BY b)")
        expr_tgt = parse_one("SELECT RANK() OVER (PARTITION BY a ORDER BY b)")

        self._validate_delta_only(diff(expr_src, expr_src), [])

        self._validate_delta_only(
            diff(expr_src, expr_tgt),
            [
                Remove(parse_one("ROW_NUMBER()")),  # the Anonymous node
                Insert(parse_one("RANK()")),  # the Anonymous node
            ],
        )

    def _validate_delta_only(self, actual_diff, expected_delta):
        actual_delta = _delta_only(actual_diff)
        self.assertEqual(set(actual_delta), set(expected_delta))


def _delta_only(changes):
    return [d for d in changes if not isinstance(d, Keep)]
