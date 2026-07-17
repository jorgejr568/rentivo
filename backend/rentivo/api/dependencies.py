from fastapi import Request

from rentivo.services.container import RequestServices


def get_services(request: Request) -> RequestServices:
    return request.state.services.get()
