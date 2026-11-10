# Ground truth for the bundled fictional sites

One file per site in `tests/fixtures/sites/`, in the format of the real-corpus
ground truth (see the field definitions in the project README). The products
are invented; these files record what each invented site states, written
from the HTML before the extractor was run on it. `fixture://<slug>/path`
stands for the local test server, whose port changes from run to run.

`tests/test_fixture_score.py` requires the tool to match every field of every
file. That is a regression gate on sites the author wrote, not a measure of
accuracy on real websites.
