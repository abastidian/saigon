# Saigon

This repository contains common functionality to build cloud backends that is often necessary (
and repeated) in all projects.

Development for this repository follows the same process as the backend services. Please take a look
at the [development guide](./docs/dev_guide.md).

# Setup and build `saigon`

Code in this repo is a single Python package located in `src`. For both developing and creating
the installable package you will need first to create a virtual environment. You can do so under the 
parent directory:

```bash
$ python -m venv .venv
$ source .venv/bin/activate
```

Then proceed to install the development dependencies along with the package's:

```bash
(.venv) $ pip install ".[build]"
(.venv) $ hatch build
```

Note that the second command will also create the installable `saigon` package under `dist`.
You can re-run the second command as needed in order to regenerate the package bundle.