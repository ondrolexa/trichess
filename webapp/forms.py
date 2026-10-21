import os

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileSize
from wtforms import (
    EmailField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, Length, Optional, Regexp


class NewGameForm(FlaskForm):
    seat = SelectField(
        "Select seat",
        validators=[DataRequired()],
        choices=["Seat 1", "Seat 2", "Seat 3"],
    )
    submit = SubmitField("Create")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=4, max=20),
            Regexp(
                r"^[A-Za-z0-9_-]+$",
                message="Username may only contain letters, numbers, underscores and hyphens.",
            ),
        ],
    )
    password = PasswordField(
        "Password", validators=[DataRequired(), Length(min=6, max=128)]
    )
    email = EmailField(validators=[DataRequired(), Email()])
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
        "Colors",
        validators=[DataRequired()],
        choices=theme_files,
    )
    pieces_dir = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "static/pieces"
    )
    pieces_files = sorted(
        [
            os.path.splitext(f)[0]
            for f in os.listdir(pieces_dir)
            if os.path.splitext(f)[1] == ".yaml"
        ]
    )
    pieces = SelectField(
        "Pieces",
        validators=[DataRequired()],
        choices=pieces_files,
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
        validators=[DataRequired(), Length(min=6, max=128)],
    )
    password_new = PasswordField(
        "New",
        validators=[DataRequired(), Length(min=6, max=128)],
    )
    submit = SubmitField("Change password")


class ForgotPasswordForm(FlaskForm):
    email = EmailField(validators=[DataRequired(), Email()])
    submit = SubmitField("Send reset link")


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=6, max=128)],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password")],
    )
    submit = SubmitField("Reset password")


CONTACT_EXTENSIONS = ["png", "jpg", "jpeg", "gif", "webp", "pdf", "txt", "log"]


class ContactForm(FlaskForm):
    subject = StringField(
        "Subject", validators=[DataRequired(), Length(min=3, max=150)]
    )
    message = TextAreaField(
        "Message",
        validators=[DataRequired(), Length(max=5000)],
        render_kw={"rows": 8},
    )
    attachment = FileField(
        "Attachment",
        validators=[
            FileAllowed(CONTACT_EXTENSIONS, "Images, PDF or text files only."),
            FileSize(max_size=1024 * 1024, message="Attachment too large (max 1 MB)."),
        ],
        description="Optional: an image, PDF or text file, max 1 MB.",
        render_kw={"accept": ",".join("." + e for e in CONTACT_EXTENSIONS)},
    )
    submit = SubmitField("Send")
