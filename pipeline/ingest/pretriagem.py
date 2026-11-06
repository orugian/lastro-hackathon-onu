import geopandas as gpd
import pandas as pd
from shapely.geometry import box
from .common import OUT, utm, BBOX

def ranking(auth, rules, deter, prodes):
    df = auth.merge(rules.drop(columns='tipo'),on='autex',validate='one_to_one')
    year = pd.to_datetime(df.validade_ini).dt.year
    mask_poa = df.tipo.eq('POA') & year.between(2022,2025) & df.n_arvores.ge(200) & df.area_ha.between(100,5000)
    mask_asv = df.tipo.isin(['ASV','UAS']) & year.ge(2022) & df.area_ha.between(20,2000)
    df = df[mask_poa | mask_asv].copy()
    df['n_deter_buffer'] = pd.Series(0,index=df.index,dtype='Int64'); df['n_prodes_buffer'] = pd.Series(0,index=df.index,dtype='Int64')
    projected = {}
    for idx,a in df.iterrows():
        crs = utm(a.geometry)
        if crs not in projected: projected[crs] = (deter.to_crs(crs),prodes.to_crs(crs))
        buffer = gpd.GeoSeries([a.geometry],crs=4326).to_crs(crs).iloc[0].buffer(2000)
        coverage = gpd.GeoSeries([box(*BBOX)],crs=4326).to_crs(crs).iloc[0]
        if not coverage.covers(buffer):
            df.loc[idx,['n_deter_buffer','n_prodes_buffer']] = pd.NA
            continue
        for col,layer in zip(['n_deter_buffer','n_prodes_buffer'],projected[crs]):
            df.loc[idx,col] = len(layer.sindex.query(buffer,predicate='intersects'))
    days = (pd.to_datetime(df.data_expl_max)-pd.to_datetime(df.data_expl_min)).dt.days
    df['score_pre'] = (df.flag_C.astype(int)*20 + df.flag_D.astype(int)*25 + df.flag_E.astype(int)*20
        + df.n_deter_buffer.fillna(0).clip(upper=10)*2 + df.n_prodes_buffer.fillna(0).clip(upper=10)*df.tipo.ne('POA')
        + days.le(90).fillna(False).astype(int)*10)
    df['motivo'] = df.apply(lambda a: '; '.join([f'indicio documental {code}' for code in ['C','D','E'] if a[f'flag_{code}']] + [('cobertura INPE incompleta: revisar localizacao' if pd.isna(a.n_deter_buffer) else f'{a.n_deter_buffer} alertas DETER no entorno'),f'{a.n_arvores} registros IF100']),axis=1)
    df = df.sort_values(['score_pre','n_arvores','autex'],ascending=[False,False,True])
    df = pd.concat([df[df.tipo.eq('POA')].head(60),df[df.tipo.ne('POA')].head(20)])
    return pd.DataFrame(df[['autex','tipo','uf','municipio','area_ha','validade_ini','validade_fim','n_arvores','data_expl_min','data_expl_max','n_deter_buffer','n_prodes_buffer','score_pre','motivo']])

def run():
    df = ranking(gpd.read_parquet(OUT/'autorizacoes.parquet'),pd.read_parquet(OUT/'regras_doc.parquet'),gpd.read_parquet(OUT/'deter.parquet'),gpd.read_parquet(OUT/'prodes.parquet'))
    df.to_csv(OUT/'pretriagem.csv',index=False)
    return df
