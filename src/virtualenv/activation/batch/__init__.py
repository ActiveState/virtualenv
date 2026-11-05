from __future__ import absolute_import, unicode_literals

import logging
import os

from virtualenv.util.path import Path
from virtualenv.util.text import collapse_line_boundaries

from ..via_template import ViaTemplateActivator

# cmd.exe's own command-line parser looks for these regardless of surrounding quotes: `@set "VAR=x & cmd"` still
# runs `cmd` as a second statement even though the whole VAR=value expression is quoted. `(` and `)` are not in this
# set, since parentheses are only special to cmd.exe as block delimiters in control-flow syntax (if/for), not as bare
# characters in a quoted value. `!` is only live when the caller already has delayed expansion enabled, but then a
# prompt like `foo!SECRET!` substitutes an existing variable, so it is neutered unconditionally.
_CMD_OPERATORS = ("&", "|", "<", ">", "^", "!", '"')

# Of _CMD_OPERATORS, only `&` can actually occur in a real Windows path: `|`, `<`, `>` and `"` are illegal in Windows
# filenames, and a literal `^` is silently dropped by cmd.exe itself. quote() can neuter `&` in free text like the
# prompt, but doing that to a path would silently point activate.bat at a directory that does not exist, so refuse.
_PATH_UNSAFE_CHARS = ("&",)

_PATH_REPLACEMENT_NAMES = {
    "__VIRTUAL_ENV__": "the destination directory",
}


class BatchActivator(ViaTemplateActivator):
    @classmethod
    def supports(cls, interpreter):
        return interpreter.os == "nt"

    def templates(self):
        yield Path("activate.bat")
        yield Path("deactivate.bat")
        yield Path("pydoc.bat")

    def generate(self, creator):
        values = self.replacements(creator, creator.bin_dir)
        problems = [_unsafe_path_reason(key, values[key]) for key in sorted(_PATH_REPLACEMENT_NAMES)]
        problems = [problem for problem in problems if problem]
        if problems:
            for problem in problems:
                logging.warning("skipping batch activation scripts: %s", problem)
            return []
        return super(BatchActivator, self).generate(creator)

    @staticmethod
    def quote(string):
        """
        Make a value safe to sit inside ``set "VAR=value"``.

        Batch has no escape for a double quote in this context: it always closes the quoted string, and whatever
        follows on the line runs as live cmd.exe syntax. A raw line boundary is worse - batch is line-oriented
        regardless of quote state, so it starts a brand-new statement. None of these can be represented literally
        here, so replace them with a space. ``%`` still triggers variable expansion inside the quotes, but doubling it
        to ``%%`` is a real, in-file escape that keeps the literal character.
        """
        string = string.replace("%", "%%")
        for operator in _CMD_OPERATORS:
            string = string.replace(operator, " ")
        return collapse_line_boundaries(string)

    def instantiate_template(self, replacements, template, creator):
        # ensure the text has all newlines as \r\n - required by batch
        base = super(BatchActivator, self).instantiate_template(replacements, template, creator)
        return base.replace(os.linesep, "\n").replace("\n", os.linesep)


def _unsafe_path_reason(key, value):
    found = sorted({char for char in value if char in _PATH_UNSAFE_CHARS})
    if not found:
        return None
    return (
        "{} ({!r}) contains {!r}, and cmd.exe has no way to keep that literal inside the "
        'set "VAR=value" lines activate.bat relies on'.format(_PATH_REPLACEMENT_NAMES[key], value, "".join(found))
    )
