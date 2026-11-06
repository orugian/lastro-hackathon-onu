"""Comunicação automática ao IBAMA (Ouvidoria) para casos acima do limiar de prioridade.

Regra: score de triagem ≥ LIMIAR (padrão 0,70) e ao menos um indício → gera automaticamente um
PROTOCOLO DE COMUNICAÇÃO (pacote auditável) e o coloca na fila "Comunicações ao IBAMA".

O envio passa por um conector configurável (env LASTRO_CONECTOR):
  - "simulado" (padrão): grava o pacote numa caixa de saída local (data/comunicacoes/saida/), sem
    contato externo. É o modo da demonstração.
  - "email": envia por SMTP para LASTRO_EMAIL_DESTINO (exige LASTRO_SMTP_HOST/USER/PASS). Desligado
    por padrão; só deve ser ativado mediante acordo institucional.
  - "falabr": gera o texto da manifestação no formato do Fala.BR (Ouvidoria do IBAMA) para protocolo
    pelo servidor responsável; o Fala.BR não oferece API pública de submissão.

Salvaguarda (human-in-the-loop): o envio exige confirmação de um servidor identificado
(LASTRO_CONFIRMACAO_HUMANA=1, padrão). Com 0, o envio é automático — não recomendado: o score é
índice de prioridade, não probabilidade de irregularidade.
"""
from __future__ import annotations

import hashlib
import json
import os
import smtplib
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(os.environ.get("LASTRO_COMUNICACOES", ROOT / "data" / "comunicacoes"))
LIMIAR = float(os.environ.get("LASTRO_LIMIAR_COMUNICACAO", "0.70"))
CONECTOR = os.environ.get("LASTRO_CONECTOR", "simulado")
CONFIRMACAO_HUMANA = os.environ.get("LASTRO_CONFIRMACAO_HUMANA", "1") != "0"
DESTINO = {
    "orgao": "IBAMA - Ouvidoria",
    "canal": "Fala.BR (https://falabr.cgu.gov.br) · Ouvidoria do IBAMA",
    "assunto": "Comunicação de indício para priorização de fiscalização - exploração florestal (DOF/AUTEX)",
}
AVISO = ("Comunicação gerada automaticamente por ferramenta experimental de triagem. Os indícios abaixo "
         "NÃO constituem prova, conclusão de irregularidade ou auto de infração; destinam-se à "
         "priorização de verificação pelo órgão competente.")
_lock = threading.Lock()


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _arquivo() -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    return BASE / "fila.json"


def carregar() -> dict:
    p = _arquivo()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"limiar": LIMIAR, "conector": CONECTOR, "comunicacoes": []}


def _salvar(estado: dict) -> None:
    p = _arquivo()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def elegivel(caso: dict, limiar: float = LIMIAR) -> bool:
    indicios = [f for f in caso.get("flags", []) if f.get("status") == "indicio"]
    return float(caso.get("score") or 0) >= limiar and bool(indicios)


def montar_pacote(dossier: dict, base_url: str = "http://127.0.0.1:8000") -> dict:
    """Pacote auditável: resumo, indícios com regra/evidência, volumes, proveniência e hash."""
    autex = dossier["autex"]
    flags = [f for f in dossier.get("flags_detalhe", []) if f.get("status") == "indicio"]
    corpo = {
        "destino": DESTINO,
        "aviso": AVISO,
        "referencia": {
            "autorizacao_autex": autex,
            "documento": "AUTEX / DOF vinculado (Sinaflor)",
            "tipo": dossier.get("tipo"), "uf": dossier.get("uf"), "municipio": dossier.get("municipio"),
            "validade": dossier.get("validade"), "situacao": dossier.get("situacao"),
            "centroide_lon_lat": dossier.get("centroide"),
        },
        "prioridade": {"score": dossier.get("score"), "limiar": LIMIAR,
                       "natureza": "índice de prioridade de triagem, não probabilidade"},
        "volumes_m3": {
            "autorizado": dossier.get("volume_autorizado_m3"),
            "declarado_explorado": dossier.get("volume_declarado_explorado_m3"),
            "estimado_imagem": dossier.get("volume_estimado_m3"),
        },
        "indicios": [{
            "codigo": f["codigo"], "titulo": f["titulo"], "severidade": f["severidade"],
            "confianca": f["confianca"], "regra": f["regra"],
            "evidencias": [e.get("descricao") for e in f.get("evidencias", [])],
            "volume_m3": f.get("volume_m3"), "area_ha": f.get("area_ha"),
        } for f in flags],
        "limitacoes": dossier.get("limitacoes", []),
        "proveniencia": [{k: p.get(k) for k in ("fonte", "url", "consultado_em")} for p in dossier.get("proveniencia", [])],
        "dossie_url": f"{base_url}/api/cases/{autex}/dossier.html",
        "source_mode": dossier.get("source_mode"),
        "gerado_em": _agora(),
    }
    canon = json.dumps(corpo, ensure_ascii=False, sort_keys=True).encode("utf-8")
    corpo["sha256"] = hashlib.sha256(canon).hexdigest()
    return corpo


def texto_manifestacao(pacote: dict) -> str:
    r = pacote["referencia"]
    v = pacote["volumes_m3"]
    est = v.get("estimado_imagem") or {}
    linhas = [
        f"Assunto: {DESTINO['assunto']}",
        "",
        pacote["aviso"],
        "",
        f"Autorização (AUTEX): {r['autorizacao_autex']} · {r['tipo']} · {r['municipio']}/{r['uf']}",
        f"Validade: {(r.get('validade') or {}).get('inicio')} a {(r.get('validade') or {}).get('fim')} · Situação: {r.get('situacao')}",
        f"Prioridade de triagem: {pacote['prioridade']['score']:.2f} (limiar {pacote['prioridade']['limiar']:.2f})",
        f"Volumes (m³): autorizado {v.get('autorizado')} · declarado explorado {v.get('declarado_explorado')} · "
        f"estimado pela imagem p10–p90 {est.get('p10')}–{est.get('p90')}",
        "",
        "Indícios:",
    ]
    for f in pacote["indicios"]:
        linhas.append(f"- [{f['codigo']}] {f['titulo']} (severidade {f['severidade']}, confiança {f['confianca']:.0%})")
        for e in f["evidencias"][:3]:
            linhas.append(f"    · {e}")
    linhas += ["", f"Dossiê completo: {pacote['dossie_url']}", f"Integridade (SHA-256): {pacote['sha256']}"]
    if pacote.get("source_mode") == "simulado":
        linhas.insert(0, "*** CENÁRIO SIMULADO - NÃO ENVIAR ***")
    return "\n".join(linhas)


def _evento(c: dict, acao: str, por: str, detalhe: str = "") -> None:
    c.setdefault("trilha", []).append({"em": _agora(), "acao": acao, "por": por, "detalhe": detalhe})


def gerar_automaticamente(casos: list[dict], ler_dossier, limiar: float = LIMIAR, base_url: str = "http://127.0.0.1:8000") -> dict:
    """Varre o índice e cria comunicações para os casos elegíveis ainda sem protocolo. Idempotente."""
    with _lock:
        estado = carregar()
        estado["limiar"], estado["conector"], estado["confirmacao_humana"] = limiar, CONECTOR, CONFIRMACAO_HUMANA
        existentes = {c["autex"] for c in estado["comunicacoes"]}
        novos = 0
        for caso in casos:
            if caso["autex"] in existentes or not elegivel(caso, limiar):
                continue
            pacote = montar_pacote(ler_dossier(caso["autex"]), base_url)
            n = len(estado["comunicacoes"]) + 1
            com = {
                "protocolo": f"LASTRO-{datetime.now(timezone.utc):%Y%m%d}-{n:04d}",
                "autex": caso["autex"], "score": caso["score"], "tipo": caso["tipo"],
                "municipio": caso["municipio"], "uf": caso["uf"],
                "indicios": [f["codigo"] for f in caso["flags"] if f["status"] == "indicio"],
                "source_mode": caso.get("source_mode", "real"),
                "status": "aguardando_confirmacao" if CONFIRMACAO_HUMANA else "pronto_para_envio",
                "sha256": pacote["sha256"], "criado_em": _agora(),
            }
            _evento(com, "gerado_automaticamente", "sistema", f"score {caso['score']:.2f} ≥ limiar {limiar:.2f}")
            pdir = BASE / "pacotes"
            pdir.mkdir(parents=True, exist_ok=True)
            (pdir / f"{com['protocolo']}.json").write_text(json.dumps(pacote, ensure_ascii=False, indent=1), encoding="utf-8")
            (pdir / f"{com['protocolo']}.txt").write_text(texto_manifestacao(pacote), encoding="utf-8")
            estado["comunicacoes"].append(com)
            novos += 1
            if not CONFIRMACAO_HUMANA:
                _enviar(com, "sistema (envio automático)")
        _salvar(estado)
        return {"novos": novos, "total": len(estado["comunicacoes"])}


def _enviar(com: dict, por: str) -> None:
    pacote_txt = BASE / "pacotes" / f"{com['protocolo']}.txt"
    if com.get("source_mode") == "simulado":
        com["status"] = "bloqueado_simulacao"
        _evento(com, "envio_bloqueado", por, "cenário simulado nunca é enviado")
        return
    if CONECTOR == "email":
        host, dest = os.environ.get("LASTRO_SMTP_HOST"), os.environ.get("LASTRO_EMAIL_DESTINO")
        if not host or not dest:
            com["status"] = "erro_envio"
            _evento(com, "erro_envio", por, "SMTP/destino não configurados")
            return
        msg = EmailMessage()
        msg["Subject"] = f"[{com['protocolo']}] {DESTINO['assunto']}"
        msg["From"] = os.environ.get("LASTRO_SMTP_USER", "lastro@localhost")
        msg["To"] = dest
        msg.set_content(pacote_txt.read_text(encoding="utf-8"))
        msg.add_attachment((BASE / "pacotes" / f"{com['protocolo']}.json").read_bytes(), maintype="application",
                           subtype="json", filename=f"{com['protocolo']}.json")
        with smtplib.SMTP(host, int(os.environ.get("LASTRO_SMTP_PORT", "587")), timeout=30) as s:
            s.starttls()
            if os.environ.get("LASTRO_SMTP_USER"):
                s.login(os.environ["LASTRO_SMTP_USER"], os.environ.get("LASTRO_SMTP_PASS", ""))
            s.send_message(msg)
        com["status"], com["canal"] = "enviado", f"email:{dest}"
    else:
        saida = BASE / "saida"
        saida.mkdir(parents=True, exist_ok=True)
        (saida / f"{com['protocolo']}.txt").write_text(pacote_txt.read_text(encoding="utf-8"), encoding="utf-8")
        com["status"] = "enviado_simulado" if CONECTOR == "simulado" else "pronto_falabr"
        com["canal"] = "caixa de saída local (demonstração)" if CONECTOR == "simulado" else "texto Fala.BR para protocolo manual"
    com["enviado_em"] = _agora()
    _evento(com, "enviado", por, com.get("canal", ""))


def confirmar(protocolo: str, servidor: str, justificativa: str) -> dict:
    with _lock:
        estado = carregar()
        com = next((c for c in estado["comunicacoes"] if c["protocolo"] == protocolo), None)
        if com is None:
            raise KeyError(protocolo)
        if com["status"] not in ("aguardando_confirmacao", "pronto_para_envio", "erro_envio"):
            return com
        _evento(com, "confirmado", servidor, justificativa)
        _enviar(com, servidor)
        _salvar(estado)
        return com


def descartar(protocolo: str, servidor: str, justificativa: str) -> dict:
    with _lock:
        estado = carregar()
        com = next((c for c in estado["comunicacoes"] if c["protocolo"] == protocolo), None)
        if com is None:
            raise KeyError(protocolo)
        com["status"] = "descartado"
        _evento(com, "descartado", servidor, justificativa)
        _salvar(estado)
        return com
