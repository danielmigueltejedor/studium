"""Structured, checkable diagrams.

A diagram here is drawn from stored data (geometry, loads, functions) by a
registered generator, never by hand. The same data feeds the checks, and the
checks are stored apart from the drawing. Compiling the drawing proves only
that it compiles; the verification status says what else was checked.

Subject-specific generators (beams, cross-sections, Mohr circles) live in
extension packages such as :mod:`studium.engineering.structures` and register
themselves in :mod:`studium.diagrams.registry`.
"""
