from interpreter.exceptions import InterpreterError
from interpreter.error_codes import ErrorCode
from interpreter.input_model import Block


class SolClass:
    """
    Class represents runtime classes of SOL26
    """

    def __init__(
        self, name: str, super_class: SolClass | None, methods: dict[str, SolMethod]
    ) -> None:
        self.name: str = name
        self.parent: SolClass = super_class
        self.methods: dict[str, SolMethod] = methods

    def get_method(self, selector: str) -> SolMethod | None:
        if selector in self.methods:
            return self.methods[selector]

        if self.parent is not None:
            return self.parent.get_method(selector)

        if selector == "run":
            raise InterpreterError(
                error_code=ErrorCode.SEM_MAIN, message="Main class has no method named `run`"
            )
        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF,
            message=f"Class `{self.name}` has no method `{selector}`",
        )


class SolObject:
    def __init__(self, cls: SolClass, value: int | str | True | False | Block | None) -> None:
        self.cls: SolClass = cls
        self.attributes = []
        self.value: int | str | True | False | Block | None = value


class SolMethod:
    def __init__(
        self, selector: str, is_builtin: bool, func: "callable | Block", arity: int
    ) -> None:
        self.selector: str = selector
        self.is_builtin: bool = is_builtin
        self.function: "callable | Block" = func
        self.arity: int = arity


class Scope:
    """
    Class for creating scopes and finding variables in them, handling everything related to scope
    """

    def __init__(self, parent_scope: Scope | None = None) -> None:
        self.parent_scope = parent_scope
        self.objects: dict[str, SolObject] = {}

    def get_object(self, object_name: str) -> SolObject | None:
        if object_name in self.objects:
            return self.objects[object_name]

        if self.parent_scope != None:
            return self.parent_scope.get_object(object_name)

        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF, message=f"No object with `{object_name}` exists"
        )

    def set_object(self, object_name: str, object: SolObject) -> None:
        self.objects[object_name] = object
