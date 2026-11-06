"""HTML imprimível do dossiê (servido em /api/cases/{autex}/dossier.html). Todo texto passa por html.escape."""
from __future__ import annotations

from html import escape

NOTICE = "Resultado experimental de triagem. Não constitui prova nem auto de infração."
STATUS_PT = {"indicio": "Indício", "inconclusivo": "Inconclusivo", "sem_indicio": "Sem indício", "nao_avaliado": "Não avaliado"}

CSS = """
body{font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;margin:2rem auto;max-width:960px;color:#1d2321;padding:0 1rem}
h1{font-size:1.6rem;margin:0 0 .2rem}h2{font-size:1.15rem;border-bottom:2px solid #1d2321;padding-bottom:.2rem;margin-top:1.8rem}
.sub{color:#555}.aviso{border:3px solid #9a3b1a;background:#fff4ee;padding:.7rem 1rem;margin:1rem 0;font-weight:600}
table{border-collapse:collapse;width:100%;margin:.5rem 0}th,td{border:1px solid #bbb;padding:.3rem .5rem;text-align:left;vertical-align:top}
th{background:#eef1ef}td.n{text-align:right;font-variant-numeric:tabular-nums}
.flag{border:1px solid #bbb;border-left:6px solid #888;padding:.5rem .8rem;margin:.6rem 0;page-break-inside:avoid}
.flag.indicio{border-left-color:#b3261e}.flag.inconclusivo{border-left-color:#c98a00}.flag.sem_indicio{border-left-color:#2e7d32}
.regra{color:#444;font-style:italic}.imgs{display:flex;gap:.8rem}.imgs figure{flex:1;margin:0}.imgs img{width:100%;border:1px solid #999}
figcaption{font-size:.85rem;color:#444}.score{font-size:1.3rem;font-weight:700}
@media print{body{margin:0;max-width:none}a{color:inherit;text-decoration:none}}
"""


def _e(x) -> str:
    return escape("" if x is None else str(x), quote=True)


def _num(v, nd=1, unit="") -> str:
    if v is None:
        return "—"
    s = f"{v:,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {unit}".strip()


def render(d) -> str:
    e = _e
    v = d.volume_estimado_m3
    linhas = [("Volume autorizado", None, d.volume_autorizado_m3, None, "Sinaflor (AUTEX)"),
              ("Volume declarado explorado", None, d.volume_declarado_explorado_m3, None, "IBAMA IF100" if d.tipo == "POA" else "—"),
              ("Volume compatível com a imagem", v.p10, v.p50, v.p90,
               "Sentinel-2 + calibração quantílica" if d.tipo == "POA" else "Área desmatada × estoque/ha")]
    for f in d.flags_detalhe:
        if f.volume_m3 and f.volume_m3.p50 is not None:
            linhas.append((f"Flag {f.codigo} · {f.titulo}", f.volume_m3.p10, f.volume_m3.p50, f.volume_m3.p90, "Monte Carlo"))
    vol_rows = "".join(f"<tr><td>{e(n)}</td><td class=n>{_num(a)}</td><td class=n>{_num(b)}</td><td class=n>{_num(c)}</td><td>{e(s)}</td></tr>"
                       for n, a, b, c, s in linhas)
    flags = []
    for f in d.flags_detalhe:
        evs = []
        for ev in f.evidencias:
            extra = []
            if ev.valor is not None:
                extra.append(_num(ev.valor, 2, ev.unidade or ""))
            if ev.fonte:
                extra.append(f"fonte {ev.fonte}")
            evs.append(f"<li>{e(ev.descricao)}" + (f" <small>({e('; '.join(extra))})</small>" if extra else "") + "</li>")
        flags.append(f"<div class='flag {e(f.status)}'><strong>{e(f.codigo)} · {e(f.titulo)}</strong> — {e(STATUS_PT.get(f.status, f.status))}"
                     f" · severidade {e(f.severidade)} · confiança {_num(f.confianca, 2)}"
                     + (f" · área {e(_num(f.area_ha, 2, 'ha'))}" if f.area_ha is not None else "")
                     + f"<div class=regra>Regra: {e(f.regra)}</div>" + (f"<ul>{''.join(evs)}</ul>" if evs else "") + "</div>")
    imgs = {i.id: i for i in d.imagens}

    def fig(k):
        i = imgs[k]
        cap = i.rotulo + (f" · nuvem {_num(i.nuvem_pct)}%" if i.nuvem_pct is not None else "")
        return f"<figure><img src='{e(i.png)}' alt='{e(i.rotulo)}'><figcaption>{e(cap)}</figcaption></figure>"
    s2 = "".join(fig(k) for k in ("s2_pre", "s2_pos") if k in imgs)
    cb = "".join(fig(k) for k in ("cbers_pre", "cbers_pos") if k in imgs)
    tl = "".join(f"<tr><td>{e(t.get('data'))}</td><td>{e(t.get('evento'))}</td><td>{e(t.get('fonte'))}</td></tr>" for t in d.linha_do_tempo)
    esp = "".join(f"<tr><td><i>{e(s.nome_cientifico)}</i></td><td>{e(s.nome_popular)}</td><td class=n>{_num(s.volume_autorizado_m3)}</td>"
                  f"<td class=n>{_num(s.volume_explorado_m3)}</td><td class=n>{_num(s.n_arvores, 0)}</td></tr>" for s in d.especies)
    prov = "".join(f"<li>{e(p.fonte)} — <a href='{e(p.url)}'>{e(p.url)}</a> · consultado em {e(p.consultado_em)}"
                   + (f" · licença {e(p.licenca)}" if p.licenca else "") + "</li>" for p in d.proveniencia)
    lim = "".join(f"<li>{e(x)}</li>" for x in d.limitacoes)
    resumo = [("Tipo", d.tipo), ("Município/UF", f"{d.municipio}/{d.uf}"), ("Situação", d.situacao),
              ("Validade", f"{d.validade.inicio or '—'} a {d.validade.fim or '—'}"), ("Área autorizada", _num(d.area_autorizada_ha, 2, "ha")),
              ("Árvores IF100 declaradas", _num(d.n_arvores_declaradas, 0)),
              ("Distúrbio dentro / fora", f"{_num(d.area_disturbio_ha, 2, 'ha')} / {_num(d.area_disturbio_fora_ha, 2, 'ha')}"),
              ("Análise de imagem", "sim" if d.analise_imagem else "não (somente documental)"),
              ("Modo", "SIMULAÇÃO" if d.source_mode == "simulado" else "dados reais"), ("Processado em", d.processado_em)]
    res = "".join(f"<tr><th>{e(k)}</th><td>{e(val)}</td></tr>" for k, val in resumo)
    aviso = d.aviso or NOTICE
    if NOTICE not in aviso:
        aviso = f"{aviso} {NOTICE}"
    return ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<title>Dossiê Lastro — {e(d.autex)}</title><style>{CSS}</style></head><body>"
            f"<h1>Dossiê de triagem — autorização {e(d.autex)}</h1><div class=sub>Lastro · prioridade de fiscalização</div>"
            f"<div class=aviso>{e(aviso)}</div>"
            f"<p class=score>Score de prioridade: {_num(d.score, 2)}</p>"
            f"<h2>Resumo</h2><table>{res}</table>"
            f"<h2>Volumes (m³)</h2><table><tr><th>Grandeza</th><th>p10</th><th>p50</th><th>p90</th><th>Fonte</th></tr>{vol_rows}</table>"
            f"<h2>Flags</h2>{''.join(flags) or '<p>Nenhuma flag avaliada.</p>'}"
            + (f"<h2>Imagens Sentinel-2 (antes / depois)</h2><div class=imgs>{s2}</div>" if s2 else "")
            + (f"<h2>Imagens CBERS-4A WPM 2 m</h2><div class=imgs>{cb}</div>" if cb else "")
            + (f"<h2>Espécies (top por volume explorado)</h2><table><tr><th>Espécie</th><th>Nome popular</th><th>Autorizado m³</th><th>Explorado m³</th><th>Árvores</th></tr>{esp}</table>" if esp else "")
            + (f"<h2>Linha do tempo</h2><table><tr><th>Data</th><th>Evento</th><th>Fonte</th></tr>{tl}</table>" if tl else "")
            + f"<h2>Limitações</h2><ul>{lim}</ul><h2>Proveniência</h2><ul>{prov}</ul>"
            "<p class=sub>Documento gerado automaticamente pelo Lastro. Indícios para priorização de fiscalização; não constituem prova nem conclusão jurídica.</p>"
            "</body></html>")
