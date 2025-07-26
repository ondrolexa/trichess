import os

from flask_wtf import FlaskForm
from wtforms import (
    EmailField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
)
from wtforms.validators import DataRequired, Email, Length, Optional
from wtforms.widgets import TextArea


class NewGameForm(FlaskForm):
    seat = SelectField(
        "Select seat",
        validators=[DataRequired()],
        choices=["Player 1", "Player 2", "Player 3"],
    )
    slog = StringField("Game log", widget=TextArea())
    submit = SubmitField("Create")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username", validators=[DataRequired(), Length(min=4, max=20)]
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=6, max=20)]
    )
    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Login")


class ProfileForm(FlaskForm):
    password = PasswordField(
        "Password",
        validators=[Optional(), Length(min=6, max=20)],
        render_kw={"placeholder": "Leave blank for current"},
    )
    email = EmailField(validators=[Optional(), Email()])
    themes_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "static/themes"
    )
    theme_files = [
        os.path.splitext(f)[0]
        for f in os.listdir(themes_dir)
        if os.path.splitext(f)[1] == ".yaml"
    ]
    theme = SelectField(
        "Select theme",
        validators=[DataRequired()],
        choices=theme_files,
    )
    submit = SubmitField("Save")
