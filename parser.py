from queuen.lexer import Token, TokenStream
from queuen.lexer import KEYWORD as Keywords

# The token classes are  newline   ,  natural ,  string    ,
#                        delimiter ,  special ,  separator ,  operator
#                        keyword   ,  name

class ParseTree:
    def __init__(self, kind, children):
        self.kind = kind            # instance of str
        self.children = children    # list of ParseTrees or literal values

    def __repr__(self):
        tk = "\x1B[38;5;128mParseTree\x1B[39m"
        return f"⟨{tk} {self.kind} = {self.children}⟩"

class ParseError:
    def __init__(self, msg, ctx):
        self.message = msg          # instance of str
        self.context = ctx          # instance of ParseTree or Token,
                                    #   or a list of ParseTrees and Tokens

    def __repr__(self):
        return "\x1B[91merror\x1B[39m: " + self.message + "\n" + str(self.context)
        # TODO this needs to be significantly improved


################################################################################


def index_token(ln, val, cls):
    idx = 0
    while idx < len(ln):
        obj = ln[idx]
        if isinstance(obj, Token):
            setlike_cls = (isinstance(cls, set) or isinstance(cls, list))
            if obj.cls == cls or (setlike_cls and obj.cls in cls):
                setlike_val = (isinstance(val, set) or isinstance(val, list))
                if obj.val == val or (setlike_val and obj.val in val):
                    return idx
        idx += 1
    return None


def rindex_token(ln, val, cls):
    idx = len(ln)-1
    while idx >= 0:
        obj = ln[idx]
        if isinstance(obj, Token):
            setlike_cls = (isinstance(cls, set) or isinstance(cls, list))
            if obj.cls == cls or (setlike_cls and obj.cls in cls):
                setlike_val = (isinstance(val, set) or isinstance(val, list))
                if obj.val == val or (setlike_val and obj.val in val):
                    return idx
        idx -= 1
    return None


def split_token(ln, val, cls = 'separator'):
    gather, run = [], []
    idx = 0
    while idx < len(ln):
        obj = ln[idx]
        if isinstance(obj, Token) and obj.cls == cls and obj.val == val:
            gather.append(run)
            run = []
        else:
            run.append(obj)
        idx += 1
    gather.append(run)
    return gather


################################################################################


# Arranged from high to low precedence.
#   Each element looks like [op, 'left'|'right', kind]     for binary ops
#                       and [op, 'prefix'|'postfix', kind] for unary ops
#
Operators = [[':', 'left',   'concat' ],
             ['$', 'prefix', 'factory'],
             ['~', 'left',   'zip'    ],
             ['_', 'prefix', 'flatten']]

# Returns None, an instance of ParseTree, or an instance of ParseError.
#
def _parse(line):

    if len(line) == 0:
        return None

    while (lp := index_token(line, "(", 'delimiter')) is not None:
        rp = index_token(line, ")", 'delimiter')
        if (rp is not None) and rp < lp:
            return ParseError("missing left parenthesis", line)
        height = 1
        rp = lp + 1
        while True:
            if rp >= len(line):
                return ParseError("missing right parenthesis", line)
            obj = line[rp]
            if isinstance(obj, Token) and obj.cls == 'delimiter':
                if obj.val == '(': height += 1
                if obj.val == ')': height -= 1
            if height == 0: break
            rp += 1

        interior = _parse(line[lp+1:rp])
        if interior is None:
            return ParseError("nothing to parse inside parentheses", None)
        if isinstance(interior, ParseError):
            return interior

        line = line[:lp] + [interior] + line[rp+1:]

    # And now, at this point, we're guaranteed that aren't any parentheses.
    # First, construct queue literals.

    while (lb := index_token(line, "[", 'delimiter')) is not None:
        rb = index_token(line, "]", 'delimiter')
        if (rb is not None) and rb < lb:
            return ParseError("missing left bracket", line)
        height = 1
        rb = lb + 1
        while True:
            if rb >= len(line):
                return ParseError("missing right bracket", line)
            obj = line[rb]
            if isinstance(obj, Token) and obj.cls == 'delimiter':
                if obj.val == '[': height += 1
                if obj.val == ']': height -= 1
            if height == 0: break
            rb += 1

        elems = split_token(line[lb+1:rb], ",")
        interior = []
        for elem in elems:
            parsed_elem = _parse(elem)
            if isinstance(parsed_elem, ParseError):
                return parsed_elem
            interior.append(parsed_elem)

        if len(interior) < 1:
            raise Exception("this should never happen")

        elif len(interior) == 1:
            if interior[0] is None:
                interior = []

        elif len(interior) > 1:
            if None in interior:
                return ParseError("missing element", line)

        literal = ParseTree('literal', interior)
        line = line[:lb] + [literal] + line[rb+1:]

    # At this point, we're guaranteed that aren't any parentheses or brackets.
    # Second, complain about any braces, since they don't do anything yet.

    if (index_token(line, "{", 'delimiter') is not None) \
            or (index_token(line, "}", 'delimiter') is not None):
        return ParseError("illegal delimiter", line)

    # Third, parse operators and application (concatenation).
    for op, assoc, kind in Operators:
        if assoc in ['left', 'right']:
            while True:
                if assoc == 'left':
                    idx = index_token(line, op, 'operator')
                if assoc == 'right':
                    idx = rindex_token(line, op, 'operator')
                if idx is None:
                    break
                if idx == 0:
                    return ParseError("binary operator missing left argument", line)
                if idx == len(line)-1:
                    return ParseError("binary operator missing right argument", line)
                lhs = line[idx-1]
                rhs = line[idx+1]
                if isinstance(lhs, Token) and lhs.cls not in ['natural', 'string', 'name']:
                    return ParseError("invalid left argument", line)
                if isinstance(rhs, Token) and rhs.cls not in ['natural', 'string', 'name']:
                    return ParseError("invalid right argument", line)
                tree = ParseTree(kind, [lhs, rhs])
                line = line[:idx-1] + [tree] + line[idx+2:]

        if assoc in ['prefix', 'postfix']:
            while True:
                if assoc == 'postfix':
                    idx = index_token(line, op, 'operator')
                if assoc == 'prefix':
                    idx = rindex_token(line, op, 'operator')
                if idx is None:
                    break
                if idx == 0 and assoc == 'postfix':
                    return ParseError("postfix operator missing argument", line)
                if idx == len(line)-1 and assoc == 'prefix':
                    return ParseError("prefix operator missing argument", line)
                if assoc == 'postfix':
                    arg = line[idx-1]
                if assoc == 'prefix':
                    arg = line[idx+1]
                if isinstance(arg, Token) and arg.cls not in ['natural', 'string', 'name']:
                    return ParseError(f"invalid {assoc} argument", line)
                tree = ParseTree(kind, [arg])
                if assoc == 'postfix':
                    line = line[:idx-1] + [tree] + line[idx+1:]
                if assoc == 'prefix':
                    line = line[:idx] + [tree] + line[idx+2:]

    # Fourth, keyword functions.
    while True:
        idx = rindex_token(line, Keywords, 'keyword')
        if idx is None:
            break
        if idx == len(line)-1:
            return ParseError("keyword missing argument", line)
        rhs = line[idx+1]
        if isinstance(rhs, Token) and rhs.cls not in ['natural', 'string', 'name']:
            return ParseError("invalid keyword argument", line)
        tree = ParseTree(line[idx], [rhs])
        line = line[:idx] + [tree] + line[idx+2:]

    # And we're all done!
    if len(line) < 1:
        raise Exception("this should never happen")
    if len(line) > 1:
        return ParseError("undreducable expression", line)

    return line[0]


def parse_line(stream):
    # read until we encounter a newline
    line = []
    while True:
        tok = next(stream)
        if (tok is None) or (tok.cls == 'newline'):
            break
        line.append(tok)

    return _parse(line)


################################################################################


if __name__ == "__main__":

    from sys import exit

    def prompt():
        print("\x1B[2mqueuen>\x1B[22m ", end='')
        line = input()
        if line in ['exit', 'quit']:
            exit()
        return line + "\n"

    stream = TokenStream("", prompt)

    try:
        while True:
            ln = parse_line(stream)
            print(ln)

    except KeyboardInterrupt:
        print("\b\bexit")

    except EOFError:
        print('exit')

