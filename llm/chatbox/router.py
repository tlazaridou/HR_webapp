"""Κεντρικό σημείο εισόδου του chatbox: παίρνει το μήνυμα του χρήστη, καλεί
το Claude με τα διαθέσιμα skills ως tools, εκτελεί όποιο skill επιλεγεί, και
επιστρέφει την τελική απάντηση.

Η συνάρτηση `handle_message` είναι αυτή που θα καλεί το backend (π.χ. μέσα
από ένα HTTP endpoint) — βλ. TODO στο README για το πώς ακριβώς θα γίνεται
αυτή η σύνδεση.
"""

import os

import anthropic

from .skills.registry import SKILLS
from .system_prompt import SYSTEM_PROMPT

MODEL = "claude-sonnet-5"

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_skills_by_name = {skill.name: skill for skill in SKILLS}


def handle_message(conversation_history: list[dict], user_message: str) -> str:
    """Επεξεργάζεται ένα μήνυμα χρήστη και επιστρέφει την απάντηση του chatbox.

    `conversation_history`: προηγούμενα μηνύματα σε μορφή Anthropic API
    (`[{"role": "user" | "assistant", "content": ...}, ...]`). Το πώς
    αποθηκεύεται/ανακτάται αυτό το ιστορικό είναι ακόμα ανοιχτό θέμα
    (βλ. README) — εδώ απλά περνιέται ως παράμετρος.
    """
    messages = [*conversation_history, {"role": "user", "content": user_message}]
    tools = [skill.as_tool() for skill in SKILLS]

    while True:
        response = _client.messages.create(
            model=MODEL,
            system=SYSTEM_PROMPT,
            tools=tools,
            messages=messages,
            max_tokens=1024,
        )

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            skill = _skills_by_name[block.name]
            result_text = skill.handler(block.input)
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                }
            )
        messages.append({"role": "user", "content": tool_results})
