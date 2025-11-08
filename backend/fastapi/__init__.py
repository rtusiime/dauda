from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, get_type_hints


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: Any) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class Depends:
    def __init__(self, dependency: Callable[..., Any]) -> None:
        self.dependency = dependency


@dataclass
class Route:
    method: str
    path_template: str
    endpoint: Callable[..., Any]
    response_class: Optional[type] = None
    status_code: int = 200

    def match(self, method: str, path: str) -> tuple[bool, Dict[str, str]]:
        if method.upper() != self.method:
            return False, {}
        template_parts = [part for part in self.path_template.strip("/").split("/") if part]
        path_parts = [part for part in path.strip("/").split("/") if part]
        if len(template_parts) != len(path_parts):
            return False, {}
        params: Dict[str, str] = {}
        for template_part, actual_part in zip(template_parts, path_parts):
            if template_part.startswith('{') and template_part.endswith('}'):
                params[template_part[1:-1]] = actual_part
            elif '{' in template_part and '}' in template_part:
                start = template_part.index('{')
                end = template_part.index('}')
                prefix = template_part[:start]
                suffix = template_part[end + 1 :]
                if not actual_part.startswith(prefix) or not actual_part.endswith(suffix):
                    return False, {}
                key = template_part[start + 1 : end]
                value = actual_part[len(prefix) : len(actual_part) - len(suffix) if suffix else None]
                params[key] = value
            elif template_part != actual_part:
                return False, {}
        return True, params


class APIRouter:
    def __init__(self) -> None:
        self.routes: List[Route] = []

    def _add_route(
        self,
        method: str,
        path: str,
        endpoint: Callable[..., Any],
        response_model: Optional[type] = None,
        response_class: Optional[type] = None,
        status_code: int = 200,
    ) -> Callable[..., Any]:
        self.routes.append(
            Route(method.upper(), path, endpoint, response_class=response_class, status_code=status_code)
        )
        return endpoint

    def get(
        self,
        path: str,
        *,
        response_model: Optional[type] = None,
        response_class: Optional[type] = None,
        status_code: int | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return self._add_route(
                "GET",
                path,
                func,
                response_model=response_model,
                response_class=response_class,
                status_code=200 if status_code is None else status_code,
            )

        return decorator

    def post(
        self,
        path: str,
        *,
        response_model: Optional[type] = None,
        response_class: Optional[type] = None,
        status_code: int | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return self._add_route(
                "POST",
                path,
                func,
                response_model=response_model,
                response_class=response_class,
                status_code=200 if status_code is None else status_code,
            )

        return decorator


class FastAPI:
    def __init__(self, title: str | None = None) -> None:
        self.title = title
        self._routes: List[Route] = []
        self.dependency_overrides: Dict[Callable[..., Any], Callable[..., Any]] = {}

    def include_router(self, router: APIRouter) -> None:
        self._routes.extend(router.routes)

    def get(
        self,
        path: str,
        *,
        response_model: Optional[type] = None,
        response_class: Optional[type] = None,
        status_code: int | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        router = APIRouter()

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            router.get(path, response_model=response_model, response_class=response_class, status_code=status_code)(func)
            self.include_router(router)
            return func

        return decorator

    def post(
        self,
        path: str,
        *,
        response_model: Optional[type] = None,
        response_class: Optional[type] = None,
        status_code: int | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        router = APIRouter()

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            router.post(path, response_model=response_model, response_class=response_class, status_code=status_code)(func)
            self.include_router(router)
            return func

        return decorator

    def _call_dependency(
        self, dependency: Callable[..., Any], overrides: Dict[Callable[..., Any], Callable[..., Any]]
    ) -> tuple[Any, List[Iterable[Any]]]:
        cleanup: List[Iterable[Any]] = []
        callable_dep = overrides.get(dependency, dependency)
        result = callable_dep()
        if inspect.isgenerator(result):
            generator = result
            try:
                value = next(generator)
            except StopIteration as exc:  # pragma: no cover - defensive
                raise RuntimeError("Dependency generator produced no value") from exc
            cleanup.append(generator)
            return value, cleanup
        return result, cleanup

    def _prepare_arguments(
        self,
        route: Route,
        path_params: Dict[str, str],
        body: Any,
        overrides: Dict[Callable[..., Any], Callable[..., Any]],
    ) -> tuple[list[Any], dict[str, Any], List[Iterable[Any]]]:
        signature = inspect.signature(route.endpoint)
        type_hints = get_type_hints(route.endpoint)
        args: list[Any] = []
        kwargs: dict[str, Any] = {}
        cleanup: List[Iterable[Any]] = []
        for name, parameter in signature.parameters.items():
            annotation = type_hints.get(name, parameter.annotation)
            if name in path_params:
                raw_value = path_params[name]
                if annotation is int:
                    value = int(raw_value)
                elif annotation is float:
                    value = float(raw_value)
                else:
                    value = raw_value
                kwargs[name] = value
                continue
            if isinstance(parameter.default, Depends):
                value, dep_cleanup = self._call_dependency(parameter.default.dependency, overrides)
                cleanup.extend(dep_cleanup)
                kwargs[name] = value
                continue
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }:
                if body is None:
                    value = None
                else:
                    if inspect.isclass(annotation) and hasattr(annotation, "model_validate"):
                        value = annotation.model_validate(body)
                    else:
                        value = body
                kwargs[name] = value
                continue
            raise RuntimeError(f"Unsupported parameter configuration: {name}")
        return args, kwargs, cleanup

    def handle(self, method: str, path: str, body: Any = None) -> tuple[int, Any, Optional[type]]:
        for route in self._routes:
            matches, params = route.match(method, path)
            if not matches:
                continue
            overrides = self.dependency_overrides
            try:
                args, kwargs, cleanup = self._prepare_arguments(route, params, body, overrides)
                result = route.endpoint(*args, **kwargs)
            except HTTPException as exc:
                status_code = exc.status_code
                payload: Any = {"detail": exc.detail}
                return status_code, payload, None
            finally:
                for item in cleanup:
                    close = getattr(item, "close", None)
                    if callable(close):
                        close()
            return route.status_code, result, route.response_class
        return 404, {"detail": "Not Found"}, None


__all__ = ["APIRouter", "Depends", "FastAPI", "HTTPException"]
