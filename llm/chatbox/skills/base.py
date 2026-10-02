"""Common interface that every chatbox skill implements.

Ένα skill = ένα "tool" που μπορεί να καλέσει το μοντέλο (Anthropic tool-use)
όταν το μήνυμα του χρήστη ταιριάζει στην κατηγορία του.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Skill:
    name: str  # μοναδικό όνομα tool (π.χ. "leave_policy_qa")
    description: str  # περιγραφή προς το μοντέλο — πότε να το καλέσει
    input_schema: dict[str, Any]  # JSON schema των παραμέτρων του tool
    handler: Callable[[dict[str, Any]], str]  # εκτελεί το skill, επιστρέφει κείμενο

    def as_tool(self) -> dict[str, Any]:
        """Μορφή που περιμένει το Anthropic API στο `tools=[...]`."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
