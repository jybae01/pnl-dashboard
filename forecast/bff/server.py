from .http_factory import create_http_bff_from_environment


def create_app():
    return create_http_bff_from_environment()
