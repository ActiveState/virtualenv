from __future__ import absolute_import, unicode_literals

from virtualenv.util.path import Path

from ..via_template import ViaTemplateActivator


class PowerShellActivator(ViaTemplateActivator):
    def templates(self):
        yield Path("activate.ps1")

    @staticmethod
    def quote(string):
        """
        This should satisfy PowerShell quoting rules [1], unless the quoted
        string is passed directly to Windows native commands [2].
        [1]: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_quoting_rules
        [2]: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_parsing#passing-arguments-that-contain-quote-characters
        """  # noqa: D205
        # PowerShell treats the ASCII apostrophe and the curly single quotes U+2018-U+201B as interchangeable
        # single-quote delimiters, so each must be doubled to stay inert inside the literal.
        for delimiter in ("'", "\u2018", "\u2019", "\u201a", "\u201b"):
            string = string.replace(delimiter, delimiter * 2)
        return "'{0}'".format(string)
