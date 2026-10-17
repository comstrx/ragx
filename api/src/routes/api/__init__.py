from core.http import Group, Route
from app.controllers import auth, files, health, hello
from app.middlewares import authenticate

heartbeat = Route.get("/health", health.index, name="health", tags=("health",))
routes: list[Route | Group] = [
    Route.get("/hello", hello.index, name="hello", tags=("hello",)),
    Route.group("/auth", [
        Route.post("/register", auth.register, name="register").limited("10/minute"),
        Route.post("/login", auth.login, name="login").limited("20/minute"),
        Route.post("/refresh", auth.refresh, name="refresh").limited("60/minute"),
        Route.post("/logout", auth.logout, name="logout").guarded(authenticate),
        Route.get("/me", auth.me, name="me").guarded(authenticate),
    ], tags=("auth",), name="auth"),
    Route.group("/files", [
        Route.post("", files.store, name="store"),
        Route.post("/private", files.keep, name="keep"),
        Route.get("/{path}", files.show, name="show").constrained(path="path"),
    ], tags=("files",), name="files"),
]

__all__ = ["heartbeat", "routes"]
