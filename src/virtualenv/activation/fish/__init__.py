from __future__ import absolute_import, unicode_literals

import re

from virtualenv.util.path import Path

from ..via_template import ViaTemplateActivator


class FishActivator(ViaTemplateActivator):
    def templates(self):
        yield Path("activate.fish")

    @staticmethod
    def quote(string):
        """
        Quote a string for fish.

        fish reads backslash-backslash and backslash-quote as escapes inside single quotes, unlike POSIX sh, so
        shlex.quote's output lets a backslash before a quote end the literal early. Escape both characters, each in a
        quoted segment of its own (``'a\\b'`` becomes ``'a''\\\\''b'``): the escape always follows an ASCII quote, so
        a legacy decoder cannot absorb it into a preceding multibyte character, and it stays inside quotes, which
        fish 3.0 needs (it misreads an escaped backslash placed between two quoted segments).
        """
        return "'" + re.sub(r"[\\']", lambda match: "''\\{}''".format(match.group()), string) + "'"
