"""Self-contained durable execution on Lambda + DynamoDB (no Step Functions).

A ticket's workflow is persisted after every step. When the workflow needs human
input (clarification / approval) or a long agent run, it SUSPENDS: the Lambda
returns and the run record stays in DynamoDB. A later event (SNow reply, agent
callback) RESUMES the same run from the next step - the earlier steps are not
re-executed because their results are checkpointed.
"""

from .runner import start_or_resume
from .store import RunStore

__all__ = ["start_or_resume", "RunStore"]
