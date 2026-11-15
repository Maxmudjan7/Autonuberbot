# telethon_patch.py
"""
Telethon v1.45.0 bug fix for MessageBox.reset_deadlines:
'RuntimeError: Called reset_deadline on an entry for which we do not have state'

In Telethon 1.45.0, MessageBox raises RuntimeError if an entry is not yet in self.map,
which causes fatal update loop crashes, disconnecting the client and causing subsequent
requests to hang or fail.
This patch safely ignores missing entries and recalculates deadlines cleanly.
"""
import logging

logger = logging.getLogger(__name__)

def apply_telethon_patch():
    try:
        import telethon._updates.messagebox as mb

        def safe_reset_deadlines(self, entries, deadline):
            if not entries:
                return
            for entry in list(entries):
                if entry not in self.map:
                    continue
                self.map[entry].deadline = deadline

            if self.next_deadline in entries:
                if self.map:
                    self.next_deadline = min(self.map.items(), key=lambda entry_state: entry_state[1].deadline)[0]
                else:
                    self.next_deadline = None
            elif self.next_deadline in self.map and deadline < self.map[self.next_deadline].deadline:
                self.next_deadline = entries[0] if isinstance(entries, list) else next(iter(entries))

        mb.MessageBox.reset_deadlines = safe_reset_deadlines
        logger.info("✅ Telethon MessageBox.reset_deadlines xavfsiz patch qilindi.")
    except Exception as e:
        logger.warning(f"Telethon patchini qo'llashda ogohlantirish: {e}")

apply_telethon_patch()
