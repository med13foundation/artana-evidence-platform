# TG04 V6 Selection Preflight

## Decision

V6 stopped before any model call because its selected source is not hidden. The
exact sentence already exists in `tests/unit/test_nested_event_holdout_trial.py`
as an earlier null-result fixture.

The selection seed was chained correctly and the scientific graph was usable,
but a development-visible source cannot measure generalization. The next
selection must apply an exact repository exposure check across the whole candidate
universe before ranking rather than relying only on a hand-maintained document
list.
