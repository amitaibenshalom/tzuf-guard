from flask import Flask, jsonify, render_template
from flask_cors import CORS

from .config import config_by_name
from .errors import ApiError, error_response
from .extensions import db, jwt, migrate
from .routes.auth import auth_bp
from .routes.device_status import device_status_bp
from .routes.doors import doors_bp
from .routes.me import me_bp
from .routes.push_devices import push_devices_bp


def create_app(config_name=None):
    app = Flask(__name__, template_folder="../templates")
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

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def api_error(error):
        return error_response(error.message, error.status_code, error.code)

    @app.errorhandler(404)
    def not_found(error):
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
