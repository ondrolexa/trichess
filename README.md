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

Great! You have a fresh virtual environment within your project’s folder. Now you need to install all requirements.

Here’s the command that you need to run to install trichess:

    pip install -r requirements.txt

For developemenmt setup, use:

    pip install -r requirements_dev.txt


## :rocket: How to run

In the moment you can use command line to test engine. To show board coords:

    python run.py
