General
=======

- `from typing` import should always be the last import.
- Avoid leaving unused imports

Unit Tests
----------

- Always use unittest.mock for mocking.
- Place all potential reusable fixtures in conftest.py
- When mocking an object, name the variable/function always with a `mock_` prefix
- Maintain the structure of existing unit tests, and keep it consistent when adding new ones.
- Use saigon-py as much as possible for test utilities

Running Tests
-------------

- Run using the python environment under `.venv`. 
- To run the whole suite, you can run `hatch run test`

Style
-----

Use single quotes for strings, but double quotes for inline documentation and format strings (f""").
Make sure your code conforms to the project's linter. You can run it with `hatch run lint`.