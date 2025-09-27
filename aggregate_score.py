from webapp import app
from webapp.models import User

with app.app_context():
    r = User.query.order_by(User.id.asc()).all()
    for u in r:
        print(u.username, u.score())
