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


class NewGameForm(FlaskForm):
    seat = SelectField(
        "Select seat",
        validators=[DataRequired()],
        choices=["Player 1", "Player 2", "Player 3"],
    )
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
    email = EmailField(validators=[Optional(), Email()])
    themes_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "static/themes"
    )
    theme_files = sorted(
        [
            os.path.splitext(f)[0]
            for f in os.listdir(themes_dir)
            if os.path.splitext(f)[1] == ".yaml"
        ]
    )
    theme = SelectField(
        "Theme",
        validators=[DataRequired()],
        choices=theme_files,
    )
    board = SelectField(
        "Board",
        validators=[DataRequired()],
        choices=["filio", "ondro"],
    )
    submit = SubmitField("Save")


class PasswordForm(FlaskForm):
    username = StringField("Username", render_kw={"disabled": True})
    password = PasswordField(
        "Old",
        validators=[DataRequired(), Length(min=6, max=20)],
    )
    password_new = PasswordField(
        "New",
        validators=[DataRequired(), Length(min=6, max=20)],
    )
    submit = SubmitField("Change password")
