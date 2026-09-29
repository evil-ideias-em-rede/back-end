"""Teste de instalação em banco DESCARTÁVEL: cria uma conta e dados de teste.

Não chama provedores de IA. Use somente na stack de teste, nunca na base real.
python scripts/smoke_install.py --url http://127.0.0.1:5187 --disposable
"""
import argparse
import json
import secrets
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--disposable", action="store_true", help="Confirma que o banco é descartável")
    args = parser.parse_args()
    if not args.disposable:
        parser.error("Use --disposable somente com uma instalação de teste sem dados reais.")
    base = args.url.rstrip("/")
    token = None

    def request(path, data=None, method=None, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if token and authenticated:
            headers["Authorization"] = "Bearer " + token
        body = json.dumps(data).encode() if data is not None else None
        with urlopen(Request(base + path, data=body, headers=headers, method=method), timeout=30) as response:
            payload = response.read()
            return json.loads(payload) if payload else None

    assert request("/health")["status"] == "ok"
    with urlopen(base + "/home/editor", timeout=15) as response:
        assert "html" in response.headers.get("Content-Type", "")
    suffix = secrets.token_hex(6)
    email = f"smoke-{suffix}@example.invalid"
    password = secrets.token_urlsafe(24)
    account = request("/auth/register", {"email": email, "password": password, "name": "Teste de instalação"})
    token = account["access_token"]
    login = request("/auth/login", {"email": email, "password": password}, authenticated=False)
    assert login["user_id"] == account["user_id"]
    assert request("/auth/me")["email"] == email
    request("/auth/me", {"name": "Teste", "schools": ["Escola de teste"]}, "PATCH")
    turma = request("/api/turmas", {"school": "Escola de teste", "series": "6º ano", "idSeries": "A", "qtd": 30, "disciplina": "Geografia"})
    assert turma["qtd"] == 30
    assert request("/auth/me")["email"] == email
    html = '<!doctype html><html><head><style>body{margin:0}section{box-sizing:border-box;width:210mm;height:297mm;padding:12mm}</style></head><body><section data-ied-page="1"><h1>Teste de instalação</h1></section></body></html>'
    template = request("/api/templates", {"title": "Teste.html", "htmlContent": html, "turmaIds": [turma["id"]]})
    material = request("/api/materiais", {"title": "Teste", "htmlContent": html, "turmaIds": [turma["id"]]})
    assert template["turmaIds"] == material["turmaIds"] == [turma["id"]]
    updated = request(f'/api/materiais/{material["id"]}', {**material, "turmaIds": []}, "PATCH")
    assert updated["turmaIds"] == []
    pdf_request = Request(base + f'/api/materiais/{material["id"]}/download?format=pdf',
                          headers={"Authorization": "Bearer " + token})
    with urlopen(pdf_request, timeout=120) as response:
        assert response.read().startswith(b"%PDF")
    request(f'/api/templates/{template["id"]}', method="DELETE")
    request(f'/api/materiais/{material["id"]}', method="DELETE")
    session = request("/api/workflow/sessions", {"agent_name": "lesson_plan"})
    assert request(f'/api/workflow/sessions/{session["id"]}')["id"] == session["id"]
    try:
        request(f'/api/workflow/sessions/{session["id"]}', authenticated=False)
        raise AssertionError("Sessão privada acessível sem autenticação")
    except HTTPError as exc:
        assert exc.code in (401, 403, 404)
    request(f'/api/workflow/sessions/{session["id"]}', method="DELETE")
    request(f'/api/turmas/{turma["id"]}', method="DELETE")
    print("OK: proxy, SPA, saúde, cadastro, login, perfil, turma, templates, materiais, PDF, sessão e isolamento. Nenhuma chamada de IA.")
    print("A conta de teste permanece apenas no banco descartável; remova a stack de teste após a validação.")


if __name__ == "__main__":
    main()
