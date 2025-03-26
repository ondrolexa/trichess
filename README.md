# TriChess

Chess game for three players on hexagonal board. Proof of concept

##  Requirements

In the moment, the trichess requires [Matplotlib](https://matplotlib.org/).

## :hammer_and_wrench: How to install

Create a virtual environment and install app. Go ahead and open a terminal window. Then navigate to your
trichess project’s root folder. Once you’re in there, run the following commands to create a fresh environment:

    python -m venv .venv
    source .venv/bin/activate

for Windows use Command Prompt or PowerShell:

    python -m venv .venv
    .venv\Scripts\activate

> [!NOTE]
> On Microsoft Windows, it may be required to set the execution policy in PowerShell for the user.
> You can do this by issuing the following PowerShell command:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Great! You have a fresh virtual environment within your project’s folder. To install the application in there,
you’ll use the -e option of pip install. This option allows you to install packages, libraries, and tools in editable mode.

Editable mode lets you work on the source code while being able to try the latest modifications as you implement them.
This mode is quite useful in the development stage.

Here’s the command that you need to run to install trichess:

    pip install -e .[dev]

## :rocket: How to run

In the moment you can use command line to test engine. To show board coords:

    trichess coords

To show possible moves of piece on coords `(q, r)`

    trichess moves -- -4 -2

## License

Trichess is free software: you can redistribute it and/or modify it under the terms of the MIT License. A copy of this license is provided in ``LICENSE`` file.
