"""
This module contains runtime classes used by interpreter

Author: Kristian Luptak <xluptak00@stud.fit.vut.cz>
"""

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError


class Scope:
    """
    Class for creating scopes and finding variables in them, handling everything related to scope
    """

    def __init__(self, parent_scope: Scope | None = None) -> None:
        self.parent_scope = parent_scope
        self.objects: dict[str, SolObject] = {}

    def get_object(self, object_name: str) -> SolObject:
        """
        Try to find an object in scope recursively, if it doesn't exist return None
        """

        if object_name in self.objects:
            return self.objects[object_name]

        if self.parent_scope is not None:
            return self.parent_scope.get_object(object_name)

        raise InterpreterError(
            error_code=ErrorCode.SEM_UNDEF, message=f"No object with `{object_name}` exists"
        )

    def lookup_and_set_object(self, object_name: str, obj: SolObject) -> bool:
        """
        Try to set an object in scope recursively, if it doesn't exist return false
        """
        if object_name in self.objects:
            self.objects[object_name] = obj
            return True

        if self.parent_scope is not None:
            return self.parent_scope.lookup_and_set_object(object_name, obj)

        return False

    def set_variable(self, object_name: str, obj: SolObject) -> None:
        """
        Set an object in scope, if it doesn't exist create it, if it exists update it
        """
        created: bool = self.lookup_and_set_object(object_name, obj)
        if not created:
            self.objects[object_name] = obj

    def set_parameter(self, object_name: str, obj: SolObject) -> None:
        """
        Sets parameter into current scope
        """
        self.objects[object_name] = obj


class SolClass:
    """
    Class represents runtime classes of SOL26
    """

    def __init__(self, name: str, super_class: SolClass | None = None) -> None:
        self.name: str = name
        self.parent: SolClass | None = super_class
        self.methods: dict[str, SolMethod] = {}
        self.class_methods: dict[str, SolMethod] = {}

    def get_name(self) -> str:
        """
        Encapsulation method that returns Class name
        """
        return self.name

    def get_parent_cls(self) -> SolClass | None:
        """
        Encapsulation method that returns Class parent
        """
        return self.parent

    def get_method(self, selector: str) -> SolMethod | None:
        """
        function returns method if class has one with given selector,
        runs through inheritance hierarchy
        """
        if selector in self.methods:
            return self.methods[selector]
        parent: SolClass | None = self.get_parent_cls()
        if parent is not None:
            return parent.get_method(selector)

        return None

    def set_method(self, selector: str, method: SolMethod) -> None:
        """
        Adds method into class methods of class
        """
        self.methods[selector] = method

    def get_class_method(self, selector: str) -> SolMethod:
        """
        function returns class method if class has one with given selector,
        runs through inheritance hierarchy
        """
        if selector in self.class_methods:
            return self.class_methods[selector]

        parent: SolClass | None = self.get_parent_cls()
        if parent is not None:
            return parent.get_class_method(selector)

        raise InterpreterError(
            error_code=ErrorCode.INT_DNU,
            message=f"Class `{self.name}` has no class method `{selector}`",
        )

    def set_class_method(self, selector: str, cls_method: SolMethod) -> None:
        """
        sets class method
        """
        self.class_methods[selector] = cls_method

    def get_intern_cls_attr(self) -> SolClass | None:
        """
        Returns the class of internal attribute if it exists
        """

        if self.name == "String" or self.name == "Integer":
            return self

        parent: SolClass | None = self.get_parent_cls()
        if parent is not None:
            return parent.get_intern_cls_attr()

        return None

    def is_subclass(self, cls: str) -> bool:
        """
        Checks whether self is a subclass of another SOL26 class
        """

        if self.name == cls:
            return True

        parent: SolClass | None = self.get_parent_cls()
        if parent is None:
            return False

        return parent.is_subclass(cls)


class SolMethod:
    """
    class represents methods of SOL26 with both builtin callable and user blocks as functions
    """

    def __init__(
        self, selector: str, is_builtin: bool, func: object, arity: int, cls: SolClass
    ) -> None:
        self.cls: SolClass = cls
        self.selector: str = selector
        self.is_builtin: bool = is_builtin
        self.function: object = func
        self.arity: int = arity


class SolObject:
    """
    class represents runtime objects of SOL26 with different attributs for different
    types of objects
    """

    def __init__(self, cls: SolClass, intern_value: int | str | None) -> None:
        self.cls: SolClass = cls
        self.intern_value: int | str | None = intern_value
        self.instance_attributes: dict[str, SolObject] = {}  # uder defined
        self.instance_method: dict[str, SolMethod] = {}  # block value method
        self.closure_scope: Scope | None = None  # block closure scope

    def set_instance_attr(self, name: str, attr_obj: SolObject) -> None:
        """
        Encapsulation method for setting instance attributes
        """
        self.instance_attributes[name] = attr_obj

    def get_instance_attr(self, name: str) -> SolObject | None:
        """
        Encapsulation method for getting instance attributes
        """
        return self.instance_attributes.get(name)

    def get_cls(self) -> SolClass:
        """
        Encapsulation method for getting class of object
        """
        return self.cls

    def get_intern_value(self) -> int | str | None:
        """
        Encapsulation method for getting intern attribute of object
        """
        return self.intern_value

    def set_closure_scope(self, scope: Scope) -> None:
        """
        Encapsulation method for setting closure scope of block objects
        """
        self.closure_scope = scope

    def get_closure_scope(self) -> Scope | None:
        """
        Encapsulation method for getting closure scope of block objects
        """
        return self.closure_scope

    def set_instance_method(self, selector: str, instance_method: SolMethod) -> None:
        """
        Encapsulation method for setting instance method of block objects
        """
        self.instance_method[selector] = instance_method

    def get_instance_method(self, selector: str) -> SolMethod | None:
        """
        Encapsulation method for getting instance method of block objects
        """
        return self.instance_method.get(selector)
