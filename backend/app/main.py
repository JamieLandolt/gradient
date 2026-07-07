"""FastAPI application factory.

`create_app(settings)` is used by tests with explicit settings; the module-level
`app` loads settings from the environment and fails fast if any are missing.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import Settings, get_settings
from app.core.errors import register_exception_handlers


def create_app(settings: Settings) -> FastAPI:
    application = FastAPI(title="Gradient API", version="0.1.0")
    application.state.settings = settings

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(application)
    application.include_router(api_router)
    return application


app = create_app(get_settings())
