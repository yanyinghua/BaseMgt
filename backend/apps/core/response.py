"""统一 API 响应格式：{code, message, data}。"""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def ok(data=None, message="success", http_status=status.HTTP_200_OK):
    return Response({"code": 0, "message": message, "data": data}, status=http_status)


def fail(message="error", code=1, http_status=status.HTTP_400_BAD_REQUEST, data=None):
    return Response(
        {"code": code, "message": message, "data": data}, status=http_status
    )


def api_exception_handler(exc, context):
    """把 DRF 异常也包装成统一格式，前端只需判断 code。"""
    response = exception_handler(exc, context)
    if response is None:
        return None
    payload = {"code": 1, "message": "请求异常", "data": response.data}
    detail = response.data.get("detail") if isinstance(response.data, dict) else None
    if detail:
        payload["message"] = str(detail)
    else:
        payload["message"] = "参数校验失败"
        payload["data"] = response.data
    response.data = payload
    return response
