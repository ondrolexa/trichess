# Trichess

A web application for 3-player chess on hexagonal board. Proof of concept

##  Requirements

- **Python**: 3.14+ (see `.python-version`)
- **Framework**: Flask with Flask-SQLAlchemy, Flask-Login, Flask-JWT-Extended, Flask-RESTX, Flask-Migrate
- **Frontend**: Konva.js (canvas), Bootstrap 5, vanilla JavaScript
- **Database**: SQLite

## :hammer_and_wrench: How to install

Create a virtual environment and install app. Go ahead and open a terminal window. Then navigate to your
trichess project’s root folder. Once you’re in there, run the following commands to create a fresh environment:
```bash
python -m venv .venv
source .venv/bin/activate
```

for Windows use Command Prompt or PowerShell:
```bash
python -m venv .venv
.venv\Scripts\activate
```

> [!NOTE]
> On Microsoft Windows, it may be required to set the execution policy in PowerShell for the user.
> You can do this by issuing the following PowerShell command:
> ```
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Great! You have a fresh virtual environment within your project’s folder. Now you need to install all requirements.

Here’s the command that you need to run to install trichess:
```bash
pip install -r requirements.txt
```

For developemenmt setup, use:
```bash
pip install -r requirements-dev.txt
```

## :rocket: Running the Application

### Development Server
```bash
flask --app=webapp run
```
The application will be available at `http://localhost:5000`.

Purge old logs (default to 90 days)
```bash
flask --app=webapp purge-logs --days 365
```

Analyze gamelogs in Python
```python
from webapp.main import app
from webapp.models import Log
with app.app_context():
    for row in Log.query.filter_by(level="GAME").order_by(Log.created_at).all():
        print(row.created_at, row.message, row.user.username, row.board_id)
```
