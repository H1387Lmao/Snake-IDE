from PySide6.QtGui import QTextCharFormat, QColor, QFont, QSyntaxHighlighter
from PySide6.QtCore import Qt
from pygments.lexers import PythonLexer
from pygments.token import Token, STANDARD_TYPES
from pygments import lex

class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.lexer = PythonLexer()
        self.formats = self._initialize_formats()

    def _initialize_formats(self):
        # Fleet Dark Modern theme colors
        colors = {
            # Core syntax
            Token.Comment: "#6D6D6D",
            Token.Keyword: "#83D6C5",
            Token.Name: "#D6D6DD",
            Token.String: "#E394DC",
            Token.Number: "#EBC88D",
            Token.Operator: "#D6D6DD",
            Token.Punctuation: "#D6D6DD",
            
            # Keyword subtypes
            Token.Keyword.Constant: "#82D2CE",     # True, False, None
            Token.Keyword.Declaration: "#83D6C5",   # def, class
            Token.Keyword.Namespace: "#83D6C5",     # import, from
            Token.Keyword.Pseudo: "#83D6C5",        # self, cls
            Token.Keyword.Reserved: "#83D6C5",      # reserved keywords
            Token.Keyword.Type: "#EFB080",          # type annotations
            
            # Name subtypes
            Token.Name.Attribute: "#AAA0FA",        # object.attribute
            Token.Name.Builtin: "#AAA0FA",          # builtin functions
            Token.Name.Builtin.Pseudo: ("#D6D6DD", False, True),   # __magic__ methods
            Token.Name.Class: "#87C3FF",            # class names
            Token.Name.Constant: "#F8C762",         # constants
            Token.Name.Decorator: "#A8CC7C",        # decorators
            Token.Name.Entity: "#EFB080",           # HTML entities
            Token.Name.Exception: "#87C3FF",        # exceptions
            Token.Name.Function: "#AAA0FA",         # function names
            Token.Name.Function.Magic: ("#D6D6DD", True, False),   # __init__ etc.
            Token.Name.Label: "#D6D6DD",            # labels
            Token.Name.Namespace: "#D1D1D1",        # namespaces
            Token.Name.Other: "#D6D6DD",            # other names
            Token.Name.Property: "#AAA0FA",         # properties
            Token.Name.Tag: "#87C3FF",              # HTML tags
            Token.Name.Variable: "#D6D6DD",         # variables
            Token.Name.Variable.Class: "#D6D6DD",   # class variables
            Token.Name.Variable.Global: "#D6D6DD",  # global variables
            Token.Name.Variable.Instance: "#D6D6DD",# instance variables
            Token.Name.Variable.Magic: ("#D6D6DD", True, False),   # __name__ etc.
            
            # String subtypes
            Token.String.Affix: "#E394DC",          # f-string prefixes
            Token.String.Backtick: "#E394DC",        # backtick strings
            Token.String.Char: "#E394DC",            # character literals
            Token.String.Delimiter: "#D6D6DD",       # string delimiters
            Token.String.Doc: "#E394DC",             # docstrings
            Token.String.Double: "#E394DC",          # double-quoted strings
            Token.String.Escape: "#D6D6DD",          # escape sequences
            Token.String.Heredoc: "#E394DC",         # heredocs
            Token.String.Interpol: "#83D6C5",        # f-string expressions
            Token.String.Other: "#E394DC",           # other strings
            Token.String.Regex: "#E394DC",           # regex patterns
            Token.String.Single: "#E394DC",          # single-quoted strings
            Token.String.Symbol: "#E394DC",          # symbols
            
            # Number subtypes
            Token.Number.Bin: "#EBC88D",             # binary literals
            Token.Number.Float: "#EBC88D",           # floats
            Token.Number.Hex: "#EBC88D",             # hex literals
            Token.Number.Integer: "#EBC88D",         # integers
            Token.Number.Integer.Long: "#EBC88D",    # long integers
            Token.Number.Oct: "#EBC88D",             # octal literals
            
            # Operator subtypes
            Token.Operator.Word: "#83D6C5",          # and, or, not
            
            # Comment subtypes
            Token.Comment.Hashbang: "#6D6D6D",       # hashbangs
            Token.Comment.Multiline: "#6D6D6D",      # multiline comments
            Token.Comment.Preproc: "#6D6D6D",        # preprocessor comments
            Token.Comment.Single: "#6D6D6D",         # single-line comments
            Token.Comment.Special: "#6D6D6D",        # special comments
            
            # Generic subtypes
            Token.Generic.Deleted: "#F44747",        # deleted text
            Token.Generic.Emph: "#D6D6DD",           # emphasis
            Token.Generic.Error: "#F44747",          # errors
            Token.Generic.Heading: "#87C3FF",        # headings
            Token.Generic.Inserted: "#A8CC7C",       # inserted text
            Token.Generic.Output: "#D6D6DD",         # output text
            Token.Generic.Prompt: "#6D6D6D",         # prompts
            Token.Generic.Strong: "#D6D6DD",         # strong emphasis
            Token.Generic.Subheading: "#87C3FF",     # subheadings
            Token.Generic.Traceback: "#D6D6DD",      # tracebacks
            
            # Text
            Token.Text: "#CCCCCC",                   # plain text
            Token.Text.Whitespace: "#3C3C3C",        # whitespace
        }
        
        formats = {}
        
        # Create formats for all standard tokens
        for token_type in STANDARD_TYPES:
            # Get color or use default foreground
            fmt = colors.get(token_type, "#CCCCCC")
            if isinstance(fmt, str):
                color = fmt
                italic=False
                bold=False
            else:
                color = fmt[0]
                italic = fmt[1]
                bold = fmt[2]
            
            # Comments should be italic
            if token_type in Token.Comment.subtypes or token_type is Token.Comment:
                italic = True
            
            # Decorators and type hints should be bold
            if token_type in (Token.Name.Decorator, Token.Keyword.Type):
                bold = True
            
            formats[token_type] = self._format(color, bold, italic)
        
        return formats

    def _format(self, color, bold=False, italic=False):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _resolve_format(self, token_type):
        """Resolve token format using Pygments' token hierarchy"""
        while token_type not in self.formats and token_type.parent:
            token_type = token_type.parent
        return self.formats.get(token_type, None)

    def highlightBlock(self, text):
        # Tokenize with position tracking
        tokens = list(lex(text, self.lexer))
        index = 0
        
        for token, value in tokens:
            length = len(value)
            token_format = self._resolve_format(token)
            
            if token_format:
                # Apply format to the exact token position
                self.setFormat(index, length, token_format)
            
            index += length