# kuiyo-rules

Pure rule contracts and deterministic evaluators for Kuiyo.

This package owns computation only:

- typed rule definitions, versions, clauses, inputs, and outputs;
- immutable rule artifacts and validation;
- deterministic candidate generation, evaluation, and tier calculation;
- conformance fixtures and unit tests.

It does not own database access, scheduling, job runtime state, persistence,
historical data loading, replay orchestration, or audit reporting.

## Tests

```bash
PYTHONPATH=src python -m pytest
```

