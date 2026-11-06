import pandas as pd
import geopandas as gpd
from .common import RAW, OUT, read_chunks, numbers

def normalize(df, source):
    df = df.copy()
    df['volume_autorizado_m3'] = numbers(df.volume_autorizado_m3)
    df = df.drop_duplicates(['autex','especie','produto','volume_autorizado_m3'])
    df = df.groupby(['autex','especie'], dropna=False).agg(volume_autorizado_m3=('volume_autorizado_m3',lambda s:s.sum(min_count=1)),nome_popular=('nome_popular','first')).reset_index()
    df['fonte'] = source
    return df

def run():
    auth = gpd.read_parquet(OUT / 'autorizacoes.parquet').set_index('autex')
    pieces = []
    for filename in ['poa.csv','asv.csv','uas.csv']:
        selected = []
        for c in read_chunks(RAW / filename):
            c = c.rename(columns={'PRODUTO_FLORESTAL':'PRODUTO'})
            if 'PRODUTO' not in c.columns: continue
            c = c[c.NRO_AUTORIZACAO.isin(auth.index) & c.PRODUTO.fillna('').str.startswith('Tora')]
            selected.append(c[['NRO_AUTORIZACAO','NOME_CIENTIFICO','NOME_POPULAR','PRODUTO','VOLUME']].rename(columns=dict(NRO_AUTORIZACAO='autex',NOME_CIENTIFICO='especie',NOME_POPULAR='nome_popular',PRODUTO='produto',VOLUME='volume_autorizado_m3')))
        if selected: pieces.append(normalize(pd.concat(selected),filename))
    base = pd.concat(pieces,ignore_index=True).drop_duplicates(['autex','especie'])
    extras = []
    for path in sorted((RAW / 'dof_autorizacoes_csv').glob('*.csv')):
        if not path.stem.endswith(('_uf_AM','_uf_RO')): continue
        for c in read_chunks(path):
            original = c.NRO_DA_AUTORIZACAO_ORIGINAL.str.strip()
            serial = c.NUMERO_DE_SERIE_DA_AUTEX.str.strip()
            c['autex'] = original.where(original.isin(auth.index), serial)
            c = c[c.autex.isin(auth.index) & c.TIPO_DE_PRODUTO.fillna('').str.startswith('Tora') & c.UNIDADE_DE_MEDIDA.str.upper().isin(['M3','M³'])]
            extras.append(c[['autex','NOME_CIENTIFICO','NOME_POPULAR','TIPO_DE_PRODUTO','VOLUME_ORIGINAL_AUTORIZADO']].rename(columns=dict(NOME_CIENTIFICO='especie',NOME_POPULAR='nome_popular',TIPO_DE_PRODUTO='produto',VOLUME_ORIGINAL_AUTORIZADO='volume_autorizado_m3')))
    if extras:
        extra = normalize(pd.concat(extras), 'DOF AUTEX')
        # Supplement missing authorizations; never add overlapping balances to Sinaflor.
        base = pd.concat([base,extra[~extra.autex.isin(base.autex)]],ignore_index=True)
    base.to_parquet(OUT / 'poa_especies.parquet',index=False)
    print('Volumes autorizados:',len(base),'especies/autorizacao',flush=True)
    return base
