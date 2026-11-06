import geopandas as gpd
import pandas as pd
import numpy as np
from .common import RAW, OUT, numbers, dates, utm, read_chunks

def normaliza_coordenadas(lat, lon):
    """IF100 publica coordenadas sem sinal, às vezes com lat/lon trocadas e com zeros.
    Amazônia Legal: |lon| em [44, 74], |lat| em [0, 18]. Troca quando |lat| > |lon|; zero = ausente."""
    alat, alon = numbers(lat).abs(), numbers(lon).abs()
    swap = alat > alon
    alat, alon = alat.where(~swap, alon), alon.where(~swap, alat)
    lat, lon = -alat, -alon
    valid = alat.between(0.01, 18) & alon.between(44, 74)
    return lat.where(valid), lon.where(valid)

def localiza_arvores(df, autorizacoes):
    result = []
    for autex, part in df.groupby('autex', sort=False):
        part = part.copy()
        geom = autorizacoes.loc[autex].geometry
        crs = utm(geom)
        polygon = gpd.GeoSeries([geom], crs=4326).to_crs(crs).iloc[0]
        dist = part.to_crs(crs).distance(polygon)
        tested, flipped = False, False
        if (dist.dropna() > 5000).mean() > .5:
            tested = True
            positive = gpd.GeoSeries(gpd.points_from_xy(part.lon, part.lat.abs()), index=part.index, crs=4326)
            alternative = positive.to_crs(crs).distance(polygon)
            if (alternative > 5000).mean() < (dist > 5000).mean() and alternative.median() < dist.median():
                part.geometry = positive; part['lat'] = part.lat.abs(); dist = alternative; flipped = True
        part['sinal_positivo_testado'] = tested
        part['sinal_lat_corrigido'] = flipped
        part['dist_upa_m'] = dist
        part['dentro_upa'] = (dist <= 20).astype('boolean').mask(dist.isna())
        result.append(part)
    return gpd.GeoDataFrame(pd.concat(result, ignore_index=True), crs=4326) if result else df.assign(dist_upa_m=pd.Series(dtype=float), dentro_upa=pd.Series(dtype='boolean'))

def run():
    auth = gpd.read_parquet(OUT / 'autorizacoes.parquet').set_index('autex')
    parts = []
    columns = {'NRO_AUTORIZACAO':'autex','NRO_ARVORE_EXPLORADA':'id','NOME_CIENTIFICO':'especie','NOME_POPULAR':'nome_popular','VOLUME_AUTORIZADO':'vol_autorizado','VOLUME_EXPLORADO':'vol_explorado','DATA_DA_EXPLORACAO':'data_exploracao','PRODUTO':'produto','LATITUDE_ARVORE':'lat','LONGITUDE_ARVORE':'lon'}
    for path in sorted((RAW / 'if100').glob('*.csv')):
        if int(path.stem[-4:]) < 2022: continue
        for chunk in read_chunks(path):
            chunk = chunk[chunk.NRO_AUTORIZACAO.isin(auth.index) & chunk.PRODUTO.fillna('').str.startswith('Tora')]
            part = chunk[list(columns)].rename(columns=columns).copy()
            part['data_exploracao'] = dates(part.data_exploracao)
            part = part[part.data_exploracao.isna() | (part.data_exploracao >= '2022-01-01')]
            parts.append(part)
        print('IF100 lido:', path.name, flush=True)
    df = pd.concat(parts, ignore_index=True).drop_duplicates()
    df['lat'], df['lon'] = normaliza_coordenadas(df.lat, df.lon)
    for col in ['vol_autorizado','vol_explorado']: df[col] = numbers(df[col])
    df['coordenada_valida'] = df.lat.notna() & df.lon.notna()
    geometry = [None if pd.isna(x) or pd.isna(y) else __import__('shapely').Point(x,y) for x,y in zip(df.lon,df.lat)]
    df = gpd.GeoDataFrame(df, geometry=geometry, crs=4326)
    df = localiza_arvores(df, auth)
    df['data_exploracao'] = df.data_exploracao.dt.strftime('%Y-%m-%d')
    df.to_parquet(OUT / 'arvores_if100.parquet', index=False)
    print('IF100:', len(df), 'registros;', int(df.coordenada_valida.sum()), 'coordenadas validas', flush=True)
    return df
