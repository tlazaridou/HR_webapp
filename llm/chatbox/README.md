# Chatbox — LLM Router

Ο γενικός HR βοηθός (chatbox) του frontend. Ένα μοναδικό σημείο εισόδου που
δέχεται το μήνυμα του χρήστη, αποφασίζει ποιο **skill** ταιριάζει, και του
αναθέτει την απάντηση.

## Πώς δουλεύει

1. Ο χρήστης στέλνει μήνυμα στο chatbox.
2. Το [`router.py`](router.py) καλεί το Claude (Anthropic API) δίνοντάς του:
   - ένα βασικό system prompt ([`system_prompt.py`](system_prompt.py))
   - τη λίστα των διαθέσιμων **skills** ως tools (tool-use / function calling)
3. Το μοντέλο αποφασίζει αν το αίτημα ταιριάζει σε κάποιο συγκεκριμένο skill
   (καλώντας το αντίστοιχο tool) ή απαντά απευθείας.
4. Αν κληθεί ένα skill-tool, ο router εκτελεί τον handler του skill και
   επιστρέφει το αποτέλεσμα πίσω στο μοντέλο για να διαμορφώσει την τελική
   απάντηση προς τον χρήστη.

## Κατάσταση

**Σκελετός.** Δεν υπάρχουν ακόμα οι τελικές κατηγορίες/skills του HR (TODO —
θα προστεθούν μόλις οριστικοποιηθούν). Προς το παρόν υπάρχει μόνο ένα
**γενικό fallback skill** ([`skills/general.py`](skills/general.py)) που
απαντά σε οτιδήποτε δεν ταιριάζει σε συγκεκριμένη κατηγορία, ώστε το chatbox
να είναι ήδη λειτουργικό από τώρα.

## Πώς προσθέτεις ένα νέο skill αργότερα

1. Δημιούργησε ένα νέο αρχείο στο `skills/` που ορίζει ένα `Skill` instance
   (βλ. [`skills/base.py`](skills/base.py) για το interface).
2. Πρόσθεσέ το στη λίστα `SKILLS` στο [`skills/registry.py`](skills/registry.py).
3. Αυτό είναι όλο — ο router το "βλέπει" αυτόματα ως νέο tool προς το μοντέλο.

## Ανοιχτά σημεία (TODO)

- [ ] Λίστα πραγματικών κατηγοριών/skills HR.
- [ ] Πώς θα κρατιέται το conversation history (in-memory / DB / session id
      από το backend);
- [ ] Πώς θα συνδέεται το backend με αυτό το module (HTTP endpoint; direct
      call; queue;) — ίδιο ανοιχτό ερώτημα με τα υπόλοιπα LLM κομμάτια.
