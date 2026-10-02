"""Fallback skill — γενικές ερωτήσεις HR χωρίς συγκεκριμένη κατηγορία.

Δεν αντιστοιχεί σε κάποιο "επίσημο" skill του HR (αυτά δεν έχουν οριστεί
ακόμα). Υπάρχει ώστε το chatbox να είναι ήδη λειτουργικό πριν προστεθούν οι
πραγματικές κατηγορίες — απλά αφήνει το μοντέλο να απαντήσει με τις γενικές
του γνώσεις, μέσω του system prompt, χωρίς να χρειάζεται δικό του tool.

Κρατιέται εδώ σαν placeholder/παράδειγμα για το πώς θα μοιάζει ένα
μελλοντικό skill.
"""

from typing import Any

from .base import Skill


def _handle_general(args: dict[str, Any]) -> str:
    # Placeholder: δεν κάνει κάτι ιδιαίτερο ακόμα — το πραγματικό fallback
    # γίνεται ήδη μέσω του system prompt. Θα αντικατασταθεί όταν προστεθούν
    # πραγματικά skills με δική τους λογική/data sources.
    return "Δεν υπάρχει ακόμα συγκεκριμένο skill για αυτό το αίτημα."


general_skill = Skill(
    name="general_hr_info",
    description=(
        "Χρησιμοποίησέ το μόνο αν ο χρήστης ζητήσει ρητά γενικές πληροφορίες "
        "HR που δεν καλύπτονται από κάποιο άλλο πιο συγκεκριμένο skill."
    ),
    input_schema={"type": "object", "properties": {}, "required": []},
    handler=_handle_general,
)
