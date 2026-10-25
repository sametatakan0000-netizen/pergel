"""Standard browser suites: Speedometer 3.1 and JetStream 3.0 (Task 3.1).

Automation hooks below were read from the suites' own sources on 2026-10-25 —
they are NOT guessed:

Speedometer 3.1 (WebKit/Speedometer branch ``release/3.1``; deployed at
https://browserbench.org/Speedometer3.1/)
- Start: URL param ``startAutomatically`` (``resources/params.mjs``: presence of
  the key sets startAutomatically; ``resources/main.mjs`` starts the run when it
  is set). Other params: ``viewport=<w>x<h>`` (min 800x600), ``iterationCount``,
  ``suite``/``suites``, ``tags``.
- Result: ``resources/main.mjs`` writes the score into ``#result-number``
  (textContent = formattedMean) and the margin into ``#confidence-number``
  ("± formattedDelta"); on invalid subtests it writes "Error" into
  ``#result-number``. So: parse ``#result-number``; treat "Error" as failure.

JetStream 3 (WebKit/JetStream; deployed at https://browserbench.org/JetStream3.0/)
- Start: URL param ``startAutomatically`` (``utils/params.js``; implies a 100 ms
  startDelay). Other params: ``startDelay``, ``report``, ``test``/``tests``/
  ``testList``/``tag``, ``testIterationCount``/``iterations``, ``worstCaseCount``,
  ``prefetchResources=false``, ``dumpJSONResults``.
- Result: ``JetStreamDriver.js`` adds class ``done`` to ``#result-summary`` and
  renders ``<div class="score">{uiFriendlyScore(overallScore)}</div><label>Score</label>``
  first (uiFriendlyScore = integer as-is, else toFixed(2)). A ``JetStreamDone``
  CustomEvent carrying the full results object is dispatched on completion —
  a good wait-hook for the live run.

Lightpanda is reported as ``n/a (unsupported Web APIs)``, never as 0. Scores are
machine-specific: never place them next to vendor numbers from other hardware
(``bench/reported.json`` keeps those in their own section).

The live run is a manual receipt; unit tests exercise only the parsers below
against captured HTML snippets under ``tests/fixtures/``. ``run_suite(adapter,
url, timeout_s)`` drives any adapter exposing ``fetch(url, timeout_s=...) ->
str`` that returns the rendered DOM after the suite finished.
"""
import re
from typing import Callable, Dict

LIGHTPANDA_STATUS = "n/a (unsupported Web APIs)"

SPEEDOMETER_URL = "https://browserbench.org/Speedometer3.1/?startAutomatically=1"
JETSTREAM_URL = "https://browserbench.org/JetStream3.0/?startAutomatically=1"


def _visible_html(html: str) -> str:
    """Drop HTML comments: captured page sources carry sample markup inside
    comments (and our fixtures document their structure that way)."""
    return re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)


def _parse_score_text(text: str) -> float:
    cleaned = text.replace(",", "").replace("\u00a0", " ").strip()
    match = re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned)
    if not match:
        raise ValueError(f"score text is not numeric: {text!r}")
    return float(cleaned)


def extract_speedometer_score(html: str) -> float:
    """Extract the Speedometer 3.1 score from rendered/captured HTML.

    Reads #result-number (written by resources/main.mjs on run completion);
    'Error' (invalid subtests) and a missing element are failures, not 0.
    """
    match = re.search(r'id="result-number"[^>]*>([^<]*)<', _visible_html(html))
    if not match:
        raise ValueError("no #result-number element in captured HTML")
    text = match.group(1).strip()
    if text == "Error":
        raise ValueError("Speedometer reported Error (invalid subtests)")
    if not text:
        raise ValueError("Speedometer #result-number is empty (run not finished?)")
    return _parse_score_text(text)


def extract_jetstream_score(html: str) -> float:
    """Extract the JetStream 3 overall score from rendered/captured HTML.

    Reads the first ``<div class="score">`` immediately followed by
    ``<label>Score</label>`` inside the #result-summary block that
    JetStreamDriver.js renders on completion.
    """
    match = re.search(
        r'<div class="score">\s*([^<]*?)\s*</div>\s*<label>Score</label>',
        _visible_html(html),
    )
    if not match:
        raise ValueError("no rendered JetStream score in captured HTML (run not finished?)")
    return _parse_score_text(match.group(1))


_PARSERS: Dict[str, Callable[[str], float]] = {
    "Speedometer": extract_speedometer_score,
    "JetStream": extract_jetstream_score,
}


def run_suite(adapter, url: str, timeout_s: float) -> float:
    """Run a standard suite through an adapter and return its numeric score.

    ``adapter.fetch(url, timeout_s=...)`` must return the rendered DOM after the
    run completed (e.g. after the ``JetStreamDone`` event or a non-empty
    #result-number). The suite is picked by URL family; unknown URLs are
    rejected rather than guessed at.
    """
    parser = next((p for name, p in _PARSERS.items() if name in url), None)
    if parser is None:
        raise ValueError(f"not a known suite URL: {url!r}")
    html = adapter.fetch(url, timeout_s=timeout_s)
    return parser(html)
