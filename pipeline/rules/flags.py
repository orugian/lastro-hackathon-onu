"""Motor de flags do Lastro: funções puras que retornam `contracts.models.Flag`.

Linguagem: indício / divergência / prioridade de fiscalização. Dados ausentes -> nao_avaliado/inconclusivo,
nunca sem_indicio. Todas as distâncias/áreas já chegam calculadas em UTM (SIRGAS 2000).
"""
from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from contracts.models import Evidencia, Faixa, Flag

TOL_BORDA_M = 20.0
LIMITE_COORD_INCOERENTE_M = 5000.0
INTENSIDADE_MAX_M3_HA = 30.0
RAZAO_IF100_MAX = 1.10
PROB_MIN_B = 0.6           # prob média mínima do polígono para B
AREA_MIN_B_HA = 1.0        # área somada mínima para indício B
AREA_MIN_POLIGONO_HA = 0.5  # polígono mínimo fora da UPA
B_SANITY_X_AUT = 3.0        # área fora > 3 × autorizada -> inconclusivo (possível artefato)
B_SANITY_FRAC_BUFFER = 0.30 # área fora > 30% do buffer -> inconclusivo
F2_TOLERANCIA = 1.05
A_BLOCO_MIN = 5
A_FRAC_MIN = 0.10

TITULOS = {
    "A": "Volume declarado sem lastro observável",
    "B": "Distúrbio sem declaração (dentro ou fora da UPA)",
    "C": "Árvores declaradas fora do polígono",
    "D": "Volume explorado acima do autorizado",
    "E": "Exploração fora da validade",
    "F2": "Área desmatada acima da autorizada",
    "F6": "Mudança sobre UC/TI/embargo",
}
TITULOS_ASV = {"B": "Corte raso fora do polígono autorizado", "D": "Volume estimado acima do autorizado",
               "E": "Desmatamento fora da validade"}


def _fmt(x, nd=1):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "n/d"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _isnum(x) -> bool:
    try:
        return x is not None and not pd.isna(x) and np.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def _flag(codigo, status, sev, conf, regra, evid=None, vol=None, area=None, tipo="POA") -> Flag:
    titulo = TITULOS_ASV.get(codigo, TITULOS[codigo]) if tipo in ("ASV", "UAS") else TITULOS[codigo]
    if status in ("sem_indicio", "nao_avaliado"):
        sev = "info"
    elif status == "inconclusivo" and sev in ("alta", "media"):
        sev = "baixa"
    return Flag(codigo=codigo, titulo=titulo, status=status, severidade=sev,
                confianca=float(np.clip(round(conf, 2), 0, 1)), regra=regra, evidencias=evid or [],
                volume_m3=Faixa(**vol) if isinstance(vol, dict) else vol, area_ha=area)


# ------------------------------------------------------------------ A
def maior_bloco_contiguo(ids: Iterable[str]) -> int:
    """Maior componente 8-conexo entre células cujo id é '{crs}_{ix}_{iy}'."""
    from scipy.ndimage import label
    pts = []
    for i in ids:
        try:
            _, ix, iy = str(i).rsplit("_", 2)
            pts.append((int(ix), int(iy)))
        except ValueError:
            continue
    if not pts:
        return 0
    a = np.array(pts)
    a -= a.min(0)
    grid = np.zeros(a.max(0) + 1, dtype=bool)
    grid[a[:, 0], a[:, 1]] = True
    lab, n = label(grid, structure=np.ones((3, 3)))
    return int(np.bincount(lab.ravel())[1:].max()) if n else 0


def flag_A(celulas, mc: Optional[dict], cobertura_calib: Optional[float], n_arvores: int,
           blocos=None, frac_min: float = A_FRAC_MIN, exc_min_m3: float = 50.0) -> Flag:
    """Avaliação em dois níveis onde a incerteza está calibrada (R² por célula ≈ 0, então nunca por célula isolada):
    (i) UPA: Σ declarado nas células observáveis > p90 do Monte Carlo da UPA;
    (ii) blocos 3×3 (9 ha): bloco sem_lastro se Σ declarado > p90 do bloco (MC com fator comum por bloco calibrado
         para cobertura 80%); indício se Σ excesso ≥ frac_min do declarado (p95 nas UPAs limpas) e ≥ exc_min_m3.
    blocos: DataFrame de pipeline.volume.estimar.avaliar_blocos. Sem blocos -> critério legado por células."""
    if blocos is not None:
        return _flag_A_blocos(celulas, mc, cobertura_calib, n_arvores, blocos, frac_min, exc_min_m3)
    regra = (f"Σ(vol. declarado − p90 compatível com a imagem) nas células 'sem_lastro' (declarado > p90 e ≥ 5 m³). "
             f"Indício se o volume declarado na UPA superar o p90 do volume estimado pela imagem (Monte Carlo) E "
             f"(houver ≥ {A_BLOCO_MIN} células sem_lastro contíguas OU o excesso for ≥ {A_FRAC_MIN:.0%} do declarado). "
             f"Só o critério por célula, sem divergência no agregado da UPA -> inconclusivo.")
    if not n_arvores:
        return _flag("A", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Sem árvores IF100 declaradas: não há volume a confrontar com a imagem.", fonte="if100")])
    if celulas is None or len(celulas) == 0 or mc is None:
        return _flag("A", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Imagem não processada para este caso.")])
    c = celulas[celulas["dentro_upa"].astype(bool)]
    n_dec = int((c["n_arvores"] > 0).sum())
    obs = c[c["classe"] != "nao_observavel"]
    frac_obs = float((c.loc[c["n_arvores"] > 0, "classe"] != "nao_observavel").mean()) if n_dec else 0.0
    cov = cobertura_calib if _isnum(cobertura_calib) else 0.5
    conf = float(np.clip(cov * frac_obs, 0.05, 0.95))
    if frac_obs < 0.5:
        return _flag("A", "inconclusivo", "info", conf, regra, [Evidencia(
            tipo="metrica", descricao=f"Apenas {_fmt(100*frac_obs,0)}% das células com árvores declaradas são observáveis (nuvem/sem dado).",
            valor=round(100 * frac_obs, 1), unidade="%", camada="celulas", filtro={"classe": "nao_observavel"}, fonte="s2")])
    sl = obs[obs["classe"] == "sem_lastro"]
    decl_obs = float(obs["vol_declarado"].sum())
    excesso = float((sl["vol_declarado"] - sl["vol_p90"]).clip(lower=0).sum())
    frac = excesso / decl_obs if decl_obs > 0 else 0.0
    bloco = maior_bloco_contiguo(sl["id"])
    decl_upa = float(mc.get("declarado_upa_m3", decl_obs))
    upa = mc.get("upa", {})
    upa_div = _isnum(upa.get("p90")) and decl_upa > upa["p90"]
    cel_crit = (bloco >= A_BLOCO_MIN) or (frac >= A_FRAC_MIN)
    ev = [
        Evidencia(tipo="metrica", descricao=f"{len(sl)} células de 1 ha com volume declarado acima do p90 compatível com a imagem; maior bloco contíguo: {bloco} células",
                  valor=float(len(sl)), unidade="células", camada="celulas", filtro={"classe": "sem_lastro"}, fonte="if100"),
        Evidencia(tipo="metrica", descricao=f"Volume declarado nessas células: {_fmt(float(sl['vol_declarado'].sum()))} m³; p90 compatível com a imagem: {_fmt(float(sl['vol_p90'].sum()))} m³",
                  valor=round(float(sl["vol_declarado"].sum()), 1), unidade="m³", fonte="if100"),
        Evidencia(tipo="metrica", descricao=f"Excesso sem lastro = {_fmt(excesso)} m³ ({_fmt(100*frac,0)}% do declarado em células observáveis)",
                  valor=round(excesso, 1), unidade="m³", fonte="s2"),
        Evidencia(tipo="metrica", descricao=(f"Volume declarado na UPA (IF100, células observáveis): {_fmt(decl_upa)} m³; volume compatível com a imagem (Monte Carlo): "
                                             f"p10 {_fmt(upa.get('p10'))} · p50 {_fmt(upa.get('p50'))} · p90 {_fmt(upa.get('p90'))} m³"),
                  valor=round(decl_upa, 1), unidade="m³", fonte="s2"),
    ]
    sev = "alta" if frac >= 0.2 else "media"
    if upa_div and cel_crit:
        return _flag("A", "indicio", sev, conf, regra, ev, vol=mc.get("sem_lastro_excesso"))
    if cel_crit:
        ev.append(Evidencia(tipo="texto", descricao="Divergência concentrada em células, mas o total declarado da UPA está dentro do intervalo compatível com a imagem; pode refletir erro de GPS das coordenadas IF100."))
        return _flag("A", "inconclusivo", "baixa", conf, regra, ev, vol=mc.get("sem_lastro_excesso"))
    return _flag("A", "sem_indicio", "info", conf, regra, ev)


def _flag_A_blocos(celulas, mc, cobertura_calib, n_arvores, blocos, frac_min, exc_min_m3) -> Flag:
    regra = (f"Avaliado em blocos de 3×3 células (9 ha) e no total da UPA, onde a incerteza está calibrada (nunca por árvore ou célula isolada). "
             f"Indício se (i) o volume declarado na UPA (IF100, células observáveis) supera o p90 do volume compatível com a imagem "
             f"(Monte Carlo), ou (ii) os blocos com declarado > p90 do bloco somam excesso ≥ {frac_min:.0%} do declarado e ≥ {exc_min_m3:.0f} m³ "
             f"(limiar = p95 das UPAs de calibração sem indício).")
    if not n_arvores:
        return _flag("A", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Sem árvores IF100 declaradas: não há volume a confrontar com a imagem.", fonte="if100")])
    if celulas is None or len(celulas) == 0 or mc is None:
        return _flag("A", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Imagem não processada para este caso.")])
    c = celulas[celulas["dentro_upa"].astype(bool)]
    n_dec = int((c["n_arvores"] > 0).sum())
    frac_obs = float((c.loc[c["n_arvores"] > 0, "classe"] != "nao_observavel").mean()) if n_dec else 0.0
    cov = cobertura_calib if _isnum(cobertura_calib) else 0.5
    conf = float(np.clip(cov * frac_obs, 0.05, 0.95))
    if frac_obs < 0.5:
        return _flag("A", "inconclusivo", "info", conf, regra, [Evidencia(
            tipo="metrica", descricao=f"Apenas {_fmt(100*frac_obs,0)}% das células com árvores declaradas são observáveis (nuvem/sem dado).",
            valor=round(100 * frac_obs, 1), unidade="%", camada="celulas", filtro={"classe": "nao_observavel"}, fonte="s2")])
    b = blocos
    sl = b[b["sem_lastro"]]
    decl = float(b["vol_declarado"].sum())
    exc = float(sl["excesso"].sum())
    frac = exc / decl if decl > 0 else 0.0
    upa = mc.get("upa", {})
    decl_upa = float(mc.get("declarado_upa_m3", decl))
    upa_div = _isnum(upa.get("p90")) and decl_upa > upa["p90"]
    bloco_crit = frac >= frac_min and exc >= exc_min_m3
    ncel = int(c["classe"].eq("sem_lastro").sum())
    ev = [
        Evidencia(tipo="metrica", descricao=f"{len(sl)} de {len(b)} blocos de 9 ha com volume declarado acima do p90 compatível com a imagem ({ncel} células destacadas)",
                  valor=float(len(sl)), unidade="blocos", camada="celulas", filtro={"classe": "sem_lastro"}, fonte="if100"),
        Evidencia(tipo="metrica", descricao=f"Volume declarado nesses blocos: {_fmt(float(sl['vol_declarado'].sum()))} m³; p90 compatível com a imagem: {_fmt(float(sl['p90'].sum()))} m³",
                  valor=round(float(sl["vol_declarado"].sum()), 1), unidade="m³", fonte="if100"),
        Evidencia(tipo="metrica", descricao=f"Excesso sem lastro = {_fmt(exc)} m³ ({_fmt(100*frac,0)}% do declarado em células observáveis; limiar {_fmt(100*frac_min,0)}%)",
                  valor=round(exc, 1), unidade="m³", fonte="s2"),
        Evidencia(tipo="metrica", descricao=(f"Volume declarado na UPA (IF100, células observáveis): {_fmt(decl_upa)} m³; volume compatível com a imagem (Monte Carlo): "
                                             f"p10 {_fmt(upa.get('p10'))} · p50 {_fmt(upa.get('p50'))} · p90 {_fmt(upa.get('p90'))} m³"),
                  valor=round(decl_upa, 1), unidade="m³", fonte="s2"),
    ]
    vol = {"p10": round(float((sl["vol_declarado"] - sl["p90"]).clip(lower=0).sum()), 1),
           "p50": round(float((sl["vol_declarado"] - sl["p50"]).clip(lower=0).sum()), 1),
           "p90": round(float((sl["vol_declarado"] - sl["p10"]).clip(lower=0).sum()), 1)}
    if upa_div:
        vol_upa = {"p10": round(max(decl_upa - upa["p90"], 0), 1), "p50": round(max(decl_upa - upa["p50"], 0), 1), "p90": round(max(decl_upa - upa["p10"], 0), 1)}
        if vol_upa["p50"] > vol["p50"]:
            vol = vol_upa
    if upa_div or bloco_crit:
        sev = "alta" if (upa_div and bloco_crit) or frac >= 2 * frac_min else "media"
        return _flag("A", "indicio", sev, conf, regra, ev, vol=vol)
    if len(sl) and frac >= 0.5 * frac_min:
        ev.append(Evidencia(tipo="texto", descricao="Divergência localizada abaixo do limiar calibrado; pode refletir erro de GPS das coordenadas IF100 ou clareiras não visíveis em 10 m."))
        return _flag("A", "inconclusivo", "baixa", conf, regra, ev, vol=vol)
    return _flag("A", "sem_indicio", "info", conf, regra, ev)


# ------------------------------------------------------------------ B
def flag_B(mudanca, celulas, deter_aoi, mc: Optional[dict], tipo: str = "POA", vol_fora: Optional[dict] = None,
           area_upa_ha: Optional[float] = None, area_buffer_ha: Optional[float] = None) -> Flag:
    """mudanca: polígonos com area_ha, prob, dentro_upa, dist_limite_m, coberto_outra (bool)."""
    regra = (f"Polígono de distúrbio (prob média ≥ {PROB_MIN_B}, ≥ {AREA_MIN_POLIGONO_HA} ha, sobre floresta no pré) fora da UPA, a mais de {TOL_BORDA_M:.0f} m do limite e não coberto por outra autorização "
             f"(indício se ≥ {AREA_MIN_B_HA:.0f} ha); no POA, também distúrbio dentro da UPA em células sem árvore declarada "
             f"(indício se ≥ 5% da área da UPA, pois estradas e pátios de manejo são esperados). "
             f"Sanidade: área fora > {B_SANITY_X_AUT:.0f}× a autorizada ou > {B_SANITY_FRAC_BUFFER:.0%} do buffer -> inconclusivo.")
    if mudanca is None:
        return _flag("B", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Imagem não processada para este caso.")], tipo=tipo)
    m = mudanca
    fora = m[(~m["dentro_upa"].astype(bool)) & (m["dist_limite_m"] > TOL_BORDA_M) & (m["prob"] >= PROB_MIN_B) & (m["area_ha"] >= AREA_MIN_POLIGONO_HA)
             & (~m.get("coberto_outra", pd.Series(False, index=m.index)).astype(bool))] if len(m) else m
    a_fora = float(fora["area_ha"].sum()) if len(fora) else 0.0
    a_nd = 0.0
    if tipo == "POA" and celulas is not None and len(celulas):
        c = celulas[celulas["dentro_upa"].astype(bool) & (celulas["classe"] == "nao_declarado")]
        a_nd = float((c["disturbio_frac"] * c["area_ha"]).sum())
    ev = []
    if len(fora):
        dmax = float(fora["dist_limite_m"].max())
        ev.append(Evidencia(tipo="geometria", descricao=f"{_fmt(a_fora)} ha de distúrbio em {len(fora)} polígono(s) fora da UPA, até {_fmt(dmax,0)} m do limite",
                            valor=round(a_fora, 2), unidade="ha", camada="mudanca", filtro={"dentro_upa": False}, fonte="s2"))
    if a_nd > 0:
        ev.append(Evidencia(tipo="geometria", descricao=f"{_fmt(a_nd)} ha de distúrbio dentro da UPA em células sem árvore declarada (≥ 15% da célula)",
                            valor=round(a_nd, 2), unidade="ha", camada="celulas", filtro={"classe": "nao_declarado"}, fonte="s2"))
    if deter_aoi is not None and len(deter_aoi) and len(fora):
        try:
            hit = deter_aoi[deter_aoi.intersects(fora.to_crs(deter_aoi.crs).union_all())]
        except Exception:
            hit = deter_aoi.iloc[:0]
        if len(hit):
            ult = hit.sort_values("data").iloc[-1]
            ev.append(Evidencia(tipo="documento", descricao=f"{len(hit)} alerta(s) DETER coincidente(s) com o distúrbio fora da UPA; mais recente {ult['classe']} de {ult['data']}",
                                valor=float(len(hit)), unidade="alertas", camada="deter", fonte="deter"))
    area = a_fora + a_nd
    vol = None
    if tipo == "POA" and mc:
        nd, ndf = mc.get("nao_declarado", {}), mc.get("nao_declarado_fora", {})
        vol = {k: round((nd.get(k) or 0) + (ndf.get(k) or 0), 1) for k in ("p10", "p50", "p90")}
    elif vol_fora:
        vol = {k: vol_fora.get(k) for k in ("p10", "p50", "p90")}
    conf = float(np.clip(0.55 + 0.4 * (float(fora["prob"].mean()) if len(fora) else 0.5) - 0.2, 0.3, 0.9))
    lim_nd = 0.05 * area_upa_ha if _isnum(area_upa_ha) else float("inf")
    suspeito = (_isnum(area_upa_ha) and a_fora > B_SANITY_X_AUT * area_upa_ha) or (_isnum(area_buffer_ha) and a_fora > B_SANITY_FRAC_BUFFER * area_buffer_ha)
    if suspeito:
        ev.append(Evidencia(tipo="texto", descricao=(f"Área de distúrbio fora ({_fmt(a_fora)} ha) excede {B_SANITY_X_AUT:.0f}× a área autorizada ou {B_SANITY_FRAC_BUFFER:.0%} do buffer: "
                                                     "possível artefato de composição sazonal/nuvem ou desmatamento regional não vinculado; requer verificação visual.")))
        return _flag("B", "inconclusivo", "baixa", 0.3, regra, ev, vol=vol, area=round(area, 2), tipo=tipo)
    if a_fora >= AREA_MIN_B_HA or a_nd >= lim_nd:
        if any(e.fonte == "deter" for e in ev):
            conf = min(0.95, conf + 0.1)
        return _flag("B", "indicio", "alta" if area >= 10 else "media", conf, regra, ev, vol=vol, area=round(area, 2), tipo=tipo)
    if area > 0:
        return _flag("B", "inconclusivo", "baixa", conf, regra, ev, area=round(area, 2), tipo=tipo)
    return _flag("B", "sem_indicio", "info", 0.7, regra, ev, area=0.0, tipo=tipo)


# ------------------------------------------------------------------ C
def flag_C(doc: dict) -> Flag:
    """doc: linha de regras_doc (status_C, c_n_fora, c_volume_fora_m3, c_n_coord_incoerente, n_arvores, n_sem_coordenada)."""
    regra = (f"Coordenada IF100 a mais de {TOL_BORDA_M:.0f} m e até {LIMITE_COORD_INCOERENTE_M/1000:.0f} km fora do polígono autorizado "
             f"(acima de {LIMITE_COORD_INCOERENTE_M/1000:.0f} km: coordenada incoerente, tratada como limitação cadastral)")
    n = int(doc.get("n_arvores") or 0)
    if n == 0:
        return _flag("C", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Sem árvores IF100 declaradas para esta autorização.", fonte="if100")])
    nf, vf, ninc = int(doc.get("c_n_fora") or 0), float(doc.get("c_volume_fora_m3") or 0), int(doc.get("c_n_coord_incoerente") or 0)
    ev = []
    if nf:
        ev.append(Evidencia(tipo="geometria", descricao=f"{nf} árvore(s) declarada(s) como explorada(s) fora da UPA ({_fmt(vf)} m³), entre 20 m e 5 km do limite",
                            valor=float(nf), unidade="árvores", camada="arvores", filtro={"dentro_upa": False}, fonte="if100"))
    if ninc:
        ev.append(Evidencia(tipo="texto", descricao=f"{ninc} árvore(s) com coordenada a mais de 5 km do polígono: limitação de qualidade cadastral, não computada como indício", valor=float(ninc), unidade="árvores", fonte="if100"))
    nsc = int(doc.get("n_sem_coordenada") or 0)
    if nsc:
        ev.append(Evidencia(tipo="texto", descricao=f"{nsc} árvore(s) sem coordenada válida", valor=float(nsc), unidade="árvores", fonte="if100"))
    st = doc.get("status_C") or "nao_avaliado"
    if st == "sem_indicio" and nsc:
        st = "inconclusivo"
    frac = nf / max(n, 1)
    sev = "alta" if (frac >= 0.05 or vf >= 100) else "media" if nf >= 3 else "baixa"
    return _flag("C", st, sev, 0.95 if st != "nao_avaliado" else 0.0, regra, ev)


# ------------------------------------------------------------------ D
def flag_D_poa(doc: dict, area_ha: Optional[float]) -> Flag:
    regra = (f"Σ explorado (IF100) > Σ autorizado (POA), ou razão agregada IF100 explorado/autorizado > {RAZAO_IF100_MAX:.2f}, "
             f"ou intensidade > {INTENSIDADE_MAX_M3_HA:.0f} m³/ha. Diferenças por árvore (> 10%) são reportadas como contexto (cubagem real × inventário).")
    n = int(doc.get("n_arvores") or 0)
    if n == 0:
        return _flag("D", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Sem volume explorado declarado (IF100).", fonte="if100")])
    exp_, aut = doc.get("volume_explorado_m3"), doc.get("volume_autorizado_m3")
    raz, inten = doc.get("d_razao_if100"), doc.get("intensidade_m3_ha")
    ev = [Evidencia(tipo="metrica", descricao=f"Volume explorado declarado {_fmt(exp_)} m³ para {_fmt(aut)} m³ autorizados no POA", valor=round(float(exp_), 1) if _isnum(exp_) else None, unidade="m³", fonte="if100")]
    if _isnum(raz):
        ev.append(Evidencia(tipo="metrica", descricao=f"Razão agregada explorado/autorizado das mesmas árvores (IF100): {_fmt(raz,3)}", valor=round(float(raz), 3), unidade="razão", fonte="if100"))
    if _isnum(inten):
        ev.append(Evidencia(tipo="metrica", descricao=f"Intensidade declarada {_fmt(inten)} m³/ha (teto {INTENSIDADE_MAX_M3_HA:.0f} m³/ha)", valor=round(float(inten), 2), unidade="m³/ha", fonte="if100"))
    nexc = int(doc.get("d_n_arvores_excesso") or 0)
    if nexc:
        ev.append(Evidencia(tipo="texto", descricao=f"{nexc} árvore(s) com volume explorado > 110% do autorizado na própria árvore (contexto)", valor=float(nexc), unidade="árvores", fonte="if100"))
    st = doc.get("status_D") or "nao_avaliado"
    sev = "info"
    if st == "indicio":
        big = (_isnum(inten) and inten > 1.5 * INTENSIDADE_MAX_M3_HA) or (_isnum(raz) and raz > 1.25) or bool(doc.get("d_excesso_total"))
        sev = "alta" if big else "media"
    return _flag("D", st, sev, 0.9 if st != "nao_avaliado" else 0.0, regra, ev)


def flag_D_asv(vol_est: Optional[dict], vol_aut: Optional[float]) -> Flag:
    regra = "p10 do volume estimado (área desmatada × estoque/ha, Monte Carlo) > volume autorizado"
    if not _isnum(vol_aut) or not vol_est or not _isnum(vol_est.get("p10")):
        return _flag("D", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Volume autorizado ou estoque por hectare indisponível; volume não estimado.")], tipo="ASV")
    ev = [Evidencia(tipo="metrica", descricao=f"Volume estimado p10 {_fmt(vol_est['p10'])} · p50 {_fmt(vol_est['p50'])} · p90 {_fmt(vol_est['p90'])} m³ para {_fmt(vol_aut)} m³ autorizados",
                    valor=round(float(vol_est["p50"]), 1), unidade="m³", fonte="s2")]
    if vol_est["p10"] > vol_aut:
        return _flag("D", "indicio", "media", 0.7, regra, ev, vol=vol_est, tipo="ASV")
    return _flag("D", "sem_indicio", "info", 0.7, regra, ev, vol=vol_est, tipo="ASV")


# ------------------------------------------------------------------ E
def janela_vs_validade(janela: tuple[str, str], validade: tuple[Optional[str], Optional[str]]) -> str:
    """'dentro' | 'fora' | 'cruza' | 'desconhecido' para um intervalo de imagem vs validade."""
    vi, vf = validade
    if not vi or not vf or not janela or not janela[0] or not janela[1]:
        return "desconhecido"
    a, b = date.fromisoformat(janela[0][:10]), date.fromisoformat(janela[1][:10])
    i, f = date.fromisoformat(vi[:10]), date.fromisoformat(vf[:10])
    if a >= i and b <= f:
        return "dentro"
    if b < i or a > f:
        return "fora"
    return "cruza"


def flag_E_poa(doc: dict) -> Flag:
    regra = "Datas de exploração IF100 fora do intervalo [início, fim] da validade da autorização (limites inclusivos)"
    n = int(doc.get("n_arvores") or 0)
    if n == 0:
        return _flag("E", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Sem datas de exploração declaradas.", fonte="if100")])
    ne, nsd = int(doc.get("e_n_fora_validade") or 0), int(doc.get("n_sem_data") or 0)
    ev = [Evidencia(tipo="metrica", descricao=f"Exploração declarada entre {doc.get('data_expl_min')} e {doc.get('data_expl_max')}", fonte="if100")]
    if ne:
        ev.append(Evidencia(tipo="metrica", descricao=f"{ne} árvore(s) com data de exploração fora da validade", valor=float(ne), unidade="árvores", camada="arvores", fonte="if100"))
    if nsd:
        ev.append(Evidencia(tipo="texto", descricao=f"{nsd} árvore(s) sem data de exploração", valor=float(nsd), unidade="árvores", fonte="if100"))
    st = doc.get("status_E") or "nao_avaliado"
    sev = ("alta" if ne / max(n, 1) >= 0.1 else "media") if st == "indicio" else "info"
    return _flag("E", st, sev, 0.95 if st != "nao_avaliado" else 0.0, regra, ev)


def flag_E_imagem(area_dentro_ha: Optional[float], janela_pre: tuple[str, str], janela_pos: tuple[str, str],
                  validade: tuple[Optional[str], Optional[str]], tipo: str = "ASV") -> Flag:
    """Mudança detectada ocorreu entre o fim da janela pré e o fim da janela pós. Se esse intervalo cruza a validade -> inconclusivo."""
    regra = "Intervalo da mudança (fim da janela pré → fim da janela pós) comparado à validade; intervalo cruzando a fronteira da validade = inconclusivo"
    if area_dentro_ha is None:
        return _flag("E", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Imagem não processada.")], tipo=tipo)
    intervalo = (janela_pre[1], janela_pos[1])
    rel = janela_vs_validade(intervalo, validade)
    ev = [Evidencia(tipo="texto", descricao=f"Mudança observada entre {intervalo[0]} e {intervalo[1]}; validade {validade[0]} a {validade[1]}; área com distúrbio dentro do polígono {_fmt(area_dentro_ha)} ha", fonte="s2")]
    if area_dentro_ha < 1.0:
        return _flag("E", "sem_indicio", "info", 0.6, regra, ev, tipo=tipo)
    if rel == "desconhecido":
        return _flag("E", "nao_avaliado", "info", 0.0, regra, ev, tipo=tipo)
    if rel == "fora":
        return _flag("E", "indicio", "media", 0.7, regra, ev, area=round(area_dentro_ha, 2), tipo=tipo)
    if rel == "cruza":
        return _flag("E", "inconclusivo", "baixa", 0.5, regra, ev, tipo=tipo)
    return _flag("E", "sem_indicio", "info", 0.8, regra, ev, tipo=tipo)


# ------------------------------------------------------------------ F2 / F6
def flag_F2(area_desmatada_ha: Optional[float], area_autorizada_ha: Optional[float]) -> Flag:
    regra = f"Σ área desmatada (dentro + contígua até 100 m do limite) > área autorizada × {F2_TOLERANCIA:.2f}"
    if not _isnum(area_desmatada_ha) or not _isnum(area_autorizada_ha) or area_autorizada_ha <= 0:
        return _flag("F2", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Área desmatada ou autorizada indisponível.")], tipo="ASV")
    ev = [Evidencia(tipo="metrica", descricao=f"{_fmt(area_desmatada_ha)} ha desmatados para {_fmt(area_autorizada_ha)} ha autorizados",
                    valor=round(float(area_desmatada_ha), 2), unidade="ha", camada="mudanca", fonte="s2")]
    if area_desmatada_ha > area_autorizada_ha * F2_TOLERANCIA:
        r = area_desmatada_ha / area_autorizada_ha
        return _flag("F2", "indicio", "alta" if r > 1.25 else "media", 0.8, regra, ev, area=round(area_desmatada_ha, 2), tipo="ASV")
    return _flag("F2", "sem_indicio", "info", 0.8, regra, ev, area=round(area_desmatada_ha, 2), tipo="ASV")


def flag_F6(area_sobre_uc_ti_ha: Optional[float], camadas_disponiveis: bool, tipo: str = "POA") -> Flag:
    regra = "Polígono de mudança sobre Unidade de Conservação, Terra Indígena ou embargo (camadas oficiais)"
    if not camadas_disponiveis or area_sobre_uc_ti_ha is None:
        return _flag("F6", "nao_avaliado", "info", 0.0, regra, [Evidencia(tipo="texto", descricao="Camadas de UC/TI/embargo não integradas nesta versão.")], tipo=tipo)
    ev = [Evidencia(tipo="metrica", descricao=f"{_fmt(area_sobre_uc_ti_ha)} ha de mudança sobre UC/TI", valor=round(area_sobre_uc_ti_ha, 2), unidade="ha", camada="mudanca")]
    if area_sobre_uc_ti_ha >= 1:
        return _flag("F6", "indicio", "alta", 0.8, regra, ev, area=round(area_sobre_uc_ti_ha, 2), tipo=tipo)
    return _flag("F6", "sem_indicio", "info", 0.8, regra, ev, tipo=tipo)
