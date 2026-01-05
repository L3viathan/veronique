import unicodedata

from veronique import db
from veronique.db import LABEL
from veronique.utils import timed_cache
from veronique.settings import settings as S


def update_index_for_doc(cur, table, id, name):
    all_ngrams = list(ngrams(name))
    cur.execute(
        "DELETE FROM inverted_index WHERE table_name = ? AND id = ?",
        (table, id),
    )
    cur.execute(
        "DELETE FROM forward_index WHERE table_name = ? AND id = ?",
        (table, id),
    )
    for ngram in all_ngrams:
        cur.execute(
            "INSERT INTO inverted_index (table_name, id, ngram) VALUES (?, ?, ?)",
            (table, id, ngram),
        )
    cur.execute(
        "INSERT INTO forward_index (table_name, id, length) VALUES (?, ?, ?)",
        (table, id, len(all_ngrams)),
    )


def rebuild_search_index(cur):
    cur.execute("DELETE FROM inverted_index")
    cur.execute("DELETE FROM forward_index")
    for row in cur.execute(
        "SELECT subject_id, value FROM claims WHERE verb_id = ?", (LABEL,)
    ).fetchall():
        print("Updating claim")
        update_index_for_doc(cur, "claims", row["subject_id"], row["value"])
    for row in cur.execute("SELECT id, label FROM verbs").fetchall():
        update_index_for_doc(cur, "verbs", row["id"], row["label"])
    for row in cur.execute("SELECT id, label FROM queries").fetchall():
        update_index_for_doc(cur, "queries", row["id"], row["label"])

    db.conn.commit()



def ngrams(string):
    sanitized = unicodedata.normalize("NFKD", string).casefold()
    iterables = [iter(sanitized) for _ in range(S.search_n)]
    for index, it in enumerate(iterables):
        for _ in range(index):
            next(it)
    yield from ("".join(e) for e in zip(*iterables))


@timed_cache(60*60)
def calculate_avgdl(cur):
    row = cur.execute("SELECT AVG(length) AS avgdl FROM forward_index").fetchone()
    if not row:
        return 15  # just some semi-realistic value
    return row["avgdl"]


def find(cur, query, *, table=None, page_size=20, page_no=0):
    tokens = list(ngrams(query))
    # This is an attempt at implementing BM25 on a character ngram level.
    # k_1 is unusually low, but this seems to give better results.
    avgdl = calculate_avgdl(cur)
    cur.execute(f"""
        SELECT table_name, id, SUM(t_score) FROM (
            SELECT i.table_name, i.id, (count(1) * ({S.search_k_1} + 1))/(count(1) + {S.search_k_1} * (1 - {S.search_b} + {S.search_b} * (f.length / {avgdl}))) AS t_score
            FROM inverted_index i
            LEFT JOIN forward_index f ON i.table_name=f.table_name AND i.id=f.id
            WHERE i.ngram IN ({",".join("?"*len(tokens))})
            {f'AND i.table_name="{table}"' if table else ""}
            GROUP BY i.table_name, i.id, i.ngram
        )
        GROUP BY table_name, id
        ORDER BY SUM(t_score) DESC
        LIMIT {page_size}
        OFFSET {page_no * page_size}
    """, tuple(tokens))
    return cur.fetchall()
