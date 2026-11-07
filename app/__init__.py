from flask import Flask, jsonify, redirect, render_template, request
from flask_cors import CORS

from .config import config_by_name
from .errors import ApiError, error_response
from .extensions import db, jwt, migrate
from .routes.auth import auth_bp
from .routes.device_status import device_status_bp
from .routes.doors import doors_bp
from .routes.me import me_bp
from .routes.push_devices import push_devices_bp
from .routes.public_demo import public_demo_bp
from .routes.realtime import realtime_bp


def create_app(config_name=None):
    # Vercel serves public/ directly from its CDN. Point Flask at the same
    # directory so local development and tests use identical asset URLs.
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../public",
        static_url_path="",
    )
    config = config_by_name(config_name)
    app.config.from_object(config)
    config.configure_app(app)
    config.validate(app)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)

    register_routes(app)
    register_error_handlers(app)
    register_jwt_handlers(jwt)
    register_cors(app)

    return app


def register_routes(app):
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(me_bp, url_prefix="/api")
    app.register_blueprint(doors_bp, url_prefix="/api/doors")
    app.register_blueprint(device_status_bp, url_prefix="/api")
    app.register_blueprint(push_devices_bp, url_prefix="/api/push-devices")
    app.register_blueprint(public_demo_bp, url_prefix="/api/public")
    app.register_blueprint(realtime_bp, url_prefix="/api/realtime")

    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/login")
    def login_page():
        return render_template(
            "auth.html",
            auth_mode="login",
            google_client_id=app.config["GOOGLE_WEB_CLIENT_ID"],
        )

    @app.get("/register")
    def register_page():
        return render_template(
            "auth.html",
            auth_mode="register",
            google_client_id=app.config["GOOGLE_WEB_CLIENT_ID"],
        )

    @app.get("/reset-password")
    def reset_password_page():
        return render_template("reset_password.html")

    @app.get("/app")
    @app.get("/dashboard")
    @app.get("/doors")
    def app_redirect():
        return redirect("/app/doors")

    @app.get("/app/doors")
    def doors_page():
        return render_template("dashboard.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        return response


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def api_error(error):
        return error_response(error.message, error.status_code, error.code)

    @app.errorhandler(404)
    def not_found(error):
        if not request.path.startswith("/api/"):
            return render_template("404.html"), 404
        return error_response("Not found.", 404, "not_found")

    @app.errorhandler(405)
    def method_not_allowed(error):
        return error_response("Method not allowed.", 405, "method_not_allowed")

    @app.errorhandler(500)
    def internal_server_error(error):
        app.logger.exception("Unhandled server error: %s", error)
        return error_response("Internal server error.", 500, "internal_server_error")


def register_jwt_handlers(jwt_manager):
    @jwt_manager.unauthorized_loader
    def missing_token(message):
        return error_response("Authentication is required.", 401, "unauthorized")

    @jwt_manager.invalid_token_loader
    def invalid_token(message):
        return error_response("Invalid authentication token.", 401, "invalid_token")

    @jwt_manager.expired_token_loader
    def expired_token(header, payload):
        return error_response("Authentication token expired.", 401, "token_expired")


def register_cors(app):
    if app.config["CORS_ENABLED"]:
        CORS(
            app,
            resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
            allow_headers=["Content-Type", "Authorization"],
            methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        )
