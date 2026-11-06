import geopandas as gpd
import pandas as pd
from shapely import make_valid
from shapely.geometry import box
from .common import OUT, BBOX, session, text_key

URL = 'https://pamgia.ibama.gov.br/server/rest/services/SINAFLORGEO/sinaflor_proj_externo_merge_a/FeatureServer/6/query'
MUNICIPIOS = {'AM': {'HUMAITA','LABREA','NOVO ARIPUANA','MANICORE','CANUTAMA'}, 'RO': {'PORTO VELHO','CANDEIAS DO JAMARI'}}

def run():
    features, offset = [], 0
    s = session()
    where = "(uf = 'AM' AND municipio IN ('HUMAITA','HUMAITÁ','LABREA','LÁBREA','NOVO ARIPUANA','NOVO ARIPUANÃ','MANICORE','MANICORÉ','CANUTAMA')) OR (uf = 'RO' AND municipio IN ('PORTO VELHO','CANDEIAS DO JAMARI'))"
    while True:
        r = s.get(URL, params=dict(f='geojson', where=where, outFields='*', outSR=4326,
            resultOffset=offset, resultRecordCount=2000, orderByFields='objectid'), timeout=120)
        r.raise_for_status()
        data = r.json()
        if 'error' in data: raise RuntimeError(data['error'])
        batch = data['features']; features.extend(batch)
        if not data.get('exceededTransferLimit', data.get('properties',{}).get('exceededTransferLimit',False)): break
        if not batch: raise RuntimeError('PAMGIA pagination returned empty page')
        offset += len(batch)
    df = gpd.GeoDataFrame.from_features(features, crs=4326)
    df = df[df.apply(lambda r: text_key(r.municipio) in MUNICIPIOS.get(r.uf, set()),axis=1)].copy()
    df['tipo'] = df.tipo_atividade.map(lambda x: 'POA' if x == 'PMFS/POA' else 'ASV' if 'ASV' in str(x) else 'UAS' if x == 'Uso Alternativo do Solo' else None)
    df = df[df.tipo.notna() & df.nu_autorizacao.notna() & df.geometry.notna()].copy()
    df['autex'] = df.nu_autorizacao.astype(str).str.strip()
    df.geometry = df.geometry.map(make_valid)
    df = df[~df.geometry.is_empty].copy()
    # Multiple parts of the same authorization form one authorized footprint.
    df = df.sort_values('dt_atualizacao').dissolve('autex', aggfunc='last').reset_index()
    for src, dst in [('dt_valid_inicio','validade_ini'),('dt_valid_fim','validade_fim')]:
        df[dst] = pd.to_datetime(df[src], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
    df['area_ha'] = df.area_pamgia_ha
    df['geometria_fora_bbox_polo'] = ~df.intersects(box(*BBOX))
    df.to_parquet(OUT / 'autorizacoes.parquet', index=False)
    print('PAMGIA:', df.tipo.value_counts().to_dict(), flush=True)
    return df
