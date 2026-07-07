Policy Agent
============

Simple agent that evaluates `SupplierEvaluation` records against procurement policies using the existing `PolicyEvaluationService`.

Usage
-----

Create a `PolicyAgent` and call `execute()` with a list of `SupplierEvaluation` instances:

```py
from agents.policy_agent.agent import PolicyAgent
from agents.supplier_selection.models import SupplierEvaluation

agent = PolicyAgent()
result = agent.execute([/* SupplierEvaluation objects */], policy_name="STANDARD")
```

Testing
-------

Run tests with `pytest` from the repository root:

```bash
pytest -q
```
