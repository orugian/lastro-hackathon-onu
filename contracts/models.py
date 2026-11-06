"""Contrato de artefatos do Lastro (v1). FONTE ÚNICA DA VERDADE.

O pipeline grava, a API lê e o front consome (ver contracts/types.ts, espelho TS).
Não altere sem avisar o orquestrador. Campos novos opcionais são permitidos; renomear/remover não.

Layout em disco (raiz = data/artifacts ou data/artifacts-mock):
  index.json                         -> Index
  cases/{autex}/dossier.json         -> Dossier
  cases/{autex}/upa.geojson          -> polígono(s) autorizados (FeatureCollection)
  cases/{autex}/buffer.geojson       -> AOI = upa + 2 km, menos outras autorizações
  cases/{autex}/arvores.geojson      -> Points IF100 (props: ArvoreProps)  [POA]
  cases/{autex}/celulas.geojson      -> Polygons 100 m (props: CelulaProps)
  cases/{autex}/mudanca.geojson      -> Polygons de distúrbio detectado (props: MudancaProps)
  cases/{autex}/deter.geojson        -> alertas DETER na AOI (props originais + classe, data)
  cases/{autex}/prodes.geojson       -> PRODES na AOI
  cases/{autex}/img/{id}.png         -> imagens referenciadas em Dossier.imagens
  metrics/detector.json              -> MetricsDetector
  metrics/calibracao.json            -> MetricsCalibracao
  metrics/montecarlo.json            -> dict livre com parâmetros/distribuições globais

Convenções: GeoJSON em EPSG:4326; áreas/distâncias calculadas em UTM SIRGAS2000;
volumes em m³ (volume comercial em tora); áreas em ha; datas ISO 'YYYY-MM-DD'.
Valores desconhecidos = null (nunca 0 inventado).
"""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

TipoAutorizacao = Literal["POA", "ASV", "UAS"]
Severidade = Literal["alta", "media", "baixa", "info"]
SourceMode = Literal["real", "simulado"]
FlagCodigo = Literal[
    "A",   # volume declarado sem lastro observável (indício de esquentamento) - agregado por célula
    "B",   # distúrbio sem declaração (dentro ou fora da UPA)
    "C",   # árvore declarada fora do polígono autorizado (> tolerância)
    "D",   # volume explorado > autorizado, ou intensidade > teto (m³/ha)
    "E",   # exploração/mudança fora da validade
    "F2",  # ASV: área desmatada > área autorizada
    "F6",  # mudança sobre UC/TI/embargo
]
Status = Literal["indicio", "inconclusivo", "sem_indicio", "nao_avaliado"]


class Faixa(BaseModel):
    p10: Optional[float] = None
    p50: Optional[float] = None
    p90: Optional[float] = None


class Validade(BaseModel):
    inicio: Optional[str] = None
    fim: Optional[str] = None


class FlagResumo(BaseModel):
    codigo: FlagCodigo
    titulo: str                      # ex.: "Volume declarado sem lastro na imagem"
    status: Status
    severidade: Severidade
    confianca: float = Field(ge=0, le=1)


class Evidencia(BaseModel):
    tipo: Literal["metrica", "geometria", "imagem", "documento", "texto"]
    descricao: str                   # frase legível, linguagem de triagem
    valor: Optional[float] = None
    unidade: Optional[str] = None
    camada: Optional[str] = None     # nome do geojson/img a destacar no mapa (ex.: "celulas")
    filtro: Optional[dict] = None    # ex.: {"classe": "sem_lastro"}
    fonte: Optional[str] = None      # id em Dossier.proveniencia


class Flag(FlagResumo):
    regra: str                       # descrição da regra aplicada, com limiares
    evidencias: list[Evidencia] = []
    volume_m3: Optional[Faixa] = None
    area_ha: Optional[float] = None


class CaseSummary(BaseModel):
    autex: str                       # nº autorização (Sinaflor) - público
    tipo: TipoAutorizacao
    uf: str
    municipio: str
    centroide: tuple[float, float]   # [lon, lat]
    bbox: tuple[float, float, float, float]  # [minx, miny, maxx, maxy]
    area_autorizada_ha: Optional[float] = None
    validade: Validade = Validade()
    situacao: Optional[str] = None
    volume_autorizado_m3: Optional[float] = None
    volume_declarado_explorado_m3: Optional[float] = None   # IF100 (POA) / DOF (ASV)
    volume_estimado_m3: Faixa = Faixa()                      # pelo que a imagem mostra
    area_disturbio_ha: Optional[float] = None
    area_disturbio_fora_ha: Optional[float] = None
    n_arvores_declaradas: Optional[int] = None
    flags: list[FlagResumo] = []
    score: float = Field(ge=0, le=1)
    source_mode: SourceMode = "real"
    analise_imagem: bool = True      # False = só regras documentais (sem raster)
    processado_em: str


class Index(BaseModel):
    schema_version: str = SCHEMA_VERSION
    gerado_em: str
    polo: str                        # "AMACRO - Sul do AM + Porto Velho/RO"
    totais: dict                     # {"autorizacoes_avaliadas": n, "com_imagem": n, "com_indicio": n, ...}
    casos: list[CaseSummary]


class Imagem(BaseModel):
    id: str                          # ex.: "s2_pre", "s2_pos", "dndvi", "cbers_pre", "cbers_pos", "dl_pred"
    sensor: Literal["Sentinel-2", "CBERS-4A WPM", "Derivado", "Modelo"]
    rotulo: str                      # ex.: "Sentinel-2 · mediana jun-set 2023"
    data: Optional[str] = None       # data ou "2023-06-01/2023-09-30"
    png: str                         # caminho relativo ao diretório do caso, ex.: "img/s2_pre.png"
    bounds: tuple[float, float, float, float]  # [minx, miny, maxx, maxy] EPSG:4326
    resolucao_m: Optional[float] = None
    nuvem_pct: Optional[float] = None
    par: Optional[Literal["pre", "pos"]] = None


class Proveniencia(BaseModel):
    id: str
    fonte: str                       # ex.: "IBAMA - Volumes Explorados IF100"
    url: str
    consultado_em: str
    versao: Optional[str] = None     # data de atualização da fonte
    licenca: Optional[str] = None


class ParametroVolume(BaseModel):
    nome: str
    distribuicao: str                # ex.: "lognormal(mu, sigma)" / "quantil LightGBM"
    valor: Optional[float] = None
    unidade: Optional[str] = None
    origem: str


class Especie(BaseModel):
    nome_cientifico: str
    nome_popular: Optional[str] = None
    volume_autorizado_m3: Optional[float] = None
    volume_explorado_m3: Optional[float] = None
    n_arvores: Optional[int] = None


class Dossier(CaseSummary):
    schema_version: str = SCHEMA_VERSION
    flags_detalhe: list[Flag] = []
    imagens: list[Imagem] = []
    camadas: list[str] = []          # geojsons disponíveis no diretório do caso
    especies: list[Especie] = []
    parametros_volume: list[ParametroVolume] = []
    modelo: dict = {}                # {"detector": "lightgbm-v1", "calibracao": "lgbm-quantil-v1", ...}
    proveniencia: list[Proveniencia] = []
    limitacoes: list[str] = []
    linha_do_tempo: list[dict] = []  # [{"data": "...", "evento": "...", "fonte": "..."}]
    legal_conclusion: Literal[False] = False
    aviso: str = "Resultado experimental de triagem. Não constitui prova nem auto de infração."


# ---- Propriedades de features ----
class ArvoreProps(BaseModel):
    id: str
    especie: str
    vol_autorizado: Optional[float] = None
    vol_explorado: Optional[float] = None
    data_exploracao: Optional[str] = None
    dentro_upa: bool = True


CelulaClasse = Literal["consistente", "sem_lastro", "nao_declarado", "sem_atividade", "nao_observavel"]


class CelulaProps(BaseModel):
    id: str
    vol_declarado: float             # m³ declarados (IF100) na célula
    n_arvores: int
    disturbio_frac: Optional[float]  # fração da célula com distúrbio (0-1), null se nuvem
    vol_p10: Optional[float] = None
    vol_p50: Optional[float] = None
    vol_p90: Optional[float] = None
    classe: CelulaClasse
    dentro_upa: bool = True


class MudancaProps(BaseModel):
    id: str
    area_ha: float
    prob: float
    dentro_upa: bool
    dist_limite_m: float
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    metodo: str                      # "baseline" | "lightgbm" | "dl"


# ---- Métricas ----
class MetricaModelo(BaseModel):
    nome: str                        # "baseline-otsu", "lightgbm", "prithvi"
    iou: Optional[float] = None
    f1: Optional[float] = None
    precisao: Optional[float] = None
    recall: Optional[float] = None
    matriz_confusao: Optional[list[list[int]]] = None
    n_pixels_teste: Optional[int] = None
    obs: Optional[str] = None


class MetricsDetector(BaseModel):
    protocolo: str                   # ex.: "GroupKFold espacial (blocos 5 km), k=5, rótulos PRODES+DETER"
    rotulos: str
    modelos: list[MetricaModelo]
    selecionado: str
    gerado_em: str


class MetricsCalibracao(BaseModel):
    protocolo: str                   # ex.: "GroupKFold por UPA, k=5"
    n_celulas_treino: int
    n_upas: int
    r2: Optional[float] = None
    mae_m3_ha: Optional[float] = None
    cobertura_p10_p90: Optional[float] = None    # esperado ~0.80
    cobertura_nominal: float = 0.80
    curva: list[dict] = []           # [{"disturbio_frac": x, "p10": , "p50": , "p90": }] para gráfico
    obs: Optional[str] = None
    gerado_em: str
