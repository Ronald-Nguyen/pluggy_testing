from typing import final

class PluggyWarning(UserWarning):
    __module__ = "pluggy"

@final
class PluggyTeardownRaisedWarning(PluggyWarning):
    __module__ = "pluggy"