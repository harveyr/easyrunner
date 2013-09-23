easyrunner
==========

This will eventually be a helper script to easily run targeted tests (unit, integration, ui, what have you).

It's intended to be helpful when whatever test runner you're using doesn't offer sufficient test-filtering options, and/or when you need to run time-consuming test suites and would like to have progressive test tallies printed to the terminal as the suite runs.

Currently, it has grown too big for its britches and needs to be paired down to a simpler state. I tried to turn it into a single-page terminal app with dynamic feedback using Python's curses module. Working out the resulting glitches, which varied depending on Python version, ended up being a time suck. Since this was originally written as a personal efficiency *booster*, I decided the continual costs weren't worth the benefits.

I'll probably whip this back into shape next time I have a new project that could use it.
