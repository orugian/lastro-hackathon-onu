import pandas as pd
import geopandas as gpd
from .common import OUT

def calcula(autorizacoes, arvores, especies):
    volumes = especies.groupby('autex').volume_autorizado_m3.sum(min_count=1)
    grouped = dict(tuple(arvores.groupby('autex')))
    rows = []
    for a in autorizacoes.itertuples():
        t = grouped.get(a.autex,arvores.iloc[:0])
        explored = t.vol_explorado.sum(min_count=1)
        authorized = volumes.get(a.autex,float('nan'))
        # C: fora do polígono entre 20 m e 5 km. Acima de 5 km = coordenada inconsistente (qualidade cadastral, reportado à parte)
        outside = (t.dist_upa_m > 20) & (t.dist_upa_m <= 5000)
        incoerente = t.dist_upa_m > 5000
        over = t.vol_explorado > t.vol_autorizado * 1.1
        dt = pd.to_datetime(t.data_exploracao,errors='coerce')
        start,end = pd.to_datetime(a.validade_ini),pd.to_datetime(a.validade_fim)
        invalid_date = ((dt < start) | (dt > end)) & dt.notna()
        intensity = explored/a.area_ha if pd.notna(a.area_ha) and a.area_ha > 0 else float('nan')
        c = bool(outside.any())
        total_excess = bool(pd.notna(explored) and pd.notna(authorized) and explored > authorized)
        # Razão agregada IF100 (Σ explorado / Σ autorizado das mesmas árvores). Diferença por árvore é
        # esperada (cubagem real x inventário); só a agregada > 1,10 é indício (p95 do polo ≈ 1,05).
        aut_if = t.vol_autorizado.sum(min_count=1)
        razao_if100 = explored / aut_if if pd.notna(explored) and pd.notna(aut_if) and aut_if > 0 else float('nan')
        d = bool(total_excess or (pd.notna(razao_if100) and razao_if100 > 1.10) or (pd.notna(intensity) and intensity > 30))
        e = bool(invalid_date.any())
        rows.append(dict(autex=a.autex,tipo=a.tipo,n_arvores=len(t),volume_explorado_m3=explored,volume_autorizado_m3=authorized,
            c_n_fora=int(outside.sum()),c_n_coord_incoerente=int(incoerente.sum()),c_volume_fora_m3=t.loc[outside,'vol_explorado'].sum(min_count=1) if outside.any() else 0.,
            d_n_arvores_excesso=int(over.sum()),d_razao_if100=razao_if100,d_excesso_total=total_excess,intensidade_m3_ha=intensity,
            e_n_fora_validade=int(invalid_date.sum()),n_sem_coordenada=int(t.dist_upa_m.isna().sum()),n_sem_data=int(dt.isna().sum()),
            flag_C=c,flag_D=d,flag_E=e,
            status_C='indicio' if c else 'nao_avaliado' if t.empty or t.dist_upa_m.isna().all() else 'inconclusivo' if t.dist_upa_m.isna().any() else 'sem_indicio',
            status_D='indicio' if d else 'nao_avaliado' if t.empty else 'inconclusivo' if pd.isna(authorized) else 'sem_indicio',
            status_E='indicio' if e else 'nao_avaliado' if t.empty or pd.isna(start) or pd.isna(end) else 'inconclusivo' if dt.isna().any() else 'sem_indicio',
            data_expl_min=dt.min().strftime('%Y-%m-%d') if dt.notna().any() else None,
            data_expl_max=dt.max().strftime('%Y-%m-%d') if dt.notna().any() else None))
    return pd.DataFrame(rows)

def run():
    df = calcula(gpd.read_parquet(OUT/'autorizacoes.parquet'),gpd.read_parquet(OUT/'arvores_if100.parquet'),pd.read_parquet(OUT/'poa_especies.parquet'))
    df.to_parquet(OUT/'regras_doc.parquet',index=False)
    print('Regras documentais:',len(df),'autorizacoes;',df[['flag_C','flag_D','flag_E']].sum().to_dict(),flush=True)
    return df
