class Uint32(int):
    MAX_VALUE = 2**32 - 1

    def __new__(cls, value):
        # 确保值在0到MAX_VALUE之间
        return super(Uint32, cls).__new__(cls, value & cls.MAX_VALUE)

    def __add__(self, other):
        return Uint32(int(self) + int(other))

    def __sub__(self, other):
        return Uint32(int(self) - int(other))

    def __mul__(self, other):
        return Uint32(int(self) * int(other))

    def __floordiv__(self, other):
        return Uint32(int(self) // int(other))

    def __mod__(self, other):
        return Uint32(int(self) % int(other))

    def __pow__(self, other, modulo=None):
        return Uint32(int(self) ** int(other))

    def __lshift__(self, other):
        return Uint32(int(self) << int(other))

    def __rshift__(self, other):
        return Uint32(int(self) >> int(other))

    def __and__(self, other):
        return Uint32(int(self) & int(other))

    def __or__(self, other):
        return Uint32(int(self) | int(other))

    def __xor__(self, other):
        return Uint32(int(self) ^ int(other))

    def __neg__(self):
        return Uint32(-int(self))

    def __invert__(self):
        return Uint32(~int(self))

    def __repr__(self):
        return f"Uint32({int(self)})"
