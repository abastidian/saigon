# Saigon Backend Development Guide

Welcome to Saigon development! This document is a keep-it-simple guide for the development of
the backend components for the Saigon platform. It covers how to write and structure the code
in terms of style, patterns, and internal documentation. 

## Dev Process

This section provides a brief summary with the key items of the development process. Please refer
to Saigon's development process for the complete content if you're new to product development.

### Code Changes

All code changes must refer to an existing ticket (Jira story/task) in the corresponding project.
Code changes are always made in a dedicated *feature branch* off the `dev` branch. The naming
scheme of the feature branch is as a follows:

<div style="text-align: center;">feature/{ISSUE-ID}-{DESC}]</div>

where:

 - `{ISSUE-ID}`: Mandatory. Corresponds to the related ticket ID (e.g. MYPROJECT-1).
 - `-{DESC}`: Optional. Provides a short description of the work, with dash separated words
                 (e.g. `-add-logging`)

Examples of valid branch names:

- `feature/MYPROJECT-1`
- `feature/MYPROJECT-1-add-logging`

You can then work on your feature branch committing changes as you see fit. You should create a 
pull request (PR) as soon as your code is ready for review. The ready-for-review definition requires
that:

 - The code is already clean and considered as finished.
 - It incorporates the required applicable tests.

In the situation you want to have an early feedback on the changes you're making, you can still 
create a PR but in *draft* mode, so reviewers can know your intent.

To create a PR, make sure that the title follows the format:

<div style="text-align: center;">{ISSUE-ID}: {DESC}</div>

where:
    - `{ISSUE-ID}`: Corresponds to the related ticket ID, as in the branch name (e.g. MYPROJECT-1).
    - `{DESC}`: Description sentence of the work contained in the PR

Example:

```
MYPROJECT-1: Create initial implementation of endpoints
```

### Merging

To merge  your PR you will need at least one approval from the reviewers alongside a successful
run of the validation piepline.  Changes in feature branches undergo a series of validation tasks 
which in essence consists of code static analysis and tests. This task piepline is part of the 
general CI/CD, and it needs to be successful in order for changes to be merged.

The repository and PR settings are configured to merge PRs by squashing commits, so that the history
in the target branch will be clean and with a one-to-one commit correspondence with feature branches.
Make sure that the target branch to merge PR is always `dev`.

Production code is deployed from `main`, to which merges from dev are done periodically and/or on
demand, depending on the CI/CD structure and project needs. In general, you will not be manually
merging into `main` as there will be a designated release manager in charge of doing so, however
there will be cases where you may need to do so (such as for an urgent hot fix).

### Work Management

As mentioned before, all code changes must have an associated ticket. These tickets are created
either from the Product Manager (PM) or by developers. PMs will create tickets as *stories* with
high level description of the required functionality. You will be assigned to implement one or more
stories.

Before jumping into code, it's recommended that you write up some content with the architecture
and design of the functionality. You will add this content as a new page under the corresponding
content umbrella (e.g., a sub-page within the project in Confluence). It's up to you to determine
the detail of the documentation. The key is to add content that will help others to understand
what's going on.

To keep PRs small, decompose the story in smaller subtasks as you see fit. For example, you may
define a set of subtask to address endpoint definition, handlers implementation, logging, error
handling and tests. There's no pre-defined script for this, you can choose your own strategy as long
as PRs are small and easy to review.

The cases where you file tickets yourself will be related to internal improvements (
such as refactorings and test enhancements), and bug fixes. For internal improvements, you should
be creating a single task that will take care of the necessary changes. For bug fixes, you must
create a bug ticket providing all the context of the problem, indicating the environment, conditions,
and resulting behavior.

## Style Format

### PEP8 Conformant

Microservices are written in Python 3.12 with the code conformant to [PEP8](https://peps.python.org/pep-0008/).
CI/CD setup validates conformance to the required formatting so your code will not make it through
if it's not properly formatted. 

The most recommended way to develop code with the required formatting is to use an IDE configured
to provide real time linting. In addition, we provide configuration file for 
[Flake8,](https://flake8.pycqa.org/en/latest/) so you can run the linter to find and fix the
errors.

### Line max width

Lines of code are limited to a maximum width (see .flake8 configuration).

### Package Import Order

Importing of packages should appear from more to less generic order. This is as simple as
importing with the following order:

- Python packages
- Third-party packages
- Local packages

Same package import are grouped together with no blank lines between them. A blank line separates
import groups. Example:

```python
import logging
from typing import Dict, Type

import boto3
from boto3 import client

from .hms import main
```

### Multiline format**

When a statement needs to be split into multiple lines there are two possible formats:

a. Break the statement with an opening `(` followed by placing **all** elements into a new line
   indented one level. Terminate the statement with a closing `)` in a new line. Examples:

```
# Imports
from pydantic import (
    BaseModel, FiniteFloat, conlist
)

# Function calls
my_function(
    param1: str, param2: str, param3: str
) -> str
```

b. Break the statement with an opening `(` followed by placing each split element into a new line 
   indented one level. Terminate the statement with a closing `)` in a new line. Examples:

```
from pydantic import (
    BaseModel, 
    FiniteFloat,
    conlist
)

# Function calls
my_function(
    param1, 
    param2,
    param3
)
```

Rule `a)` is valid as long as it respects the maximum length width defined for 
[line max width](#line-max-width). 

Note that statements for which the parenthesis are added artificially need to have a white space
for the opening `(`. This is not applicable to statements that the language require it anyway
such as functions or classes, where the [PEP8](#pep8-conformant) rule prevails in terms of spacing.

### Type Hints

The code must be annotated wherever necessary in order to have strong typing hints. This means that,
at the very least, function parameters and return values need type annotations. 

In some situations, variable declaration may need type annotation if the calling function does
not provide explicit hints. This occurs typically when using a third-party package.

### String Literals

String literals are defined using single quote (`'`). Double quotes (`"`) must be used for the
string format expression with `f`.

```python
# regular literal
my_var = 'string literal'
my_format_exp = f"format expression with sub={value}"
```

## Logging

All services and components shall implement structured and context-aware logging. They shall
use the standard package `logging.logger` to emit messages, but configured with our custom
`logutils (currently obtained as copy-paste).

The usage is fairly straightforward:
- First, enable the logging capabilities to enable JSON and context in the application entry point 
  by calling `logutils.enable_log_context()`. 
- Whenever is desired, define a context scope with `logutils.logcontext()`, and add entries to 
  the context with `logutils.set_log_context()`

Example:

```python
import logging

from saigon.logutils import enable_log_context, logcontext, set_log_context

logger = logging.getLogger(__name__)
enable_log_context('app')

@logcontext()
def my_function(param: str):
    set_log_context(param_key1=param, other_key='value')
    logger.info('a log message')

```

The above code enables JSON formatting for all messages, appending additional metadata 
attributes and all the context keys to the logged message :

```
app: {"name": "hms.timestream", "message": "a log message", 
      "param_key1": "<param_value>", "other_key": "value", 
      "level": "INFO", "time": "2024-08-27 13:00:11,383", "func": "my_function"}
```

Note that the keys set with `set_log_context` will appear always for every subsequent log message.

### Message Format

As just shown above log messages are formatted as JSON, with the object containing standard
attributes (`name`, `time`, `level`, ...) and custom context keys (`controller_id`, `operation_id`).
The log message is set in the `message` attribute. This corresponds with the string provided in
the log function (e.g., `logger.error('my message')`). To keep the JSON object structure as much
as possible, messages should contain a line of basic text, with any associated parameter provided
with the `extra` keyword in the log operation.

For example, to log that a given user input value was provided by the user:

```
logger.info('User provided input name`, extra={'input_value': value})
```

This format will help with format consistency and enable easier log matching when performing and 
a search in a log stream using filter expressions. Hence, avoid constructing a formatted message 
with `f""` or substitution characters ('%s') since that will make it harder to build such filters.

### When and what to log

There is no universal one-size-fits-all rule for adding log messages. In our case we're after
content-rich and consistent logs accross our services and products. The following guidlines help
achieve such goal:

- Use `logutils` infrastructure to enable and configure logging
- Add an `Info` log at the beginning of each high level activity
- Set the log context with key attributes that help track related entities for an operation
  (e.g. user id in a login operation, transaction id for a payment, etc)
- Do not log exceptions unless you're catching the exception for other justified reason (see
  [error handling](#error-reporting-and-handling)).
- Do not log when throwing an exception/error. Instead. build the exception with an informative 
  message and let the handler log the exception if needed.

## Error reporting and handling

As it is part of the Python essence, errors are reported through exceptions. However, your code
should throw exceptions related to bad or unexpected inputs, and do so as soon as you have the
right context to check for it.

The most basic example would consist of checking for the expected value of an input parameter. In
this case, you want to throw the exception in the first function that can know if the input is
wrong and avoid letting the input travel down the call stack.

Alternatively, do not throw exception for code logic errors where a certain situation should not
occur. For example, if your class' member should be initialized, you should not throw an error
if it's not; instead, let the underlying Python runtime throw the corresponding error.

### When to catch exceptions

There are two main situations–and potentially others more unique to each situation–where catching
an exception may be necessary:

1.To convert an otherwise invalid return value or error code into an exception. This typically
  occurs when using third-party packages. 

For example:

```python
result = client.request()
if result == 'unavailable':
    raise Exception(f"client request failed with status={result}")
```

2.To proxy the exception to either provide a user-descriptive error, or to convert to return value.
  This typically occurs when calling third-party clients in order to hide implementation details 
  (e.g., using a http client) or when a given framework requires returnin a value (e.g. returning
  a http response). 

For example:

 ```python
# Exception translation 
try:
    result = client.request()
except ClientError as ce:
    logger.error(ce)
    raise Exception(f"Failed to retrieve user profile")
   
# Conversion to return value
try:
    client.request()
except ClientError as ce:
    logger.error(ce)
    return HTTPResponse(status_code=500, detail='error processing the request')
```

## Microservices

This section covers some of the patterns and structure of code related to microservices components
and business logic.

### Fast API

Messaging between microservices is through standard HTTP endpoints, with 
[FastAPI](https://fastapi.tiangolo.com/) as client implementation. The basic structure to follow
when using FastAPI is as follows:

- Place all endpoints definitions in a top-level file called `main.py`
- This file creates and sets up the `FastAPI` app, along with the logging infrastructure.
- Endpoint implementation shall contain two sections:
  - Input check (when appicable)
  - Set [logging context](#logging) appropriate. Always include an `operation_id` key with the
    name of the function.
  - Invoke the corresponding implementation of the `RequestHandler` for that operation.

Example:

```python
#import section
...

# logging setup
enable_log_context('my_service')
logger = logging.getLogger(__name__)

# app creation
app = FastAPI()
app.add_middleware(LogMiddleware, logger=logger)

@app.post('/v1/filters/{entity_id}')
async def push_data(
    entity_id: UUID,
    request_body: Annotated[dict, Body]
):
    set_log_context(
        operation_id=f"push_data", controller_id=str(entity_id)
    )
    return MyHandler().handle_request(
        request_body,
        entity_id=entity_id
    )
```

## Object Validation

For object validation we use [Pydantic](https://docs.pydantic.dev/latest/). Define your entities
in a file named `model.py` and use these whenever interacting with frameworks that require data
serialization (`FastAPI`, `boto3`, `sqlalchemy`, etc.).













