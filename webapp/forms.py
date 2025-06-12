from flask_wtf import FlaskForm
from wtforms import (
    DateTimeField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length
from wtforms.widgets import TextArea


class ExampleForm(FlaskForm):
    seat = SelectField("Player 0", validators=[DataRequired()], choices=[])
    headquarters = StringField("HQ Country", validators=[DataRequired()])
    submit = SubmitField("Create")
    # recaptcha = RecaptchaField("Recaptcha")


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
