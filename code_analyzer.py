""" It's a simple static analyzer tool that finds common stylistic issues in Python code according to PEP8.
The program obtains the path to the file or directory via command-line arguments:
> python code_analyzer.py directory-or-file
"""
from collections import deque
from os import scandir
from sys import argv
import ast
import re


class CodeAnalyzer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.path: str = ""
        self.directory_path: str = ""
        self.string: str = ""
        self.line_number: int = 1
        self.match_object = None
        self.last_3_lines_queue: deque = deque()
        self.blank_lines_counter: int = 0
        self.hash_index: int = 0
        self.warning_queue: deque = deque()
        self.file_list_of_lines: list = []
        self.file_text: str = ''

    def refresh_hash_index(self) -> int:
        if '#' in self.string:
            return self.string.index('#')
        else:
            return len(self.string)

    def check_line_length(self) -> None:
        """ Checks the length of the line."""
        if len(self.string) > 79:
            print(f"{self.path}: Line {self.line_number}: S001 Too long line.")

    def check_indentation(self) -> None:
        """ Checks the size of indentation."""
        whitespace_counter = 0
        string = self.string
        while string.startswith(" "):
            string = string[1:len(string)]
            whitespace_counter += 1
        if whitespace_counter % 4 != 0:
            print(f"{self.path}: Line {self.line_number}: S002 Indentation is not a multiple of four.")

    def check_semicolon(self) -> None:
        """ Checks is there an unnecessary semicolon after a statement."""
        if ';' in self.string and self.find_extra_semicolon(self.string):
            print(f"{self.path}: Line {self.line_number}: S003 Unnecessary semicolon after a statement.")
        return None

    def check_comment_spaces(self) -> None:
        """ Checks how many spaces are before inline comment."""
        if '#' in self.string:
            if self.string.lstrip().startswith('#'):
                return None
            elif self.string[:self.hash_index].endswith("  "):
                return None
            else:
                print(f"{self.path}: "
                      f"Line {self.line_number}: S004 At least two spaces before inline comments required.")
        return None

    def check_is_todo(self) -> None:
        """ Checks _TODO marks in comments."""
        if '#' in self.string:
            comment = self.string[self.hash_index + 1:].casefold()
            if "todo" in comment:
                print(f"{self.path}: Line {self.line_number}: S005 TODO found.")

    def check_blank_lines(self) -> None:
        """ Checks how mane blank lines are used before this line."""
        self.last_3_lines_queue.append(self.string)
        if len(self.last_3_lines_queue) > 4:  # We don't need to keep long list, 4 strings are enough.
            self.last_3_lines_queue.popleft()
        if self.string.startswith(('\n', '\r')):
            self.blank_lines_counter += 1
        else:
            if self.blank_lines_counter == 3:
                print(f"{self.path}: Line {self.line_number}: S006 More than two blank lines used before this line.")
            self.blank_lines_counter = 0

    def check_definition_spaces(self) -> None:
        """ Checks how many spaces is after '%construction_name%' (def or class)."""
        if len(self.match_object.group("space")) > 1:
            print(f"{self.path}: Line {self.line_number}: "
                  f"S007 Too many spaces after '{self.match_object.group('construction_name')}'.")

    def is_camel_case(self, name: str):
        """ If name in CamelCase style return match object, else None."""
        return re.match(r"[A-Z][a-z]+[A-Z]?[a-z]+", name)

    def is_snake_case(self, name: str):
        """ If name in snake_case style return match object, else None."""
        return re.match(r"_{,2}?[a-z]+[0-9]?_?[a-z]?[0-9]?", name)

    def check_class_name(self) -> None:
        """ Checks the class name in CamelCase style or not.
        match_object contains groups' names: construction_name, space, entity_name, arguments.
        Source of groups is get_groups() function.
        """
        if self.match_object.group('construction_name') != "class":
            return None
        for class_name in (self.match_object.group("entity_name"), self.match_object.group("arguments")):
            if len(class_name) == 0:
                return None
            if not self.is_camel_case(class_name):
                print(f"{self.path}: Line {self.line_number}: S008 Class name '{class_name}' should use CamelCase.")

    def check_function_name(self) -> None:
        """ Checks the function name in snake_case style or not."""
        if self.match_object.group("construction_name") != "def":
            return None
        function_name = self.match_object.group("entity_name")
        if not self.is_snake_case(function_name):
            print(f"{self.path}: Line {self.line_number}: S009 Function name '{function_name}' should use snake_case.")

    def _get_groups(self):
        # Returns one or more subgroups of the match or None.
        return re.match(
            r" *(?P<construction_name>def|class)(?P<space>\s+?)(?P<entity_name>[\w]+)\(?(?P<arguments>[\w\s,:]*)\)?:",
            self.string)

    def check_argument_name(self, node) -> None:
        """Checks argument name in snake_case or not."""
        for item in ast.walk(node.args):
            # print("node.args dump", ast.dump(item, include_attributes=True))
            if isinstance(item, ast.arg):
                if not self.is_snake_case(item.arg):
                    self.warning_queue.append((item.lineno,
                                               f"{self.path}: Line {item.lineno}: S010 Argument name "
                                               f"'{item.arg}' should use snake_case."))
                    break

    def check_local_variable_name(self, node) -> None:
        """Checks variable names in functions in snake_case or not."""
        for list_item in node.body:  # body is a list
            # print("list_item dump", ast.dump(list_item, include_attributes=True))
            if isinstance(list_item, ast.Assign) or isinstance(list_item, ast.AnnAssign):
                for item in list_item.targets:  # targets contains list
                    if isinstance(item, ast.Name):
                        if not self.is_snake_case(item.id):
                            self.warning_queue.append((item.lineno, f"{self.path}: Line {item.lineno}: "
                                                                    f"S011 Variable '{item.id}' in function should be "
                                                                    f"snake_case."))
                            break
                    elif isinstance(item, ast.Tuple):  # For the case of group assignment through tuple
                        for tuple_item in item.elts:
                            if not self.is_snake_case(tuple_item.id):
                                self.warning_queue.append((item.lineno, f"{self.path}: Line {tuple_item.lineno}: "
                                                                        f"S011 Variable '{tuple_item.id}' in functions "
                                                                        f"should be snake_case."))
                                break

    def is_default_argument_mutable(self, node) -> None:
        """Checks the default argument value is mutable of not."""
        # print("dump", ast.dump(node, include_attributes=False))
        arguments_list = deque()
        if node.args.kw_defaults:
            arguments_list.extend(node.args.kw_defaults)
        if node.args.defaults:
            arguments_list.extend(node.args.defaults)
        for defaults in arguments_list:
            for mutable_type in (ast.List, ast.Dict, ast.Set):
                if isinstance(defaults, mutable_type):
                    self.warning_queue.append((defaults.lineno, f"{self.path}: Line {defaults.lineno}: "
                                               f"S012 Default argument value is mutable."))
                    return None

    def visit_FunctionDef(self, node):
        """It's iterates through FunctionDef nodes of AST and runs preparation of S010-S012 warning_queue,
        if there are mistakes.
        """
        self.check_argument_name(node)
        self.check_local_variable_name(node)
        self.is_default_argument_mutable(node)
        self.warning_queue = deque(sorted(self.warning_queue, key=lambda x: x[0]))

    def check_warning_queue(self):
        while len(self.warning_queue) and self.warning_queue[0][0] == self.line_number:
            print(self.warning_queue.popleft()[1])

    def fix_indentation_error(self, error_message):
        """Fixes indentation error in parsed file."""
        self.create_working_source()
        error_location = int(error_message.lineno) - 1
        self.file_list_of_lines[error_location] = self.file_list_of_lines[error_location].lstrip()
        self.file_text = ''.join(self.file_list_of_lines)

    def find_extra_semicolon(self, string):
        """Looks for and return index of extra semicolon in string."""
        semicolon_index = -1
        if '#' in string:
            hash_index = string.find('#')
        else:
            hash_index = len(string)
        semicolon_amount = string.count(';')
        if string.count('#') == 0:
            hash_amount = 1
        else:
            hash_amount = string.count(';')
        for _ in range(semicolon_amount):
            semicolon_index = string.find(';', semicolon_index + 1)
            for _ in range(hash_amount):
                if semicolon_index > hash_index  \
                        or '"' in string[semicolon_index + 1: hash_index] \
                        or "'" in string[semicolon_index + 1: hash_index]:
                    if hash_amount > 1:
                        hash_index = string.find('#', hash_index + 1)
                    continue
                else:
                    return semicolon_index

    def fix_syntax_error(self, error_message):
        """Removes an extra semicolon from string."""
        self.create_working_source()
        error_location = int(error_message.lineno) - 1
        semicolon_index = self.find_extra_semicolon(self.file_list_of_lines[error_location])
        self.file_list_of_lines[error_location] = self.file_list_of_lines[error_location][:semicolon_index]\
                                                  + self.file_list_of_lines[error_location][semicolon_index + 1:]
        self.file_text = ''.join(self.file_list_of_lines)

    def create_working_source(self):
        """Initializes an attribute."""
        self.file_list_of_lines = self.file_text.splitlines(keepends=True)

    def built_ast(self):
        """Builds the AST and fix_indentation_error, if it occurs."""
        with open(self.path) as file:
            self.file_text = file.read()
        while True:
            try:
                tree = ast.parse(self.file_text)
                return tree
            except IndentationError as error_message:
                self.fix_indentation_error(error_message)
            except SyntaxError as error_message:
                self.fix_syntax_error(error_message)

    def run_checks(self) -> None:
        """Refreshes class attributes and runs the all PEP8 checks for every single line."""
        tree = self.built_ast()
        self.generic_visit(tree)  # generic_visit() method runs visit_FunctionDef() function.
        with open(self.path) as file2:
            for line in file2:
                self.string: str = line
                self.match_object = self._get_groups()
                self.hash_index: int = self.refresh_hash_index()
                self.check_line_length()
                self.check_indentation()
                self.check_semicolon()
                self.check_comment_spaces()
                self.check_is_todo()
                self.check_blank_lines()
                if self.match_object is not None:
                    self.check_definition_spaces()
                    self.check_class_name()
                    self.check_function_name()
                self.check_warning_queue()
                self.line_number += 1

    def check_path(self) -> None:
        """The path can lead to a file or to a directory.
        The function checks what is it and choose a proper way work.
        """
        if self.path.endswith(".py"):
            self.run_checks()
        else:
            self.directory_path = self.path
            entries_list = []
            with scandir(self.path) as entries_iterator:
                for entry in entries_iterator:
                    if entry.is_file():
                        entries_list.append(str(entry.name))
            entries_list.sort()
            for file_name in entries_list:
                self.path = f"{self.directory_path}/{file_name}"
                self.line_number = 1
                self.run_checks()

    def run(self) -> None:
        """ If number of CL arguments is correct runs the programme.
        For debugging uncomment the first two strings and comment the another strings of this function.
        """
        # self.path = '/home/roman/PycharmProjects/Static Code Analyzer1/Static Code Analyzer/task/test'
        # self.check_path()
        command_line_arguments = argv
        if len(command_line_arguments) == 2:
            self.path = command_line_arguments[1]
            self.check_path()
        else:
            print("The number of passed arguments is incorrect.")


if __name__ == '__main__':
    code_analyzer_ = CodeAnalyzer()
    code_analyzer_.run()
