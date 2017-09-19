# cherrymusic-rewrite

Experimental project to rewrite the [CherryMusic streaming server][]
in modern, clean code, to make it more maintainable and extensible.

While the goal is also to introduce a new, RESTful API, at least
initially a legacy API will also be included to remain backward-compatible
with the existing web client.

[CherryMusic streaming server]: https://github.com/devsnd/cherrymusic

## Goals

### Continuity of original main goals

The project's main goals remain unchanged from the original:

* Easy-to-use personal server for own music collection;
* minimal dependencies for easy deployment;
* fast search;
* friend accounts;
* separate data: no changes or writes to the audio file collection.

### Additional goals

* Write modern, clean code.
* Provide good documentation for contributers.
* Close-to-full test coverage.
* Feature parity with original, and beyond.


## Dependencies

To be able to take advantage of modern libraries and language features,
this new project will be based on current, state-of-the-art
dependencies. There will be no support for older versions
that work with the original project, for the very reason that the
original will remain available, at least as long it is the more mature,
complete and stable choice.

* Python 3.6+
* sqlite 3.19+
* ... more to come.

For development dependencies, see `requirements-dev.txt`.


## Features

The project is still in a very early exploratory stage.
There are no features to speak of so far.

(c) 2017 Tilman Börner
