"""Aho-Corasick multi-pattern substring matcher.

Finds every occurrence of a set of literal patterns in a text in a single pass:
O(text + matches) after an O(sum of pattern lengths) build, instead of one
``str.find`` per pattern (O(patterns * text)). Used by the rule engine's literal
filter bucket, where a real blocklist can carry thousands of unanchored
substring filters that all have to be tested against every request URL.
"""


from typing import Iterable


class AhoCorasick:
    """Immutable automaton: build once with ``find`` as the query."""

    __slots__ = ("_out", "_link", "_goto")

    def __init__(self, patterns: Iterable[str]) -> None:
        # goto: list of dicts (char -> state). state 0 is the root.
        goto: list[dict] = [{}]
        # out[state] = tuple of patterns that END at this state.
        out: list[tuple] = [()]

        # 1. Build the trie.
        for p in patterns:
            if not p:
                continue
            node = 0
            for ch in p:
                nxt = goto[node].get(ch)
                if nxt is None:
                    goto.append({})
                    out.append(())
                    nxt = len(goto) - 1
                    goto[node][ch] = nxt
                node = nxt
            out[node] = out[node] + (p,)

        # 2. Failure links (BFS): longest proper suffix that is also a trie node.
        link = [0] * len(goto)
        queue = list(goto[0].values())
        for node in queue:
            link[node] = 0
        head = 0
        while head < len(queue):
            node = queue[head]
            head += 1
            for ch, nxt in goto[node].items():
                queue.append(nxt)
                state = link[node]
                while state and ch not in goto[state]:
                    state = link[state]
                link[nxt] = goto[state].get(ch, 0) if goto[state].get(ch, 0) != nxt else 0
                if link[nxt] != nxt:
                    out[nxt] = out[nxt] + out[link[nxt]]

        self._goto = goto
        self._link = link
        self._out = out

    def find(self, text: str) -> set:
        """Return the set of patterns occurring in ``text``."""
        hits: set = set()
        goto, link, out = self._goto, self._link, self._out
        state = 0
        for ch in text:
            while state and ch not in goto[state]:
                state = link[state]
            state = goto[state].get(ch, 0)
            if out[state]:
                hits.update(out[state])
        return hits
