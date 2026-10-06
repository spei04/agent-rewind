"""Typed client for managed execution. Provider credentials stay on workers."""

from typing import Any

import httpx

from .models import BranchRequest, StudyRequest, TaskSpec


class Client:
    def __init__(self, url: str, api_key: str):
        self.http = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
            follow_redirects=False,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(self, method: str, path: str, body: Any = None) -> Any:
        response = self.http.request(method, path, json=body)
        response.raise_for_status()
        return response.json()

    def record(self, task: TaskSpec) -> str:
        return str(self._request("POST", "/api/runs", task.model_dump())["job_id"])

    def branch(self, request: BranchRequest) -> str:
        return str(self._request("POST", "/api/branches", request.model_dump())["job_id"])

    def study(self, request: StudyRequest) -> str:
        return str(self._request("POST", "/api/studies", request.model_dump())["job_id"])

    def run(self, run_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self._request("GET", f"/api/runs/{run_id}")
        return result

    def cancel(self, job_id: str) -> None:
        self._request("POST", f"/api/jobs/{job_id}/cancel", {})
