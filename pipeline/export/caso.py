"""Processamento completo de um caso com imagem -> data/artifacts/cases/{autex}/ (Dossier + camadas)."""
from __future__ import annotations

import json
import logging
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.geometry import mapping

from contracts.models import Dossier, Evidencia, Imagem
from pipeline.export.dados import ART, IMG, POLO, agora, dados, nn
from pipeline.ingest.common import utm
from pipeline.rules import flags as F
from pipeline.rules.score import parametros_score, score

LOG = logging.getLogger(__name__)
RING_CELULAS_M = 500.0
BUFFER_AOI_M = 2000.0
BUFFER_REDUZIDO_M = 500.0
MAX_AOI_KM = 15.0          # lado máximo da AOI com buffer de 2 km; acima disso usa 500 m
MAX_AOI_ESCALA_KM = 30.0   # acima disso, imagem não avaliada por escala (caso segue só documental)


class EscalaExcedida(RuntimeError):
    pass


def _lado_km(geom_u) -> float:
    minx, miny, maxx, maxy = geom_u.bounds
    return max(maxx - minx, maxy - miny) / 1000.0
MAX_ARVORES = 8000
HOJE = date.today()


# ------------------------------------------------------------------ geojson
def _round(geom, nd=6):
    return shapely.transform(geom, lambda c: np.round(c, nd))


def escrever_fc(path: Path, gdf, props: list[str], simplify_m: float | None = 2.0):
    feats = []
    if gdf is not None and len(gdf):
        g = gdf
        if simplify_m:
            crs = utm(g.to_crs(4326).geometry.union_all())
            g = g.to_crs(crs)
            g = g.set_geometry(g.geometry.simplify(simplify_m, preserve_topology=True))
        g = g.to_crs(4326)
        for _, r in g.iterrows():
            if r.geometry is None or r.geometry.is_empty:
                continue
            feats.append({"type": "Feature", "geometry": mapping(_round(r.geometry)),
                          "properties": {k: nn(r[k]) if not isinstance(r[k], (list, dict)) else r[k] for k in props if k in r}})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False), encoding="utf-8")


def arvores_fc(path: Path, arv, celulas_sem_lastro=None, maximo=MAX_ARVORES, seed=0):
    a = arv
    if len(a) > maximo:
        keep = ~a["dentro_upa"].fillna(False).astype(bool)
        if celulas_sem_lastro is not None and len(celulas_sem_lastro):
            hit = gpd.sjoin(a[["geometry"]], celulas_sem_lastro[["geometry"]].to_crs(4326), predicate="intersects").index.unique()
            keep |= a.index.isin(hit)
        rest = a[~keep]
        n = max(0, maximo - int(keep.sum()))
        a = pd.concat([a[keep], rest.sample(n=min(n, len(rest)), random_state=seed)])
    a = a.copy()
    a["id"] = a["id"].astype(str)
    a["vol_autorizado"] = a["vol_autorizado"].astype(float).round(3)
    a["vol_explorado"] = a["vol_explorado"].astype(float).round(3)
    a["dentro_upa"] = a["dentro_upa"].fillna(False).astype(bool)
    a["dist_upa_m"] = a["dist_upa_m"].astype(float).round(1)
    escrever_fc(path, a, ["id", "especie", "nome_popular", "vol_autorizado", "vol_explorado", "data_exploracao", "dentro_upa", "dist_upa_m"], simplify_m=None)
    return len(a)


# ------------------------------------------------------------------ janelas
def janelas_caso(tipo, data_min, data_max, val_ini, val_fim):
    from pipeline.imagery.s2 import janelas_automaticas
    if tipo == "POA" and (data_min or val_ini):
        pre, pos = janelas_automaticas(data_min, data_max, val_ini)
    else:
        y0 = date.fromisoformat(val_ini).year
        y1 = min(date.fromisoformat(val_fim).year if val_fim else y0, HOJE.year if HOJE.month >= 10 else HOJE.year - 1)
        y1 = max(y1, y0)
        pre, pos = (f"{y0 - 1}-06-01", f"{y0 - 1}-09-30"), (f"{y1}-06-01", f"{y1}-09-30")
    if date.fromisoformat(pos[1]) > HOJE:
        pos = ((HOJE - timedelta(days=120)).isoformat(), HOJE.isoformat())
    if date.fromisoformat(pos[0]) > date.fromisoformat(pos[1]):
        pos = (pos[1], pos[1])
    return pre, pos


# ------------------------------------------------------------------ mudança
def vetorizar_mudanca(prob_path, limiar: float, area_min_ha: float = 0.1) -> gpd.GeoDataFrame:
    """Máscara prob ≥ limiar (já restrita a floresta no pré) -> abertura morfológica 3×3 (remove faixas de 1 pixel)
    -> polígonos com área (ha, UTM do raster) e prob média."""
    import rasterio
    from rasterio.features import rasterize, shapes
    from scipy.ndimage import binary_opening
    from shapely.geometry import shape
    with rasterio.open(prob_path) as src:
        prob = src.read(1).astype("float32")
        nod, tr, crs = src.nodata, src.transform, src.crs
    valid = (prob != nod) & np.isfinite(prob)
    mask = binary_opening(valid & (prob >= limiar), structure=np.ones((3, 3), bool)) & valid
    geoms = [shape(g) for g, v in shapes(mask.astype("uint8"), mask=mask, transform=tr) if v == 1]
    g = gpd.GeoDataFrame(geometry=geoms, crs=crs)
    if not len(g):
        return gpd.GeoDataFrame({"prob": []}, geometry=[], crs=crs)
    g = g[g.area >= area_min_ha * 1e4].reset_index(drop=True)
    if len(g):
        ids = rasterize(((geo, i + 1) for i, geo in enumerate(g.geometry)), out_shape=prob.shape, transform=tr, fill=0, dtype="int32")
        sel = (ids > 0) & mask
        s = np.bincount(ids[sel], weights=prob[sel], minlength=len(g) + 1)
        n = np.bincount(ids[sel], minlength=len(g) + 1)
        g["prob"] = (s / np.maximum(n, 1))[1:]
    else:
        g["prob"] = []
    return g


def poligonos_mudanca(g, upa_u, outras_u, crs, pre, pos):
    if g is None or not len(g):
        return gpd.GeoDataFrame({"id": [], "area_ha": [], "prob": [], "dentro_upa": [], "dist_limite_m": [], "coberto_outra": []},
                                geometry=[], crs=crs)
    g = g.to_crs(crs)
    g["geometry"] = g.geometry.buffer(0)
    rows = []
    for _, r in g.iterrows():
        for dentro, part in ((True, r.geometry.intersection(upa_u)), (False, r.geometry.difference(upa_u))):
            if part.is_empty or part.area < 1000:  # < 0,1 ha
                continue
            if dentro:
                dist, dmin, cob = 0.0, 0.0, False
            else:
                pts = shapely.points(shapely.get_coordinates(part))
                dist = float(shapely.distance(pts, upa_u).max())
                dmin = float(part.distance(upa_u))
                cob = bool(outras_u is not None and part.intersection(outras_u).area > 0.5 * part.area)
            rows.append(dict(geometry=part, area_ha=part.area / 1e4, prob=float(r["prob"]), dentro_upa=dentro,
                             dist_limite_m=round(dist, 1), dist_min_m=round(dmin, 1), coberto_outra=cob))
    m = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs) if rows else gpd.GeoDataFrame(
        {"area_ha": [], "prob": [], "dentro_upa": [], "dist_limite_m": [], "dist_min_m": [], "coberto_outra": []}, geometry=[], crs=crs)
    m["id"] = [str(i + 1) for i in range(len(m))]
    m["data_inicio"], m["data_fim"], m["metodo"] = pre[1], pos[1], "lightgbm"
    m["area_ha"] = m["area_ha"].round(3)
    m["prob"] = m["prob"].round(3)
    return m


# ------------------------------------------------------------------ principal
def processar_caso(autex: str, cbers: bool = False, progress_cb: Optional[Callable[[str, float], None]] = None,
                   out_root: Path = ART, sem_imagem_falha: bool = False) -> Dossier:
    from pipeline.detect.predict import prever
    from pipeline.grid.celulas import agrega_arvores, grade_celulas
    from pipeline.imagery.render import render_probability
    from pipeline.imagery.s2 import baixar_par_s2
    from pipeline.volume.estimar import (classificar_celulas, estimar_celulas, modelo_info, monte_carlo_upa,
                                         patch_s2_utm, volume_corte_raso, limiar_detector, prob_floresta,
                                         avaliar_blocos, bloco_ids)
    import rasterio

    def p(etapa, frac):
        if progress_cb:
            try:
                progress_cb(etapa, frac)
            except Exception:
                pass

    D = dados()
    autex = str(autex)
    if autex not in D.aut.index:
        raise KeyError(f"AUTEX {autex} não encontrada no polo")
    a = D.aut.loc[autex]
    doc = {k: nn(v) for k, v in D.regras.loc[autex].to_dict().items()} if autex in D.regras.index else {}
    tipo = a["tipo"]
    geom = a.geometry.buffer(0)
    crs = utm(geom)
    upa_u = gpd.GeoSeries([geom], crs=4326).to_crs(crs).iloc[0].buffer(0)
    limit_escala = []
    buf_m = BUFFER_AOI_M
    aoi_u = upa_u.buffer(buf_m)
    if _lado_km(aoi_u) > MAX_AOI_KM:
        buf_m = BUFFER_REDUZIDO_M
        aoi_u = upa_u.buffer(buf_m)
        limit_escala.append(f"Autorização extensa (AOI com 2 km > {MAX_AOI_KM:.0f} km de lado): entorno analisado reduzido a {buf_m:.0f} m do limite.")
    if _lado_km(aoi_u) > MAX_AOI_ESCALA_KM:
        raise EscalaExcedida(f"AOI com {_lado_km(aoi_u):.0f} km de lado excede {MAX_AOI_ESCALA_KM:.0f} km")
    aoi_4326 = gpd.GeoSeries([aoi_u], crs=crs).to_crs(4326).iloc[0].buffer(0)
    viz = D.aut[D.aut.intersects(aoi_4326) & (D.aut.autex != autex)]
    outras_u = gpd.GeoSeries(viz.geometry, crs=4326).to_crs(crs).buffer(0).union_all() if len(viz) else None
    buffer_u = upa_u.union(aoi_u.difference(outras_u)) if outras_u is not None else aoi_u
    case = out_root / "cases" / autex
    (case / "img").mkdir(parents=True, exist_ok=True)
    limit, timeline, camadas, imagens = list(limit_escala), [], [], []
    area_aut = nn(a.get("area_ha"))
    val_ini, val_fim = nn(a.get("validade_ini")), nn(a.get("validade_fim"))
    arv = D.arvores(autex)
    n_arv = int(doc.get("n_arvores") or 0)

    # 1. imagem
    p("Baixando Sentinel-2", 0.15)
    from pipeline.volume.janelas import janelas_sazonais
    pre, pos, lim_jan = janelas_sazonais(tipo, nn(doc.get("data_expl_min")), nn(doc.get("data_expl_max")), val_ini, val_fim)
    limit += lim_jan
    patch_s2_utm()
    idir = IMG / autex
    idir.mkdir(parents=True, exist_ok=True)
    if (idir / "s2_stack.tif").exists() and (idir / "s2_meta.json").exists():
        old = json.loads((idir / "s2_meta.json").read_text(encoding="utf-8"))
        if old.get("pre") != list(pre) or old.get("pos", [None])[0] != pos[0]:
            shutil.rmtree(idir); idir.mkdir(parents=True)
    try:
        meta = baixar_par_s2(autex, aoi_4326, pre, pos, idir)
    except ValueError as exc:
        if "different inputs" not in str(exc):
            raise
        shutil.rmtree(idir); idir.mkdir(parents=True)
        meta = baixar_par_s2(autex, aoi_4326, pre, pos, idir)
    pos = tuple(meta["pos"])
    stack = idir / "s2_stack.tif"
    p("Detectando distúrbio (LightGBM)", 0.45)
    if not (idir / "prob.tif").exists() or (idir / "prob.tif").stat().st_mtime < stack.stat().st_mtime:
        prever(stack, idir)
    deter_aoi = D.deter[D.deter.intersects(aoi_4326)].copy()
    prodes_aoi = D.prodes[D.prodes.intersects(aoi_4326)].copy()
    # máscara de floresta no pré: NDVI pré ≥ 0,7 e fora de PRODES até o ano da janela pré
    flo = prob_floresta(stack, idir / "prob.tif", idir / "prob_floresta.tif", prodes_aoi, int(pre[0][:4]))
    probf = idir / "prob_floresta.tif"

    # 2. mudança
    mud = poligonos_mudanca(vetorizar_mudanca(probf, limiar_detector()), upa_u, outras_u, crs, pre, pos)
    area_dentro = float(mud.loc[mud.dentro_upa.astype(bool), "area_ha"].sum()) if len(mud) else 0.0
    fora_ok = mud[(~mud.dentro_upa.astype(bool)) & (mud.dist_limite_m > F.TOL_BORDA_M) & (mud.prob >= F.PROB_MIN_B)
                  & (mud.area_ha >= F.AREA_MIN_POLIGONO_HA) & (~mud.coberto_outra.astype(bool)) & (mud.dist_min_m <= F.B_ADJACENCIA_M)] if len(mud) else mud
    area_fora = float(fora_ok["area_ha"].sum()) if len(fora_ok) else 0.0
    area_buffer_ha = float(buffer_u.difference(upa_u).area / 1e4)
    limit.append(f"Máscara de floresta: só conta distúrbio em pixel com NDVI pré ≥ {flo['ndvi_min']} e fora de PRODES até {flo['ano_pre']}; "
                 f"{100*flo['frac_floresta_pre']:.0f}% da AOI observável era floresta no pré.")
    info = modelo_info()

    # 3. células + volume (POA)
    cel, mc = None, None
    vol_est = {}
    vol_fora = None
    parametros = []
    p("Estimando volume por célula", 0.6)
    if tipo == "POA":
        ring = upa_u.buffer(RING_CELULAS_M).difference(upa_u)
        if outras_u is not None:
            ring = ring.difference(outras_u)
        cin = grade_celulas(gpd.GeoSeries([upa_u], crs=crs).to_crs(4326).iloc[0], 100)
        cin["dentro_upa"] = True
        parts = [cin]
        if not ring.is_empty:
            cout = grade_celulas(gpd.GeoSeries([ring], crs=crs).to_crs(4326).iloc[0], 100)
            cout["dentro_upa"] = False
            cout["id"] = cout["id"] + "_f"
            parts.append(cout)
        cel = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs=4326)
        cel = agrega_arvores(cel, arv[arv.geometry.notna()] if len(arv) else arv)
        cel = estimar_celulas(cel, stack, probf)
        cel = classificar_celulas(cel)
        mc = monte_carlo_upa(cel, n=10000, seed=0)
        blocos = avaliar_blocos(cel)
        # células destacadas no mapa = células com árvores dentro de blocos sem_lastro
        bl_sl = set(blocos.loc[blocos.sem_lastro, "bloco"])
        if len(cel):
            cb = pd.Series(bloco_ids(cel["id"]), index=cel.index)
            obs = cel.classe != "nao_observavel"
            cel.loc[(cel.classe == "sem_lastro") & ~cb.isin(bl_sl), "classe"] = "consistente"
            cel.loc[obs & cel.dentro_upa & cb.isin(bl_sl) & (cel.n_arvores > 0) & (cel.vol_declarado > cel.vol_p50), "classe"] = "sem_lastro"
        vol_est = {k: round(v, 1) for k, v in mc["upa"].items()}
        parametros += [
            dict(nome="Volume por célula de 1 ha a partir da imagem", distribuicao="quantis LightGBM q10/q50/q90 + ajuste conformal (CQR)",
                 valor=info.get("conformal_q_m3_ha"), unidade="m³/ha (ajuste conformal)", origem=f"{info['calibracao']} · calibração IF100 em {info.get('n_upas') or 'n/d'} UPAs sem indício"),
            dict(nome="Fator comum de escala por UPA", distribuicao=f"lognormal(0, {mc['sigma_upa']:.2f})", valor=mc["sigma_upa"], unidade=None,
                 origem="dispersão log declarado/estimado por UPA (validação cruzada)"),
            dict(nome="Monte Carlo", distribuicao="CDF linear por partes pelos quantis de cada célula", valor=float(mc["n"]), unidade="amostras", origem="seed 0"),
        ]
        nobs = cel[cel.dentro_upa & (cel.classe == "nao_observavel")]
        if len(nobs):
            limit.append(f"Nuvem/sem dado: {len(nobs)} de {int(cel.dentro_upa.sum())} células da UPA ({100*len(nobs)/max(1,int(cel.dentro_upa.sum())):.0f}%) não observáveis (classe nao_observavel); volume dessas células não entra na estimativa.")
    else:
        estoque = None
        va = nn(doc.get("volume_autorizado_m3"))
        if va and area_aut:
            estoque = va / area_aut
        # F2: dentro + fora contígua (partes a até 100 m do limite, não cobertas por outra autorização)
        contig = mud[(~mud.dentro_upa.astype(bool)) & (~mud.coberto_outra.astype(bool))] if len(mud) else mud
        if len(contig):
            contig = contig[contig.geometry.distance(upa_u) <= 100]
        # só a parte contígua até 500 m do limite (evita somar desmatamento regional que apenas encosta no polígono)
        anel = upa_u.buffer(500).difference(upa_u)
        area_contig = float(contig.geometry.intersection(anel).area.sum() / 1e4) if len(contig) else 0.0
        area_desm = area_dentro + area_contig
        r = volume_corte_raso(area_desm, estoque, None)
        vol_est = {k: (round(r[k], 1) if r[k] is not None else None) for k in ("p10", "p50", "p90")}
        parametros += r["parametros"]
        if estoque is None:
            limit.append("Estoque por hectare indisponível (sem volume autorizado na AUTEX e GEDI não integrado): volume de corte raso não estimado (D = não avaliado).")
        if area_fora > 0 and estoque:
            rf = volume_corte_raso(area_fora, estoque, None)
            vol_fora = {k: rf[k] for k in ("p10", "p50", "p90")}

    # 4. flags
    p("Aplicando regras", 0.75)
    deter_u = deter_aoi.to_crs(crs)
    mud_valid = mud
    if tipo == "POA":
        fl = [F.flag_A(cel, mc, info.get("cobertura_bloco") or info.get("cobertura_celula"), n_arv, blocos=blocos,
                       frac_min=info.get("a_frac_excesso_min", F.A_FRAC_MIN)),
              F.flag_B(mud_valid, cel, deter_u, mc, "POA", area_upa_ha=area_aut, area_buffer_ha=area_buffer_ha),
              F.flag_C(doc), F.flag_D_poa(doc, area_aut)]
        fe = F.flag_E_poa(doc)
        fe_img = F.flag_E_imagem(area_dentro, pre, pos, (val_ini, val_fim), "POA")
        if fe.status != "indicio" and fe_img.status == "indicio" and n_arv:
            fe = fe_img
        elif fe_img.status in ("indicio", "inconclusivo"):
            fe.evidencias.append(Evidencia(tipo="texto", descricao="Imagem: " + fe_img.evidencias[0].descricao + f" (relação com a validade: {fe_img.status})", fonte="s2"))
        fl.append(fe)
    else:
        fl = [F.flag_B(mud_valid, None, deter_u, None, tipo, vol_fora=vol_fora, area_upa_ha=area_aut, area_buffer_ha=area_buffer_ha),
              F.flag_F2(area_desm, area_aut, area_buffer_ha),
              F.flag_D_asv(vol_est if vol_est.get("p10") is not None else None, nn(doc.get("volume_autorizado_m3")),
                           suspeito=F.area_suspeita(area_desm, area_aut, area_buffer_ha)),
              F.flag_E_imagem(area_dentro, pre, pos, (val_ini, val_fim), tipo)]
    fl.append(F.flag_F6(None, False, tipo))
    sc = score(fl)

    # 5. imagens
    p("Gerando imagens", 0.85)
    b = list(meta["bounds_4326"])
    for nome in ("s2_pre.png", "s2_pos.png", "dndvi.png"):
        if (idir / nome).exists():
            shutil.copy2(idir / nome, case / "img" / nome)
    imagens += [
        Imagem(id="s2_pre", sensor="Sentinel-2", rotulo=f"Sentinel-2 · mediana {pre[0]} a {pre[1]}", data=f"{pre[0]}/{pre[1]}", png="img/s2_pre.png",
               bounds=b, resolucao_m=10, nuvem_pct=round(meta.get("nuvem_pct_pre", 0), 1), par="pre"),
        Imagem(id="s2_pos", sensor="Sentinel-2", rotulo=f"Sentinel-2 · mediana {pos[0]} a {pos[1]}", data=f"{pos[0]}/{pos[1]}", png="img/s2_pos.png",
               bounds=b, resolucao_m=10, nuvem_pct=round(meta.get("nuvem_pct_pos", 0), 1), par="pos"),
        Imagem(id="dndvi", sensor="Derivado", rotulo="Queda de NDVI (pós − pré)", data=f"{pre[1]}/{pos[1]}", png="img/dndvi.png", bounds=b, resolucao_m=10),
    ]
    with rasterio.open(probf) as src:
        pr = src.read(1).astype("float32")
        pr[pr == src.nodata] = np.nan
        rp = render_probability(pr, src.transform, src.crs, case / "img" / "prob.png", threshold=limiar_detector())
    imagens.append(Imagem(id="prob", sensor="Modelo", rotulo=f"Distúrbio sobre floresta no pré, prob ≥ {limiar_detector():.2f} (LightGBM)", data=f"{pre[1]}/{pos[1]}",
                          png="img/prob.png", bounds=rp["bounds_4326"], resolucao_m=10))
    prov = ["pamgia", "sinaflor", "s2", "deter", "prodes"] + (["if100"] if n_arv else [])
    if cbers:
        p("Recortando CBERS-4A", 0.9)
        from pipeline.imagery.cbers import recorte_cbers
        ok = 0
        for par, win in (("pre", pre), ("pos", pos)):
            mid = (date.fromisoformat(win[0]) + (date.fromisoformat(win[1]) - date.fromisoformat(win[0])) / 2).isoformat()
            try:
                cm = recorte_cbers(aoi_4326, mid, idir / f"cbers_{par}.png")
            except Exception as exc:
                cm = None
                LOG.warning("CBERS %s %s: %s", autex, par, exc)
            if cm:
                shutil.copy2(idir / f"cbers_{par}.png", case / "img" / f"cbers_{par}.png")
                imagens.append(Imagem(id=f"cbers_{par}", sensor="CBERS-4A WPM", rotulo=f"CBERS-4A WPM 2 m · {cm['data']}", data=cm["data"],
                                      png=f"img/cbers_{par}.png", bounds=cm["bounds_4326"], resolucao_m=2,
                                      nuvem_pct=round(cm.get("brilho_nuvem_pct", 0), 1), par=par))
                timeline.append({"data": cm["data"], "evento": f"Imagem CBERS-4A WPM ({par})", "fonte": "cbers"})
                ok += 1
        if ok:
            prov.append("cbers")
        if ok < 2:
            limit.append("CBERS-4A WPM: par completo não encontrado (cobertura > 90% e baixa nebulosidade) nas janelas ±120 dias; comparação em 2 m indisponível.")
    else:
        limit.append("CBERS-4A WPM 2 m não processado para este caso (reservado aos 5 casos de maior score).")

    # 6. camadas
    p("Exportando camadas", 0.93)
    upa_g = gpd.GeoDataFrame({"autex": [autex], "tipo": [tipo], "area_ha": [area_aut]}, geometry=[geom], crs=4326)
    escrever_fc(case / "upa.geojson", upa_g, ["autex", "tipo", "area_ha"])
    escrever_fc(case / "buffer.geojson", gpd.GeoDataFrame({"descricao": [f"UPA + {buf_m/1000:g} km, menos outras autorizações"]}, geometry=[buffer_u], crs=crs), ["descricao"], 5)
    camadas += ["upa", "buffer"]
    if tipo == "POA":
        sl = cel[cel.classe == "sem_lastro"]
        n_exp = arvores_fc(case / "arvores.geojson", arv, sl)
        if n_exp < len(arv):
            limit.append(f"Mapa de árvores amostrado: {n_exp} de {len(arv)} pontos (todas as árvores fora da UPA e em células sem_lastro preservadas).")
        camadas.append("arvores")
        cc = cel.copy()
        for k in ("vol_declarado", "vol_p10", "vol_p50", "vol_p90"):
            cc[k] = cc[k].astype(float).round(2)
        cc["disturbio_frac"] = cc["disturbio_frac"].astype(float).round(3)
        cc["frac_valida"] = cc["frac_valida"].astype(float).round(2)
        cc["n_arvores"] = cc["n_arvores"].astype(int)
        cc.loc[cc.classe == "nao_observavel", "disturbio_frac"] = np.nan
        escrever_fc(case / "celulas.geojson", cc, ["id", "vol_declarado", "n_arvores", "disturbio_frac", "vol_p10", "vol_p50", "vol_p90", "classe", "dentro_upa", "frac_valida"], None)
        camadas.append("celulas")
        cel.drop(columns="geometry").to_parquet(IMG / autex / "celulas.parquet")
    escrever_fc(case / "mudanca.geojson", mud, ["id", "area_ha", "prob", "dentro_upa", "dist_limite_m", "dist_min_m", "data_inicio", "data_fim", "metodo", "coberto_outra"], 2)
    escrever_fc(case / "deter.geojson", deter_aoi, ["classe", "data", "gid"], 5)
    escrever_fc(case / "prodes.geojson", prodes_aoi, ["classe", "ano", "image_date", "main_class"], 5)
    camadas += ["mudanca", "deter", "prodes"]

    # 7. linha do tempo, espécies, limitações
    rotulo = "POA" if tipo == "POA" else tipo
    if val_ini:
        timeline.append({"data": val_ini, "evento": f"Início da validade da {rotulo}", "fonte": "pamgia"})
    if val_fim:
        timeline.append({"data": val_fim, "evento": "Fim da validade", "fonte": "pamgia"})
    if doc.get("data_expl_min"):
        timeline.append({"data": doc["data_expl_min"], "evento": "Primeira árvore declarada como explorada", "fonte": "if100"})
    if doc.get("data_expl_max"):
        timeline.append({"data": doc["data_expl_max"], "evento": "Última árvore declarada como explorada", "fonte": "if100"})
    timeline += [{"data": pre[0], "evento": f"Início da janela Sentinel-2 pré ({pre[0]} a {pre[1]})", "fonte": "s2"},
                 {"data": pos[0], "evento": f"Início da janela Sentinel-2 pós ({pos[0]} a {pos[1]})", "fonte": "s2"}]
    if len(deter_aoi):
        dupa = deter_aoi[deter_aoi.intersects(geom)]
        for _, r in dupa.sort_values("data").tail(6).iterrows():
            timeline.append({"data": r["data"], "evento": f"Alerta DETER {r['classe']} dentro da autorização", "fonte": "deter"})
        rest = deter_aoi[~deter_aoi.index.isin(dupa.index)]
        if len(rest):
            timeline.append({"data": rest["data"].max(), "evento": f"{len(rest)} alerta(s) DETER no entorno de 2 km desde {rest['data'].min()}; mais recente nesta data (proximidade não implica vínculo)", "fonte": "deter"})
    timeline = sorted([t for t in timeline if t.get("data")], key=lambda t: t["data"])

    especies = []
    if len(arv):
        e = arv.groupby("especie").agg(vol=("vol_explorado", "sum"), n=("id", "size"), pop=("nome_popular", "first")).sort_values("vol", ascending=False).head(10)
        aut_e = D.especies[D.especies.autex == autex].groupby("especie").volume_autorizado_m3.sum()
        for sp, r in e.iterrows():
            especies.append(dict(nome_cientifico=sp, nome_popular=nn(r["pop"]), volume_autorizado_m3=nn(round(float(aut_e[sp]), 2)) if sp in aut_e.index else None,
                                 volume_explorado_m3=round(float(r["vol"]), 2), n_arvores=int(r["n"])))

    limit += [
        f"Janelas Sentinel-2: pré {pre[0]} a {pre[1]}; pós {pos[0]} a {pos[1]}. Nuvem sem observação limpa: {meta.get('nuvem_pct_pre', 0):.1f}% (pré) e {meta.get('nuvem_pct_pos', 0):.1f}% (pós); cenas na mediana: {meta.get('n_cenas_pre')} e {meta.get('n_cenas_pos')}.",
        "A mudança detectada é datada apenas pelo intervalo entre as janelas; não há data exata do evento.",
        "Detector LightGBM treinado com rótulos PRODES/DETER (corte raso e degradação); recall para exploração seletiva é baixo (clareiras de árvore isolada de 200–600 m² são sub-pixel e fecham em meses). Ausência de distúrbio na imagem não prova ausência de exploração.",
        "Camadas de UC/TI/embargo não integradas: F6 não avaliado.",
    ]
    if tipo == "POA":
        limit.append(f"Calibração imagem→volume: {info['calibracao']}; o indício A é agregado por célula de 1 ha e por UPA, nunca por árvore.")
    ninc = int(doc.get("c_n_coord_incoerente") or 0)
    if ninc:
        limit.append(f"Qualidade cadastral: {ninc} árvore(s) IF100 com coordenada a mais de 5 km do polígono (coordenada incoerente); não computadas como indício C.")

    modelo = {"detector": f"lightgbm-v1 (limiar {limiar_detector():.2f})", "calibracao": info["calibracao"],
              "score": "1 − exp(−Σ peso × severidade × confiança)", "s2_meta": {k: meta.get(k) for k in ("crs", "n_cenas_pre", "n_cenas_pos", "n_cenas_limpas_pre", "n_cenas_limpas_pos")}}
    if mc:
        modelo["monte_carlo_upa"] = {k: mc[k] for k in ("upa", "sem_lastro_excesso", "nao_declarado", "nao_declarado_fora", "declarado_upa_m3", "prob_declarado_acima_estimado", "n_celulas", "sigma_upa")}
        modelo["celulas_por_classe"] = cel[cel.dentro_upa].classe.value_counts().to_dict()
        modelo["blocos_9ha"] = {"n": int(len(blocos)), "sem_lastro": int(blocos.sem_lastro.sum()),
                                "excesso_m3": round(float(blocos.excesso.sum()), 1), "sigma_bloco": info.get("sigma_bloco")}
    modelo["mascara_floresta"] = flo
    modelo["area_buffer_ha"] = round(area_buffer_ha, 1)
    parametros += [dict(nome="Tolerância de borda", distribuicao="fixo", valor=F.TOL_BORDA_M, unidade="m", origem="2 pixels Sentinel-2 / erro de GPS"),
                   dict(nome="Teto de intensidade", distribuicao="fixo", valor=F.INTENSIDADE_MAX_M3_HA, unidade="m³/ha", origem="regra D")]
    parametros += parametros_score()

    d = Dossier(
        autex=autex, tipo=tipo, uf=a["uf"], municipio=a["municipio"],
        centroide=(round(geom.centroid.x, 6), round(geom.centroid.y, 6)), bbox=tuple(round(v, 6) for v in geom.bounds),
        area_autorizada_ha=round(area_aut, 2) if area_aut else None, validade={"inicio": val_ini, "fim": val_fim},
        situacao=nn(a.get("status_autorizacao")),
        volume_autorizado_m3=nn(round(doc["volume_autorizado_m3"], 2)) if nn(doc.get("volume_autorizado_m3")) else None,
        volume_declarado_explorado_m3=round(float(doc["volume_explorado_m3"]), 2) if nn(doc.get("volume_explorado_m3")) else None,
        volume_estimado_m3=vol_est, area_disturbio_ha=round(area_dentro, 2), area_disturbio_fora_ha=round(area_fora, 2),
        n_arvores_declaradas=n_arv if tipo == "POA" else None,
        flags=[f.model_dump(include={"codigo", "titulo", "status", "severidade", "confianca"}) for f in fl], score=sc,
        source_mode="real", analise_imagem=True, processado_em=agora(),
        flags_detalhe=fl, imagens=imagens, camadas=camadas, especies=especies, parametros_volume=parametros, modelo=modelo,
        proveniencia=[D.prov[k] for k in prov], limitacoes=limit, linha_do_tempo=timeline,
    )
    Dossier.model_validate(d.model_dump())
    (case / "dossier.json").write_text(json.dumps(d.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    p("Concluído", 1.0)
    return d


# ------------------------------------------------------------------ só documental
def caso_documental(autex: str, out_root: Path = ART, escrever: bool = True) -> Dossier:
    D = dados()
    a = D.aut.loc[autex]
    doc = {k: nn(v) for k, v in D.regras.loc[autex].to_dict().items()} if autex in D.regras.index else {}
    tipo = a["tipo"]
    geom = a.geometry
    n_arv = int(doc.get("n_arvores") or 0)
    if tipo == "POA":
        fl = [F.flag_C(doc), F.flag_D_poa(doc, nn(a.get("area_ha"))), F.flag_E_poa(doc)]
    else:
        fl = [F._flag("C", "nao_avaliado", "info", 0.0, "Árvores IF100 fora do polígono (não se aplica a corte raso sem IF100)", tipo=tipo),
              F._flag("D", "nao_avaliado", "info", 0.0, "Volume estimado por imagem > volume autorizado (requer análise de imagem)", tipo=tipo),
              F._flag("E", "nao_avaliado", "info", 0.0, "Mudança fora da validade (requer análise de imagem)", tipo=tipo)]
    sc = score(fl)
    especies = []
    arv = D.arvores(autex)
    if len(arv):
        e = arv.groupby("especie").agg(vol=("vol_explorado", "sum"), n=("id", "size"), pop=("nome_popular", "first")).sort_values("vol", ascending=False).head(10)
        aut_e = D.especies[D.especies.autex == autex].groupby("especie").volume_autorizado_m3.sum()
        for sp, r in e.iterrows():
            especies.append(dict(nome_cientifico=sp, nome_popular=nn(r["pop"]), volume_autorizado_m3=nn(round(float(aut_e[sp]), 2)) if sp in aut_e.index else None,
                                 volume_explorado_m3=round(float(r["vol"]), 2), n_arvores=int(r["n"])))
    val_ini, val_fim = nn(a.get("validade_ini")), nn(a.get("validade_fim"))
    tl = [{"data": val_ini, "evento": "Início da validade", "fonte": "pamgia"}, {"data": val_fim, "evento": "Fim da validade", "fonte": "pamgia"}]
    if doc.get("data_expl_min"):
        tl += [{"data": doc["data_expl_min"], "evento": "Primeira árvore declarada como explorada", "fonte": "if100"},
               {"data": doc["data_expl_max"], "evento": "Última árvore declarada como explorada", "fonte": "if100"}]
    tl = sorted([t for t in tl if t["data"]], key=lambda t: t["data"])
    lim = ["Análise somente documental (IF100 × autorização); imagem de satélite não processada para esta autorização."]
    if not n_arv and tipo == "POA":
        lim.append("Sem registros IF100 (2022+) para esta autorização: regras C, D e E não avaliadas.")
    ninc = int(doc.get("c_n_coord_incoerente") or 0)
    if ninc:
        lim.append(f"Qualidade cadastral: {ninc} árvore(s) IF100 com coordenada a mais de 5 km do polígono (coordenada incoerente).")
    d = Dossier(
        autex=autex, tipo=tipo, uf=a["uf"], municipio=a["municipio"],
        centroide=(round(geom.centroid.x, 6), round(geom.centroid.y, 6)), bbox=tuple(round(v, 6) for v in geom.bounds),
        area_autorizada_ha=round(float(a["area_ha"]), 2) if nn(a.get("area_ha")) else None, validade={"inicio": val_ini, "fim": val_fim},
        situacao=nn(a.get("status_autorizacao")),
        volume_autorizado_m3=round(float(doc["volume_autorizado_m3"]), 2) if nn(doc.get("volume_autorizado_m3")) else None,
        volume_declarado_explorado_m3=round(float(doc["volume_explorado_m3"]), 2) if nn(doc.get("volume_explorado_m3")) else None,
        n_arvores_declaradas=n_arv if tipo == "POA" else None,
        flags=[f.model_dump(include={"codigo", "titulo", "status", "severidade", "confianca"}) for f in fl], score=sc,
        analise_imagem=False, processado_em=agora(), flags_detalhe=fl, camadas=["upa"] + (["arvores"] if len(arv) else []),
        especies=especies, parametros_volume=parametros_score(), modelo={"score": "1 − exp(−Σ peso × severidade × confiança)"},
        proveniencia=[D.prov[k] for k in (["pamgia", "sinaflor"] + (["if100"] if n_arv else []))], limitacoes=lim, linha_do_tempo=tl,
    )
    if escrever:
        case = out_root / "cases" / autex
        case.mkdir(parents=True, exist_ok=True)
        escrever_fc(case / "upa.geojson", gpd.GeoDataFrame({"autex": [autex], "tipo": [tipo]}, geometry=[geom], crs=4326), ["autex", "tipo"])
        if len(arv):
            arvores_fc(case / "arvores.geojson", arv, None, maximo=3000)
        (case / "dossier.json").write_text(json.dumps(d.model_dump(), ensure_ascii=False, indent=1), encoding="utf-8")
    return d
