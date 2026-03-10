"""
This module contains the main logic of the interpreter.

IPP: You must definitely modify this file. Bend it to your will.

Author: Ondřej Ondryáš <iondryas@fit.vut.cz>
Author: Kristian Luptak
"""

import logging
from pathlib import Path
from typing import TextIO

from lxml import etree
from lxml.etree import ParseError
from pydantic import ValidationError

from interpreter.error_codes import ErrorCode
from interpreter.exceptions import InterpreterError
from interpreter.input_model import Block, ClassDef, Program

logger = logging.getLogger(__name__)


class Interpreter:
    """
    The main interpreter class, responsible for loading the source file and executing the program.
    """

    def __init__(self) -> None:
        self.current_program: Program | None = None
        self.classes: dict[str, SolClass] = {}
        self.scope: Scope = None

    def load_program(self, source_file_path: Path) -> None:
        """
        Reads the source SOL-XML file and stores it as the target program for this interpreter.
        If any program was previously loaded, it is replaced by the new one.

        IPP: If you wish to run static checks on the program before execution, this is a good place
             to call them from.
        """
        logger.info("Opening source file: %s", source_file_path)
        try:
            xml_tree = etree.parse(source_file_path)
        except ParseError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_XML, message="Error parsing input XML"
            ) from e
        try:
            self.current_program = Program.from_xml_tree(xml_tree.getroot())  # type: ignore
        except ValidationError as e:
            raise InterpreterError(
                error_code=ErrorCode.INT_STRUCTURE, message="Invalid SOL-XML structure"
            ) from e
        # static check for classes

    def execute(self, input_io: TextIO) -> None:
        """
        Executes the currently loaded program, using the provided input stream as standard input.
        """
        logger.info("Executing program")

        # create dict of userclasses,
        self.load_classes()
        logger.info("Loaded user and buildin classes")
        # add user functions and methods

        if "Main" not in self.classes.keys():
            raise InterpreterError(error_code=ErrorCode.SEM_MAIN, message="Main class missing")
        main_obj = SolObject(self.classes["Main"])
        ### TODO: create global scope here

        self.call_method(main_obj, "run", [])

    def load_classes(self):
        "Loads both buildin and classes into global class dict for easy lookup"
        # builtins
        object_cls = SolClass("Object", None, {})
        integer_cls = SolClass("Integer", object_cls, {})
        string_cls = SolClass("String", object_cls, {})
        boolean_cls = SolClass("Boolean", object_cls, {})

        self.classes["Object"] = object_cls
        self.classes["Integer"] = integer_cls
        self.classes["String"] = string_cls
        self.classes["Boolean"] = boolean_cls

        # user classes
        for cls in self.current_program.classes:
            if cls.name not in self.classes.keys():
                # recursively creates classes
                self.create_class(self, cls.name)

    def create_class(self, cls: ClassDef) -> None:
        """Creates class and links to parent, if parent doesnt exist recursively creates it"""
        if cls.name in self.classes:
            return

        # parent doesnt exist??
        if cls.parent is None:
            pass

        # recursively create parent-s
        if cls.parent not in self.classes:
            for cls_parent in self.current_program.classes:
                if cls.parent == cls_parent.name:
                    self.create_class(self, cls_parent)

        parent: SolClass = self.classes[cls.parent]
        methods: dict[str, SolMethod] = {}
        for method in cls.methods:
            if method.selector in methods:
                raise InterpreterError(
                    error_code=ErrorCode.SEM_ERROR, message="Redefinition of Method in class"
                )
            methods[method.selector] = SolMethod(method.selector, False, method.block, None)
        # create classs
        self.classes[cls.name] = SolClass(cls.name, parent, methods)

    def call_method(
        self, reciever: SolObject, selector: str, arguments: list[idk] | None = []
    ) -> None:
        if not reciever.cls.check_for_method(selector):
            if reciever.cls.name == "Main":
                raise InterpreterError(
                    error_code=ErrorCode.SEM_MAIN, message="Main class has no method named `run`"
                )
            raise InterpreterError(
                error_code=ErrorCode.SEM_UNDEF, message="Main class has no method named `run`"
            )


class SolClass:
    def __init__(self, name: str, super_class: SolClass | None, methods: dict[str, SolMethod]):
        self.name = name
        self.parent = super_class
        self.methods = methods

    def check_for_method(self, method_name: str) -> bool:
        if self.name == "Object":
            return method_name in self.methods
        if method_name in self.methods:
            return True
        return self.parent.check_for_method(method_name)


class SolObject:
    def __init__(self, cls: SolClass):
        self.cls = cls
        self.attributes = []
        self.value = None


class SolMethod:
    def __init__(self, selector: str, is_builtin: bool, block: Block | None = None, func=None):
        self.selector = selector
        self.is_builtin = is_builtin
        self.block = block
        self.function = func


class Scope:
    def __init__(self, parent_scope: Scope | None = None):
        self.parent_scope = parent_scope
        self.objects: dict[str, SolObject]
