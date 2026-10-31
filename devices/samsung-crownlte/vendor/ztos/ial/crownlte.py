# SPDX-License-Identifier: GPL-2.0-only
"""Crown bring-up: suspend remains unavailable until separately validated."""
from ztos_ial.backends import NotSupported
from ztos_ial.backends.generic import Sleep as GenericSleep


class Sleep(GenericSleep):
    def available(self):
        return False

    def props(self):
        return {"Method": "unavailable", "Enabled": False, "State": "awake",
                "Inhibitors": sorted(f"{who}: {why}" for who, why, _ in self.held.values())}

    def m_SetEnabled(self, enabled):
        if enabled:
            raise NotSupported("suspend is not validated on crownlte")
