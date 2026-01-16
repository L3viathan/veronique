from contextvars import ContextVar


class Variable:
    def __init__(self):
        self.token = []

    def __set_name__(self, owner, name):
        self._var = ContextVar(name)

    def __get__(self, obj, otype=None):
        return self._var.get(None)

    def __set__(self, obj, value):
        self.token.append(self._var.set(value))

    def __delete__(self, obj):
        if self.token:
            self._var.reset(self.token.pop())


@type.__call__
class context:
    user = Variable()
    payload = Variable()
    impersonator = Variable()
