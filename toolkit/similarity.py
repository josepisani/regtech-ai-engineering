"""similarity.py — dot product, length and cosine similarity, in numpy.

WHAT IT DOES
    Four small functions on vectors (1-D arrays) and one on a matrix
    (2-D array, one vector per row):

        dot(a, b)            multiply position by position, add up
        length(a)            how long the arrow is (Pythagoras, n dimensions)
        cosine(a, b)         dot(a, b) / (length(a) * length(b)); -1..1
        cosine_matrix(M, q)  cosine of q against EVERY row of M, in one go
        top_k(M, q, k)       row positions of the k most similar rows, best first

WHY IT EXISTS
    An embedding is a vector that stands in for a piece of text. "These two
    texts are about the same thing" becomes "these two arrows point the same
    way", and cosine is the number that says how much they do. The dot product
    alone will not do: it grows when a vector is merely longer, and length
    carries no meaning here. Dividing by both lengths removes it.

    Project 2 retrieves chunks by cosine against a question. Writing the five
    lines here, instead of importing a library, is the point of Day 6: the
    author can explain every one of them.

HOW TO CALL IT
    import numpy as np
    from toolkit.similarity import cosine, cosine_matrix, top_k

    cosine(np.array([1, 0]), np.array([1, 1]))          # 0.707...
    M = np.array([[1, 0], [0, 1], [1, 1]])              # three vectors
    cosine_matrix(M, np.array([1, 0]))                  # [1.0, 0.0, 0.707]
    top_k(M, np.array([1, 0]), k=2)                     # [0, 2]

    The matrix form is what production code uses: thousands of chunks become
    thousands of rows, and `M @ q` does every dot product in one call.
"""
from __future__ import annotations

import numpy as np


def dot(a: np.ndarray, b: np.ndarray) -> float:
    """a[0]*b[0] + a[1]*b[1] + ... — big when a and b are big in the same places."""
    return float(np.dot(a, b))


def length(a: np.ndarray) -> float:
    """The length of the arrow: sqrt(a . a). Pythagoras with n legs."""
    return float(np.sqrt(np.dot(a, a)))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Direction-only similarity. 1 = same way, 0 = right angle, -1 = opposite.

    A zero vector has no direction, so its cosine with anything is defined
    here as 0.0 rather than raising a division error.
    """
    denom = length(a) * length(b)
    if denom == 0.0:
        return 0.0
    return dot(a, b) / denom


def cosine_matrix(M: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Cosine of q against every row of M. Returns one number per row.

    `M @ q` is every dot product at once. `np.linalg.norm(M, axis=1)` is every
    row length at once (axis=1 means "collapse each row to one number").
    """
    scores = M @ q
    row_lengths = np.linalg.norm(M, axis=1)
    denom = row_lengths * length(q)
    # Where a length is zero the score is already zero; avoid 0/0 -> nan.
    denom[denom == 0.0] = 1.0
    return scores / denom


def top_k(M: np.ndarray, q: np.ndarray, k: int = 5) -> list[int]:
    """Row positions of the k rows most similar to q, most similar first."""
    sims = cosine_matrix(M, q)
    order = np.argsort(sims)[::-1]  # argsort is ascending; flip for descending
    return [int(i) for i in order[:k]]
