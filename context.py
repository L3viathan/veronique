from contextvars import ContextVar

class Variable:
    def __set_name__(self, owner, name):
        self._var = ContextVar(name)

    def __get__(self, obj, otype=None):
        return self._var.get(None)

    def __set__(self, obj, value):
        self._var.set(value)


@type.__call__
class context:
    user = Variable()
    payload = Variable()
