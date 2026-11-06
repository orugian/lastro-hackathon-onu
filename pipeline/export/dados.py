"""Carregamento único (cache em memória) das tabelas processadas usadas pelo export."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
ART = ROOT / "data" / "artifacts"
IMG = PROC / "imagery"
POLO = "AMACRO - Sul do AM + Porto Velho/RO"
_LOCK = threading.Lock()


def nn(x):
    """NaN/NA -> None; numpy -> python."""
    if x is None:
        return None
    try:
        if pd.isna(x):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _mtime(p: Path) -> str:
    try:
        return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
    except OSError:
        return agora()


class Dados:
    def __init__(self):
        self.aut = gpd.read_parquet(PROC / "autorizacoes.parquet").to_crs(4326)
        self.aut["autex"] = self.aut["autex"].astype(str)
        self.aut = self.aut.set_index("autex", drop=False)
        self.regras = pd.read_parquet(PROC / "regras_doc.parquet")
        self.regras["autex"] = self.regras["autex"].astype(str)
        self.regras = self.regras.set_index("autex", drop=False)
        arv = gpd.read_parquet(PROC / "arvores_if100.parquet")
        arv["autex"] = arv["autex"].astype(str)
        self.arv_por_autex = {k: v for k, v in arv.groupby("autex")}
        self.n_arvores_total = len(arv)
        self.vol_total = float(arv["vol_explorado"].sum())
        self.especies = pd.read_parquet(PROC / "poa_especies.parquet")
        self.especies["autex"] = self.especies["autex"].astype(str)
        self.deter = gpd.read_parquet(PROC / "deter.parquet").to_crs(4326)
        self.prodes = gpd.read_parquet(PROC / "prodes.parquet").to_crs(4326)
        self.pre = pd.read_csv(PROC / "pretriagem.csv", dtype={"autex": str})
        self.prov = self._proveniencia()

    def arvores(self, autex):
        g = self.arv_por_autex.get(autex)
        if g is None:
            return gpd.GeoDataFrame({"vol_explorado": [], "dentro_upa": []}, geometry=[], crs=4326)
        return g

    def _proveniencia(self):
        def j(name):
            p = PROC / name
            return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        dj, pj = j("deter.proveniencia.json"), j("prodes.proveniencia.json")
        return {
            "pamgia": dict(id="pamgia", fonte="IBAMA PAMGIA - Polígonos Sinaflor (autorizações)",
                           url="https://pamgia.ibama.gov.br/server/rest/services/SINAFLORGEO/sinaflor_proj_externo_merge_a/FeatureServer/6",
                           consultado_em=_mtime(PROC / "autorizacoes.parquet"), versao=None, licenca="Dados abertos"),
            "if100": dict(id="if100", fonte="IBAMA - Volumes Explorados IF100 (Sinaflor)",
                          url="https://dadosabertos.ibama.gov.br/dataset/volumes-explorados-if-100",
                          consultado_em=_mtime(RAW / "if100.zip"), versao=None, licenca="Dados abertos"),
            "sinaflor": dict(id="sinaflor", fonte="IBAMA - Sinaflor: POA, ASV e UAS (volumes autorizados por espécie)",
                             url="https://dadosabertos.ibama.gov.br/organization/instituto-brasileiro-do-meio-ambiente-e-dos-recursos-naturais-renovaveis",
                             consultado_em=_mtime(RAW / "poa.csv"), versao=None, licenca="Dados abertos"),
            "s2": dict(id="s2", fonte="Copernicus Sentinel-2 L2A (harmonizado) via Google Earth Engine",
                       url="https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED",
                       consultado_em=agora(), versao=None, licenca="Copernicus open"),
            "deter": dict(id="deter", fonte="INPE DETER Amazônia (TerraBrasilis, deter-amz:deter_amz)",
                          url=dj.get("url", "https://terrabrasilis.dpi.inpe.br/geoserver/ows"),
                          consultado_em=dj.get("consultado_em", _mtime(PROC / "deter.parquet")), versao=None, licenca="CC-BY-SA"),
            "prodes": dict(id="prodes", fonte="INPE PRODES Amazônia Legal (TerraBrasilis, yearly_deforestation)",
                           url=pj.get("url", "https://terrabrasilis.dpi.inpe.br/geoserver/ows"),
                           consultado_em=pj.get("consultado_em", _mtime(PROC / "prodes.parquet")), versao=None, licenca="CC-BY-SA"),
            "cbers": dict(id="cbers", fonte="INPE BDC - CBERS-4A WPM 2 m (CB4A-WPM-PCA-FUSED-1)",
                          url="https://data.inpe.br/bdc/stac/v1/collections/CB4A-WPM-PCA-FUSED-1",
                          consultado_em=agora(), versao=None, licenca="CC-BY-SA"),
        }


_D = None


def dados() -> Dados:
    global _D
    with _LOCK:
        if _D is None:
            _D = Dados()
    return _D
