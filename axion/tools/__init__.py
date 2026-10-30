"""Registers every tool (importing a module registers its tools in the registry)."""
from axion.tools import registry, files, archive, shell, web, research, misc, project  # noqa: F401
from axion import knowledge as _knowledge, skills as _skills, templates as _templates, verify as _verify  # noqa: F401
